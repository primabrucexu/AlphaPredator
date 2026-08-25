from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PendingNotification:
    task_uuid: str
    session_id: str
    state: str
    attempts: int
    payload: dict[str, Any] | None


class NotificationStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_notifications (
                    task_uuid TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    lease_until REAL NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def add(self, task_uuid: str, session_id: str, now: float | None = None) -> bool:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO task_notifications
                    (task_uuid, session_id, state, created_at, updated_at)
                VALUES (?, ?, 'POLLING', ?, ?)
                """,
                (task_uuid, session_id, timestamp, timestamp),
            )
        return result.rowcount == 1

    def due(self, now: float | None = None, limit: int = 20) -> list[PendingNotification]:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT task_uuid, session_id, state, attempts, payload_json
                FROM task_notifications
                WHERE state IN ('POLLING', 'READY')
                  AND next_attempt <= ?
                ORDER BY created_at
                LIMIT ?
                """,
                (timestamp, limit),
            ).fetchall()
        return [PendingNotification(
            task_uuid=row["task_uuid"],
            session_id=row["session_id"],
            state=row["state"],
            attempts=row["attempts"],
            payload=json.loads(row["payload_json"]) if row["payload_json"] else None,
        ) for row in rows]

    def schedule_poll(self, task_uuid: str, delay: float, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE task_notifications
                SET attempts = 0, next_attempt = ?, last_error = '', updated_at = ?
                WHERE task_uuid = ? AND state = 'POLLING'
                """,
                (timestamp + delay, timestamp, task_uuid),
            )

    def record_error(self, task_uuid: str, message: str, delay: float, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE task_notifications
                SET attempts = attempts + 1, next_attempt = ?, last_error = ?, updated_at = ?
                WHERE task_uuid = ? AND state IN ('POLLING', 'READY')
                """,
                (timestamp + delay, message[:1000], timestamp, task_uuid),
            )

    def mark_ready(self, task_uuid: str, payload: dict[str, Any], now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE task_notifications
                SET state = 'READY', payload_json = ?, attempts = 0,
                    next_attempt = ?, last_error = '', updated_at = ?
                WHERE task_uuid = ? AND state = 'POLLING'
                """,
                (json.dumps(payload, ensure_ascii=False), timestamp, timestamp, task_uuid),
            )

    def claim_delivery(self, task_uuid: str, lease_seconds: float = 120, now: float | None = None) -> bool:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            result = connection.execute(
                """
                UPDATE task_notifications
                SET state = 'SENDING', lease_until = ?, updated_at = ?
                WHERE task_uuid = ? AND state = 'READY'
                """,
                (timestamp + lease_seconds, timestamp, task_uuid),
            )
        return result.rowcount == 1

    def recover_stale_deliveries(self, now: float | None = None) -> int:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            result = connection.execute(
                """
                UPDATE task_notifications
                SET state = 'READY', next_attempt = ?, updated_at = ?
                WHERE state = 'SENDING' AND lease_until <= ?
                """,
                (timestamp, timestamp, timestamp),
            )
        return result.rowcount

    def delivery_failed(self, task_uuid: str, message: str, delay: float, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE task_notifications
                SET state = 'READY', attempts = attempts + 1, next_attempt = ?,
                    lease_until = 0, last_error = ?, updated_at = ?
                WHERE task_uuid = ? AND state = 'SENDING'
                """,
                (timestamp + delay, message[:1000], timestamp, task_uuid),
            )

    def mark_sent(self, task_uuid: str, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE task_notifications
                SET state = 'SENT', lease_until = 0, last_error = '', updated_at = ?
                WHERE task_uuid = ? AND state = 'SENDING'
                """,
                (timestamp, task_uuid),
            )

    def get(self, task_uuid: str) -> PendingNotification | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT task_uuid, session_id, state, attempts, payload_json
                FROM task_notifications WHERE task_uuid = ?
                """,
                (task_uuid,),
            ).fetchone()
        if row is None:
            return None
        return PendingNotification(
            task_uuid=row["task_uuid"],
            session_id=row["session_id"],
            state=row["state"],
            attempts=row["attempts"],
            payload=json.loads(row["payload_json"]) if row["payload_json"] else None,
        )
