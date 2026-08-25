from __future__ import annotations

from alphapredator_task_notifier.store import NotificationStore


def test_store_is_idempotent_and_delivery_claim_is_exclusive(tmp_path):
    store = NotificationStore(tmp_path / "notifier.sqlite3")
    assert store.add("task-1", "session-1", now=10) is True
    assert store.add("task-1", "session-other", now=10) is False
    assert store.due(now=10)[0].session_id == "session-1"

    payload = {"uuid": "task-1", "status": "SUCCEEDED", "result": {"count": 3}}
    store.mark_ready("task-1", payload, now=11)
    assert store.claim_delivery("task-1", now=12) is True
    assert store.claim_delivery("task-1", now=12) is False
    store.mark_sent("task-1", now=13)
    assert store.get("task-1").state == "SENT"
    assert store.due(now=100) == []


def test_store_recovers_expired_delivery_lease(tmp_path):
    store = NotificationStore(tmp_path / "notifier.sqlite3")
    store.add("task-1", "session-1", now=10)
    store.mark_ready("task-1", {"uuid": "task-1", "status": "FAILED"}, now=11)
    assert store.claim_delivery("task-1", lease_seconds=5, now=12) is True
    assert store.recover_stale_deliveries(now=16) == 0
    assert store.recover_stale_deliveries(now=18) == 1
    assert store.get("task-1").state == "READY"
