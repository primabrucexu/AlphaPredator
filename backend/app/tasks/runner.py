from __future__ import annotations

import json
import logging
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import timedelta
from threading import Event, Thread
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from .context import TaskCancelled, TaskContext
from .handlers import TaskItemSkipped, get_handler
from .models import (
    SchedulingPolicy,
    Task,
    TaskItem,
    TaskItemStatus,
    TaskStatus,
    TaskWorkerLease,
    utc_now,
)
from .service import next_pending_task


logger = logging.getLogger(__name__)


def _dump(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def acquire_worker_lease(
    session_factory: sessionmaker[Session],
    owner_id: str,
    *,
    stale_after_seconds: int = 15,
) -> bool:
    now = utc_now()
    cutoff = now - timedelta(seconds=stale_after_seconds)
    with session_factory() as db:
        result = db.execute(
            update(TaskWorkerLease)
            .where(TaskWorkerLease.id == 1)
            .where(or_(
                TaskWorkerLease.owner_id == "",
                TaskWorkerLease.owner_id == owner_id,
                TaskWorkerLease.heartbeat_at.is_(None),
                TaskWorkerLease.heartbeat_at < cutoff,
            ))
            .values(owner_id=owner_id, acquired_at=now, heartbeat_at=now)
        )
        db.commit()
        return result.rowcount == 1


def refresh_worker_lease(session_factory: sessionmaker[Session], owner_id: str) -> bool:
    with session_factory() as db:
        result = db.execute(
            update(TaskWorkerLease)
            .where(TaskWorkerLease.id == 1, TaskWorkerLease.owner_id == owner_id)
            .values(heartbeat_at=utc_now())
        )
        db.commit()
        return result.rowcount == 1


def release_worker_lease(session_factory: sessionmaker[Session], owner_id: str) -> None:
    with session_factory() as db:
        db.execute(
            update(TaskWorkerLease)
            .where(TaskWorkerLease.id == 1, TaskWorkerLease.owner_id == owner_id)
            .values(owner_id="", acquired_at=None, heartbeat_at=None)
        )
        db.commit()


def start_lease_heartbeat(
    session_factory: sessionmaker[Session],
    owner_id: str,
    stop: Event,
    *,
    interval_seconds: float = 5,
) -> Thread:
    def heartbeat() -> None:
        while not stop.wait(interval_seconds):
            if not refresh_worker_lease(session_factory, owner_id):
                logger.error("任务 Worker 已失去单实例租约")
                stop.set()
                return

    thread = Thread(target=heartbeat, name="task-worker-heartbeat", daemon=True)
    thread.start()
    return thread


def recover_interrupted_tasks(db: Session) -> int:
    tasks = list(db.scalars(select(Task).where(Task.status.in_((
        TaskStatus.RUNNING.value,
        TaskStatus.CANCEL_REQUESTED.value,
    )))).all())
    now = utc_now()
    for task in tasks:
        task.status = TaskStatus.FAILED.value
        task.error = "Worker 异常中断，任务未自动恢复"
        task.status_message = "任务异常中断"
        task.finished_at = now
        items = db.scalars(select(TaskItem).where(TaskItem.task_id == task.id)).all()
        for item in items:
            if item.status == TaskItemStatus.RUNNING.value:
                item.status = TaskItemStatus.FAILED.value
                item.error = "Worker 异常中断"
                item.finished_at = now
            elif item.status == TaskItemStatus.PENDING.value:
                item.status = TaskItemStatus.SKIPPED.value
                item.finished_at = now
    db.commit()
    return len(tasks)


def _mark_remaining_cancelled(db: Session, task_id: int) -> None:
    now = utc_now()
    for item in db.scalars(select(TaskItem).where(
        TaskItem.task_id == task_id,
        TaskItem.status == TaskItemStatus.PENDING.value,
    )).all():
        item.status = TaskItemStatus.CANCELLED.value
        item.finished_at = now
    db.commit()


def _update_task_counts(db: Session, task: Task) -> list[TaskItem]:
    items = list(db.scalars(
        select(TaskItem).where(TaskItem.task_id == task.id).order_by(TaskItem.sequence)
    ).all())
    task.completed_items = sum(item.status == TaskItemStatus.SUCCEEDED.value for item in items)
    task.failed_items = sum(item.status == TaskItemStatus.FAILED.value for item in items)
    if items:
        task.progress = round(sum(item.progress or 0 for item in items) / len(items))
    return items


def _finish_from_items(db: Session, task: Task, handler: Any) -> None:
    items = _update_task_counts(db, task)
    statuses = {item.status for item in items}
    failure_errors = [item.error for item in items if item.status == TaskItemStatus.FAILED.value and item.error]
    if task.status == TaskStatus.CANCEL_REQUESTED.value or TaskItemStatus.CANCELLED.value in statuses:
        task.status = TaskStatus.CANCELLED.value
        task.status_message = "任务已取消"
    elif statuses <= {TaskItemStatus.SUCCEEDED.value, TaskItemStatus.SKIPPED.value}:
        task.status = TaskStatus.SUCCEEDED.value
        task.progress = 100
        task.status_message = (
            "任务已完成" if TaskItemStatus.SUCCEEDED.value in statuses else "任务无需执行"
        )
    elif TaskItemStatus.FAILED.value in statuses and statuses & {
        TaskItemStatus.SUCCEEDED.value,
        TaskItemStatus.SKIPPED.value,
    }:
        task.status = TaskStatus.PARTIALLY_SUCCEEDED.value
        task.status_message = "任务部分成功"
        task.error = task.error or (failure_errors[0] if failure_errors else "部分子任务执行失败")
    else:
        task.status = TaskStatus.FAILED.value
        task.status_message = "任务执行失败"
        task.error = task.error or (failure_errors[0] if failure_errors else "所有子任务均未成功")
    try:
        task.result_json = _dump(handler.summarize(task, items))
    except Exception as exc:
        logger.exception("任务 %s 结果汇总失败", task.id)
        summary_error = f"任务结果汇总失败：{exc}"
        task.error = f"{task.error}；{summary_error}" if task.error else summary_error
        if task.status != TaskStatus.CANCELLED.value:
            task.status = TaskStatus.FAILED.value
            task.status_message = "任务结果汇总失败"
    task.finished_at = utc_now()
    db.commit()


def _run_item(db: Session, task: Task, item: TaskItem, handler: Any) -> None:
    db.refresh(task)
    if task.status == TaskStatus.CANCEL_REQUESTED.value:
        item.status = TaskItemStatus.CANCELLED.value
        item.status_message = "子任务已取消"
        item.finished_at = utc_now()
        db.commit()
        return
    item.status = TaskItemStatus.RUNNING.value
    item.started_at = utc_now()
    item.status_message = "子任务执行中"
    db.commit()
    context = TaskContext(db, task, item)
    try:
        result = handler.run_item(task, item, context)
        context.check_cancelled()
        item.result_json = _dump(result)
        item.progress = 100
        item.current = item.total if item.total is not None else item.current
        item.status = TaskItemStatus.SUCCEEDED.value
        item.status_message = "子任务已完成"
    except TaskItemSkipped as exc:
        item.result_json = _dump(exc.result)
        item.progress = 100
        item.current = item.total if item.total is not None else item.current
        item.status = TaskItemStatus.SKIPPED.value
        item.status_message = exc.message
    except TaskCancelled:
        item.status = TaskItemStatus.CANCELLED.value
        item.status_message = "子任务已取消"
    except Exception as exc:
        task_id, item_id = task.id, item.id
        logger.exception("任务 %s 的子任务 %s 执行失败", task_id, item_id)
        db.rollback()
        task = db.get(Task, task_id)
        item = db.get(TaskItem, item_id)
        item.status = TaskItemStatus.FAILED.value
        item.status_message = "子任务执行失败"
        item.error = str(exc)
    item.finished_at = utc_now()
    db.commit()


def _run_item_in_session(
    session_factory: sessionmaker[Session],
    handler: Any,
    task_id: int,
    item_id: int,
) -> None:
    with session_factory() as db:
        task = db.get(Task, task_id)
        item = db.get(TaskItem, item_id)
        if task is None or item is None or item.status != TaskItemStatus.PENDING.value:
            return
        _run_item(db, task, item, handler)


def _run_items_serial(db: Session, task: Task, items: list[TaskItem], handler: Any) -> None:
    for item in items:
        db.refresh(task)
        if task.status == TaskStatus.CANCEL_REQUESTED.value:
            _mark_remaining_cancelled(db, task.id)
            break
        if item.status != TaskItemStatus.PENDING.value:
            continue
        _run_item(db, task, item, handler)
        _update_task_counts(db, task)
        db.commit()
        if item.status == TaskItemStatus.CANCELLED.value:
            _mark_remaining_cancelled(db, task.id)
            break


def _run_items_parallel(
    db: Session,
    session_factory: sessionmaker[Session],
    task: Task,
    items: list[TaskItem],
    handler: Any,
    parallelism: int,
) -> None:
    pending_ids = [item.id for item in items if item.status == TaskItemStatus.PENDING.value]
    running: dict[Future[None], int] = {}

    with ThreadPoolExecutor(max_workers=parallelism, thread_name_prefix="compute-item") as executor:
        while pending_ids or running:
            db.expire_all()
            current_task = db.get(Task, task.id)
            cancelled = current_task.status == TaskStatus.CANCEL_REQUESTED.value
            if cancelled:
                _mark_remaining_cancelled(db, task.id)
                pending_ids.clear()
            else:
                while pending_ids and len(running) < parallelism:
                    item_id = pending_ids.pop(0)
                    future = executor.submit(
                        _run_item_in_session,
                        session_factory,
                        handler,
                        task.id,
                        item_id,
                    )
                    running[future] = item_id
            if not running:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                item_id = running.pop(future)
                try:
                    future.result()
                except Exception as exc:
                    logger.exception("任务 %s 的并行子任务 %s 异常退出", task.id, item_id)
                    with session_factory() as item_db:
                        item = item_db.get(TaskItem, item_id)
                        if item is not None and item.status in {
                            TaskItemStatus.PENDING.value,
                            TaskItemStatus.RUNNING.value,
                        }:
                            item.status = TaskItemStatus.FAILED.value
                            item.status_message = "子任务执行失败"
                            item.error = f"并行执行器异常退出：{exc}"
                            item.finished_at = utc_now()
                            item_db.commit()
            db.expire_all()
            task = db.get(Task, task.id)
            _update_task_counts(db, task)
            db.commit()


def run_next_task(
    session_factory: sessionmaker[Session],
    *,
    compute_parallelism: int = 1,
) -> bool:
    if compute_parallelism < 1:
        raise ValueError("计算任务并行度必须大于等于 1")
    with session_factory() as db:
        task = next_pending_task(db)
        if task is None:
            return False
        handler = get_handler(task.task_type)
        task.status = TaskStatus.RUNNING.value
        task.started_at = task.started_at or utc_now()
        task.status_message = "任务执行中"
        db.commit()

        if handler is None:
            task.status = TaskStatus.FAILED.value
            task.error = f"未注册任务处理器：{task.task_type}"
            task.status_message = "任务执行失败"
            task.finished_at = utc_now()
            db.commit()
            return True

        items = list(db.scalars(
            select(TaskItem).where(TaskItem.task_id == task.id).order_by(TaskItem.sequence)
        ).all())

        if (
            task.scheduling_policy == SchedulingPolicy.COMPUTE.value
            and compute_parallelism > 1
            and len(items) > 1
        ):
            _run_items_parallel(
                db, session_factory, task, items, handler, compute_parallelism
            )
        else:
            _run_items_serial(db, task, items, handler)

        db.expire_all()
        task = db.get(Task, task.id)
        _finish_from_items(db, task, handler)
        return True
