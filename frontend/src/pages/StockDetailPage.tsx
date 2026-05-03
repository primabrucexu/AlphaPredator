import { useCallback, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { Alert, Card, Col, Empty, Row, Space, Spin, Tabs, Tag, Typography } from 'antd';
import { useParams } from 'react-router-dom';
import { getStockDetail, type DailyBar, type StockDetailResponse, type StockIndicatorSeries } from '../lib/api';

// ---------------------------------------------------------------------------
// Color tokens (from docs/kline-limit-color-design.md, light theme)
// ---------------------------------------------------------------------------
const UP_COLOR = '#E64B4B';          // up_normal fill
const UP_BORDER_COLOR = '#C62828';   // up_normal border
const DOWN_COLOR = '#2FA164';        // down_normal fill
const DOWN_BORDER_COLOR = '#1E7A4C'; // down_normal border
// Limit colors (P1: requires is_limit_up/is_limit_down fields from backend)
// const UP_LIMIT_COLOR = '#8E24AA';
// const UP_LIMIT_BORDER = '#6A1B9A';
// const DOWN_LIMIT_COLOR = '#1565C0';
// const DOWN_LIMIT_BORDER = '#0D47A1';

const MA_COLORS: Record<string, string> = {
  MA5: '#f5a623',
  MA10: '#7ed321',
  MA20: '#4a90e2',
  MA60: '#9013fe',
};

const KDJ_COLORS = { K: '#f5a623', D: '#7ed321', J: '#cf1322' };
const MACD_COLORS = { DIF: '#f5a623', DEA: '#7ed321' };
const RSI_COLORS = { RSI6: '#f5a623', RSI12: '#7ed321', RSI24: '#cf1322' };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtNum(v: number | null | undefined, decimals = 2): string {
  return v != null ? v.toFixed(decimals) : '--';
}

function fmtVol(v: number): string {
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  return `${(v / 1e4).toFixed(0)}万`;
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
    <div style={{ fontSize: 12, lineHeight: 1.6 }}>
      {items.map(({ label, value, color }) => (
        <span key={label} style={{ marginRight: 16 }}>
          <span style={{ color: '#8c8c8c' }}>{label}: </span>
          <span style={{ color: color ?? '#262626', fontWeight: 500 }}>{value}</span>
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
          { label: '开', value: fmtNum(bar.open_price), color: '#262626' },
          { label: '高', value: fmtNum(bar.high_price), color: UP_COLOR },
          { label: '低', value: fmtNum(bar.low_price), color: DOWN_COLOR },
          { label: '收', value: fmtNum(bar.close_price), color: priceColor },
          { label: '量', value: fmtVol(bar.volume), color: '#262626' },
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
  return (
    <InfoRow
      items={[
        { label: 'VOL', value: fmtVol(bar.volume), color: bar.close_price >= bar.open_price ? UP_COLOR : DOWN_COLOR },
        { label: 'MA5', value: fmtNum(ind.volume_ma5[idx]), color: MA_COLORS.MA5 },
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
// Chart option builder
// ---------------------------------------------------------------------------
function buildChartOption(data: StockDetailResponse) {
  const bars = data.daily_bars;
  const ind = data.indicators;
  const dates = bars.map((b) => b.trade_date);

  const GRID_LEFT = '70px';
  const GRID_RIGHT = '80px';

  // Grid positions (percentage of chart height)
  const grids = [
    { top: '3%', left: GRID_LEFT, right: GRID_RIGHT, height: '37%' },  // K-line
    { top: '44%', left: GRID_LEFT, right: GRID_RIGHT, height: '10%' }, // Volume
    { top: '57%', left: GRID_LEFT, right: GRID_RIGHT, height: '10%' }, // KDJ
    { top: '70%', left: GRID_LEFT, right: GRID_RIGHT, height: '10%' }, // MACD
    { top: '83%', left: GRID_LEFT, right: GRID_RIGHT, height: '9%' },  // RSI
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
    splitLine: { lineStyle: { color: '#e8e8e8', type: 'dashed' as const } },
  };

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
    { ...yAxisBase, gridIndex: 2, min: 0, max: 100, splitLine: { show: false } },
    { ...yAxisBase, gridIndex: 3, splitLine: { show: false } },
    { ...yAxisBase, gridIndex: 4, min: 0, max: 100, splitLine: { show: false } },
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
      fillerColor: 'rgba(100,150,200,0.15)',
      backgroundColor: '#f5f5f5',
      dataBackground: { areaStyle: { color: '#d0d0d0' }, lineStyle: { color: '#bbb' } },
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

  const volMaSeries = {
    ...lineSeriesBase,
    name: 'VOL_MA5',
    xAxisIndex: 1,
    yAxisIndex: 1,
    data: ind.volume_ma5,
    lineStyle: { width: 1, color: MA_COLORS.MA5 },
  };

  const kdjSeries = [
    { key: 'kdj_k', name: 'KDJ_K', color: KDJ_COLORS.K },
    { key: 'kdj_d', name: 'KDJ_D', color: KDJ_COLORS.D },
    { key: 'kdj_j', name: 'KDJ_J', color: KDJ_COLORS.J },
  ].map(({ key, name, color }) => ({
    ...lineSeriesBase,
    name,
    xAxisIndex: 2,
    yAxisIndex: 2,
    data: ind[key as keyof StockIndicatorSeries],
    lineStyle: { width: 1, color },
  }));

  const macdLineSeries = [
    { key: 'macd_dif', name: 'DIF', color: MACD_COLORS.DIF },
    { key: 'macd_dea', name: 'DEA', color: MACD_COLORS.DEA },
  ].map(({ key, name, color }) => ({
    ...lineSeriesBase,
    name,
    xAxisIndex: 3,
    yAxisIndex: 3,
    data: ind[key as keyof StockIndicatorSeries],
    lineStyle: { width: 1, color },
  }));

  const rsiSeries = [
    { key: 'rsi6', name: 'RSI6', color: RSI_COLORS.RSI6 },
    { key: 'rsi12', name: 'RSI12', color: RSI_COLORS.RSI12 },
    { key: 'rsi24', name: 'RSI24', color: RSI_COLORS.RSI24 },
  ].map(({ key, name, color }) => ({
    ...lineSeriesBase,
    name,
    xAxisIndex: 4,
    yAxisIndex: 4,
    data: ind[key as keyof StockIndicatorSeries],
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
      volMaSeries,
      ...kdjSeries,
      ...macdLineSeries,
      {
        name: 'MACD_HIST',
        type: 'bar' as const,
        xAxisIndex: 3,
        yAxisIndex: 3,
        data: ind.macd_hist.map((v) => ({
          value: v,
          itemStyle: { color: v != null && v >= 0 ? UP_COLOR : DOWN_COLOR },
        })),
        barMaxWidth: 8,
      },
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
        <div style={{ fontSize: 11, color: '#8c8c8c', marginBottom: 2 }}>{label}</div>
        <div style={{ fontSize: 14, fontWeight: 500, color: color ?? '#262626' }}>{value}</div>
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

  const onChartEvents = useCallback(
    (bars: DailyBar[]) => ({
      updateAxisPointer: (params: { axesInfo?: { value?: number }[] }) => {
        const axesInfo = params?.axesInfo;
        if (axesInfo && axesInfo.length > 0) {
          const idx = axesInfo[0].value;
          if (typeof idx === 'number' && idx >= 0 && idx < bars.length) {
            setHoverInfo({ idx, bar: bars[idx] });
          }
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
  const events = onChartEvents(bars);

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
                    {/* K-line hover info */}
                    <KLineInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />

                    {/* Sub-chart info bars */}
                    <div style={{ display: 'flex', gap: 24, marginBottom: 4 }}>
                      <VolumeInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />
                    </div>
                    <div style={{ display: 'flex', gap: 24, marginBottom: 4 }}>
                      <KDJInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />
                    </div>
                    <div style={{ display: 'flex', gap: 24, marginBottom: 4 }}>
                      <MACDInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />
                    </div>
                    <div style={{ display: 'flex', gap: 24, marginBottom: 4 }}>
                      <RSIInfoBar hover={hoverInfo} latest={latestInfo} ind={ind} />
                    </div>

                    {/* Main chart */}
                    <ReactECharts
                      ref={chartRef}
                      option={chartOption}
                      style={{ height: 780 }}
                      onEvents={events}
                    />
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
