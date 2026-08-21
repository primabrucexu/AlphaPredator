export interface StockSummary { symbol: string; code: string; name: string }
export interface Quote {
  symbol: string; name: string; price: number | null; change: number | null; change_percent: number | null
  previous_close: number | null; open: number | null; high: number | null; low: number | null
  volume: number | null; amount: number | null; volume_ratio: number | null; turnover_rate: number | null
  pe_ttm: number | null; total_market_cap: number | null; float_market_cap: number | null; timestamp: string | null
}
export interface DailyBar {
  date: string; open: number; high: number; low: number; close: number; volume: number; amount: number
  previous_close: number | null; is_limit_up: boolean; is_limit_down: boolean
}
export interface Tag { id: number; name: string; sort_order: number; stock_sort_order?: number }
export interface GlobalTag extends Tag { stock_count: number }
export interface WatchItem { id: number; symbol: string; code: string; name: string; tags: Tag[] }
export interface LimitUpRecord { trade_date: string; limit_up_time: string; streak_text: string; hot_theme: string; reason: string }
export interface JygsStatus {
  is_configured: boolean; is_valid: boolean; updated_at: string | null; last_checked_at: string | null; last_error: string
}
