import { ArrowLeftOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Descriptions, Modal, Space, Table, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { ApiError, api } from '../api'
import SR001TaskResult from '../components/SR001TaskResult'
import { activeTaskStatuses, TaskProgress, TaskStatusTag } from '../components/TaskStatusTag'
import type { Task, TaskItem } from '../types'

function displayTime(value: string | null) { return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—' }

const resultLabels: Record<string, string> = {
  selected_days: '选择天数', executed_days: '实际执行', skipped_days: '历史跳过', succeeded_days: '本次成功',
  failed_days: '失败天数', records: '写入记录', source_count: '行情源数量', processed_count: '本地处理数量',
  mode: '更新模式', target_end_date: '目标结束日期', stock_count: '股票总数', succeeded_stocks: '成功股票',
  skipped_stocks: '跳过股票', failed_stocks: '失败股票', incremental_stocks: '增量更新股票', full_stocks: '全量更新股票',
  written_rows: '写入日线', actual_end_date: '实际行情截止日期',
}

function resultItems(task: Task) {
  return Object.entries(task.result).filter(([key]) => key in resultLabels).map(([key, value]) => ({
    key, label: resultLabels[key], children: String(value),
  }))
}

export default function TaskDetailPage({ section = 'tasks' }: { section?: 'tasks' | 'screening' }) {
  const navigate = useNavigate(); const client = useQueryClient(); const taskId = Number(useParams().taskId); const [page, setPage] = useState(1)
  const [modal, modalContext] = Modal.useModal()
  const task = useQuery({ queryKey: ['task', taskId], queryFn: () => api.task(taskId), enabled: Number.isInteger(taskId), refetchInterval: query => activeTaskStatuses.has(query.state.data?.status ?? '') ? 2000 : false })
  const items = useQuery({ queryKey: ['task-items', taskId, page], queryFn: () => api.taskItems(taskId, page, 50), enabled: Number.isInteger(taskId), refetchInterval: () => activeTaskStatuses.has(task.data?.status ?? '') ? 2000 : false })
  useEffect(() => {
    if (task.data && !activeTaskStatuses.has(task.data.status)) {
      void client.invalidateQueries({ queryKey: ['task-items', taskId] })
    }
  }, [client, task.data?.status, taskId])
  const isMarketDailyBarsTask = task.data?.task_type === 'market_daily_bars_update'
  const cancel = useMutation({ mutationFn: () => api.cancelTask(taskId), onSuccess: () => { message.success('已提交取消请求'); client.invalidateQueries({ queryKey: ['task', taskId] }); client.invalidateQueries({ queryKey: ['tasks'] }) }, onError: error => message.error(error.message) })
  const retry = useMutation({
    mutationFn: () => api.retryFailedMarketDailyBarsTask(taskId),
    onSuccess: created => { message.success('已创建失败股票重试任务'); client.invalidateQueries({ queryKey: ['tasks'] }); navigate(`/tasks/${created.id}`) },
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
  const confirmCancel = () => modal.confirm({ title: '取消任务？', content: '正在执行的处理会在下一个安全检查点停止。', okText: '确认取消', cancelText: '返回', okButtonProps: { danger: true }, onOk: () => cancel.mutateAsync() })
  const columns: ColumnsType<TaskItem> = [
    { title: '#', dataIndex: 'sequence', width: 60, render: value => value + 1 },
    { title: '子任务', dataIndex: 'title' },
    { title: '状态', dataIndex: 'status', width: 110, render: value => <TaskStatusTag status={value} /> },
    { title: '进度', dataIndex: 'progress', width: 180, render: (value, row) => <TaskProgress progress={value} status={row.status} /> },
    { title: isMarketDailyBarsTask ? '处理步骤' : '工作量', width: 110, render: (_, row) => row.total === null ? '—' : isMarketDailyBarsTask ? `第 ${row.current ?? 0}/${row.total} 步` : `${row.current ?? 0}/${row.total}` },
    { title: '状态说明', dataIndex: 'status_message' },
    { title: '错误', dataIndex: 'error', render: value => value || '—' },
  ]
  if (task.error) return <Alert type="error" showIcon message="任务详情读取失败" description={(task.error as Error).message} />
  if (task.data && section === 'tasks' && task.data.scheduling_policy === 'COMPUTE') return <Navigate replace to={`/screening/tasks/${taskId}`} />
  if (task.data && section === 'screening' && task.data.scheduling_policy !== 'COMPUTE') return <Navigate replace to={`/tasks/${taskId}`} />
  const summaryItems = task.data ? resultItems(task.data) : []
  const isSR001Task = task.data?.input.rule_id === 'SR001'
  return <div className="stack-lg task-detail-page">{modalContext}
    <div><Button type="link" icon={<ArrowLeftOutlined />} onClick={() => navigate(section === 'screening' ? '/screening' : '/tasks')}>{section === 'screening' ? '返回模式选股' : '返回任务列表'}</Button></div>
    <Card loading={task.isLoading} title={task.data?.title ?? '任务详情'} extra={task.data && ['PENDING', 'RUNNING'].includes(task.data.status)
      ? <Button danger icon={<StopOutlined />} loading={cancel.isPending} onClick={confirmCancel}>取消任务</Button>
      : task.data?.task_type === 'market_daily_bars_update' && task.data.status === 'PARTIALLY_SUCCEEDED'
        ? <Button type="primary" icon={<ReloadOutlined />} loading={retry.isPending} onClick={() => retry.mutate()}>重试失败股票</Button>
        : null}>
      {task.data && <Space direction="vertical" size="large" className="task-summary">
        <Descriptions column={{ xs: 1, sm: 2, lg: 3 }} items={[
          { key: 'status', label: '状态', children: <TaskStatusTag status={task.data.status} /> },
          { key: 'type', label: '任务类型', children: task.data.task_type },
          { key: 'policy', label: '调度类型', children: task.data.scheduling_policy === 'EXCLUSIVE_UPDATE' ? '数据更新' : '计算任务' },
          { key: 'created', label: '创建时间', children: displayTime(task.data.created_at) },
          { key: 'started', label: '开始时间', children: displayTime(task.data.started_at) },
          { key: 'finished', label: '结束时间', children: displayTime(task.data.finished_at) },
        ]} />
        <div><Typography.Text>{task.data.status_message || '暂无状态说明'}</Typography.Text><TaskProgress progress={task.data.progress} status={task.data.status} /></div>
        {task.data.error && <Alert type="error" showIcon message="任务错误" description={task.data.error} />}
      </Space>}
    </Card>
    {task.data && isSR001Task && <SR001TaskResult task={task.data} />}
    {!isSR001Task && summaryItems.length > 0 && <Card title="执行结果"><Descriptions column={{ xs: 1, sm: 2, lg: 3 }} items={summaryItems} /></Card>}
    <Card title="子任务">
      {items.error && <Alert type="error" showIcon message="子任务读取失败" description={(items.error as Error).message} className="mb-16" />}
      <Table<TaskItem> rowKey="id" loading={items.isLoading} dataSource={items.data?.items} columns={columns} pagination={{ current: page, pageSize: 50, total: items.data?.total, showSizeChanger: false, onChange: setPage }} locale={{ emptyText: '该任务没有子任务' }} />
    </Card>
  </div>
}
