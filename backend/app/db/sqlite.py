import sqlite3
from pathlib import Path

from sqlmodel import create_engine

from app.core.settings import settings


SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS stock_profiles (
    stock_code TEXT PRIMARY KEY,
    stock_name TEXT NOT NULL,
    sectors_json TEXT NOT NULL,
    ai_quick_summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_stock_snapshots (
    trade_date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    current_price REAL NOT NULL,
    change_amount REAL NOT NULL,
    change_pct REAL NOT NULL,
    turnover_amount_billion REAL NOT NULL,
    turnover_rate REAL NOT NULL,
    PRIMARY KEY (trade_date, stock_code),
    FOREIGN KEY (stock_code) REFERENCES stock_profiles(stock_code)
);

CREATE INDEX IF NOT EXISTS idx_daily_stock_snapshots_trade_date ON daily_stock_snapshots (trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_stock_snapshots_stock_code ON daily_stock_snapshots (stock_code);

CREATE TABLE IF NOT EXISTS hot_sector_snapshots (
    trade_date TEXT NOT NULL,
    name TEXT NOT NULL,
    trend_label TEXT NOT NULL,
    heat_score INTEGER NOT NULL,
    PRIMARY KEY (trade_date, name)
);

CREATE INDEX IF NOT EXISTS idx_hot_sector_snapshots_trade_date ON hot_sector_snapshots (trade_date);

CREATE TABLE IF NOT EXISTS hot_sector_image_sources (
    trade_date TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_type TEXT NOT NULL,
    import_batch TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    parse_notes TEXT NOT NULL,
    PRIMARY KEY (trade_date, source_file)
);

CREATE INDEX IF NOT EXISTS idx_hot_sector_image_sources_trade_date ON hot_sector_image_sources (trade_date);

CREATE TABLE IF NOT EXISTS hot_sector_stock_facts (
    trade_date TEXT NOT NULL,
    source_file TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    board_count INTEGER,
    limit_up_time TEXT NOT NULL,
    reason_raw TEXT NOT NULL,
    reason_clean TEXT NOT NULL,
    ocr_confidence REAL NOT NULL,
    needs_review INTEGER NOT NULL,
    PRIMARY KEY (trade_date, source_file, stock_code)
);

CREATE INDEX IF NOT EXISTS idx_hot_sector_stock_facts_trade_date ON hot_sector_stock_facts (trade_date);
CREATE INDEX IF NOT EXISTS idx_hot_sector_stock_facts_stock_code ON hot_sector_stock_facts (stock_code);

CREATE TABLE IF NOT EXISTS hot_sector_sector_mappings (
    trade_date TEXT NOT NULL,
    source_file TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    sector_name_canonical TEXT NOT NULL,
    sector_alias_hit TEXT NOT NULL,
    is_primary_sector INTEGER NOT NULL,
    mapping_method TEXT NOT NULL,
    mapping_confidence REAL NOT NULL,
    needs_review INTEGER NOT NULL,
    PRIMARY KEY (trade_date, source_file, stock_code, sector_name_canonical)
);

CREATE INDEX IF NOT EXISTS idx_hot_sector_sector_mappings_trade_date ON hot_sector_sector_mappings (trade_date);
CREATE INDEX IF NOT EXISTS idx_hot_sector_sector_mappings_sector ON hot_sector_sector_mappings (sector_name_canonical);

CREATE TABLE IF NOT EXISTS hot_sector_daily_aggregates (
    trade_date TEXT NOT NULL,
    sector_name_canonical TEXT NOT NULL,
    source_stock_count INTEGER NOT NULL,
    max_board_count INTEGER NOT NULL,
    representative_stock_codes_json TEXT NOT NULL,
    representative_stock_names_json TEXT NOT NULL,
    heat_score INTEGER NOT NULL,
    rank_today INTEGER NOT NULL,
    aggregate_confidence REAL NOT NULL,
    needs_review INTEGER NOT NULL,
    PRIMARY KEY (trade_date, sector_name_canonical)
);

CREATE INDEX IF NOT EXISTS idx_hot_sector_daily_aggregates_trade_date ON hot_sector_daily_aggregates (trade_date);
CREATE INDEX IF NOT EXISTS idx_hot_sector_daily_aggregates_rank ON hot_sector_daily_aggregates (trade_date, rank_today);

CREATE TABLE IF NOT EXISTS hot_sector_recent_3d (
    trade_date TEXT NOT NULL,
    sector_name_canonical TEXT NOT NULL,
    days_present_3d INTEGER NOT NULL,
    heat_sum_3d INTEGER NOT NULL,
    heat_avg_3d REAL NOT NULL,
    best_rank_3d INTEGER NOT NULL,
    latest_rank INTEGER NOT NULL,
    trend_tag TEXT NOT NULL,
    PRIMARY KEY (trade_date, sector_name_canonical)
);

CREATE INDEX IF NOT EXISTS idx_hot_sector_recent_3d_trade_date ON hot_sector_recent_3d (trade_date);

CREATE TABLE IF NOT EXISTS focus_stock_entries (
    stock_code TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    FOREIGN KEY (stock_code) REFERENCES stock_profiles(stock_code)
);

CREATE TABLE IF NOT EXISTS stock_universe (
    ts_code TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    cnspell TEXT NOT NULL DEFAULT '',
    market TEXT NOT NULL DEFAULT '',
    list_status TEXT NOT NULL DEFAULT '',
    list_date TEXT NOT NULL DEFAULT '',
    delist_date TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stock_universe_symbol ON stock_universe (symbol);
CREATE INDEX IF NOT EXISTS idx_stock_universe_cnspell ON stock_universe (cnspell);
CREATE INDEX IF NOT EXISTS idx_stock_universe_market ON stock_universe (market);

-- V2 init tables ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS init_task (
    task_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'RANGE',
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    total_days INTEGER NOT NULL DEFAULT 0,
    processed_days INTEGER NOT NULL DEFAULT 0,
    trading_days INTEGER NOT NULL DEFAULT 0,
    done_trading_days INTEGER NOT NULL DEFAULT 0,
    current_date TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_init_task_status ON init_task (status);
CREATE INDEX IF NOT EXISTS idx_init_task_created ON init_task (created_at);

CREATE TABLE IF NOT EXISTS init_task_day (
    task_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    is_trading_day INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    row_count INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (task_id, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_init_task_day_task ON init_task_day (task_id);
CREATE INDEX IF NOT EXISTS idx_init_task_day_status ON init_task_day (task_id, status);

CREATE TABLE IF NOT EXISTS market_daily_quote (
    trade_date TEXT NOT NULL,
    ts_code TEXT NOT NULL,
    open REAL NOT NULL DEFAULT 0,
    high REAL NOT NULL DEFAULT 0,
    low REAL NOT NULL DEFAULT 0,
    close REAL NOT NULL DEFAULT 0,
    pre_close REAL NOT NULL DEFAULT 0,
    change REAL NOT NULL DEFAULT 0,
    pct_chg REAL NOT NULL DEFAULT 0,
    vol REAL NOT NULL DEFAULT 0,
    amount REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (trade_date, ts_code)
);

CREATE INDEX IF NOT EXISTS idx_market_daily_quote_date ON market_daily_quote (trade_date);
CREATE INDEX IF NOT EXISTS idx_market_daily_quote_code ON market_daily_quote (ts_code);

CREATE TABLE IF NOT EXISTS data_range_meta (
    dataset TEXT PRIMARY KEY,
    min_trade_date TEXT NOT NULL DEFAULT '',
    max_trade_date TEXT NOT NULL DEFAULT '',
    trading_day_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT ''
);
'''


def ensure_sqlite_parent(sqlite_path: Path | None = None) -> Path:
    target_path = sqlite_path or settings.sqlite_path
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    return target_path


def connect_sqlite(sqlite_path: Path | None = None) -> sqlite3.Connection:
    target_path = ensure_sqlite_parent(sqlite_path)
    connection = sqlite3.connect(target_path)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_sqlite_schema(sqlite_path: Path | None = None) -> None:
    connection = connect_sqlite(sqlite_path)
    try:
        connection.executescript(SCHEMA_SQL)
        connection.commit()
    finally:
        connection.close()


def get_sqlite_engine(sqlite_path: Path | None = None):
    target_path = ensure_sqlite_parent(sqlite_path)
    return create_engine(f'sqlite:///{target_path}', echo=False)
