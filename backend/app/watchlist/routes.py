from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import Stock, StockTag, Tag, WatchlistItem
from app.database.session import get_session
from app.market_data.provider.base import normalize_symbol

from .schemas import TagCreate, TagOrderInput, TagStockOrderInput, WatchlistAdd


router = APIRouter()


def _watchlist_rows(db: Session) -> list[dict]:
    items = db.scalars(select(WatchlistItem).order_by(WatchlistItem.id)).all()
    symbols = {item.symbol for item in items}
    stocks = db.scalars(select(Stock).where(Stock.symbol.in_(symbols))).all() if symbols else []
    stock_names = {stock.symbol: stock.name for stock in stocks}
    tags: dict[str, list[dict]] = {symbol: [] for symbol in symbols}
    if symbols:
        rows = db.execute(
            select(StockTag, Tag).join(Tag, Tag.id == StockTag.tag_id)
            .where(StockTag.symbol.in_(symbols)).order_by(Tag.sort_order, Tag.id)
        ).all()
        for association, tag in rows:
            tags[association.symbol].append({"id": tag.id, "name": tag.name, "sort_order": tag.sort_order,
                                             "stock_sort_order": association.sort_order})
    return [{"id": item.id, "symbol": item.symbol, "code": item.symbol[:6],
             "name": stock_names.get(item.symbol, ""), "tags": tags[item.symbol]} for item in items]


@router.get("/watchlist/items")
def list_watchlist_items(db: Session = Depends(get_session)):
    return _watchlist_rows(db)


@router.post("/watchlist/items", status_code=status.HTTP_201_CREATED)
def add_watchlist_item(payload: WatchlistAdd, db: Session = Depends(get_session)):
    try:
        symbol = normalize_symbol(payload.symbol)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    item = WatchlistItem(symbol=symbol)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "该股票已在自选中") from exc
    db.refresh(item)
    return next(row for row in _watchlist_rows(db) if row["id"] == item.id)


@router.delete("/watchlist/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist_item(item_id: int, db: Session = Depends(get_session)):
    item = db.get(WatchlistItem, item_id)
    if not item:
        raise HTTPException(404, "自选股不存在")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@router.get("/stocks/{symbol}/tags")
def list_tags(symbol: str, db: Session = Depends(get_session)):
    normalized = normalize_symbol(symbol)
    return [{"id": tag.id, "name": tag.name, "sort_order": tag.sort_order} for tag in db.scalars(
        select(Tag).join(StockTag, StockTag.tag_id == Tag.id)
        .where(StockTag.symbol == normalized).order_by(Tag.sort_order, Tag.id)
    ).all()]


@router.post("/stocks/{symbol}/tags", status_code=status.HTTP_201_CREATED)
def add_tag(symbol: str, payload: TagCreate, db: Session = Depends(get_session)):
    normalized = normalize_symbol(symbol)
    name = payload.name.strip()
    if not db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == normalized)):
        db.add(WatchlistItem(symbol=normalized))
    tag = db.scalar(select(Tag).where(Tag.name == name))
    if not tag:
        current_max = db.scalar(select(func.max(Tag.sort_order)))
        next_order = (current_max if current_max is not None else -1) + 1
        tag = Tag(name=name, sort_order=next_order)
        db.add(tag)
        db.flush()
    current_max = db.scalar(select(func.max(StockTag.sort_order)).where(StockTag.tag_id == tag.id))
    db.add(StockTag(symbol=normalized, tag_id=tag.id,
                    sort_order=(current_max if current_max is not None else -1) + 1))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "标签已存在") from exc
    return {"id": tag.id, "name": tag.name, "sort_order": tag.sort_order}


@router.delete("/stocks/{symbol}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(symbol: str, tag_id: int, db: Session = Depends(get_session)):
    association = db.scalar(select(StockTag).where(
        StockTag.symbol == normalize_symbol(symbol), StockTag.tag_id == tag_id
    ))
    if not association:
        raise HTTPException(404, "标签不存在")
    db.delete(association)
    db.commit()
    return Response(status_code=204)


@router.get("/tags")
def list_tag_catalog(db: Session = Depends(get_session)):
    rows = db.execute(
        select(Tag, func.count(WatchlistItem.id))
        .outerjoin(StockTag, StockTag.tag_id == Tag.id)
        .outerjoin(WatchlistItem, WatchlistItem.symbol == StockTag.symbol)
        .group_by(Tag.id).order_by(Tag.sort_order, Tag.id)
    ).all()
    return [{"id": tag.id, "name": tag.name, "sort_order": tag.sort_order,
             "stock_count": count} for tag, count in rows]


@router.post("/tags", status_code=status.HTTP_201_CREATED)
def create_global_tag(payload: TagCreate, db: Session = Depends(get_session)):
    current_max = db.scalar(select(func.max(Tag.sort_order)))
    tag = Tag(name=payload.name.strip(), sort_order=(current_max if current_max is not None else -1) + 1)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "标签名称已存在") from exc
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "sort_order": tag.sort_order}


@router.put("/tags/order")
def reorder_tags(payload: TagOrderInput, db: Session = Depends(get_session)):
    tags = db.scalars(select(Tag)).all()
    if len(payload.tag_ids) != len(set(payload.tag_ids)) or set(payload.tag_ids) != {tag.id for tag in tags}:
        raise HTTPException(400, "排序必须包含全部标签且不能重复")
    positions = {tag_id: index for index, tag_id in enumerate(payload.tag_ids)}
    for tag in tags:
        tag.sort_order = positions[tag.id]
    db.commit()
    return {"tag_ids": payload.tag_ids}


@router.put("/tags/{tag_id}/stocks/order")
def reorder_tag_stocks(tag_id: int, payload: TagStockOrderInput, db: Session = Depends(get_session)):
    if not db.get(Tag, tag_id):
        raise HTTPException(404, "标签不存在")
    try:
        symbols = [normalize_symbol(symbol) for symbol in payload.symbols]
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    associations = db.scalars(select(StockTag).where(StockTag.tag_id == tag_id)).all()
    current_symbols = {association.symbol for association in associations}
    if len(symbols) != len(set(symbols)) or set(symbols) != current_symbols:
        raise HTTPException(400, "排序必须包含该标签下的全部股票且不能重复")
    positions = {symbol: index for index, symbol in enumerate(symbols)}
    for association in associations:
        association.sort_order = positions[association.symbol]
    db.commit()
    return {"symbols": symbols}


@router.put("/tags/{tag_id}")
def rename_tag(tag_id: int, payload: TagCreate, db: Session = Depends(get_session)):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "标签不存在")
    tag.name = payload.name.strip()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "标签名称已存在") from exc
    return {"id": tag.id, "name": tag.name, "sort_order": tag.sort_order}


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_tag(tag_id: int, db: Session = Depends(get_session)):
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "标签不存在")
    db.delete(tag)
    db.commit()
    return Response(status_code=204)
