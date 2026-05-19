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


def ensure_sqlite_schema(sqlite_path: Path | None = None) -> None:
    schema_sql = _SCHEMA_FILE.read_text(encoding='utf-8')
    connection = connect_sqlite(sqlite_path)
    try:
        connection.executescript(schema_sql)
        _migrate_add_missing_columns(connection)
    finally:
        connection.close()


def get_sqlite_engine(sqlite_path: Path | None = None):
    target_path = ensure_sqlite_parent(sqlite_path)
    return create_engine(f'sqlite:///{target_path}', echo=False)
