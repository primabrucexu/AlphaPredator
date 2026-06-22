from sqlmodel import Field, SQLModel



class StockList(SQLModel, table=True):
    __tablename__ = 'stock_list'

    full_code: str = Field(primary_key=True)
    code: str
    name: str
    is_st: bool = False
    cnspell: str = ''
    market: str = ''


class TaskInfo(SQLModel, table=True):
    __tablename__ = 'task_info'

    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(unique=True)
    task_type: str = 'MARKET_DATA'
    start_date: str
    end_date: str
    status: str = 'PENDING'
    total_items: int = 0
    processed_items: int = 0
    current_label: str = ''
    error_message: str = ''
    task_start_date: str = ''
    task_end_date: str = ''


class DailyHotPic(SQLModel, table=True):
    __tablename__ = 'daily_hot_pic'

    id: int | None = Field(default=None, primary_key=True)
    trade_date: str
    summary_image_url: str
    source: str


class DailyHotInfo(SQLModel, table=True):
    __tablename__ = 'daily_hot_info'

    id: int | None = Field(default=None, primary_key=True)
    trade_date: str
    limit_up_time: str = ''
    stock_code: str
    name: str
    streak_text: str
    hot_theme: str
    reason: str
    source: str
    short_reason: str = ''


class TradeReviewSession(SQLModel, table=True):
    __tablename__ = 'trade_review_session'

    id: str = Field(primary_key=True)
    stock_code: str
    stock_name: str
    start_date: str
    end_date: str | None = None
    status: str = 'open'
    total_buy_amount: float | None = None
    total_sell_amount: float | None = None
    realized_pnl: float | None = None
    return_rate: float | None = None
    entry_reason: str = ''
    entry_expectation: str = ''
    reflection_did_well: str = ''
    reflection_did_poorly: str = ''
    reflection_redo_plan: str = ''
    ai_status: str = 'pending'
    created_at: str
    updated_at: str


class TradeReviewOperation(SQLModel, table=True):
    __tablename__ = 'trade_review_operation'

    id: str = Field(primary_key=True)
    review_id: str
    trade_time: str
    operation_type: str
    price: float
    quantity: int
    amount: float
    source: str = 'manual'
    note: str = ''
    sort_index: int | None = None
    created_at: str
    updated_at: str


class TradeReviewDecisionNote(SQLModel, table=True):
    __tablename__ = 'trade_review_decision_note'

    id: str = Field(primary_key=True)
    review_id: str
    related_operation_id: str | None = None
    decision_type: str
    decision_time: str
    reason: str = ''
    created_at: str
    updated_at: str


class TradeReviewAiResult(SQLModel, table=True):
    __tablename__ = 'trade_review_ai_result'

    id: str = Field(primary_key=True)
    result_type: str
    review_id: str | None = None
    month_key: str | None = None
    model_name: str = ''
    input_payload_json: str = ''
    output_payload_json: str = ''
    status: str = 'done'
    error_message: str = ''
    created_at: str


class TradeReviewMonthlySummary(SQLModel, table=True):
    __tablename__ = 'trade_review_monthly_summary'

    month_key: str = Field(primary_key=True)
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    realized_pnl: float = 0
    average_return_rate: float | None = None
    max_gain: float | None = None
    max_loss: float | None = None
    generated_at: str


class StockLinkageBacktestJob(SQLModel, table=True):
    __tablename__ = 'stock_linkage_backtest_job'

    id: str = Field(primary_key=True)
    job_name: str | None = None
    a_select_mode: str
    manual_a_full_code: str | None = None
    hot_top_n: int | None = None
    start_date: str
    end_date: str
    min_sample_count: int = 30
    status: str = 'pending'
    error_message: str | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None


class StockLinkageTriggerEvent(SQLModel, table=True):
    __tablename__ = 'stock_linkage_trigger_event'

    id: str = Field(primary_key=True)
    job_id: str
    a_full_code: str
    trade_date: str
    bar_time: str
    bar_index: int
    trigger_type: str
    trigger_threshold: float
    trigger_return: float


class StockLinkageBaselineMetric(SQLModel, table=True):
    __tablename__ = 'stock_linkage_baseline_metric'

    id: str = Field(primary_key=True)
    job_id: str
    b_full_code: str
    observation_type: str
    target_threshold: float
    baseline_sample_count: int
    baseline_hit_count: int
    baseline_probability: float


class StockLinkageBacktestResult(SQLModel, table=True):
    __tablename__ = 'stock_linkage_backtest_result'

    id: str = Field(primary_key=True)
    job_id: str
    a_full_code: str
    b_full_code: str
    trigger_type: str
    trigger_threshold: float
    observation_type: str
    target_threshold: float
    sample_count: int
    hit_count: int
    condition_probability: float
    baseline_probability: float
    probability_lift: float
    lift_multiple: float | None = None
    trigger_coverage_rate: float
    confidence_level: str
    score: float
    created_at: str


class MacdAlertResult(SQLModel, table=True):
    __tablename__ = 'macd_alert_result'

    id: str = Field(primary_key=True)
    trade_date: str
    stock_code: str
    stock_name: str
    pattern_key: str
    pattern_name: str
    cross_zone: str
    close_price: float
    next_cross_trigger_price: float
    cross_trigger_distance_pct: float
    next_limit_up_price: float | None = None
    cross_trigger_reachable: int = 1
    cross_trigger_unreachable_reason: str | None = None
    next_trend_keep_price: float
    trend_keep_distance_pct: float
    macd_dif: float
    macd_dea: float
    macd_hist: float
    green_shrink_days: int = 2
    last_limit_up_date: str | None = None
    last_limit_up_theme: str | None = None
    last_limit_up_days_ago: int | None = None
    theme_heat_window_days: int = 5
    theme_recent_limit_up_count: int = 0
    theme_recent_rank: int | None = None
    theme_heat_level: str = 'none'
    next_track_date: str | None = None
    track_status: str = 'pending'
    tracked_close_price: float | None = None
    tracked_macd_dif: float | None = None
    tracked_macd_dea: float | None = None
    tracked_macd_hist: float | None = None
    tracked_at: str | None = None
    backtest_lookback_days: int = 720
    backtest_sample_count: int = 0
    backtest_cross_success_count: int = 0
    backtest_cross_success_rate: float | None = None
    backtest_t1_cross_confirmed_count: int = 0
    backtest_t1_trend_kept_count: int = 0
    backtest_t1_trend_weakened_count: int = 0
    backtest_t1_trend_keep_rate: float | None = None
    backtest_completed_trade_count: int = 0
    backtest_profit_trade_count: int = 0
    backtest_win_rate: float | None = None
    backtest_avg_return_pct: float | None = None
    backtest_max_return_pct: float | None = None
    backtest_max_loss_pct: float | None = None
    backtest_avg_holding_days: float | None = None
    backtest_confidence_level: str = 'insufficient'
    score: float = 0
    summary: str
    status: str = 'active'
    created_at: str
    updated_at: str


class MacdAlertBacktestSample(SQLModel, table=True):
    __tablename__ = 'macd_alert_backtest_sample'

    id: str = Field(primary_key=True)
    alert_result_id: str
    stock_code: str
    stock_name: str
    alert_date: str
    alert_close_price: float
    next_cross_trigger_price: float
    cross_trigger_distance_pct: float
    next_trend_keep_price: float
    trend_keep_distance_pct: float
    alert_macd_dif: float
    alert_macd_dea: float
    alert_macd_hist: float
    alert_cross_zone: str
    last_limit_up_date: str | None = None
    last_limit_up_theme: str | None = None
    last_limit_up_days_ago: int | None = None
    theme_heat_window_days: int = 5
    theme_recent_limit_up_count: int = 0
    theme_recent_rank: int | None = None
    theme_heat_level: str = 'none'
    buy_date: str | None = None
    buy_price: float | None = None
    t1_close_price: float | None = None
    t1_track_status: str | None = None
    t1_macd_dif: float | None = None
    t1_macd_dea: float | None = None
    t1_macd_hist: float | None = None
    cross_date: str | None = None
    cross_type: str | None = None
    sell_date: str | None = None
    sell_price: float | None = None
    sell_reason: str | None = None
    return_pct: float | None = None
    holding_days: int | None = None
    status: str
    created_at: str


class MacdAlertReport(SQLModel, table=True):
    __tablename__ = 'macd_alert_report'

    id: str = Field(primary_key=True)
    report_type: str
    trade_date: str | None = None
    source_trade_date: str | None = None
    alert_result_id: str | None = None
    html_file_path: str | None = None
    pdf_file_path: str | None = None
    csv_file_path: str | None = None
    formats_json: str
    title: str
    summary: str | None = None
    created_at: str


