from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database.session import get_session

from .provider.base import MarketDataError, normalize_symbol
from .service import StockService


router = APIRouter()


def _provider(request: Request):
    return request.app.state.market_provider


def _market_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/stocks/search")
def search_stocks(request: Request, q: str = Query(min_length=1), db: Session = Depends(get_session)):
    try:
        return StockService(_provider(request)).search(db, q)
    except (MarketDataError, ValueError) as exc:
        raise _market_error(exc) from exc


@router.post("/stocks/sync-directory")
def sync_stock_directory(request: Request, db: Session = Depends(get_session)):
    try:
        return {"count": StockService(_provider(request)).sync_directory(db)}
    except MarketDataError as exc:
        raise _market_error(exc) from exc


@router.get("/market/stocks/{symbol}/quote")
def quote(request: Request, symbol: str):
    try:
        return _provider(request).get_quote(normalize_symbol(symbol))
    except (MarketDataError, ValueError) as exc:
        raise _market_error(exc) from exc


@router.get("/market/stocks/{symbol}/daily-bars")
def daily_bars(
    request: Request,
    symbol: str,
    count: int = Query(250, ge=20, le=1000),
    start_date: date | None = None,
    end_date: date | None = None,
):
    try:
        if (start_date is None) != (end_date is None):
            raise ValueError("start_date 和 end_date 必须同时提供")
        if start_date is not None and end_date is not None:
            if end_date < start_date:
                raise ValueError("end_date 不能早于 start_date")
            if (end_date - start_date).days > 366:
                raise ValueError("单次最多查询 366 天")
        bars = _provider(request).get_daily_bars(symbol, count, start_date, end_date)
        return {"symbol": normalize_symbol(symbol), "bars": bars}
    except (MarketDataError, ValueError) as exc:
        raise _market_error(exc) from exc
