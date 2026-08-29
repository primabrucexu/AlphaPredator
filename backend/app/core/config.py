from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.getenv("ALPHAPREDATOR_DATA_DIR", BASE_DIR / "data"))
THS_CREDENTIALS_PATH = DATA_DIR / "ths_credentials.json"
MARKET_DATA_DATABASE_PATH = DATA_DIR / "market_data.duckdb"
DATABASE_URL = os.getenv(
    "ALPHAPREDATOR_DATABASE_URL",
    f"sqlite:///{(DATA_DIR / 'alphapredator.db').as_posix()}",
)
