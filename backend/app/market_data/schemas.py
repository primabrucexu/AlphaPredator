from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StockSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    code: str
    name: str


class Quote(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    previous_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    amount: float | None = None
    volume_ratio: float | None = None
    turnover_rate: float | None = None
    pe_ttm: float | None = None
    total_market_cap: float | None = None
    float_market_cap: float | None = None
    timestamp: str | None = None


class DailyBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    previous_close: float | None = None
    is_limit_up: bool = False
    is_limit_down: bool = False
