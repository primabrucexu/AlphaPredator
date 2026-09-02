from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tasks.handlers.mode_screening import TASK_TYPE as MODE_SCREENING_TASK_TYPE
from app.tasks.models import ModeScreeningStockResult, Task, TaskStatus
from app.tasks.service import load_json


REPORT_LIMIT = 10
SUPPORTED_RULE_ID = "SR001"
REPORT_STATES = ("pending_entry", "bought_today")
STATE_LABELS = {
    "pending_entry": "T点待买入",
    "bought_today": "B点刚买入",
}
RANKING_FIELDS = ("win_rate", "average_return", "maximum_return")


class SR001ReportError(ValueError):
    pass


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleMetadata(_StrictModel):
    rule_id: str = Field(min_length=1)
    rule_revision: int = Field(ge=1)
    rule_name: str = Field(min_length=1)
    source_document: str = Field(min_length=1)


class TradeSimulationSummary(_StrictModel):
    entry: str = Field(min_length=1)
    take_profit: str = Field(min_length=1)
    exit: str = Field(min_length=1)
    stop_loss: str = Field(min_length=1)


class RuleSummaryData(_StrictModel):
    purpose: str = Field(min_length=1)
    applicable_scope: str = Field(min_length=1)
    term_definitions: dict[str, str]
    selection_logic: list[str] = Field(min_length=1)
    opportunity_states: dict[str, str]
    trade_simulation_summary: TradeSimulationSummary
    insufficient_history_definition: str = Field(min_length=1)
    interpretation_limits: list[str] = Field(min_length=1)


class RuleSummary(_StrictModel):
    rule_metadata: RuleMetadata
    summary_data: RuleSummaryData


class ReportStock(_StrictModel):
    symbol: str
    code: str
    name: str
    current_state: str
    current_state_label: str
    signal_date: str | None
    data_start_date: str | None
    data_end_date: str | None
    completed_trades: int
    winning_trades: int
    losing_trades: int
    flat_trades: int
    win_rate: str | None
    average_return: str | None
    maximum_return: str | None
    minimum_return: str | None
    macd_signal_window: dict[str, Any]
    rank: int | None = Field(default=None, ge=1)


class InsufficientHistorySection(_StrictModel):
    total: int
    returned: int
    truncated: bool
    items: list[ReportStock]


class OpportunityLeaderboards(_StrictModel):
    win_rate: list[ReportStock]
    average_return: list[ReportStock]
    maximum_return: list[ReportStock]


class OpportunitySection(_StrictModel):
    state: str
    label: str
    total: int
    ranked_candidates: int
    leaderboards: OpportunityLeaderboards
    insufficient_history: InsufficientHistorySection


class ReportExecutionSummary(_StrictModel):
    scanned_stocks: int
    matched_stocks: int
    pending_entry_stocks: int
    bought_today_stocks: int
    filtered_other_states: int
    skipped_stocks: int
    failed_stocks: int


class ScreeningScope(_StrictModel):
    type: Literal["all_market", "specified_symbols"]
    symbol_count: int | None


class SR001ScreeningReport(_StrictModel):
    task_uuid: str
    task_status: str
    rule_id: str
    rule_revision: int
    parameters: dict[str, Any]
    as_of_date: str
    scope: ScreeningScope
    execution_summary: ReportExecutionSummary
    opportunities: dict[str, OpportunitySection]
    rule_summary: RuleSummary
    report_limit: int
    disclaimers: list[str]


def load_rule_summary(rule_id: str, revision: int) -> RuleSummary:
    if rule_id != SUPPORTED_RULE_ID:
        raise SR001ReportError(f"报告不支持规则：{rule_id}")
    resource = (
        files("app.screening.rule_summaries")
        .joinpath(rule_id)
        .joinpath(f"revision-{revision}.json")
    )
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
        summary = RuleSummary.model_validate(payload)
    except FileNotFoundError as exc:
        raise SR001ReportError(f"SR001 revision {revision} 尚未支持报告") from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise SR001ReportError(f"SR001 revision {revision} 规则摘要无效：{exc}") from exc
    metadata = summary.rule_metadata
    if metadata.rule_id != rule_id or metadata.rule_revision != revision:
        raise SR001ReportError("规则摘要元数据与任务规则版本不匹配")
    return summary


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _macd_signal_window(row: ModeScreeningStockResult) -> dict[str, Any]:
    for evidence in _json_list(row.evidence_json):
        if isinstance(evidence, dict) and evidence.get("condition_id") == "C1":
            values = evidence.get("values")
            return values if isinstance(values, dict) else {}
    return {}


def _report_stock(
    row: ModeScreeningStockResult,
    *,
    rank: int | None = None,
) -> ReportStock:
    return ReportStock(
        symbol=row.symbol,
        code=row.code,
        name=row.name,
        current_state=row.current_state,
        current_state_label=STATE_LABELS[row.current_state],
        signal_date=row.signal_date,
        data_start_date=row.data_start_date,
        data_end_date=row.data_end_date,
        completed_trades=row.completed_trades,
        winning_trades=row.winning_trades,
        losing_trades=row.losing_trades,
        flat_trades=row.flat_trades,
        win_rate=row.win_rate,
        average_return=row.average_return,
        maximum_return=row.maximum_return,
        minimum_return=row.minimum_return,
        macd_signal_window=_macd_signal_window(row),
        rank=rank,
    )


def _metric_value(row: ModeScreeningStockResult, field: str) -> Decimal | None:
    raw = getattr(row, field)
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise SR001ReportError(f"{row.symbol} 的 {field} 统计值无效") from exc


def _state_section(
    rows: list[ModeScreeningStockResult],
    state: str,
) -> OpportunitySection:
    state_rows = [row for row in rows if row.current_state == state]
    ranked_rows = [row for row in state_rows if not row.insufficient_history]
    leaderboards: dict[str, list[ReportStock]] = {}
    for field in RANKING_FIELDS:
        eligible = [row for row in ranked_rows if _metric_value(row, field) is not None]
        eligible.sort(key=lambda row: (-_metric_value(row, field), row.symbol))
        top = eligible[:REPORT_LIMIT]
        leaderboards[field] = [
            _report_stock(row, rank=rank)
            for rank, row in enumerate(top, start=1)
        ]
    insufficient_rows = sorted(
        (row for row in state_rows if row.insufficient_history),
        key=lambda row: row.symbol,
    )
    insufficient_items = [
        _report_stock(row) for row in insufficient_rows[:REPORT_LIMIT]
    ]
    return OpportunitySection(
        state=state,
        label=STATE_LABELS[state],
        total=len(state_rows),
        ranked_candidates=len(ranked_rows),
        leaderboards=OpportunityLeaderboards(**leaderboards),
        insufficient_history=InsufficientHistorySection(
            total=len(insufficient_rows),
            returned=len(insufficient_items),
            truncated=len(insufficient_rows) > REPORT_LIMIT,
            items=insufficient_items,
        ),
    )


def build_sr001_screening_report(
    db: Session,
    task: Task,
) -> SR001ScreeningReport:
    if task.task_type != MODE_SCREENING_TASK_TYPE:
        raise SR001ReportError("该任务不是模式选股分析任务")
    if task.status != TaskStatus.SUCCEEDED.value:
        raise SR001ReportError("只有成功完成的任务才能生成报告")
    task_input = load_json(task.input_json)
    rule_id = task_input.get("rule_id")
    revision = task_input.get("rule_revision")
    if rule_id != SUPPORTED_RULE_ID:
        raise SR001ReportError("该任务不是 SR001 规则任务")
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise SR001ReportError("任务规则版本无效")
    rule_summary = load_rule_summary(rule_id, revision)
    as_of_date = task_input.get("as_of_date")
    if not isinstance(as_of_date, str) or not as_of_date:
        raise SR001ReportError("任务扫描日期无效")
    rows = list(db.scalars(
        select(ModeScreeningStockResult)
        .where(ModeScreeningStockResult.task_id == task.id)
        .order_by(ModeScreeningStockResult.symbol)
    ).all())
    report_rows = [row for row in rows if row.current_state in REPORT_STATES]
    task_result = load_json(task.result_json)
    symbols = task_input.get("symbols")
    scope = ScreeningScope(
        type="specified_symbols" if isinstance(symbols, list) else "all_market",
        symbol_count=len(symbols) if isinstance(symbols, list) else None,
    )
    sections = {
        state: _state_section(report_rows, state) for state in REPORT_STATES
    }
    return SR001ScreeningReport(
        task_uuid=task.uuid,
        task_status=task.status,
        rule_id=rule_id,
        rule_revision=revision,
        parameters=dict(task_input.get("parameters") or {}),
        as_of_date=as_of_date,
        scope=scope,
        execution_summary=ReportExecutionSummary(
            scanned_stocks=int(task_result.get("stock_count") or task.total_items),
            matched_stocks=len(rows),
            pending_entry_stocks=sections["pending_entry"].total,
            bought_today_stocks=sections["bought_today"].total,
            filtered_other_states=len(rows) - len(report_rows),
            skipped_stocks=int(task_result.get("skipped_stocks") or 0),
            failed_stocks=int(task_result.get("failed_stocks") or 0),
        ),
        opportunities=sections,
        rule_summary=rule_summary,
        report_limit=REPORT_LIMIT,
        disclaimers=[
            "本报告是规则执行结果的精简表达，不构成投资建议。",
            "历史表现不代表未来收益。",
        ],
    )


__all__ = [
    "REPORT_LIMIT",
    "SR001ReportError",
    "SR001ScreeningReport",
    "build_sr001_screening_report",
    "load_rule_summary",
]
