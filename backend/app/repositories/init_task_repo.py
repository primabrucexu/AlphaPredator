from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel import select

from app.db.session import get_sqlite_session_factory
from app.models.sqlite_models import TaskInfo


class InitTaskRepo:
    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._sqlite_path = sqlite_path

    def _session_factory(self):
        return get_sqlite_session_factory(self._sqlite_path)

    @staticmethod
    def _to_dict(task: TaskInfo) -> dict[str, Any]:
        return task.model_dump()

    def _get_model(self, task_id: str) -> TaskInfo | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            return session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()

    def create_task_with_days(
            self,
            *,
            task_id: str,
            task_type: str,
            start_date: str,
            end_date: str,
            total_items: int,
    ) -> None:
        session_factory = self._session_factory()
        with session_factory() as session:
            session.add(
                TaskInfo(
                    task_id=task_id,
                    task_type=task_type,
                    start_date=start_date,
                    end_date=end_date,
                    status='PENDING',
                    total_items=total_items,
                    processed_items=0,
                    current_label='',
                    error_message='',
                    task_start_date='',
                    task_end_date='',
                )
            )
            session.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()
            return self._to_dict(task) if task else None

    def list_tasks(self, limit: int) -> list[dict[str, Any]]:
        session_factory = self._session_factory()
        with session_factory() as session:
            tasks = session.exec(
                select(TaskInfo).order_by(TaskInfo.id.desc()).limit(limit)  # type: ignore[union-attr]
            ).all()
            return [self._to_dict(task) for task in tasks]

    def get_latest_task_by_type(self, task_type: str) -> dict[str, Any] | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(
                select(TaskInfo)
                .where(TaskInfo.task_type == task_type)
                .order_by(TaskInfo.id.desc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            return self._to_dict(task) if task else None

    def get_task_status(self, task_id: str) -> str | None:
        task = self.get_task(task_id)
        return str(task['status']) if task else None

    def find_running_task_id(self) -> str | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(
                select(TaskInfo).where(TaskInfo.status == 'RUNNING').limit(1)
            ).first()
            return task.task_id if task else None

    def find_running_task_id_by_type(self, task_type: str) -> str | None:
        """Return the task_id of a RUNNING task with the given task_type, or None."""
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(
                select(TaskInfo)
                .where(TaskInfo.status == 'RUNNING', TaskInfo.task_type == task_type)
                .limit(1)
            ).first()
            return task.task_id if task else None

    def try_mark_task_running(self, task_id: str, task_start_date: str) -> bool:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()
            if not task or task.status not in {'PENDING', 'FAILED', 'TERMINATED'}:
                return False
            task.status = 'RUNNING'
            task.task_start_date = task_start_date
            session.add(task)
            session.commit()
            return True

    def reset_task_for_retry(self, task_id: str) -> None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()
            if not task:
                return
            task.status = 'PENDING'
            task.processed_items = 0
            task.current_label = ''
            task.error_message = ''
            task.task_start_date = ''
            task.task_end_date = ''
            session.add(task)
            session.commit()

    def prepare_task_for_resume(self, task_id: str, *, keep_current_label: bool) -> None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()
            if not task:
                return
            task.status = 'PENDING'
            task.error_message = ''
            task.task_end_date = ''
            if not keep_current_label:
                task.current_label = ''
            session.add(task)
            session.commit()

    def terminate_task(self, task_id: str, task_end_date: str) -> bool:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()
            if not task or task.status not in {'RUNNING', 'FAILED', 'PENDING'}:
                return False
            task.status = 'TERMINATED'
            task.task_end_date = task_end_date
            if task.error_message == '':
                task.error_message = 'Terminated by user'
            session.add(task)
            session.commit()
            return True

    def get_running_task(self) -> dict[str, Any] | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(
                select(TaskInfo)
                .where(TaskInfo.status == 'RUNNING')
                .order_by(TaskInfo.task_start_date.desc())  # type: ignore[attr-defined]
                .limit(1)
            ).first()
            return self._to_dict(task) if task else None

    def get_latest_finished_task(self) -> dict[str, Any] | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(
                select(TaskInfo)
                .where(TaskInfo.status.in_(['SUCCESS', 'FAILED', 'TERMINATED']))  # type: ignore[attr-defined]
                .order_by(TaskInfo.task_end_date.desc())  # type: ignore[attr-defined]
                .limit(1)
            ).first()
            return self._to_dict(task) if task else None

    def get_latest_successful_market_data_task(self) -> dict[str, Any] | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(
                select(TaskInfo)
                .where(TaskInfo.task_type == 'MARKET_DATA', TaskInfo.status == 'SUCCESS')
                .order_by(TaskInfo.task_end_date.desc(), TaskInfo.id.desc())  # type: ignore[union-attr]
                .limit(1)
            ).first()
            return self._to_dict(task) if task else None

    def set_total_items(self, task_id: str, total: int) -> None:
        self._update_task(task_id, total_items=total)

    def increment_processed_items(self, task_id: str) -> None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()
            if not task:
                return
            task.processed_items += 1
            session.add(task)
            session.commit()

    def set_processed_items(self, task_id: str, processed: int) -> None:
        self._update_task(task_id, processed_items=processed)

    def set_current_label(self, task_id: str, label: str) -> None:
        self._update_task(task_id, current_label=label)

    def finalize_task_success_if_running(self, task_id: str, task_end_date: str) -> bool:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()
            if not task or task.status != 'RUNNING':
                return False
            task.status = 'SUCCESS'
            task.task_end_date = task_end_date
            task.current_label = ''
            session.add(task)
            session.commit()
            return True

    def mark_task_failed(self, task_id: str, task_end_date: str, error_message: str) -> None:
        self._update_task(
            task_id,
            status='FAILED',
            task_end_date=task_end_date,
            error_message=error_message,
        )

    def is_task_terminated(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        return bool(task and task['status'] == 'TERMINATED')

    def get_market_data_range(self) -> dict[str, Any] | None:
        """Return min/max trade date from successful MARKET_DATA tasks in task_info."""
        session_factory = self._session_factory()
        with session_factory() as session:
            tasks = session.exec(
                select(TaskInfo).where(TaskInfo.task_type == 'MARKET_DATA', TaskInfo.status == 'SUCCESS')
            ).all()
            if not tasks:
                return None
            return {
                'min_trade_date': min(task.start_date for task in tasks),
                'max_trade_date': max(task.end_date for task in tasks),
            }

    def _update_task(self, task_id: str, **fields: Any) -> None:
        session_factory = self._session_factory()
        with session_factory() as session:
            task = session.exec(select(TaskInfo).where(TaskInfo.task_id == task_id)).first()
            if not task:
                return
            for key, value in fields.items():
                setattr(task, key, value)
            session.add(task)
            session.commit()
