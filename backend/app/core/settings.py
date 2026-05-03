from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT_DIR: Final[Path] = Path(__file__).resolve().parents[3]
CONF_DIR: Final[Path] = ROOT_DIR / 'conf'
DATA_DIR: Final[Path] = ROOT_DIR / 'data'


@dataclass(frozen=True)
class Settings:
    app_host: str = '127.0.0.1'
    app_port: int = 8000
    cors_origins: tuple[str, ...] = (
        'http://127.0.0.1:5173',
        'http://localhost:5173',
        'http://127.0.0.1:5174',
        'http://localhost:5174',
    )
    sqlite_path: Path = DATA_DIR / 'sqlite' / 'alphapredator.db'
    duckdb_path: Path = DATA_DIR / 'duckdb' / 'alphapredator.duckdb'
    parquet_dir: Path = DATA_DIR / 'parquet'
    market_snapshot_path: Path = parquet_dir / 'market_snapshot.json'
    daily_bars_parquet_path: Path = parquet_dir / 'stock_daily_bars.parquet'
    market_data_import_dir: Path = DATA_DIR / 'imports' / 'market-data'
    hot_sector_import_dir: Path = DATA_DIR / 'imports' / 'hot-sector-images'
    init_status_dir: Path = DATA_DIR / 'status'


settings = Settings()
