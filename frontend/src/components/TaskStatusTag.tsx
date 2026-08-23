import { Progress, Tag, Typography } from 'antd'

const statusLabels: Record<string, string> = {
  PENDING: '等待中', RUNNING: '执行中', CANCEL_REQUESTED: '正在取消', SUCCEEDED: '成功',
  PARTIALLY_SUCCEEDED: '部分成功', FAILED: '失败', CANCELLED: '已取消', SKIPPED: '已跳过',
}
const statusColors: Record<string, string> = {
  PENDING: 'default', RUNNING: 'processing', CANCEL_REQUESTED: 'warning', SUCCEEDED: 'success',
  PARTIALLY_SUCCEEDED: 'warning', FAILED: 'error', CANCELLED: 'default', SKIPPED: 'default',
}

export const activeTaskStatuses = new Set(['PENDING', 'RUNNING', 'CANCEL_REQUESTED'])

export function TaskStatusTag({ status }: { status: string }) {
  return <Tag color={statusColors[status] ?? 'default'}>{statusLabels[status] ?? status}</Tag>
}

export function TaskProgress({ progress, status }: { progress: number | null; status: string }) {
  if (progress === null) return <Typography.Text type="secondary">{activeTaskStatuses.has(status) ? '处理中' : '—'}</Typography.Text>
  return <Progress percent={progress} size="small" status={status === 'FAILED' ? 'exception' : undefined} />
}
