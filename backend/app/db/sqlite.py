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

CREATE TABLE IF NOT EXISTS focus_stock_entries (
    stock_code TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    FOREIGN KEY (stock_code) REFERENCES stock_profiles(stock_code)
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
