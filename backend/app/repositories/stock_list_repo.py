from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from app.db.sqlite import connect_sqlite
from app.queries.market_queries import get_stock_list_active_board_count_rows


class StockListRepo:
    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._sqlite_path = sqlite_path

    def _connect(self):
        return connect_sqlite(self._sqlite_path)

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return cast(dict[str, Any], dict(row))

    def replace_all(self, rows: list[tuple[str, str, str, int, str, str]]) -> None:
        """Upsert incoming rows into stock_list.

        Guard: if *rows* is empty, the existing data is preserved and the
        method returns without touching the table.  This prevents an
        accidental full wipe when the upstream provider returns nothing.

        Strategy: never delete existing rows during sync.
        """
        if not rows:
            logging.getLogger(__name__).warning(
                'replace_all called with empty rows – keeping existing stock_list data'
            )
            return
        conn = self._connect()
        try:
            conn.executemany(
                '''INSERT OR REPLACE INTO stock_list
                   (full_code, code, name, is_st, cnspell, market)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def get_by_full_code_upper(self, full_code_upper: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT full_code, code, name, is_st, cnspell, market FROM stock_list WHERE UPPER(full_code) = ? LIMIT 1',
                [full_code_upper],
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def list_by_code(self, code: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT full_code, code, name, is_st, cnspell, market FROM stock_list WHERE code = ?',
                [code],
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def list_by_cnspell_exact(self, cnspell_upper: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT full_code, code, name, is_st, cnspell, market FROM stock_list WHERE cnspell = ?',
                [cnspell_upper],
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def list_by_cnspell_prefix(self, cnspell_prefix_upper: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT full_code, code, name, is_st, cnspell, market FROM stock_list WHERE cnspell LIKE ? LIMIT ?',
                [cnspell_prefix_upper + '%', limit],
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def list_for_search(self, query_upper: str, limit: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            if query_upper.isdigit():
                rows = conn.execute(
                    'SELECT full_code, code, name, is_st, cnspell, market FROM stock_list WHERE code LIKE ? LIMIT ?',
                    [query_upper + '%', limit],
                ).fetchall()
            else:
                rows = conn.execute(
                    'SELECT full_code, code, name, is_st, cnspell, market FROM stock_list WHERE cnspell LIKE ? LIMIT ?',
                    [query_upper + '%', limit],
                ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def list_code_name_pairs(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute('SELECT code, name FROM stock_list').fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def count_rows(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute('SELECT COUNT(*) AS cnt FROM stock_list').fetchone()
            return int(row['cnt'] if row else 0)
        finally:
            conn.close()

    def has_rows(self) -> bool:
        return self.count_rows() > 0

    def get_board_counts(self) -> dict[str, int]:
        conn = self._connect()
        try:
            rows = get_stock_list_active_board_count_rows(conn)
            return {str(row['market']): int(row['cnt']) for row in rows}
        finally:
            conn.close()
