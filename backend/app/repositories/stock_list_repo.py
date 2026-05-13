from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.sqlite import connect_sqlite
from app.queries.market_queries import (
    get_stock_list_active_board_count_rows,
    get_stock_list_latest_uploaded_at,
)


class StockListRepo:
    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._sqlite_path = sqlite_path

    def _connect(self):
        return connect_sqlite(self._sqlite_path)

    def replace_all(self, rows: list[tuple[str, str, str, str, str, str, str, str, str]]) -> None:
        conn = self._connect()
        try:
            conn.execute('DELETE FROM stock_list')
            if rows:
                conn.executemany(
                    '''INSERT OR REPLACE INTO stock_list
                       (ts_code, symbol, name, cnspell, market, list_status, list_date, delist_date, uploaded_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    rows,
                )
            conn.commit()
        finally:
            conn.close()

    def get_active_by_ts_code_upper(self, ts_code_upper: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT ts_code, symbol, name FROM stock_list WHERE UPPER(ts_code) = ? AND list_status = 'L' LIMIT 1",
                [ts_code_upper],
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_active_by_symbol(self, symbol: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT ts_code, symbol, name FROM stock_list WHERE symbol = ? AND list_status = 'L'",
                [symbol],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_active_by_cnspell_exact(self, cnspell_upper: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT ts_code, symbol, name FROM stock_list WHERE cnspell = ? AND list_status = 'L'",
                [cnspell_upper],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_active_by_cnspell_prefix(self, cnspell_prefix_upper: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT ts_code, symbol, name FROM stock_list WHERE cnspell LIKE ? AND list_status = 'L' LIMIT ?",
                [cnspell_prefix_upper + '%', limit],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_active_for_search(self, query_upper: str, limit: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            if query_upper.isdigit():
                rows = conn.execute(
                    "SELECT ts_code, symbol, name FROM stock_list WHERE symbol LIKE ? AND list_status = 'L' LIMIT ?",
                    [query_upper + '%', limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT ts_code, symbol, name FROM stock_list WHERE cnspell LIKE ? AND list_status = 'L' LIMIT ?",
                    [query_upper + '%', limit],
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_active_symbol_name_pairs(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT symbol, name FROM stock_list WHERE list_status = 'L'"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_latest_uploaded_at(self) -> str | None:
        conn = self._connect()
        try:
            return get_stock_list_latest_uploaded_at(conn)
        finally:
            conn.close()

    def get_active_board_counts(self) -> dict[str, int]:
        conn = self._connect()
        try:
            rows = get_stock_list_active_board_count_rows(conn)
            return {str(row['market']): int(row['cnt']) for row in rows}
        finally:
            conn.close()
