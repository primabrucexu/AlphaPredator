import type { DailyBar, GlobalTag, JygsStatus, LimitUpRecord, Quote, StockSummary, Tag, WatchItem } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } })
  if (!response.ok) {
    let message = `请求失败 (${response.status})`
    try { message = (await response.json()).detail || message } catch { /* no JSON body */ }
    throw new Error(message)
  }
  return response.status === 204 ? undefined as T : response.json()
}

export const api = {
  searchStocks: (q: string) => request<StockSummary[]>(`/api/stocks/search?q=${encodeURIComponent(q)}`),
  syncStocks: () => request<{ count: number }>('/api/stocks/sync-directory', { method: 'POST' }),
  quote: (symbol: string) => request<Quote>(`/api/market/stocks/${encodeURIComponent(symbol)}/quote`),
  bars: (symbol: string) => request<{ symbol: string; bars: DailyBar[] }>(`/api/market/stocks/${encodeURIComponent(symbol)}/daily-bars?count=250`),
  barsRange: (symbol: string, startDate: string, endDate: string) => request<{ symbol: string; bars: DailyBar[] }>(`/api/market/stocks/${encodeURIComponent(symbol)}/daily-bars?start_date=${startDate}&end_date=${endDate}`),
  watchlist: () => request<WatchItem[]>('/api/watchlist/items'),
  addWatch: (symbol: string) => request<WatchItem>('/api/watchlist/items', { method: 'POST', body: JSON.stringify({ symbol }) }),
  deleteWatch: (itemId: number) => request(`/api/watchlist/items/${itemId}`, { method: 'DELETE' }),
  tags: (symbol: string) => request<Tag[]>(`/api/stocks/${encodeURIComponent(symbol)}/tags`),
  addTag: (symbol: string, name: string) => request<Tag>(`/api/stocks/${encodeURIComponent(symbol)}/tags`, { method: 'POST', body: JSON.stringify({ name }) }),
  deleteTag: (symbol: string, id: number) => request(`/api/stocks/${encodeURIComponent(symbol)}/tags/${id}`, { method: 'DELETE' }),
  tagCatalog: () => request<GlobalTag[]>('/api/tags'),
  createTag: (name: string) => request<Tag>('/api/tags', { method: 'POST', body: JSON.stringify({ name }) }),
  renameTag: (id: number, name: string) => request<Tag>(`/api/tags/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deleteGlobalTag: (id: number) => request(`/api/tags/${id}`, { method: 'DELETE' }),
  reorderTags: (tagIds: number[]) => request<{ tag_ids: number[] }>('/api/tags/order', { method: 'PUT', body: JSON.stringify({ tag_ids: tagIds }) }),
  reorderTagStocks: (tagId: number, symbols: string[]) => request<{ symbols: string[] }>(`/api/tags/${tagId}/stocks/order`, { method: 'PUT', body: JSON.stringify({ symbols }) }),
  limitUps: (symbol: string) => request<LimitUpRecord[]>(`/api/stocks/${encodeURIComponent(symbol)}/limit-up-history?limit=10`),
  jygsStatus: () => request<JygsStatus>('/api/jygs/status'),
  loginJygs: () => request<{ is_valid: boolean }>('/api/jygs/login', { method: 'POST', body: JSON.stringify({ timeout_seconds: 300 }) }),
  syncJygs: (start_date: string, end_date: string) => request<{ days: number; records: number }>('/api/jygs/sync', { method: 'POST', body: JSON.stringify({ start_date, end_date }) }),
}
