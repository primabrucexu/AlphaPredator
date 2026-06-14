from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StockLinkageBacktestRequest:
    a_select_mode: str
    start_date: str
    end_date: str
    manual_a_full_code: str | None = None
    hot_top_n: int | None = None
    min_sample_count: int = 30
    job_name: str | None = None


@dataclass(frozen=True)
class StockLinkageBacktestSummary:
    job_id: str
    status: str
    trigger_event_count: int
    baseline_count: int
    result_count: int


@dataclass(frozen=True)
class StockLinkageBacktestJob:
    job_id: str
    job_name: str | None
    a_select_mode: str
    manual_a_full_code: str | None
    hot_top_n: int | None
    start_date: str
    end_date: str
    min_sample_count: int
    status: str
    error_message: str | None
    created_at: str
    updated_at: str
    finished_at: str | None


@dataclass(frozen=True)
class FiveMinuteBar:
    full_code: str
    trade_date: str
    trade_day: str
    bar_index: int
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    is_stop: bool


@dataclass(frozen=True)
class TriggerEvent:
    a_full_code: str
    trade_date: str
    bar_time: str
    bar_index: int
    trigger_type: str
    trigger_threshold: float
    trigger_return: float
