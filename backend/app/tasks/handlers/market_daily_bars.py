from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Stock
from app.database.session import SessionLocal
from app.market_data.provider import get_process_market_provider
from app.market_data.provider.base import MarketDataProvider
from app.market_data.storage import DuckDbMarketDataStore, StoredDailyBar, prepare_daily_bars
from app.tasks.context import TaskContext
from app.tasks.models import Task, TaskItem, TaskItemStatus

from . import TaskItemSpec


TASK_TYPE = "market_daily_bars_update"
FULL_START_DATE = date(2025, 1, 1)
VALID_MODES = {"incremental", "full"}


def _json(value: str) -> dict:
    parsed = json.loads(value or "{}")
    return parsed if isinstance(parsed, dict) else {}


def _same_ohlc(left: StoredDailyBar, right: StoredDailyBar) -> bool:
    return (left.open, left.high, left.low, left.close) == (
        right.open,
        right.high,
        right.low,
        right.close,
    )


class MarketDailyBarsUpdateHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session] = SessionLocal,
        provider_factory: Callable[[], MarketDataProvider] = get_process_market_provider,
        store_factory: Callable[[], DuckDbMarketDataStore] = DuckDbMarketDataStore,
    ):
        self.session_factory = session_factory
        self.provider_factory = provider_factory
        self.store_factory = store_factory
        self._provider: MarketDataProvider | None = None
        self._store: DuckDbMarketDataStore | None = None

    def build_items(self, task_input: dict) -> list[TaskItemSpec]:
        mode = task_input.get("mode")
        if mode not in VALID_MODES:
            raise ValueError("行情更新模式必须是 incremental 或 full")
        try:
            date.fromisoformat(str(task_input.get("target_end_date") or ""))
        except ValueError as exc:
            raise ValueError("行情更新目标日期无效") from exc
        requested = task_input.get("symbols")
        if requested is not None and (
            not isinstance(requested, list)
            or not requested
            or any(not isinstance(symbol, str) for symbol in requested)
        ):
            raise ValueError("重试股票列表无效")
        with self.session_factory() as db:
            query = select(Stock).order_by(Stock.symbol)
            if requested is not None:
                query = query.where(Stock.symbol.in_(set(requested)))
            stocks = list(db.scalars(query).all())
        if not stocks:
            raise ValueError("本地股票目录为空，请先刷新股票搜索目录")
        if requested is not None:
            by_symbol = {stock.symbol: stock for stock in stocks}
            missing = sorted(set(requested) - set(by_symbol))
            if missing:
                raise ValueError(f"重试股票已不在本地目录：{', '.join(missing)}")
            stocks = [by_symbol[symbol] for symbol in sorted(set(requested)) if symbol in by_symbol]
        return [
            TaskItemSpec(
                title=f"更新 {stock.symbol} {stock.name}",
                input={
                    "symbol": stock.symbol,
                    "mode": mode,
                    "target_end_date": task_input["target_end_date"],
                },
                total=3,
            )
            for stock in stocks
        ]

    def _market_store(self) -> DuckDbMarketDataStore:
        if self._store is None:
            self._store = self.store_factory()
        return self._store

    def _market_provider(self) -> MarketDataProvider:
        if self._provider is None:
            self._provider = self.provider_factory()
        return self._provider

    def _full_update(
        self,
        provider: MarketDataProvider,
        store: DuckDbMarketDataStore,
        symbol: str,
        target_end_date: date,
        context: TaskContext,
    ) -> tuple[int, date, date]:
        context.report_progress(1, 3, f"正在拉取 {symbol} 全量日线")
        source = provider.get_daily_bars(
            symbol,
            start_date=FULL_START_DATE,
            end_date=target_end_date,
        )
        bars = prepare_daily_bars(source, start_date=FULL_START_DATE, end_date=target_end_date)
        context.report_progress(2, 3, f"正在写入 {symbol} 全量日线")
        written = store.replace_full(symbol, bars)
        return written, bars[0].trade_date, bars[-1].trade_date

    def run_item(self, task: Task, item: TaskItem, context: TaskContext) -> dict:
        item_input = _json(item.input_json)
        symbol = str(item_input["symbol"])
        mode = str(item_input["mode"])
        target_end_date = date.fromisoformat(str(item_input["target_end_date"]))
        provider = self._market_provider()
        store = self._market_store()
        old_state = store.get_state(symbol)
        old_first = old_state.first_trade_date.isoformat() if old_state else None
        old_last = old_state.last_trade_date.isoformat() if old_state else None
        execution = "full"
        reason = "forced" if mode == "full" else "missing_local_data"
        corporate_action_count: int | None = None
        corporate_action_diagnostic = ""
        corporate_action_summary: list[dict[str, str]] = []

        if mode == "incremental" and old_state is not None and old_state.adjust == "forward":
            local_overlap = store.recent_bars(symbol, 5)
            if local_overlap:
                context.report_progress(1, 3, f"正在检查 {symbol} 重叠日线")
                source = provider.get_daily_bars(
                    symbol,
                    start_date=local_overlap[0].trade_date,
                    end_date=target_end_date,
                )
                fetched = prepare_daily_bars(
                    source,
                    start_date=local_overlap[0].trade_date,
                    end_date=target_end_date,
                )
                fetched_by_date = {bar.trade_date: bar for bar in fetched}
                valid_overlap = all(bar.trade_date in fetched_by_date for bar in local_overlap)
                changed = valid_overlap and any(
                    not _same_ohlc(bar, fetched_by_date[bar.trade_date]) for bar in local_overlap
                )
                if valid_overlap and not changed:
                    execution = "incremental"
                    reason = "overlap_unchanged"
                    context.report_progress(2, 3, f"正在写入 {symbol} 增量日线")
                    written = store.append_new(symbol, fetched)
                    new_state = store.get_state(symbol)
                    context.report_progress(3, 3, f"{symbol} 增量更新完成")
                    return {
                        "symbol": symbol,
                        "execution": execution,
                        "reason": reason,
                        "written_rows": written,
                        "before_first_date": old_first,
                        "before_last_date": old_last,
                        "after_first_date": new_state.first_trade_date.isoformat(),
                        "after_last_date": new_state.last_trade_date.isoformat(),
                    }
                reason = "overlap_changed" if changed else "invalid_overlap"
                if changed:
                    try:
                        actions = provider.corporate_action(symbol)
                        corporate_action_count = len(actions)
                        corporate_action_diagnostic = f"权息接口返回 {len(actions)} 条记录"
                        corporate_action_summary = [
                            {str(key): str(value) for key, value in action.items()}
                            for action in actions[-3:]
                        ]
                    except Exception as exc:
                        corporate_action_diagnostic = f"权息资料查询失败：{exc}"

        written, first_date, last_date = self._full_update(
            provider, store, symbol, target_end_date, context
        )
        context.report_progress(3, 3, f"{symbol} 全量更新完成")
        result = {
            "symbol": symbol,
            "execution": execution,
            "reason": reason,
            "written_rows": written,
            "before_first_date": old_first,
            "before_last_date": old_last,
            "after_first_date": first_date.isoformat(),
            "after_last_date": last_date.isoformat(),
        }
        if corporate_action_count is not None:
            result["corporate_action_count"] = corporate_action_count
        if corporate_action_diagnostic:
            result["corporate_action_diagnostic"] = corporate_action_diagnostic
        if corporate_action_summary:
            result["corporate_action_summary"] = corporate_action_summary
        return result

    def summarize(self, task: Task, items: list[TaskItem]) -> dict:
        try:
            results = [_json(item.result_json) for item in items]
            succeeded = [
                result
                for item, result in zip(items, results, strict=True)
                if item.status == TaskItemStatus.SUCCEEDED.value
            ]
            failed = [item for item in items if item.status == TaskItemStatus.FAILED.value]
            task_input = _json(task.input_json)
            actual_dates = [str(result["after_last_date"]) for result in succeeded if result.get("after_last_date")]
            return {
                "mode": task_input.get("mode"),
                "target_end_date": task_input.get("target_end_date"),
                "stock_count": len(items),
                "succeeded_stocks": len(succeeded),
                "failed_stocks": len(failed),
                "incremental_stocks": sum(result.get("execution") == "incremental" for result in succeeded),
                "full_stocks": sum(result.get("execution") == "full" for result in succeeded),
                "written_rows": sum(int(result.get("written_rows") or 0) for result in succeeded),
                "actual_end_date": max(actual_dates) if actual_dates else None,
                "failed_summary": [
                    {"symbol": _json(item.input_json).get("symbol"), "error": item.error}
                    for item in failed[:20]
                ],
            }
        finally:
            if self._store is not None:
                self._store.close()
                self._store = None
            if self._provider is not None:
                self._provider.close()
                self._provider = None
