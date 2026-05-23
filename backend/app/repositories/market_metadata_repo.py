from __future__ import annotations

from pathlib import Path

from app.repositories.stock_list_repo import StockListRepo


class MarketMetadataRepo:
    """Read-only repository for lightweight SQLite market metadata lookups."""

    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._stock_list_repo = StockListRepo(sqlite_path)

    def build_stock_name_map(self) -> dict[str, str]:
        name_map: dict[str, str] = {}
        for row in self._stock_list_repo.list_code_name_pairs():
            stock_code = str(row.get('code') or '').zfill(6)
            name = str(row.get('name') or '')
            if stock_code and name:
                name_map[stock_code] = name
        return name_map

