import { useQuery } from '@tanstack/react-query'
import { Alert, Card, Typography } from 'antd'
import { api } from '../api'

const fmt = (value: number | null, digits = 2) => value == null ? '--' : value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
const fmtYi = (value: number | null) => value == null ? '--' : `${fmt(value / 100_000_000)}亿`
const fmtVolume = (value: number | null) => value == null ? '--' : `${fmt(value / 1_000_000)}万手`

export default function QuoteCard({ symbol }: { symbol: string }) {
  const quote = useQuery({ queryKey: ['quote', symbol], queryFn: () => api.quote(symbol), refetchInterval: 5000 })
  if (quote.error) return <Alert type="error" showIcon message="最新行情获取失败" description={(quote.error as Error).message} />
  const data = quote.data
  const up = (data?.change || 0) >= 0
  return <Card loading={quote.isLoading} className="quote-card">
    <div className="quote-heading">
      <Typography.Title level={2}>{data?.name || symbol}</Typography.Title>
      <Typography.Text type="secondary">{data?.symbol || symbol}</Typography.Text>
    </div>
    <div className="quote-market">
      <div className={`quote-price ${up ? 'up' : 'down'}`}>
        <strong>{fmt(data?.price ?? null)}</strong>
        <span>{fmt(data?.change ?? null)}&nbsp;&nbsp;{fmt(data?.change_percent ?? null)}%</span>
      </div>
      <div className="quote-metrics">
        <div><span>高</span><b className={up ? 'up' : 'down'}>{fmt(data?.high ?? null)}</b></div>
        <div><span>低</span><b className={up ? 'up' : 'down'}>{fmt(data?.low ?? null)}</b></div>
        <div><span>开</span><b className={up ? 'up' : 'down'}>{fmt(data?.open ?? null)}</b></div>
      </div>
      <div className="quote-metrics quote-metrics-wide">
        <div><span>市值</span><b>{fmtYi(data?.total_market_cap ?? null)}</b></div>
        <div><span>流通</span><b>{fmtYi(data?.float_market_cap ?? null)}</b></div>
        <div><span>市盈 TTM</span><b>{fmt(data?.pe_ttm ?? null)}</b></div>
      </div>
      <div className="quote-metrics quote-metrics-wide">
        <div><span>量比</span><b className={up ? 'up' : 'down'}>{fmt(data?.volume_ratio ?? null)}</b></div>
        <div><span>换手</span><b>{fmt(data?.turnover_rate ?? null)}%</b></div>
        <div><span>成交额</span><b>{fmtYi(data?.amount ?? null)}</b></div>
      </div>
    </div>
    <div className="quote-summary">
      <span>昨收 <b>{fmt(data?.previous_close ?? null)}</b></span>
      <span>成交量 <b>{fmtVolume(data?.volume ?? null)}</b></span>
      <span>更新时间 <b>{data?.timestamp ? new Date(data.timestamp).toLocaleTimeString('zh-CN', { hour12: false }) : '--'}</b></span>
    </div>
  </Card>
}
