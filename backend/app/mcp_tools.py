from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.market_data.provider.base import normalize_symbol
from app.tasks.models import Task, TaskItem
from app.tasks.operations import (
    TaskOperationConflict,
    TaskOperationError,
    create_market_daily_bars_update_task,
    create_stock_directory_refresh_task,
    retry_failed_market_daily_bars_task,
)
from app.tasks.service import get_task_by_uuid, list_task_items, load_json
from app.watchlist import service as watchlist_service


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _public_task_input(db: Session, task: Task) -> dict:
    task_input = load_json(task.input_json)
    retry_id = task_input.pop("retry_of_task_id", None)
    if isinstance(retry_id, int):
        original = db.get(Task, retry_id)
        if original is not None:
            task_input["retry_of_task_uuid"] = original.uuid
    return task_input


def _task_dict(db: Session, task: Task) -> dict:
    return {
        "uuid": task.uuid,
        "task_type": task.task_type,
        "scheduling_policy": task.scheduling_policy,
        "title": task.title,
        "status": task.status,
        "total_items": task.total_items,
        "completed_items": task.completed_items,
        "failed_items": task.failed_items,
        "progress": task.progress,
        "status_message": task.status_message,
        "input": _public_task_input(db, task),
        "result": load_json(task.result_json),
        "error": task.error,
        "created_at": _timestamp(task.created_at),
        "started_at": _timestamp(task.started_at),
        "finished_at": _timestamp(task.finished_at),
        "updated_at": _timestamp(task.updated_at),
        "cancel_requested_at": _timestamp(task.cancel_requested_at),
    }


def _task_item_dict(item: TaskItem) -> dict:
    return {
        "sequence": item.sequence,
        "title": item.title,
        "status": item.status,
        "current": item.current,
        "total": item.total,
        "progress": item.progress,
        "status_message": item.status_message,
        "result": load_json(item.result_json),
        "error": item.error,
        "started_at": _timestamp(item.started_at),
        "finished_at": _timestamp(item.finished_at),
        "updated_at": _timestamp(item.updated_at),
    }


def _watchlist_error(exc: watchlist_service.WatchlistServiceError) -> ToolError:
    return ToolError(str(exc))


def _task_error(exc: Exception) -> ToolError:
    if isinstance(exc, TaskOperationConflict):
        return ToolError(
            f"{exc}；现有任务 UUID：{exc.existing_task.uuid}"
        )
    return ToolError(str(exc))


def _task_by_uuid(db: Session, task_uuid: str) -> Task:
    try:
        task = get_task_by_uuid(db, task_uuid)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if task is None:
        raise ToolError("任务不存在")
    return task


def register_mcp_tools(mcp: FastMCP) -> None:
    @mcp.tool(description="查询全部自选股及其标签。")
    def list_watchlist() -> list[dict]:
        with SessionLocal() as db:
            return watchlist_service.list_watchlist(db)

    @mcp.tool(description="按股票代码加入自选股。")
    def add_watchlist_stock(symbol: str) -> dict:
        with SessionLocal() as db:
            try:
                return watchlist_service.add_watchlist_stock(db, symbol)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc

    @mcp.tool(description="按股票代码移出自选股，保留全局标签。")
    def remove_watchlist_stock(symbol: str) -> dict:
        with SessionLocal() as db:
            try:
                normalized = watchlist_service.remove_watchlist_stock(db, symbol)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc
            return {"success": True, "symbol": normalized}

    @mcp.tool(description="查询全部标签及每个标签的股票数量。")
    def list_tags() -> list[dict]:
        with SessionLocal() as db:
            return watchlist_service.list_tags(db)

    @mcp.tool(description="创建一个全局自选股标签。")
    def create_tag(name: str) -> dict:
        with SessionLocal() as db:
            try:
                return watchlist_service.create_tag(db, name)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc

    @mcp.tool(description="重命名一个全局自选股标签。")
    def rename_tag(tag_id: int, name: str) -> dict:
        with SessionLocal() as db:
            try:
                return watchlist_service.rename_tag(db, tag_id, name)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc

    @mcp.tool(description="删除一个全局标签及其股票关联，但保留自选股。")
    def delete_tag(tag_id: int) -> dict:
        with SessionLocal() as db:
            try:
                watchlist_service.delete_tag(db, tag_id)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc
            return {"success": True, "tag_id": tag_id}

    @mcp.tool(description="把已有标签关联到股票；必要时自动把股票加入自选。")
    def attach_tag_to_stock(symbol: str, tag_id: int) -> dict:
        with SessionLocal() as db:
            try:
                tag = watchlist_service.attach_tag_to_stock(db, symbol, tag_id)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc
            return {"success": True, "symbol": normalize_symbol(symbol), "tag": tag}

    @mcp.tool(description="解除股票与标签的关联，保留股票和全局标签。")
    def detach_tag_from_stock(symbol: str, tag_id: int) -> dict:
        with SessionLocal() as db:
            try:
                watchlist_service.detach_tag_from_stock(db, symbol, tag_id)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc
            return {"success": True, "symbol": normalize_symbol(symbol), "tag_id": tag_id}

    @mcp.tool(description="使用包含全部标签且不重复的 ID 列表更新标签顺序。")
    def reorder_tags(tag_ids: list[int]) -> dict:
        with SessionLocal() as db:
            try:
                ordered = watchlist_service.reorder_tags(db, tag_ids)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc
            return {"tag_ids": ordered}

    @mcp.tool(description="使用包含标签内全部股票且不重复的代码列表更新股票顺序。")
    def reorder_tag_stocks(tag_id: int, symbols: list[str]) -> dict:
        with SessionLocal() as db:
            try:
                ordered = watchlist_service.reorder_tag_stocks(db, tag_id, symbols)
            except watchlist_service.WatchlistServiceError as exc:
                raise _watchlist_error(exc) from exc
            return {"symbols": ordered}

    @mcp.tool(
        name="create_stock_directory_refresh_task",
        description="创建股票搜索目录刷新任务并立即返回公开 UUID。",
    )
    def create_stock_directory_refresh_task_tool() -> dict:
        with SessionLocal() as db:
            try:
                task = create_stock_directory_refresh_task(db)
            except TaskOperationError as exc:
                raise _task_error(exc) from exc
            return _task_dict(db, task)

    @mcp.tool(
        name="create_market_daily_bars_update_task",
        description="创建日线增量或强制全量更新任务并立即返回公开 UUID。",
    )
    def create_market_daily_bars_update_task_tool(
        mode: Literal["incremental", "full"],
    ) -> dict:
        with SessionLocal() as db:
            try:
                task = create_market_daily_bars_update_task(db, mode)
            except TaskOperationError as exc:
                raise _task_error(exc) from exc
            return _task_dict(db, task)

    @mcp.tool(
        name="retry_failed_market_daily_bars_task",
        description="为部分成功日线任务的失败股票创建重试任务，返回新的公开 UUID。",
    )
    def retry_failed_market_daily_bars_task_tool(task_uuid: str) -> dict:
        with SessionLocal() as db:
            original = _task_by_uuid(db, task_uuid)
            try:
                task = retry_failed_market_daily_bars_task(db, original)
            except TaskOperationError as exc:
                raise _task_error(exc) from exc
            return _task_dict(db, task)

    @mcp.tool(description="根据公开 UUID 查询任务状态、进度和任务级结果。")
    def get_task(task_uuid: str) -> dict:
        with SessionLocal() as db:
            return _task_dict(db, _task_by_uuid(db, task_uuid))

    @mcp.tool(description="根据公开 UUID 分页查询子任务状态和详细输出。")
    def get_task_output(task_uuid: str, page: int = 1, page_size: int = 50) -> dict:
        if page < 1:
            raise ToolError("page 必须大于等于 1")
        if page_size < 1 or page_size > 100:
            raise ToolError("page_size 必须在 1 到 100 之间")
        with SessionLocal() as db:
            task = _task_by_uuid(db, task_uuid)
            items, total = list_task_items(db, task.id, page=page, page_size=page_size)
            return {
                "task_uuid": task.uuid,
                "items": [_task_item_dict(item) for item in items],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
