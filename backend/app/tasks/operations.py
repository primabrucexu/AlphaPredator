from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Stock
from app.market_data.provider.base import normalize_symbol

from .handlers.individual_backtest import TASK_TYPE as INDIVIDUAL_BACKTEST_TASK_TYPE
from .handlers.market_daily_bars import TASK_TYPE as MARKET_DAILY_BARS_TASK_TYPE
from .handlers.mode_screening import TASK_TYPE as MODE_SCREENING_TASK_TYPE
from .handlers.screening import TASK_TYPE as SCREENING_RULE_TASK_TYPE
from .handlers.stock_directory import TASK_TYPE as STOCK_DIRECTORY_TASK_TYPE
from .models import SchedulingPolicy, Task, TaskItem, TaskItemStatus, TaskStatus
from .process import start_worker_process
from .service import TaskPlanningError, create_task, get_active_task_by_type, load_json


_creation_lock = Lock()
_shanghai_timezone = ZoneInfo("Asia/Shanghai")
_same_day_cutoff = time(15, 45)


class TaskOperationError(ValueError):
    pass


class TaskOperationConflict(TaskOperationError):
    def __init__(self, existing_task: Task):
        super().__init__("同类型任务正在等待或执行")
        self.existing_task = existing_task


def _create_compute_task(
    db: Session,
    *,
    task_type: str,
    title: str,
    input: dict,
    start_worker: Callable[[], None] = start_worker_process,
) -> Task:
    try:
        return create_task(
            db,
            task_type=task_type,
            scheduling_policy=SchedulingPolicy.COMPUTE,
            title=title,
            input=input,
            start_worker=start_worker,
        )
    except TaskPlanningError as exc:
        raise TaskOperationError(str(exc)) from exc


def create_screening_rule_task(
    db: Session,
    *,
    rule_id: str,
    rule_revision: int,
    parameters: dict,
    as_of_date: date,
    symbols: list[str] | None = None,
    start_worker: Callable[[], None] = start_worker_process,
) -> Task:
    normalized_symbols = None
    if symbols is not None:
        try:
            normalized_symbols = sorted({normalize_symbol(symbol) for symbol in symbols})
        except ValueError as exc:
            raise TaskOperationError(str(exc)) from exc
    task_input = {
        "rule_id": rule_id,
        "rule_revision": rule_revision,
        "parameters": parameters,
        "as_of_date": as_of_date.isoformat(),
    }
    if normalized_symbols is not None:
        task_input["symbols"] = normalized_symbols
    return _create_compute_task(
        db,
        task_type=SCREENING_RULE_TASK_TYPE,
        title=f"执行选股规则 {rule_id} v{rule_revision}（{as_of_date.isoformat()}）",
        input=task_input,
        start_worker=start_worker,
    )


def create_individual_backtest_task(
    db: Session,
    *,
    rule_id: str,
    rule_revision: int,
    parameters: dict,
    symbol: str,
    start_date: date,
    end_date: date,
    start_worker: Callable[[], None] = start_worker_process,
) -> Task:
    try:
        normalized_symbol = normalize_symbol(symbol)
    except ValueError as exc:
        raise TaskOperationError(str(exc)) from exc
    return _create_compute_task(
        db,
        task_type=INDIVIDUAL_BACKTEST_TASK_TYPE,
        title=f"个股回测 {rule_id} v{rule_revision}：{normalized_symbol}",
        input={
            "rule_id": rule_id,
            "rule_revision": rule_revision,
            "parameters": parameters,
            "symbol": normalized_symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        start_worker=start_worker,
    )


def create_mode_screening_analysis_task(
    db: Session,
    *,
    rule_id: str,
    rule_revision: int,
    parameters: dict,
    as_of_date: date,
    symbols: list[str] | None = None,
    start_worker: Callable[[], None] = start_worker_process,
) -> Task:
    normalized_symbols = None
    if symbols is not None:
        try:
            normalized_symbols = sorted({normalize_symbol(symbol) for symbol in symbols})
        except ValueError as exc:
            raise TaskOperationError(str(exc)) from exc
    task_input = {
        "rule_id": rule_id,
        "rule_revision": rule_revision,
        "parameters": parameters,
        "as_of_date": as_of_date.isoformat(),
    }
    if normalized_symbols is not None:
        task_input["symbols"] = normalized_symbols
    return _create_compute_task(
        db,
        task_type=MODE_SCREENING_TASK_TYPE,
        title=f"模式选股分析 {rule_id} v{rule_revision}（{as_of_date.isoformat()}）",
        input=task_input,
        start_worker=start_worker,
    )


def market_target_end_date(now: datetime | None = None) -> date:
    local_now = now.astimezone(_shanghai_timezone) if now is not None else datetime.now(_shanghai_timezone)
    if local_now.time() > _same_day_cutoff:
        return local_now.date()
    return local_now.date() - timedelta(days=1)


def _create_update_task(
    db: Session,
    *,
    task_type: str,
    title: str,
    input: dict | None = None,
    start_worker: Callable[[], None] = start_worker_process,
) -> Task:
    with _creation_lock:
        existing = get_active_task_by_type(db, task_type)
        if existing is not None:
            raise TaskOperationConflict(existing)
        try:
            return create_task(
                db,
                task_type=task_type,
                scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title=title,
                input=input,
                start_worker=start_worker,
            )
        except TaskPlanningError as exc:
            raise TaskOperationError(str(exc)) from exc


def create_stock_directory_refresh_task(
    db: Session,
    *,
    start_worker: Callable[[], None] = start_worker_process,
) -> Task:
    return _create_update_task(
        db,
        task_type=STOCK_DIRECTORY_TASK_TYPE,
        title="刷新股票搜索目录",
        start_worker=start_worker,
    )


def create_market_daily_bars_update_task(
    db: Session,
    mode: str,
    *,
    start_worker: Callable[[], None] = start_worker_process,
    now: datetime | None = None,
) -> Task:
    if mode not in {"incremental", "full"}:
        raise TaskOperationError("mode 必须是 incremental 或 full")
    if db.scalar(select(Stock.symbol).limit(1)) is None:
        raise TaskOperationError("本地股票目录为空，请先刷新股票搜索目录")
    target_end_date = market_target_end_date(now).isoformat()
    title = "自动增量更新股票日线" if mode == "incremental" else "强制全量更新股票日线"
    return _create_update_task(
        db,
        task_type=MARKET_DAILY_BARS_TASK_TYPE,
        title=f"{title}（截至 {target_end_date}）",
        input={"mode": mode, "target_end_date": target_end_date},
        start_worker=start_worker,
    )


def retry_failed_market_daily_bars_task(
    db: Session,
    original: Task,
    *,
    start_worker: Callable[[], None] = start_worker_process,
) -> Task:
    if original.task_type != MARKET_DAILY_BARS_TASK_TYPE:
        raise TaskOperationError("该任务不支持失败股票重试")
    if original.status != TaskStatus.PARTIALLY_SUCCEEDED.value:
        raise TaskOperationError("只有部分成功的行情任务可以重试失败股票")
    failed_items = list(db.scalars(select(TaskItem).where(
        TaskItem.task_id == original.id,
        TaskItem.status == TaskItemStatus.FAILED.value,
    ).order_by(TaskItem.sequence)).all())
    symbols = [str(load_json(item.input_json).get("symbol") or "") for item in failed_items]
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols:
        raise TaskOperationError("原任务没有可重试的失败股票")
    original_input = load_json(original.input_json)
    return _create_update_task(
        db,
        task_type=MARKET_DAILY_BARS_TASK_TYPE,
        title=f"重试任务 {original.uuid} 的失败股票",
        input={
            "mode": original_input["mode"],
            "target_end_date": original_input["target_end_date"],
            "symbols": symbols,
            "retry_of_task_id": original.id,
        },
        start_worker=start_worker,
    )
