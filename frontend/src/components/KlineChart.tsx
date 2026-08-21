import ReactECharts from 'echarts-for-react'
import { Card, InputNumber, Segmented, Space } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { DailyBar } from '../types'

type MainIndicator = 'MA' | 'EXPMA'
type LowerIndicator = 'MACD' | 'KDJ'
type VolumeMetric = '成交量' | '成交额'

interface ChartSettings {
  mainIndicator: MainIndicator
  lowerIndicator: LowerIndicator
  volumeMetric: VolumeMetric
  ma: number[]
  expma: number[]
  macdParams: number[]
  kdjParams: number[]
}

const SETTINGS_KEY = 'alphapredator:kline-settings:v1'
const DEFAULT_SETTINGS: ChartSettings = {
  mainIndicator: 'MA', lowerIndicator: 'MACD', volumeMetric: '成交量',
  ma: [5, 10, 20, 60], expma: [12, 50], macdParams: [12, 26, 9], kdjParams: [9, 3, 3],
}

const DEFAULT_PERIODS: Record<MainIndicator, number[]> = {
  MA: [5, 10, 20, 60, 120, 250],
  EXPMA: [12, 50, 120, 250],
}

function loadSettings(): ChartSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? '{}') as Partial<ChartSettings>
    const periods = (value: unknown, fallback: number[]) => Array.isArray(value) && value.length && value.every(item => Number.isInteger(item) && item > 0) ? value : fallback
    return {
      mainIndicator: saved.mainIndicator === 'EXPMA' ? 'EXPMA' : 'MA',
      lowerIndicator: saved.lowerIndicator === 'KDJ' ? 'KDJ' : 'MACD',
      volumeMetric: saved.volumeMetric === '成交额' ? '成交额' : '成交量',
      ma: periods(saved.ma, DEFAULT_SETTINGS.ma), expma: periods(saved.expma, DEFAULT_SETTINGS.expma),
      macdParams: periods(saved.macdParams, DEFAULT_SETTINGS.macdParams), kdjParams: periods(saved.kdjParams, DEFAULT_SETTINGS.kdjParams),
    }
  } catch {
    return DEFAULT_SETTINGS
  }
}

function resizePeriods(current: number[], count: number, defaults: number[]): number[] {
  return Array.from({ length: count }, (_, index) => current[index] ?? defaults[index] ?? current.at(-1) ?? 1)
}

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
  lineStyle: { width: 1.2, color }, itemStyle: { color }, tooltip: { valueFormatter: (value: number) => value.toFixed(2) },
})

interface DisplaySeries { name?: string; data?: unknown[] }

function seriesValue(series: DisplaySeries, index: number): number | null {
  const entry = series.data?.[index]
  const value = typeof entry === 'object' && entry !== null && 'value' in entry ? (entry as { value: unknown }).value : entry
  return typeof value === 'number' ? value : null
}

function indicatorGraphics(series: DisplaySeries[], index: number, mainIndicator: MainIndicator, lowerIndicator: LowerIndicator, volumeMetric: VolumeMetric) {
  const format = (name: string, value: number) => name.startsWith('成交量')
    ? `${(value / 1_000_000).toFixed(2)}万手`
    : name.startsWith('成交额') ? `${(value / 100_000_000).toFixed(2)}亿` : value.toFixed(2)
  const text = (names: string[]) => names.map(name => {
    const item = series.find(row => row.name === name)
    const value = item ? seriesValue(item, index) : null
    return `${name} ${value === null ? '--' : format(name, value)}`
  }).join('   ')
  const mainPattern = mainIndicator === 'MA' ? /^MA\d+$/ : /^EXPMA\d+$/
  const volumeMaPattern = new RegExp(`^${volumeMetric}MA\\d+$`)
  return [
    { id: 'main-indicator-values', type: 'text', left: 68, top: 45, silent: true, style: { text: text(series.filter(row => row.name && mainPattern.test(row.name)).map(row => row.name!)), fill: '#4b5563', font: '12px sans-serif' } },
    { id: 'volume-indicator-value', type: 'text', left: 68, top: '58%', silent: true, style: { text: text([volumeMetric, ...series.filter(row => row.name && volumeMaPattern.test(row.name)).map(row => row.name!)]), fill: '#4b5563', font: '12px sans-serif' } },
    { id: 'lower-indicator-values', type: 'text', left: 68, top: '75%', silent: true, style: { text: text(lowerIndicator === 'MACD' ? ['DIF', 'DEA', 'MACD'] : ['K', 'D', 'J']), fill: '#4b5563', font: '12px sans-serif' } },
  ]
}

interface Props {
  bars: DailyBar[]
  hasEarlier: boolean
  isLoadingEarlier: boolean
  onLoadEarlier: () => void
}

export default function KlineChart({ bars, hasEarlier, isLoadingEarlier, onLoadEarlier }: Props) {
  const [initialSettings] = useState(loadSettings)
  const [mainIndicator, setMainIndicator] = useState<MainIndicator>(initialSettings.mainIndicator)
  const [lowerIndicator, setLowerIndicator] = useState<LowerIndicator>(initialSettings.lowerIndicator)
  const [volumeMetric, setVolumeMetric] = useState<VolumeMetric>(initialSettings.volumeMetric)
  const [ma, setMa] = useState(initialSettings.ma); const [expma, setExpma] = useState(initialSettings.expma)
  const [macdParams, setMacdParams] = useState(initialSettings.macdParams); const [kdjParams, setKdjParams] = useState(initialSettings.kdjParams)
  const mainParams = mainIndicator === 'MA' ? ma : expma
  const setMainParams = mainIndicator === 'MA' ? setMa : setExpma
  const mainDefaults = DEFAULT_PERIODS[mainIndicator]
  const lowerParams = lowerIndicator === 'MACD' ? macdParams : kdjParams
  const setLowerParams = lowerIndicator === 'MACD' ? setMacdParams : setKdjParams
  const zoomRef = useRef({ startValue: Math.max(0, bars.length - 120), endValue: Math.max(0, bars.length - 1) })
  const previousFirstRef = useRef('')
  const loadLockRef = useRef(false)
  const requestedEarliestRef = useRef('')
  useEffect(() => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ mainIndicator, lowerIndicator, volumeMetric, ma, expma, macdParams, kdjParams }))
  }, [mainIndicator, lowerIndicator, volumeMetric, ma, expma, macdParams, kdjParams])
  useEffect(() => {
    if (loadLockRef.current && !isLoadingEarlier && bars[0]?.date !== requestedEarliestRef.current) {
      loadLockRef.current = false
    }
  }, [bars, isLoadingEarlier])
  const option = useMemo(() => {
    const previousFirst = previousFirstRef.current
    if (!previousFirst) {
      zoomRef.current = { startValue: Math.max(0, bars.length - 120), endValue: Math.max(0, bars.length - 1) }
    } else if (previousFirst !== bars[0]?.date) {
      const prependCount = bars.findIndex(bar => bar.date === previousFirst)
      zoomRef.current = prependCount > 0
        ? { startValue: zoomRef.current.startValue + prependCount, endValue: zoomRef.current.endValue + prependCount }
        : { startValue: Math.max(0, bars.length - 120), endValue: Math.max(0, bars.length - 1) }
    }
    previousFirstRef.current = bars[0]?.date ?? ''
    const dates = bars.map(v => v.date), closes = bars.map(v => v.close)
    const candle = bars.map(v => ({ value: [v.open, v.close, v.low, v.high], itemStyle: v.is_limit_up ? { color: '#facc15', borderColor: '#ca8a04', borderWidth: 2 } : v.is_limit_down ? { color: '#3b82f6', borderColor: '#1d4ed8', borderWidth: 2 } : undefined }))
    const series: object[] = [{ name: '日K', type: 'candlestick', data: candle, xAxisIndex: 0, yAxisIndex: 0,
      itemStyle: { color: '#ef4444', color0: '#22c55e', borderColor: '#ef4444', borderColor0: '#22c55e' } }]
    if (mainIndicator === 'MA') ma.forEach((p, i) => series.push(line(`MA${p}`, sma(closes, p), ['#d97706', '#0284c7', '#9333ea', '#db2777'][i % 4])))
    if (mainIndicator === 'EXPMA') expma.forEach((p, i) => series.push(line(`EXPMA${p}`, ema(closes, p), ['#d97706', '#0284c7'][i % 2])))
    const volumeValues = bars.map(v => volumeMetric === '成交量' ? v.volume : v.amount)
    series.push({ name: volumeMetric, type: 'bar', data: bars.map((v, i) => ({ value: volumeValues[i], itemStyle: { color: v.close >= v.open ? '#ef4444' : '#22c55e' } })), xAxisIndex: 1, yAxisIndex: 1 })
    ;[5, 10, 20].forEach((period, index) => series.push(line(`${volumeMetric}MA${period}`, sma(volumeValues, period), ['#db2777', '#d97706', '#0284c7'][index], 1, 1)))
    if (lowerIndicator === 'MACD') {
      const value = macd(closes, ...macdParams as [number, number, number])
      series.push(line('DIF', value.dif, '#d97706', 2, 2), line('DEA', value.dea, '#0284c7', 2, 2),
        { name: 'MACD', type: 'bar', data: value.histogram.map(v => ({ value: v, itemStyle: { color: v >= 0 ? '#ef4444' : '#22c55e' } })), xAxisIndex: 2, yAxisIndex: 2,
          tooltip: { valueFormatter: (value: number) => value.toFixed(2) },
          markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: '#9ca3af', width: 1 }, data: [{ yAxis: 0 }] } })
    }
    if (lowerIndicator === 'KDJ') {
      const value = kdj(bars, ...kdjParams as [number, number, number])
      series.push(line('K', value.k, '#d97706', 2, 2), line('D', value.d, '#0284c7', 2, 2), line('J', value.j, '#9333ea', 2, 2))
    }
    return {
      animation: false, backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, formatter: (params: { dataIndex: number }[]) => {
        const index = params[0]?.dataIndex
        const bar = bars[index]
        if (!bar) return ''
        const change = bar.previous_close ? (bar.close - bar.previous_close) / bar.previous_close * 100 : null
        return `${bar.date}<br/>最高　${bar.high.toFixed(2)}<br/>最低　${bar.low.toFixed(2)}<br/>开盘　${bar.open.toFixed(2)}<br/>收盘　${bar.close.toFixed(2)}<br/>涨幅　${change === null ? '--' : `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`}`
      } },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: [{ left: 64, right: 24, top: 42, height: '47%' }, { left: 64, right: 24, top: '58%', height: '12%' }, { left: 64, right: 24, top: '75%', height: '14%' }],
      xAxis: [0, 1, 2].map((_, i) => ({
        type: 'category', data: dates, gridIndex: i, boundaryGap: true,
        position: i === 2 ? 'top' : 'bottom',
        axisLabel: { color: '#6b7280', show: i === 0, interval: 19, hideOverlap: true },
        axisLine: { lineStyle: { color: i === 2 ? '#94a3b8' : '#d1d5db', width: i === 2 ? 2 : 1 } }, axisPointer: { label: { show: true } },
      })),
      yAxis: [0, 1, 2].map(i => ({
        scale: true, gridIndex: i,
        ...(i === 2 && lowerIndicator === 'MACD' ? {
          min: ({ min, max }: { min: number; max: number }) => -Math.max(Math.abs(min), Math.abs(max)),
          max: ({ min, max }: { min: number; max: number }) => Math.max(Math.abs(min), Math.abs(max)),
        } : {}),
        splitLine: { show: i !== 2 || lowerIndicator !== 'MACD', lineStyle: { color: '#e5e7eb' } },
        axisTick: { show: i !== 1 && (i !== 2 || lowerIndicator !== 'MACD') },
        axisLabel: { show: i !== 1 && (i !== 2 || lowerIndicator !== 'MACD'), color: '#6b7280', formatter: (value: number) => value.toFixed(2) },
      })),
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1, 2], ...zoomRef.current },
        { type: 'slider', xAxisIndex: [0, 1, 2], bottom: 4, height: 18, ...zoomRef.current },
      ],
      graphic: indicatorGraphics(series as DisplaySeries[], bars.length - 1, mainIndicator, lowerIndicator, volumeMetric),
      series,
    }
  }, [bars, mainIndicator, lowerIndicator, volumeMetric, ma, expma, macdParams, kdjParams])
  const handleZoom = useCallback((_event: unknown, chart: { getOption: () => { dataZoom?: { start?: number; startValue?: number; endValue?: number }[] } }) => {
    const zoom = chart.getOption().dataZoom?.[0]
    if (!zoom) return
    zoomRef.current = { startValue: Number(zoom.startValue ?? 0), endValue: Number(zoom.endValue ?? bars.length - 1) }
    if (Number(zoom.start ?? 100) <= 1.5 && zoomRef.current.startValue <= 3 && hasEarlier && !isLoadingEarlier && !loadLockRef.current) {
      loadLockRef.current = true
      requestedEarliestRef.current = bars[0]?.date ?? ''
      onLoadEarlier()
    }
  }, [bars.length, hasEarlier, isLoadingEarlier, onLoadEarlier])
  const handleAxisPointer = useCallback((event: { axesInfo?: { value?: string | number; seriesDataIndices?: { dataIndexInside?: number }[] }[] }, chart: {
    getOption: () => { series?: DisplaySeries[]; xAxis?: { data?: string[] }[] }
    setOption: (option: { graphic: object[] }) => void
  }) => {
    const axis = event.axesInfo?.find(item => item.value !== undefined)
    const axisValue = axis?.value
    const index = axis?.seriesDataIndices?.[0]?.dataIndexInside
      ?? (typeof axisValue === 'number' ? Math.round(axisValue) : chart.getOption().xAxis?.[0]?.data?.indexOf(String(axisValue)))
      ?? -1
    if (index < 0) return
    chart.setOption({ graphic: indicatorGraphics(chart.getOption().series ?? [], index, mainIndicator, lowerIndicator, volumeMetric) })
  }, [lowerIndicator, mainIndicator, volumeMetric])
  return <Card className="kline-card"><div className="chart-periods"><span>分时</span><b>日 K</b><span>五日</span><span>周 K</span><span>月 K</span></div><Space wrap className="chart-controls">
    <Segmented<MainIndicator> value={mainIndicator} options={['MA', 'EXPMA']} onChange={setMainIndicator} />
    <span className="chart-frequency">日线</span>
    <span>数量</span><InputNumber size="small" min={1} max={8} precision={0} value={mainParams.length} style={{ width: 56 }}
      onChange={next => setMainParams(resizePeriods(mainParams, next || 1, mainDefaults))} />
    {mainParams.map((value, i) => <InputNumber key={`${mainIndicator}-${i}`} size="small" min={1} max={250} value={value} style={{ width: 64 }}
      onChange={next => setMainParams(mainParams.map((v, index) => index === i ? next || 1 : v))} />)}
    <Segmented<LowerIndicator> value={lowerIndicator} options={['MACD', 'KDJ']} onChange={setLowerIndicator} />
    {lowerParams.map((value, i) => <InputNumber key={`${lowerIndicator}-${i}`} size="small" min={1} max={250} value={value} style={{ width: 64 }}
      onChange={next => setLowerParams(lowerParams.map((v, index) => index === i ? next || 1 : v))} />)}
    <span className="chart-loading-note">{isLoadingEarlier ? '正在加载更早数据…' : hasEarlier ? '拖到最左侧自动加载历史数据' : '已到最早可用数据'}</span>
    <Segmented<VolumeMetric> value={volumeMetric} options={['成交量', '成交额']} onChange={setVolumeMetric} />
  </Space><ReactECharts option={option} onEvents={{ datazoom: handleZoom, updateAxisPointer: handleAxisPointer }} style={{ height: 720 }} notMerge /></Card>
}
