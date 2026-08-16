import ReactECharts from 'echarts-for-react'
import { Card, InputNumber, Segmented, Space } from 'antd'
import { useMemo, useState } from 'react'
import type { DailyBar } from '../types'

type Indicator = 'MA' | 'EXPMA' | 'MACD' | 'KDJ'

function sma(values: number[], period: number): (number | null)[] {
  return values.map((_, i) => i + 1 < period ? null : values.slice(i + 1 - period, i + 1).reduce((a, b) => a + b, 0) / period)
}
function ema(values: number[], period: number): number[] {
  const alpha = 2 / (period + 1); const result: number[] = []
  values.forEach((value, i) => result.push(i ? alpha * value + (1 - alpha) * result[i - 1] : value))
  return result
}
function macd(values: number[], fast: number, slow: number, signal: number) {
  const fastLine = ema(values, fast), slowLine = ema(values, slow)
  const dif = values.map((_, i) => fastLine[i] - slowLine[i]); const dea = ema(dif, signal)
  return { dif, dea, histogram: dif.map((v, i) => (v - dea[i]) * 2) }
}
function kdj(bars: DailyBar[], period: number, kSmooth: number, dSmooth: number) {
  let k = 50, d = 50
  return bars.reduce<{ k: number[]; d: number[]; j: number[] }>((acc, bar, i) => {
    const window = bars.slice(Math.max(0, i + 1 - period), i + 1)
    const high = Math.max(...window.map(v => v.high)), low = Math.min(...window.map(v => v.low))
    const rsv = high === low ? 50 : (bar.close - low) / (high - low) * 100
    k = ((kSmooth - 1) * k + rsv) / kSmooth; d = ((dSmooth - 1) * d + k) / dSmooth
    acc.k.push(k); acc.d.push(d); acc.j.push(3 * k - 2 * d); return acc
  }, { k: [], d: [], j: [] })
}

const line = (name: string, data: (number | null)[], color: string, xAxisIndex = 0, yAxisIndex = 0) => ({
  name, type: 'line', data, showSymbol: false, smooth: true, xAxisIndex, yAxisIndex,
  lineStyle: { width: 1.2, color }, itemStyle: { color },
})

export default function KlineChart({ bars }: { bars: DailyBar[] }) {
  const [indicator, setIndicator] = useState<Indicator>('MA')
  const [volumeMetric, setVolumeMetric] = useState<'成交量' | '成交额'>('成交量')
  const [ma, setMa] = useState([5, 10, 20, 60]); const [expma, setExpma] = useState([12, 50])
  const [macdParams, setMacdParams] = useState([12, 26, 9]); const [kdjParams, setKdjParams] = useState([9, 3, 3])
  const params = indicator === 'MA' ? ma : indicator === 'EXPMA' ? expma : indicator === 'MACD' ? macdParams : kdjParams
  const setParams = indicator === 'MA' ? setMa : indicator === 'EXPMA' ? setExpma : indicator === 'MACD' ? setMacdParams : setKdjParams
  const option = useMemo(() => {
    const dates = bars.map(v => v.date), closes = bars.map(v => v.close)
    const candle = bars.map(v => ({ value: [v.open, v.close, v.low, v.high], itemStyle: v.is_limit_up ? { color: '#ff2638', borderColor: '#ffd1d5', borderWidth: 2 } : v.is_limit_down ? { color: '#00a854', borderColor: '#b6f2d2', borderWidth: 2 } : undefined }))
    const series: object[] = [{ name: '日K', type: 'candlestick', data: candle, xAxisIndex: 0, yAxisIndex: 0,
      itemStyle: { color: '#ef4444', color0: '#22c55e', borderColor: '#ef4444', borderColor0: '#22c55e' } }]
    if (indicator === 'MA') ma.forEach((p, i) => series.push(line(`MA${p}`, sma(closes, p), ['#f59e0b', '#38bdf8', '#c084fc', '#f472b6'][i % 4])))
    if (indicator === 'EXPMA') expma.forEach((p, i) => series.push(line(`EXPMA${p}`, ema(closes, p), ['#f59e0b', '#38bdf8'][i % 2])))
    series.push({ name: volumeMetric, type: 'bar', data: bars.map(v => ({ value: volumeMetric === '成交量' ? v.volume : v.amount, itemStyle: { color: v.close >= v.open ? '#ef4444' : '#22c55e' } })), xAxisIndex: 1, yAxisIndex: 1 })
    if (indicator === 'MACD') {
      const value = macd(closes, ...macdParams as [number, number, number])
      series.push(line('DIF', value.dif, '#f59e0b', 2, 2), line('DEA', value.dea, '#38bdf8', 2, 2),
        { name: 'MACD', type: 'bar', data: value.histogram.map(v => ({ value: v, itemStyle: { color: v >= 0 ? '#ef4444' : '#22c55e' } })), xAxisIndex: 2, yAxisIndex: 2 })
    }
    if (indicator === 'KDJ') {
      const value = kdj(bars, ...kdjParams as [number, number, number])
      series.push(line('K', value.k, '#f59e0b', 2, 2), line('D', value.d, '#38bdf8', 2, 2), line('J', value.j, '#c084fc', 2, 2))
    }
    const lower = indicator === 'MACD' || indicator === 'KDJ'
    return {
      animation: false, backgroundColor: 'transparent', legend: { top: 2, textStyle: { color: '#9ca3af' } },
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: [{ left: 58, right: 24, top: 38, height: lower ? '49%' : '64%' }, { left: 58, right: 24, top: lower ? '61%' : '76%', height: '12%' }, ...(lower ? [{ left: 58, right: 24, top: '77%', height: '15%' }] : [])],
      xAxis: [0, 1, ...(lower ? [2] : [])].map((_, i) => ({ type: 'category', data: dates, gridIndex: i, boundaryGap: true, axisLabel: { color: '#6b7280', show: i === (lower ? 2 : 1) }, axisLine: { lineStyle: { color: '#30363d' } }, axisPointer: { label: { show: true } } })),
      yAxis: [0, 1, ...(lower ? [2] : [])].map(i => ({ scale: true, gridIndex: i, splitLine: { lineStyle: { color: '#21262d' } }, axisLabel: { color: '#6b7280' } })),
      dataZoom: [{ type: 'inside', xAxisIndex: lower ? [0, 1, 2] : [0, 1], start: 45, end: 100 }, { type: 'slider', xAxisIndex: lower ? [0, 1, 2] : [0, 1], bottom: 4, height: 18, start: 45, end: 100 }], series,
    }
  }, [bars, indicator, volumeMetric, ma, expma, macdParams, kdjParams])
  return <Card title="日 K 与技术指标" extra={<Space wrap>
    <Segmented<'成交量' | '成交额'> value={volumeMetric} options={['成交量', '成交额']} onChange={setVolumeMetric} />
    <Segmented<Indicator> value={indicator} options={['MA', 'EXPMA', 'MACD', 'KDJ']} onChange={setIndicator} />
    {params.map((value, i) => <InputNumber key={`${indicator}-${i}`} size="small" min={1} max={250} value={value} style={{ width: 64 }}
      onChange={next => setParams(params.map((v, index) => index === i ? next || 1 : v))} />)}
  </Space>}><ReactECharts option={option} style={{ height: 620 }} notMerge /></Card>
}
