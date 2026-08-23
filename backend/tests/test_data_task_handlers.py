from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import JygsCredential, Stock
from app.database.session import Base
from app.market_data.provider.base import MarketDataError
from app.market_data.schemas import StockSummary
from app.tasks.handlers import register_handler, unregister_handler
from app.tasks.handlers.jygs import JygsLimitUpSyncHandler, TASK_TYPE as JYGS_TASK_TYPE
from app.tasks.handlers.stock_directory import StockDirectoryRefreshHandler, TASK_TYPE as STOCK_TASK_TYPE
from app.tasks.models import SchedulingPolicy, Task, TaskItem, TaskItemStatus, TaskStatus
from app.tasks.runner import run_next_task
from app.tasks.service import create_task, load_json


def file_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'tasks.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


class FakeProvider:
    def __init__(self, stocks):
        self.stocks = stocks
        self.closed = False

    def list_stocks(self):
        return self.stocks

    def close(self):
        self.closed = True


def test_jygs_successful_zero_record_day_is_skipped_next_time(tmp_path, monkeypatch):
    factory = file_factory(tmp_path)
    handler = JygsLimitUpSyncHandler(factory)
    register_handler(JYGS_TASK_TYPE, handler)
    monkeypatch.setattr("app.tasks.handlers.jygs.fetch_date_records", lambda *_args: [])
    try:
        with factory() as db:
            db.add(JygsCredential(id=1, session="test-session"))
            db.commit()
            first = create_task(
                db, task_type=JYGS_TASK_TYPE, scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title="first", input={"start_date": "2026-08-23", "end_date": "2026-08-23"},
                start_worker=lambda: None,
            )
            first_id = first.id
        run_next_task(factory)

        with factory() as db:
            second = create_task(
                db, task_type=JYGS_TASK_TYPE, scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title="second", input={"start_date": "2026-08-23", "end_date": "2026-08-23"},
                start_worker=lambda: None,
            )
            second_id = second.id
        run_next_task(factory)

        with factory() as db:
            assert db.get(Task, first_id).status == TaskStatus.SUCCEEDED.value
            second = db.get(Task, second_id)
            item = db.scalar(select(TaskItem).where(TaskItem.task_id == second_id))
            assert second.status == TaskStatus.SUCCEEDED.value
            assert second.completed_items == 0
            assert second.progress == 100
            assert load_json(second.result_json) == {
                "selected_days": 1, "executed_days": 0, "skipped_days": 1,
                "succeeded_days": 0, "failed_days": 0, "records": 0,
            }
            assert item.status == TaskItemStatus.SKIPPED.value
    finally:
        unregister_handler(JYGS_TASK_TYPE)


def test_jygs_task_planning_allows_more_than_366_days(tmp_path):
    handler = JygsLimitUpSyncHandler(file_factory(tmp_path))
    items = handler.build_items({"start_date": "2024-01-01", "end_date": "2025-01-02"})
    assert len(items) == 368


def test_jygs_failed_day_does_not_stop_later_dates(tmp_path, monkeypatch):
    factory = file_factory(tmp_path)
    handler = JygsLimitUpSyncHandler(factory)
    register_handler(JYGS_TASK_TYPE, handler)

    def fetch(_db, trade_date):
        if trade_date == "2026-08-22":
            raise RuntimeError("first day failed")
        return []

    monkeypatch.setattr("app.tasks.handlers.jygs.fetch_date_records", fetch)
    try:
        with factory() as db:
            db.add(JygsCredential(id=1, session="test-session"))
            db.commit()
            task = create_task(
                db, task_type=JYGS_TASK_TYPE, scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title="partial", input={"start_date": "2026-08-22", "end_date": "2026-08-23"},
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
            assert [item.status for item in items] == [
                TaskItemStatus.FAILED.value, TaskItemStatus.SUCCEEDED.value
            ]
            assert load_json(task.result_json)["failed_days"] == 1
            assert load_json(task.result_json)["succeeded_days"] == 1
    finally:
        unregister_handler(JYGS_TASK_TYPE)


def test_stock_directory_handler_updates_atomically_and_closes_provider(tmp_path):
    factory = file_factory(tmp_path)
    provider = FakeProvider([
        StockSummary(symbol="600519.SH", code="600519", name="贵州茅台"),
        StockSummary(symbol="000001.SZ", code="000001", name="平安银行"),
    ])
    register_handler(STOCK_TASK_TYPE, StockDirectoryRefreshHandler(factory, lambda: provider))
    try:
        with factory() as db:
            task = create_task(
                db, task_type=STOCK_TASK_TYPE, scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title="stocks", start_worker=lambda: None,
            )
            task_id = task.id
        run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            assert task.status == TaskStatus.SUCCEEDED.value
            assert load_json(task.result_json) == {"source_count": 2, "processed_count": 2}
            assert {row.symbol for row in db.scalars(select(Stock)).all()} == {
                "600519.SH", "000001.SZ"
            }
        assert provider.closed is True
    finally:
        unregister_handler(STOCK_TASK_TYPE)


def test_stock_directory_empty_response_fails_without_deleting_existing_stock(tmp_path):
    factory = file_factory(tmp_path)
    provider = FakeProvider([])
    register_handler(STOCK_TASK_TYPE, StockDirectoryRefreshHandler(factory, lambda: provider))
    try:
        with factory() as db:
            db.add(Stock(symbol="600519.SH", code="600519", name="贵州茅台"))
            db.commit()
            task = create_task(
                db, task_type=STOCK_TASK_TYPE, scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
                title="stocks", start_worker=lambda: None,
            )
            task_id = task.id
        run_next_task(factory)
        with factory() as db:
            assert db.get(Task, task_id).status == TaskStatus.FAILED.value
            assert "股票目录为空" in db.get(Task, task_id).error
            assert db.get(Stock, "600519.SH") is not None
        assert provider.closed is True
    finally:
        unregister_handler(STOCK_TASK_TYPE)
