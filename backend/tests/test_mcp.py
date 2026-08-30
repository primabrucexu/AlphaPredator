from __future__ import annotations

import asyncio
from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient
from fastmcp import Client
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from starlette.routing import Mount

from app.database.models import Stock
from app.mcp_server import mcp
from app.tasks.handlers.production import register_production_handlers
from app.tasks.models import (
    ModeScreeningSaleResult,
    ModeScreeningStockResult,
    ModeScreeningTradeResult,
    Task,
    TaskItem,
    TaskItemStatus,
    TaskStatus,
)
from app.tasks import operations


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


EXPECTED_TOOLS = {
    "list_watchlist",
    "add_watchlist_stock",
    "remove_watchlist_stock",
    "list_tags",
    "create_tag",
    "rename_tag",
    "delete_tag",
    "attach_tag_to_stock",
    "detach_tag_from_stock",
    "reorder_tags",
    "reorder_tag_stocks",
    "create_stock_directory_refresh_task",
    "create_market_daily_bars_update_task",
    "retry_failed_market_daily_bars_task",
    "create_sr001_mode_screening_task",
    "get_task",
    "get_task_output",
    "get_mode_screening_results",
    "get_mode_screening_trades",
}


def test_mcp_server_exposes_confirmed_tools_only() -> None:
    async def verify() -> None:
        async with Client(mcp) as client:
            assert {tool.name for tool in await client.list_tools()} == EXPECTED_TOOLS
            assert await client.list_resources() == []
            assert await client.list_prompts() == []

    asyncio.run(verify())


def _use_test_database(monkeypatch, db) -> None:
    monkeypatch.setattr(
        "app.mcp_tools.SessionLocal",
        sessionmaker(db.get_bind(), expire_on_commit=False),
    )


def test_mcp_watchlist_and_tag_round_trip(db, monkeypatch) -> None:
    _use_test_database(monkeypatch, db)
    db.add(Stock(symbol="600519.SH", code="600519", name="贵州茅台"))
    db.commit()

    async def verify() -> None:
        async with Client(mcp) as client:
            tag = (await client.call_tool("create_tag", {"name": "白酒"})).data
            attached = (await client.call_tool("attach_tag_to_stock", {
                "symbol": "600519", "tag_id": tag["id"],
            })).data
            assert attached["symbol"] == "600519.SH"
            assert (await client.call_tool("list_watchlist", {})).data[0]["name"] == "贵州茅台"
            renamed = (await client.call_tool("rename_tag", {
                "tag_id": tag["id"], "name": "消费",
            })).data
            assert renamed["name"] == "消费"
            assert (await client.call_tool("reorder_tags", {"tag_ids": [tag["id"]]})).data == {
                "tag_ids": [tag["id"]],
            }
            assert (await client.call_tool("reorder_tag_stocks", {
                "tag_id": tag["id"], "symbols": ["600519"],
            })).data == {"symbols": ["600519.SH"]}
            await client.call_tool("detach_tag_from_stock", {
                "symbol": "600519", "tag_id": tag["id"],
            })
            await client.call_tool("attach_tag_to_stock", {
                "symbol": "600519", "tag_id": tag["id"],
            })
            await client.call_tool("remove_watchlist_stock", {"symbol": "600519"})
            assert (await client.call_tool("list_watchlist", {})).data == []
            assert (await client.call_tool("list_tags", {})).data[0]["stock_count"] == 0
            await client.call_tool("delete_tag", {"tag_id": tag["id"]})
            assert (await client.call_tool("list_tags", {})).data == []

    asyncio.run(verify())


def test_mcp_task_create_query_output_and_retry_use_public_uuid(db, monkeypatch) -> None:
    _use_test_database(monkeypatch, db)
    register_production_handlers()
    db.add(Stock(symbol="000001.SZ", code="000001", name="平安银行"))
    db.commit()
    monkeypatch.setattr(
        "app.mcp_tools.create_stock_directory_refresh_task",
        lambda session: operations.create_stock_directory_refresh_task(
            session, start_worker=lambda: None,
        ),
    )
    monkeypatch.setattr(
        "app.mcp_tools.create_market_daily_bars_update_task",
        lambda session, mode: operations.create_market_daily_bars_update_task(
            session, mode, start_worker=lambda: None,
        ),
    )
    monkeypatch.setattr(
        "app.mcp_tools.retry_failed_market_daily_bars_task",
        lambda session, original: operations.retry_failed_market_daily_bars_task(
            session, original, start_worker=lambda: None,
        ),
    )

    async def verify() -> None:
        async with Client(mcp) as client:
            directory = (await client.call_tool(
                "create_stock_directory_refresh_task", {},
            )).data
            assert set(directory) >= {"uuid", "status", "progress"}
            assert "id" not in directory

            market = (await client.call_tool(
                "create_market_daily_bars_update_task", {"mode": "incremental"},
            )).data
            task_uuid = market["uuid"]
            detail = (await client.call_tool("get_task", {"task_uuid": task_uuid})).data
            assert detail["uuid"] == task_uuid
            assert "id" not in detail

            task = db.scalar(select(Task).where(Task.uuid == task_uuid))
            item = db.scalar(select(TaskItem).where(TaskItem.task_id == task.id))
            task.status = TaskStatus.PARTIALLY_SUCCEEDED.value
            item.status = TaskItemStatus.FAILED.value
            item.error = "remote failed"
            db.commit()

            output = (await client.call_tool("get_task_output", {
                "task_uuid": task_uuid, "page": 1, "page_size": 50,
            })).data
            assert output["task_uuid"] == task_uuid
            assert output["items"][0]["error"] == "remote failed"
            assert "id" not in output["items"][0]
            assert "task_id" not in output["items"][0]

            retried = (await client.call_tool(
                "retry_failed_market_daily_bars_task", {"task_uuid": task_uuid},
            )).data
            assert retried["uuid"] != task_uuid
            assert retried["input"]["retry_of_task_uuid"] == task_uuid
            assert "retry_of_task_id" not in retried["input"]

    asyncio.run(verify())


def test_mcp_sr001_mode_screening_uses_fixed_rule_and_public_results(db, monkeypatch) -> None:
    _use_test_database(monkeypatch, db)
    register_production_handlers()
    db.add(Stock(symbol="000021.SZ", code="000021", name="深科技"))
    db.commit()
    monkeypatch.setattr(
        "app.mcp_tools.create_mode_screening_analysis",
        lambda session, **kwargs: operations.create_mode_screening_analysis_task(
            session, **kwargs, start_worker=lambda: None,
        ),
    )

    async def verify() -> None:
        async with Client(mcp) as client:
            created = (await client.call_tool("create_sr001_mode_screening_task", {
                "as_of_date": "2026-07-22",
                "symbols": ["000021"],
            })).data
            assert created["task_type"] == "mode_screening_analysis"
            assert created["input"]["rule_id"] == "SR001"
            assert created["input"]["rule_revision"] == 1
            assert created["input"]["parameters"] == {
                "macd_fast": 8,
                "macd_slow": 17,
                "macd_signal": 6,
                "warmup_bars": 100,
                "take_profit_rate": "0.05",
                "take_profit_fraction": "0.5",
                "stop_loss_rate": "0.05",
            }
            assert created["input"]["symbols"] == ["000021.SZ"]

            task = db.scalar(select(Task).where(Task.uuid == created["uuid"]))
            item = db.scalar(select(TaskItem).where(TaskItem.task_id == task.id))
            stock_result = ModeScreeningStockResult(
                task_id=task.id,
                task_item_id=item.id,
                symbol="000021.SZ",
                code="000021",
                name="深科技",
                as_of_date="2026-07-22",
                data_start_date="2024-06-03",
                data_end_date="2026-07-22",
                signal_date="2026-07-22",
                evidence_json='[{"condition_id":"C1","passed":true}]',
                metrics_json='{"histogram":"-2.8756"}',
                backtest_status="open",
                completed_trades=1,
                winning_trades=1,
                win_rate="1",
                average_return="0.1",
                maximum_return="0.1",
                minimum_return="0.1",
            )
            db.add(stock_result)
            db.flush()
            trade = ModeScreeningTradeResult(
                stock_result_id=stock_result.id,
                sequence=0,
                signal_date="2026-01-02",
                buy_date="2026-01-05",
                buy_price="10",
                realized_return="0.1",
            )
            db.add(trade)
            db.flush()
            db.add(ModeScreeningSaleResult(
                trade_result_id=trade.id,
                sequence=0,
                trade_date="2026-01-06",
                reason_id="EX1",
                price="11",
                fraction_of_original="1",
                return_rate="0.1",
            ))
            db.commit()

            results = (await client.call_tool("get_mode_screening_results", {
                "task_uuid": task.uuid,
                "page": 1,
                "page_size": 20,
                "sort_by": "win_rate",
                "sort_order": "desc",
            })).data
            assert results["total"] == 1
            assert results["items"][0]["symbol"] == "000021.SZ"
            assert results["items"][0]["evidence"][0]["condition_id"] == "C1"
            assert "id" not in results["items"][0]
            assert "task_id" not in results["items"][0]

            trades = (await client.call_tool("get_mode_screening_trades", {
                "task_uuid": task.uuid,
                "symbol": "000021",
                "page": 1,
                "page_size": 20,
            })).data
            assert trades["symbol"] == "000021.SZ"
            assert trades["items"][0]["sells"][0]["reason_id"] == "EX1"
            assert "id" not in trades["items"][0]
            assert "stock_result_id" not in trades["items"][0]

            wrong_type = Task(
                task_type="stock_directory_refresh",
                scheduling_policy="EXCLUSIVE_UPDATE",
                title="wrong type",
            )
            db.add(wrong_type)
            db.commit()
            wrong_type_result = await client.call_tool(
                "get_mode_screening_results",
                {"task_uuid": wrong_type.uuid},
                raise_on_error=False,
            )
            assert wrong_type_result.is_error
            assert "不是模式选股分析任务" in wrong_type_result.content[0].text

            missing_stock = await client.call_tool(
                "get_mode_screening_trades",
                {"task_uuid": task.uuid, "symbol": "600519"},
                raise_on_error=False,
            )
            assert missing_stock.is_error
            assert "命中股票结果不存在" in missing_stock.content[0].text

            missing_task = await client.call_tool(
                "get_mode_screening_results",
                {"task_uuid": str(uuid4())},
                raise_on_error=False,
            )
            assert missing_task.is_error
            assert "任务不存在" in missing_task.content[0].text

            invalid_sort = await client.call_tool(
                "get_mode_screening_results",
                {"task_uuid": task.uuid, "sort_by": "win_rate"},
                raise_on_error=False,
            )
            assert invalid_sort.is_error
            assert "必须同时提供" in invalid_sort.content[0].text

    asyncio.run(verify())


def _patch_main_startup(monkeypatch, main_module) -> list[str]:
    events: list[str] = []
    for name in (
        "migrate_legacy_watchlists",
        "migrate_legacy_tags",
        "migrate_stock_tag_order",
        "migrate_task_tables",
        "migrate_task_public_uuids",
        "migrate_mode_screening_results",
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
        "migrate_task_public_uuids",
        "migrate_mode_screening_results",
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
