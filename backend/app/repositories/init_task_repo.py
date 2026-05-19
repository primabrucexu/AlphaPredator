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
            start_date: str,
            end_date: str,
            total_items: int,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''
                INSERT INTO task_info
                (task_id, task_type, start_date, end_date, status, total_items, processed_items)
                VALUES (?, ?, ?, ?, 'PENDING', ?, 0)
                ''',
                (task_id, task_type, start_date, end_date, total_items),
            )
            conn.commit()
        finally:
            conn.close()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT * FROM task_info WHERE task_id = ?',
                (task_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_tasks(self, limit: int) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT * FROM task_info ORDER BY id DESC LIMIT ?',
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_task_status(self, task_id: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT status FROM task_info WHERE task_id = ?',
                (task_id,),
            ).fetchone()
            return str(row['status']) if row else None
        finally:
            conn.close()

    def find_running_task_id(self) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT task_id FROM task_info WHERE status = 'RUNNING' LIMIT 1"
            ).fetchone()
            return str(row['task_id']) if row else None
        finally:
            conn.close()

    def try_mark_task_running(self, task_id: str, task_start_date: str) -> bool:
        conn = self._connect()
        try:
            updated = conn.execute(
                '''
                UPDATE task_info
                SET status          = 'RUNNING',
                    task_start_date = ?
                WHERE task_id = ?
                  AND status IN ('PENDING', 'FAILED', 'TERMINATED')
                ''',
                (task_start_date, task_id),
            ).rowcount
            conn.commit()
            return bool(updated)
        finally:
            conn.close()

    def reset_task_for_retry(self, task_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''UPDATE task_info
                   SET status          = 'PENDING',
                       processed_items = 0,
                       current_label   = '',
                       error_message   = '',
                       task_start_date = '',
                       task_end_date   = ''
                   WHERE task_id = ?''',
                (task_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def prepare_task_for_resume(self, task_id: str, *, keep_current_label: bool) -> None:
        conn = self._connect()
        try:
            if keep_current_label:
                conn.execute(
                    '''UPDATE task_info
                       SET status        = 'PENDING',
                           error_message = '',
                           task_end_date = ''
                       WHERE task_id = ?''',
                    (task_id,),
                )
            else:
                conn.execute(
                    '''UPDATE task_info
                       SET status        = 'PENDING',
                           current_label = '',
                           error_message = '',
                           task_end_date = ''
                       WHERE task_id = ?''',
                    (task_id,),
                )
            conn.commit()
        finally:
            conn.close()

    def terminate_task(self, task_id: str, task_end_date: str) -> bool:
        conn = self._connect()
        try:
            updated = conn.execute(
                '''UPDATE task_info
                   SET status        = 'TERMINATED',
                       task_end_date = ?,
                       error_message = CASE
                                           WHEN error_message = '' THEN 'Terminated by user'
                                           ELSE error_message
                           END
                   WHERE task_id = ?
                     AND status IN ('RUNNING', 'FAILED', 'PENDING')''',
                (task_end_date, task_id),
            ).rowcount
            conn.commit()
            return bool(updated)
        finally:
            conn.close()

    def get_running_task(self) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM task_info WHERE status = 'RUNNING' ORDER BY task_start_date DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_latest_finished_task(self) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM task_info WHERE status IN ('SUCCESS', 'FAILED', 'TERMINATED') "
                "ORDER BY task_end_date DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def set_total_items(self, task_id: str, total: int) -> None:
        conn = self._connect()
        try:
            conn.execute(
                'UPDATE task_info SET total_items = ? WHERE task_id = ?',
                (total, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def increment_processed_items(self, task_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                'UPDATE task_info SET processed_items = processed_items + 1 WHERE task_id = ?',
                (task_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def set_processed_items(self, task_id: str, processed: int) -> None:
        conn = self._connect()
        try:
            conn.execute(
                'UPDATE task_info SET processed_items = ? WHERE task_id = ?',
                (processed, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_current_label(self, task_id: str, label: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                'UPDATE task_info SET current_label = ? WHERE task_id = ?',
                (label, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def finalize_task_success_if_running(self, task_id: str, task_end_date: str) -> bool:
        conn = self._connect()
        try:
            updated = conn.execute(
                '''UPDATE task_info
                   SET status        = 'SUCCESS',
                       task_end_date = ?,
                       current_label = ''
                   WHERE task_id = ?
                     AND status = 'RUNNING' ''',
                (task_end_date, task_id),
            ).rowcount
            conn.commit()
            return bool(updated)
        finally:
            conn.close()

    def mark_task_failed(self, task_id: str, task_end_date: str, error_message: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                '''UPDATE task_info
                   SET status        = 'FAILED',
                       task_end_date = ?,
                       error_message = ?
                   WHERE task_id = ?''',
                (task_end_date, error_message, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def is_task_terminated(self, task_id: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT status FROM task_info WHERE task_id = ?',
                (task_id,),
            ).fetchone()
            return bool(row and row['status'] == 'TERMINATED')
        finally:
            conn.close()

    def get_data_range_meta(self) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM data_range_meta WHERE dataset = 'day_level_trade_data'"
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM data_range_meta WHERE dataset = 'daily_price'"
                ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
