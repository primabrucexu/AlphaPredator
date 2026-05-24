import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import {Alert, Card, Col, Empty, Row, Space, Spin, Tabs, Tag, Typography} from 'antd';
import {useParams} from 'react-router-dom';
import {
  type DailyBar,
  getStockBarsRange,
  getStockDetail,
  getStockLimitUpHistory,
  type StockDetailResponse,
  type StockIndicatorSeries,
  type StockLimitUpHistoryRow,
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

const MA_COLORS: Record<'MA5' | 'MA10' | 'MA20' | 'MA60', string> = {
  MA5: '#f5a623',
  MA10: '#7ed321',
  MA20: '#4a90e2',
  MA60: '#9013fe',
};

const KDJ_COLORS = { K: '#f5a623', D: '#7ed321', J: '#cf1322' };
const MACD_COLORS = {DIF: '#2962FF', DEA: '#FF6D00'};

const CARD_CHART_HEIGHT = 340;
const CHART_SYNC_GROUP = 'stock-detail-sync-group';
const GRID_LEFT = '70px';
const GRID_RIGHT = '80px';

// K-line candle width tuning: use wider candles so adjacent gap is about 1-2px.
const KLINE_BAR_WIDTH = '88%';
const KLINE_BAR_MIN_WIDTH = 3;
const KLINE_BAR_MAX_WIDTH = 18;

type IndicatorTabKey = 'macd' | 'kdj';

const INITIAL_MONTHS_WINDOW = 6;
const LOAD_MORE_MONTHS_STEP = 6;


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtAmount(v: number | null | undefined): string {
  // API already returns turnover amount in 亿元.
  return v != null ? `${v.toFixed(2)}亿` : '--';
}

function fmtNum(v: number | null | undefined, decimals = 4): string {
  return v != null ? v.toFixed(decimals) : '--';
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
interface ZoomRange {
  start: number;
  end: number;
}

function buildKlineCardOption(data: StockDetailResponse, zoomRange: ZoomRange) {
  const bars = data.daily_bars;
  const ind = data.indicators;
  const dates = bars.map((b) => b.trade_date);
  return {
    animation: false,
    tooltip: { show: true, showContent: false, trigger: 'axis' as const, axisPointer: { type: 'cross' as const } },
    grid: { top: 36, left: GRID_LEFT, right: GRID_RIGHT, bottom: 56 },
    xAxis: {
      type: 'category' as const,
      data: dates,
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#d0d0d0' } },
      axisTick: { show: false },
      axisLabel: { color: '#666', fontSize: 11 },
    },
    yAxis: {
      type: 'value' as const,
      scale: true,
      position: 'right' as const,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#666', fontSize: 10 },
      splitLine: { lineStyle: { color: '#f0f0f0', type: 'dashed' as const } },
    },
    dataZoom: [
      { type: 'inside', start: zoomRange.start, end: zoomRange.end },
      { type: 'slider', start: zoomRange.start, end: zoomRange.end, height: 18, bottom: 8, showDetail: false },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick' as const,
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
      },
      {
        name: 'MA5',
        type: 'line' as const,
        data: ind.ma5,
        showSymbol: false,
        lineStyle: { width: 1, color: MA_COLORS.MA5 },
      },
      {
        name: 'MA10',
        type: 'line' as const,
        data: ind.ma10,
        showSymbol: false,
        lineStyle: { width: 1, color: MA_COLORS.MA10 },
      },
      {
        name: 'MA20',
        type: 'line' as const,
        data: ind.ma20,
        showSymbol: false,
        lineStyle: { width: 1, color: MA_COLORS.MA20 },
      },
      {
        name: 'MA60',
        type: 'line' as const,
        data: ind.ma60,
        showSymbol: false,
        lineStyle: { width: 1, color: MA_COLORS.MA60 },
      },
    ],
  };
}

function buildVolumeCardOption(data: StockDetailResponse, zoomRange: ZoomRange) {
  const bars = data.daily_bars;
  const ind = data.indicators;
  const dates = bars.map((b) => b.trade_date);
  return {
    animation: false,
    tooltip: { show: true, showContent: false, trigger: 'axis' as const, axisPointer: { type: 'cross' as const } },
    grid: { top: 36, left: GRID_LEFT, right: GRID_RIGHT, bottom: 56 },
    xAxis: {
      type: 'category' as const,
      data: dates,
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#d0d0d0' } },
      axisTick: { show: false },
      axisLabel: { color: '#666', fontSize: 11 },
    },
    yAxis: {
      type: 'value' as const,
      scale: true,
      position: 'right' as const,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#666',
        fontSize: 10,
        formatter: (v: number) => (v >= 1e8 ? `${(v / 1e8).toFixed(1)}亿` : `${(v / 1e4).toFixed(0)}万`),
      },
      splitLine: { show: false },
    },
    dataZoom: [
      { type: 'inside', start: zoomRange.start, end: zoomRange.end },
      { type: 'slider', start: zoomRange.start, end: zoomRange.end, height: 18, bottom: 8, showDetail: false },
    ],
    series: [
      {
        name: '成交量',
        type: 'bar' as const,
        data: bars.map((b) => ({
          value: b.volume,
          itemStyle: { color: b.close_price >= b.open_price ? UP_COLOR : DOWN_COLOR },
        })),
        barMaxWidth: 8,
      },
      {
        name: 'VOL_MA5',
        type: 'line' as const,
        data: ind.volume_ma5,
        showSymbol: false,
        lineStyle: { width: 1, color: MA_COLORS.MA5 },
      },
      {
        name: 'VOL_MA10',
        type: 'line' as const,
        data: ind.volume_ma10,
        showSymbol: false,
        lineStyle: { width: 1, color: MA_COLORS.MA10 },
      },
      {
        name: 'VOL_MA20',
        type: 'line' as const,
        data: ind.volume_ma20,
        showSymbol: false,
        lineStyle: { width: 1, color: MA_COLORS.MA20 },
      },
    ],
  };
}

function buildIndicatorCardOption(data: StockDetailResponse, zoomRange: ZoomRange, tab: IndicatorTabKey) {
  const dates = data.daily_bars.map((b) => b.trade_date);
  const ind = data.indicators;
  const common = {
    animation: false,
    tooltip: { show: true, showContent: false, trigger: 'axis' as const, axisPointer: { type: 'cross' as const } },
    grid: { top: 36, left: GRID_LEFT, right: GRID_RIGHT, bottom: 56 },
    xAxis: {
      type: 'category' as const,
      data: dates,
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#d0d0d0' } },
      axisTick: { show: false },
      axisLabel: { color: '#666', fontSize: 11 },
    },
    dataZoom: [
      { type: 'inside', start: zoomRange.start, end: zoomRange.end },
      { type: 'slider', start: zoomRange.start, end: zoomRange.end, height: 18, bottom: 8, showDetail: false },
    ],
  };

  if (tab === 'macd') {
    return {
      ...common,
      yAxis: {
        type: 'value' as const,
        scale: true,
        position: 'right' as const,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#666', fontSize: 10 },
        splitLine: { show: false },
      },
      series: [
        {
          name: 'MACD_HIST',
          type: 'bar' as const,
          data: ind.macd_hist.map((v) => ({ value: v, itemStyle: { color: v != null && v >= 0 ? UP_COLOR : DOWN_COLOR } })),
          barMaxWidth: 8,
        },
        { name: 'DIF', type: 'line' as const, data: ind.macd_dif, showSymbol: false, lineStyle: { width: 1, color: MACD_COLORS.DIF } },
        { name: 'DEA', type: 'line' as const, data: ind.macd_dea, showSymbol: false, lineStyle: { width: 1, color: MACD_COLORS.DEA } },
      ],
    };
  }

  if (tab === 'kdj') {
    return {
      ...common,
      yAxis: {
        type: 'value' as const,
        scale: true,
        position: 'right' as const,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#666', fontSize: 10 },
        splitLine: { show: false },
      },
      series: [
        { name: 'K', type: 'line' as const, data: ind.kdj_k, showSymbol: false, lineStyle: { width: 1, color: KDJ_COLORS.K } },
        { name: 'D', type: 'line' as const, data: ind.kdj_d, showSymbol: false, lineStyle: { width: 1, color: KDJ_COLORS.D } },
        { name: 'J', type: 'line' as const, data: ind.kdj_j, showSymbol: false, lineStyle: { width: 1, color: KDJ_COLORS.J } },
      ],
    };
  }

  return {
    ...common,
    yAxis: {
      type: 'value' as const,
      scale: true,
      position: 'right' as const,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#666', fontSize: 10 },
      splitLine: { show: false },
    },
    series: [
      { name: 'K', type: 'line' as const, data: ind.kdj_k, showSymbol: false, lineStyle: { width: 1, color: KDJ_COLORS.K } },
      { name: 'D', type: 'line' as const, data: ind.kdj_d, showSymbol: false, lineStyle: { width: 1, color: KDJ_COLORS.D } },
      { name: 'J', type: 'line' as const, data: ind.kdj_j, showSymbol: false, lineStyle: { width: 1, color: KDJ_COLORS.J } },
    ],
  };
}

function splitThemes(raw: string): string[] {
  return raw
    .split(/[;,，、|\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function DetailOverlay({
  date,
  items,
  align,
}: {
  date: string;
  items: { label: string; value: string; color?: string }[];
  align: 'left' | 'right';
}) {
  const cells = [
    { label: '日期', value: date, color: '#555' },
    ...items,
  ];
  return (
    <div
      style={{
        position: 'absolute',
        top: 8,
        left: align === 'left' ? 8 : undefined,
        right: align === 'right' ? 8 : undefined,
        zIndex: 10,
        maxWidth: '58%',
        padding: '8px 10px',
        border: '1px solid rgba(0,0,0,0.15)',
        borderRadius: 8,
        background: 'rgba(255,255,255,0.88)',
        backdropFilter: 'blur(2px)',
        pointerEvents: 'none',
      }}
    >
      <Row gutter={[12, 8]}>
        {cells.map((item) => (
          <Col key={item.label} xs={12} md={6} xl={4}>
            <div style={{lineHeight: 1.3}}>
              <div style={{fontSize: 11, color: '#8c8c8c'}}>{item.label}</div>
              <div style={{fontSize: 13, fontWeight: 600, color: item.color ?? '#333'}}>{item.value}</div>
            </div>
          </Col>
        ))}
      </Row>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export function StockDetailPage() {
  const { stockCode } = useParams();
  const klineChartRef = useRef<ReactECharts | null>(null);
  const volumeChartRef = useRef<ReactECharts | null>(null);
  const indicatorChartRef = useRef<ReactECharts | null>(null);
  const [zoomRange, setZoomRange] = useState<ZoomRange>({start: 0, end: 100});
  const [indicatorTab, setIndicatorTab] = useState<IndicatorTabKey>('macd');
  const [activeIndicatorIdx, setActiveIndicatorIdx] = useState<number | null>(null);
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

  const { data: limitUpHistory } = useQuery({
    queryKey: ['stock-limit-up-history', stockCode],
    queryFn: () => getStockLimitUpHistory(stockCode as string, 10),
    enabled: Boolean(stockCode),
  });

  useEffect(() => {
    return () => {
      echarts.disconnect(CHART_SYNC_GROUP);
    };
  }, []);

  const bindChartGroup = useCallback(() => {
    const instances = [
      klineChartRef.current?.getEchartsInstance(),
      volumeChartRef.current?.getEchartsInstance(),
      indicatorChartRef.current?.getEchartsInstance(),
    ].filter(Boolean) as Array<{ group?: string }>;
    if (instances.length === 0) return;
    instances.forEach((instance) => {
      instance.group = CHART_SYNC_GROUP;
    });
    echarts.connect(CHART_SYNC_GROUP);
  }, []);

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
    setActiveIndicatorIdx(data.daily_bars.length > 0 ? data.daily_bars.length - 1 : null);
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
          setActiveIndicatorIdx(resp.daily_bars.length > 0 ? resp.daily_bars.length - 1 : null);
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

  const onChartEvents = useCallback(
    (indexMap: Record<string, number>, maxLen: number) => ({
      updateAxisPointer: (params: { axesInfo?: { value?: number | string }[] }) => {
        const raw = params?.axesInfo?.[0]?.value;
        if (raw == null) return;
        const idx = typeof raw === 'number' ? raw : indexMap[raw];
        if (typeof idx === 'number' && idx >= 0 && idx < maxLen) {
          setActiveIndicatorIdx(idx);
        }
      },
      globalout: () => {
        setActiveIndicatorIdx(maxLen > 0 ? maxLen - 1 : null);
      },
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

  const chartData = useMemo<StockDetailResponse | null>(() => {
    if (!data) return null;
    const effectiveBars = barsData.length > 0 ? barsData : data.daily_bars;
    const effectiveIndicators = barsData.length > 0 ? indicatorData : data.indicators;
    return {
      ...data,
      daily_bars: effectiveBars,
      indicators: effectiveIndicators,
    };
  }, [data, barsData, indicatorData]);

  const klineOption = useMemo(() => {
    if (!chartData) return {};
    return buildKlineCardOption(chartData, zoomRange);
  }, [chartData, zoomRange]);

  const volumeOption = useMemo(() => {
    if (!chartData) return {};
    return buildVolumeCardOption(chartData, zoomRange);
  }, [chartData, zoomRange]);

  const indicatorOption = useMemo(() => {
    if (!chartData) return {};
    return buildIndicatorCardOption(chartData, zoomRange, indicatorTab);
  }, [chartData, zoomRange, indicatorTab]);

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
  const indicatorSeries = barsData.length > 0 ? indicatorData : data.indicators;
  const dateIndexMap: Record<string, number> = {};
  bars.forEach((bar, idx) => {
    dateIndexMap[bar.trade_date] = idx;
  });
  const indicatorIdx = activeIndicatorIdx != null && activeIndicatorIdx >= 0 && activeIndicatorIdx < bars.length
    ? activeIndicatorIdx
    : (bars.length > 0 ? bars.length - 1 : 0);
  // Keep overlay on the opposite side of the current cursor position to reduce overlap.
  const overlayAlign: 'left' | 'right' = bars.length > 0 && indicatorIdx > Math.floor(bars.length * 0.55)
    ? 'left'
    : 'right';
  const activeBar = bars[indicatorIdx];
  const priceColor = colorOf(data.change_pct);
  const changeSign = data.change_amount >= 0 ? '+' : '';
  const events = onChartEvents(dateIndexMap, bars.length);

  const indicatorDetailItems: { label: string; value: string; color?: string }[] = bars.length === 0
    ? []
    : indicatorTab === 'macd'
      ? (() => {
        const hist = indicatorSeries.macd_hist[indicatorIdx];
        return [
          { label: 'DIF', value: fmtNum(indicatorSeries.macd_dif[indicatorIdx]), color: MACD_COLORS.DIF },
          { label: 'DEA', value: fmtNum(indicatorSeries.macd_dea[indicatorIdx]), color: MACD_COLORS.DEA },
          { label: 'MACD', value: fmtNum(hist), color: hist != null && hist >= 0 ? UP_COLOR : DOWN_COLOR },
        ];
      })()
      : [
        { label: 'K', value: fmtNum(indicatorSeries.kdj_k[indicatorIdx]), color: KDJ_COLORS.K },
        { label: 'D', value: fmtNum(indicatorSeries.kdj_d[indicatorIdx]), color: KDJ_COLORS.D },
        { label: 'J', value: fmtNum(indicatorSeries.kdj_j[indicatorIdx]), color: KDJ_COLORS.J },
      ];

  const klineDetailItems: { label: string; value: string; color?: string }[] = activeBar
    ? [
      { label: '开', value: fmtNum(activeBar.open_price, 2) },
      { label: '高', value: fmtNum(activeBar.high_price, 2), color: UP_COLOR },
      { label: '低', value: fmtNum(activeBar.low_price, 2), color: DOWN_COLOR },
      { label: '收', value: fmtNum(activeBar.close_price, 2), color: activeBar.close_price >= activeBar.open_price ? UP_COLOR : DOWN_COLOR },
      { label: 'MA5', value: fmtNum(indicatorSeries.ma5[indicatorIdx], 2), color: MA_COLORS.MA5 },
      { label: 'MA10', value: fmtNum(indicatorSeries.ma10[indicatorIdx], 2), color: MA_COLORS.MA10 },
      { label: 'MA20', value: fmtNum(indicatorSeries.ma20[indicatorIdx], 2), color: MA_COLORS.MA20 },
    ]
    : [];

  const volumeDetailItems: { label: string; value: string; color?: string }[] = activeBar
    ? [
      { label: '成交量', value: (activeBar.volume ?? 0).toLocaleString() },
      { label: '成交额', value: fmtAmount(activeBar.turnover_amount_billion) },
      { label: '换手率', value: activeBar.turnover_rate != null ? `${activeBar.turnover_rate.toFixed(2)}%` : '--' },
      { label: 'VOL_MA5', value: fmtNum(indicatorSeries.volume_ma5[indicatorIdx], 2), color: MA_COLORS.MA5 },
      { label: 'VOL_MA10', value: fmtNum(indicatorSeries.volume_ma10[indicatorIdx], 2), color: MA_COLORS.MA10 },
      { label: 'VOL_MA20', value: fmtNum(indicatorSeries.volume_ma20[indicatorIdx], 2), color: MA_COLORS.MA20 },
    ]
    : [];

  const latestLimitUp: StockLimitUpHistoryRow | null = limitUpHistory?.rows?.[0] ?? null;
  const latestThemes = latestLimitUp ? splitThemes(latestLimitUp.hot_theme) : [];

  return (
    <Space direction="vertical" size={12} style={{ display: 'flex' }}>
      {/* 1. Title bar */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '8px 14px' }}>
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
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>昨收 {data.prev_close.toFixed(2)}</Typography.Text>
        <Typography.Text style={{ fontSize: 13, color: UP_COLOR }}>最高 {data.high_price.toFixed(2)}</Typography.Text>
        <Typography.Text style={{ fontSize: 13, color: DOWN_COLOR }}>最低 {data.low_price.toFixed(2)}</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>成交额 {fmtAmount(data.turnover_amount_billion)}</Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>换手率 {data.turnover_rate.toFixed(2)}%</Typography.Text>
      </div>

      {/* 2. Tags */}
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

      {/* 3. Hot sentiment link */}
      <Card className="page-card" title="热点情绪联动" styles={{ body: { padding: '12px 16px' } }}>
        {latestLimitUp ? (
          <Space direction="vertical" size={8} style={{display: 'flex'}}>
            <Space size={16} wrap>
              <Typography.Text type="secondary">最近涨停: {latestLimitUp.trade_date}{latestLimitUp.limit_up_time ? ` ${latestLimitUp.limit_up_time}` : ''}</Typography.Text>
              <Typography.Text>{latestLimitUp.streak_text || '--'}</Typography.Text>
            </Space>
            <Space size={[6, 6]} wrap>
              <Typography.Text type="secondary">热点题材:</Typography.Text>
              {latestThemes.length > 0 ? latestThemes.map((theme) => (
                <Tag key={theme} color="gold">{theme}</Tag>
              )) : <Typography.Text>--</Typography.Text>}
            </Space>
            <Typography.Text strong>涨停原因解析</Typography.Text>
            <Typography.Paragraph style={{marginBottom: 0, whiteSpace: 'pre-wrap'}}>
              {latestLimitUp.reason || latestLimitUp.short_reason || '--'}
            </Typography.Paragraph>
          </Space>
        ) : (
          <Empty description="暂无涨停历史，暂时无法联动热点情绪" />
        )}
      </Card>

      {/* 4. Charts */}
      <Card className="page-card" title="K线图" styles={{ body: { padding: '12px 16px' } }}>
        {bars.length > 0 ? (
          <>
            <div style={{position: 'relative', height: CARD_CHART_HEIGHT}}>
              <ReactECharts
                ref={klineChartRef}
                option={klineOption}
                notMerge={false}
                lazyUpdate={true}
                style={{height: '100%'}}
                onEvents={events}
                onChartReady={bindChartGroup}
              />
              <DetailOverlay date={activeBar?.trade_date ?? '--'} items={klineDetailItems} align={overlayAlign} />
            </div>
          </>
        ) : (
          <Empty description="暂无K线数据" />
        )}
      </Card>

      <Card className="page-card" title="成交量" styles={{ body: { padding: '12px 16px' } }}>
        {bars.length > 0 ? (
          <>
            <div style={{position: 'relative', height: CARD_CHART_HEIGHT}}>
              <ReactECharts
                ref={volumeChartRef}
                option={volumeOption}
                notMerge={false}
                lazyUpdate={true}
                style={{height: '100%'}}
                onEvents={events}
                onChartReady={bindChartGroup}
              />
              <DetailOverlay date={activeBar?.trade_date ?? '--'} items={volumeDetailItems} align={overlayAlign} />
            </div>
          </>
        ) : (
          <Empty description="暂无成交量数据" />
        )}
      </Card>

      <Card className="page-card" title="指标" styles={{ body: { padding: '12px 16px' } }}>
        <Tabs
          activeKey={indicatorTab}
          onChange={(key) => setIndicatorTab(key as IndicatorTabKey)}
          size="small"
          items={[
            { key: 'macd', label: 'MACD' },
            { key: 'kdj', label: 'KDJ' },
          ]}
        />
        {bars.length > 0 ? (
          <>
            <div style={{position: 'relative', height: CARD_CHART_HEIGHT}}>
              <ReactECharts
                ref={indicatorChartRef}
                option={indicatorOption}
                notMerge={false}
                lazyUpdate={true}
                style={{height: '100%'}}
                onEvents={events}
                onChartReady={bindChartGroup}
              />
              <DetailOverlay date={bars[indicatorIdx]?.trade_date ?? '--'} items={indicatorDetailItems} align={overlayAlign} />
            </div>
          </>
        ) : (
          <Empty description="暂无指标数据" />
        )}
      </Card>
    </Space>
  );
}
