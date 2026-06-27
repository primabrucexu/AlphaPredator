from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount

from app.api.routes.mcp import get_alpha_predator_info, get_macd_alert_daily_brief, mcp


def test_alpha_predator_probe_tool_returns_basic_status() -> None:
    assert get_alpha_predator_info() == {
        'name': 'AlphaPredator',
        'mcp_status': 'ok',
        'capabilities_stage': 'F06-macd-alert',
    }


@pytest.mark.anyio
async def test_probe_tool_is_discoverable_and_callable_through_mcp() -> None:
    from fastmcp import Client

    async with Client(mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool('get_alpha_predator_info')

    tool_names = [tool.name for tool in tools]
    assert 'get_alpha_predator_info' in tool_names
    assert 'get_macd_alert_daily_brief' in tool_names
    assert 'start_market_data_incremental_update' in tool_names
    assert result.data == {
        'name': 'AlphaPredator',
        'mcp_status': 'ok',
        'capabilities_stage': 'F06-macd-alert',
    }


def test_macd_daily_brief_tool_includes_disclaimer(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.routes.mcp as mcp_route

    monkeypatch.setattr(
        mcp_route,
        'get_macd_daily_brief',
        lambda **kwargs: {
            'trade_date': '2026-01-10',
            'latest_trade_date': '2026-01-10',
            'is_data_fresh': True,
            'new_alert_count': 1,
            'tracking': {'tracked_count': 0},
            'highlights': [],
        },
    )

    result = get_macd_alert_daily_brief('2026-01-10', limit=10)

    assert result['disclaimer'] == '以下为技术形态观察结果，不构成买卖建议。'
    assert result['new_alert_count'] == 1


def test_market_data_incremental_update_tool_creates_task_from_latest_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.routes.mcp as mcp_route

    created: dict[str, str] = {}

    monkeypatch.setattr(
        mcp_route,
        'get_overview',
        lambda: {
            'latest_market_data_task': {
                'task_id': 'previous',
                'end_date': '20240331',
            },
        },
    )

    def fake_create_batch_tasks(start_date: str, end_date: str, *, market_mode: str) -> dict:
        created.update(
            start_date=start_date,
            end_date=end_date,
            market_mode=market_mode,
        )
        return {
            'stock_list_task': {'task_id': 'stock-task', 'task_type': 'STOCK_LIST_SYNC', 'status': 'PENDING'},
            'market_data_task': {
                'task_id': 'market-task',
                'task_type': 'MARKET_DATA',
                'start_date': start_date,
                'end_date': end_date,
                'status': 'PENDING',
            },
            'jygs_review_task': {'task_id': 'jygs-task', 'task_type': 'JYGS_REVIEW', 'status': 'PENDING'},
        }

    monkeypatch.setattr(mcp_route, 'create_batch_tasks', fake_create_batch_tasks)

    result = mcp_route.start_market_data_incremental_update(target_end_date='20240403')

    assert created == {
        'start_date': '20240401',
        'end_date': '20240403',
        'market_mode': 'INCREMENTAL_SYNC',
    }
    assert result['started'] is True
    assert result['task_id'] == 'market-task'
    assert result['stock_list_task_id'] == 'stock-task'
    assert result['jygs_review_task_id'] == 'jygs-task'
    assert result['start_date'] == '20240401'
    assert result['end_date'] == '20240403'
    assert result['status'] == 'PENDING'


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
