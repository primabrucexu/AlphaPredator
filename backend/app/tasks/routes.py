from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_session

from .handlers.market_daily_bars import TASK_TYPE as MARKET_DAILY_BARS_TASK_TYPE
from .models import Task, TaskItem, TaskItemStatus
from .operations import (
    TaskOperationConflict,
    TaskOperationError,
    create_individual_backtest_task as create_individual_backtest,
    create_market_daily_bars_update_task as create_market_daily_bars_update,
    create_screening_rule_task as create_screening_rule,
    create_stock_directory_refresh_task as create_stock_directory_refresh,
    market_target_end_date as _market_target_end_date,
    retry_failed_market_daily_bars_task as retry_failed_market_daily_bars,
)
from .process import start_worker_process
from .schemas import (
    ActiveTaskCount,
    IndividualBacktestTaskCreate,
    MarketDailyBarsCoverage,
    MarketDailyBarsTaskCreate,
    ScreeningRuleTaskCreate,
    TaskItemPage,
    TaskItemRead,
    TaskPage,
    TaskRead,
)
from .service import (
    TERMINAL_TASK_STATUSES,
    active_task_count,
    get_task,
    list_task_items,
    list_tasks,
    load_json,
    request_cancel,
)


router = APIRouter(prefix="/tasks", tags=["tasks"])


def task_read(task: Task) -> TaskRead:
    return TaskRead(
        id=task.id,
        uuid=task.uuid,
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
    scheduling_policy: str | None = None,
    db: Session = Depends(get_session),
):
    tasks, total = list_tasks(
        db, page=page, page_size=page_size, status=status, task_type=task_type,
        scheduling_policy=scheduling_policy,
    )
    return TaskPage(items=[task_read(task) for task in tasks], total=total, page=page, page_size=page_size)


@router.get("/active-count", response_model=ActiveTaskCount)
def task_active_count(
    scheduling_policy: str | None = None,
    db: Session = Depends(get_session),
):
    return ActiveTaskCount(count=active_task_count(
        db, scheduling_policy=scheduling_policy,
    ))


def _raise_operation_error(exc: TaskOperationError) -> None:
    if isinstance(exc, TaskOperationConflict):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "existing_task_id": exc.existing_task.id,
                "existing_task_uuid": exc.existing_task.uuid,
            },
        ) from exc
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
    try:
        return task_read(create_stock_directory_refresh(db, start_worker=start_worker_process))
    except TaskOperationError as exc:
        _raise_operation_error(exc)


@router.post(
    "/market-daily-bars-update",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_market_daily_bars_task(
    payload: MarketDailyBarsTaskCreate,
    db: Session = Depends(get_session),
):
    try:
        return task_read(create_market_daily_bars_update(
            db,
            payload.mode,
            start_worker=start_worker_process,
        ))
    except TaskOperationError as exc:
        _raise_operation_error(exc)


@router.post(
    "/screening-rule-execute",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_screening_task(
    payload: ScreeningRuleTaskCreate,
    db: Session = Depends(get_session),
):
    try:
        return task_read(create_screening_rule(
            db,
            rule_id=payload.rule_id,
            rule_revision=payload.rule_revision,
            parameters=payload.parameters,
            as_of_date=payload.as_of_date,
            symbols=payload.symbols,
            start_worker=start_worker_process,
        ))
    except TaskOperationError as exc:
        _raise_operation_error(exc)


@router.post(
    "/individual-backtest",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_individual_backtest_task(
    payload: IndividualBacktestTaskCreate,
    db: Session = Depends(get_session),
):
    try:
        return task_read(create_individual_backtest(
            db,
            rule_id=payload.rule_id,
            rule_revision=payload.rule_revision,
            parameters=payload.parameters,
            symbol=payload.symbol,
            start_date=payload.start_date,
            end_date=payload.end_date,
            start_worker=start_worker_process,
        ))
    except TaskOperationError as exc:
        _raise_operation_error(exc)


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
    try:
        return task_read(retry_failed_market_daily_bars(
            db,
            original,
            start_worker=start_worker_process,
        ))
    except TaskOperationError as exc:
        _raise_operation_error(exc)


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
