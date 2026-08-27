import { Alert, Card, Descriptions, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Task } from '../types'
import ModeScreeningAnalysisResult from './ModeScreeningAnalysisResult'

interface Evidence {
  condition_id: string
  passed: boolean
  values: Record<string, unknown>
}

interface ScreeningMatch {
  symbol: string
  code?: string
  name: string
  data_end_date: string | null
  signal_date: string | null
  evidence?: Evidence[]
  insufficient_history?: boolean
}

interface Sale {
  date: string
  reason_id: string
  price: string
  fraction_of_original: string
  return_rate: string
}

interface Trade {
  signal_date: string
  buy_date: string
  buy_price: string
  sells: Sale[]
  realized_return: string
}

interface OpenTrade extends Trade {
  remaining_fraction: string
}

interface TradeRow {
  key: string
  state: string
  signalDate: string
  buyDate: string
  buyPrice: string
  sellDate: string | null
  reason: string | null
  sellPrice: string | null
  fraction: string | null
  sellReturn: string | null
  realizedReturn: string
}

const text = (value: unknown) => value === null || value === undefined || value === '' ? '—' : String(value)
const count = (value: unknown) => typeof value === 'number' ? value : Number(value ?? 0)
const values = <T,>(value: unknown): T[] => Array.isArray(value) ? value as T[] : []
const percent = (value: unknown) => {
  const number = Number(value)
  return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : '—'
}
const decimal3 = (value: unknown) => {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(3) : '—'
}
const evidence = (match: ScreeningMatch, conditionId: string) => values<Evidence>(match.evidence).find(item => item.condition_id === conditionId)

function ScreeningResult({ task }: { task: Task }) {
  const result = task.result
  const matches = values<ScreeningMatch>(result.matches)
  const columns: ColumnsType<ScreeningMatch> = [
    { title: '股票', fixed: 'left', width: 150, render: (_, row) => <><Typography.Text strong>{row.code ?? row.symbol.split('.')[0]}</Typography.Text><br /><Typography.Text type="secondary">{row.name}</Typography.Text></> },
    { title: '行情截止日', dataIndex: 'data_end_date', width: 120, render: text },
    { title: '信号日', dataIndex: 'signal_date', width: 120, render: text },
    { title: '条件', width: 190, render: (_, row) => <Space size={4} wrap>{['U1', 'U2', 'C1'].map(id => {
      const item = evidence(row, id); return <Tag key={id} color={item ? item.passed ? 'success' : 'error' : undefined}>{id} {item ? item.passed ? '通过' : '未通过' : '未记录'}</Tag>
    })}</Space> },
    { title: '三根 MACD 柱', width: 300, render: (_, row) => {
      const c1 = evidence(row, 'C1')?.values ?? {}
      return <Typography.Text code>{[c1.h_s_minus_2, c1.h_s_minus_1, c1.h_s].map(decimal3).join(' → ')}</Typography.Text>
    } },
    { title: '历史状态', width: 110, render: (_, row) => row.insufficient_history === undefined ? <Tag>未记录</Tag> : row.insufficient_history ? <Tag color="warning">不足 100 根</Tag> : <Tag color="success">充足</Tag> },
  ]
  return <Card title="SR001 选股结果">
    <Descriptions column={{ xs: 1, sm: 2, lg: 4 }} items={[
      { key: 'date', label: '选股基准日', children: text(result.as_of_date) },
      { key: 'total', label: '股票总数', children: count(result.stock_count) },
      { key: 'matched', label: '命中', children: count(result.matched_stocks) },
      { key: 'not-matched', label: '未命中', children: count(result.not_matched_stocks) },
      { key: 'skipped', label: '跳过', children: count(result.skipped_stocks) },
      { key: 'failed', label: '失败', children: count(result.failed_stocks) },
    ]} />
    <Table<ScreeningMatch> className="mt-16" rowKey="symbol" dataSource={matches} columns={columns} scroll={{ x: 900 }}
      pagination={{ pageSize: 20, showSizeChanger: false }} locale={{ emptyText: '本次没有命中股票' }} />
  </Card>
}

function BacktestResult({ task }: { task: Task }) {
  const result = task.result
  const trades = values<Trade>(result.trades)
  const openTrade = result.open_trade && typeof result.open_trade === 'object' ? result.open_trade as unknown as OpenTrade : null
  const rows: TradeRow[] = []
  const append = (trade: Trade, state: string, keyPrefix: string) => {
    const sells = values<Sale>(trade.sells)
    if (!sells.length) rows.push({ key: `${keyPrefix}-open`, state, signalDate: trade.signal_date, buyDate: trade.buy_date, buyPrice: trade.buy_price, sellDate: null, reason: null, sellPrice: null, fraction: null, sellReturn: null, realizedReturn: trade.realized_return })
    sells.forEach((sale, index) => rows.push({ key: `${keyPrefix}-${index}`, state, signalDate: trade.signal_date, buyDate: trade.buy_date, buyPrice: trade.buy_price, sellDate: sale.date, reason: sale.reason_id, sellPrice: sale.price, fraction: sale.fraction_of_original, sellReturn: sale.return_rate, realizedReturn: trade.realized_return }))
  }
  trades.forEach((trade, index) => append(trade, '已结束', `closed-${index}`))
  if (openTrade) append(openTrade, `未平仓（剩余 ${percent(openTrade.remaining_fraction)}）`, 'open')
  const columns: ColumnsType<TradeRow> = [
    { title: '状态', dataIndex: 'state', width: 170, render: value => <Tag color={String(value).startsWith('未平仓') ? 'warning' : 'success'}>{value}</Tag> },
    { title: '信号日', dataIndex: 'signalDate', width: 120 },
    { title: '买入日', dataIndex: 'buyDate', width: 120 },
    { title: '买入价', dataIndex: 'buyPrice', width: 100 },
    { title: '卖出日', dataIndex: 'sellDate', width: 120, render: text },
    { title: '原因', dataIndex: 'reason', width: 90, render: text },
    { title: '卖出价', dataIndex: 'sellPrice', width: 100, render: text },
    { title: '原始仓位占比', dataIndex: 'fraction', width: 130, render: percent },
    { title: '本次收益率', dataIndex: 'sellReturn', width: 120, render: percent },
    { title: '已实现收益率', dataIndex: 'realizedReturn', width: 130, render: percent },
  ]
  const pending = values<{ action: string; reason_id: string; signal_date: string }>(result.pending_orders)
  return <Card title="SR001 个股回测结果">
    <Descriptions column={{ xs: 1, sm: 2, lg: 4 }} items={[
      { key: 'stock', label: '股票', children: `${text(result.code)} ${text(result.name)}` },
      { key: 'range', label: '回测区间', children: `${text(result.start_date)} 至 ${text(result.end_date)}` },
      { key: 'data', label: '实际数据', children: `${text(result.data_start_date)} 至 ${text(result.data_end_date)}` },
      { key: 'status', label: '结果状态', children: text(result.status) },
      { key: 'trades', label: '已完成交易', children: count(result.completed_trades) },
    ]} />
    {pending.length > 0 && <Alert className="mt-16" type="warning" showIcon message="回测结束时仍有待成交订单"
      description={pending.map(order => `${order.reason_id}（${order.action}，信号日 ${order.signal_date}）`).join('；')} />}
    <Table<TradeRow> className="mt-16" rowKey="key" dataSource={rows} columns={columns} scroll={{ x: 1200 }} pagination={false}
      locale={{ emptyText: result.status === 'pending_entry' ? '存在等待买入信号，尚未成交' : '区间内没有产生交易' }} />
  </Card>
}

export default function SR001TaskResult({ task }: { task: Task }) {
  if (task.input.rule_id !== 'SR001' || Object.keys(task.result).length === 0) return null
  if (task.task_type === 'mode_screening_analysis') return <ModeScreeningAnalysisResult task={task} />
  if (task.task_type === 'screening_rule_execute') return <ScreeningResult task={task} />
  if (task.task_type === 'individual_backtest') return <BacktestResult task={task} />
  return null
}
