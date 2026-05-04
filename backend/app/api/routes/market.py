from fastapi import APIRouter, Query

from app.modules.market_data.service import market_data_service
from app.schemas.market import MarketOverviewResponse, StockCandidate, StockDetailResponse, StockResolveResponse

router = APIRouter()


@router.get('/overview', response_model=MarketOverviewResponse)
def get_market_overview() -> MarketOverviewResponse:
    return market_data_service.get_market_overview()


@router.get('/stocks/{stock_code}', response_model=StockDetailResponse)
def get_stock_detail(stock_code: str) -> StockDetailResponse:
    return market_data_service.get_stock_detail(stock_code)


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
