import { BarChartOutlined, CheckOutlined, CloseOutlined, DeleteOutlined, DragOutlined, EditOutlined, PlusOutlined, SearchOutlined, SettingOutlined, StarOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Layout, Menu, Modal, Typography, message } from 'antd'
import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { GlobalTag } from '../types'

export default function TagSidebar() {
  const location = useLocation(); const navigate = useNavigate(); const client = useQueryClient()
  const catalog = useQuery({ queryKey: ['tag-catalog'], queryFn: api.tagCatalog })
  const watchlist = useQuery({ queryKey: ['watchlist'], queryFn: api.watchlist })
  const [tags, setTags] = useState<GlobalTag[]>([]); const [search, setSearch] = useState(''); const [dragging, setDragging] = useState<number>()
  const [editing, setEditing] = useState<number>(); const [editName, setEditName] = useState(''); const [newTagName, setNewTagName] = useState('')
  const activeTag = new URLSearchParams(location.search).get('tag')
  useEffect(() => setTags(catalog.data ?? []), [catalog.data])
  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: ['tag-catalog'] }), client.invalidateQueries({ queryKey: ['watchlist'] }), client.invalidateQueries({ queryKey: ['tags'] })])
  const action = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: refresh, onError: error => { setTags(catalog.data ?? []); message.error(error.message) } })
  const visibleTags = useMemo(() => tags.filter(tag => tag.name.toLowerCase().includes(search.trim().toLowerCase())), [search, tags])
  const untaggedCount = watchlist.data?.filter(item => item.tags.length === 0).length ?? 0
  const reorder = (targetId: number) => {
    if (!dragging || dragging === targetId) return
    const next = [...tags]; const sourceIndex = next.findIndex(tag => tag.id === dragging); const targetIndex = next.findIndex(tag => tag.id === targetId)
    if (sourceIndex < 0 || targetIndex < 0) return
    const [moved] = next.splice(sourceIndex, 1); next.splice(targetIndex, 0, moved); setTags(next); setDragging(undefined)
    action.mutate(() => api.reorderTags(next.map(tag => tag.id)))
  }
  const rename = (tag: GlobalTag) => {
    if (!editName.trim()) return
    action.mutate(() => api.renameTag(tag.id, editName.trim()).then(() => { setEditing(undefined) }))
  }
  const create = () => {
    if (!newTagName.trim()) return
    action.mutate(() => api.createTag(newTagName.trim()).then(() => { setNewTagName(''); message.success('标签已创建') }))
  }
  const remove = (tag: GlobalTag) => Modal.confirm({ title: `删除标签“${tag.name}”？`, content: '将从所有关联股票移除此标签，但不会删除自选股。', okText: '删除', okButtonProps: { danger: true }, onOk: () => action.mutateAsync(() => api.deleteGlobalTag(tag.id)).then(() => { if (activeTag === String(tag.id)) navigate('/') }) })
  const navKey = location.pathname.startsWith('/settings') ? '/settings' : '/'
  return <Fragment>
    <Layout.Sider width={200} theme="light" className="sidebar primary-sidebar">
      <Link to="/" className="sidebar-brand"><BarChartOutlined /><span>AlphaPredator</span></Link>
      <Menu mode="inline" selectedKeys={[navKey]} items={[
        { key: '/', icon: <StarOutlined />, label: <Link to="/">我的自选</Link> },
        { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">数据设置</Link> },
      ]} />
    </Layout.Sider>
    {location.pathname === '/' && <Layout.Sider width={240} theme="light" className="sidebar tag-sidebar">
      <div className="tag-sidebar-header"><Typography.Text strong>标签</Typography.Text></div>
      <div className="tag-panel">
        <Input allowClear size="small" prefix={<SearchOutlined />} value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索标签" />
        <div className="tag-create"><Input size="small" value={newTagName} maxLength={64} onChange={event => setNewTagName(event.target.value)} onPressEnter={create} placeholder="新建标签" /><Button size="small" icon={<PlusOutlined />} loading={action.isPending} onClick={create} /></div>
        <div className="tag-list">
        {!search && <Link to="/" className={`tag-row tag-static ${!activeTag && location.pathname === '/' ? 'active' : ''}`}><span>全部标签</span></Link>}
        {visibleTags.map(tag => <div key={tag.id} draggable={editing !== tag.id} className={`tag-row ${activeTag === String(tag.id) ? 'active' : ''}`}
          onDragStart={() => setDragging(tag.id)} onDragOver={event => event.preventDefault()} onDrop={() => reorder(tag.id)}>
          <DragOutlined className="tag-drag" />
          {editing === tag.id ? <><Input autoFocus size="small" value={editName} maxLength={64} onChange={event => setEditName(event.target.value)} onPressEnter={() => rename(tag)} />
            <Button type="text" size="small" icon={<CheckOutlined />} onClick={() => rename(tag)} /><Button type="text" size="small" icon={<CloseOutlined />} onClick={() => setEditing(undefined)} /></>
            : <><Link className="tag-link" to={`/?tag=${tag.id}`}><span title={tag.name}>{tag.name}</span><small>{tag.stock_count}</small></Link><span className="tag-actions">
              <Button type="text" size="small" icon={<EditOutlined />} onClick={() => { setEditing(tag.id); setEditName(tag.name) }} /><Button type="text" danger size="small" icon={<DeleteOutlined />} onClick={() => remove(tag)} /></span></>}
        </div>)}
        {!search && <Link to="/?tag=untagged" className={`tag-row tag-static ${activeTag === 'untagged' ? 'active' : ''}`}><span>未分类</span><small>{untaggedCount}</small></Link>}
        </div>
      </div>
    </Layout.Sider>}
  </Fragment>
}
