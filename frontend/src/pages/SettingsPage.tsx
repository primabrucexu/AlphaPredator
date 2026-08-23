import { KeyOutlined, LinkOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Statistic, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function SettingsPage() {
  const client = useQueryClient(); const navigate = useNavigate()
  const status = useQuery({ queryKey: ['jygs-status'], queryFn: api.jygsStatus })
  const action = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => client.invalidateQueries({ queryKey: ['jygs-status'] }), onError: e => message.error(e.message) })
  return <div className="stack-lg settings-page">
    <div><Typography.Title>数据设置</Typography.Title><Typography.Text type="secondary">管理韭研公社连接；股票目录和涨停历史更新统一在任务页创建。</Typography.Text></div>
    <Card title="韭研公社连接" extra={<KeyOutlined />}>
      {status.data?.last_error && <Alert type="error" showIcon message={status.data.last_error} className="mb-16" />}
      <div className="status-row"><Statistic title="配置状态" value={status.data?.is_configured ? '已配置' : '未配置'} /><Statistic title="认证状态" value={status.data?.is_valid ? '有效' : '待验证'} valueStyle={{ color: status.data?.is_valid ? '#22c55e' : '#f59e0b' }} /></div>
      <Typography.Paragraph type="secondary">点击登录后会弹出韭研公社网页。请在弹出的浏览器中完成登录，系统将自动捕获 SESSION 并保存到本机 SQLite。</Typography.Paragraph>
      <Button type="primary" icon={<LinkOutlined />} loading={action.isPending} onClick={() => action.mutate(() => api.loginJygs().then(() => message.success('登录成功，认证信息已保存')))}>{status.data?.is_valid ? '重新登录' : '登录韭研公社'}</Button>
    </Card>
    <Card title="数据更新任务"><Typography.Paragraph type="secondary">韭研涨停数据和股票搜索目录均通过后台任务更新，可以离开任务详情页后继续执行。</Typography.Paragraph><Button onClick={() => navigate('/tasks')}>前往任务页</Button></Card>
  </div>
}
