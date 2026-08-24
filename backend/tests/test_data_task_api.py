from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.router import api_router
from app.database.models import JygsCredential, Stock
from app.database.session import get_session
from app.tasks.handlers.production import register_production_handlers
from app.tasks.handlers import get_handler
from app.tasks.handlers import register_handler
from app.tasks.handlers.market_daily_bars import MarketDailyBarsUpdateHandler
from app.tasks.models import Task, TaskItem, TaskItemStatus, TaskStatus
from app.tasks.routes import _market_target_end_date
from app.tasks.service import load_json


def make_client(db):
    app = FastAPI()
    app.include_router(api_router)

    def session_override():
        yield db

    app.dependency_overrides[get_session] = session_override
    return TestClient(app)


def test_data_task_creation_and_duplicate_conflict(db, monkeypatch):
    register_production_handlers()
    monkeypatch.setattr("app.tasks.routes.start_worker_process", lambda: None)
    db.add(JygsCredential(id=1, session="secret"))
    db.commit()
    client = make_client(db)

    created = client.post("/api/tasks/jygs-limit-up-sync", json={
        "start_date": "2026-08-22", "end_date": "2026-08-23"
    })
    assert created.status_code == 202
    assert created.json()["task_type"] == "jygs_limit_up_sync"
    task_id = created.json()["id"]
    items = list(db.scalars(select(TaskItem).where(TaskItem.task_id == task_id)))
    assert [load_json(item.input_json)["trade_date"] for item in items] == [
        "2026-08-22", "2026-08-23"
    ]
    assert "secret" not in created.text

    db.delete(db.get(JygsCredential, 1))
    db.commit()
    duplicate = client.post("/api/tasks/jygs-limit-up-sync", json={
        "start_date": "2026-08-24", "end_date": "2026-08-24"
    })
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["existing_task_id"] == task_id

    stocks = client.post("/api/tasks/stock-directory-refresh")
    assert stocks.status_code == 202
    assert stocks.json()["task_type"] == "stock_directory_refresh"


def test_production_registration_exposes_all_handlers():
    register_production_handlers()
    assert get_handler("jygs_limit_up_sync") is not None
    assert get_handler("stock_directory_refresh") is not None
    assert get_handler("market_daily_bars_update") is not None


def test_market_daily_bars_creation_and_failed_stock_retry(db, monkeypatch):
    factory = sessionmaker(db.get_bind(), expire_on_commit=False)
    def forbidden_store():
        raise AssertionError("Web 不得打开 DuckDB")
    register_handler(
        "market_daily_bars_update",
        MarketDailyBarsUpdateHandler(
            factory,
            store_factory=forbidden_store,
        ),
    )
    monkeypatch.setattr("app.tasks.routes.start_worker_process", lambda: None)
    db.add(Stock(symbol="000001.SZ", code="000001", name="平安银行"))
    db.commit()
    client = make_client(db)

    created = client.post("/api/tasks/market-daily-bars-update", json={"mode": "incremental"})
    assert created.status_code == 202
    payload = created.json()
    assert payload["task_type"] == "market_daily_bars_update"
    assert payload["input"]["mode"] == "incremental"
    task_id = payload["id"]
    item = db.scalar(select(TaskItem).where(TaskItem.task_id == task_id))
    assert load_json(item.input_json)["symbol"] == "000001.SZ"

    task = db.get(Task, task_id)
    task.status = TaskStatus.SUCCEEDED.value
    item.status = TaskItemStatus.SUCCEEDED.value
    item.result_json = json.dumps({
        "after_first_date": "2025-01-02",
        "after_last_date": "2026-08-20",
    })
    db.commit()
    assert client.get("/api/tasks/market-daily-bars-coverage").json() == {
        "start_date": "2025-01-02",
        "end_date": "2026-08-20",
    }

    task.result_json = json.dumps({
        "data_start_date": "2025-01-02",
        "data_end_date": "2026-08-21",
    })
    db.commit()
    coverage = client.get("/api/tasks/market-daily-bars-coverage")
    assert coverage.status_code == 200
    assert coverage.json() == {"start_date": "2025-01-02", "end_date": "2026-08-21"}

    task.status = TaskStatus.PARTIALLY_SUCCEEDED.value
    item.status = TaskItemStatus.FAILED.value
    item.error = "remote failed"
    db.commit()
    retried = client.post(f"/api/tasks/{task_id}/retry-failed")
    assert retried.status_code == 202
    retry_payload = retried.json()
    assert retry_payload["input"]["symbols"] == ["000001.SZ"]
    assert retry_payload["input"]["target_end_date"] == payload["input"]["target_end_date"]
    assert retry_payload["input"]["retry_of_task_id"] == task_id
    retry_task = db.get(Task, retry_payload["id"])
    retry_task.result_json = json.dumps({"data_start_date": None, "data_end_date": None})
    db.commit()
    assert client.get("/api/tasks/market-daily-bars-coverage").json() == {
        "start_date": "2025-01-02",
        "end_date": "2026-08-21",
    }
    duplicate_retry = client.post(f"/api/tasks/{task_id}/retry-failed")
    assert duplicate_retry.status_code == 409
    assert duplicate_retry.json()["detail"]["existing_task_id"] == retry_payload["id"]


def test_market_daily_bars_creation_requires_stock_directory(db, monkeypatch):
    monkeypatch.setattr("app.tasks.routes.start_worker_process", lambda: None)
    client = make_client(db)
    response = client.post("/api/tasks/market-daily-bars-update", json={"mode": "full"})
    assert response.status_code == 400
    assert "股票目录为空" in response.json()["detail"]
    assert client.get("/api/tasks/market-daily-bars-coverage").json() == {
        "start_date": None,
        "end_date": None,
    }


@pytest.mark.parametrize(("hour", "minute", "second", "expected"), [
    (15, 44, 59, date(2026, 8, 23)),
    (15, 45, 0, date(2026, 8, 23)),
    (15, 45, 1, date(2026, 8, 24)),
])
def test_market_target_end_date_boundary(hour, minute, second, expected):
    now = datetime(2026, 8, 24, hour, minute, second, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert _market_target_end_date(now) == expected


def test_old_data_update_routes_are_removed(db):
    client = make_client(db)
    assert client.post("/api/jygs/sync", json={}).status_code == 404
    assert client.post("/api/stocks/sync-directory").status_code == 404
