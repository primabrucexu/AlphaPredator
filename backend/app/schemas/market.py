from pydantic import BaseModel, Field


class MarketSummary(BaseModel):
    trade_date: str = Field(..., description='数据日期')
    rising_count: int = Field(..., description='上涨家数')
    falling_count: int = Field(..., description='下跌家数')
    turnover_amount_billion: float = Field(..., description='成交额（亿元）')


class HotSectorItem(BaseModel):
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
