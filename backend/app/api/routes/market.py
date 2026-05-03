from fastapi import APIRouter, Query

from app.modules.market_data.service import market_data_service
from app.schemas.market import MarketOverviewResponse, StockDetailResponse, StockResolveResponse

router = APIRouter()


@router.get('/overview', response_model=MarketOverviewResponse)
def get_market_overview() -> MarketOverviewResponse:
    return market_data_service.get_market_overview()


@router.get('/stocks/{stock_code}', response_model=StockDetailResponse)
def get_stock_detail(stock_code: str) -> StockDetailResponse:
    return market_data_service.get_stock_detail(stock_code)


@router.get('/resolve', response_model=StockResolveResponse)
def resolve_stock(q: str = Query(..., min_length=1, description='股票代码或拼音简称')) -> StockResolveResponse:
    """
    Resolve a user input (stock code or pinyin abbreviation) to a unique stock.

    Returns status='ok' with stock_code/stock_name on unique match,
    status='not_found' when no match, or status='ambiguous' with candidates.
    """
    return market_data_service.resolve_stock(q)
