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

CREATE TABLE IF NOT EXISTS jygs_auth (
    id INTEGER PRIMARY KEY,
    auth_cookie TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    last_checked_at TEXT NOT NULL DEFAULT '',
    is_valid INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS jygs_sync_log (
    slot_key TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    triggered_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jygs_sync_log_trade_date ON jygs_sync_log (trade_date);


CREATE TABLE IF NOT EXISTS stock_list (
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

CREATE INDEX IF NOT EXISTS idx_stock_list_symbol ON stock_list (symbol);
CREATE INDEX IF NOT EXISTS idx_stock_list_cnspell ON stock_list (cnspell);
CREATE INDEX IF NOT EXISTS idx_stock_list_market ON stock_list (market);

-- V2 init tables ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS init_task (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL DEFAULT 'MARKET_DATA',
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


CREATE TABLE IF NOT EXISTS data_range_meta (
    dataset TEXT PRIMARY KEY,
    min_trade_date TEXT NOT NULL DEFAULT '',
    max_trade_date TEXT NOT NULL DEFAULT '',
    trading_day_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT ''
);

-- 韭研公社每日复盘数据表（按 docs/human/data-storage.md 规范）

CREATE TABLE IF NOT EXISTS daily_hot_pic
(
    id
    INTEGER
    PRIMARY
    KEY
    AUTOINCREMENT,
    trade_date
    VARCHAR
    NOT
    NULL,
    summary_image_url
    VARCHAR
    NOT
    NULL,
    source
    VARCHAR
    NOT
    NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_hot_pic_trade_date ON daily_hot_pic (trade_date);

CREATE TABLE IF NOT EXISTS daily_hot_info
(
    id
    INTEGER
    PRIMARY
    KEY
    AUTOINCREMENT,
    trade_date
    TEXT
    NOT
    NULL,
    limit_up_time
    TEXT
    NOT
    NULL
    DEFAULT
    '',
    stock_code
    INTEGER
    NOT
    NULL,
    name
    VARCHAR
    NOT
    NULL,
    streak_text
    VARCHAR
    NOT
    NULL,
    hot_theme
    VARCHAR
    NOT
    NULL,
    reason
    TEXT
    NOT
    NULL,
    source
    VARCHAR
    NOT
    NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_hot_info_trade_date ON daily_hot_info (trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_hot_info_stock_code ON daily_hot_info (stock_code);
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
        _migrate_legacy_stock_list_table(connection)
        connection.executescript(SCHEMA_SQL)
        _drop_obsolete_tables(connection)
        connection.commit()
        _migrate_init_task_table(connection)
        connection.commit()
    finally:
        connection.close()


def _migrate_legacy_stock_list_table(connection: sqlite3.Connection) -> None:
    """Rename legacy stock table to stock_list for existing databases.

    Checks for the legacy table name via sqlite_master and renames it when found
    (idempotent: no-op when the legacy table does not exist).
    """
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_universe'"
    ).fetchone()
    if row is not None:
        connection.execute('ALTER TABLE stock_universe RENAME TO stock_list')


def _drop_obsolete_tables(connection: sqlite3.Connection) -> None:
    """Remove deprecated V1 tables that are no longer used by the backend."""
    obsolete_tables = (
        'daily_stock_snapshots',
        'hot_sector_snapshots',
        'focus_stock_entries',
        'market_daily_quote',
    )
    for table in obsolete_tables:
        connection.execute(f'DROP TABLE IF EXISTS {table}')



def _migrate_init_task_table(connection: sqlite3.Connection) -> None:
    """Add task_type column/index to init_task for existing databases."""
    init_task_exists = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='init_task'"
    ).fetchone()
    if init_task_exists is None:
        return

    existing_cols = {
        row[1]
        for row in connection.execute('PRAGMA table_info(init_task)')
    }
    if 'task_type' not in existing_cols:
        connection.execute(
            "ALTER TABLE init_task ADD COLUMN task_type TEXT NOT NULL DEFAULT 'MARKET_DATA'"
        )

    # Ensure index exists for task type filtering.
    connection.execute(
        'CREATE INDEX IF NOT EXISTS idx_init_task_type ON init_task (task_type)'
    )


def get_sqlite_engine(sqlite_path: Path | None = None):
    target_path = ensure_sqlite_parent(sqlite_path)
    return create_engine(f'sqlite:///{target_path}', echo=False)
