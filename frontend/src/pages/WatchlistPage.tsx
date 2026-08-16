import { DeleteOutlined, EditOutlined, FolderAddOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Empty, Input, Modal, Select, Space, Table, Typography, message } from 'antd'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { WatchGroup, WatchItem } from '../types'

function QuoteCells({ symbol }: { symbol: string }) {
  const query = useQuery({ queryKey: ['quote', symbol], queryFn: () => api.quote(symbol), refetchInterval: 5000 })
  if (query.error) return <span className="error-text">{(query.error as Error).message}</span>
  if (!query.data) return <span>加载中…</span>
  const up = (query.data.change || 0) >= 0
  return <span className={up ? 'up' : 'down'}>{query.data.price?.toFixed(2) ?? '--'}　{query.data.change_percent?.toFixed(2) ?? '--'}%</span>
}

export default function WatchlistPage() {
  const client = useQueryClient(); const [newName, setNewName] = useState(''); const [editing, setEditing] = useState<number | null>(null); const [editName, setEditName] = useState('')
  const groups = useQuery({ queryKey: ['groups'], queryFn: api.groups })
  const refresh = () => client.invalidateQueries({ queryKey: ['groups'] })
  const action = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => { refresh(); message.success('已保存') }, onError: e => message.error(e.message) })
  const create = () => { if (newName.trim()) action.mutate(() => api.createGroup(newName.trim())); setNewName('') }
  const rename = (group: WatchGroup) => { if (editName.trim()) action.mutate(() => api.renameGroup(group.id, editName.trim())); setEditing(null) }
  return <div className="stack-lg">
    <div className="page-heading"><div><Typography.Title>我的自选</Typography.Title><Typography.Text type="secondary">行情每 5 秒刷新；连接失败时保留明确错误。</Typography.Text></div>
      <Space.Compact><Input value={newName} onChange={e => setNewName(e.target.value)} onPressEnter={create} placeholder="新分组名称" /><Button icon={<FolderAddOutlined />} onClick={create}>创建分组</Button></Space.Compact></div>
    {groups.error && <Alert type="error" message="自选数据加载失败" description={(groups.error as Error).message} />}
    {!groups.isLoading && !groups.data?.some(group => group.items.length) && <Card><Empty description="还没有自选股，请先搜索一只股票并在详情页加入自选" /></Card>}
    {groups.data?.map(group => <Card key={group.id} className="watch-group" title={editing === group.id ? <Space.Compact>
      <Input autoFocus value={editName} onChange={e => setEditName(e.target.value)} onPressEnter={() => rename(group)} /><Button onClick={() => rename(group)}>保存</Button>
    </Space.Compact> : <Space><span>{group.name}</span><Typography.Text type="secondary">{group.items.length}</Typography.Text></Space>}
      extra={<Space><Button type="text" icon={<EditOutlined />} onClick={() => { setEditing(group.id); setEditName(group.name) }} />
        {!group.is_default && <Button type="text" danger icon={<DeleteOutlined />} onClick={() => Modal.confirm({ title: `删除分组“${group.name}”？`, content: '其中股票会移动到默认分组。', onOk: () => action.mutateAsync(() => api.deleteGroup(group.id)) })} />}</Space>}>
      <Table<WatchItem> rowKey="id" pagination={false} dataSource={group.items} locale={{ emptyText: '分组为空' }} columns={[
        { title: '股票', dataIndex: 'symbol', render: symbol => <Link to={`/stocks/${symbol}`}>{symbol}</Link> },
        { title: '最新行情', dataIndex: 'symbol', render: symbol => <QuoteCells symbol={symbol} /> },
        { title: '移动到', key: 'move', width: 180, render: (_, item) => <Select value={group.id} style={{ width: 150 }} options={groups.data?.map(g => ({ value: g.id, label: g.name }))} onChange={id => action.mutate(() => api.moveWatch(item.id, id))} /> },
        { title: '', key: 'delete', width: 56, render: (_, item) => <Button type="text" danger icon={<DeleteOutlined />} onClick={() => action.mutate(() => api.deleteWatch(item.id))} /> },
      ]} />
    </Card>)}
  </div>
}
