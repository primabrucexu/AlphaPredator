from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.session import Base, get_session
from app.tasks import process as task_process
from app.tasks.handlers import TaskItemSkipped, TaskItemSpec, register_handler, unregister_handler
from app.tasks.migrations import migrate_task_public_uuids, migrate_task_tables
from app.tasks.models import SchedulingPolicy, Task, TaskItem, TaskItemStatus, TaskStatus
from app.tasks.runner import (
    acquire_worker_lease,
    recover_interrupted_tasks,
    release_worker_lease,
    run_next_task,
)
from app.tasks.service import TaskPlanningError, create_task, load_json, request_cancel
from app.tasks.worker import run_worker


def make_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def item_input(*titles: str) -> dict:
    return {"items": [{"title": title} for title in titles]}


class RecordingHandler:
    def __init__(self, calls: list[str], fail_title: str | None = None):
        self.calls = calls
        self.fail_title = fail_title

    def build_items(self, task_input):
        return [
            TaskItemSpec(
                title=item["title"], input=item.get("input", {}), total=item.get("total")
            )
            for item in task_input.get("items", [])
        ]

    def run_item(self, task, item, context):
        self.calls.append(item.title)
        if item.title == self.fail_title:
            raise RuntimeError(f"{item.title} failed")
        context.report_progress(1, 1, item.title)
        return {"item": item.title}

    def summarize(self, task, items):
        return {
            "succeeded": sum(item.status == TaskItemStatus.SUCCEEDED.value for item in items),
            "failed": sum(item.status == TaskItemStatus.FAILED.value for item in items),
            "skipped": sum(item.status == TaskItemStatus.SKIPPED.value for item in items),
        }


class DateRangeHandler(RecordingHandler):
    def build_items(self, task_input):
        current = date.fromisoformat(task_input["start_date"])
        end = date.fromisoformat(task_input["end_date"])
        items = []
        while current <= end:
            value = current.isoformat()
            items.append(TaskItemSpec(title=f"同步 {value}", input={"date": value}))
            current += timedelta(days=1)
        return items


class CancellingHandler(RecordingHandler):
    def __init__(self, factory):
        super().__init__([])
        self.factory = factory

    def run_item(self, task, item, context):
        with self.factory() as db:
            request_cancel(db, db.get(Task, task.id))
        context.check_cancelled()


class InvalidItemHandler:
    def __init__(self, items):
        self.items = items

    def build_items(self, task_input):
        return self.items

    def run_item(self, task, item, context):
        raise AssertionError("invalid task must not execute")

    def summarize(self, task, items):
        raise AssertionError("invalid task must not summarize")


class SkippingHandler(RecordingHandler):
    def __init__(self, skip_titles: set[str], fail_title: str | None = None):
        super().__init__([], fail_title=fail_title)
        self.skip_titles = skip_titles

    def run_item(self, task, item, context):
        if item.title in self.skip_titles:
            raise TaskItemSkipped("历史任务已完成", {"reason": "already_succeeded"})
        return super().run_item(task, item, context)


class FailingSummaryHandler(RecordingHandler):
    def summarize(self, task, items):
        raise RuntimeError("summary failed")


class CancellingFailingSummaryHandler(CancellingHandler):
    def summarize(self, task, items):
        raise RuntimeError("summary failed after cancel")


def test_task_migration_is_repeatable():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE existing_data (id INTEGER PRIMARY KEY, value TEXT)")
        connection.exec_driver_sql("INSERT INTO existing_data (value) VALUES ('kept')")

    assert migrate_task_tables(engine) is True
    assert migrate_task_tables(engine) is False
    assert {"tasks", "task_items", "task_worker_lease"} <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT value FROM existing_data").scalar_one() == "kept"


def test_task_public_uuid_migration_backfills_existing_rows_and_is_repeatable():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT)")
        connection.exec_driver_sql("INSERT INTO tasks (id, title) VALUES (1, 'old'), (2, 'older')")

    assert migrate_task_public_uuids(engine) is True
    assert migrate_task_public_uuids(engine) is False

    columns = {column["name"]: column for column in inspect(engine).get_columns("tasks")}
    assert columns["uuid"]["nullable"] is False
    with engine.connect() as connection:
        values = connection.exec_driver_sql("SELECT uuid FROM tasks ORDER BY id").scalars().all()
    assert len(set(values)) == 2
    assert [str(UUID(value)) for value in values] == values


def test_worker_process_uses_dedicated_module(monkeypatch):
    captured = {}

    def fake_popen(command, **options):
        captured["command"] = command
        captured.update(options)

    monkeypatch.setattr(task_process.subprocess, "Popen", fake_popen)
    task_process.start_worker_process()

    assert captured["command"][1:] == ["-m", "app.tasks.worker"]
    assert captured["cwd"] == task_process.BACKEND_DIR


def test_build_items_persists_date_range_before_starting_worker():
    _engine, factory = make_factory()
    register_handler("date-range", DateRangeHandler([]))
    worker_observations = []

    def observe_persisted_items():
        with factory() as observer:
            worker_observations.append(
                observer.scalar(select(func.count()).select_from(TaskItem))
            )

    try:
        with factory() as db:
            task = create_task(
                db,
                task_type="date-range",
                scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title="date range",
                input={"start_date": "2026-08-21", "end_date": "2026-08-23"},
                start_worker=observe_persisted_items,
            )
            items = list(db.scalars(
                select(TaskItem).where(TaskItem.task_id == task.id).order_by(TaskItem.sequence)
            ))

        assert task.total_items == 3
        assert [item.sequence for item in items] == [0, 1, 2]
        assert [load_json(item.input_json)["date"] for item in items] == [
            "2026-08-21", "2026-08-22", "2026-08-23"
        ]
        assert worker_observations == [3]
    finally:
        unregister_handler("date-range")


def test_update_tasks_are_selected_before_compute_tasks_and_items_are_serial():
    _engine, factory = make_factory()
    calls: list[str] = []
    register_handler("record", RecordingHandler(calls))
    try:
        with factory() as db:
            compute = create_task(
                db, task_type="record", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="compute", input=item_input("compute-1", "compute-2"),
                start_worker=lambda: None,
            )
            update = create_task(
                db, task_type="record",
                scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title="update", input=item_input("update-1", "update-2"),
                start_worker=lambda: None,
            )
            compute_id, update_id = compute.id, update.id

        assert run_next_task(factory) is True
        assert run_next_task(factory) is True
        assert calls == ["update-1", "update-2", "compute-1", "compute-2"]
        with factory() as db:
            assert db.get(Task, update_id).status == TaskStatus.SUCCEEDED.value
            assert db.get(Task, compute_id).status == TaskStatus.SUCCEEDED.value
    finally:
        unregister_handler("record")


def test_failed_item_allows_partial_success_and_preserves_error():
    _engine, factory = make_factory()
    register_handler("partial", RecordingHandler([], fail_title="bad"))
    try:
        with factory() as db:
            task = create_task(
                db, task_type="partial", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="partial", input=item_input("good", "bad"),
                start_worker=lambda: None,
            )
            task_id = task.id

        run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            items = list(db.scalars(
                select(TaskItem).where(TaskItem.task_id == task_id).order_by(TaskItem.sequence)
            ))
            assert task.status == TaskStatus.PARTIALLY_SUCCEEDED.value
            assert task.completed_items == 1
            assert task.failed_items == 1
            assert task.progress == 50
            assert items[1].status == TaskItemStatus.FAILED.value
            assert items[1].error == "bad failed"
    finally:
        unregister_handler("partial")


@pytest.mark.parametrize(
    ("titles", "skip_titles", "fail_title", "expected_status", "completed", "failed"),
    [
        (("skip",), {"skip"}, None, TaskStatus.SUCCEEDED.value, 0, 0),
        (("good", "skip"), {"skip"}, None, TaskStatus.SUCCEEDED.value, 1, 0),
        (("bad", "skip"), {"skip"}, "bad", TaskStatus.PARTIALLY_SUCCEEDED.value, 0, 1),
    ],
)
def test_skipped_items_are_satisfied_work(
    titles, skip_titles, fail_title, expected_status, completed, failed
):
    _engine, factory = make_factory()
    register_handler("skip", SkippingHandler(skip_titles, fail_title=fail_title))
    try:
        with factory() as db:
            task = create_task(
                db, task_type="skip", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="skip", input=item_input(*titles), start_worker=lambda: None,
            )
            task_id = task.id

        run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            assert task.status == expected_status
            expected_progress = 100 if failed == 0 else round(100 / len(titles))
            assert task.progress == expected_progress
            assert task.completed_items == completed
            assert task.failed_items == failed
            assert load_json(task.result_json)["skipped"] == len(skip_titles)
    finally:
        unregister_handler("skip")


def test_summary_failure_changes_success_to_failed():
    _engine, factory = make_factory()
    register_handler("summary-fail", FailingSummaryHandler([]))
    try:
        with factory() as db:
            task = create_task(
                db, task_type="summary-fail", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="summary", input=item_input("item"), start_worker=lambda: None,
            )
            task_id = task.id
        run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            assert task.status == TaskStatus.FAILED.value
            assert task.error == "任务结果汇总失败：summary failed"
    finally:
        unregister_handler("summary-fail")


def test_summary_failure_preserves_cancelled_status():
    _engine, factory = make_factory()
    register_handler("cancel-summary-fail", CancellingFailingSummaryHandler(factory))
    try:
        with factory() as db:
            task = create_task(
                db, task_type="cancel-summary-fail", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="cancel summary", input=item_input("item"), start_worker=lambda: None,
            )
            task_id = task.id
        run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            assert task.status == TaskStatus.CANCELLED.value
            assert task.error == "任务结果汇总失败：summary failed after cancel"
    finally:
        unregister_handler("cancel-summary-fail")


def test_no_loop_task_builds_and_runs_one_item():
    _engine, factory = make_factory()
    calls: list[str] = []
    register_handler("single", RecordingHandler(calls))
    try:
        with factory() as db:
            task = create_task(
                db, task_type="single", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="single task", input=item_input("all operations"),
                start_worker=lambda: None,
            )
            task_id = task.id

        run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            assert task.total_items == 1
            assert task.status == TaskStatus.SUCCEEDED.value
            assert task.progress == 100
            assert calls == ["all operations"]
    finally:
        unregister_handler("single")


@pytest.mark.parametrize(
    ("task_type", "handler", "expected"),
    [
        ("empty", InvalidItemHandler([]), "至少需要一个子任务"),
        (
            "not-json",
            InvalidItemHandler([TaskItemSpec("bad input", input={"value": object()})]),
            "无法序列化为 JSON",
        ),
    ],
)
def test_invalid_item_plan_does_not_create_task(task_type, handler, expected):
    _engine, factory = make_factory()
    register_handler(task_type, handler)
    worker_started = []
    try:
        with factory() as db:
            with pytest.raises(TaskPlanningError, match=expected):
                create_task(
                    db, task_type=task_type, scheduling_policy=SchedulingPolicy.COMPUTE,
                    title="invalid", start_worker=lambda: worker_started.append(True),
                )
            assert db.scalar(select(func.count()).select_from(Task)) == 0
            assert db.scalar(select(func.count()).select_from(TaskItem)) == 0
        assert worker_started == []
    finally:
        unregister_handler(task_type)


def test_missing_handler_and_invalid_task_input_do_not_create_task():
    _engine, factory = make_factory()
    with factory() as db:
        with pytest.raises(TaskPlanningError, match="未注册任务处理器"):
            create_task(
                db, task_type="missing", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="missing", start_worker=lambda: None,
            )
        with pytest.raises(TaskPlanningError, match="总任务输入无法序列化"):
            create_task(
                db, task_type="missing", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="bad input", input={"value": object()}, start_worker=lambda: None,
            )
        assert db.scalar(select(func.count()).select_from(Task)) == 0


def test_cancel_is_idempotent_for_pending_and_running_tasks():
    _engine, factory = make_factory()
    register_handler("cancel-state", RecordingHandler([]))
    try:
        with factory() as db:
            pending = create_task(
                db, task_type="cancel-state", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="pending", input=item_input("pending item"), start_worker=lambda: None,
            )
            request_cancel(db, pending)
            request_cancel(db, pending)
            assert pending.status == TaskStatus.CANCELLED.value
            assert db.scalar(
                select(TaskItem).where(TaskItem.task_id == pending.id)
            ).status == TaskItemStatus.CANCELLED.value

            running = create_task(
                db, task_type="cancel-state", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="running", input=item_input("running item"), start_worker=lambda: None,
            )
            running.status = TaskStatus.RUNNING.value
            db.commit()
            request_cancel(db, running)
            request_cancel(db, running)
            assert running.status == TaskStatus.CANCEL_REQUESTED.value
    finally:
        unregister_handler("cancel-state")


def test_running_task_cancels_at_handler_checkpoint():
    _engine, factory = make_factory()
    register_handler("cancel-checkpoint", CancellingHandler(factory))
    try:
        with factory() as db:
            task = create_task(
                db, task_type="cancel-checkpoint",
                scheduling_policy=SchedulingPolicy.COMPUTE, title="cancel checkpoint",
                input=item_input("current", "remaining"), start_worker=lambda: None,
            )
            task_id = task.id

        run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            items = list(db.scalars(
                select(TaskItem).where(TaskItem.task_id == task_id).order_by(TaskItem.sequence)
            ))
            assert task.status == TaskStatus.CANCELLED.value
            assert [item.status for item in items] == [
                TaskItemStatus.CANCELLED.value, TaskItemStatus.CANCELLED.value
            ]
    finally:
        unregister_handler("cancel-checkpoint")


def test_worker_lease_allows_only_one_owner():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    migrate_task_tables(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    assert acquire_worker_lease(factory, "first") is True
    assert acquire_worker_lease(factory, "second") is False
    release_worker_lease(factory, "first")
    assert acquire_worker_lease(factory, "second") is True


def test_worker_exits_after_configured_idle_timeout():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    migrate_task_tables(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    assert run_worker(
        session_factory=factory, idle_timeout_seconds=0,
        poll_interval_seconds=0.001, lease_wait_seconds=0,
    ) is True


def test_worker_recovery_marks_interrupted_tasks_failed():
    _engine, factory = make_factory()
    register_handler("interrupted", RecordingHandler([]))
    try:
        with factory() as db:
            task = create_task(
                db, task_type="interrupted", scheduling_policy=SchedulingPolicy.COMPUTE,
                title="interrupted", input=item_input("running", "waiting"),
                start_worker=lambda: None,
            )
            task.status = TaskStatus.RUNNING.value
            first = db.scalar(select(TaskItem).where(
                TaskItem.task_id == task.id, TaskItem.sequence == 0
            ))
            first.status = TaskItemStatus.RUNNING.value
            task_id = task.id
            db.commit()

            assert recover_interrupted_tasks(db) == 1
            assert db.get(Task, task_id).status == TaskStatus.FAILED.value
            items = list(db.scalars(
                select(TaskItem).where(TaskItem.task_id == task_id).order_by(TaskItem.sequence)
            ))
            assert [item.status for item in items] == [
                TaskItemStatus.FAILED.value, TaskItemStatus.SKIPPED.value
            ]
    finally:
        unregister_handler("interrupted")


def test_task_api_lists_details_items_and_cancels(db):
    register_handler("api-test", RecordingHandler([]))
    register_handler("api-other", RecordingHandler([]))
    try:
        task = create_task(
            db, task_type="api-test", scheduling_policy=SchedulingPolicy.COMPUTE,
            title="API test", input=item_input("first"), start_worker=lambda: None,
        )
        other_task = create_task(
            db, task_type="api-other", scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
            title="Other API test", input=item_input("second"), start_worker=lambda: None,
        )
        app = FastAPI()
        app.include_router(api_router)

        def session_override():
            yield db

        app.dependency_overrides[get_session] = session_override
        client = TestClient(app)

        listing = client.get("/api/tasks").json()
        assert listing["total"] == 2
        assert listing["items"][0]["id"] == other_task.id
        compute = client.get("/api/tasks", params={"scheduling_policy": "COMPUTE"}).json()
        assert compute["total"] == 1
        assert compute["items"][0]["id"] == task.id
        updates = client.get("/api/tasks", params={"scheduling_policy": "EXCLUSIVE_UPDATE"}).json()
        assert updates["total"] == 1
        assert updates["items"][0]["id"] == other_task.id
        assert client.get("/api/tasks/active-count").json() == {"count": 2}
        assert client.get("/api/tasks/active-count", params={"scheduling_policy": "COMPUTE"}).json() == {"count": 1}
        assert client.get("/api/tasks/active-count", params={"scheduling_policy": "EXCLUSIVE_UPDATE"}).json() == {"count": 1}
        assert client.get(f"/api/tasks/{task.id}/items").json()["items"][0]["title"] == "first"
        cancelled = client.post(f"/api/tasks/{task.id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == TaskStatus.CANCELLED.value
        assert client.get("/api/tasks/99999").status_code == 404
    finally:
        unregister_handler("api-test")
        unregister_handler("api-other")
