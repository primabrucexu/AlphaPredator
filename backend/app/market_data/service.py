from __future__ import annotations

from pypinyin import Style, lazy_pinyin
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database.models import Stock
from app.market_data.provider.base import MarketDataProvider
from app.market_data.schemas import StockSummary


def pinyin_keys(name: str) -> tuple[str, str]:
    full = "".join(lazy_pinyin(name, style=Style.NORMAL)).lower()
    initials = "".join(lazy_pinyin(name, style=Style.FIRST_LETTER)).lower()
    return full, initials


class StockService:
    def __init__(self, provider: MarketDataProvider):
        self.provider = provider

    def sync_directory(self, session: Session) -> int:
        stocks = self.provider.list_stocks()
        for item in stocks:
            full, initials = pinyin_keys(item.name)
            current = session.get(Stock, item.symbol)
            if current:
                current.code, current.name = item.code, item.name
                current.pinyin, current.pinyin_initials = full, initials
            else:
                session.add(Stock(symbol=item.symbol, code=item.code, name=item.name, pinyin=full, pinyin_initials=initials))
        session.commit()
        return len(stocks)

    def search(self, session: Session, keyword: str, limit: int = 20) -> list[StockSummary]:
        query = keyword.strip().lower()
        if not query:
            return []
        rows = session.scalars(select(Stock).where(or_(
            Stock.code.startswith(query), Stock.symbol.ilike(f"{query}%"), Stock.name.contains(keyword.strip()),
            Stock.pinyin.startswith(query), Stock.pinyin_initials.startswith(query),
        )).limit(limit)).all()
        if rows:
            return [StockSummary.model_validate(row) for row in rows]
        remote = self.provider.search_stocks(keyword)
        for item in remote:
            full, initials = pinyin_keys(item.name)
            session.merge(Stock(symbol=item.symbol, code=item.code, name=item.name, pinyin=full, pinyin_initials=initials))
        session.commit()
        return remote[:limit]
