from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.market_data.storage import StoredDailyBar
from app.screening.backtest import (
    BacktestAction,
    BacktestInstruction,
    BacktestPendingOrder,
    run_individual_backtest,
)
from app.screening.executor import execute_screening_rule
from app.screening.models import (
    RuleEvidence,
    RuleEvaluation,
    ScreeningOutcome,
    StockIdentity,
    valid_daily_bars,
)


STOCK = StockIdentity(symbol="000001.SZ", code="000001", name="平安银行")


def bar(day: int, *, volume: int = 100, close: str = "10") -> StoredDailyBar:
    trade_date = date(2026, 1, 1) + timedelta(days=day)
    price = Decimal(close)
    return StoredDailyBar(
        trade_date=trade_date,
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price,
        volume=volume,
        amount=Decimal("1000"),
    )


class PrefixRule:
    rule_id = "TEST"
    revision = 1

    def validate_parameters(self, parameters):
        if set(parameters) != {"minimum"}:
            raise ValueError("需要 minimum 参数")
        return {"minimum": int(parameters["minimum"])}

    def evaluate(self, stock, bars, parameters):
        assert stock == STOCK
        assert all(item.trade_date <= bars[-1].trade_date for item in bars)
        return RuleEvaluation(
            matched=len(bars) >= parameters["minimum"],
            signal_date=bars[-1].trade_date,
            evidence=(),
            metrics={"bar_count": len(bars)},
        )


def test_valid_daily_bars_filters_zero_volume_and_rejects_bad_data():
    assert [item.trade_date for item in valid_daily_bars([bar(0), bar(1, volume=0), bar(2)])] == [
        bar(0).trade_date,
        bar(2).trade_date,
    ]
    invalid = bar(3)
    invalid = StoredDailyBar(
        trade_date=invalid.trade_date,
        open=Decimal("0"),
        high=invalid.high,
        low=invalid.low,
        close=invalid.close,
        volume=invalid.volume,
        amount=invalid.amount,
    )
    with pytest.raises(ValueError, match="OHLC 字段缺失或非法"):
        valid_daily_bars([invalid])


def test_screening_executor_isolates_future_bars_and_records_cutoff():
    result = execute_screening_rule(
        PrefixRule(),
        stock=STOCK,
        source_bars=[bar(0), bar(1), bar(2)],
        as_of_date=bar(1).trade_date,
        parameters={"minimum": 2},
    )
    assert result.outcome == ScreeningOutcome.MATCHED
    assert result.data_end_date == bar(1).trade_date
    assert result.signal_date == bar(1).trade_date
    assert result.parameters == {"minimum": 2}


class InvalidEvidenceRule(PrefixRule):
    def evaluate(self, stock, bars, parameters):
        return RuleEvaluation(
            matched=True,
            signal_date=bars[-1].trade_date,
            evidence=(
                RuleEvidence("C1", True, {}),
                RuleEvidence("C1", True, {}),
            ),
            metrics={},
        )


def test_screening_executor_rejects_duplicate_evidence_ids():
    with pytest.raises(ValueError, match="判定依据编号不能重复"):
        execute_screening_rule(
            InvalidEvidenceRule(),
            stock=STOCK,
            source_bars=[bar(0)],
            as_of_date=bar(0).trade_date,
            parameters={"minimum": 1},
        )


class PartialSellSession:
    def on_bar(self, context):
        day = context.bar.trade_date
        assert context.history[-1].trade_date == day
        if day == bar(1).trade_date:
            return [BacktestInstruction(
                action=BacktestAction.BUY,
                price=context.bar.open,
                reason_id="B1",
                signal_date=bar(0).trade_date,
            )]
        if day == bar(2).trade_date:
            return [BacktestInstruction(
                action=BacktestAction.SELL,
                price=context.bar.close,
                fraction=Decimal("0.5"),
                reason_id="TP1",
                signal_date=day,
            )]
        if day == bar(3).trade_date:
            return [BacktestInstruction(
                action=BacktestAction.SELL,
                price=context.bar.open,
                reason_id="EX1",
                signal_date=bar(2).trade_date,
            )]
        return []

    def pending_orders(self):
        return []


def test_individual_backtest_tracks_partial_sales_and_is_deterministic():
    kwargs = {
        "rule_id": "TEST",
        "rule_revision": 1,
        "parameters": {},
        "stock": STOCK,
        "source_bars": [bar(0), bar(1), bar(2, close="11"), bar(3, close="12")],
        "start_date": bar(0).trade_date,
        "end_date": bar(3).trade_date,
    }
    first = run_individual_backtest(**kwargs, session=PartialSellSession()).to_dict()
    second = run_individual_backtest(**kwargs, session=PartialSellSession()).to_dict()
    assert first == second
    assert first["status"] == "completed"
    assert first["completed_trades"] == 1
    assert [sale["reason_id"] for sale in first["trades"][0]["sells"]] == ["TP1", "EX1"]
    assert [sale["fraction_of_original"] for sale in first["trades"][0]["sells"]] == ["0.5", "0.5"]


class SameDaySellSession:
    def on_bar(self, context):
        return [
            BacktestInstruction(BacktestAction.BUY, context.bar.open, "B1", context.bar.trade_date),
            BacktestInstruction(BacktestAction.SELL, context.bar.close, "SL1", context.bar.trade_date),
        ]

    def pending_orders(self):
        return []


def test_individual_backtest_enforces_t_plus_one():
    with pytest.raises(ValueError, match="不允许在买入日卖出"):
        run_individual_backtest(
            rule_id="TEST",
            rule_revision=1,
            parameters={},
            stock=STOCK,
            source_bars=[bar(0)],
            start_date=bar(0).trade_date,
            end_date=bar(0).trade_date,
            session=SameDaySellSession(),
        )


class PendingEntrySession:
    def on_bar(self, context):
        return []

    def pending_orders(self):
        return [BacktestPendingOrder(BacktestAction.BUY, "B1", bar(0).trade_date)]


def test_individual_backtest_distinguishes_unfilled_entry():
    result = run_individual_backtest(
        rule_id="TEST",
        rule_revision=1,
        parameters={},
        stock=STOCK,
        source_bars=[bar(0), bar(1)],
        start_date=bar(0).trade_date,
        end_date=bar(1).trade_date,
        session=PendingEntrySession(),
    )
    assert result.status == "pending_entry"
    assert result.pending_orders[0].reason_id == "B1"
