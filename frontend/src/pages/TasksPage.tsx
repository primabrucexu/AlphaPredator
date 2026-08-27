import { CloudSyncOutlined, LineChartOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Input, Row, Select, Space, Table, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api } from '../api'
import { activeTaskStatuses, TaskProgress, TaskStatusTag } from '../components/TaskStatusTag'
import type { Task } from '../types'

const statusOptions = [
  ['PENDING', '等待中'], ['RUNNING', '执行中'], ['CANCEL_REQUESTED', '正在取消'], ['SUCCEEDED', '成功'],
  ['PARTIALLY_SUCCEEDED', '部分成功'], ['FAILED', '失败'], ['CANCELLED', '已取消'],
].map(([value, label]) => ({ value, label }))

export default function TasksPage() {
  const navigate = useNavigate(); const client = useQueryClient(); const [page, setPage] = useState(1); const [status, setStatus] = useState(''); const [taskType, setTaskType] = useState('')
  const marketCoverage = useQuery({ queryKey: ['market-daily-bars-coverage'], queryFn: api.marketDailyBarsCoverage })
  const createTask = useMutation<Task, Error, () => Promise<Task>>({
    mutationFn: factory => factory(),
    onSuccess: task => { client.invalidateQueries({ queryKey: ['tasks'] }); navigate(`/tasks/${task.id}`) },
    onError: error => {
      const detail = error instanceof ApiError && typeof error.data?.detail === 'object' ? error.data.detail : null
      if (error instanceof ApiError && error.status === 409 && detail?.existing_task_id) {
        message.warning('同类型任务已在等待或执行，已打开现有任务')
        navigate(`/tasks/${detail.existing_task_id}`)
        return
      }
      message.error(error.message)
    },
  })
  const tasks = useQuery({
    queryKey: ['tasks', page, status, taskType], queryFn: () => api.tasks(page, 20, status, taskType.trim()),
    refetchInterval: query => query.state.data?.items.some(task => activeTaskStatuses.has(task.status)) ? 2000 : false,
  })
  const columns: ColumnsType<Task> = [
    { title: '任务', dataIndex: 'title', render: (value, row) => <><Typography.Text strong>{value}</Typography.Text><br /><Typography.Text type="secondary">{row.task_type}</Typography.Text></> },
    { title: '类型', dataIndex: 'scheduling_policy', width: 130, render: value => value === 'EXCLUSIVE_UPDATE' ? '数据更新' : '计算任务' },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <TaskStatusTag status={value} /> },
    { title: '进度', dataIndex: 'progress', width: 190, render: (value, row) => <TaskProgress progress={value} status={row.status} /> },
    { title: '子任务', width: 260, render: (_, row) => row.task_type === 'jygs_limit_up_sync' && typeof row.result.skipped_days === 'number'
      ? `本次 ${row.completed_items} / 跳过 ${row.result.skipped_days} / 共 ${row.total_items}`
      : row.task_type === 'market_daily_bars_update' && typeof row.result.skipped_stocks === 'number'
        ? `成功 ${row.result.succeeded_stocks ?? 0} / 跳过 ${row.result.skipped_stocks} / 失败 ${row.result.failed_stocks ?? 0} / 共 ${row.total_items}`
        : `${row.completed_items}/${row.total_items}` },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: value => dayjs(value).format('YYYY-MM-DD HH:mm:ss') },
  ]
  return <div className="stack-lg tasks-page">
    <div><Typography.Title>任务</Typography.Title><Typography.Text type="secondary">统一创建和查看后台任务，任务按照调度规则串行执行。</Typography.Text></div>
    <Card title="创建任务"><Row gutter={[16, 16]}>
      <Col xs={24} xl={12}><Card type="inner" title="刷新股票搜索目录" extra={<CloudSyncOutlined />}>
        <Typography.Paragraph type="secondary">从 thsdk 获取完整 A 股目录，更新本地代码、名称和拼音索引。</Typography.Paragraph>
        <Button type="primary" loading={createTask.isPending} onClick={() => createTask.mutate(api.createStockDirectoryTask)}>创建刷新任务</Button>
      </Card></Col>
      <Col xs={24} xl={12}><Card type="inner" title="更新股票日线" extra={<LineChartOutlined />}>
        <Typography.Paragraph type="secondary">保存从 2024-06-01 开始的前复权日线；15:45 后包含今天，否则截至昨天。</Typography.Paragraph>
        <Typography.Paragraph>
          当前已有数据：{marketCoverage.isLoading
            ? '读取中…'
            : marketCoverage.error
              ? '读取失败'
              : marketCoverage.data?.start_date && marketCoverage.data.end_date
                ? `${marketCoverage.data.start_date} 至 ${marketCoverage.data.end_date}`
                : '暂无已保存的日线数据'}
        </Typography.Paragraph>
        <Space wrap>
          <Button type="primary" loading={createTask.isPending} onClick={() => createTask.mutate(() => api.createMarketDailyBarsTask('incremental'))}>自动增量更新</Button>
          <Button loading={createTask.isPending} onClick={() => createTask.mutate(() => api.createMarketDailyBarsTask('full'))}>强制全量更新</Button>
        </Space>
      </Card></Col>
    </Row></Card>
    <Card title="任务记录" extra={<Space wrap><Select allowClear placeholder="全部状态" options={statusOptions} value={status || undefined} onChange={value => { setStatus(value ?? ''); setPage(1) }} /><Input allowClear placeholder="按任务类型筛选" value={taskType} onChange={event => { setTaskType(event.target.value); setPage(1) }} /></Space>}>
      {tasks.error && <Alert type="error" showIcon message="任务列表读取失败" description={(tasks.error as Error).message} className="mb-16" />}
      <Table<Task> rowKey="id" loading={tasks.isLoading} dataSource={tasks.data?.items} columns={columns} onRow={row => ({ onClick: () => navigate(`/tasks/${row.id}`) })} rowClassName="clickable-row"
        pagination={{ current: page, pageSize: 20, total: tasks.data?.total, showSizeChanger: false, onChange: setPage }} locale={{ emptyText: '暂无任务记录' }} />
    </Card>
  </div>
}
