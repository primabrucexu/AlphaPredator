import { StarOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Empty, Space, Tag, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import KlineChart from '../components/KlineChart'
import QuoteCard from '../components/QuoteCard'
import TagPicker from '../components/TagPicker'
import type { DailyBar } from '../types'

export default function StockDetailPage() {
  const { symbol = '' } = useParams(); const client = useQueryClient()
  const [history, setHistory] = useState<DailyBar[]>([]); const [hasEarlier, setHasEarlier] = useState(true)
  const bars = useQuery({ queryKey: ['bars', symbol], queryFn: () => api.bars(symbol) })
  const tags = useQuery({ queryKey: ['tags', symbol], queryFn: () => api.tags(symbol) })
  const catalog = useQuery({ queryKey: ['tag-catalog'], queryFn: api.tagCatalog })
  const watchlist = useQuery({ queryKey: ['watchlist'], queryFn: api.watchlist })
  const mutate = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: () => message.success('已保存'), onError: e => message.error(e.message) })
  const earlier = useMutation({ mutationFn: async () => {
    const earliest = history[0]?.date
    if (!earliest) return { symbol, bars: [] as DailyBar[] }
    const end = dayjs(earliest).subtract(1, 'day'); const start = end.subtract(1, 'year').add(1, 'day')
    return api.barsRange(symbol, start.format('YYYY-MM-DD'), end.format('YYYY-MM-DD'))
  }, onSuccess: result => {
    if (result.symbol !== symbol) return
    setHistory(current => {
      const previousDates = new Set(current.map(bar => bar.date)); const added = result.bars.filter(bar => !previousDates.has(bar.date))
      if (added.length === 0) setHasEarlier(false)
      return [...added, ...current].sort((a, b) => a.date.localeCompare(b.date))
    })
  }, onError: error => message.error(`更早 K 线加载失败：${error.message}`) })
  useEffect(() => { setHistory(bars.data?.bars ?? []); setHasEarlier(true) }, [symbol, bars.data])
  const refreshTags = () => Promise.all([client.invalidateQueries({ queryKey: ['tags', symbol] }), client.invalidateQueries({ queryKey: ['watchlist'] }), client.invalidateQueries({ queryKey: ['tag-catalog'] })])
  const addTag = (name: string) => mutate.mutate(() => api.addTag(symbol, name).then(refreshTags))
  const watched = watchlist.data?.find(item => item.symbol === symbol)
  return <div className="stack-lg">
    <QuoteCard symbol={symbol} />
    <Card size="small"><div className="detail-actions">
      <Space wrap><Typography.Text strong>个股标签</Typography.Text>{tags.data?.map(tag => <Tag key={tag.id} closable onClose={e => { e.preventDefault(); mutate.mutate(() => api.deleteTag(symbol, tag.id).then(refreshTags)) }}>{tag.name}</Tag>)}
        <TagPicker catalog={catalog.data ?? []} excludedIds={(tags.data ?? []).map(tag => tag.id)} onAdd={addTag} loading={mutate.isPending} /></Space>
      <Button icon={<StarOutlined />} danger={Boolean(watched)} loading={watchlist.isLoading || mutate.isPending} onClick={() => mutate.mutate(() => (watched ? api.deleteWatch(watched.id) : api.addWatch(symbol)).then(() => client.invalidateQueries({ queryKey: ['watchlist'] })))}>{watched ? '移出自选' : '加入自选'}</Button>
    </div></Card>
    {bars.error && <Alert type="error" showIcon message="K 线获取失败" description={(bars.error as Error).message} />}
    {history.length > 0 && <KlineChart key={symbol} bars={history} hasEarlier={hasEarlier} isLoadingEarlier={earlier.isPending} onLoadEarlier={() => { if (hasEarlier && !earlier.isPending) earlier.mutate() }} />}
    {bars.data && bars.data.bars.length === 0 && <Card><Empty description="行情源没有返回日 K 数据" /></Card>}
  </div>
}
