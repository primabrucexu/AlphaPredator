from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.database.models import JygsCredential, Stock
from app.database.session import get_session
from app.market_data.schemas import Quote, StockSummary
from app.main import main


class FakeProvider:
    def connect(self): pass
    def close(self): pass
    def list_stocks(self): return [StockSummary(symbol="600519.SH", code="600519", name="贵州茅台")]
    def search_stocks(self, keyword): return self.list_stocks()
    def get_quote(self, symbol): return Quote(symbol=symbol, name="贵州茅台", price=1500, change=10, change_percent=0.67)
    def get_daily_bars(self, symbol, count=250, start_date=None, end_date=None): return []


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


def test_daily_bars_rejects_incomplete_date_range(db):
    response = make_client(db).get("/api/market/stocks/600519/daily-bars?start_date=2024-01-01")
    assert response.status_code == 503
    assert "必须同时提供" in response.json()["detail"]


def test_jygs_browser_login_captures_and_validates_session(db, monkeypatch):
    monkeypatch.setattr("app.jygs.routes.login_and_capture_session", lambda _timeout: {"session": "captured-session"})
    monkeypatch.setattr("app.jygs.client._post", lambda *_args, **_kwargs: {"errCode": "0"})

    response = make_client(db).post("/api/jygs/login", json={"timeout_seconds": 300})

    assert response.status_code == 200
    assert response.json() == {"is_valid": True}
    credential = db.get(JygsCredential, 1)
    assert credential.session == "captured-session"
    assert credential.is_valid is True


def test_watchlist_api_round_trip(db):
    db.add(Stock(symbol="600519.SH", code="600519", name="贵州茅台"))
    db.commit()
    client = make_client(db)
    item = client.post("/api/watchlist/items", json={"symbol": "600519"})
    assert item.status_code == 201
    assert item.json()["symbol"] == "600519.SH"
    tag = client.post("/api/stocks/600519.SH/tags", json={"name": "白酒"})
    assert tag.status_code == 201
    saved = client.get("/api/watchlist/items").json()[0]
    assert saved["symbol"] == "600519.SH"
    assert saved["code"] == "600519"
    assert saved["name"] == "贵州茅台"
    assert saved["tags"][0]["name"] == "白酒"


def test_tag_api_round_trip(db):
    client = make_client(db)
    created = client.post("/api/stocks/600519.SH/tags", json={"name": "高股息"})
    assert created.status_code == 201
    assert client.get("/api/watchlist/items").json()[0]["symbol"] == "600519.SH"
    assert client.get("/api/stocks/600519.SH/tags").json()[0]["name"] == "高股息"
    assert client.delete(f"/api/stocks/600519.SH/tags/{created.json()['id']}").status_code == 204


def test_global_tag_can_be_created_without_stock_and_then_reused(db):
    client = make_client(db)
    created = client.post("/api/tags", json={"name": "科技"})
    assert created.status_code == 201
    assert client.get("/api/tags").json()[0]["stock_count"] == 0
    attached = client.post("/api/stocks/600519.SH/tags", json={"name": "科技"})
    assert attached.status_code == 201
    assert attached.json()["id"] == created.json()["id"]
    assert client.get("/api/tags").json()[0]["stock_count"] == 1
    assert client.post("/api/watchlist/items", json={"symbol": "600519.SH"}).status_code == 409
    assert client.post("/api/tags", json={"name": "科技"}).status_code == 409


def test_global_tags_can_be_renamed_reordered_and_deleted(db):
    client = make_client(db)
    item = client.post("/api/watchlist/items", json={"symbol": "000001.SZ"}).json()
    first = client.post("/api/stocks/600519.SH/tags", json={"name": "白酒"}).json()
    second = client.post("/api/stocks/000001.SZ/tags", json={"name": "银行"}).json()

    assert [tag["name"] for tag in client.get("/api/tags").json()] == ["白酒", "银行"]
    assert client.put("/api/tags/order", json={"tag_ids": [second["id"], first["id"]]}).status_code == 200
    assert [tag["name"] for tag in client.get("/api/tags").json()] == ["银行", "白酒"]
    assert client.put(f"/api/tags/{first['id']}", json={"name": "消费"}).json()["name"] == "消费"
    assert client.delete(f"/api/tags/{second['id']}").status_code == 204
    assert [tag["name"] for tag in client.get("/api/tags").json()] == ["消费"]
    items = client.get("/api/watchlist/items").json()
    assert {row["symbol"] for row in items} == {"000001.SZ", "600519.SH"}
    assert next(row for row in items if row["id"] == item["id"])["tags"] == []
    assert next(row for row in items if row["symbol"] == "600519.SH")["tags"][0]["name"] == "消费"


def test_stocks_can_be_reordered_independently_inside_each_tag(db):
    client = make_client(db)
    first_tag = client.post("/api/stocks/600519.SH/tags", json={"name": "消费"}).json()
    second_tag = client.post("/api/stocks/600519.SH/tags", json={"name": "核心"}).json()
    client.post("/api/stocks/000001.SZ/tags", json={"name": "消费"})
    client.post("/api/stocks/000001.SZ/tags", json={"name": "核心"})

    response = client.put(f"/api/tags/{first_tag['id']}/stocks/order", json={
        "symbols": ["000001.SZ", "600519.SH"]
    })
    assert response.status_code == 200
    assert client.put(f"/api/tags/{second_tag['id']}/stocks/order", json={
        "symbols": ["600519.SH"]
    }).status_code == 400

    items = client.get("/api/watchlist/items").json()
    by_symbol = {item["symbol"]: item for item in items}
    first_orders = {
        symbol: next(tag["stock_sort_order"] for tag in item["tags"] if tag["id"] == first_tag["id"])
        for symbol, item in by_symbol.items()
    }
    second_orders = {
        symbol: next(tag["stock_sort_order"] for tag in item["tags"] if tag["id"] == second_tag["id"])
        for symbol, item in by_symbol.items()
    }
    assert first_orders == {"600519.SH": 1, "000001.SZ": 0}
    assert second_orders == {"600519.SH": 0, "000001.SZ": 1}


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
        "reload": True,
    }
