from __future__ import annotations

from app.screening.registry import RuleRegistry, rule_registry

from .sr001 import SR001Rule, create_sr001_backtest_session


def register_production_rules(registry: RuleRegistry = rule_registry) -> None:
    try:
        registry.get(SR001Rule.rule_id, SR001Rule.revision)
    except ValueError:
        registry.register(SR001Rule(), backtest_factory=create_sr001_backtest_session)


__all__ = ["SR001Rule", "create_sr001_backtest_session", "register_production_rules"]
