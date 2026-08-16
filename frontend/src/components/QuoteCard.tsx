import { useQuery } from '@tanstack/react-query'
import { Alert, Card, Statistic, Typography } from 'antd'
import { api } from '../api'

const fmt = (value: number | null, digits = 2) => value == null ? '--' : value.toLocaleString('zh-CN', { maximumFractionDigits: digits })

export default function QuoteCard({ symbol }: { symbol: string }) {
  const quote = useQuery({ queryKey: ['quote', symbol], queryFn: () => api.quote(symbol), refetchInterval: 5000 })
  if (quote.error) return <Alert type="error" showIcon message="最新行情获取失败" description={(quote.error as Error).message} />
  const data = quote.data
  const up = (data?.change || 0) >= 0
  return <Card loading={quote.isLoading} className="quote-card">
    <div className="quote-main">
      <div><Typography.Title level={2}>{data?.name || symbol}</Typography.Title><Typography.Text type="secondary">{symbol}</Typography.Text></div>
      <Statistic value={data?.price ?? '--'} precision={2} valueStyle={{ color: up ? '#ef4444' : '#22c55e', fontSize: 38 }}
        suffix={<small className={up ? 'up' : 'down'}>{data ? `${fmt(data.change)}  ${fmt(data.change_percent)}%` : ''}</small>} />
    </div>
    <div className="quote-grid">
      <span>今开 <b>{fmt(data?.open ?? null)}</b></span><span>最高 <b>{fmt(data?.high ?? null)}</b></span>
      <span>最低 <b>{fmt(data?.low ?? null)}</b></span><span>昨收 <b>{fmt(data?.previous_close ?? null)}</b></span>
      <span>成交量 <b>{fmt(data?.volume ?? null, 0)}</b></span><span>成交额 <b>{fmt(data?.amount ?? null, 0)}</b></span>
    </div>
  </Card>
}
