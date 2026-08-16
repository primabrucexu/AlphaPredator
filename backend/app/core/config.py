from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.getenv("ALPHAPREDATOR_DATA_DIR", BASE_DIR / "data"))
DATABASE_URL = os.getenv(
    "ALPHAPREDATOR_DATABASE_URL",
    f"sqlite:///{(DATA_DIR / 'alphapredator.db').as_posix()}",
)
