import { useQuery } from '@tanstack/react-query'
import { Alert, Card, Descriptions, Pagination, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { api } from '../api'
import type { ModeScreeningCurrentState, ModeScreeningSaleResult, ModeScreeningStockResult, ModeScreeningTradeResult, Task } from '../types'
import { activeTaskStatuses } from './TaskStatusTag'

interface OpenTrade {
  signal_date: string
  buy_date: string
  buy_price: string
  remaining_fraction: string
  realized_return: string
  sells?: ModeScreeningSaleResult[]
}

interface TradeRow {
  key: string
  state: string
  signalDate: string
  buyDate: string
  buyPrice: string
  operations: ModeScreeningSaleResult[]
  realizedReturn: string
}

const text = (value: unknown) => value === null || value === undefined || value === '' ? '—' : String(value)
const percent = (value: unknown) => {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : '—'
}
const decimal3 = (value: unknown) => {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(3) : '—'
}
const evidence = (row: ModeScreeningStockResult, conditionId: string) => row.evidence.find(item => item.condition_id === conditionId)
const macdWindow = (row: ModeScreeningStockResult) => {
  const values = evidence(row, 'C1')?.values ?? {}
  const keys = values.h_s_minus_4 === undefined
    ? ['h_s_minus_2', 'h_s_minus_1', 'h_s']
    : ['h_s_minus_4', 'h_s_minus_3', 'h_s_minus_2', 'h_s_minus_1', 'h_s']
  return keys.map(key => values[key])
}
type ResultSortField = 'win_rate' | 'average_return' | 'maximum_return'
type ResultSortOrder = 'asc' | 'desc'
const currentStateLabels: Record<string, string> = {
  pending_entry: 'S点待买入',
  bought_today: 'B点刚买入',
  holding: '持仓中',
  take_profit: '已执行 TP1',
  pending_exit: '待卖出',
  completed: '已结束（历史版本）',
}
const currentStateOptions = (['pending_entry', 'bought_today', 'holding', 'take_profit', 'pending_exit'] as ModeScreeningCurrentState[])
  .map(value => ({ value, label: currentStateLabels[value] }))

function TradeDetails({ taskId, result }: { taskId: number; result: ModeScreeningStockResult }) {
  const [page, setPage] = useState(1)
  const trades = useQuery({
    queryKey: ['mode-screening-trades', taskId, result.id, page],
    queryFn: () => api.modeScreeningTrades(taskId, result.id, page, 10),
  })
  const rows: TradeRow[] = []
  const append = (trade: Pick<ModeScreeningTradeResult, 'signal_date' | 'buy_date' | 'buy_price' | 'realized_return' | 'sells'>, state: string, prefix: string) => {
    rows.push({
      key: prefix,
      state,
      signalDate: trade.signal_date,
      buyDate: trade.buy_date,
      buyPrice: trade.buy_price,
      operations: trade.sells,
      realizedReturn: trade.realized_return,
    })
  }
  const openTrade = result.open_trade as unknown as OpenTrade | null
  if (page === 1 && openTrade) append({ ...openTrade, sells: openTrade.sells ?? [] }, `未平仓（剩余 ${percent(openTrade.remaining_fraction)}）`, 'open')
  trades.data?.items.forEach(trade => append(trade, '已结束', `trade-${trade.id}`))
  const columns: ColumnsType<TradeRow> = [
    { title: '状态', dataIndex: 'state', width: 170, render: value => <Tag color={String(value).startsWith('未平仓') ? 'warning' : 'success'}>{value}</Tag> },
    { title: '信号日', dataIndex: 'signalDate', width: 120 },
    { title: '买入日', dataIndex: 'buyDate', width: 120 },
    { title: '买入价', dataIndex: 'buyPrice', width: 90 },
    { title: '操作明细', dataIndex: 'operations', width: 440, render: (operations: ModeScreeningSaleResult[]) => operations.length
      ? <Space direction="vertical" size={2}>{operations.map((sale, index) => <Typography.Text key={`${sale.date}-${index}`}>
        {sale.date} {sale.reason_id}｜卖出 {percent(sale.fraction_of_original)}｜{sale.price}｜收益 {percent(sale.return_rate)}
      </Typography.Text>)}</Space>
      : <Typography.Text type="secondary">暂无卖出操作</Typography.Text> },
    { title: '整笔已实现', dataIndex: 'realizedReturn', width: 120, render: percent },
  ]
  return <div className="stack-lg">
    {trades.error && <Alert type="error" showIcon message="交易明细读取失败" description={(trades.error as Error).message} />}
    {result.pending_orders.length > 0 && <Alert type="warning" showIcon message="扫描日仍有待成交订单"
      description={result.pending_orders.map(order => `${text(order.reason_id)}（${text(order.action)}，信号日 ${text(order.signal_date)}）`).join('；')} />}
    <Table<TradeRow> rowKey="key" size="small" loading={trades.isLoading} dataSource={rows} columns={columns} scroll={{ x: 1060 }} pagination={false}
      locale={{ emptyText: result.backtest_status === 'pending_entry' ? '存在等待买入信号，尚未成交' : '历史区间内没有产生交易' }} />
    {(trades.data?.total ?? 0) > 10 && <Pagination current={page} pageSize={10} total={trades.data?.total} showSizeChanger={false} onChange={setPage} />}
  </div>
}

export default function ModeScreeningAnalysisResult({ task }: { task: Task }) {
  const [page, setPage] = useState(1)
  const [sortBy, setSortBy] = useState<ResultSortField | ''>('')
  const [sortOrder, setSortOrder] = useState<ResultSortOrder | ''>('')
  const [currentStates, setCurrentStates] = useState<ModeScreeningCurrentState[]>([])
  const results = useQuery({
    queryKey: ['mode-screening-results', task.id, page, sortBy, sortOrder, currentStates],
    queryFn: () => api.modeScreeningResults(task.id, page, 20, sortBy, sortOrder, currentStates),
    refetchInterval: activeTaskStatuses.has(task.status) ? 2000 : false,
  })
  const summary = task.result
  const columns: ColumnsType<ModeScreeningStockResult> = [
    { title: '股票', fixed: 'left', width: 150, render: (_, row) => <><Typography.Text strong>{row.code}</Typography.Text><br /><Typography.Text type="secondary">{row.name}</Typography.Text></> },
    { title: '信号日', dataIndex: 'signal_date', width: 115, render: text },
    { title: '当前状态', dataIndex: 'current_state', width: 130, render: value => <Tag color={value === 'pending_entry' || value === 'bought_today' ? 'processing' : value === 'pending_exit' ? 'warning' : 'success'}>{currentStateLabels[String(value)] ?? text(value)}</Tag> },
    { title: 'MACD 柱窗口', width: 340, render: (_, row) => <Typography.Text code>{macdWindow(row).map(decimal3).join(' → ')}</Typography.Text> },
    { title: '完成交易', dataIndex: 'completed_trades', width: 90 },
    { title: '盈/亏/平', width: 100, render: (_, row) => `${row.winning_trades}/${row.losing_trades}/${row.flat_trades}` },
    { title: '胜率', dataIndex: 'win_rate', width: 90, render: percent, sorter: true, sortDirections: ['descend', 'ascend'], sortOrder: sortBy === 'win_rate' ? sortOrder === 'desc' ? 'descend' : 'ascend' : null },
    { title: '平均收益', dataIndex: 'average_return', width: 100, render: percent, sorter: true, sortDirections: ['descend', 'ascend'], sortOrder: sortBy === 'average_return' ? sortOrder === 'desc' ? 'descend' : 'ascend' : null },
    { title: '最大收益', dataIndex: 'maximum_return', width: 100, render: percent, sorter: true, sortDirections: ['descend', 'ascend'], sortOrder: sortBy === 'maximum_return' ? sortOrder === 'desc' ? 'descend' : 'ascend' : null },
    { title: '最小收益', dataIndex: 'minimum_return', width: 100, render: percent },
  ]
  return <Card title="SR001 模式选股分析结果">
    <Descriptions column={{ xs: 1, sm: 2, lg: 4 }} items={[
      { key: 'date', label: '扫描日期', children: text(summary.as_of_date) },
      { key: 'rule-version', label: '规则版本', children: `${text(task.input.rule_id)} revision ${text(task.input.rule_revision)}` },
      { key: 'range', label: '历史数据区间', children: `各股票本地最早可用行情 至 ${text(summary.as_of_date)}` },
      { key: 'total', label: '候选股票', children: text(summary.stock_count) },
      { key: 'matched', label: '命中', children: text(summary.matched_stocks) },
      { key: 'not-matched', label: '未命中', children: text(summary.not_matched_stocks) },
      { key: 'skipped', label: '跳过', children: text(summary.skipped_stocks) },
      { key: 'failed', label: '失败', children: text(summary.failed_stocks) },
    ]} />
    {results.error && <Alert className="mt-16" type="error" showIcon message="命中股票读取失败" description={(results.error as Error).message} />}
    <Space className="mt-16" wrap>
      <Typography.Text>当前状态</Typography.Text>
      <Select mode="multiple" allowClear placeholder="全部状态" value={currentStates} options={currentStateOptions} style={{ minWidth: 360 }}
        onChange={value => { setCurrentStates(value as ModeScreeningCurrentState[]); setPage(1) }} />
    </Space>
    <Table<ModeScreeningStockResult> className="mt-16" rowKey="id" loading={results.isLoading} dataSource={results.data?.items} columns={columns} scroll={{ x: 1200 }}
      expandable={{ expandedRowRender: row => <TradeDetails taskId={task.id} result={row} /> }}
      pagination={{ current: page, pageSize: 20, total: results.data?.total, showSizeChanger: false }}
      onChange={(pagination, _filters, sorter) => {
        const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter
        const field = activeSorter.order && ['win_rate', 'average_return', 'maximum_return'].includes(String(activeSorter.field))
          ? activeSorter.field as ResultSortField : ''
        const order: ResultSortOrder | '' = activeSorter.order === 'ascend' ? 'asc' : activeSorter.order === 'descend' ? 'desc' : ''
        const sortingChanged = field !== sortBy || order !== sortOrder
        setSortBy(field); setSortOrder(order); setPage(sortingChanged ? 1 : pagination.current ?? 1)
      }}
      locale={{ emptyText: activeTaskStatuses.has(task.status) ? '正在扫描，暂无命中结果' : '本次没有命中股票' }} />
  </Card>
}
