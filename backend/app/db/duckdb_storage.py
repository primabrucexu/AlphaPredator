from pathlib import Path

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

if __name__ == '__main__':
    duck = connect_duckdb(settings.duckdb_path)
    duck.execute("CALL start_ui();")
    print("duckdb ui启动完成")
    input("按任意键退出...")