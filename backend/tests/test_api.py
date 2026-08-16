from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.database.models import WatchlistGroup
from app.database.session import get_session
from app.market_data.schemas import Quote, StockSummary
from app.main import main


class FakeProvider:
    def connect(self): pass
    def close(self): pass
    def list_stocks(self): return [StockSummary(symbol="600519.SH", code="600519", name="贵州茅台")]
    def search_stocks(self, keyword): return self.list_stocks()
    def get_quote(self, symbol): return Quote(symbol=symbol, name="贵州茅台", price=1500, change=10, change_percent=0.67)
    def get_daily_bars(self, symbol, count=250): return []


def make_client(db):
    app = FastAPI()
    app.state.market_provider = FakeProvider()
    app.include_router(api_router)

    def session_override():
        yield db

    app.dependency_overrides[get_session] = session_override
    return TestClient(app)


def test_health_and_market_api(db):
    client = make_client(db)
    assert client.get("/api/health").json() == {"status": "ok"}
    quote = client.get("/api/market/stocks/600519/quote")
    assert quote.status_code == 200
    assert quote.json()["symbol"] == "600519.SH"
    assert quote.json()["price"] == 1500


def test_watchlist_api_round_trip(db):
    default = WatchlistGroup(name="默认分组", is_default=True)
    db.add(default)
    db.commit()
    client = make_client(db)
    created = client.post("/api/watchlist/groups", json={"name": "白酒"})
    assert created.status_code == 201
    group_id = created.json()["id"]
    item = client.post(f"/api/watchlist/groups/{group_id}/items", json={"symbol": "600519"})
    assert item.status_code == 201
    assert item.json()["symbol"] == "600519.SH"
    groups = client.get("/api/watchlist/groups").json()
    assert next(group for group in groups if group["id"] == group_id)["items"][0]["symbol"] == "600519.SH"


def test_tag_api_round_trip(db):
    client = make_client(db)
    created = client.post("/api/stocks/600519.SH/tags", json={"name": "高股息"})
    assert created.status_code == 201
    assert client.get("/api/stocks/600519.SH/tags").json()[0]["name"] == "高股息"
    assert client.delete(f"/api/stocks/600519.SH/tags/{created.json()['id']}").status_code == 204


def test_main_starts_uvicorn_for_ide(monkeypatch):
    captured = {}

    def fake_run(application, **options):
        captured["application"] = application
        captured.update(options)

    monkeypatch.setattr("app.main.uvicorn.run", fake_run)
    main()
    assert captured == {
        "application": "app.main:app",
        "host": "127.0.0.1",
        "port": 8000,
        "workers": 1,
    }
