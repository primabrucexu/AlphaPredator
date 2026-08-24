from __future__ import annotations

import asyncio
from contextlib import contextmanager

from fastapi.testclient import TestClient
from fastmcp import Client
from starlette.routing import Mount

from app.mcp_server import mcp


INITIALIZE_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "AlphaPredatorTest", "version": "1.0"},
    },
}


def test_mcp_server_exposes_no_capabilities() -> None:
    async def verify() -> None:
        async with Client(mcp) as client:
            assert await client.list_tools() == []
            assert await client.list_resources() == []
            assert await client.list_prompts() == []

    asyncio.run(verify())


def _patch_main_startup(monkeypatch, main_module) -> list[str]:
    events: list[str] = []
    for name in (
        "migrate_legacy_watchlists",
        "migrate_legacy_tags",
        "migrate_stock_tag_order",
        "migrate_task_tables",
        "sync_tagged_stocks_to_watchlist",
    ):
        monkeypatch.setattr(main_module, name, lambda *_args, _name=name: events.append(_name))
    monkeypatch.setattr(
        main_module.Base.metadata,
        "create_all",
        lambda *_args: events.append("create_all"),
    )

    @contextmanager
    def session_factory():
        events.append("session")
        yield object()

    monkeypatch.setattr(main_module, "SessionLocal", session_factory)
    monkeypatch.setattr(main_module, "next_pending_task", lambda _session: None)
    monkeypatch.setattr(
        main_module,
        "close_process_market_provider",
        lambda: events.append("provider_closed"),
    )
    return events


def test_main_mounts_mcp_and_preserves_lifespan(monkeypatch) -> None:
    import app.main as main

    events = _patch_main_startup(monkeypatch, main)
    mounted_paths = [route.path for route in main.app.routes if isinstance(route, Mount)]
    assert "/api/mcp" in mounted_paths

    with TestClient(main.app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        response = client.post(
            "/api/mcp/",
            headers={"Accept": "application/json, text/event-stream"},
            json=INITIALIZE_REQUEST,
        )
        assert response.status_code == 200
        assert "AlphaPredator" in response.text

    assert events == [
        "migrate_legacy_watchlists",
        "migrate_legacy_tags",
        "migrate_stock_tag_order",
        "migrate_task_tables",
        "create_all",
        "sync_tagged_stocks_to_watchlist",
        "session",
        "provider_closed",
    ]


def test_mcp_rejects_non_local_host_and_origin(monkeypatch) -> None:
    import app.main as main

    _patch_main_startup(monkeypatch, main)
    with TestClient(main.app) as client:
        host_response = client.post(
            "/api/mcp/",
            headers={
                "Accept": "application/json, text/event-stream",
                "Host": "malicious.example",
            },
            json=INITIALIZE_REQUEST,
        )
        origin_response = client.post(
            "/api/mcp/",
            headers={
                "Accept": "application/json, text/event-stream",
                "Origin": "https://malicious.example",
            },
            json=INITIALIZE_REQUEST,
        )

    assert host_response.status_code == 421
    assert origin_response.status_code == 403
