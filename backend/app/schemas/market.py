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
    pre_close: float | None = None
    change_amount: float | None = None
    change_pct: float | None = None
    volume: int
    turnover_amount_billion: float | None = None
    turnover_rate: float | None = None
    is_up_limit: bool = False
    is_down_limit: bool = False


class StockKeyIndicators(BaseModel):
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    avg_volume_5d: int | None = None


class StockTags(BaseModel):
    industry: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    region: list[str] = Field(default_factory=list)


class StockIndicatorSeries(BaseModel):
    """Per-bar indicator series aligned with daily_bars (None where history insufficient)."""

    ma5: list[float | None] = Field(default_factory=list)
    ma10: list[float | None] = Field(default_factory=list)
    ma20: list[float | None] = Field(default_factory=list)
    ma60: list[float | None] = Field(default_factory=list)
    volume_ma5: list[float | None] = Field(default_factory=list)
    volume_ma10: list[float | None] = Field(default_factory=list)
    volume_ma20: list[float | None] = Field(default_factory=list)
    kdj_k: list[float | None] = Field(default_factory=list)
    kdj_d: list[float | None] = Field(default_factory=list)
    kdj_j: list[float | None] = Field(default_factory=list)
    macd_dif: list[float | None] = Field(default_factory=list)
    macd_dea: list[float | None] = Field(default_factory=list)
    macd_hist: list[float | None] = Field(default_factory=list)
    rsi6: list[float | None] = Field(default_factory=list)
    rsi12: list[float | None] = Field(default_factory=list)
    rsi24: list[float | None] = Field(default_factory=list)


class StockDetailResponse(BaseModel):
    trade_date: str
    stock_code: str
    stock_name: str
    current_price: float
    change_amount: float
    change_pct: float
    open_price: float = 0.0
    prev_close: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    turnover_amount_billion: float
    turnover_rate: float
    sectors: list[str]
    tags: StockTags = Field(default_factory=StockTags)
    ai_quick_summary: str
    key_indicators: StockKeyIndicators
    daily_bars: list[DailyBar]
    indicators: StockIndicatorSeries = Field(default_factory=StockIndicatorSeries)
    has_more_before: bool = False


class StockBarsRangeResponse(BaseModel):
    stock_code: str
    months: int
    end_date: str | None = None
    has_more_before: bool = False
    daily_bars: list[DailyBar] = Field(default_factory=list)
    indicators: StockIndicatorSeries = Field(default_factory=StockIndicatorSeries)


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


# ---------------------------------------------------------------------------
# Phase 2: Sentiment overview
# ---------------------------------------------------------------------------


class HotSectorHistorySector(BaseModel):
    name: str
    heat_score: int
    trend_tag: str | None = None
    trend_label: str | None = None
    rank_today: int | None = None
    max_board_count: int | None = None


class HotSectorHistoryDay(BaseModel):
    trade_date: str
    sectors: list[HotSectorHistorySector] = Field(default_factory=list)


class HotSectorHistoryResponse(BaseModel):
    trade_dates: list[str] = Field(default_factory=list)
    days: list[HotSectorHistoryDay] = Field(default_factory=list)


class LimitUpStreakItem(BaseModel):
    trade_date: str
    stock_code: str
    stock_name: str
    board_count: int
    limit_up_time: str
    hot_theme: str


class LimitUpStreaksResponse(BaseModel):
    trade_date: str
    streaks: list[LimitUpStreakItem] = Field(default_factory=list)


class HotReviewImageItem(BaseModel):
    url: str
    source_file: str


class HotReviewImagesResponse(BaseModel):
    trade_date: str
    images: list[HotReviewImageItem] = Field(default_factory=list)
