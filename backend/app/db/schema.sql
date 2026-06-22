-- AlphaPredator SQLite Schema
-- 该文件由 sqlite.py 的 ensure_sqlite_schema() 在启动时自动执行。
-- 所有表均使用 CREATE TABLE IF NOT EXISTS，保证幂等。
-- 新增列通过 sqlite.py 中的 _migrate_add_missing_columns() 处理。

-- ── 股票基础数据 ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stock_profiles
(
    stock_code       TEXT PRIMARY KEY,
    stock_name       TEXT NOT NULL,
    sectors_json     TEXT NOT NULL,
    ai_quick_summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_list
(
    full_code TEXT PRIMARY KEY,
    code      TEXT    NOT NULL,
    name      TEXT    NOT NULL,
    is_st     INTEGER NOT NULL DEFAULT 0,
    cnspell   TEXT    NOT NULL DEFAULT '',
    market    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_stock_list_code ON stock_list (code);
CREATE INDEX IF NOT EXISTS idx_stock_list_cnspell ON stock_list (cnspell);
CREATE INDEX IF NOT EXISTS idx_stock_list_market ON stock_list (market);

-- ── 行情数据导入任务（V2）────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS task_info
(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT    NOT NULL UNIQUE,
    task_type       TEXT    NOT NULL DEFAULT 'MARKET_DATA',
    start_date      TEXT    NOT NULL DEFAULT '',
    end_date        TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'PENDING',
    total_items     INTEGER NOT NULL DEFAULT 0,
    processed_items INTEGER NOT NULL DEFAULT 0,
    current_label   TEXT    NOT NULL DEFAULT '',
    error_message   TEXT    NOT NULL DEFAULT '',
    task_start_date TEXT    NOT NULL DEFAULT '',
    task_end_date   TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_task_info_status ON task_info (status);

CREATE TABLE IF NOT EXISTS data_range_meta
(
    dataset           TEXT PRIMARY KEY,
    min_trade_date    TEXT    NOT NULL DEFAULT '',
    max_trade_date    TEXT    NOT NULL DEFAULT '',
    trading_day_count INTEGER NOT NULL DEFAULT 0,
    updated_at        TEXT    NOT NULL DEFAULT ''
);


-- ── 韭研公社每日复盘数据 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS daily_hot_pic
(
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date        VARCHAR NOT NULL,
    summary_image_url VARCHAR NOT NULL,
    source            VARCHAR NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_hot_pic_trade_date ON daily_hot_pic (trade_date);

CREATE TABLE IF NOT EXISTS daily_hot_info
(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date    TEXT    NOT NULL,
    limit_up_time TEXT    NOT NULL DEFAULT '',
    stock_code TEXT NOT NULL,
    name          VARCHAR NOT NULL,
    streak_text   VARCHAR NOT NULL,
    hot_theme     VARCHAR NOT NULL,
    reason        TEXT    NOT NULL,
    source        VARCHAR NOT NULL,
    short_reason  TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_daily_hot_info_trade_date ON daily_hot_info (trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_hot_info_stock_code ON daily_hot_info (stock_code);

-- ── 交易复盘系统 ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trade_review_session
(
    id                    TEXT    PRIMARY KEY,
    stock_code            TEXT    NOT NULL,
    stock_name            TEXT    NOT NULL,
    start_date            TEXT    NOT NULL,
    end_date              TEXT,
    status                TEXT    NOT NULL DEFAULT 'open',
    total_buy_amount      REAL,
    total_sell_amount     REAL,
    realized_pnl          REAL,
    return_rate           REAL,
    entry_reason          TEXT    NOT NULL DEFAULT '',
    entry_expectation     TEXT    NOT NULL DEFAULT '',
    reflection_did_well   TEXT    NOT NULL DEFAULT '',
    reflection_did_poorly TEXT    NOT NULL DEFAULT '',
    reflection_redo_plan  TEXT    NOT NULL DEFAULT '',
    ai_status             TEXT    NOT NULL DEFAULT 'pending',
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trs_stock_date ON trade_review_session (stock_code, start_date);
CREATE INDEX IF NOT EXISTS idx_trs_status     ON trade_review_session (status);
CREATE INDEX IF NOT EXISTS idx_trs_month      ON trade_review_session (substr(start_date, 1, 7));

CREATE TABLE IF NOT EXISTS trade_review_operation
(
    id             TEXT    PRIMARY KEY,
    review_id      TEXT    NOT NULL,
    trade_time     TEXT    NOT NULL,
    operation_type TEXT    NOT NULL,
    price          REAL    NOT NULL,
    quantity       INTEGER NOT NULL,
    amount         REAL    NOT NULL,
    source         TEXT    NOT NULL DEFAULT 'manual',
    note           TEXT    NOT NULL DEFAULT '',
    sort_index     INTEGER,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tro_review_time ON trade_review_operation (review_id, trade_time);

CREATE TABLE IF NOT EXISTS trade_review_decision_note
(
    id                   TEXT PRIMARY KEY,
    review_id            TEXT NOT NULL,
    related_operation_id TEXT,
    decision_type        TEXT NOT NULL,
    decision_time        TEXT NOT NULL,
    reason               TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trdn_review ON trade_review_decision_note (review_id);

CREATE TABLE IF NOT EXISTS trade_review_ai_result
(
    id                  TEXT PRIMARY KEY,
    result_type         TEXT NOT NULL,
    review_id           TEXT,
    month_key           TEXT,
    model_name          TEXT NOT NULL DEFAULT '',
    input_payload_json  TEXT NOT NULL DEFAULT '',
    output_payload_json TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'done',
    error_message       TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trar_review_type ON trade_review_ai_result (review_id, result_type);
CREATE INDEX IF NOT EXISTS idx_trar_month_type  ON trade_review_ai_result (month_key, result_type);

CREATE TABLE IF NOT EXISTS trade_review_monthly_summary
(
    month_key           TEXT    PRIMARY KEY,
    trade_count         INTEGER NOT NULL DEFAULT 0,
    win_count           INTEGER NOT NULL DEFAULT 0,
    loss_count          INTEGER NOT NULL DEFAULT 0,
    realized_pnl        REAL    NOT NULL DEFAULT 0,
    average_return_rate REAL,
    max_gain            REAL,
    max_loss            REAL,
    generated_at        TEXT    NOT NULL
);
-- ── 股票联动套利回测 ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stock_linkage_backtest_job
(
    id                 TEXT PRIMARY KEY,
    job_name           TEXT,
    a_select_mode      TEXT    NOT NULL,
    manual_a_full_code TEXT,
    hot_top_n          INTEGER,
    start_date         TEXT    NOT NULL,
    end_date           TEXT    NOT NULL,
    min_sample_count   INTEGER NOT NULL DEFAULT 30,
    status             TEXT    NOT NULL DEFAULT 'pending',
    error_message      TEXT,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL,
    finished_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_stock_linkage_job_status_created
    ON stock_linkage_backtest_job (status, created_at);
CREATE INDEX IF NOT EXISTS idx_stock_linkage_job_created
    ON stock_linkage_backtest_job (created_at);

CREATE TABLE IF NOT EXISTS stock_linkage_trigger_event
(
    id                TEXT PRIMARY KEY,
    job_id            TEXT NOT NULL,
    a_full_code       TEXT NOT NULL,
    trade_date        TEXT NOT NULL,
    bar_time          TEXT NOT NULL,
    bar_index         INTEGER NOT NULL,
    trigger_type      TEXT NOT NULL,
    trigger_threshold REAL NOT NULL,
    trigger_return    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stock_linkage_trigger_a_condition
    ON stock_linkage_trigger_event (job_id, a_full_code, trigger_type, trigger_threshold);
CREATE INDEX IF NOT EXISTS idx_stock_linkage_trigger_time
    ON stock_linkage_trigger_event (job_id, trade_date, bar_index);

CREATE TABLE IF NOT EXISTS stock_linkage_baseline_metric
(
    id                   TEXT PRIMARY KEY,
    job_id               TEXT    NOT NULL,
    b_full_code          TEXT    NOT NULL,
    observation_type     TEXT    NOT NULL,
    target_threshold     REAL    NOT NULL,
    baseline_sample_count INTEGER NOT NULL,
    baseline_hit_count    INTEGER NOT NULL,
    baseline_probability  REAL    NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_linkage_baseline_b_metric
    ON stock_linkage_baseline_metric (job_id, b_full_code, observation_type, target_threshold);

CREATE TABLE IF NOT EXISTS stock_linkage_backtest_result
(
    id                    TEXT PRIMARY KEY,
    job_id                TEXT    NOT NULL,
    a_full_code           TEXT    NOT NULL,
    b_full_code           TEXT    NOT NULL,
    trigger_type          TEXT    NOT NULL,
    trigger_threshold     REAL    NOT NULL,
    observation_type      TEXT    NOT NULL,
    target_threshold      REAL    NOT NULL,
    sample_count          INTEGER NOT NULL,
    hit_count             INTEGER NOT NULL,
    condition_probability REAL    NOT NULL,
    baseline_probability  REAL    NOT NULL,
    probability_lift      REAL    NOT NULL,
    lift_multiple         REAL,
    trigger_coverage_rate REAL    NOT NULL,
    confidence_level      TEXT    NOT NULL,
    score                 REAL    NOT NULL,
    created_at            TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stock_linkage_result_job_score
    ON stock_linkage_backtest_result (job_id, score);
CREATE INDEX IF NOT EXISTS idx_stock_linkage_result_pair
    ON stock_linkage_backtest_result (job_id, a_full_code, b_full_code);
CREATE INDEX IF NOT EXISTS idx_stock_linkage_result_trigger
    ON stock_linkage_backtest_result (job_id, trigger_type, trigger_threshold);
CREATE INDEX IF NOT EXISTS idx_stock_linkage_result_observation
    ON stock_linkage_backtest_result (job_id, observation_type, target_threshold);

-- ── MACD 日线形态预警 ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS macd_alert_result
(
    id                               TEXT PRIMARY KEY,
    trade_date                       TEXT    NOT NULL,
    stock_code                       TEXT    NOT NULL,
    stock_name                       TEXT    NOT NULL,
    pattern_key                      TEXT    NOT NULL,
    pattern_name                     TEXT    NOT NULL,
    cross_zone                       TEXT    NOT NULL,
    close_price                      REAL    NOT NULL,
    next_cross_trigger_price         REAL    NOT NULL,
    cross_trigger_distance_pct       REAL    NOT NULL,
    next_limit_up_price              REAL,
    cross_trigger_reachable          INTEGER NOT NULL DEFAULT 1,
    cross_trigger_unreachable_reason TEXT,
    next_trend_keep_price            REAL    NOT NULL,
    trend_keep_distance_pct          REAL    NOT NULL,
    macd_dif                         REAL    NOT NULL,
    macd_dea                         REAL    NOT NULL,
    macd_hist                        REAL    NOT NULL,
    green_shrink_days                INTEGER NOT NULL DEFAULT 2,
    last_limit_up_date               TEXT,
    last_limit_up_theme              TEXT,
    last_limit_up_days_ago           INTEGER,
    theme_heat_window_days           INTEGER NOT NULL DEFAULT 5,
    theme_recent_limit_up_count      INTEGER NOT NULL DEFAULT 0,
    theme_recent_rank                INTEGER,
    theme_heat_level                 TEXT    NOT NULL DEFAULT 'none',
    next_track_date                  TEXT,
    track_status                     TEXT    NOT NULL DEFAULT 'pending',
    tracked_close_price              REAL,
    tracked_macd_dif                 REAL,
    tracked_macd_dea                 REAL,
    tracked_macd_hist                REAL,
    tracked_at                       TEXT,
    backtest_lookback_days           INTEGER NOT NULL DEFAULT 720,
    backtest_sample_count            INTEGER NOT NULL DEFAULT 0,
    backtest_cross_success_count     INTEGER NOT NULL DEFAULT 0,
    backtest_cross_success_rate      REAL,
    backtest_t1_cross_confirmed_count INTEGER NOT NULL DEFAULT 0,
    backtest_t1_trend_kept_count     INTEGER NOT NULL DEFAULT 0,
    backtest_t1_trend_weakened_count INTEGER NOT NULL DEFAULT 0,
    backtest_t1_trend_keep_rate      REAL,
    backtest_completed_trade_count   INTEGER NOT NULL DEFAULT 0,
    backtest_profit_trade_count      INTEGER NOT NULL DEFAULT 0,
    backtest_win_rate                REAL,
    backtest_avg_return_pct          REAL,
    backtest_max_return_pct          REAL,
    backtest_max_loss_pct            REAL,
    backtest_avg_holding_days        REAL,
    backtest_confidence_level        TEXT    NOT NULL DEFAULT 'insufficient',
    score                            REAL    NOT NULL DEFAULT 0,
    summary                          TEXT    NOT NULL,
    status                           TEXT    NOT NULL DEFAULT 'active',
    created_at                       TEXT    NOT NULL,
    updated_at                       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_macd_alert_result_date_pattern_zone
    ON macd_alert_result (trade_date, pattern_key, cross_zone);
CREATE INDEX IF NOT EXISTS idx_macd_alert_result_stock_date
    ON macd_alert_result (stock_code, trade_date);
CREATE INDEX IF NOT EXISTS idx_macd_alert_result_date_score
    ON macd_alert_result (trade_date, score);
CREATE UNIQUE INDEX IF NOT EXISTS uq_macd_alert_result_unique
    ON macd_alert_result (trade_date, stock_code, pattern_key, cross_zone);

CREATE TABLE IF NOT EXISTS macd_alert_backtest_sample
(
    id                            TEXT PRIMARY KEY,
    alert_result_id               TEXT    NOT NULL,
    stock_code                    TEXT    NOT NULL,
    stock_name                    TEXT    NOT NULL,
    alert_date                    TEXT    NOT NULL,
    alert_close_price             REAL    NOT NULL,
    next_cross_trigger_price      REAL    NOT NULL,
    cross_trigger_distance_pct    REAL    NOT NULL,
    next_trend_keep_price         REAL    NOT NULL,
    trend_keep_distance_pct       REAL    NOT NULL,
    alert_macd_dif                REAL    NOT NULL,
    alert_macd_dea                REAL    NOT NULL,
    alert_macd_hist               REAL    NOT NULL,
    alert_cross_zone              TEXT    NOT NULL,
    last_limit_up_date            TEXT,
    last_limit_up_theme           TEXT,
    last_limit_up_days_ago        INTEGER,
    theme_heat_window_days        INTEGER NOT NULL DEFAULT 5,
    theme_recent_limit_up_count   INTEGER NOT NULL DEFAULT 0,
    theme_recent_rank             INTEGER,
    theme_heat_level              TEXT    NOT NULL DEFAULT 'none',
    buy_date                      TEXT,
    buy_price                     REAL,
    t1_close_price                REAL,
    t1_track_status               TEXT,
    t1_macd_dif                   REAL,
    t1_macd_dea                   REAL,
    t1_macd_hist                  REAL,
    cross_date                    TEXT,
    cross_type                    TEXT,
    sell_date                     TEXT,
    sell_price                    REAL,
    sell_reason                   TEXT,
    return_pct                    REAL,
    holding_days                  INTEGER,
    status                        TEXT    NOT NULL,
    created_at                    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_macd_alert_sample_result_date
    ON macd_alert_backtest_sample (alert_result_id, alert_date);
CREATE INDEX IF NOT EXISTS idx_macd_alert_sample_result_return
    ON macd_alert_backtest_sample (alert_result_id, return_pct);
CREATE INDEX IF NOT EXISTS idx_macd_alert_sample_stock_date
    ON macd_alert_backtest_sample (stock_code, alert_date);

CREATE TABLE IF NOT EXISTS macd_alert_report
(
    id                TEXT PRIMARY KEY,
    report_type       TEXT NOT NULL,
    trade_date        TEXT,
    source_trade_date TEXT,
    alert_result_id   TEXT,
    html_file_path    TEXT,
    pdf_file_path     TEXT,
    csv_file_path     TEXT,
    formats_json      TEXT NOT NULL,
    title             TEXT NOT NULL,
    summary           TEXT,
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_macd_alert_report_type_date
    ON macd_alert_report (report_type, trade_date);
CREATE INDEX IF NOT EXISTS idx_macd_alert_report_alert_result
    ON macd_alert_report (alert_result_id);
