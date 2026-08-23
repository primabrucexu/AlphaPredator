from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Task, TaskItem, TaskStatus


class TaskCancelled(Exception):
    pass


class TaskContext:
    def __init__(self, db: Session, task: Task, item: TaskItem | None = None):
        self.db = db
        self.task = task
        self.item = item

    def check_cancelled(self) -> None:
        self.db.refresh(self.task)
        if self.task.status == TaskStatus.CANCEL_REQUESTED.value:
            raise TaskCancelled()

    def report_progress(
        self,
        current: int,
        total: int | None,
        message: str = "",
    ) -> None:
        self.check_cancelled()
        target = self.item or self.task
        if total is None or total <= 0:
            progress = None
        else:
            progress = min(100, max(0, round(current * 100 / total)))
        previous = target.progress
        if previous is not None and progress is not None:
            progress = max(previous, progress)
        target.progress = progress
        target.status_message = message
        if self.item is not None:
            self.item.current = current
            self.item.total = total
            self.db.flush()
            progresses = list(self.db.scalars(
                select(TaskItem.progress).where(TaskItem.task_id == self.task.id)
            ).all())
            self.task.progress = round(sum(value or 0 for value in progresses) / len(progresses))
            self.task.status_message = message
        self.db.commit()
