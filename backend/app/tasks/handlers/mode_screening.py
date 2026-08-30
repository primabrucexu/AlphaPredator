from __future__ import annotations

import json
from decimal import Decimal

from app.screening.backtest import run_individual_backtest
from app.screening.executor import execute_screening_rule_with_backtest
from app.screening.models import ScreeningOutcome, StockIdentity, valid_daily_bars
from app.tasks.context import TaskContext
from app.tasks.models import (
    ModeScreeningSaleResult,
    ModeScreeningStockResult,
    ModeScreeningTradeResult,
    Task,
    TaskItem,
    TaskItemStatus,
)
from app.tasks.mode_screening_state import derive_mode_screening_current_state

from . import TaskItemSkipped, TaskItemSpec
from .screening import ScreeningRuleExecuteHandler, _json, _parse_date, _parse_rule_input


TASK_TYPE = "mode_screening_analysis"


def _decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _trade_statistics(trades: list[dict]) -> dict:
    returns = [Decimal(str(trade["realized_return"])) for trade in trades]
    wins = sum(value > 0 for value in returns)
    losses = sum(value < 0 for value in returns)
    flats = sum(value == 0 for value in returns)
    count = len(returns)
    return {
        "completed_trades": count,
        "winning_trades": wins,
        "losing_trades": losses,
        "flat_trades": flats,
        "win_rate": _decimal(Decimal(wins) / Decimal(count)) if count else None,
        "average_return": _decimal(sum(returns, Decimal("0")) / Decimal(count)) if count else None,
        "maximum_return": _decimal(max(returns)) if count else None,
        "minimum_return": _decimal(min(returns)) if count else None,
    }


class ModeScreeningAnalysisHandler(ScreeningRuleExecuteHandler):
    def build_items(self, task_input: dict) -> list[TaskItemSpec]:
        rule_id, revision, _, _ = _parse_rule_input(task_input, self.registry)
        self.registry.get_backtest_factory(rule_id, revision)
        return [
            TaskItemSpec(
                title=spec.title.replace("执行", "分析", 1),
                input=spec.input,
                total=2,
            )
            for spec in super().build_items(task_input)
        ]

    def run_item(self, task: Task, item: TaskItem, context: TaskContext) -> dict:
        item_input = _json(item.input_json)
        rule_id = str(item_input["rule_id"])
        revision = int(item_input["rule_revision"])
        parameters = dict(item_input.get("parameters") or {})
        as_of_date = _parse_date(item_input["as_of_date"], "as_of_date")
        stock = StockIdentity(
            symbol=str(item_input["symbol"]),
            code=str(item_input["code"]),
            name=str(item_input["name"]),
        )
        context.report_progress(0, 2, f"正在扫描 {stock.symbol}")
        source_bars = self._market_store().daily_bars(stock.symbol, end_date=as_of_date)
        screening, evaluated_backtest = execute_screening_rule_with_backtest(
            self.registry.get(rule_id, revision),
            stock=stock,
            source_bars=source_bars,
            as_of_date=as_of_date,
            parameters=parameters,
        )
        screening_payload = screening.to_dict()
        if screening.outcome == ScreeningOutcome.SKIPPED:
            raise TaskItemSkipped(screening.reason or "规则无法计算", screening_payload)
        if screening.outcome == ScreeningOutcome.NOT_MATCHED:
            context.report_progress(2, 2, f"{stock.symbol} 未命中")
            return screening_payload

        context.report_progress(1, 2, f"{stock.symbol} 已命中，正在回测")
        valid_bars = valid_daily_bars(source_bars)
        factory = self.registry.get_backtest_factory(rule_id, revision)
        backtest = (
            evaluated_backtest
            or run_individual_backtest(
                rule_id=rule_id,
                rule_revision=revision,
                parameters=parameters,
                stock=stock,
                source_bars=source_bars,
                start_date=valid_bars[0].trade_date,
                end_date=as_of_date,
                session=factory(stock, parameters),
            )
        ).to_dict()
        trades = list(backtest["trades"])
        statistics = _trade_statistics(trades)
        open_trade = backtest.get("open_trade")
        pending_orders = list(backtest.get("pending_orders", []))
        stock_result = ModeScreeningStockResult(
            task_id=task.id,
            task_item_id=item.id,
            symbol=stock.symbol,
            code=stock.code,
            name=stock.name,
            as_of_date=as_of_date.isoformat(),
            data_start_date=backtest.get("data_start_date"),
            data_end_date=screening_payload.get("data_end_date"),
            signal_date=screening_payload.get("signal_date"),
            insufficient_history=bool(screening_payload.get("insufficient_history")),
            evidence_json=json.dumps(screening_payload.get("evidence", []), ensure_ascii=False),
            metrics_json=json.dumps(screening_payload.get("metrics", {}), ensure_ascii=False),
            backtest_status=str(backtest["status"]),
            current_state=derive_mode_screening_current_state(
                backtest_status=str(backtest["status"]),
                as_of_date=as_of_date.isoformat(),
                open_trade=open_trade if isinstance(open_trade, dict) else None,
                pending_orders=pending_orders,
            ),
            open_trade_json=json.dumps(open_trade, ensure_ascii=False),
            pending_orders_json=json.dumps(pending_orders, ensure_ascii=False),
            **statistics,
        )
        context.db.add(stock_result)
        context.db.flush()
        for trade_sequence, trade in enumerate(trades):
            trade_result = ModeScreeningTradeResult(
                stock_result_id=stock_result.id,
                sequence=trade_sequence,
                signal_date=str(trade["signal_date"]),
                buy_date=str(trade["buy_date"]),
                buy_price=str(trade["buy_price"]),
                realized_return=str(trade["realized_return"]),
            )
            context.db.add(trade_result)
            context.db.flush()
            for sale_sequence, sale in enumerate(trade.get("sells", [])):
                context.db.add(ModeScreeningSaleResult(
                    trade_result_id=trade_result.id,
                    sequence=sale_sequence,
                    trade_date=str(sale["date"]),
                    reason_id=str(sale["reason_id"]),
                    price=str(sale["price"]),
                    fraction_of_original=str(sale["fraction_of_original"]),
                    return_rate=str(sale["return_rate"]),
                ))
        context.report_progress(2, 2, f"{stock.symbol} 分析完成")
        return {
            **screening_payload,
            "result_id": stock_result.id,
            "backtest_status": backtest["status"],
            **statistics,
        }

    def summarize(self, task: Task, items: list[TaskItem]) -> dict:
        try:
            results = [_json(item.result_json) for item in items]
            matched = [
                result for item, result in zip(items, results, strict=True)
                if item.status == TaskItemStatus.SUCCEEDED.value and result.get("outcome") == "matched"
            ]
            task_input = _json(task.input_json)
            return {
                "mode": "screening_with_backtest",
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
                "matches": [{
                    key: result.get(key) for key in (
                        "result_id", "symbol", "code", "name", "data_end_date", "signal_date",
                        "insufficient_history", "backtest_status", "completed_trades", "winning_trades",
                        "losing_trades", "flat_trades", "win_rate", "average_return", "maximum_return",
                        "minimum_return",
                    )
                } for result in matched],
            }
        finally:
            self._close_market_stores()
