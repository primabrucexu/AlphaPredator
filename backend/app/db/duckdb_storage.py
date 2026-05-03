from pathlib import Path

import duckdb

from app.core.settings import settings

DAILY_BARS_SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS daily_bars (
    stock_code VARCHAR NOT NULL,
    trade_date VARCHAR NOT NULL,
    open_price DOUBLE NOT NULL,
    high_price DOUBLE NOT NULL,
    low_price DOUBLE NOT NULL,
    close_price DOUBLE NOT NULL,
    volume BIGINT NOT NULL,
    turnover_amount_billion DOUBLE NOT NULL DEFAULT 0.0
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
        connection.execute(DAILY_BARS_SCHEMA_SQL)
        # Migration: add turnover_amount_billion if missing (for existing DuckDB files)
        try:
            connection.execute(
                'ALTER TABLE daily_bars ADD COLUMN turnover_amount_billion DOUBLE DEFAULT 0.0'
            )
        except Exception:  # noqa: BLE001
            pass  # Column already exists
    finally:
        connection.close()

if __name__ == '__main__':
    duck = connect_duckdb(Path("D:\\dev\\AlphaPredator\\data\\duckdb\\alphapredator.duckdb"))
    duck.execute("CALL start_ui();")
    print("duckdb ui启动完成")
    input("按任意键退出...")