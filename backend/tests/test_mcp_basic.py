from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount

from app.api.routes.mcp import get_alpha_predator_info, mcp


def test_alpha_predator_probe_tool_returns_basic_status() -> None:
    assert get_alpha_predator_info() == {
        'name': 'AlphaPredator',
        'mcp_status': 'ok',
        'capabilities_stage': 'F05a-basic-mcp',
    }


@pytest.mark.anyio
async def test_probe_tool_is_discoverable_and_callable_through_mcp() -> None:
    from fastmcp import Client

    async with Client(mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool('get_alpha_predator_info')

    assert [tool.name for tool in tools] == ['get_alpha_predator_info']
    assert result.data == {
        'name': 'AlphaPredator',
        'mcp_status': 'ok',
        'capabilities_stage': 'F05a-basic-mcp',
    }


def test_main_app_mounts_mcp_under_api_mcp() -> None:
    from app.main import app

    mounted_paths = [route.path for route in app.routes if isinstance(route, Mount)]

    assert '/api/mcp' in mounted_paths


def test_main_app_lifespan_keeps_existing_startup_and_mcp_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.main as main

    startup_calls = []
    monkeypatch.setattr(
        main,
        'ensure_sqlite_parent',
        lambda: startup_calls.append('sqlite_parent'),
    )
    monkeypatch.setattr(
        main,
        'ensure_sqlite_schema',
        lambda: startup_calls.append('sqlite_schema'),
    )
    monkeypatch.setattr(
        main,
        'ensure_duckdb_parent',
        lambda: startup_calls.append('duckdb_parent'),
    )
    monkeypatch.setattr(
        main,
        'ensure_duckdb_schema',
        lambda: startup_calls.append('duckdb_schema'),
    )

    with TestClient(main.app) as client:
        response = client.get('/')

    assert response.status_code == 200
    assert response.json()['name'] == 'AlphaPredator API'
    assert startup_calls == ['sqlite_parent', 'sqlite_schema', 'duckdb_parent', 'duckdb_schema']


def test_unauthenticated_mcp_rejects_public_bind_address(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main

    monkeypatch.setattr(main, 'settings', SimpleNamespace(app_host='0.0.0.0'))

    with pytest.raises(RuntimeError, match='must bind to 127.0.0.1 or localhost'):
        main._ensure_localhost_binding()
