from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.sqlite import connect_sqlite


class JygsRepo:
    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._sqlite_path = sqlite_path

    def _connect(self):
        return connect_sqlite(self._sqlite_path)

    def get_auth_row(self) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT auth_cookie, updated_at, last_checked_at, is_valid, last_error FROM jygs_auth WHERE id = 1'
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def save_auth_cookie(self, cookie: str, updated_at: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''
                INSERT INTO jygs_auth (id, auth_cookie, updated_at, last_checked_at, is_valid, last_error)
                VALUES (1, ?, ?, '', 0, '') ON CONFLICT(id) DO
                UPDATE SET
                    auth_cookie = excluded.auth_cookie,
                    updated_at = excluded.updated_at,
                    is_valid = 0,
                    last_error = ''
                ''',
                [cookie.strip(), updated_at],
            )
            conn.commit()
        finally:
            conn.close()

    def get_auth_cookie(self) -> str:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT auth_cookie FROM jygs_auth WHERE id = 1'
            ).fetchone()
            return str(row['auth_cookie'] or '').strip() if row else ''
        finally:
            conn.close()

    def update_auth_check_status(self, checked_at: str, is_valid: bool, message: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''
                INSERT INTO jygs_auth (id, auth_cookie, updated_at, last_checked_at, is_valid, last_error)
                VALUES (1, '', '', ?, ?, ?) ON CONFLICT(id) DO
                UPDATE SET
                    last_checked_at = excluded.last_checked_at,
                    is_valid = excluded.is_valid,
                    last_error = excluded.last_error
                ''',
                [checked_at, 1 if is_valid else 0, message],
            )
            conn.commit()
        finally:
            conn.close()

    def has_sync_slot(self, slot_key: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT slot_key FROM jygs_sync_log WHERE slot_key = ?',
                [slot_key],
            ).fetchone()
            return bool(row)
        finally:
            conn.close()

    def upsert_sync_log(
            self,
            *,
            slot_key: str,
            trade_date: str,
            mode: str,
            status: str,
            message: str,
            triggered_at: str,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''
                INSERT OR REPLACE INTO jygs_sync_log (slot_key, trade_date, mode, status, message, triggered_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                [slot_key, trade_date, mode, status, message, triggered_at],
            )
            conn.commit()
        finally:
            conn.close()
