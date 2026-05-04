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
  pre_close?: number;
  change_amount?: number;
  change_pct?: number;
  volume: number;
  turnover_amount_billion?: number;
  turnover_rate?: number;
  is_up_limit?: boolean;
  is_down_limit?: boolean;
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
  has_more_before?: boolean;
}

export interface StockBarsRangeResponse {
  stock_code: string;
  months: number;
  end_date?: string | null;
  has_more_before: boolean;
  daily_bars: DailyBar[];
  indicators: StockIndicatorSeries;
}

// ---------------------------------------------------------------------------
// Data Initialization (legacy types kept for backward compatibility)
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
// V2 Init types
// ---------------------------------------------------------------------------

export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'TERMINATED';

export interface TaskResponse {
  task_id: string;
  mode: string;
  start_date: string;
  end_date: string;
  status: TaskStatus;
  total_days: number;
  processed_days: number;
  current_date: string;
  error_message: string;
  created_at: string;
  started_at: string;
  finished_at: string;
  progress_percent: number;
}

export type DayStatus =
  | 'PENDING'
  | 'FETCHING'
  | 'WRITING'
  | 'SUCCESS'
  | 'FAILED';

export interface TaskDayItem {
  task_id: string;
  trade_date: string;
  status: DayStatus;
  row_count: number;
  started_at: string;
  finished_at: string;
  error_message: string;
}

export interface TaskDaysResponse {
  task_id: string;
  total: number;
  page: number;
  per_page: number;
  days: TaskDayItem[];
}

export interface DataRangeInfo {
  min_trade_date: string | null;
  max_trade_date: string | null;
  trading_day_count: number;
}

export interface InitV2OverviewResponse {
  running_task: TaskResponse | null;
  latest_task: TaskResponse | null;
  data_range: DataRangeInfo;
  token_configured: boolean;
  stock_list_uploaded: boolean;
  stock_list_updated_at: string | null;
  daily_quote_cutoff_time: string | null;
  board_counts: Record<string, number>;
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

export function getStockBarsRange(
    stockCode: string,
    months: number,
    endDate?: string,
): Promise<StockBarsRangeResponse> {
  const query = new URLSearchParams({months: String(months)});
  if (endDate) query.set('end_date', endDate);
  return fetchJson<StockBarsRangeResponse>(
      `/api/market/stocks/${encodeURIComponent(stockCode)}/bars?${query.toString()}`,
  );
}

export function getInitStatus(): Promise<InitStatusResponse> {
  return fetchJson<InitStatusResponse>('/api/data-init/status');
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
// V2 Init API functions
// ---------------------------------------------------------------------------

export function createInitTask(
  startDate: string,
  endDate: string,
  mode: string = 'RANGE',
): Promise<TaskResponse> {
  return postJson<TaskResponse>('/api/data-init/tasks', {
    start_date: startDate,
    end_date: endDate,
    mode,
  });
}

export function getInitTask(taskId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/api/data-init/tasks/${taskId}`);
}

export function getInitTaskDays(
  taskId: string,
  page: number = 1,
  perPage: number = 50,
): Promise<TaskDaysResponse> {
  return fetchJson<TaskDaysResponse>(
    `/api/data-init/tasks/${taskId}/days?page=${page}&per_page=${perPage}`,
  );
}

export function reimportDay(tradeDate: string): Promise<TaskResponse> {
  return postJson<TaskResponse>('/api/data-init/reimport-day', { trade_date: tradeDate });
}

export function retryInitTask(taskId: string): Promise<TaskResponse> {
  return postJson<TaskResponse>(`/api/data-init/tasks/${taskId}/retry`);
}

export function terminateInitTask(taskId: string): Promise<TaskResponse> {
  return postJson<TaskResponse>(`/api/data-init/tasks/${taskId}/terminate`);
}

export function getInitV2Overview(): Promise<InitV2OverviewResponse> {
  return fetchJson<InitV2OverviewResponse>('/api/data-init/init/overview');
}

// ---------------------------------------------------------------------------
// Phase 2.10: Stock resolve + Init overview (legacy)
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
  market_data_start_date: string | null;
  market_data_end_date: string | null;
  market_data_trading_day_count: number;
  board_counts: Record<string, number>;
}

export function resolveStockInput(query: string): Promise<StockResolveResponse> {
  return fetchJson<StockResolveResponse>(`/api/market/resolve?q=${encodeURIComponent(query)}`);
}

export function searchStocks(query: string, limit = 10): Promise<StockCandidate[]> {
  return fetchJson<StockCandidate[]>(
    `/api/market/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
}

export function getInitOverview(): Promise<InitOverviewResponse> {
  return fetchJson<InitOverviewResponse>('/api/data-init/overview');
}
