from __future__ import annotations

from app.screening.registry import RuleRegistry, rule_registry

from .sr001 import (
    SR001Revision2Rule,
    SR001Rule,
    create_sr001_backtest_session,
    create_sr001_v2_backtest_session,
)


def register_production_rules(registry: RuleRegistry = rule_registry) -> None:
    rules = (
        (SR001Rule(), create_sr001_backtest_session),
        (SR001Revision2Rule(), create_sr001_v2_backtest_session),
    )
    for rule, backtest_factory in rules:
        try:
            registry.get(rule.rule_id, rule.revision)
        except ValueError:
            registry.register(rule, backtest_factory=backtest_factory)


__all__ = [
    "SR001Revision2Rule",
    "SR001Rule",
    "create_sr001_backtest_session",
    "create_sr001_v2_backtest_session",
    "register_production_rules",
]
