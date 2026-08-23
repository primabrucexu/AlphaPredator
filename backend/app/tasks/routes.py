from __future__ import annotations

from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.models import JygsCredential
from app.database.session import get_session

from .handlers.jygs import TASK_TYPE as JYGS_TASK_TYPE
from .handlers.stock_directory import TASK_TYPE as STOCK_DIRECTORY_TASK_TYPE
from .models import SchedulingPolicy, Task, TaskItem
from .process import start_worker_process
from .schemas import ActiveTaskCount, JygsLimitUpTaskCreate, TaskItemPage, TaskItemRead, TaskPage, TaskRead
from .service import (
    active_task_count,
    create_task,
    get_active_task_by_type,
    get_task,
    list_task_items,
    list_tasks,
    load_json,
    request_cancel,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])
_creation_lock = Lock()


def task_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        task_type=task.task_type,
        scheduling_policy=task.scheduling_policy,
        title=task.title,
        status=task.status,
        total_items=task.total_items,
        completed_items=task.completed_items,
        failed_items=task.failed_items,
        progress=task.progress,
        status_message=task.status_message,
        input=load_json(task.input_json),
        result=load_json(task.result_json),
        error=task.error,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        updated_at=task.updated_at,
        cancel_requested_at=task.cancel_requested_at,
    )


def task_item_read(item: TaskItem) -> TaskItemRead:
    return TaskItemRead(
        id=item.id,
        task_id=item.task_id,
        sequence=item.sequence,
        title=item.title,
        status=item.status,
        current=item.current,
        total=item.total,
        progress=item.progress,
        status_message=item.status_message,
        result=load_json(item.result_json),
        error=item.error,
        started_at=item.started_at,
        finished_at=item.finished_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=TaskPage)
def task_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    task_type: str | None = None,
    db: Session = Depends(get_session),
):
    tasks, total = list_tasks(db, page=page, page_size=page_size, status=status, task_type=task_type)
    return TaskPage(items=[task_read(task) for task in tasks], total=total, page=page, page_size=page_size)


@router.get("/active-count", response_model=ActiveTaskCount)
def task_active_count(db: Session = Depends(get_session)):
    return ActiveTaskCount(count=active_task_count(db))


def _raise_if_active_task_exists(db: Session, task_type: str) -> None:
    existing = get_active_task_by_type(db, task_type)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"message": "同类型任务正在等待或执行", "existing_task_id": existing.id},
        )


def _create_update_task(
    db: Session,
    *,
    task_type: str,
    title: str,
    input: dict | None = None,
) -> Task:
    with _creation_lock:
        _raise_if_active_task_exists(db, task_type)
        return create_task(
            db,
            task_type=task_type,
            scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
            title=title,
            input=input,
            start_worker=start_worker_process,
        )


@router.post(
    "/jygs-limit-up-sync",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_jygs_limit_up_task(
    payload: JygsLimitUpTaskCreate,
    db: Session = Depends(get_session),
):
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "结束日期不能早于开始日期")
    _raise_if_active_task_exists(db, JYGS_TASK_TYPE)
    if db.get(JygsCredential, 1) is None:
        raise HTTPException(400, "尚未配置韭研公社 SESSION")
    task = _create_update_task(
        db,
        task_type=JYGS_TASK_TYPE,
        title=f"同步韭研涨停数据 {payload.start_date} 至 {payload.end_date}",
        input={
            "start_date": payload.start_date.isoformat(),
            "end_date": payload.end_date.isoformat(),
        },
    )
    return task_read(task)


@router.post(
    "/stock-directory-refresh",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_stock_directory_task(db: Session = Depends(get_session)):
    return task_read(_create_update_task(
        db,
        task_type=STOCK_DIRECTORY_TASK_TYPE,
        title="刷新股票搜索目录",
    ))


@router.get("/{task_id}", response_model=TaskRead)
def task_detail(task_id: int, db: Session = Depends(get_session)):
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task_read(task)


@router.get("/{task_id}/items", response_model=TaskItemPage)
def task_items(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_session),
):
    if get_task(db, task_id) is None:
        raise HTTPException(404, "任务不存在")
    items, total = list_task_items(db, task_id, page=page, page_size=page_size)
    return TaskItemPage(items=[task_item_read(item) for item in items], total=total, page=page, page_size=page_size)


@router.post("/{task_id}/cancel", response_model=TaskRead)
def cancel_task(task_id: int, db: Session = Depends(get_session)):
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task_read(request_cancel(db, task))
