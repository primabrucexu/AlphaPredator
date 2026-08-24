from __future__ import annotations

from datetime import date, datetime, time, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Stock
from app.database.session import get_session

from .handlers.market_daily_bars import TASK_TYPE as MARKET_DAILY_BARS_TASK_TYPE
from .handlers.stock_directory import TASK_TYPE as STOCK_DIRECTORY_TASK_TYPE
from .models import SchedulingPolicy, Task, TaskItem, TaskItemStatus, TaskStatus
from .process import start_worker_process
from .schemas import (
    ActiveTaskCount,
    MarketDailyBarsCoverage,
    MarketDailyBarsTaskCreate,
    TaskItemPage,
    TaskItemRead,
    TaskPage,
    TaskRead,
)
from .service import (
    TERMINAL_TASK_STATUSES,
    active_task_count,
    create_task,
    get_active_task_by_type,
    get_task,
    list_task_items,
    list_tasks,
    load_json,
    request_cancel,
    TaskPlanningError,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])
_creation_lock = Lock()
_shanghai_timezone = ZoneInfo("Asia/Shanghai")
_same_day_cutoff = time(15, 45)


def _market_target_end_date(now: datetime | None = None) -> date:
    local_now = now.astimezone(_shanghai_timezone) if now is not None else datetime.now(_shanghai_timezone)
    if local_now.time() > _same_day_cutoff:
        return local_now.date()
    return local_now.date() - timedelta(days=1)


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
        try:
            return create_task(
                db,
                task_type=task_type,
                scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title=title,
                input=input,
                start_worker=start_worker_process,
            )
        except TaskPlanningError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/jygs-limit-up-sync", include_in_schema=False)
def disabled_jygs_limit_up_task():
    raise HTTPException(404, "韭研同步能力已暂时停用")


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


@router.post(
    "/market-daily-bars-update",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_market_daily_bars_task(
    payload: MarketDailyBarsTaskCreate,
    db: Session = Depends(get_session),
):
    if db.scalar(select(Stock.symbol).limit(1)) is None:
        raise HTTPException(400, "本地股票目录为空，请先刷新股票搜索目录")
    target_end_date = _market_target_end_date().isoformat()
    title = "自动增量更新股票日线" if payload.mode == "incremental" else "强制全量更新股票日线"
    return task_read(_create_update_task(
        db,
        task_type=MARKET_DAILY_BARS_TASK_TYPE,
        title=f"{title}（截至 {target_end_date}）",
        input={"mode": payload.mode, "target_end_date": target_end_date},
    ))


@router.get(
    "/market-daily-bars-coverage",
    response_model=MarketDailyBarsCoverage,
)
def market_daily_bars_coverage(db: Session = Depends(get_session)):
    snapshots = db.scalars(
        select(Task).where(
            Task.task_type == MARKET_DAILY_BARS_TASK_TYPE,
            Task.result_json.contains('"data_start_date"'),
        ).order_by(Task.created_at.desc(), Task.id.desc())
    ).all()
    for snapshot in snapshots:
        result = load_json(snapshot.result_json)
        start_date = result.get("data_start_date")
        end_date = result.get("data_end_date")
        if isinstance(start_date, str) and isinstance(end_date, str):
            return MarketDailyBarsCoverage(start_date=start_date, end_date=end_date)
    first_dates: list[date] = []
    last_dates: list[date] = []
    historical_items = db.scalars(
        select(TaskItem).join(Task, Task.id == TaskItem.task_id).where(
            Task.task_type == MARKET_DAILY_BARS_TASK_TYPE,
            Task.status.in_(TERMINAL_TASK_STATUSES),
            TaskItem.status == TaskItemStatus.SUCCEEDED.value,
        )
    ).all()
    for item in historical_items:
        result = load_json(item.result_json)
        try:
            first_date = date.fromisoformat(str(result["after_first_date"]))
            last_date = date.fromisoformat(str(result["after_last_date"]))
        except (KeyError, ValueError):
            continue
        first_dates.append(first_date)
        last_dates.append(last_date)
    if first_dates and last_dates:
        return MarketDailyBarsCoverage(start_date=min(first_dates), end_date=max(last_dates))
    return MarketDailyBarsCoverage(start_date=None, end_date=None)


@router.post(
    "/{task_id}/retry-failed",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_failed_market_daily_bars_task(task_id: int, db: Session = Depends(get_session)):
    original = get_task(db, task_id)
    if original is None:
        raise HTTPException(404, "任务不存在")
    if original.task_type != MARKET_DAILY_BARS_TASK_TYPE:
        raise HTTPException(400, "该任务不支持失败股票重试")
    if original.status != TaskStatus.PARTIALLY_SUCCEEDED.value:
        raise HTTPException(400, "只有部分成功的行情任务可以重试失败股票")
    failed_items = list(db.scalars(select(TaskItem).where(
        TaskItem.task_id == task_id,
        TaskItem.status == TaskItemStatus.FAILED.value,
    ).order_by(TaskItem.sequence)).all())
    symbols = [str(load_json(item.input_json).get("symbol") or "") for item in failed_items]
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols:
        raise HTTPException(400, "原任务没有可重试的失败股票")
    original_input = load_json(original.input_json)
    return task_read(_create_update_task(
        db,
        task_type=MARKET_DAILY_BARS_TASK_TYPE,
        title=f"重试任务 #{task_id} 的失败股票",
        input={
            "mode": original_input["mode"],
            "target_end_date": original_input["target_end_date"],
            "symbols": symbols,
            "retry_of_task_id": task_id,
        },
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
