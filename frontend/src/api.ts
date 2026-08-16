import type { DailyBar, JygsStatus, LimitUpRecord, Quote, StockSummary, Tag, WatchGroup } from './types'

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
  groups: () => request<WatchGroup[]>('/api/watchlist/groups'),
  createGroup: (name: string) => request<WatchGroup>('/api/watchlist/groups', { method: 'POST', body: JSON.stringify({ name }) }),
  renameGroup: (id: number, name: string) => request(`/api/watchlist/groups/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deleteGroup: (id: number) => request(`/api/watchlist/groups/${id}`, { method: 'DELETE' }),
  addWatch: (groupId: number, symbol: string) => request(`/api/watchlist/groups/${groupId}/items`, { method: 'POST', body: JSON.stringify({ symbol }) }),
  moveWatch: (itemId: number, groupId: number) => request(`/api/watchlist/items/${itemId}`, { method: 'PUT', body: JSON.stringify({ group_id: groupId }) }),
  deleteWatch: (itemId: number) => request(`/api/watchlist/items/${itemId}`, { method: 'DELETE' }),
  tags: (symbol: string) => request<Tag[]>(`/api/stocks/${encodeURIComponent(symbol)}/tags`),
  addTag: (symbol: string, name: string) => request<Tag>(`/api/stocks/${encodeURIComponent(symbol)}/tags`, { method: 'POST', body: JSON.stringify({ name }) }),
  deleteTag: (symbol: string, id: number) => request(`/api/stocks/${encodeURIComponent(symbol)}/tags/${id}`, { method: 'DELETE' }),
  limitUps: (symbol: string) => request<LimitUpRecord[]>(`/api/stocks/${encodeURIComponent(symbol)}/limit-up-history?limit=10`),
  jygsStatus: () => request<JygsStatus>('/api/jygs/status'),
  saveJygsSession: (session: string) => request('/api/jygs/session', { method: 'PUT', body: JSON.stringify({ session }) }),
  checkJygs: () => request<{ is_valid: boolean; last_error: string }>('/api/jygs/check', { method: 'POST' }),
  syncJygs: (start_date: string, end_date: string) => request<{ days: number; records: number }>('/api/jygs/sync', { method: 'POST', body: JSON.stringify({ start_date, end_date }) }),
}
