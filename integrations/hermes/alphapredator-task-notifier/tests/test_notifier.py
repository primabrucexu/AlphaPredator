from __future__ import annotations

import json
from pathlib import Path

from alphapredator_task_notifier.config import Config
from alphapredator_task_notifier.notifier import TaskNotifier
from alphapredator_task_notifier.store import NotificationStore


class FakeContext:
    def __init__(self):
        self.status = "RUNNING"
        self.calls = []

    def dispatch_tool(self, name, args):
        self.calls.append((name, args))
        payload = {
            "uuid": args["task_uuid"],
            "task_type": "stock_directory_refresh",
            "title": "刷新股票搜索目录",
            "status": self.status,
            "progress": 100 if self.status == "SUCCEEDED" else 20,
            "completed_items": 1 if self.status == "SUCCEEDED" else 0,
            "failed_items": 0,
            "result": {"synced": 10} if self.status == "SUCCEEDED" else {},
        }
        return json.dumps({"result": payload}, ensure_ascii=False)


class FakeSessionClient:
    def __init__(self):
        self.calls = []

    def inject(self, session_id, message):
        self.calls.append((session_id, message))


def config(path: Path) -> Config:
    return Config(
        mcp_server_name="ap",
        api_url="http://127.0.0.1:8642",
        api_key="test-key",
        poll_seconds=1,
        database_path=path,
    )


def test_hook_tracks_task_and_terminal_result_is_injected_once(tmp_path):
    ctx = FakeContext()
    session_client = FakeSessionClient()
    store = NotificationStore(tmp_path / "notifier.sqlite3")
    notifier = TaskNotifier(ctx, config(store.path), store, session_client)
    hook_result = json.dumps({
        "structuredContent": {"result": {"uuid": "task-1", "status": "PENDING"}}
    })

    notifier.on_post_tool_call(
        tool_name="mcp_ap_create_stock_directory_refresh_task",
        result=hook_result,
        session_id="agent:main:weixin:dm:user-1",
    )
    notifier.on_post_tool_call(
        tool_name="mcp_ap_create_stock_directory_refresh_task",
        result=hook_result,
        session_id="agent:main:weixin:dm:user-other",
    )
    assert store.get("task-1").session_id == "agent:main:weixin:dm:user-1"

    notifier.run_once()
    assert store.get("task-1").state == "POLLING"
    ctx.status = "SUCCEEDED"
    store.schedule_poll("task-1", 0)
    notifier.run_once()
    assert store.get("task-1").state == "READY"
    notifier.run_once()
    assert store.get("task-1").state == "SENT"
    assert len(session_client.calls) == 1
    assert "task-1" in session_client.calls[0][1]
    assert "get_task_output" in session_client.calls[0][1]
    notifier.run_once()
    assert len(session_client.calls) == 1


def test_hook_falls_back_to_task_id_for_older_hermes(tmp_path):
    store = NotificationStore(tmp_path / "notifier.sqlite3")
    notifier = TaskNotifier(FakeContext(), config(store.path), store, FakeSessionClient())
    notifier.on_post_tool_call(
        tool_name="mcp_ap_create_market_daily_bars_update_task",
        result=json.dumps({"result": {"uuid": "task-2"}}),
        task_id="legacy-session",
    )
    assert store.get("task-2").session_id == "legacy-session"
