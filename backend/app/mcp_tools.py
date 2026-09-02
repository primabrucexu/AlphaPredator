from __future__ import annotations

import json
from datetime import date, datetime
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from fastmcp.utilities.types import File
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.market_data.provider.base import normalize_symbol
from app.screening.registry import rule_registry
from app.screening.sr001_report import (
    SR001ReportError,
    build_sr001_screening_report,
)
from app.screening.sr001_report_pdf import (
    SR001ReportPdfError,
    render_sr001_screening_report_pdf,
)
from app.tasks.models import Task, TaskItem
from app.tasks.operations import (
    TaskOperationConflict,
    TaskOperationError,
    create_market_daily_bars_update_task,
    create_mode_screening_analysis_task as create_mode_screening_analysis,
    create_stock_directory_refresh_task,
    get_mode_screening_result_by_symbol,
    list_mode_screening_results as query_mode_screening_results,
    list_mode_screening_trades as query_mode_screening_trades,
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


def _load_json_value(value: str, fallback):
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _mode_screening_result_dict(result) -> dict:
    evidence = _load_json_value(result.evidence_json, [])
    metrics = _load_json_value(result.metrics_json, {})
    open_trade = _load_json_value(result.open_trade_json, None)
    pending_orders = _load_json_value(result.pending_orders_json, [])
    return {
        "symbol": result.symbol,
        "code": result.code,
        "name": result.name,
        "as_of_date": result.as_of_date,
        "data_start_date": result.data_start_date,
        "data_end_date": result.data_end_date,
        "signal_date": result.signal_date,
        "insufficient_history": result.insufficient_history,
        "evidence": evidence if isinstance(evidence, list) else [],
        "metrics": metrics if isinstance(metrics, dict) else {},
        "backtest_status": result.backtest_status,
        "completed_trades": result.completed_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "flat_trades": result.flat_trades,
        "win_rate": result.win_rate,
        "average_return": result.average_return,
        "maximum_return": result.maximum_return,
        "minimum_return": result.minimum_return,
        "open_trade": open_trade if isinstance(open_trade, dict) else None,
        "pending_orders": pending_orders if isinstance(pending_orders, list) else [],
    }


def _mode_screening_trade_dict(trade, sales) -> dict:
    return {
        "sequence": trade.sequence,
        "signal_date": trade.signal_date,
        "buy_date": trade.buy_date,
        "buy_price": trade.buy_price,
        "realized_return": trade.realized_return,
        "sells": [{
            "date": sale.trade_date,
            "reason_id": sale.reason_id,
            "price": sale.price,
            "fraction_of_original": sale.fraction_of_original,
            "return_rate": sale.return_rate,
        } for sale in sales],
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

    @mcp.tool(
        name="create_sr001_mode_screening_task",
        description="创建固定使用 SR001 revision 1 的模式选股与命中股票历史回测任务，立即返回公开 UUID。",
    )
    def create_sr001_mode_screening_task_tool(
        as_of_date: date,
        symbols: list[str] | None = None,
    ) -> dict:
        with SessionLocal() as db:
            try:
                rule = rule_registry.get_latest("SR001")
                task = create_mode_screening_analysis(
                    db,
                    rule_id="SR001",
                    rule_revision=rule.revision,
                    parameters=rule.validate_parameters({}),
                    as_of_date=as_of_date,
                    symbols=symbols,
                )
            except (TaskOperationError, ValueError) as exc:
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

    @mcp.tool(description="按任务 UUID 分页查询模式选股命中股票、信号依据和历史回测统计。")
    def get_mode_screening_results(
        task_uuid: str,
        page: int = 1,
        page_size: int = 20,
        sort_by: Literal["win_rate", "average_return", "maximum_return"] | None = None,
        sort_order: Literal["asc", "desc"] | None = None,
    ) -> dict:
        if page < 1:
            raise ToolError("page 必须大于等于 1")
        if page_size < 1 or page_size > 100:
            raise ToolError("page_size 必须在 1 到 100 之间")
        with SessionLocal() as db:
            task = _task_by_uuid(db, task_uuid)
            try:
                rows, total = query_mode_screening_results(
                    db,
                    task,
                    page=page,
                    page_size=page_size,
                    sort_by=sort_by,
                    sort_order=sort_order,
                )
            except TaskOperationError as exc:
                raise _task_error(exc) from exc
            return {
                "task_uuid": task.uuid,
                "items": [_mode_screening_result_dict(row) for row in rows],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @mcp.tool(description="按任务 UUID 和股票代码分页查询模式选股命中股票的交易及分次卖出明细。")
    def get_mode_screening_trades(
        task_uuid: str,
        symbol: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        if page < 1:
            raise ToolError("page 必须大于等于 1")
        if page_size < 1 or page_size > 100:
            raise ToolError("page_size 必须在 1 到 100 之间")
        with SessionLocal() as db:
            task = _task_by_uuid(db, task_uuid)
            try:
                stock_result = get_mode_screening_result_by_symbol(db, task, symbol)
                trades, total, sales_by_trade = query_mode_screening_trades(
                    db, stock_result, page=page, page_size=page_size,
                )
            except TaskOperationError as exc:
                raise _task_error(exc) from exc
            return {
                "task_uuid": task.uuid,
                "symbol": stock_result.symbol,
                "items": [
                    _mode_screening_trade_dict(trade, sales_by_trade.get(trade.id, []))
                    for trade in trades
                ],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    @mcp.tool(
        description="根据成功完成的 SR001 模式选股任务 UUID，一次返回精简结构化报告和可供用户阅读的 PDF。",
    )
    def get_sr001_screening_report(task_uuid: str) -> ToolResult:
        with SessionLocal() as db:
            task = _task_by_uuid(db, task_uuid)
            try:
                report = build_sr001_screening_report(db, task)
                pdf = render_sr001_screening_report_pdf(report)
            except (SR001ReportError, SR001ReportPdfError) as exc:
                raise ToolError(str(exc)) from exc
            filename = f"sr001-revision-{report.rule_revision}-{report.as_of_date}.pdf"
            return ToolResult(
                content=[
                    File(data=pdf, format="pdf", name=filename.removesuffix(".pdf"))
                    .to_resource_content()
                ],
                structured_content=report.model_dump(mode="json"),
            )
