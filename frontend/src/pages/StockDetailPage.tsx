import { useCallback, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { Alert, Card, Col, Empty, Row, Space, Spin, Tabs, Tag, Typography } from 'antd';
import { useParams } from 'react-router-dom';
import { getStockDetail, type DailyBar, type StockDetailResponse, type StockIndicatorSeries } from '../lib/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const UP_COLOR = '#cf1322';
const DOWN_COLOR = '#14b8a6';

const MA_COLORS: Record<string, string> = {
  MA5: '#f5a623',
  MA10: '#7ed321',
  MA20: '#4a90e2',
  MA60: '#9013fe',
};

const KDJ_COLORS = { K: '#f5a623', D: '#7ed321', J: '#cf1322' };
const MACD_COLORS = { DIF: '#f5a623', DEA: '#7ed321' };
const RSI_COLORS = { RSI6: '#f5a623', RSI12: '#7ed321', RSI24: '#cf1322' };

// Grid percentage positions (used for overlay and chart option)
const GRID_POSITIONS = {
  kline: { top: '3%', height: '37%' },
  volume: { top: '44%', height: '10%' },
  macd: { top: '57%', height: '10%' },
  kdj: { top: '70%', height: '10%' },
  rsi: { top: '83%', height: '9%' },
} as const;

const CHART_HEIGHT = 780;
const GRID_LEFT = '70px';
const GRID_RIGHT = '80px';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtNum(v: number | null | undefined, decimals = 2): string {
  return v != null ? v.toFixed(decimals) : '--';
}

function fmtVol(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿手`;
  return `${(v / 1e4).toFixed(0)}万手`;
}

function fmtAmount(v: number | undefined | null): string {
  if (v == null) return '--';
  return `${v.toFixed(2)}亿`;
}

function fmtTurnover(v: number | undefined | null): string {
  if (v == null) return '--';
  return `${v.toFixed(2)}%`;
}

function colorOf(change: number): string {
  return change >= 0 ? UP_COLOR : DOWN_COLOR;
}

// ---------------------------------------------------------------------------
// Indicator info bar types
// ---------------------------------------------------------------------------
interface HoverInfo {
  idx: number;
  bar: DailyBar;
}

// ---------------------------------------------------------------------------
// Sub-info rows shown inside chart
// ---------------------------------------------------------------------------
function InfoRow({ items }: { items: { label: string; value: string; color?: string }[] }) {
  return (
    <div style={{ fontSize: 11, lineHeight: 1.6 }}>
      {items.map(({ label, value, color }) => (
        <span key={label} style={{ marginRight: 12 }}>
          <span style={{ color: '#888' }}>{label}: </span>
          <span style={{ color: color ?? '#333', fontWeight: 500 }}>{value}</span>
        </span>
      ))}
    </div>
  );
}

function KLineInfoBar({
  hover,
  latest,
  ind,
}: {
  hover: HoverInfo | null;
  latest: HoverInfo;
  ind: StockIndicatorSeries;
}) {
  const { idx, bar } = hover ?? latest;
  const priceColor = bar.close_price >= bar.open_price ? UP_COLOR : DOWN_COLOR;

  return (
    <div style={{ padding: '4px 0 8px', borderBottom: '1px solid #e8e8e8', marginBottom: 4 }}>
      <InfoRow
        items={[
          { label: '日期', value: bar.trade_date },
          { label: '开', value: fmtNum(bar.open_price), color: '#333' },
          { label: '高', value: fmtNum(bar.high_price), color: UP_COLOR },
          { label: '低', value: fmtNum(bar.low_price), color: DOWN_COLOR },
          { label: '收', value: fmtNum(bar.close_price), color: priceColor },
        ]}
      />
      <InfoRow
        items={[
          { label: 'MA5', value: fmtNum(ind.ma5[idx]), color: MA_COLORS.MA5 },
          { label: 'MA10', value: fmtNum(ind.ma10[idx]), color: MA_COLORS.MA10 },
          { label: 'MA20', value: fmtNum(ind.ma20[idx]), color: MA_COLORS.MA20 },
          { label: 'MA60', value: fmtNum(ind.ma60[idx]), color: MA_COLORS.MA60 },
        ]}
      />
    </div>
  );
}

function VolumeInfoBar({ hover, latest, ind }: { hover: HoverInfo | null; latest: HoverInfo; ind: StockIndicatorSeries }) {
  const { idx, bar } = hover ?? latest;
  const volColor = bar.close_price >= bar.open_price ? UP_COLOR : DOWN_COLOR;
  return (
    <InfoRow
      items={[
        { label: 'VOL', value: fmtVol(bar.volume), color: volColor },
        { label: 'MA5', value: fmtNum(ind.volume_ma5[idx]), color: MA_COLORS.MA5 },
        { label: 'MA10', value: fmtNum(ind.volume_ma10[idx]), color: MA_COLORS.MA10 },
        { label: 'MA20', value: fmtNum(ind.volume_ma20[idx]), color: MA_COLORS.MA20 },
        { label: '成交额', value: fmtAmount(bar.turnover_amount_billion) },
        { label: '换手率', value: fmtTurnover(bar.turnover_rate) },
      ]}
    />
  );
}

function MACDInfoBar({ hover, latest, ind }: { hover: HoverInfo | null; latest: HoverInfo; ind: StockIndicatorSeries }) {
  const { idx } = hover ?? latest;
  const hist = ind.macd_hist[idx];
  return (
    <InfoRow
      items={[
        { label: 'DIF', value: fmtNum(ind.macd_dif[idx], 4), color: MACD_COLORS.DIF },
        { label: 'DEA', value: fmtNum(ind.macd_dea[idx], 4), color: MACD_COLORS.DEA },
        { label: 'MACD', value: fmtNum(hist, 4), color: hist != null && hist >= 0 ? UP_COLOR : DOWN_COLOR },
      ]}
    />
  );
}

function KDJInfoBar({ hover, latest, ind }: { hover: HoverInfo | null; latest: HoverInfo; ind: StockIndicatorSeries }) {
  const { idx } = hover ?? latest;
  return (
    <InfoRow
      items={[
        { label: 'K', value: fmtNum(ind.kdj_k[idx]), color: KDJ_COLORS.K },
        { label: 'D', value: fmtNum(ind.kdj_d[idx]), color: KDJ_COLORS.D },
        { label: 'J', value: fmtNum(ind.kdj_j[idx]), color: KDJ_COLORS.J },
      ]}
    />
  );
}

function RSIInfoBar({ hover, latest, ind }: { hover: HoverInfo | null; latest: HoverInfo; ind: StockIndicatorSeries }) {
  const { idx } = hover ?? latest;
  return (
    <InfoRow
      items={[
        { label: 'RSI6', value: fmtNum(ind.rsi6[idx]), color: RSI_COLORS.RSI6 },
        { label: 'RSI12', value: fmtNum(ind.rsi12[idx]), color: RSI_COLORS.RSI12 },
        { label: 'RSI24', value: fmtNum(ind.rsi24[idx]), color: RSI_COLORS.RSI24 },
      ]}
    />
  );
}

// ---------------------------------------------------------------------------
// Sub-chart overlay label component
// ---------------------------------------------------------------------------
function SubChartOverlay({
  gridKey,
  title,
  children,
}: {
  gridKey: keyof typeof GRID_POSITIONS;
  title: string;
  children: React.ReactNode;
}) {
  const pos = GRID_POSITIONS[gridKey];
  return (
    <div
      style={{
        position: 'absolute',
        top: pos.top,
        left: GRID_LEFT,
        right: GRID_RIGHT,
        zIndex: 10,
        pointerEvents: 'none',
        padding: '2px 4px',
      }}
    >
      <span style={{ color: '#aaa', fontSize: 10, marginRight: 8, fontWeight: 600 }}>{title}</span>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chart option builder
// Sub-chart order: Volume(1) → MACD(2) → KDJ(3) → RSI(4)
// ---------------------------------------------------------------------------
function buildChartOption(data: StockDetailResponse) {
  const bars = data.daily_bars;
  const ind = data.indicators;
  const dates = bars.map((b) => b.trade_date);

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
    axisLabel: { ...xAxisBase.axisLabel, show: i === grids.length - 1 },
    axisTick: { show: i === grids.length - 1 },
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
    { ...yAxisBase, gridIndex: 3, splitLine: { show: false } }, // KDJ — auto range (no fixed min/max)
    { ...yAxisBase, gridIndex: 4, min: 0, max: 100, splitLine: { show: false } }, // RSI fixed 0-100
  ];

  const dataZoom = [
    { type: 'inside', xAxisIndex: [0, 1, 2, 3, 4], start: 0, end: 100 },
    {
      type: 'slider',
      xAxisIndex: [0, 1, 2, 3, 4],
      start: 0,
      end: 100,
      bottom: '1%',
      height: 18,
      handleSize: '80%',
      borderColor: '#d0d0d0',
      fillerColor: 'rgba(0,120,255,0.1)',
      backgroundColor: '#fff',
      dataBackground: { areaStyle: { color: '#e0e0e0' }, lineStyle: { color: '#bbb' } },
      textStyle: { color: '#666', fontSize: 10 },
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
      axisPointer: { type: 'cross' as const, link: [{ xAxisIndex: 'all' }] },
      show: false, // hide built-in tooltip; we use custom info bar
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
        data: bars.map((b) => [b.open_price, b.close_price, b.low_price, b.high_price]),
        itemStyle: {
          color: UP_COLOR,
          color0: DOWN_COLOR,
          borderColor: UP_COLOR,
          borderColor0: DOWN_COLOR,
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

  const { data, error, isLoading } = useQuery({
    queryKey: ['stock-detail', stockCode],
    queryFn: () => getStockDetail(stockCode as string),
    enabled: Boolean(stockCode),
  });

  // Build date → index map for robust hover resolution
  const dateIndexMap = useMemo<Record<string, number>>(() => {
    if (!data) return {};
    const map: Record<string, number> = {};
    data.daily_bars.forEach((bar, i) => {
      map[bar.trade_date] = i;
    });
    return map;
  }, [data]);

  const onChartEvents = useCallback(
    (bars: DailyBar[], indexMap: Record<string, number>) => ({
      updateAxisPointer: (params: { axesInfo?: { value?: number | string }[] }) => {
        const axesInfo = params?.axesInfo;
        if (!axesInfo || axesInfo.length === 0) return;
        const raw = axesInfo[0].value;
        let idx: number;
        if (typeof raw === 'number') {
          idx = raw;
        } else if (typeof raw === 'string') {
          idx = indexMap[raw] ?? -1;
        } else {
          return;
        }
        if (idx >= 0 && idx < bars.length) {
          setHoverInfo({ idx, bar: bars[idx] });
        }
      },
      globalout: () => setHoverInfo(null),
    }),
    [],
  );

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

  const bars = data.daily_bars;
  const ind = data.indicators;
  const latestIdx = bars.length - 1;
  const latestInfo: HoverInfo = { idx: latestIdx, bar: bars[latestIdx] };
  const priceColor = colorOf(data.change_pct);
  const changeSign = data.change_amount >= 0 ? '+' : '';
  const chartOption = buildChartOption(data);
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
        <QuoteItem label="开盘" value={data.open_price.toFixed(2)} />
        <QuoteItem label="昨收" value={data.prev_close.toFixed(2)} />
        <QuoteItem label="最高" value={data.high_price.toFixed(2)} color={UP_COLOR} />
        <QuoteItem label="最低" value={data.low_price.toFixed(2)} color={DOWN_COLOR} />
        <QuoteItem label="成交额" value={`${data.turnover_amount_billion.toFixed(2)}亿`} />
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
                    {/* K-line hover info (above chart) */}
                    <KLineInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />

                    {/* Chart with sub-chart info overlays */}
                    <div style={{ position: 'relative', height: CHART_HEIGHT }}>
                      {/* Sub-chart info overlays — positioned near each sub-chart */}
                      <SubChartOverlay gridKey="volume" title="VOL">
                        <VolumeInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />
                      </SubChartOverlay>

                      <SubChartOverlay gridKey="macd" title="MACD">
                        <MACDInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />
                      </SubChartOverlay>

                      <SubChartOverlay gridKey="kdj" title="KDJ">
                        <KDJInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />
                      </SubChartOverlay>

                      <SubChartOverlay gridKey="rsi" title="RSI">
                        <RSIInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />
                      </SubChartOverlay>

                      {/* Main chart */}
                      <ReactECharts
                        ref={chartRef}
                        option={chartOption}
                        style={{ height: CHART_HEIGHT }}
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
