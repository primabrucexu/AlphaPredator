from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from .backtest import BacktestContext, BacktestInstruction, BacktestPendingOrder
from .models import JsonValue, RuleEvaluation, StockIdentity, ValidDailyBar


class ScreeningRule(Protocol):
    rule_id: str
    revision: int

    def validate_parameters(self, parameters: dict[str, Any]) -> dict[str, JsonValue]: ...

    def evaluate(
        self,
        stock: StockIdentity,
        bars: tuple[ValidDailyBar, ...],
        parameters: dict[str, JsonValue],
    ) -> RuleEvaluation: ...


class IndividualBacktestSession(Protocol):
    def on_bar(self, context: BacktestContext) -> Sequence[BacktestInstruction]: ...

    def pending_orders(self) -> Sequence[BacktestPendingOrder]: ...


BacktestFactory = Callable[[StockIdentity, dict[str, JsonValue]], IndividualBacktestSession]


class RuleRegistry:
    def __init__(self) -> None:
        self._rules: dict[tuple[str, int], ScreeningRule] = {}
        self._backtests: dict[tuple[str, int], BacktestFactory] = {}

    def register(
        self,
        rule: ScreeningRule,
        *,
        backtest_factory: BacktestFactory | None = None,
    ) -> None:
        if not rule.rule_id.strip() or rule.revision < 1:
            raise ValueError("规则编号不能为空且规则版本必须为正整数")
        key = (rule.rule_id, rule.revision)
        if key in self._rules:
            raise ValueError(f"规则已注册：{rule.rule_id} v{rule.revision}")
        self._rules[key] = rule
        if backtest_factory is not None:
            self._backtests[key] = backtest_factory

    def get(self, rule_id: str, revision: int) -> ScreeningRule:
        try:
            return self._rules[(rule_id, revision)]
        except KeyError as exc:
            raise ValueError(f"未注册规则：{rule_id} v{revision}") from exc

    def get_latest(self, rule_id: str) -> ScreeningRule:
        revisions = [
            revision for registered_rule_id, revision in self._rules
            if registered_rule_id == rule_id
        ]
        if not revisions:
            raise ValueError(f"未注册规则：{rule_id}")
        return self._rules[(rule_id, max(revisions))]

    def get_backtest_factory(self, rule_id: str, revision: int) -> BacktestFactory:
        self.get(rule_id, revision)
        try:
            return self._backtests[(rule_id, revision)]
        except KeyError as exc:
            raise ValueError(f"规则不支持个股回测：{rule_id} v{revision}") from exc


rule_registry = RuleRegistry()
