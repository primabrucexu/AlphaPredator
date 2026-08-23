from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.router import api_router
from app.database.models import JygsCredential
from app.database.session import get_session
from app.tasks.handlers.production import register_production_handlers
from app.tasks.handlers import get_handler
from app.tasks.models import TaskItem
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


def test_production_registration_exposes_both_handlers():
    register_production_handlers()
    assert get_handler("jygs_limit_up_sync") is not None
    assert get_handler("stock_directory_refresh") is not None


def test_old_data_update_routes_are_removed(db):
    client = make_client(db)
    assert client.post("/api/jygs/sync", json={}).status_code == 404
    assert client.post("/api/stocks/sync-directory").status_code == 404
