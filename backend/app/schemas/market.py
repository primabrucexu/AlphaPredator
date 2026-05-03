from __future__ import annotations

from pydantic import BaseModel, Field


class MarketSummary(BaseModel):
    trade_date: str = Field(..., description='数据日期')
    rising_count: int = Field(..., description='上涨家数')
    falling_count: int = Field(..., description='下跌家数')
    turnover_amount_billion: float = Field(..., description='成交额（亿元）')


class HotSectorItem(BaseModel):
    trade_date: str
    name: str
    trend_label: str
    heat_score: int


class MarketListRow(BaseModel):
    stock_code: str
    stock_name: str
    current_price: float
    change_amount: float
    change_pct: float
    turnover_amount_billion: float
    turnover_rate: float


class MarketOverviewResponse(BaseModel):
    summary: MarketSummary
    hot_sectors: list[HotSectorItem]
    stocks: list[MarketListRow]


class DailyBar(BaseModel):
    trade_date: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int


class StockKeyIndicators(BaseModel):
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    avg_volume_5d: int | None = None


class StockDetailResponse(BaseModel):
    trade_date: str
    stock_code: str
    stock_name: str
    current_price: float
    change_amount: float
    change_pct: float
    turnover_amount_billion: float
    turnover_rate: float
    sectors: list[str]
    ai_quick_summary: str
    key_indicators: StockKeyIndicators
    daily_bars: list[DailyBar]


# ---------------------------------------------------------------------------
# Phase 2.10: Stock resolve (direct search)
# ---------------------------------------------------------------------------


class StockCandidate(BaseModel):
    stock_code: str
    stock_name: str


class StockResolveResponse(BaseModel):
    status: str = Field(..., description='ok | not_found | ambiguous')
    stock_code: str | None = Field(None, description='Resolved code (status=ok only)')
    stock_name: str | None = Field(None, description='Stock name (status=ok only)')
    match_type: str | None = Field(None, description='code | cnspell | cnspell_prefix (status=ok only)')
    message: str | None = Field(None, description='Error message (non-ok status)')
    candidates: list[StockCandidate] = Field(default_factory=list, description='Candidates (status=ambiguous only)')
