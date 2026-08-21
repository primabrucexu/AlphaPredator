from __future__ import annotations

from app.database.models import Stock, StockTag, Tag, WatchlistItem
from app.market_data.schemas import Quote, StockSummary
from app.market_data.service import StockService, pinyin_keys


class FakeProvider:
    stocks = [
        StockSummary(symbol="600519.SH", code="600519", name="贵州茅台"),
        StockSummary(symbol="000001.SZ", code="000001", name="平安银行"),
    ]

    def connect(self): pass
    def close(self): pass
    def list_stocks(self): return self.stocks
    def search_stocks(self, keyword): return [s for s in self.stocks if keyword in s.code or keyword in s.name]
    def get_quote(self, symbol): return Quote(symbol=symbol, name="测试")
    def get_daily_bars(self, symbol, count=250): return []


def test_pinyin_keys():
    assert pinyin_keys("贵州茅台") == ("guizhoumaotai", "gzmt")


def test_directory_sync_and_search_by_code_name_and_initials(db):
    service = StockService(FakeProvider())
    assert service.sync_directory(db) == 2
    assert service.search(db, "600519")[0].name == "贵州茅台"
    assert service.search(db, "贵州")[0].symbol == "600519.SH"
    assert service.search(db, "gzmt")[0].symbol == "600519.SH"
    assert db.get(Stock, "600519.SH").pinyin == "guizhoumaotai"


def test_watchlist_and_tags_persist(db):
    tag = Tag(name="白酒", sort_order=0)
    db.add(tag)
    db.flush()
    db.add_all([WatchlistItem(symbol="600519.SH"), StockTag(symbol="600519.SH", tag_id=tag.id)])
    db.commit()
    db.expire_all()
    assert db.query(WatchlistItem).one().symbol == "600519.SH"
    assert db.query(StockTag).one().tag_id == tag.id
