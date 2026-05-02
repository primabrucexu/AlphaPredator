from fastapi import APIRouter

from app.modules.market_data.service import market_data_service
from app.schemas.market import MarketOverviewResponse, StockDetailResponse

router = APIRouter()


@router.get('/overview', response_model=MarketOverviewResponse)
def get_market_overview() -> MarketOverviewResponse:
    return market_data_service.get_market_overview()


@router.get('/stocks/{stock_code}', response_model=StockDetailResponse)
def get_stock_detail(stock_code: str) -> StockDetailResponse:
    return market_data_service.get_stock_detail(stock_code)
