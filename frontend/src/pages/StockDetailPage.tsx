import { PlusOutlined, StarOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Empty, Input, Select, Space, Table, Tag, Typography, message } from 'antd'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import KlineChart from '../components/KlineChart'
import QuoteCard from '../components/QuoteCard'
import type { LimitUpRecord } from '../types'

export default function StockDetailPage() {
  const { symbol = '' } = useParams(); const client = useQueryClient(); const [tagName, setTagName] = useState(''); const [groupId, setGroupId] = useState<number>()
  const bars = useQuery({ queryKey: ['bars', symbol], queryFn: () => api.bars(symbol) })
  const tags = useQuery({ queryKey: ['tags', symbol], queryFn: () => api.tags(symbol) })
  const groups = useQuery({ queryKey: ['groups'], queryFn: api.groups })
  const limitUps = useQuery({ queryKey: ['limit-ups', symbol], queryFn: () => api.limitUps(symbol) })
  const mutate = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => message.success('已保存'), onError: e => message.error(e.message) })
  const addTag = () => { if (!tagName.trim()) return; mutate.mutate(() => api.addTag(symbol, tagName.trim()).then(() => { setTagName(''); return client.invalidateQueries({ queryKey: ['tags', symbol] }) })) }
  const targetGroup = groupId || groups.data?.[0]?.id
  return <div className="stack-lg">
    <QuoteCard symbol={symbol} />
    <Card size="small"><div className="detail-actions">
      <Space wrap><Typography.Text strong>个股标签</Typography.Text>{tags.data?.map(tag => <Tag key={tag.id} closable onClose={e => { e.preventDefault(); mutate.mutate(() => api.deleteTag(symbol, tag.id).then(() => client.invalidateQueries({ queryKey: ['tags', symbol] }))) }}>{tag.name}</Tag>)}
        <Space.Compact><Input size="small" value={tagName} onChange={e => setTagName(e.target.value)} onPressEnter={addTag} placeholder="添加标签" maxLength={32} /><Button size="small" icon={<PlusOutlined />} onClick={addTag} /></Space.Compact></Space>
      <Space><Select value={targetGroup} onChange={setGroupId} style={{ width: 140 }} options={groups.data?.map(g => ({ value: g.id, label: g.name }))} /><Button icon={<StarOutlined />} disabled={!targetGroup} onClick={() => mutate.mutate(() => api.addWatch(targetGroup!, symbol).then(() => client.invalidateQueries({ queryKey: ['groups'] })))}>加入自选</Button></Space>
    </div></Card>
    {bars.error && <Alert type="error" showIcon message="K 线获取失败" description={(bars.error as Error).message} />}
    {bars.data && bars.data.bars.length > 0 && <KlineChart bars={bars.data.bars} />}
    {bars.data && bars.data.bars.length === 0 && <Card><Empty description="行情源没有返回日 K 数据" /></Card>}
    <Card title="最近涨停记录" extra={<Typography.Text type="secondary">来源：韭研公社，最近 10 条</Typography.Text>}>
      {limitUps.error ? <Alert type="error" message="涨停记录读取失败" description={(limitUps.error as Error).message} /> : <Table<LimitUpRecord> rowKey={row => `${row.trade_date}-${row.limit_up_time}`} loading={limitUps.isLoading} dataSource={limitUps.data} pagination={false} locale={{ emptyText: '尚未同步到该股票的涨停记录' }} columns={[
        { title: '日期', dataIndex: 'trade_date', width: 110 }, { title: '封板时间', dataIndex: 'limit_up_time', width: 100 },
        { title: '连板', dataIndex: 'streak_text', width: 90 }, { title: '题材', dataIndex: 'hot_theme', width: 180 },
        { title: '涨停原因', dataIndex: 'reason' },
      ]} />}
    </Card>
  </div>
}
