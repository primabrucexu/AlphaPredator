import sqlite3
from pathlib import Path

from sqlmodel import create_engine

from app.core.settings import settings

_SCHEMA_FILE = Path(__file__).parent / 'schema.sql'


def ensure_sqlite_parent(sqlite_path: Path | None = None) -> Path:
    target_path = sqlite_path or settings.sqlite_path
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    return target_path


def connect_sqlite(sqlite_path: Path | None = None) -> sqlite3.Connection:
    target_path = ensure_sqlite_parent(sqlite_path)
    connection = sqlite3.connect(target_path)
    connection.row_factory = sqlite3.Row
    return connection


def _migrate_add_missing_columns(connection: sqlite3.Connection) -> None:
    """为已存在的表补加后续新增的列（column migration），保证旧数据库可用。"""
    migrations: list[tuple[str, str, str]] = [
        # (table, column, column_def)
        ('task_info', 'task_start_date', "TEXT NOT NULL DEFAULT ''"),
        ('task_info', 'task_end_date', "TEXT NOT NULL DEFAULT ''"),
    ]
    for table, column, col_def in migrations:
        existing = {
            row[1]
            for row in connection.execute(f'PRAGMA table_info({table})').fetchall()
        }
        if column not in existing:
            connection.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_def}')
    connection.commit()


def _migrate_daily_hot_info_stock_code(connection: sqlite3.Connection) -> None:
    """将 daily_hot_info.stock_code 从 INTEGER 迁移为 TEXT，并用 PRINTF 补零恢复前导零。

    SQLite 不支持 ALTER COLUMN，需重建表。
    迁移后 stock_code 保证为 6 位字符串（如 '000826'）。
    """
    # 检查当前 stock_code 列类型
    col_type = None
    for row in connection.execute('PRAGMA table_info(daily_hot_info)').fetchall():
        if row[1] == 'stock_code':
            col_type = str(row[2]).upper()
            break

    if col_type is None or col_type == 'TEXT':
        return  # 已是 TEXT，无需迁移

    # stock_code 是 INTEGER，需要重建表并补零
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS daily_hot_info_v2 (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date    TEXT    NOT NULL,
            limit_up_time TEXT    NOT NULL DEFAULT '',
            stock_code    TEXT    NOT NULL,
            name          VARCHAR NOT NULL,
            streak_text   VARCHAR NOT NULL,
            hot_theme     VARCHAR NOT NULL,
            reason        TEXT    NOT NULL,
            source        VARCHAR NOT NULL,
            short_reason  TEXT    NOT NULL DEFAULT ''
        );

        INSERT INTO daily_hot_info_v2
            (id, trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, source, short_reason)
        SELECT
            id,
            trade_date,
            limit_up_time,
            PRINTF('%06d', stock_code),
            name,
            streak_text,
            hot_theme,
            reason,
            source,
            short_reason
        FROM daily_hot_info;

        DROP TABLE daily_hot_info;
        ALTER TABLE daily_hot_info_v2 RENAME TO daily_hot_info;

        CREATE INDEX IF NOT EXISTS idx_daily_hot_info_trade_date ON daily_hot_info (trade_date);
        CREATE INDEX IF NOT EXISTS idx_daily_hot_info_stock_code  ON daily_hot_info (stock_code);
    ''')


def ensure_sqlite_schema(sqlite_path: Path | None = None) -> None:
    schema_sql = _SCHEMA_FILE.read_text(encoding='utf-8')
    connection = connect_sqlite(sqlite_path)
    try:
        connection.executescript(schema_sql)
        _migrate_add_missing_columns(connection)
        _migrate_daily_hot_info_stock_code(connection)
    finally:
        connection.close()


def get_sqlite_engine(sqlite_path: Path | None = None):
    target_path = ensure_sqlite_parent(sqlite_path)
    return create_engine(f'sqlite:///{target_path}', echo=False)
