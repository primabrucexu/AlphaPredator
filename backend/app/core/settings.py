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
        'https://www.jiuyangongshe.com',
        'https://app.jiuyangongshe.com',
    )
    sqlite_path: Path = DATA_DIR / 'alphapredator.db'
    duckdb_path: Path = DATA_DIR / 'alphapredator.duckdb'
    parquet_dir: Path = DATA_DIR / 'parquet'
    market_snapshot_path: Path = parquet_dir / 'market_snapshot.json'
    daily_bars_parquet_path: Path = parquet_dir / 'stock_daily_bars.parquet'
    market_data_import_dir: Path = DATA_DIR / 'imports' / 'market-data'
    hot_sector_import_dir: Path = DATA_DIR / 'imports' / 'hot-sector-images'
    init_status_dir: Path = DATA_DIR / 'status'
    # Tushare configuration
    tushare_token_path: Path = DATA_DIR / 'config' / 'tushare.token'
    stock_list_path: Path = DATA_DIR / 'config' / 'stock_list.csv'
    tushare_rate_limit: int = 45  # max requests per minute (strict upper bound)
    tushare_history_start: str = '2024-01-01'
    # 韭研公社配置
    jygs_site_url: str = 'https://www.jiuyangongshe.com'
    jygs_api_url: str = 'https://app.jiuyangongshe.com/jystock-app'
    jygs_credentials_path: Path = DATA_DIR / 'config' / 'jygs.credentials'
    jygs_flow_trace_path: Path = DATA_DIR / 'status' / 'jygs-flow-trace.jsonl'
    jygs_flow_trace_enabled: bool = True


settings = Settings()
