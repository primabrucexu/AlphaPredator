import { CloudSyncOutlined, KeyOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, DatePicker, Space, Statistic, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { api } from '../api'

export default function SettingsPage() {
  const client = useQueryClient(); const [range, setRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([dayjs().subtract(30, 'day'), dayjs()])
  const status = useQuery({ queryKey: ['jygs-status'], queryFn: api.jygsStatus })
  const action = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => client.invalidateQueries({ queryKey: ['jygs-status'] }), onError: e => message.error(e.message) })
  return <div className="stack-lg settings-page">
    <div><Typography.Title>数据设置</Typography.Title><Typography.Text type="secondary">行情保持在线获取；这里只维护股票搜索目录与韭研涨停历史。</Typography.Text></div>
    <Card title="股票搜索目录" extra={<CloudSyncOutlined />}>
      <Typography.Paragraph type="secondary">从 thsdk 获取 A 股目录并建立本地代码、名称和拼音索引。不会保存行情。</Typography.Paragraph>
      <Button type="primary" icon={<ReloadOutlined />} loading={action.isPending} onClick={() => action.mutate(() => api.syncStocks().then(result => message.success(`已同步 ${result.count} 只股票`)))}>刷新股票目录</Button>
    </Card>
    <Card title="韭研公社连接" extra={<KeyOutlined />}>
      {status.data?.last_error && <Alert type="error" showIcon message={status.data.last_error} className="mb-16" />}
      <div className="status-row"><Statistic title="配置状态" value={status.data?.is_configured ? '已配置' : '未配置'} /><Statistic title="认证状态" value={status.data?.is_valid ? '有效' : '待验证'} valueStyle={{ color: status.data?.is_valid ? '#22c55e' : '#f59e0b' }} /></div>
      <Typography.Paragraph type="secondary">点击登录后会弹出韭研公社网页。请在弹出的浏览器中完成登录，系统将自动捕获 SESSION 并保存到本机 SQLite。</Typography.Paragraph>
      <Button type="primary" icon={<LinkOutlined />} loading={action.isPending} onClick={() => action.mutate(() => api.loginJygs().then(() => message.success('登录成功，认证信息已保存')))}>{status.data?.is_valid ? '重新登录' : '登录韭研公社'}</Button>
    </Card>
    <Card title="涨停历史同步">
      <Typography.Paragraph type="secondary">按日期从韭研公社逐日拉取并覆盖本地同日记录。同步时间取决于所选日期范围，请保持应用运行。</Typography.Paragraph>
      <Space wrap><DatePicker.RangePicker value={range} onChange={value => value?.[0] && value[1] && setRange([value[0], value[1]])} /><Button type="primary" disabled={!status.data?.is_configured} loading={action.isPending} onClick={() => action.mutate(() => api.syncJygs(range[0].format('YYYY-MM-DD'), range[1].format('YYYY-MM-DD')).then(result => message.success(`同步完成：${result.days} 天，${result.records} 条`)))}>开始同步</Button></Space>
    </Card>
  </div>
}
