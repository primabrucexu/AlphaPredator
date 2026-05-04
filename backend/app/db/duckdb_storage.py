import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb

from app.core.settings import settings

DAILY_BARS_SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS daily_bars (
    ts_code VARCHAR NOT NULL,
    trade_date VARCHAR NOT NULL,
    open DOUBLE NOT NULL,
    high DOUBLE NOT NULL,
    low DOUBLE NOT NULL,
    close DOUBLE NOT NULL,
    pre_close DOUBLE NOT NULL DEFAULT 0.0,
    change DOUBLE NOT NULL DEFAULT 0.0,
    pct_chg DOUBLE NOT NULL DEFAULT 0.0,
    vol DOUBLE NOT NULL DEFAULT 0.0,
    amount DOUBLE NOT NULL DEFAULT 0.0,
    is_up_limit BOOLEAN NOT NULL DEFAULT FALSE,
    is_down_limit BOOLEAN NOT NULL DEFAULT FALSE
)
'''


def ensure_duckdb_parent(duckdb_path: Path | None = None, parquet_dir: Path | None = None) -> tuple[Path, Path]:
    target_duckdb_path = duckdb_path or settings.duckdb_path
    target_parquet_dir = parquet_dir or settings.parquet_dir
    Path(target_duckdb_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_parquet_dir).mkdir(parents=True, exist_ok=True)
    return target_duckdb_path, target_parquet_dir


def connect_duckdb(duckdb_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    target_duckdb_path, _ = ensure_duckdb_parent(duckdb_path)
    return duckdb.connect(str(target_duckdb_path))


def ensure_duckdb_schema(duckdb_path: Path | None = None) -> None:
    connection = connect_duckdb(duckdb_path)
    try:
        # Migration: if old schema (stock_code column) exists, drop to recreate with spec schema
        try:
            cols = {row[0] for row in connection.execute('DESCRIBE daily_bars').fetchall()}
            if 'stock_code' in cols:
                connection.execute('DROP TABLE daily_bars')
        except Exception:  # noqa: BLE001
            pass  # table doesn't exist yet, that's fine
        connection.execute(DAILY_BARS_SCHEMA_SQL)
        # Migration: add any missing columns for partial upgrades
        existing_cols = {row[0] for row in connection.execute('DESCRIBE daily_bars').fetchall()}
        for col_name, col_def in [
            ('pre_close', 'DOUBLE DEFAULT 0.0'),
            ('change', 'DOUBLE DEFAULT 0.0'),
            ('pct_chg', 'DOUBLE DEFAULT 0.0'),
            ('is_up_limit', 'BOOLEAN DEFAULT FALSE'),
            ('is_down_limit', 'BOOLEAN DEFAULT FALSE'),
        ]:
            if col_name not in existing_cols:
                try:
                    connection.execute(
                        f'ALTER TABLE daily_bars ADD COLUMN {col_name} {col_def}'
                    )
                except Exception:  # noqa: BLE001
                    pass
    finally:
        connection.close()


def _parse_sql_params(params_text: str | None) -> Any:
    if not params_text:
        return None
    try:
        return json.loads(params_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            'Invalid --params JSON. Example: --params "[\"000001\", \"2026-04-30\"]"'
        ) from exc


def run_sql(sql: str, *, params: Any = None, duckdb_path: Path | None = None) -> list[tuple[Any, ...]]:
    connection = connect_duckdb(duckdb_path)
    try:
        if params is None:
            cursor = connection.execute(sql)
        else:
            cursor = connection.execute(sql, params)
        if cursor.description is None:
            return []
        return cursor.fetchall()
    finally:
        connection.close()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='DuckDB helper (UI mode or execute SQL).')
    parser.add_argument(
        '--sql',
        help='SQL to execute. If omitted, starts DuckDB UI mode.',
    )
    parser.add_argument(
        '--params',
        help='SQL parameters in JSON format, e.g. ["000001", "2026-04-30"] or {"code":"000001"}.',
    )
    parser.add_argument(
        '--duckdb-path',
        help='Optional DuckDB file path. Defaults to app settings.',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    target_path = Path(args.duckdb_path) if args.duckdb_path else settings.duckdb_path

    if not args.sql:
        duck = connect_duckdb(target_path)
        try:
            duck.execute('CALL start_ui();')
            print('duckdb ui启动完成')
            input('按任意键退出...')
        finally:
            duck.close()
        return 0

    try:
        parsed_params = _parse_sql_params(args.params)
        rows = run_sql(args.sql, params=parsed_params, duckdb_path=target_path)
    except Exception as exc:  # noqa: BLE001
        print(f'SQL execution failed: {exc}', file=sys.stderr)
        return 1

    if rows:
        for row in rows:
            print(row)
    else:
        print('SQL executed successfully (no result rows).')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
