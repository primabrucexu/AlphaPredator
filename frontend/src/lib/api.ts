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

export interface MairuiLicenceConfigResponse {
    configured: boolean;
    masked_licence: string | null;
    source: 'env' | 'file' | 'none';
}

export type MarketBoard = '主板' | '创业板' | '科创板' | '北交所';
export const ALL_MARKET_BOARDS: MarketBoard[] = ['主板', '创业板', '科创板', '北交所'];

// ---------------------------------------------------------------------------
// V2 Init types
// ---------------------------------------------------------------------------

export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'TERMINATED';

export type TaskType = 'STOCK_LIST_SYNC' | 'MARKET_DATA' | 'JYGS_REVIEW';

export interface TaskResponse {
  task_id: string;
  task_type: TaskType;
  start_date: string;
  end_date: string;
  status: TaskStatus;
    total_items: number;
    processed_items: number;
    current_label: string;
  error_message: string;
    task_start_date: string;
    task_end_date: string;
  progress_percent: number;
}

export type DayStatus =
  | 'PENDING'
  | 'FETCHING'
  | 'WRITING'
  | 'SUCCESS'
  | 'FAILED';

export interface TaskItemsResponse {
  task_id: string;
    task_type: TaskType;
    label_type: 'stock' | 'date' | 'sync';
    label_name: string;
    total_items: number;
    processed_items: number;
    current_label: string;
    status: TaskStatus;
  error_message: string;
    progress_percent: number;
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
    market_data_configured: boolean;
  daily_quote_cutoff_time: string | null;
  board_counts: Record<string, number>;
}

export interface HotSectorHistorySector {
  name: string;
  heat_score: number;
  trend_tag?: string;
  trend_label?: string;
  rank_today?: number;
  max_board_count?: number;
}

export interface HotSectorHistoryDay {
  trade_date: string;
  sectors: HotSectorHistorySector[];
}

export interface HotSectorHistoryResponse {
  trade_dates: string[];
  days: HotSectorHistoryDay[];
}

export interface LimitUpStreakItem {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  board_count: number;
  limit_up_time: string;
  hot_theme: string;
}

export interface LimitUpStreaksResponse {
  trade_date: string;
  streaks: LimitUpStreakItem[];
}

export interface HotReviewImageItem {
    url: string;
    source_file: string;
}

export interface HotReviewImagesResponse {
    trade_date: string;
    images: HotReviewImageItem[];
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

export function getMairuiLicenceConfig(): Promise<MairuiLicenceConfigResponse> {
    return fetchJson<MairuiLicenceConfigResponse>('/api/data-init/licence');
}

export function saveMairuiLicence(licence: string): Promise<MairuiLicenceConfigResponse> {
    return postJson<MairuiLicenceConfigResponse>('/api/data-init/licence', {licence});
}


// ---------------------------------------------------------------------------
// V2 Init API functions
// ---------------------------------------------------------------------------

export function createInitTask(
  startDate: string,
  endDate: string,
  mode: string = 'FULL_SYNC',
  taskType: TaskType = 'MARKET_DATA',
): Promise<TaskResponse> {
  return postJson<TaskResponse>('/api/data-init/tasks', {
    start_date: startDate,
    end_date: endDate,
    mode,
    task_type: taskType,
  });
}

export function getInitTask(taskId: string): Promise<TaskResponse> {
  return fetchJson<TaskResponse>(`/api/data-init/tasks/${taskId}`);
}

export function getTaskItems(taskId: string): Promise<TaskItemsResponse> {
    return fetchJson<TaskItemsResponse>(`/api/data-init/tasks/${taskId}/items`);
}

export function reimportDay(tradeDate: string): Promise<TaskResponse> {
  return postJson<TaskResponse>('/api/data-init/reimport-day', { trade_date: tradeDate });
}

export function retryInitTask(taskId: string): Promise<TaskResponse> {
  return postJson<TaskResponse>(`/api/data-init/tasks/${taskId}/retry`);
}

export function retryInitSubtask(taskId: string, itemLabel: string): Promise<TaskResponse> {
    return postJson<TaskResponse>(`/api/data-init/tasks/${taskId}/retry-item`, {item_label: itemLabel});
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
    market_data_configured: boolean;
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

// ---------------------------------------------------------------------------
// 韭研公社鉴权
// ---------------------------------------------------------------------------

export interface JygsAuthStatus {
  configured: boolean;
  valid: boolean;
  saved_at: string | null;
  expires_at: string | null;
}

export function getJygsAuthStatus(): Promise<JygsAuthStatus> {
  return fetchJson<JygsAuthStatus>('/api/jygs/auth/status');
}

export async function saveJygsSession(session: string): Promise<void> {
  const resp = await fetch(`${API_BASE_URL}/api/jygs/auth/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session }),
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.error ?? '保存失败');
  }
}

export async function loginJygsWithPlaywright(timeoutSeconds = 300): Promise<void> {
    const resp = await fetch(`${API_BASE_URL}/api/jygs/auth/login/playwright`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({timeout_seconds: timeoutSeconds}),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.ok === false) {
        throw new Error(data.error ?? 'Playwright 登录失败');
    }
}

export async function clearJygsSession(): Promise<void> {
  await fetch(`${API_BASE_URL}/api/jygs/auth/session`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Sentiment API functions
// ---------------------------------------------------------------------------

export function getHotSectorHistory(days: number = 7): Promise<HotSectorHistoryResponse> {
  return fetchJson<HotSectorHistoryResponse>(
    `/api/market/hot-sector-history?days=${days}`,
  );
}

export function getLimitUpStreaks(
  tradeDate?: string,
  minBoards: number = 2,
): Promise<LimitUpStreaksResponse> {
  const query = new URLSearchParams({ min_boards: String(minBoards) });
  if (tradeDate) query.set('trade_date', tradeDate);
  return fetchJson<LimitUpStreaksResponse>(
    `/api/market/limit-up-streaks?${query.toString()}`,
  );
}

export function getHotReviewImages(tradeDate?: string): Promise<HotReviewImagesResponse> {
    const query = new URLSearchParams();
    if (tradeDate) query.set('trade_date', tradeDate);
    const suffix = query.toString();
    return fetchJson<HotReviewImagesResponse>(
        `/api/market/hot-review-images${suffix ? `?${suffix}` : ''}`,
    );
}

