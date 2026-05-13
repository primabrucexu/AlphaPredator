from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.sqlite import connect_sqlite


class StockProfileRepo:
    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._sqlite_path = sqlite_path

    def _connect(self):
        return connect_sqlite(self._sqlite_path)

    def get_profile(self, stock_code: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT stock_name, sectors_json, ai_quick_summary FROM stock_profiles WHERE stock_code = ?',
                [stock_code],
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_stock_code_name_pairs(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT stock_code, stock_name FROM stock_profiles'
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
