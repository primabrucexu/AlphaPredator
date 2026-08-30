from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskRead(BaseModel):
    id: int
    uuid: str
    task_type: str
    scheduling_policy: str
    title: str
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    progress: int | None
    status_message: str
    input: dict[str, Any]
    result: dict[str, Any]
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime
    cancel_requested_at: datetime | None


class TaskItemRead(BaseModel):
    id: int
    task_id: int
    sequence: int
    title: str
    status: str
    current: int | None
    total: int | None
    progress: int | None
    status_message: str
    result: dict[str, Any]
    error: str
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class TaskPage(BaseModel):
    items: list[TaskRead]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class TaskItemPage(BaseModel):
    items: list[TaskItemRead]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class ActiveTaskCount(BaseModel):
    count: int


class MarketDailyBarsTaskCreate(BaseModel):
    mode: Literal["incremental", "full"]


class MarketDailyBarsCoverage(BaseModel):
    start_date: date | None
    end_date: date | None


class ScreeningRuleTaskCreate(BaseModel):
    rule_id: str = Field(min_length=1)
    rule_revision: int = Field(ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    as_of_date: date
    symbols: list[str] | None = Field(default=None, min_length=1)


class IndividualBacktestTaskCreate(BaseModel):
    rule_id: str = Field(min_length=1)
    rule_revision: int = Field(ge=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    symbol: str = Field(min_length=1)
    start_date: date
    end_date: date


class ModeScreeningStockResultRead(BaseModel):
    id: int
    symbol: str
    code: str
    name: str
    as_of_date: date
    data_start_date: date | None
    data_end_date: date | None
    signal_date: date | None
    insufficient_history: bool
    evidence: list[dict[str, Any]]
    metrics: dict[str, Any]
    backtest_status: str
    current_state: str
    completed_trades: int
    winning_trades: int
    losing_trades: int
    flat_trades: int
    win_rate: str | None
    average_return: str | None
    maximum_return: str | None
    minimum_return: str | None
    open_trade: dict[str, Any] | None
    pending_orders: list[dict[str, Any]]


class ModeScreeningStockResultPage(BaseModel):
    items: list[ModeScreeningStockResultRead]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class ModeScreeningSaleResultRead(BaseModel):
    date: date
    reason_id: str
    price: str
    fraction_of_original: str
    return_rate: str


class ModeScreeningTradeResultRead(BaseModel):
    id: int
    sequence: int
    signal_date: date
    buy_date: date
    buy_price: str
    realized_return: str
    sells: list[ModeScreeningSaleResultRead]


class ModeScreeningTradeResultPage(BaseModel):
    items: list[ModeScreeningTradeResultRead]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
