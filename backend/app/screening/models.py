from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.market_data.storage import StoredDailyBar


JsonValue = str | int | float | bool | None


@dataclass(frozen=True)
class StockIdentity:
    symbol: str
    code: str
    name: str


@dataclass(frozen=True)
class ValidDailyBar:
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class RuleEvidence:
    condition_id: str
    passed: bool
    values: dict[str, JsonValue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "passed": self.passed,
            "values": self.values,
        }


@dataclass(frozen=True)
class RuleEvaluation:
    matched: bool
    signal_date: date | None
    evidence: tuple[RuleEvidence, ...]
    metrics: dict[str, JsonValue]
    insufficient_history: bool = False


class ScreeningOutcome(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ScreeningResult:
    rule_id: str
    rule_revision: int
    parameters: dict[str, JsonValue]
    stock: StockIdentity
    as_of_date: date
    data_end_date: date | None
    signal_date: date | None
    outcome: ScreeningOutcome
    evidence: tuple[RuleEvidence, ...] = ()
    metrics: dict[str, JsonValue] | None = None
    insufficient_history: bool = False
    reason_code: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_revision": self.rule_revision,
            "parameters": self.parameters,
            "symbol": self.stock.symbol,
            "code": self.stock.code,
            "name": self.stock.name,
            "as_of_date": self.as_of_date.isoformat(),
            "data_end_date": self.data_end_date.isoformat() if self.data_end_date else None,
            "signal_date": self.signal_date.isoformat() if self.signal_date else None,
            "outcome": self.outcome.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "metrics": self.metrics or {},
            "insufficient_history": self.insufficient_history,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


class RuleNotEvaluable(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


def valid_daily_bars(bars: list[StoredDailyBar]) -> tuple[ValidDailyBar, ...]:
    result: list[ValidDailyBar] = []
    previous_date: date | None = None
    for bar in bars:
        if previous_date is not None and bar.trade_date <= previous_date:
            raise ValueError("日 K 日期必须严格递增且不能重复")
        previous_date = bar.trade_date
        prices = (bar.open, bar.high, bar.low, bar.close)
        if any(not value.is_finite() or value <= 0 for value in prices):
            raise ValueError(f"{bar.trade_date} 的 OHLC 字段缺失或非法")
        if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
            raise ValueError(f"{bar.trade_date} 的 OHLC 价格关系非法")
        if bar.volume < 0:
            raise ValueError(f"{bar.trade_date} 的成交量非法")
        if bar.volume == 0:
            continue
        result.append(ValidDailyBar(
            trade_date=bar.trade_date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        ))
    return tuple(result)
