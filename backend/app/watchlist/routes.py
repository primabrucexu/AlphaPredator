from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database.models import StockTag, WatchlistGroup, WatchlistItem
from app.database.session import get_session
from app.market_data.provider.base import normalize_symbol

from .schemas import GroupCreate, TagCreate, WatchlistAdd, WatchlistMove


router = APIRouter()


@router.get("/watchlist/groups")
def list_groups(db: Session = Depends(get_session)):
    groups = db.scalars(
        select(WatchlistGroup).options(selectinload(WatchlistGroup.items)).order_by(WatchlistGroup.id)
    ).all()
    return [{"id": g.id, "name": g.name, "is_default": g.is_default,
             "items": [{"id": i.id, "symbol": i.symbol} for i in g.items]} for g in groups]


@router.post("/watchlist/groups", status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, db: Session = Depends(get_session)):
    group = WatchlistGroup(name=payload.name.strip())
    db.add(group)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "分组名称已存在") from exc
    db.refresh(group)
    return {"id": group.id, "name": group.name, "is_default": group.is_default, "items": []}


@router.put("/watchlist/groups/{group_id}")
def rename_group(group_id: int, payload: GroupCreate, db: Session = Depends(get_session)):
    group = db.get(WatchlistGroup, group_id)
    if not group:
        raise HTTPException(404, "分组不存在")
    group.name = payload.name.strip()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "分组名称已存在") from exc
    return {"id": group.id, "name": group.name, "is_default": group.is_default}


@router.delete("/watchlist/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, db: Session = Depends(get_session)):
    group = db.scalar(
        select(WatchlistGroup).options(selectinload(WatchlistGroup.items)).where(WatchlistGroup.id == group_id)
    )
    if not group:
        raise HTTPException(404, "分组不存在")
    if group.is_default:
        raise HTTPException(400, "默认分组不能删除")
    default = db.scalar(select(WatchlistGroup).where(WatchlistGroup.is_default.is_(True)))
    existing = {item.symbol for item in default.items}
    for item in list(group.items):
        if item.symbol in existing:
            db.delete(item)
        else:
            item.group_id = default.id
    db.delete(group)
    db.commit()
    return Response(status_code=204)


@router.post("/watchlist/groups/{group_id}/items", status_code=status.HTTP_201_CREATED)
def add_watchlist_item(group_id: int, payload: WatchlistAdd, db: Session = Depends(get_session)):
    if not db.get(WatchlistGroup, group_id):
        raise HTTPException(404, "分组不存在")
    try:
        symbol = normalize_symbol(payload.symbol)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    item = WatchlistItem(group_id=group_id, symbol=symbol)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "该股票已在此分组") from exc
    db.refresh(item)
    return {"id": item.id, "group_id": item.group_id, "symbol": item.symbol}


@router.put("/watchlist/items/{item_id}")
def move_watchlist_item(item_id: int, payload: WatchlistMove, db: Session = Depends(get_session)):
    item = db.get(WatchlistItem, item_id)
    if not item or not db.get(WatchlistGroup, payload.group_id):
        raise HTTPException(404, "自选股或目标分组不存在")
    item.group_id = payload.group_id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "目标分组中已存在该股票") from exc
    return {"id": item.id, "group_id": item.group_id, "symbol": item.symbol}


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
    return [{"id": row.id, "name": row.name} for row in db.scalars(
        select(StockTag).where(StockTag.symbol == normalized).order_by(StockTag.id)
    ).all()]


@router.post("/stocks/{symbol}/tags", status_code=status.HTTP_201_CREATED)
def add_tag(symbol: str, payload: TagCreate, db: Session = Depends(get_session)):
    tag = StockTag(symbol=normalize_symbol(symbol), name=payload.name.strip())
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "标签已存在") from exc
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name}


@router.delete("/stocks/{symbol}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(symbol: str, tag_id: int, db: Session = Depends(get_session)):
    tag = db.get(StockTag, tag_id)
    if not tag or tag.symbol != normalize_symbol(symbol):
        raise HTTPException(404, "标签不存在")
    db.delete(tag)
    db.commit()
    return Response(status_code=204)
