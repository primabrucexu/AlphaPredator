from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import Stock, StockTag, Tag, WatchlistItem
from app.market_data.provider.base import normalize_symbol


class WatchlistServiceError(ValueError):
    pass


class WatchlistNotFoundError(WatchlistServiceError):
    pass


class WatchlistConflictError(WatchlistServiceError):
    pass


class WatchlistValidationError(WatchlistServiceError):
    pass


def _symbol(value: str) -> str:
    try:
        return normalize_symbol(value)
    except ValueError as exc:
        raise WatchlistValidationError(str(exc)) from exc


def _tag_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise WatchlistValidationError("标签名称不能为空")
    if len(name) > 64:
        raise WatchlistValidationError("标签名称不能超过 64 个字符")
    return name


def _tag_dict(tag: Tag) -> dict:
    return {"id": tag.id, "name": tag.name, "sort_order": tag.sort_order}


def list_watchlist(db: Session) -> list[dict]:
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
            tags[association.symbol].append({
                **_tag_dict(tag),
                "stock_sort_order": association.sort_order,
            })
    return [{
        "id": item.id,
        "symbol": item.symbol,
        "code": item.symbol[:6],
        "name": stock_names.get(item.symbol, ""),
        "tags": tags[item.symbol],
    } for item in items]


def add_watchlist_stock(db: Session, symbol: str) -> dict:
    normalized = _symbol(symbol)
    item = WatchlistItem(symbol=normalized)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WatchlistConflictError("该股票已在自选中") from exc
    db.refresh(item)
    return next(row for row in list_watchlist(db) if row["id"] == item.id)


def remove_watchlist_item(db: Session, item_id: int) -> None:
    item = db.get(WatchlistItem, item_id)
    if item is None:
        raise WatchlistNotFoundError("自选股不存在")
    db.execute(delete(StockTag).where(StockTag.symbol == item.symbol))
    db.delete(item)
    db.commit()


def remove_watchlist_stock(db: Session, symbol: str) -> str:
    normalized = _symbol(symbol)
    item = db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == normalized))
    if item is None:
        raise WatchlistNotFoundError("自选股不存在")
    db.execute(delete(StockTag).where(StockTag.symbol == normalized))
    db.delete(item)
    db.commit()
    return normalized


def list_stock_tags(db: Session, symbol: str) -> list[dict]:
    normalized = _symbol(symbol)
    return [_tag_dict(tag) for tag in db.scalars(
        select(Tag).join(StockTag, StockTag.tag_id == Tag.id)
        .where(StockTag.symbol == normalized).order_by(Tag.sort_order, Tag.id)
    ).all()]


def _attach(db: Session, normalized: str, tag: Tag) -> dict:
    if db.scalar(select(WatchlistItem).where(WatchlistItem.symbol == normalized)) is None:
        db.add(WatchlistItem(symbol=normalized))
    current_max = db.scalar(select(func.max(StockTag.sort_order)).where(StockTag.tag_id == tag.id))
    db.add(StockTag(
        symbol=normalized,
        tag_id=tag.id,
        sort_order=(current_max if current_max is not None else -1) + 1,
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WatchlistConflictError("标签已关联该股票") from exc
    return _tag_dict(tag)


def attach_tag_to_stock(db: Session, symbol: str, tag_id: int) -> dict:
    normalized = _symbol(symbol)
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise WatchlistNotFoundError("标签不存在")
    return _attach(db, normalized, tag)


def attach_tag_name_to_stock(db: Session, symbol: str, name: str) -> dict:
    normalized = _symbol(symbol)
    clean_name = _tag_name(name)
    tag = db.scalar(select(Tag).where(Tag.name == clean_name))
    if tag is None:
        current_max = db.scalar(select(func.max(Tag.sort_order)))
        tag = Tag(
            name=clean_name,
            sort_order=(current_max if current_max is not None else -1) + 1,
        )
        db.add(tag)
        db.flush()
    return _attach(db, normalized, tag)


def detach_tag_from_stock(db: Session, symbol: str, tag_id: int) -> None:
    normalized = _symbol(symbol)
    association = db.scalar(select(StockTag).where(
        StockTag.symbol == normalized,
        StockTag.tag_id == tag_id,
    ))
    if association is None:
        raise WatchlistNotFoundError("标签关联不存在")
    db.delete(association)
    db.commit()


def list_tags(db: Session) -> list[dict]:
    rows = db.execute(
        select(Tag, func.count(WatchlistItem.id))
        .outerjoin(StockTag, StockTag.tag_id == Tag.id)
        .outerjoin(WatchlistItem, WatchlistItem.symbol == StockTag.symbol)
        .group_by(Tag.id).order_by(Tag.sort_order, Tag.id)
    ).all()
    return [{**_tag_dict(tag), "stock_count": count} for tag, count in rows]


def create_tag(db: Session, name: str) -> dict:
    current_max = db.scalar(select(func.max(Tag.sort_order)))
    tag = Tag(
        name=_tag_name(name),
        sort_order=(current_max if current_max is not None else -1) + 1,
    )
    db.add(tag)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WatchlistConflictError("标签名称已存在") from exc
    db.refresh(tag)
    return _tag_dict(tag)


def reorder_tags(db: Session, tag_ids: list[int]) -> list[int]:
    tags = db.scalars(select(Tag)).all()
    if len(tag_ids) != len(set(tag_ids)) or set(tag_ids) != {tag.id for tag in tags}:
        raise WatchlistValidationError("排序必须包含全部标签且不能重复")
    positions = {tag_id: index for index, tag_id in enumerate(tag_ids)}
    for tag in tags:
        tag.sort_order = positions[tag.id]
    db.commit()
    return tag_ids


def reorder_tag_stocks(db: Session, tag_id: int, symbols: list[str]) -> list[str]:
    if db.get(Tag, tag_id) is None:
        raise WatchlistNotFoundError("标签不存在")
    normalized_symbols = [_symbol(symbol) for symbol in symbols]
    associations = db.scalars(select(StockTag).where(StockTag.tag_id == tag_id)).all()
    current_symbols = {association.symbol for association in associations}
    if (
        len(normalized_symbols) != len(set(normalized_symbols))
        or set(normalized_symbols) != current_symbols
    ):
        raise WatchlistValidationError("排序必须包含该标签下的全部股票且不能重复")
    positions = {symbol: index for index, symbol in enumerate(normalized_symbols)}
    for association in associations:
        association.sort_order = positions[association.symbol]
    db.commit()
    return normalized_symbols


def rename_tag(db: Session, tag_id: int, name: str) -> dict:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise WatchlistNotFoundError("标签不存在")
    tag.name = _tag_name(name)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WatchlistConflictError("标签名称已存在") from exc
    return _tag_dict(tag)


def delete_tag(db: Session, tag_id: int) -> None:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise WatchlistNotFoundError("标签不存在")
    db.delete(tag)
    db.commit()
