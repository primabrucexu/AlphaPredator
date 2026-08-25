from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_session

from . import service
from .schemas import TagCreate, TagOrderInput, TagStockOrderInput, WatchlistAdd


router = APIRouter()


def _raise_http(exc: service.WatchlistServiceError) -> None:
    if isinstance(exc, service.WatchlistNotFoundError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, service.WatchlistConflictError):
        raise HTTPException(409, str(exc)) from exc
    raise HTTPException(400, str(exc)) from exc


@router.get("/watchlist/items")
def list_watchlist_items(db: Session = Depends(get_session)):
    return service.list_watchlist(db)


@router.post("/watchlist/items", status_code=status.HTTP_201_CREATED)
def add_watchlist_item(payload: WatchlistAdd, db: Session = Depends(get_session)):
    try:
        return service.add_watchlist_stock(db, payload.symbol)
    except service.WatchlistValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except service.WatchlistServiceError as exc:
        _raise_http(exc)


@router.delete("/watchlist/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist_item(item_id: int, db: Session = Depends(get_session)):
    try:
        service.remove_watchlist_item(db, item_id)
    except service.WatchlistServiceError as exc:
        _raise_http(exc)
    return Response(status_code=204)


@router.get("/stocks/{symbol}/tags")
def list_tags(symbol: str, db: Session = Depends(get_session)):
    try:
        return service.list_stock_tags(db, symbol)
    except service.WatchlistServiceError as exc:
        _raise_http(exc)


@router.post("/stocks/{symbol}/tags", status_code=status.HTTP_201_CREATED)
def add_tag(symbol: str, payload: TagCreate, db: Session = Depends(get_session)):
    try:
        return service.attach_tag_name_to_stock(db, symbol, payload.name)
    except service.WatchlistServiceError as exc:
        _raise_http(exc)


@router.delete("/stocks/{symbol}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(symbol: str, tag_id: int, db: Session = Depends(get_session)):
    try:
        service.detach_tag_from_stock(db, symbol, tag_id)
    except service.WatchlistServiceError as exc:
        _raise_http(exc)
    return Response(status_code=204)


@router.get("/tags")
def list_tag_catalog(db: Session = Depends(get_session)):
    return service.list_tags(db)


@router.post("/tags", status_code=status.HTTP_201_CREATED)
def create_global_tag(payload: TagCreate, db: Session = Depends(get_session)):
    try:
        return service.create_tag(db, payload.name)
    except service.WatchlistServiceError as exc:
        _raise_http(exc)


@router.put("/tags/order")
def reorder_tags(payload: TagOrderInput, db: Session = Depends(get_session)):
    try:
        return {"tag_ids": service.reorder_tags(db, payload.tag_ids)}
    except service.WatchlistServiceError as exc:
        _raise_http(exc)


@router.put("/tags/{tag_id}/stocks/order")
def reorder_tag_stocks(tag_id: int, payload: TagStockOrderInput, db: Session = Depends(get_session)):
    try:
        return {"symbols": service.reorder_tag_stocks(db, tag_id, payload.symbols)}
    except service.WatchlistServiceError as exc:
        _raise_http(exc)


@router.put("/tags/{tag_id}")
def rename_tag(tag_id: int, payload: TagCreate, db: Session = Depends(get_session)):
    try:
        return service.rename_tag(db, tag_id, payload.name)
    except service.WatchlistServiceError as exc:
        _raise_http(exc)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_tag(tag_id: int, db: Session = Depends(get_session)):
    try:
        service.delete_tag(db, tag_id)
    except service.WatchlistServiceError as exc:
        _raise_http(exc)
    return Response(status_code=204)
