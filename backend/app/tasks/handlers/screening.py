from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Stock
from app.database.session import SessionLocal
from app.market_data.storage import DuckDbMarketDataStore
from app.screening.executor import execute_screening_rule
from app.screening.models import ScreeningOutcome, StockIdentity
from app.screening.registry import RuleRegistry, rule_registry
from app.tasks.context import TaskContext
from app.tasks.models import Task, TaskItem, TaskItemStatus

from . import TaskItemSkipped, TaskItemSpec


TASK_TYPE = "screening_rule_execute"


def _json(value: str) -> dict:
    parsed = json.loads(value or "{}")
    return parsed if isinstance(parsed, dict) else {}


def _parse_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise ValueError(f"{field} 日期无效") from exc


def _parse_rule_input(task_input: dict, registry: RuleRegistry) -> tuple[str, int, dict, date]:
    rule_id = task_input.get("rule_id")
    revision = task_input.get("rule_revision")
    parameters = task_input.get("parameters", {})
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise ValueError("rule_id 不能为空")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError("rule_revision 必须为正整数")
    if not isinstance(parameters, dict):
        raise ValueError("parameters 必须是 JSON 对象")
    as_of_date = _parse_date(task_input.get("as_of_date"), "as_of_date")
    normalized = registry.get(rule_id, revision).validate_parameters(parameters)
    return rule_id, revision, normalized, as_of_date


class ScreeningRuleExecuteHandler:
    def __init__(
        self,
        *,
        registry: RuleRegistry = rule_registry,
        session_factory: sessionmaker[Session] = SessionLocal,
        store_factory: Callable[[], DuckDbMarketDataStore] = DuckDbMarketDataStore,
    ):
        self.registry = registry
        self.session_factory = session_factory
        self.store_factory = store_factory
        self._store: DuckDbMarketDataStore | None = None

    def build_items(self, task_input: dict) -> list[TaskItemSpec]:
        rule_id, revision, parameters, as_of_date = _parse_rule_input(task_input, self.registry)
        requested = task_input.get("symbols")
        if requested is not None and (
            not isinstance(requested, list)
            or not requested
            or any(not isinstance(symbol, str) or not symbol for symbol in requested)
        ):
            raise ValueError("symbols 必须是非空股票代码数组")
        with self.session_factory() as db:
            query = select(Stock).order_by(Stock.symbol)
            if requested is not None:
                query = query.where(Stock.symbol.in_(set(requested)))
            stocks = list(db.scalars(query).all())
        if not stocks:
            raise ValueError("没有可执行选股的股票")
        if requested is not None:
            found = {stock.symbol for stock in stocks}
            missing = sorted(set(requested) - found)
            if missing:
                raise ValueError(f"股票不在本地目录：{', '.join(missing)}")
        return [
            TaskItemSpec(
                title=f"执行 {rule_id} v{revision}：{stock.symbol} {stock.name}",
                input={
                    "rule_id": rule_id,
                    "rule_revision": revision,
                    "parameters": parameters,
                    "as_of_date": as_of_date.isoformat(),
                    "symbol": stock.symbol,
                    "code": stock.code,
                    "name": stock.name,
                },
            )
            for stock in stocks
        ]

    def _market_store(self) -> DuckDbMarketDataStore:
        if self._store is None:
            self._store = self.store_factory()
        return self._store

    def run_item(self, task: Task, item: TaskItem, context: TaskContext) -> dict:
        item_input = _json(item.input_json)
        rule_id = str(item_input["rule_id"])
        revision = int(item_input["rule_revision"])
        as_of_date = _parse_date(item_input["as_of_date"], "as_of_date")
        symbol = str(item_input["symbol"])
        context.report_progress(0, 1, f"正在计算 {symbol}")
        result = execute_screening_rule(
            self.registry.get(rule_id, revision),
            stock=StockIdentity(symbol=symbol, code=str(item_input["code"]), name=str(item_input["name"])),
            source_bars=self._market_store().daily_bars(symbol, end_date=as_of_date),
            as_of_date=as_of_date,
            parameters=dict(item_input.get("parameters") or {}),
        )
        context.report_progress(1, 1, f"{symbol} 计算完成")
        payload = result.to_dict()
        if result.outcome == ScreeningOutcome.SKIPPED:
            raise TaskItemSkipped(result.reason or "规则无法计算", payload)
        return payload

    def summarize(self, task: Task, items: list[TaskItem]) -> dict:
        try:
            results = [_json(item.result_json) for item in items]
            matched = [
                result for item, result in zip(items, results, strict=True)
                if item.status == TaskItemStatus.SUCCEEDED.value and result.get("outcome") == "matched"
            ]
            task_input = _json(task.input_json)
            return {
                "rule_id": task_input.get("rule_id"),
                "rule_revision": task_input.get("rule_revision"),
                "parameters": task_input.get("parameters", {}),
                "as_of_date": task_input.get("as_of_date"),
                "stock_count": len(items),
                "matched_stocks": len(matched),
                "not_matched_stocks": sum(
                    item.status == TaskItemStatus.SUCCEEDED.value and result.get("outcome") == "not_matched"
                    for item, result in zip(items, results, strict=True)
                ),
                "skipped_stocks": sum(item.status == TaskItemStatus.SKIPPED.value for item in items),
                "failed_stocks": sum(item.status == TaskItemStatus.FAILED.value for item in items),
                "matches": [
                    {
                        "symbol": result.get("symbol"),
                        "code": result.get("code"),
                        "name": result.get("name"),
                        "data_end_date": result.get("data_end_date"),
                        "signal_date": result.get("signal_date"),
                        "evidence": result.get("evidence", []),
                        "metrics": result.get("metrics", {}),
                        "insufficient_history": result.get("insufficient_history", False),
                    }
                    for result in matched
                ],
            }
        finally:
            if self._store is not None:
                self._store.close()
                self._store = None
