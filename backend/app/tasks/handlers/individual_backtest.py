from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Stock
from app.database.session import SessionLocal
from app.market_data.storage import DuckDbMarketDataStore
from app.screening.backtest import run_individual_backtest
from app.screening.models import StockIdentity
from app.screening.registry import RuleRegistry, rule_registry
from app.tasks.context import TaskContext
from app.tasks.models import Task, TaskItem, TaskItemStatus

from . import TaskItemSkipped, TaskItemSpec
from .screening import _parse_date, _parse_rule_input


TASK_TYPE = "individual_backtest"


def _json(value: str) -> dict:
    parsed = json.loads(value or "{}")
    return parsed if isinstance(parsed, dict) else {}


class IndividualBacktestHandler:
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
        rule_id, revision, parameters, _ = _parse_rule_input(
            {**task_input, "as_of_date": task_input.get("end_date")}, self.registry
        )
        self.registry.get_backtest_factory(rule_id, revision)
        start_date = _parse_date(task_input.get("start_date"), "start_date")
        end_date = _parse_date(task_input.get("end_date"), "end_date")
        if start_date > end_date:
            raise ValueError("回测开始日期不能晚于结束日期")
        symbol = task_input.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("symbol 不能为空")
        with self.session_factory() as db:
            stock = db.get(Stock, symbol)
        if stock is None:
            raise ValueError(f"股票不在本地目录：{symbol}")
        return [TaskItemSpec(
            title=f"回测 {rule_id} v{revision}：{stock.symbol} {stock.name}",
            input={
                "rule_id": rule_id,
                "rule_revision": revision,
                "parameters": parameters,
                "symbol": stock.symbol,
                "code": stock.code,
                "name": stock.name,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )]

    def _market_store(self) -> DuckDbMarketDataStore:
        if self._store is None:
            self._store = self.store_factory()
        return self._store

    def run_item(self, task: Task, item: TaskItem, context: TaskContext) -> dict:
        item_input = _json(item.input_json)
        rule_id = str(item_input["rule_id"])
        revision = int(item_input["rule_revision"])
        parameters = dict(item_input.get("parameters") or {})
        start_date = _parse_date(item_input["start_date"], "start_date")
        end_date = _parse_date(item_input["end_date"], "end_date")
        stock = StockIdentity(
            symbol=str(item_input["symbol"]),
            code=str(item_input["code"]),
            name=str(item_input["name"]),
        )
        context.report_progress(0, 1, f"正在回测 {stock.symbol}")
        factory = self.registry.get_backtest_factory(rule_id, revision)
        try:
            result = run_individual_backtest(
                rule_id=rule_id,
                rule_revision=revision,
                parameters=parameters,
                stock=stock,
                source_bars=self._market_store().daily_bars(stock.symbol, end_date=end_date),
                start_date=start_date,
                end_date=end_date,
                session=factory(stock, parameters),
            )
        except ValueError as exc:
            if str(exc) == "回测区间内没有有效日 K":
                raise TaskItemSkipped(
                    str(exc),
                    {
                        "mode": "individual",
                        "rule_id": rule_id,
                        "rule_revision": revision,
                        "symbol": stock.symbol,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "status": "skipped",
                        "reason_code": "no_valid_daily_bars",
                        "reason": str(exc),
                    },
                ) from exc
            raise
        context.report_progress(1, 1, f"{stock.symbol} 回测完成")
        return result.to_dict()

    def summarize(self, task: Task, items: list[TaskItem]) -> dict:
        try:
            item = items[0]
            result = _json(item.result_json)
            if item.status == TaskItemStatus.SKIPPED.value:
                return result
            return {
                **result,
                "failed": item.status == TaskItemStatus.FAILED.value,
            }
        finally:
            if self._store is not None:
                self._store.close()
                self._store = None
