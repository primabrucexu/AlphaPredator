export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export interface MarketSummary {
  trade_date: string;
  rising_count: number;
  falling_count: number;
  turnover_amount_billion: number;
}

export interface HotSectorItem {
  trade_date: string;
  name: string;
  trend_label: string;
  heat_score: number;
}

export interface MarketListRow {
  stock_code: string;
  stock_name: string;
  current_price: number;
  change_amount: number;
  change_pct: number;
  turnover_amount_billion: number;
  turnover_rate: number;
}

export interface MarketOverviewResponse {
  summary: MarketSummary;
  hot_sectors: HotSectorItem[];
  stocks: MarketListRow[];
}

export interface DailyBar {
  trade_date: string;
  open_price: number;
  high_price: number;
  low_price: number;
  close_price: number;
  volume: number;
}

export interface StockKeyIndicators {
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  avg_volume_5d: number | null;
}

export interface StockDetailResponse {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  current_price: number;
  change_amount: number;
  change_pct: number;
  turnover_amount_billion: number;
  turnover_rate: number;
  sectors: string[];
  ai_quick_summary: string;
  key_indicators: StockKeyIndicators;
  daily_bars: DailyBar[];
}

// ---------------------------------------------------------------------------
// Phase 2.9: Data Initialization
// ---------------------------------------------------------------------------

export type InitStatus = 'idle' | 'running' | 'done' | 'error';

export interface InitStatusResponse {
  status: InitStatus;
  trade_date: string;
  total_stocks: number;
  processed_stocks: number;
  started_at: string;
  finished_at: string;
  error_message: string;
}

export interface UpdateResult {
  trade_date: string;
  stock_count: number;
  bar_count: number;
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    const responseText = await response.text();
    throw new Error(responseText || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const responseText = await response.text();
    throw new Error(responseText || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getMarketOverview(): Promise<MarketOverviewResponse> {
  return fetchJson<MarketOverviewResponse>('/api/market/overview');
}

export function getStockDetail(stockCode: string): Promise<StockDetailResponse> {
  return fetchJson<StockDetailResponse>(`/api/market/stocks/${encodeURIComponent(stockCode)}`);
}

export function getInitStatus(): Promise<InitStatusResponse> {
  return fetchJson<InitStatusResponse>('/api/data-init/status');
}

export function startInit(historyDays: number = 60): Promise<InitStatusResponse> {
  return postJson<InitStatusResponse>('/api/data-init/start', { history_days: historyDays });
}

export function triggerDailyUpdate(): Promise<UpdateResult> {
  return postJson<UpdateResult>('/api/data-init/update');
}

