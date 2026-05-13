from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.sqlite import connect_sqlite


class InitTaskRepo:
    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._sqlite_path = sqlite_path

    def _connect(self):
        return connect_sqlite(self._sqlite_path)

    def create_task_with_days(
            self,
            *,
            task_id: str,
            task_type: str,
            mode: str,
            start_date: str,
            end_date: str,
            total_days: int,
            trading_days: int,
            created_at: str,
            dates: list[str],
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''
                INSERT INTO init_task (task_id, task_type, mode, start_date, end_date, status,
                                       total_days, processed_days, trading_days, done_trading_days,
                                       current_date, error_message, created_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?, 0, ?, 0, '', '', ?, '', '')
                ''',
                (task_id, task_type, mode, start_date, end_date, total_days, trading_days, created_at),
            )
            conn.executemany(
                '''
                INSERT INTO init_task_day
                (task_id, trade_date, is_trading_day, status, row_count,
                 started_at, finished_at, error_message)
                VALUES (?, ?, ?, 'PENDING', 0, '', '', '')
                ''',
                [(task_id, d, 1) for d in dates],
            )
            conn.commit()
        finally:
            conn.close()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT * FROM init_task WHERE task_id = ?',
                (task_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_tasks(self, limit: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT * FROM init_task ORDER BY created_at DESC LIMIT ?',
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_task_days_page(self, task_id: str, page: int, per_page: int) -> dict[str, Any]:
        offset = (page - 1) * per_page
        conn = self._connect()
        try:
            total = conn.execute(
                'SELECT COUNT(*) FROM init_task_day WHERE task_id = ?',
                (task_id,),
            ).fetchone()[0]
            rows = conn.execute(
                '''
                SELECT *
                FROM init_task_day
                WHERE task_id = ?
                ORDER BY trade_date ASC LIMIT ?
                OFFSET ?
                ''',
                (task_id, per_page, offset),
            ).fetchall()
            return {
                'task_id': task_id,
                'total': total,
                'page': page,
                'per_page': per_page,
                'days': [dict(r) for r in rows],
            }
        finally:
            conn.close()

    def get_task_status(self, task_id: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT status FROM init_task WHERE task_id = ?',
                (task_id,),
            ).fetchone()
            return str(row['status']) if row else None
        finally:
            conn.close()

    def find_running_task_id(self) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT task_id FROM init_task WHERE status = 'RUNNING' LIMIT 1"
            ).fetchone()
            return str(row['task_id']) if row else None
        finally:
            conn.close()

    def try_mark_task_running(self, task_id: str, started_at: str) -> bool:
        conn = self._connect()
        try:
            updated = conn.execute(
                '''
                UPDATE init_task
                SET status     = 'RUNNING',
                    started_at = ?
                WHERE task_id = ?
                  AND status IN ('PENDING', 'FAILED', 'TERMINATED')
                ''',
                (started_at, task_id),
            ).rowcount
            conn.commit()
            return bool(updated)
        finally:
            conn.close()

    def reset_task_for_retry(self, task_id: str, now: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''UPDATE init_task
                   SET status            = 'PENDING',
                       processed_days    = 0,
                       done_trading_days = 0,
                       current_date      = '',
                       error_message     = '',
                       started_at        = '',
                       finished_at       = ''
                   WHERE task_id = ?''',
                (task_id,),
            )
            conn.execute(
                '''UPDATE init_task_day
                   SET status        = 'PENDING',
                       row_count     = 0,
                       started_at    = '',
                       finished_at   = '',
                       error_message = ''
                   WHERE task_id = ?''',
                (task_id,),
            )
            conn.execute(
                'UPDATE init_task SET created_at = ? WHERE task_id = ?',
                (now, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def terminate_task(self, task_id: str, finished_at: str) -> bool:
        conn = self._connect()
        try:
            updated = conn.execute(
                '''UPDATE init_task
                   SET status        = 'TERMINATED',
                       finished_at   = ?,
                       current_date  = '',
                       error_message = CASE
                                           WHEN error_message = '' THEN 'Terminated by user'
                                           ELSE error_message
                           END
                   WHERE task_id = ?
                     AND status IN ('RUNNING', 'FAILED', 'PENDING')''',
                (finished_at, task_id),
            ).rowcount
            conn.commit()
            return bool(updated)
        finally:
            conn.close()

    def get_running_task(self) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM init_task WHERE status = 'RUNNING' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_latest_finished_task(self) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM init_task WHERE status IN ('SUCCESS', 'FAILED', 'TERMINATED') "
                "ORDER BY finished_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def set_current_date_and_mark_day_running(self, task_id: str, trade_date: str, started_at: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                'UPDATE init_task SET current_date = ? WHERE task_id = ?',
                (trade_date, task_id),
            )
            conn.execute(
                "UPDATE init_task_day SET started_at = ?, status = 'RUNNING' "
                'WHERE task_id = ? AND trade_date = ?',
                (started_at, task_id, trade_date),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_day_writing(self, task_id: str, trade_date: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE init_task_day SET status = 'WRITING' WHERE task_id = ? AND trade_date = ?",
                (task_id, trade_date),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_day_success_and_increment(self, task_id: str, trade_date: str, finished_at: str, row_count: int) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''UPDATE init_task_day
                   SET status      = 'SUCCESS',
                       finished_at = ?,
                       row_count   = ?
                   WHERE task_id = ?
                     AND trade_date = ?''',
                (finished_at, row_count, task_id, trade_date),
            )
            conn.execute(
                '''UPDATE init_task
                   SET processed_days    = processed_days + 1,
                       done_trading_days = done_trading_days + 1
                   WHERE task_id = ?''',
                (task_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_task_progress_processed_only(self, task_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''UPDATE init_task
                   SET processed_days = processed_days + 1
                   WHERE task_id = ?''',
                (task_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def finalize_task_success_if_running(self, task_id: str, finished_at: str) -> bool:
        conn = self._connect()
        try:
            updated = conn.execute(
                '''UPDATE init_task
                   SET status       = 'SUCCESS',
                       finished_at  = ?,
                       current_date = ''
                   WHERE task_id = ?
                     AND status = 'RUNNING' ''',
                (finished_at, task_id),
            ).rowcount
            conn.commit()
            return bool(updated)
        finally:
            conn.close()

    def mark_day_failed(self, task_id: str, trade_date: str, finished_at: str, error_message: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''UPDATE init_task_day
                   SET status        = 'FAILED',
                       finished_at   = ?,
                       error_message = ?
                   WHERE task_id = ?
                     AND trade_date = ?''',
                (finished_at, error_message, task_id, trade_date),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_task_failed(self, task_id: str, finished_at: str, error_message: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''UPDATE init_task
                   SET status        = 'FAILED',
                       finished_at   = ?,
                       error_message = ?
                   WHERE task_id = ?''',
                (finished_at, error_message, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def is_task_terminated(self, task_id: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT status FROM init_task WHERE task_id = ?',
                (task_id,),
            ).fetchone()
            return bool(row and row['status'] == 'TERMINATED')
        finally:
            conn.close()

    def get_data_range_meta(self) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM data_range_meta WHERE dataset = 'daily_bars'"
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM data_range_meta WHERE dataset = 'market_daily_quote'"
                ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
