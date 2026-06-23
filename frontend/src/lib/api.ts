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
  expma8: (number | null)[];
  expma17: (number | null)[];
  expma21: (number | null)[];
  expma55: (number | null)[];
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
    source: 'file' | 'none';
    rate_limit_per_minute: number;
    fetch_concurrency: number;
}

export type MarketBoard = '主板' | '创业板' | '科创板' | '北交所';
export const ALL_MARKET_BOARDS: MarketBoard[] = ['主板', '创业板', '科创板', '北交所'];

// ---------------------------------------------------------------------------
// V2 Init types
// ---------------------------------------------------------------------------

export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'TERMINATED';

export type TaskType = 'STOCK_LIST_SYNC' | 'MARKET_DATA' | 'MARKET_DATA_5M' | 'JYGS_REVIEW' | 'MACD_ALERT_SCAN';

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
  latest_market_data_task: TaskResponse | null;
  data_range: DataRangeInfo;
    market_data_configured: boolean;
  daily_quote_cutoff_time: string | null;
  board_counts: Record<string, number>;
}

export interface BatchTaskResponse {
  stock_list_task: TaskResponse;
  market_data_task: TaskResponse;
  jygs_review_task: TaskResponse;
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

export interface HotReviewTableRow {
  trade_date: string;
  stock_code: string;
  stock_name: string;
  limit_up_time: string;
  streak_text: string;
  hot_theme: string;
  reason: string;
  short_reason: string;
}

export interface HotReviewTableResponse {
  trade_date: string;
  rows: HotReviewTableRow[];
}

export interface HotSectorAggregatedItem {
  name: string;
  counts: Record<string, number>;
}

export interface HotSectorAggregatedResponse {
  windows: number[];
  sectors: HotSectorAggregatedItem[];
}

export interface StockLimitUpHistoryRow {
  trade_date: string;
  limit_up_time: string;
  streak_text: string;
  hot_theme: string;
  reason: string;
  short_reason: string;
}

export interface StockLimitUpHistoryResponse {
  stock_code: string;
  rows: StockLimitUpHistoryRow[];
}

export type StockLinkageASelectMode = 'manual_single' | 'hot_limit_top';

export interface StockLinkageBacktestCreateRequest {
  a_select_mode: StockLinkageASelectMode;
  manual_a_full_code?: string | null;
  hot_top_n?: number | null;
  start_date: string;
  end_date: string;
  min_sample_count: number;
  job_name?: string | null;
}

export interface StockLinkageBacktestSummaryResponse {
  job_id: string;
  status: string;
  trigger_event_count: number;
  baseline_count: number;
  result_count: number;
}

export interface StockLinkageBacktestJobResponse {
  job_id: string;
  job_name: string | null;
  a_select_mode: StockLinkageASelectMode;
  manual_a_full_code: string | null;
  hot_top_n: number | null;
  start_date: string;
  end_date: string;
  min_sample_count: number;
  status: 'pending' | 'running' | 'success' | 'failed';
  error_message: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface StockLinkageBacktestResultRow {
  job_id: string;
  a_full_code: string;
  b_full_code: string;
  trigger_type: string;
  trigger_threshold: number;
  observation_type: string;
  target_threshold: number;
  sample_count: number;
  hit_count: number;
  condition_probability: number;
  baseline_probability: number;
  probability_lift: number;
  lift_multiple: number | null;
  trigger_coverage_rate: number;
  confidence_level: string;
  score: number;
}

export interface MacdAlertScanRequest {
  trade_date: string;
  universe_scope?: 'market';
  markets?: string[];
  exclude_st?: boolean;
  green_shrink_days?: number;
}

export interface MacdAlertResultRow {
  id: string;
  trade_date: string;
  stock_code: string;
  stock_name: string;
  pattern_key: string;
  pattern_name: string;
  cross_zone: 'underwater' | 'above_zero' | 'mixed';
  close_price: number;
  next_cross_trigger_price: number;
  cross_trigger_distance_pct: number;
  next_limit_up_price: number | null;
  cross_trigger_reachable: number | boolean;
  cross_trigger_unreachable_reason: string | null;
  next_trend_keep_price: number;
  trend_keep_distance_pct: number;
  macd_dif: number;
  macd_dea: number;
  macd_hist: number;
  green_shrink_days: number;
  last_limit_up_date: string | null;
  last_limit_up_theme: string | null;
  last_limit_up_days_ago: number | null;
  theme_recent_limit_up_count: number;
  theme_recent_rank: number | null;
  theme_heat_level: string;
  track_status: string;
  tracked_close_price: number | null;
  backtest_sample_count: number;
  backtest_cross_success_rate: number | null;
  backtest_win_rate: number | null;
  backtest_avg_return_pct: number | null;
  backtest_confidence_level: string;
  score: number;
  summary: string;
}

export interface MacdAlertScanResponse {
  trade_date: string;
  total_scanned: number;
  matched_count: number;
  report_generatable: boolean;
  report_generation_hint: string;
  results: MacdAlertResultRow[];
}

export interface MacdAlertTrackResponse {
  trade_date: string;
  source_trade_date: string;
  tracked_count: number;
  cross_confirmed_count: number;
  trend_kept_count: number;
  trend_weakened_count: number;
  data_missing_count: number;
  report_generatable: boolean;
  report_generation_hint: string;
  results: Record<string, unknown>[];
}

export interface MacdAlertBacktestSampleRow {
  id: string;
  alert_result_id: string;
  stock_code: string;
  stock_name: string;
  alert_date: string;
  alert_close_price: number;
  t1_track_status: string | null;
  cross_date: string | null;
  cross_type: string | null;
  sell_date: string | null;
  sell_reason: string | null;
  return_pct: number | null;
  holding_days: number | null;
  status: string;
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

export function saveMairuiLicence(
    licence: string,
    rateLimitPerMinute: number,
): Promise<MairuiLicenceConfigResponse> {
    return postJson<MairuiLicenceConfigResponse>('/api/data-init/licence', {
        licence,
        rate_limit_per_minute: rateLimitPerMinute,
    });
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

export function getLatestInitTaskByType(taskType: TaskType): Promise<TaskResponse | null> {
  return fetchJson<TaskResponse | null>(`/api/data-init/tasks/latest?task_type=${encodeURIComponent(taskType)}`);
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

export function createBatchInitTasks(startDate: string, endDate: string): Promise<BatchTaskResponse> {
  return postJson<BatchTaskResponse>('/api/data-init/tasks/batch', {
    start_date: startDate,
    end_date: endDate,
  });
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
  market_data_last_sync_start_date: string | null;
  market_data_last_sync_end_date: string | null;
  market_data_last_sync_finished_at: string | null;
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

export function getHotSectorHistory(days: number = 7, excludeSt: boolean = true): Promise<HotSectorHistoryResponse> {
  const params = new URLSearchParams({ days: String(days), exclude_st: String(excludeSt) });
  return fetchJson<HotSectorHistoryResponse>(`/api/market/hot-sector-history?${params.toString()}`);
}

export function getLimitUpStreaks(
  tradeDate?: string,
  minBoards: number = 2,
  excludeSt: boolean = true,
): Promise<LimitUpStreaksResponse> {
  const query = new URLSearchParams({ min_boards: String(minBoards) });
  if (tradeDate) query.set('trade_date', tradeDate);
  query.set('exclude_st', String(excludeSt));
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

export function getHotReviewTable(
  tradeDate?: string,
  excludeSt: boolean = true,
): Promise<HotReviewTableResponse> {
  const query = new URLSearchParams({ exclude_st: String(excludeSt) });
  if (tradeDate) query.set('trade_date', tradeDate);
  return fetchJson<HotReviewTableResponse>(`/api/market/hot-review-table?${query.toString()}`);
}

export function getHotSectorAggregated(
  excludeSt: boolean = true,
): Promise<HotSectorAggregatedResponse> {
  const query = new URLSearchParams({ exclude_st: String(excludeSt) });
  return fetchJson<HotSectorAggregatedResponse>(`/api/market/hot-sector-aggregated?${query.toString()}`);
}

export function getStockLimitUpHistory(
  stockCode: string,
  limit: number = 20,
): Promise<StockLimitUpHistoryResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  return fetchJson<StockLimitUpHistoryResponse>(
    `/api/market/stocks/${encodeURIComponent(stockCode)}/limit-up-history?${query.toString()}`,
  );
}

export function createStockLinkageBacktest(
  request: StockLinkageBacktestCreateRequest,
): Promise<StockLinkageBacktestJobResponse> {
  return postJson<StockLinkageBacktestJobResponse>('/api/stock-linkage/backtests', request);
}

export function getStockLinkageBacktest(jobId: string): Promise<StockLinkageBacktestJobResponse> {
  return fetchJson<StockLinkageBacktestJobResponse>(
    `/api/stock-linkage/backtests/${encodeURIComponent(jobId)}`,
  );
}

export function listStockLinkageBacktests(limit: number = 20): Promise<StockLinkageBacktestJobResponse[]> {
  return fetchJson<StockLinkageBacktestJobResponse[]>(`/api/stock-linkage/backtests?limit=${limit}`);
}

export function getStockLinkageBacktestResults(
  jobId: string,
  limit: number = 100,
): Promise<StockLinkageBacktestResultRow[]> {
  return fetchJson<StockLinkageBacktestResultRow[]>(
    `/api/stock-linkage/backtests/${encodeURIComponent(jobId)}/results?limit=${limit}`,
  );
}

export function scanMacdAlerts(request: MacdAlertScanRequest): Promise<TaskResponse> {
  return postJson<TaskResponse>('/api/macd-alerts/scan', request);
}

export function trackMacdAlerts(tradeDate: string, sourceTradeDate: string): Promise<MacdAlertTrackResponse> {
  return postJson<MacdAlertTrackResponse>('/api/macd-alerts/track', {
    trade_date: tradeDate,
    source_trade_date: sourceTradeDate,
  });
}

export function listMacdAlertResults(params: {
  trade_date: string;
  cross_zone?: string;
  limit?: number;
  offset?: number;
}): Promise<MacdAlertResultRow[]> {
  const query = new URLSearchParams({
    trade_date: params.trade_date,
    limit: String(params.limit ?? 100),
    offset: String(params.offset ?? 0),
  });
  if (params.cross_zone) query.set('cross_zone', params.cross_zone);
  return fetchJson<MacdAlertResultRow[]>(`/api/macd-alerts/results?${query.toString()}`);
}

export function listMacdAlertBacktestSamples(
  alertId: string,
  limit: number = 50,
): Promise<MacdAlertBacktestSampleRow[]> {
  return fetchJson<MacdAlertBacktestSampleRow[]>(
    `/api/macd-alerts/results/${encodeURIComponent(alertId)}/backtest-samples?limit=${limit}`,
  );
}

// ---------------------------------------------------------------------------
// 交易复盘系统 Trade Review
// ---------------------------------------------------------------------------

export interface OperationItem {
  id?: string;
  review_id?: string;
  trade_time: string;
  operation_type: string; // buy/sell/add/reduce/t_buy/t_sell
  price: number;
  quantity: number;
  amount: number;
  source: string; // ocr/manual/import
  note: string;
  sort_index?: number;
}

export interface DecisionNoteItem {
  id?: string;
  review_id?: string;
  related_operation_id?: string;
  decision_type: string; // add/reduce/sell/t/other
  decision_time: string;
  reason: string;
}

export interface TradeReviewSessionItem {
  id: string;
  stock_code: string;
  stock_name: string;
  start_date: string;
  end_date?: string;
  status: string; // open / closed
  total_buy_amount?: number;
  total_sell_amount?: number;
  realized_pnl?: number;
  return_rate?: number;
  entry_reason: string;
  entry_expectation: string;
  reflection_did_well: string;
  reflection_did_poorly: string;
  reflection_redo_plan: string;
  ai_status: string; // pending/done/failed
  created_at: string;
  updated_at: string;
}

export interface TradeReviewDetail extends TradeReviewSessionItem {
  operations: OperationItem[];
  decision_notes: DecisionNoteItem[];
  ai_result?: Record<string, unknown>;
}

export interface TradeReviewListResponse {
  total: number;
  items: TradeReviewSessionItem[];
}

export interface MonthlyStatsResponse {
  month_key: string;
  trade_count: number;
  win_count: number;
  loss_count: number;
  realized_pnl: number;
  average_return_rate?: number;
  max_gain?: number;
  max_loss?: number;
  reviews: Record<string, unknown>[];
}

export interface OcrParseRequest {
  image_base64: string;
  mime_type?: string;
}

export interface OcrOperationItem {
  trade_time: string;
  operation_type: string;
  price: number;
  quantity: number;
  amount: number;
}

export interface OcrParseResponse {
  stock_name?: string;
  stock_code?: string;
  start_date?: string;
  end_date?: string;
  status?: string;
  total_buy_amount?: number;
  total_sell_amount?: number;
  realized_pnl?: number;
  return_rate?: number;
  operations: OcrOperationItem[];
  raw_lines: string[];
}

export type CreateTradeReviewRequest = Omit<TradeReviewSessionItem,
  'id' | 'ai_status' | 'created_at' | 'updated_at'> & {
  operations: OperationItem[];
  decision_notes: DecisionNoteItem[];
};

export type UpdateTradeReviewRequest = CreateTradeReviewRequest;

// API 函数

export function listTradeReviews(params?: {
  month?: string;
  stock_code?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<TradeReviewListResponse> {
  const q = new URLSearchParams();
  if (params?.month) q.set('month', params.month);
  if (params?.stock_code) q.set('stock_code', params.stock_code);
  if (params?.status) q.set('status', params.status);
  if (params?.limit != null) q.set('limit', String(params.limit));
  if (params?.offset != null) q.set('offset', String(params.offset));
  const suffix = q.toString() ? `?${q.toString()}` : '';
  return fetchJson<TradeReviewListResponse>(`/api/trade-reviews${suffix}`);
}

export function getTradeReview(reviewId: string): Promise<TradeReviewDetail> {
  return fetchJson<TradeReviewDetail>(`/api/trade-reviews/${reviewId}`);
}

export function createTradeReview(req: CreateTradeReviewRequest): Promise<TradeReviewDetail> {
  return postJson<TradeReviewDetail>('/api/trade-reviews', req);
}

export async function updateTradeReview(
  reviewId: string,
  req: UpdateTradeReviewRequest,
): Promise<TradeReviewDetail> {
  const resp = await fetch(`${API_BASE_URL}/api/trade-reviews/${reviewId}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(req),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function deleteTradeReview(reviewId: string): Promise<void> {
  const resp = await fetch(`${API_BASE_URL}/api/trade-reviews/${reviewId}`, {method: 'DELETE'});
  if (!resp.ok) throw new Error(await resp.text());
}

export function getMonthlyStats(monthKey: string): Promise<MonthlyStatsResponse> {
  return fetchJson<MonthlyStatsResponse>(`/api/trade-reviews/monthly/${monthKey}`);
}

export function ocrParseImage(req: OcrParseRequest): Promise<OcrParseResponse> {
  return postJson<OcrParseResponse>('/api/trade-reviews/ocr-parse', req);
}
