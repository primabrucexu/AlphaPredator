import type { DailyBar, GlobalTag, Page, Quote, StockSummary, Tag, Task, TaskItem, WatchItem } from './types'

export interface ApiErrorBody {
  detail?: string | { message?: string; existing_task_id?: number }
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public data: ApiErrorBody | null) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } })
  if (!response.ok) {
    let message = `请求失败 (${response.status})`
    let data: ApiErrorBody | null = null
    try {
      data = await response.json() as ApiErrorBody
      message = typeof data.detail === 'string' ? data.detail : data.detail?.message || message
    } catch { /* no JSON body */ }
    throw new ApiError(message, response.status, data)
  }
  return response.status === 204 ? undefined as T : response.json()
}

export const api = {
  searchStocks: (q: string) => request<StockSummary[]>(`/api/stocks/search?q=${encodeURIComponent(q)}`),
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
  createStockDirectoryTask: () => request<Task>('/api/tasks/stock-directory-refresh', { method: 'POST' }),
  createMarketDailyBarsTask: (mode: 'incremental' | 'full') => request<Task>('/api/tasks/market-daily-bars-update', { method: 'POST', body: JSON.stringify({ mode }) }),
  marketDailyBarsCoverage: () => request<{ start_date: string | null; end_date: string | null }>('/api/tasks/market-daily-bars-coverage'),
  tasks: (page = 1, pageSize = 20, status = '', taskType = '') => {
    const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (status) query.set('status', status)
    if (taskType) query.set('task_type', taskType)
    return request<Page<Task>>(`/api/tasks?${query}`)
  },
  task: (id: number) => request<Task>(`/api/tasks/${id}`),
  taskItems: (id: number, page = 1, pageSize = 50) => request<Page<TaskItem>>(`/api/tasks/${id}/items?page=${page}&page_size=${pageSize}`),
  cancelTask: (id: number) => request<Task>(`/api/tasks/${id}/cancel`, { method: 'POST' }),
  retryFailedMarketDailyBarsTask: (id: number) => request<Task>(`/api/tasks/${id}/retry-failed`, { method: 'POST' }),
  activeTaskCount: () => request<{ count: number }>('/api/tasks/active-count'),
}
