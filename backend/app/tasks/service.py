from __future__ import annotations

import json
from typing import Any, Callable

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .handlers import TaskItemSpec, get_handler
from .models import SchedulingPolicy, Task, TaskItem, TaskItemStatus, TaskStatus, utc_now
from .process import start_worker_process


TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED.value,
    TaskStatus.PARTIALLY_SUCCEEDED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}
ACTIVE_TASK_STATUSES = {
    TaskStatus.PENDING.value,
    TaskStatus.RUNNING.value,
    TaskStatus.CANCEL_REQUESTED.value,
}


class TaskPlanningError(ValueError):
    pass


def _dump(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, allow_nan=False)


def _build_item_specs(task_type: str, task_input: dict[str, Any]) -> list[TaskItemSpec]:
    handler = get_handler(task_type)
    if handler is None:
        raise TaskPlanningError(f"未注册任务处理器：{task_type}")
    try:
        specs = list(handler.build_items(task_input))
    except Exception as exc:
        raise TaskPlanningError(f"任务子任务规划失败：{exc}") from exc
    if not specs:
        raise TaskPlanningError("任务至少需要一个子任务")
    for spec in specs:
        if not isinstance(spec, TaskItemSpec):
            raise TaskPlanningError("build_items() 必须返回 TaskItemSpec")
        if not spec.title.strip():
            raise TaskPlanningError("子任务标题不能为空")
        if not isinstance(spec.input, dict):
            raise TaskPlanningError(f"子任务“{spec.title}”的输入必须是 JSON 对象")
        try:
            _dump(spec.input)
        except (TypeError, ValueError) as exc:
            raise TaskPlanningError(f"子任务“{spec.title}”的输入无法序列化为 JSON") from exc
    return specs


def load_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def create_task(
    db: Session,
    *,
    task_type: str,
    scheduling_policy: SchedulingPolicy,
    title: str,
    input: dict[str, Any] | None = None,
    start_worker: Callable[[], None] = start_worker_process,
) -> Task:
    if input is not None and not isinstance(input, dict):
        raise TaskPlanningError("总任务输入必须是 JSON 对象")
    task_input = input or {}
    try:
        input_json = _dump(task_input)
    except (TypeError, ValueError) as exc:
        raise TaskPlanningError("总任务输入无法序列化为 JSON") from exc
    specs = _build_item_specs(task_type, task_input)
    task = Task(
        task_type=task_type,
        scheduling_policy=scheduling_policy.value,
        title=title,
        total_items=len(specs),
        input_json=input_json,
    )
    try:
        db.add(task)
        db.flush()
        for sequence, spec in enumerate(specs):
            db.add(TaskItem(
                task_id=task.id,
                sequence=sequence,
                title=spec.title,
                total=spec.total,
                input_json=_dump(spec.input),
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(task)
    start_worker()
    return task


def get_task(db: Session, task_id: int) -> Task | None:
    return db.get(Task, task_id)


def list_tasks(
    db: Session,
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    task_type: str | None = None,
) -> tuple[list[Task], int]:
    filters = []
    if status:
        filters.append(Task.status == status)
    if task_type:
        filters.append(Task.task_type == task_type)
    total = db.scalar(select(func.count()).select_from(Task).where(*filters)) or 0
    rows = list(db.scalars(
        select(Task).where(*filters).order_by(Task.created_at.desc(), Task.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all())
    return rows, total


def list_task_items(db: Session, task_id: int, *, page: int, page_size: int) -> tuple[list[TaskItem], int]:
    total = db.scalar(select(func.count()).select_from(TaskItem).where(TaskItem.task_id == task_id)) or 0
    rows = list(db.scalars(
        select(TaskItem).where(TaskItem.task_id == task_id).order_by(TaskItem.sequence)
        .offset((page - 1) * page_size).limit(page_size)
    ).all())
    return rows, total


def active_task_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Task).where(Task.status.in_(ACTIVE_TASK_STATUSES))) or 0


def get_active_task_by_type(db: Session, task_type: str) -> Task | None:
    return db.scalar(
        select(Task).where(
            Task.task_type == task_type,
            Task.status.in_(ACTIVE_TASK_STATUSES),
        ).order_by(Task.created_at, Task.id).limit(1)
    )


def request_cancel(db: Session, task: Task) -> Task:
    if task.status in TERMINAL_TASK_STATUSES:
        return task
    now = utc_now()
    task.cancel_requested_at = task.cancel_requested_at or now
    if task.status == TaskStatus.PENDING.value:
        task.status = TaskStatus.CANCELLED.value
        task.finished_at = now
        task.status_message = "任务已取消"
        for item in db.scalars(select(TaskItem).where(TaskItem.task_id == task.id)).all():
            if item.status == TaskItemStatus.PENDING.value:
                item.status = TaskItemStatus.CANCELLED.value
                item.finished_at = now
    else:
        task.status = TaskStatus.CANCEL_REQUESTED.value
        task.status_message = "正在取消"
    db.commit()
    db.refresh(task)
    return task


def next_pending_task(db: Session) -> Task | None:
    priority = case(
        (Task.scheduling_policy == SchedulingPolicy.EXCLUSIVE_UPDATE.value, 0),
        else_=1,
    )
    return db.scalar(
        select(Task).where(Task.status == TaskStatus.PENDING.value)
        .order_by(priority, Task.created_at, Task.id).limit(1)
    )
