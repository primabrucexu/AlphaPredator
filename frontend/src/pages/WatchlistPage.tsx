import { DeleteOutlined, DragOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, AutoComplete, Button, Card, Empty, Input, Space, Table, Tag, Typography, message } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import TagPicker from '../components/TagPicker'
import type { GlobalTag, WatchItem } from '../types'

function QuoteCells({ symbol }: { symbol: string }) {
  const query = useQuery({ queryKey: ['quote', symbol], queryFn: () => api.quote(symbol), refetchInterval: 5000 })
  if (query.error) return <span className="error-text">{(query.error as Error).message}</span>
  if (!query.data) return <span>加载中…</span>
  const up = (query.data.change || 0) >= 0
  return <span className={up ? 'up' : 'down'}>{query.data.price?.toFixed(2) ?? '--'}　{query.data.change_percent?.toFixed(2) ?? '--'}%</span>
}

function StockIdentity({ item }: { item: WatchItem }) {
  const query = useQuery({ queryKey: ['quote', item.symbol], queryFn: () => api.quote(item.symbol), refetchInterval: 5000 })
  const name = item.name || query.data?.name
  return <Link to={`/stocks/${item.symbol}`} className="stock-identity">
    <Typography.Text strong>{name || (query.isLoading ? '名称加载中…' : '名称暂不可用')}</Typography.Text>
    <Typography.Text type="secondary">{item.code}</Typography.Text>
  </Link>
}

function TagEditor({ item, catalog, onAdd, onDelete }: { item: WatchItem; catalog: GlobalTag[]; onAdd: (name: string) => void; onDelete: (id: number) => void }) {
  return <Space wrap size={[4, 4]}>{item.tags.map(tag => <Tag key={tag.id} closable onClose={event => { event.preventDefault(); onDelete(tag.id) }}>{tag.name}</Tag>)}
    <TagPicker catalog={catalog} excludedIds={item.tags.map(tag => tag.id)} onAdd={onAdd} />
  </Space>
}

function QuickAddStock({ excludedSymbols, onAdd, loading }: { excludedSymbols: string[]; onAdd: (symbol: string) => void; loading: boolean }) {
  const [value, setValue] = useState('')
  const [query, setQuery] = useState('')
  useEffect(() => { const timer = setTimeout(() => setQuery(value.trim()), 250); return () => clearTimeout(timer) }, [value])
  const result = useQuery({ queryKey: ['stock-search', query], queryFn: () => api.searchStocks(query), enabled: query.length > 0 })
  const excluded = new Set(excludedSymbols)
  const options = (result.data ?? []).filter(stock => !excluded.has(stock.symbol)).map(stock => ({
    value: stock.symbol,
    label: <div className="search-option"><span>{stock.name}</span><Typography.Text type="secondary">{stock.symbol}</Typography.Text></div>,
  }))
  return <AutoComplete size="small" value={value} options={options} onSearch={setValue} onSelect={symbol => { setValue(''); onAdd(symbol) }}
    notFoundContent={query && !result.isFetching ? '未找到可添加的股票' : null} style={{ width: 220 }}>
    <Input prefix={<PlusOutlined />} placeholder="添加股票：代码 / 名称 / 拼音" allowClear disabled={loading} />
  </AutoComplete>
}

export default function WatchlistPage() {
  const client = useQueryClient()
  const [searchParams] = useSearchParams()
  const watchlist = useQuery({ queryKey: ['watchlist'], queryFn: api.watchlist })
  const catalog = useQuery({ queryKey: ['tag-catalog'], queryFn: api.tagCatalog })
  const [dragging, setDragging] = useState<{ tagId: number; symbol: string }>()
  const activeTag = searchParams.get('tag')
  const refresh = () => Promise.all([
    client.invalidateQueries({ queryKey: ['watchlist'] }),
    client.invalidateQueries({ queryKey: ['tag-catalog'] }),
  ])
  const action = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => { refresh(); message.success('已保存') }, onError: e => { refresh(); message.error(e.message) } })
  const groups = useMemo(() => {
    const items = watchlist.data ?? []
    const tagged = (catalog.data ?? []).map(tag => ({ tag, items: items.filter(item => item.tags.some(itemTag => itemTag.id === tag.id)).sort((left, right) => {
      const leftOrder = left.tags.find(itemTag => itemTag.id === tag.id)?.stock_sort_order ?? left.id
      const rightOrder = right.tags.find(itemTag => itemTag.id === tag.id)?.stock_sort_order ?? right.id
      return leftOrder - rightOrder
    }) }))
    const untagged = { tag: null as GlobalTag | null, items: items.filter(item => item.tags.length === 0) }
    if (activeTag === 'untagged') return [untagged]
    if (activeTag) {
      const id = Number(activeTag)
      const match = tagged.find(group => group.tag.id === id)
      return match ? [match] : []
    }
    return [...tagged.filter(group => group.items.length), ...(untagged.items.length ? [untagged] : [])]
  }, [activeTag, catalog.data, watchlist.data])
  const dropStock = (tag: GlobalTag, targetSymbol: string, items: WatchItem[]) => {
    if (!dragging || dragging.tagId !== tag.id || dragging.symbol === targetSymbol) return
    const symbols = items.map(item => item.symbol)
    const sourceIndex = symbols.indexOf(dragging.symbol); const targetIndex = symbols.indexOf(targetSymbol)
    if (sourceIndex < 0 || targetIndex < 0) return
    const [moved] = symbols.splice(sourceIndex, 1); symbols.splice(targetIndex, 0, moved); setDragging(undefined)
    action.mutate(() => api.reorderTagStocks(tag.id, symbols))
  }
  const selectedName = activeTag === 'untagged' ? '未分类' : catalog.data?.find(tag => String(tag.id) === activeTag)?.name
  return <div className="stack-lg">
    <div className="page-heading"><div><Typography.Title>{selectedName ? `我的自选 · ${selectedName}` : '我的自选'}</Typography.Title><Typography.Text type="secondary">标签自动形成分组；一只股票可以出现在多个标签分组中。</Typography.Text></div></div>
    {watchlist.error && <Alert type="error" message="自选数据加载失败" description={(watchlist.error as Error).message} />}
    {catalog.error && <Alert type="error" message="标签数据加载失败" description={(catalog.error as Error).message} />}
    {!watchlist.isLoading && !watchlist.data?.length && <Card><Empty description="还没有自选股，请先搜索一只股票并在详情页加入自选" /></Card>}
    {!!watchlist.data?.length && !watchlist.isLoading && !catalog.isLoading && !groups.length && <Card><Empty description="该标签下没有自选股" /></Card>}
    {groups.map(({ tag, items }) => <Card key={tag?.id ?? 'untagged'} className="watch-group" title={<Space><span>{tag?.name ?? '未分类'}</span><Typography.Text type="secondary">{items.length}</Typography.Text></Space>}
      extra={tag ? <QuickAddStock excludedSymbols={items.map(item => item.symbol)} loading={action.isPending} onAdd={symbol => action.mutate(() => api.addTag(symbol, tag.name))} /> : undefined}>
      <Table<WatchItem> rowKey="id" pagination={false} dataSource={items} onRow={item => tag ? ({
        draggable: true,
        onDragStart: () => setDragging({ tagId: tag.id, symbol: item.symbol }),
        onDragOver: event => event.preventDefault(),
        onDrop: () => dropStock(tag, item.symbol, items),
        onDragEnd: () => setDragging(undefined),
      }) : {}} columns={[
        ...(tag ? [{ title: '', key: 'sort', width: 34, render: () => <DragOutlined className="stock-drag" title="拖动排序" /> }] : []),
        { title: '股票', key: 'stock', render: (_, item) => <StockIdentity item={item} /> },
        { title: '标签', key: 'tags', render: (_, item) => <TagEditor item={item} catalog={catalog.data ?? []} onAdd={tagName => action.mutate(() => api.addTag(item.symbol, tagName))} onDelete={tagId => action.mutate(() => api.deleteTag(item.symbol, tagId))} /> },
        { title: '最新行情', dataIndex: 'symbol', render: symbol => <QuoteCells symbol={symbol} /> },
        { title: '', key: 'delete', width: 56, render: (_, item) => <Button type="text" danger title="移出自选" icon={<DeleteOutlined />} onClick={() => action.mutate(() => api.deleteWatch(item.id))} /> },
      ]} />
    </Card>)}
  </div>
}
