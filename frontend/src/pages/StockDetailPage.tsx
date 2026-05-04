import {type ReactNode, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import {Alert, Card, Col, Empty, Row, Space, Spin, Tabs, Tag, Typography} from 'antd';
import {useParams} from 'react-router-dom';
import {
  type DailyBar,
  getStockBarsRange,
  getStockDetail,
  type StockDetailResponse,
  type StockIndicatorSeries,
} from '../lib/api';

// ---------------------------------------------------------------------------
// Color tokens (from docs/kline-limit-color-design.md, light theme)
// ---------------------------------------------------------------------------
const UP_COLOR = '#E64B4B';          // up_normal fill
const UP_BORDER_COLOR = '#C62828';   // up_normal border
const DOWN_COLOR = '#2FA164';        // down_normal fill
const DOWN_BORDER_COLOR = '#1E7A4C'; // down_normal border
// Limit colors (涨跌停专属颜色)
const UP_LIMIT_COLOR = '#8E24AA';
const UP_LIMIT_BORDER = '#6A1B9A';
const DOWN_LIMIT_COLOR = '#1565C0';
const DOWN_LIMIT_BORDER = '#0D47A1';

const MA_COLORS: Record<string, string> = {
  MA5: '#f5a623',
  MA10: '#7ed321',
  MA20: '#4a90e2',
  MA60: '#9013fe',
};

const KDJ_COLORS = { K: '#f5a623', D: '#7ed321', J: '#cf1322' };
const MACD_COLORS = {DIF: '#2962FF', DEA: '#FF6D00'};
const RSI_COLORS = { RSI6: '#f5a623', RSI12: '#7ed321', RSI24: '#cf1322' };

// Grid percentage positions (used for overlay and chart option)
// Slider lives at top: 0, height: 18px (~2%); kline starts at 8% to leave room for slider + two-line labels
const GRID_POSITIONS = {
  kline: {top: '8%', height: '26%'},
  volume: {top: '38%', height: '13%'},
  macd: {top: '55%', height: '13%'},
  kdj: {top: '72%', height: '13%'},
  rsi: {top: '89%', height: '9%'},
} as const;

const CHART_HEIGHT = 'calc(100vh - 210px)';
const CHART_MIN_HEIGHT = 980;
const GRID_LEFT = '70px';
const GRID_RIGHT = '80px';

// K-line candle width tuning: use wider candles so adjacent gap is about 1-2px.
const KLINE_BAR_WIDTH = '88%';
const KLINE_BAR_MIN_WIDTH = 3;
const KLINE_BAR_MAX_WIDTH = 18;

const SUB_CHART_TITLES = {
  volume: 'VOL',
  macd: 'MACD',
  kdj: 'KDJ',
  rsi: 'RSI',
} as const;

// Backend returns duckdb raw amount sourced from Tushare `amount` (unit: 千元).
// UI should display in 亿元.
const QIANYUAN_PER_YI = 100_000;
const INITIAL_MONTHS_WINDOW = 6;
const LOAD_MORE_MONTHS_STEP = 6;

// Separator lines between panels (bottom edge of each panel = top% + height%)
// kline 8%+26%=34%, volume 38%+13%=51%, macd 55%+13%=68%, kdj 72%+13%=85%
const PANEL_SEPARATORS = ['34%', '51%', '68%', '85%'] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtNum(v: number | null | undefined, decimals = 2): string {
  return v != null ? v.toFixed(decimals) : '--';
}

function fmtVol(v: number): string {
  return v >= 1e8 ? `${(v / 1e8).toFixed(2)}亿手` : `${(v / 1e4).toFixed(0)}万手`;
}

function fmtAmount(v: number | null | undefined): string {
  return v != null ? `${(v / QIANYUAN_PER_YI).toFixed(2)}亿` : '--';
}

function fmtPct(v: number | null | undefined): string {
  return v != null ? `${v.toFixed(2)}%` : '--';
}

function fmtSignedPct(v: number | null | undefined): string {
  if (v == null) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}%`;
}

function colorOf(change: number): string {
  return change >= 0 ? UP_COLOR : DOWN_COLOR;
}

function emptyIndicators(): StockIndicatorSeries {
  return {
    ma5: [], ma10: [], ma20: [], ma60: [],
    volume_ma5: [], volume_ma10: [], volume_ma20: [],
    kdj_k: [], kdj_d: [], kdj_j: [],
    macd_dif: [], macd_dea: [], macd_hist: [],
    rsi6: [], rsi12: [], rsi24: [],
  };
}

// ---------------------------------------------------------------------------
// Indicator info bar types
// ---------------------------------------------------------------------------
interface HoverInfo {
  idx: number;
  bar: DailyBar;
}

interface ZoomRange {
  start: number;
  end: number;
}

function monthKeyOf(date: string): string {
  const d = date.replace(/[^0-9]/g, '');
  if (d.length >= 6) return d.slice(0, 6);
  return date.slice(0, 7);
}

// ---------------------------------------------------------------------------
// Sub-info rows shown inside chart
// ---------------------------------------------------------------------------
function InfoRow({ items }: { items: { label: string; value: string; color?: string }[] }) {
  return (
      <div style={{fontSize: 13, lineHeight: 1.85}}>
      {items.map(({ label, value, color }) => (
          <span key={label} style={{marginRight: 16}}>
          <span style={{ color: '#888' }}>{label}: </span>
          <span style={{ color: color ?? '#333', fontWeight: 500 }}>{value}</span>
        </span>
      ))}
    </div>
  );
}

function PanelFloatCard({
  gridKey,
  title,
  children,
}: {
  gridKey: keyof typeof GRID_POSITIONS;
  title: string;
  children: ReactNode;
}) {
  const pos = GRID_POSITIONS[gridKey];
  return (
    <div
      style={{
        position: 'absolute',
        top: `calc(${pos.top} + 4px)`,
        left: GRID_LEFT,
        zIndex: 16,
        pointerEvents: 'none',
        background: 'rgba(255,255,255,0.86)',
        border: '1px solid rgba(0,0,0,0.18)',
        borderRadius: 8,
        padding: '8px 12px',
        backdropFilter: 'blur(3px)',
      }}
    >
      <div style={{color: '#555', fontSize: 13, fontWeight: 700, marginBottom: 4}}>{title}</div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chart option builder
// Sub-chart order: Volume(1) → MACD(2) → KDJ(3) → RSI(4)
// ---------------------------------------------------------------------------
function buildChartOption(data: StockDetailResponse, zoomRange: ZoomRange) {
  const bars = data.daily_bars;
  const ind = data.indicators;
  const dates = bars.map((b) => b.trade_date);

  const maxIdx = Math.max(0, bars.length - 1);
  const zoomStartPct = Math.max(0, Math.min(100, zoomRange.start));
  const zoomEndPct = Math.max(0, Math.min(100, zoomRange.end));
  const visibleStart = Math.max(0, Math.floor((zoomStartPct / 100) * maxIdx));
  const visibleEnd = Math.min(maxIdx, Math.ceil((zoomEndPct / 100) * maxIdx));

  const keyDateIndices = new Set<number>();
  const yearTransitionIndices = new Set<number>();
  const monthBuckets = new Map<string, number[]>();
  for (let i = visibleStart; i <= visibleEnd; i += 1) {
    const key = monthKeyOf(dates[i]);
    const bucket = monthBuckets.get(key);
    if (bucket) {
      bucket.push(i);
    } else {
      monthBuckets.set(key, [i]);
    }
  }
  monthBuckets.forEach((bucket) => {
    const first = bucket[0];
    const mid = bucket[Math.floor((bucket.length - 1) / 2)];
    const last = bucket[bucket.length - 1];
    keyDateIndices.add(first);
    keyDateIndices.add(mid);
    keyDateIndices.add(last);
  });

  [...keyDateIndices]
      .sort((a, b) => a - b)
      .forEach((idx, pos, arr) => {
        if (pos === 0) {
          yearTransitionIndices.add(idx);
          return;
        }
        const cur = dates[idx] ?? '';
        const prev = dates[arr[pos - 1]] ?? '';
        const curYear = cur.replace(/[^0-9]/g, '').slice(0, 4);
        const prevYear = prev.replace(/[^0-9]/g, '').slice(0, 4);
        if (curYear && prevYear && curYear !== prevYear) {
          yearTransitionIndices.add(idx);
        }
      });

  const grids = [
    { top: GRID_POSITIONS.kline.top, left: GRID_LEFT, right: GRID_RIGHT, height: GRID_POSITIONS.kline.height },
    { top: GRID_POSITIONS.volume.top, left: GRID_LEFT, right: GRID_RIGHT, height: GRID_POSITIONS.volume.height },
    { top: GRID_POSITIONS.macd.top, left: GRID_LEFT, right: GRID_RIGHT, height: GRID_POSITIONS.macd.height },
    { top: GRID_POSITIONS.kdj.top, left: GRID_LEFT, right: GRID_RIGHT, height: GRID_POSITIONS.kdj.height },
    { top: GRID_POSITIONS.rsi.top, left: GRID_LEFT, right: GRID_RIGHT, height: GRID_POSITIONS.rsi.height },
  ];

  const xAxisBase = {
    type: 'category' as const,
    data: dates,
    boundaryGap: true,
    axisLine: { lineStyle: { color: '#d0d0d0' } },
    axisTick: { show: false },
    axisLabel: { color: '#666', fontSize: 11 },
    splitLine: { show: false },
  };

  const xAxes = grids.map((_, i) => ({
    ...xAxisBase,
    gridIndex: i,
    position: i === 0 ? ('top' as const) : ('bottom' as const),
    axisLabel: {
      ...xAxisBase.axisLabel,
      show: i === 0,
      ...(i === 0
          ? {
            rich: {
              year: {color: '#333', fontSize: 11, fontWeight: 700, lineHeight: 20, align: 'center' as const},
              date: {color: '#888', fontSize: 10, lineHeight: 15, align: 'center' as const},
            },
            formatter: (_value: string, idx: number) => {
              if (!keyDateIndices.has(idx)) return '';
              const date = dates[idx];
              const d = date.replace(/[^0-9]/g, '');
              const mmdd = d.length >= 8 ? `${d.slice(4, 6)}-${d.slice(6, 8)}` : date;
              if (yearTransitionIndices.has(idx)) {
                const year = d.length >= 4 ? `${d.slice(0, 4)}年` : '';
                return `{year|${year}}\n{date|${mmdd}}`;
              }
              return `{date|${mmdd}}`;
            },
          }
          : {}),
    },
    axisTick: {show: i === 0},
  }));

  const yAxisBase = {
    type: 'value' as const,
    scale: true,
    position: 'right' as const,
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#666', fontSize: 10 },
    splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' as const } },
  };

  // Grid index mapping: 0=KLine, 1=Volume, 2=MACD, 3=KDJ, 4=RSI
  const yAxes = [
    { ...yAxisBase, gridIndex: 0 },
    {
      ...yAxisBase,
      gridIndex: 1,
      splitLine: { show: false },
      axisLabel: {
        ...yAxisBase.axisLabel,
        formatter: (v: number) => (v >= 1e8 ? `${(v / 1e8).toFixed(1)}亿` : `${(v / 1e4).toFixed(0)}万`),
      },
    },
    { ...yAxisBase, gridIndex: 2, splitLine: { show: false } }, // MACD — auto range
    {
      ...yAxisBase,
      gridIndex: 3,
      splitLine: {show: false},
      axisLabel: {show: false},
      axisTick: {show: false},
    }, // KDJ — hide right y-axis labels
    {
      ...yAxisBase,
      gridIndex: 4,
      min: 0,
      max: 100,
      splitLine: {show: false},
      axisLabel: {show: false},
      axisTick: {show: false},
    }, // RSI — hide right y-axis labels
  ];

  const dataZoom = [
    {
      type: 'inside',
      xAxisIndex: [0, 1, 2, 3, 4],
      start: zoomStartPct,
      end: zoomEndPct,
      zoomOnMouseWheel: true,
      moveOnMouseMove: false,
      moveOnMouseWheel: false,
      preventDefaultMouseMove: false,
    },
    {
      type: 'slider',
      xAxisIndex: [0, 1, 2, 3, 4],
      start: zoomStartPct,
      end: zoomEndPct,
      top: 0,
      height: 18,
      handleSize: '80%',
      borderColor: '#d0d0d0',
      fillerColor: 'rgba(0,120,255,0.1)',
      backgroundColor: '#f0f0f0',
      dataBackground: { areaStyle: { color: '#e0e0e0' }, lineStyle: { color: '#bbb' } },
      textStyle: { color: '#666', fontSize: 10 },
      showDetail: false,
    },
  ];

  const lineSeriesBase = {
    type: 'line' as const,
    smooth: false,
    showSymbol: false,
    connectNulls: false,
  };

  const MA_SERIES_KEYS: Record<'MA5' | 'MA10' | 'MA20' | 'MA60', keyof StockIndicatorSeries> = {
    MA5: 'ma5',
    MA10: 'ma10',
    MA20: 'ma20',
    MA60: 'ma60',
  };

  const maSeries = (['MA5', 'MA10', 'MA20', 'MA60'] as const).map((name) => ({
    ...lineSeriesBase,
    name,
    xAxisIndex: 0,
    yAxisIndex: 0,
    data: ind[MA_SERIES_KEYS[name]],
    lineStyle: { width: 1, color: MA_COLORS[name] },
    z: 3,
  }));

  // Volume MA series (MA5, MA10, MA20)
  const volMaSeriesConfig: { name: string; key: 'volume_ma5' | 'volume_ma10' | 'volume_ma20'; color: string }[] = [
    { name: 'VOL_MA5', key: 'volume_ma5', color: MA_COLORS.MA5 },
    { name: 'VOL_MA10', key: 'volume_ma10', color: MA_COLORS.MA10 },
    { name: 'VOL_MA20', key: 'volume_ma20', color: MA_COLORS.MA20 },
  ];
  const volMaSeries = volMaSeriesConfig.map(({ name, key, color }) => ({
    ...lineSeriesBase,
    name,
    xAxisIndex: 1,
    yAxisIndex: 1,
    data: ind[key],
    lineStyle: { width: 1, color },
  }));

  // MACD — gridIndex 2
  const macdLineSeriesConfig: { key: 'macd_dif' | 'macd_dea'; name: string; color: string }[] = [
    { key: 'macd_dif', name: 'DIF', color: MACD_COLORS.DIF },
    { key: 'macd_dea', name: 'DEA', color: MACD_COLORS.DEA },
  ];
  const macdLineSeries = macdLineSeriesConfig.map(({ key, name, color }) => ({
    ...lineSeriesBase,
    name,
    xAxisIndex: 2,
    yAxisIndex: 2,
    data: ind[key],
    lineStyle: { width: 1, color },
  }));

  // KDJ — gridIndex 3
  const kdjSeriesConfig: { key: 'kdj_k' | 'kdj_d' | 'kdj_j'; name: string; color: string }[] = [
    { key: 'kdj_k', name: 'KDJ_K', color: KDJ_COLORS.K },
    { key: 'kdj_d', name: 'KDJ_D', color: KDJ_COLORS.D },
    { key: 'kdj_j', name: 'KDJ_J', color: KDJ_COLORS.J },
  ];
  const kdjSeries = kdjSeriesConfig.map(({ key, name, color }) => ({
    ...lineSeriesBase,
    name,
    xAxisIndex: 3,
    yAxisIndex: 3,
    data: ind[key],
    lineStyle: { width: 1, color },
  }));

  // RSI — gridIndex 4
  const rsiSeriesConfig: { key: 'rsi6' | 'rsi12' | 'rsi24'; name: string; color: string }[] = [
    { key: 'rsi6', name: 'RSI6', color: RSI_COLORS.RSI6 },
    { key: 'rsi12', name: 'RSI12', color: RSI_COLORS.RSI12 },
    { key: 'rsi24', name: 'RSI24', color: RSI_COLORS.RSI24 },
  ];
  const rsiSeries = rsiSeriesConfig.map(({ key, name, color }) => ({
    ...lineSeriesBase,
    name,
    xAxisIndex: 4,
    yAxisIndex: 4,
    data: ind[key],
    lineStyle: { width: 1, color },
  }));

  return {
    animation: false,
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis' as const,
      axisPointer: {
        type: 'cross' as const,
        link: [{xAxisIndex: 'all'}],
        crossStyle: {color: '#000', width: 1, type: 'dashed' as const},
        label: {show: false},
      },
      backgroundColor: 'rgba(255, 255, 255, 0.88)',
      borderColor: 'transparent',
      borderWidth: 0,
      padding: 0,
      extraCssText: 'box-shadow:none;',
      formatter: () => '',
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
    },
    legend: { show: false },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom,
    series: [
      {
        name: 'K线',
        type: 'candlestick' as const,
        xAxisIndex: 0,
        yAxisIndex: 0,
        barWidth: KLINE_BAR_WIDTH,
        barMinWidth: KLINE_BAR_MIN_WIDTH,
        barMaxWidth: KLINE_BAR_MAX_WIDTH,
        data: bars.map((b) => {
          if (b.is_up_limit) {
            return {
              value: [b.open_price, b.close_price, b.low_price, b.high_price],
              itemStyle: { color: UP_LIMIT_COLOR, borderColor: UP_LIMIT_BORDER },
            };
          }
          if (b.is_down_limit) {
            return {
              value: [b.open_price, b.close_price, b.low_price, b.high_price],
              itemStyle: { color: DOWN_LIMIT_COLOR, borderColor: DOWN_LIMIT_BORDER },
            };
          }
          return [b.open_price, b.close_price, b.low_price, b.high_price];
        }),
        itemStyle: {
          color: UP_COLOR,
          color0: DOWN_COLOR,
          borderColor: UP_BORDER_COLOR,
          borderColor0: DOWN_BORDER_COLOR,
        },
        z: 2,
      },
      ...maSeries,
      {
        name: '成交量',
        type: 'bar' as const,
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: bars.map((b) => ({
          value: b.volume,
          itemStyle: { color: b.close_price >= b.open_price ? UP_COLOR : DOWN_COLOR },
        })),
        barMaxWidth: 8,
      },
      ...volMaSeries,
      // MACD (gridIndex 2)
      ...macdLineSeries,
      {
        name: 'MACD_HIST',
        type: 'bar' as const,
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: ind.macd_hist.map((v) => ({
          value: v,
          itemStyle: { color: v != null && v >= 0 ? UP_COLOR : DOWN_COLOR },
        })),
        barMaxWidth: 8,
      },
      // KDJ (gridIndex 3)
      ...kdjSeries,
      // RSI (gridIndex 4)
      ...rsiSeries,
    ],
  };
}

// ---------------------------------------------------------------------------
// Quote metrics row
// ---------------------------------------------------------------------------
function QuoteItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Col xs={8} sm={4}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 11, color: '#999', marginBottom: 2 }}>{label}</div>
        <div style={{ fontSize: 14, fontWeight: 500, color: color ?? '#333' }}>{value}</div>
      </div>
    </Col>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export function StockDetailPage() {
  const { stockCode } = useParams();
  const chartRef = useRef<ReactECharts>(null);
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);
  const [zoomRange, setZoomRange] = useState<ZoomRange>({start: 0, end: 100});
  const [barsData, setBarsData] = useState<DailyBar[]>([]);
  const [indicatorData, setIndicatorData] = useState<StockIndicatorSeries>(() => emptyIndicators());
  const [hasMoreBefore, setHasMoreBefore] = useState(false);
  const [monthsWindow, setMonthsWindow] = useState(INITIAL_MONTHS_WINDOW);
  const [isRangeLoading, setIsRangeLoading] = useState(false);
  const [allowAutoLoadMore, setAllowAutoLoadMore] = useState(true);
  // Tracks bars count + zoom-start so we can restore position after prepending older data
  const pendingLoadMetaRef = useRef<{ count: number; start: number } | null>(null);

  const { data, error, isLoading } = useQuery({
    queryKey: ['stock-detail', stockCode],
    queryFn: () => getStockDetail(stockCode as string),
    enabled: Boolean(stockCode),
  });

  useEffect(() => {
    if (!data) return;
    const totalBars = data.daily_bars.length;
    // Start zoomed to the last 120 trading days
    const initialStart = totalBars > 120 ? ((totalBars - 120) / totalBars) * 100 : 0;
    setBarsData(data.daily_bars);
    setIndicatorData(data.indicators);
    setHasMoreBefore(Boolean(data.has_more_before));
    setMonthsWindow(INITIAL_MONTHS_WINDOW);
    setZoomRange({start: initialStart, end: 100});
    setAllowAutoLoadMore(true);
    setHoverInfo(null);
  }, [data]);

  useEffect(() => {
    if (!stockCode || !data) return;
    if (monthsWindow === INITIAL_MONTHS_WINDOW) return;

    let cancelled = false;
    setIsRangeLoading(true);
    getStockBarsRange(stockCode, monthsWindow, data.trade_date)
        .then((resp) => {
          if (cancelled) return;
          setBarsData(resp.daily_bars);
          setIndicatorData(resp.indicators);
          setHasMoreBefore(resp.has_more_before);
          setHoverInfo(null);
          // Restore zoom so the same physical candles stay visible after prepend
          const meta = pendingLoadMetaRef.current;
          if (meta && resp.daily_bars.length > meta.count) {
            const added = resp.daily_bars.length - meta.count;
            const oldAbsStart = Math.round(meta.count * meta.start / 100);
            const newAbsStart = oldAbsStart + added;
            const newStartPct = Math.max(0, Math.min((newAbsStart / resp.daily_bars.length) * 100, 100));
            setZoomRange({start: newStartPct, end: 100});
            pendingLoadMetaRef.current = null;
          }
        })
        .finally(() => {
          if (!cancelled) setIsRangeLoading(false);
        });

    return () => {
      cancelled = true;
    };
  }, [stockCode, data, monthsWindow]);

  useEffect(() => {
    if (zoomRange.start > 20) {
      setAllowAutoLoadMore(true);
      return;
    }
    if (!allowAutoLoadMore || !hasMoreBefore || isRangeLoading) return;
    if (zoomRange.start <= 8) {
      // Record current state so we can restore position after prepend
      pendingLoadMetaRef.current = {count: barsData.length, start: zoomRange.start};
      setMonthsWindow((prev) => prev + LOAD_MORE_MONTHS_STEP);
      setAllowAutoLoadMore(false);
    }
  }, [zoomRange.start, allowAutoLoadMore, hasMoreBefore, isRangeLoading, barsData.length]);

  // Build date → index map for robust hover resolution
  const dateIndexMap = useMemo<Record<string, number>>(() => {
    if (!barsData.length) return {};
    const map: Record<string, number> = {};
    barsData.forEach((bar, i) => {
      map[bar.trade_date] = i;
    });
    return map;
  }, [barsData]);

  const onChartEvents = useCallback(
    (bars: DailyBar[], indexMap: Record<string, number>) => ({
      updateAxisPointer: (params: { axesInfo?: { value?: number | string }[] }) => {
        const axesInfo = params?.axesInfo;
        if (!axesInfo || axesInfo.length === 0) return;
        const raw = axesInfo[0].value;
        let idx: number;
        if (typeof raw === 'number' && isFinite(raw)) {
          idx = raw;
        } else if (typeof raw === 'string') {
          idx = indexMap[raw] ?? -1;
        } else {
          return;
        }
        if (idx >= 0 && idx < bars.length && bars[idx]) {
          setHoverInfo({ idx, bar: bars[idx] });
        }
      },
      globalout: () => setHoverInfo(null),
      datazoom: (params: { batch?: { start?: number; end?: number }[]; start?: number; end?: number }) => {
        const src = params?.batch?.[0] ?? params;
        if (!src) return;
        const nextStartRaw = typeof src.start === 'number' ? src.start : null;
        const nextEndRaw = typeof src.end === 'number' ? src.end : null;
        if (nextStartRaw == null || nextEndRaw == null) return;
        const nextStart = Math.max(0, Math.min(100, nextStartRaw));
        const nextEnd = Math.max(0, Math.min(100, nextEndRaw));
        setZoomRange((prev) => {
          if (Math.abs(prev.start - nextStart) < 0.01 && Math.abs(prev.end - nextEnd) < 0.01) {
            return prev;
          }
          return {start: Math.min(nextStart, nextEnd), end: Math.max(nextStart, nextEnd)};
        });
      },
    }),
    [],
  );

  // Keep hook order stable across loading/error/empty/data branches.
  // Memoized option also preserves zoom state during hover-driven re-renders.
  const chartOption = useMemo(() => {
    if (!data) return null;
    const effectiveBars = barsData.length > 0 ? barsData : data.daily_bars;
    const effectiveIndicators = barsData.length > 0 ? indicatorData : data.indicators;
    const merged: StockDetailResponse = {
      ...data,
      daily_bars: effectiveBars,
      indicators: effectiveIndicators,
    };
    return buildChartOption(merged, zoomRange);
  }, [data, barsData, indicatorData, zoomRange]);

  if (!stockCode) {
    return <Alert type="error" showIcon message="缺少股票代码参数" />;
  }

  if (isLoading) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          股票详情 · {stockCode}
        </Typography.Title>
        <Card className="page-card">
          <Space align="center" size={12}>
            <Spin />
            <Typography.Text>正在加载股票详情...</Typography.Text>
          </Space>
        </Card>
      </Space>
    );
  }

  if (error) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          股票详情 · {stockCode}
        </Typography.Title>
        <Alert
          type="error"
          showIcon
          message="加载股票详情失败"
          description={error instanceof Error ? error.message : '请检查后端服务是否已启动。'}
        />
      </Space>
    );
  }

  if (!data) {
    return (
      <Space direction="vertical" size={24} style={{ display: 'flex' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          股票详情 · {stockCode}
        </Typography.Title>
        <Card className="page-card">
          <Empty description="暂无股票详情数据" />
        </Card>
      </Space>
    );
  }

  // Use live barsData (extended window) if available, falling back to initial load
  const bars = barsData.length > 0 ? barsData : data.daily_bars;
  const ind = barsData.length > 0 ? indicatorData : data.indicators;
  const latestIdx = bars.length - 1;
  const latestInfo: HoverInfo = { idx: latestIdx, bar: bars[latestIdx] };
  const activeInfo = hoverInfo ?? latestInfo;
  const activeIdx = activeInfo.idx;
  const activeBar = activeInfo.bar;
  const activePriceColor = activeBar.close_price >= activeBar.open_price ? UP_COLOR : DOWN_COLOR;
  const activePrevClose = activeBar.pre_close ?? (activeIdx > 0 ? bars[activeIdx - 1]?.close_price ?? null : null);
  const activeChangePct =
      activeBar.change_pct ??
      (activePrevClose != null && activePrevClose !== 0
          ? ((activeBar.close_price - activePrevClose) / activePrevClose) * 100
          : null);
  const activeMacdHist = ind.macd_hist[activeIdx];
  const priceColor = colorOf(data.change_pct);
  const changeSign = data.change_amount >= 0 ? '+' : '';
  const events = onChartEvents(bars, dateIndexMap);

  return (
    <Space direction="vertical" size={12} style={{ display: 'flex' }}>
      {/* 1. Title bar */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '8px 16px' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {data.stock_name}
        </Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 14 }}>
          {data.stock_code}
        </Typography.Text>
        <Typography.Text style={{ color: priceColor, fontSize: 28, fontWeight: 700, lineHeight: 1 }}>
          {data.current_price.toFixed(2)}
        </Typography.Text>
        <Typography.Text style={{ color: priceColor, fontSize: 16 }}>
          {changeSign}
          {data.change_amount.toFixed(2)}
        </Typography.Text>
        <Typography.Text style={{ color: priceColor, fontSize: 16 }}>
          {changeSign}
          {data.change_pct.toFixed(2)}%
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {data.trade_date}
        </Typography.Text>
      </div>

      {/* 2. Quote metrics */}
      <Row gutter={[8, 8]}>
        <QuoteItem label="昨收" value={data.prev_close.toFixed(2)} />
        <QuoteItem label="最高" value={data.high_price.toFixed(2)} color={UP_COLOR} />
        <QuoteItem label="最低" value={data.low_price.toFixed(2)} color={DOWN_COLOR} />
        <QuoteItem label="成交额" value={fmtAmount(data.turnover_amount_billion)}/>
        <QuoteItem label="换手率" value={`${data.turnover_rate.toFixed(2)}%`} />
      </Row>

      {/* 3. Tags */}
      {(data.tags.industry.length > 0 || data.tags.concepts.length > 0 || data.tags.region.length > 0) && (
        <Space size={4} wrap>
          {data.tags.industry.map((t) => (
            <Tag key={`ind-${t}`} color="blue">
              {t}
            </Tag>
          ))}
          {data.tags.concepts.map((t) => (
            <Tag key={`con-${t}`} color="purple">
              {t}
            </Tag>
          ))}
          {data.tags.region.map((t) => (
            <Tag key={`reg-${t}`} color="green">
              {t}
            </Tag>
          ))}
        </Space>
      )}

      {/* 4. Charts */}
      <Card className="page-card" styles={{ body: { padding: '12px 16px' } }}>
        <Tabs
          defaultActiveKey="kline"
          size="small"
          items={[
            {
              key: 'kline',
              label: 'K线',
              children:
                bars.length > 0 ? (
                  <>
                    {/* Chart */}
                    <div style={{position: 'relative', height: CHART_HEIGHT, minHeight: CHART_MIN_HEIGHT}}>
                      {/* Panel separator lines */}
                      {PANEL_SEPARATORS.map((top) => (
                          <div
                              key={`sep-${top}`}
                              style={{
                                position: 'absolute',
                                top,
                                left: 0,
                                right: 0,
                                height: 2,
                                backgroundColor: '#bfbfbf',
                                zIndex: 5,
                                pointerEvents: 'none',
                              }}
                          />
                      ))}

                      <PanelFloatCard gridKey="kline" title="K线">
                        <InfoRow
                            items={[
                              {label: '日期', value: activeBar.trade_date},
                              {label: '开', value: fmtNum(activeBar.open_price)},
                              {label: '高', value: fmtNum(activeBar.high_price), color: UP_COLOR},
                              {label: '低', value: fmtNum(activeBar.low_price), color: DOWN_COLOR},
                              {label: '收', value: fmtNum(activeBar.close_price), color: activePriceColor},
                              {label: '涨跌幅', value: fmtSignedPct(activeChangePct), color: activePriceColor},
                            ]}
                        />
                        <InfoRow
                            items={[
                              {label: 'MA5', value: fmtNum(ind.ma5[activeIdx]), color: MA_COLORS.MA5},
                              {label: 'MA10', value: fmtNum(ind.ma10[activeIdx]), color: MA_COLORS.MA10},
                              {label: 'MA20', value: fmtNum(ind.ma20[activeIdx]), color: MA_COLORS.MA20},
                              {label: 'MA60', value: fmtNum(ind.ma60[activeIdx]), color: MA_COLORS.MA60},
                            ]}
                        />
                      </PanelFloatCard>

                      <PanelFloatCard gridKey="volume" title={SUB_CHART_TITLES.volume}>
                        <InfoRow
                            items={[
                              {label: 'VOL', value: fmtVol(activeBar.volume), color: activePriceColor},
                              {label: '额', value: fmtAmount(activeBar.turnover_amount_billion)},
                              {label: '换手', value: fmtPct(activeBar.turnover_rate)},
                            ]}
                        />
                        <InfoRow
                            items={[
                              {label: 'MA5', value: fmtNum(ind.volume_ma5[activeIdx]), color: MA_COLORS.MA5},
                              {label: 'MA10', value: fmtNum(ind.volume_ma10[activeIdx]), color: MA_COLORS.MA10},
                              {label: 'MA20', value: fmtNum(ind.volume_ma20[activeIdx]), color: MA_COLORS.MA20},
                            ]}
                        />
                      </PanelFloatCard>

                      <PanelFloatCard gridKey="macd" title={SUB_CHART_TITLES.macd}>
                        <InfoRow
                            items={[
                              {label: 'DIF', value: fmtNum(ind.macd_dif[activeIdx], 4), color: MACD_COLORS.DIF},
                              {label: 'DEA', value: fmtNum(ind.macd_dea[activeIdx], 4), color: MACD_COLORS.DEA},
                              {
                                label: 'MACD',
                                value: fmtNum(activeMacdHist, 4),
                                color: activeMacdHist != null && activeMacdHist >= 0 ? UP_COLOR : DOWN_COLOR,
                              },
                            ]}
                        />
                      </PanelFloatCard>

                      <PanelFloatCard gridKey="kdj" title={SUB_CHART_TITLES.kdj}>
                        <InfoRow
                            items={[
                              {label: 'K', value: fmtNum(ind.kdj_k[activeIdx]), color: KDJ_COLORS.K},
                              {label: 'D', value: fmtNum(ind.kdj_d[activeIdx]), color: KDJ_COLORS.D},
                              {label: 'J', value: fmtNum(ind.kdj_j[activeIdx]), color: KDJ_COLORS.J},
                            ]}
                        />
                      </PanelFloatCard>

                      <PanelFloatCard gridKey="rsi" title={SUB_CHART_TITLES.rsi}>
                        <InfoRow
                            items={[
                              {label: 'RSI6', value: fmtNum(ind.rsi6[activeIdx]), color: RSI_COLORS.RSI6},
                              {label: 'RSI12', value: fmtNum(ind.rsi12[activeIdx]), color: RSI_COLORS.RSI12},
                              {label: 'RSI24', value: fmtNum(ind.rsi24[activeIdx]), color: RSI_COLORS.RSI24},
                            ]}
                        />
                      </PanelFloatCard>

                      {/* Main chart */}
                      <ReactECharts
                        ref={chartRef}
                        option={chartOption ?? {}}
                        notMerge={false}
                        lazyUpdate={true}
                        style={{height: CHART_HEIGHT, minHeight: CHART_MIN_HEIGHT}}
                        onEvents={events}
                      />
                    </div>
                  </>
                ) : (
                  <Empty description="暂无K线数据" />
                ),
            },
            {
              key: 'minute',
              label: '分时',
              disabled: true,
              children: <Empty description="分时图功能开发中" />,
            },
          ]}
        />
      </Card>
    </Space>
  );
}
