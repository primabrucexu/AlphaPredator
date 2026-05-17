from __future__ import annotations

from pathlib import Path
from typing import Any

from app.repositories.stock_list_repo import StockListRepo
from app.repositories.stock_profile_repo import StockProfileRepo


class MarketMetadataRepo:
    """Read-only repository for lightweight SQLite market metadata lookups."""

    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._stock_list_repo = StockListRepo(sqlite_path)
        self._stock_profile_repo = StockProfileRepo(sqlite_path)

    def build_stock_name_map(self) -> dict[str, str]:
        profile_rows = self._stock_profile_repo.list_stock_code_name_pairs()
        name_map: dict[str, str] = {
            str(row['stock_code']): str(row['stock_name'])
            for row in profile_rows
            if row.get('stock_code') and row.get('stock_name')
        }
        for row in self._stock_list_repo.list_code_name_pairs():
            stock_code = str(row.get('code') or '').zfill(6)
            name = str(row.get('name') or '')
            if stock_code and name:
                name_map[stock_code] = name
        return name_map

    def get_stock_profile_payload(self, stock_code: str) -> dict[str, Any] | None:
        return self._stock_profile_repo.get_profile(stock_code)
