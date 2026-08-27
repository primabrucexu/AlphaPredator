import { FundOutlined, LineChartOutlined, RiseOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Col, DatePicker, Radio, Row, Select, Space, Table, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api } from '../api'
import { activeTaskStatuses, TaskProgress, TaskStatusTag } from '../components/TaskStatusTag'
import type { StockSummary, Task } from '../types'

const statusOptions = [
  ['PENDING', '等待中'], ['RUNNING', '执行中'], ['CANCEL_REQUESTED', '正在取消'], ['SUCCEEDED', '成功'],
  ['PARTIALLY_SUCCEEDED', '部分成功'], ['FAILED', '失败'], ['CANCELLED', '已取消'],
].map(([value, label]) => ({ value, label }))

const taskTypeOptions = [
  { value: 'screening_rule_execute', label: '信号扫描' },
  { value: 'individual_backtest', label: '个股历史回测' },
]

export default function ModeScreeningPage() {
  const navigate = useNavigate(); const client = useQueryClient(); const [page, setPage] = useState(1); const [status, setStatus] = useState(''); const [taskType, setTaskType] = useState('')
  const [screeningScope, setScreeningScope] = useState<'market' | 'symbols'>('market')
  const [screeningDate, setScreeningDate] = useState<Dayjs | null>(null); const [screeningSearch, setScreeningSearch] = useState(''); const [screeningStocks, setScreeningStocks] = useState<Array<{ value: string; label: string }>>([])
  const [backtestSearch, setBacktestSearch] = useState(''); const [backtestStock, setBacktestStock] = useState<{ value: string; label: string } | null>(null); const [backtestRange, setBacktestRange] = useState<[Dayjs, Dayjs] | null>(null)
  const marketCoverage = useQuery({ queryKey: ['market-daily-bars-coverage'], queryFn: api.marketDailyBarsCoverage })
  const screeningStockOptions = useQuery({ queryKey: ['sr001-screening-stock-search', screeningSearch], queryFn: () => api.searchStocks(screeningSearch), enabled: screeningSearch.trim().length > 0 })
  const backtestStockOptions = useQuery({ queryKey: ['sr001-backtest-stock-search', backtestSearch], queryFn: () => api.searchStocks(backtestSearch), enabled: backtestSearch.trim().length > 0 })
  useEffect(() => {
    const coverage = marketCoverage.data
    if (!coverage?.end_date) return
    setScreeningDate(current => current ?? dayjs(coverage.end_date))
    setBacktestRange(current => {
      if (current) return current
      const end = dayjs(coverage.end_date); const first = coverage.start_date ? dayjs(coverage.start_date) : end
      const candidate = end.subtract(3, 'month')
      return [candidate.isBefore(first) ? first : candidate, end]
    })
  }, [marketCoverage.data])
  const createTask = useMutation<Task, Error, () => Promise<Task>>({
    mutationFn: factory => factory(),
    onSuccess: task => {
      client.invalidateQueries({ queryKey: ['screening-tasks'] }); client.invalidateQueries({ queryKey: ['active-screening-task-count'] })
      navigate(`/screening/tasks/${task.id}`)
    },
    onError: error => {
      const detail = error instanceof ApiError && typeof error.data?.detail === 'object' ? error.data.detail : null
      if (error instanceof ApiError && error.status === 409 && detail?.existing_task_id) {
        message.warning('同类型任务已在等待或执行，已打开现有任务')
        navigate(`/screening/tasks/${detail.existing_task_id}`)
        return
      }
      message.error(error.message)
    },
  })
  const tasks = useQuery({
    queryKey: ['screening-tasks', page, status, taskType], queryFn: () => api.tasks(page, 20, status, taskType, 'COMPUTE'),
    refetchInterval: query => query.state.data?.items.some(task => activeTaskStatuses.has(task.status)) ? 2000 : false,
  })
  const columns: ColumnsType<Task> = [
    { title: '任务', dataIndex: 'title', render: (value, row) => <><Typography.Text strong>{value}</Typography.Text><br /><Typography.Text type="secondary">{row.task_type}</Typography.Text></> },
    { title: '模式', dataIndex: 'task_type', width: 140, render: value => value === 'screening_rule_execute' ? '信号扫描' : '个股历史回测' },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <TaskStatusTag status={value} /> },
    { title: '进度', dataIndex: 'progress', width: 190, render: (value, row) => <TaskProgress progress={value} status={row.status} /> },
    { title: '子任务', width: 110, render: (_, row) => `${row.completed_items}/${row.total_items}` },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: value => dayjs(value).format('YYYY-MM-DD HH:mm:ss') },
  ]
  const stockOptions = (stocks: StockSummary[] = []) => stocks.map(stock => ({ value: stock.symbol, label: `${stock.code} ${stock.name}` }))
  const screeningOptions = [...screeningStocks, ...stockOptions(screeningStockOptions.data).filter(option => !screeningStocks.some(selected => selected.value === option.value))]
  const backtestOptions = [...(backtestStock ? [backtestStock] : []), ...stockOptions(backtestStockOptions.data).filter(option => option.value !== backtestStock?.value)]
  const createScreening = () => {
    if (!screeningDate) return message.error('请选择选股基准日期')
    if (screeningScope === 'symbols' && !screeningStocks.length) return message.error('请至少选择一只股票')
    createTask.mutate(() => api.createSR001ScreeningTask(
      screeningDate.format('YYYY-MM-DD'), screeningScope === 'symbols' ? screeningStocks.map(stock => stock.value) : undefined,
    ))
  }
  const createBacktest = () => {
    if (!backtestStock) return message.error('请选择回测股票')
    if (!backtestRange) return message.error('请选择回测日期范围')
    createTask.mutate(() => api.createSR001IndividualBacktestTask(backtestStock.value, backtestRange[0].format('YYYY-MM-DD'), backtestRange[1].format('YYYY-MM-DD')))
  }
  return <div className="stack-lg tasks-page">
    <div><Typography.Title>模式选股</Typography.Title><Typography.Text type="secondary">创建并查看选股规则执行和历史回测结果。</Typography.Text></div>
    <Card title="SR001 趋势反转" extra={<RiseOutlined />}><Row gutter={[16, 16]}>
      <Col xs={24} xl={12}><Card type="inner" title="信号扫描" extra={<FundOutlined />}>
        <Typography.Paragraph type="secondary">按 SR001 revision 1 扫描指定日期，找出出现对应信号的股票。</Typography.Paragraph>
        <Space direction="vertical" className="w-full" size="middle">
          <DatePicker value={screeningDate} onChange={setScreeningDate} allowClear={false} format="YYYY-MM-DD" className="w-full" placeholder="选股基准日期" />
          <Radio.Group value={screeningScope} onChange={event => setScreeningScope(event.target.value)} options={[
            { value: 'market', label: '全市场扫描' }, { value: 'symbols', label: '指定股票' },
          ]} />
          {screeningScope === 'market'
            ? <Typography.Text type="secondary">扫描当前全部沪深主板非 ST 股票</Typography.Text>
            : <Select mode="multiple" labelInValue allowClear showSearch filterOption={false} value={screeningStocks} onChange={setScreeningStocks}
              onSearch={setScreeningSearch} options={screeningOptions} loading={screeningStockOptions.isFetching}
              className="w-full" placeholder="搜索并选择股票" notFoundContent={screeningSearch && !screeningStockOptions.isFetching ? '未找到股票' : null} />}
          <Button type="primary" loading={createTask.isPending} onClick={createScreening}>{screeningScope === 'market' ? '扫描全市场信号' : '扫描指定股票'}</Button>
        </Space>
      </Card></Col>
      <Col xs={24} xl={12}><Card type="inner" title="个股历史回测" extra={<LineChartOutlined />}>
        <Typography.Paragraph type="secondary">选择一只股票和历史区间，按 SR001 的买入、TP1、EX1、SL1 规则执行确定性回测。</Typography.Paragraph>
        <Space direction="vertical" className="w-full" size="middle">
          <Select labelInValue allowClear showSearch filterOption={false} value={backtestStock} onChange={setBacktestStock} onSearch={setBacktestSearch}
            options={backtestOptions} loading={backtestStockOptions.isFetching} className="w-full" placeholder="搜索并选择股票"
            notFoundContent={backtestSearch && !backtestStockOptions.isFetching ? '未找到股票' : null} />
          <DatePicker.RangePicker value={backtestRange} onChange={value => setBacktestRange(value?.[0] && value[1] ? [value[0], value[1]] : null)} allowClear={false} format="YYYY-MM-DD" className="w-full" />
          <Button type="primary" loading={createTask.isPending} onClick={createBacktest}>创建个股回测任务</Button>
        </Space>
      </Card></Col>
    </Row></Card>
    <Card title="选股任务记录" extra={<Space wrap>
      <Select allowClear placeholder="全部模式" options={taskTypeOptions} value={taskType || undefined} onChange={value => { setTaskType(value ?? ''); setPage(1) }} />
      <Select allowClear placeholder="全部状态" options={statusOptions} value={status || undefined} onChange={value => { setStatus(value ?? ''); setPage(1) }} />
    </Space>}>
      {tasks.error && <Alert type="error" showIcon message="选股任务读取失败" description={(tasks.error as Error).message} className="mb-16" />}
      <Table<Task> rowKey="id" loading={tasks.isLoading} dataSource={tasks.data?.items} columns={columns} onRow={row => ({ onClick: () => navigate(`/screening/tasks/${row.id}`) })} rowClassName="clickable-row"
        pagination={{ current: page, pageSize: 20, total: tasks.data?.total, showSizeChanger: false, onChange: setPage }} locale={{ emptyText: '暂无选股任务记录' }} />
    </Card>
  </div>
}
