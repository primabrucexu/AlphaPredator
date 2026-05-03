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
  turnover_amount_billion?: number;
  turnover_rate?: number;
}

export interface StockKeyIndicators {
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  avg_volume_5d: number | null;
}

export interface StockTags {
  industry: string[];
  concepts: string[];
  region: string[];
}

export interface StockIndicatorSeries {
  ma5: (number | null)[];
  ma10: (number | null)[];
  ma20: (number | null)[];
  ma60: (number | null)[];
  volume_ma5: (number | null)[];
  volume_ma10: (number | null)[];
  volume_ma20: (number | null)[];
  kdj_k: (number | null)[];
  kdj_d: (number | null)[];
  kdj_j: (number | null)[];
  macd_dif: (number | null)[];
  macd_dea: (number | null)[];
  macd_hist: (number | null)[];
  rsi6: (number | null)[];
  rsi12: (number | null)[];
  rsi24: (number | null)[];
}

export interface StockDetailResponse {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  current_price: number;
  change_amount: number;
  change_pct: number;
  open_price: number;
  prev_close: number;
  high_price: number;
  low_price: number;
  turnover_amount_billion: number;
  turnover_rate: number;
  sectors: string[];
  tags: StockTags;
  ai_quick_summary: string;
  key_indicators: StockKeyIndicators;
  daily_bars: DailyBar[];
  indicators: StockIndicatorSeries;
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
  start_trade_date: string;
  end_trade_date: string;
  processed_trade_dates: string[];
}

export interface TokenConfigResponse {
  is_configured: boolean;
}

export interface StockListUploadResponse {
  total_stocks: number;
  active_stocks: number;
  boards: Record<string, number>;
}

export type MarketBoard = '主板' | '创业板' | '科创板' | '北交所';
export const ALL_MARKET_BOARDS: MarketBoard[] = ['主板', '创业板', '科创板', '北交所'];

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

export function startInit(
  historyDays: number = 60,
  marketFilters: MarketBoard[] = ALL_MARKET_BOARDS,
): Promise<InitStatusResponse> {
  return postJson<InitStatusResponse>('/api/data-init/start', {
    history_days: historyDays,
    market_filters: marketFilters,
  });
}

export function triggerDailyUpdate(): Promise<UpdateResult> {
  return postJson<UpdateResult>('/api/data-init/update');
}

export function getTokenConfig(): Promise<TokenConfigResponse> {
  return fetchJson<TokenConfigResponse>('/api/data-init/token');
}

export function saveTokenConfig(token: string): Promise<TokenConfigResponse> {
  return postJson<TokenConfigResponse>('/api/data-init/token', { token });
}

export async function uploadStockList(file: File): Promise<StockListUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE_URL}/api/data-init/upload-stock-list`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const responseText = await response.text();
    throw new Error(responseText || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<StockListUploadResponse>;
}

// ---------------------------------------------------------------------------
// Phase 2.10: Stock resolve + Init overview
// ---------------------------------------------------------------------------

export interface StockCandidate {
  stock_code: string;
  stock_name: string;
}

export interface StockResolveResponse {
  status: 'ok' | 'not_found' | 'ambiguous';
  stock_code?: string;
  stock_name?: string;
  match_type?: 'code' | 'cnspell' | 'cnspell_prefix';
  message?: string;
  candidates?: StockCandidate[];
}

export interface InitOverviewResponse {
  init_completed: boolean;
  token_configured: boolean;
  stock_list_uploaded: boolean;
  stock_list_updated_at: string | null;
  daily_quote_cutoff_time: string | null;
  board_counts: Record<string, number>;
}

export function resolveStockInput(query: string): Promise<StockResolveResponse> {
  return fetchJson<StockResolveResponse>(`/api/market/resolve?q=${encodeURIComponent(query)}`);
}

export function getInitOverview(): Promise<InitOverviewResponse> {
  return fetchJson<InitOverviewResponse>('/api/data-init/overview');
}
