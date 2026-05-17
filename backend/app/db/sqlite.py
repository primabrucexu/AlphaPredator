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
                                          full_code
                                          TEXT
                                          PRIMARY
                                          KEY,
                                          code
                                          TEXT
                                          NOT
                                          NULL,
    name TEXT NOT NULL,
                                          is_st
                                          INTEGER
                                          NOT
                                          NULL
                                          DEFAULT
                                          0,
    cnspell TEXT NOT NULL DEFAULT '',
                                          market
                                          TEXT
                                          NOT
                                          NULL
                                          DEFAULT
                                          ''
);

CREATE INDEX IF NOT EXISTS idx_stock_list_code ON stock_list (code);
CREATE INDEX IF NOT EXISTS idx_stock_list_cnspell ON stock_list (cnspell);
CREATE INDEX IF NOT EXISTS idx_stock_list_market ON stock_list (market);

-- V2 init tables ----------------------------------------------------------

CREATE TABLE IF NOT EXISTS task_info
(
    id
    INTEGER
    PRIMARY
    KEY
    AUTOINCREMENT,
    task_id
    TEXT
    NOT
    NULL
    UNIQUE,
    task_type TEXT NOT NULL DEFAULT 'MARKET_DATA',
    start_date
    TEXT
    NOT
    NULL
    DEFAULT
    '',
    end_date
    TEXT
    NOT
    NULL
    DEFAULT
    '',
    status
    TEXT
    NOT
    NULL
    DEFAULT
    'PENDING',
    total_items
    INTEGER
    NOT
    NULL
    DEFAULT
    0,
    processed_items
    INTEGER
    NOT
    NULL
    DEFAULT
    0,
    current_label
    TEXT
    NOT
    NULL
    DEFAULT
    '',
    error_message
    TEXT
    NOT
    NULL
    DEFAULT
    '',
    task_start_date
    TEXT
    NOT
    NULL
    DEFAULT
    '',
    task_end_date
    TEXT
    NOT
    NULL
    DEFAULT
    ''
);

CREATE INDEX IF NOT EXISTS idx_task_info_status ON task_info (status);

CREATE TABLE IF NOT EXISTS task_item_info
(
    id
    INTEGER
    PRIMARY
    KEY
    AUTOINCREMENT,
    task_id
    TEXT
    NOT
    NULL
    UNIQUE,
    item
    TEXT
    NOT
    NULL
    DEFAULT
    '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    error_message TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT ''
);


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
    NULL,
    short_reason
    TEXT
    NOT
    NULL
    DEFAULT
    ''
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
        connection.executescript(SCHEMA_SQL)

        connection.commit()
    finally:
        connection.close()



def get_sqlite_engine(sqlite_path: Path | None = None):
    target_path = ensure_sqlite_parent(sqlite_path)
    return create_engine(f'sqlite:///{target_path}', echo=False)
