from fastapi import APIRouter, Query

from app.modules.market_data.service import market_data_service
from app.schemas.market import (
    HotSectorAggregatedResponse,
    HotSectorHistoryResponse,
    HotReviewImagesResponse,
    HotReviewTableResponse,
    LimitUpStreaksResponse,
    MarketOverviewResponse,
    StockBarsRangeResponse,
    StockCandidate,
    StockDetailResponse,
    StockResolveResponse,
)

router = APIRouter()


@router.get('/overview', response_model=MarketOverviewResponse)
def get_market_overview() -> MarketOverviewResponse:
    return market_data_service.get_market_overview()


@router.get('/stocks/{stock_code}', response_model=StockDetailResponse)
def get_stock_detail(stock_code: str) -> StockDetailResponse:
    return market_data_service.get_stock_detail(stock_code)


@router.get('/stocks/{stock_code}/bars', response_model=StockBarsRangeResponse)
def get_stock_bars_range(
        stock_code: str,
        months: int = Query(6, ge=1, le=120, description='时间窗口（月）'),
        end_date: str | None = Query(None, description='窗口结束日期，格式 YYYY-MM-DD，默认最新交易日'),
) -> StockBarsRangeResponse:
    return market_data_service.get_stock_bars_range(stock_code, months=months, end_date=end_date)


@router.get('/search', response_model=list[StockCandidate])
def search_stocks(
    q: str = Query(..., min_length=1, max_length=20, description='股票代码或拼音简称前缀'),
    limit: int = Query(10, ge=1, le=30, description='最多返回条数'),
) -> list[StockCandidate]:
    """Prefix search for autocomplete: returns up to *limit* matching stocks."""
    return market_data_service.search_stocks(q, limit=limit)


@router.get('/resolve', response_model=StockResolveResponse)
def resolve_stock(q: str = Query(..., min_length=1, description='股票代码或拼音简称')) -> StockResolveResponse:
    """
    Resolve a user input (stock code or pinyin abbreviation) to a unique stock.

    Returns status='ok' with stock_code/stock_name on unique match,
    status='not_found' when no match, or status='ambiguous' with candidates.
    """
    return market_data_service.resolve_stock(q)


@router.get('/hot-sector-history', response_model=HotSectorHistoryResponse)
def get_hot_sector_history(
    days: int = Query(7, ge=1, le=60, description='回看最近交易日数量'),
    exclude_st: bool = Query(True, description='是否排除ST股票'),
) -> HotSectorHistoryResponse:
    return market_data_service.get_hot_sector_history(days=days, exclude_st=exclude_st)


@router.get('/limit-up-streaks', response_model=LimitUpStreaksResponse)
def get_limit_up_streaks(
    trade_date: str | None = Query(None, description='交易日（YYYY-MM-DD），默认最新有数据交易日'),
    min_boards: int = Query(2, ge=1, le=20, description='最小连板数阈值'),
    exclude_st: bool = Query(True, description='是否排除ST股票'),
) -> LimitUpStreaksResponse:
    return market_data_service.get_limit_up_streaks(trade_date=trade_date, min_boards=min_boards, exclude_st=exclude_st)


@router.get('/hot-review-images', response_model=HotReviewImagesResponse)
def get_hot_review_images(
        trade_date: str | None = Query(None, description='交易日（YYYY-MM-DD），默认最新有数据交易日'),
) -> HotReviewImagesResponse:
    return market_data_service.get_hot_review_images(trade_date=trade_date)


@router.get('/hot-review-table', response_model=HotReviewTableResponse)
def get_hot_review_table(
        trade_date: str | None = Query(None, description='交易日（YYYY-MM-DD），默认最新有数据交易日'),
        exclude_st: bool = Query(True, description='是否排除ST股票'),
) -> HotReviewTableResponse:
    return market_data_service.get_hot_review_table(trade_date=trade_date, exclude_st=exclude_st)


@router.get('/hot-sector-aggregated', response_model=HotSectorAggregatedResponse)
def get_hot_sector_aggregated(
    exclude_st: bool = Query(True, description='是否排除ST股票'),
) -> HotSectorAggregatedResponse:
    """返回 5/10/20 交易日内各板块去重涨停家数（同一只股票多日只统计一次）。"""
    return market_data_service.get_hot_sector_aggregated(windows=[5, 10, 20], exclude_st=exclude_st)


