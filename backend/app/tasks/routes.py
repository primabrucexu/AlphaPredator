from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.session import get_session

from .handlers.market_daily_bars import TASK_TYPE as MARKET_DAILY_BARS_TASK_TYPE
from .models import (
    ModeScreeningStockResult,
    Task,
    TaskItem,
    TaskItemStatus,
)
from .operations import (
    TaskOperationConflict,
    TaskOperationError,
    create_individual_backtest_task as create_individual_backtest,
    create_market_daily_bars_update_task as create_market_daily_bars_update,
    create_mode_screening_analysis_task as create_mode_screening_analysis,
    create_screening_rule_task as create_screening_rule,
    create_stock_directory_refresh_task as create_stock_directory_refresh,
    list_mode_screening_results,
    list_mode_screening_trades,
    market_target_end_date as _market_target_end_date,
    retry_failed_market_daily_bars_task as retry_failed_market_daily_bars,
)
from .process import start_worker_process
from .schemas import (
    ActiveTaskCount,
    IndividualBacktestTaskCreate,
    MarketDailyBarsCoverage,
    MarketDailyBarsTaskCreate,
    ModeScreeningSaleResultRead,
    ModeScreeningStockResultPage,
    ModeScreeningStockResultRead,
    ModeScreeningTradeResultPage,
    ModeScreeningTradeResultRead,
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


def _utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
        created_at=_utc_timestamp(task.created_at),
        started_at=_utc_timestamp(task.started_at),
        finished_at=_utc_timestamp(task.finished_at),
        updated_at=_utc_timestamp(task.updated_at),
        cancel_requested_at=_utc_timestamp(task.cancel_requested_at),
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
        started_at=_utc_timestamp(item.started_at),
        finished_at=_utc_timestamp(item.finished_at),
        updated_at=_utc_timestamp(item.updated_at),
    )


def _load_json_value(value: str, fallback):
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def mode_screening_stock_read(result: ModeScreeningStockResult) -> ModeScreeningStockResultRead:
    evidence = _load_json_value(result.evidence_json, [])
    metrics = _load_json_value(result.metrics_json, {})
    open_trade = _load_json_value(result.open_trade_json, None)
    pending_orders = _load_json_value(result.pending_orders_json, [])
    return ModeScreeningStockResultRead(
        id=result.id,
        symbol=result.symbol,
        code=result.code,
        name=result.name,
        as_of_date=result.as_of_date,
        data_start_date=result.data_start_date,
        data_end_date=result.data_end_date,
        signal_date=result.signal_date,
        insufficient_history=result.insufficient_history,
        evidence=evidence if isinstance(evidence, list) else [],
        metrics=metrics if isinstance(metrics, dict) else {},
        backtest_status=result.backtest_status,
        current_state=result.current_state,
        completed_trades=result.completed_trades,
        winning_trades=result.winning_trades,
        losing_trades=result.losing_trades,
        flat_trades=result.flat_trades,
        win_rate=result.win_rate,
        average_return=result.average_return,
        maximum_return=result.maximum_return,
        minimum_return=result.minimum_return,
        open_trade=open_trade if isinstance(open_trade, dict) else None,
        pending_orders=pending_orders if isinstance(pending_orders, list) else [],
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
    "/mode-screening-analysis",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_mode_screening_task(
    payload: ScreeningRuleTaskCreate,
    db: Session = Depends(get_session),
):
    try:
        return task_read(create_mode_screening_analysis(
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


@router.get(
    "/{task_id}/mode-screening-results",
    response_model=ModeScreeningStockResultPage,
)
def mode_screening_results(
    task_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Literal["win_rate", "average_return", "maximum_return"] | None = None,
    sort_order: Literal["asc", "desc"] | None = None,
    current_state: list[Literal[
        "pending_entry", "bought_today", "holding", "take_profit", "pending_exit"
    ]] | None = Query(None),
    db: Session = Depends(get_session),
):
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    try:
        rows, total = list_mode_screening_results(
            db,
            task,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            current_states=current_state,
        )
    except TaskOperationError as exc:
        _raise_operation_error(exc)
    return ModeScreeningStockResultPage(
        items=[mode_screening_stock_read(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{task_id}/mode-screening-results/{result_id}/trades",
    response_model=ModeScreeningTradeResultPage,
)
def mode_screening_trades(
    task_id: int,
    result_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_session),
):
    stock_result = db.get(ModeScreeningStockResult, result_id)
    if stock_result is None or stock_result.task_id != task_id:
        raise HTTPException(404, "命中股票结果不存在")
    trades, total, raw_sales_by_trade = list_mode_screening_trades(
        db, stock_result, page=page, page_size=page_size,
    )
    sales_by_trade = {
        trade_id: [ModeScreeningSaleResultRead(
            date=sale.trade_date,
            reason_id=sale.reason_id,
            price=sale.price,
            fraction_of_original=sale.fraction_of_original,
            return_rate=sale.return_rate,
        ) for sale in sales]
        for trade_id, sales in raw_sales_by_trade.items()
    }
    return ModeScreeningTradeResultPage(
        items=[ModeScreeningTradeResultRead(
            id=trade.id,
            sequence=trade.sequence,
            signal_date=trade.signal_date,
            buy_date=trade.buy_date,
            buy_price=trade.buy_price,
            realized_return=trade.realized_return,
            sells=sales_by_trade.get(trade.id, []),
        ) for trade in trades],
        total=total,
        page=page,
        page_size=page_size,
    )


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
