from __future__ import annotations

import json
from datetime import date

from app.market_data.storage import StoredDailyBar
from app.screening.backtest import IndividualBacktestResult

from .models import (
    RuleNotEvaluable,
    ScreeningOutcome,
    ScreeningResult,
    StockIdentity,
    valid_daily_bars,
)
from .registry import ScreeningRule


def execute_screening_rule(
    rule: ScreeningRule,
    *,
    stock: StockIdentity,
    source_bars: list[StoredDailyBar],
    as_of_date: date,
    parameters: dict,
) -> ScreeningResult:
    result, _ = _execute_screening_rule(
        rule,
        stock=stock,
        source_bars=source_bars,
        as_of_date=as_of_date,
        parameters=parameters,
        include_backtest=False,
    )
    return result


def execute_screening_rule_with_backtest(
    rule: ScreeningRule,
    *,
    stock: StockIdentity,
    source_bars: list[StoredDailyBar],
    as_of_date: date,
    parameters: dict,
) -> tuple[ScreeningResult, IndividualBacktestResult | None]:
    return _execute_screening_rule(
        rule,
        stock=stock,
        source_bars=source_bars,
        as_of_date=as_of_date,
        parameters=parameters,
        include_backtest=True,
    )


def _execute_screening_rule(
    rule: ScreeningRule,
    *,
    stock: StockIdentity,
    source_bars: list[StoredDailyBar],
    as_of_date: date,
    parameters: dict,
    include_backtest: bool,
) -> tuple[ScreeningResult, IndividualBacktestResult | None]:
    normalized_parameters = rule.validate_parameters(parameters)
    bars = valid_daily_bars([bar for bar in source_bars if bar.trade_date <= as_of_date])
    if not bars:
        return ScreeningResult(
            rule_id=rule.rule_id,
            rule_revision=rule.revision,
            parameters=normalized_parameters,
            stock=stock,
            as_of_date=as_of_date,
            data_end_date=None,
            signal_date=None,
            outcome=ScreeningOutcome.SKIPPED,
            reason_code="no_valid_daily_bars",
            reason="计算日期及以前没有有效日 K",
        ), None
    backtest = None
    try:
        evaluate_with_backtest = getattr(rule, "evaluate_with_backtest", None)
        if include_backtest and callable(evaluate_with_backtest):
            evaluation, backtest = evaluate_with_backtest(stock, bars, normalized_parameters)
        else:
            evaluation = rule.evaluate(stock, bars, normalized_parameters)
    except RuleNotEvaluable as exc:
        return ScreeningResult(
            rule_id=rule.rule_id,
            rule_revision=rule.revision,
            parameters=normalized_parameters,
            stock=stock,
            as_of_date=as_of_date,
            data_end_date=bars[-1].trade_date,
            signal_date=None,
            outcome=ScreeningOutcome.SKIPPED,
            reason_code=exc.reason_code,
            reason=exc.message,
        ), None
    condition_ids = [item.condition_id for item in evaluation.evidence]
    if any(not condition_id.strip() for condition_id in condition_ids):
        raise ValueError("规则判定依据编号不能为空")
    if len(condition_ids) != len(set(condition_ids)):
        raise ValueError("规则判定依据编号不能重复")
    if evaluation.matched and evaluation.signal_date is None:
        raise ValueError("命中结果必须包含信号日期")
    if evaluation.signal_date is not None and evaluation.signal_date > bars[-1].trade_date:
        raise ValueError("规则返回了未来信号日期")
    try:
        json.dumps(
            {
                "parameters": normalized_parameters,
                "evidence": [item.to_dict() for item in evaluation.evidence],
                "metrics": evaluation.metrics,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("规则参数或判定结果无法序列化为 JSON") from exc
    return ScreeningResult(
        rule_id=rule.rule_id,
        rule_revision=rule.revision,
        parameters=normalized_parameters,
        stock=stock,
        as_of_date=as_of_date,
        data_end_date=bars[-1].trade_date,
        signal_date=evaluation.signal_date,
        outcome=(ScreeningOutcome.MATCHED if evaluation.matched else ScreeningOutcome.NOT_MATCHED),
        evidence=evaluation.evidence,
        metrics=evaluation.metrics,
        insufficient_history=evaluation.insufficient_history,
    ), backtest
