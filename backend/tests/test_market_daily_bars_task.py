from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import Stock
from app.database.session import Base
from app.market_data.schemas import DailyBar
from app.market_data.storage import DuckDbMarketDataStore
from app.tasks.handlers import register_handler, unregister_handler
from app.tasks.handlers.market_daily_bars import MarketDailyBarsUpdateHandler, TASK_TYPE
from app.tasks.models import SchedulingPolicy, Task, TaskItem, TaskItemStatus, TaskStatus
from app.tasks.runner import run_next_task
from app.tasks.service import create_task, load_json


def factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'tasks.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def bars(*values: tuple[str, float]) -> list[DailyBar]:
    return [DailyBar(
        date=day, open=close, high=close + 0.2, low=close - 0.2, close=close,
        volume=100, amount=1000,
    ) for day, close in values]


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.action_calls = []
        self.closed = False

    def get_daily_bars(self, symbol, count=250, start_date=None, end_date=None):
        self.calls.append((symbol, start_date, end_date))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def corporate_action(self, symbol):
        self.action_calls.append(symbol)
        return [{"日期": "2025-01-03", "方案": "分红"}]

    def close(self):
        self.closed = True


def create(factory_, mode="incremental"):
    with factory_() as db:
        task = create_task(
            db,
            task_type=TASK_TYPE,
            scheduling_policy=SchedulingPolicy.EXCLUSIVE_UPDATE,
            title="daily bars",
            input={"mode": mode, "target_end_date": "2025-01-04"},
            start_worker=lambda: None,
        )
        return task.id


def test_initial_full_then_unchanged_overlap_appends_only_new_bar(tmp_path):
    db_factory = factory(tmp_path)
    with db_factory() as db:
        db.add(Stock(symbol="000001.SZ", code="000001", name="平安银行"))
        db.commit()
    provider = FakeProvider([
        bars(("2025-01-02", 10), ("2025-01-03", 10.2)),
        bars(("2025-01-02", 10), ("2025-01-03", 10.2), ("2025-01-04", 10.3)),
    ])
    path = tmp_path / "market.duckdb"
    handler = MarketDailyBarsUpdateHandler(db_factory, lambda: provider, lambda: DuckDbMarketDataStore(path))
    register_handler(TASK_TYPE, handler)
    try:
        first_id = create(db_factory)
        run_next_task(db_factory)
        second_id = create(db_factory)
        run_next_task(db_factory)
        with db_factory() as db:
            first = db.get(Task, first_id)
            second = db.get(Task, second_id)
            assert first.status == second.status == TaskStatus.SUCCEEDED.value
            assert load_json(first.result_json)["full_stocks"] == 1
            assert load_json(second.result_json)["incremental_stocks"] == 1
            assert load_json(second.result_json)["written_rows"] == 1
        with DuckDbMarketDataStore(path) as store:
            assert len(store.recent_bars("000001.SZ", 10)) == 3
    finally:
        unregister_handler(TASK_TYPE)


def test_changed_overlap_queries_actions_and_rebuilds_full_history(tmp_path):
    db_factory = factory(tmp_path)
    with db_factory() as db:
        db.add(Stock(symbol="000001.SZ", code="000001", name="平安银行"))
        db.commit()
    path = tmp_path / "market.duckdb"
    with DuckDbMarketDataStore(path) as store:
        from app.market_data.storage import prepare_daily_bars
        store.replace_full("000001.SZ", prepare_daily_bars(
            bars(("2025-01-02", 10), ("2025-01-03", 10.2)),
            start_date=date(2025, 1, 1), end_date=date(2025, 1, 4),
        ))
    provider = FakeProvider([
        bars(("2025-01-02", 9), ("2025-01-03", 9.2)),
        bars(("2025-01-02", 9), ("2025-01-03", 9.2), ("2025-01-04", 9.3)),
    ])
    register_handler(TASK_TYPE, MarketDailyBarsUpdateHandler(
        db_factory, lambda: provider, lambda: DuckDbMarketDataStore(path)
    ))
    try:
        task_id = create(db_factory)
        run_next_task(db_factory)
        with db_factory() as db:
            item = db.scalar(select(TaskItem).where(TaskItem.task_id == task_id))
            result = load_json(item.result_json)
            assert result["reason"] == "overlap_changed"
            assert result["execution"] == "full"
            assert result["corporate_action_count"] == 1
            assert result["corporate_action_summary"] == [{"日期": "2025-01-03", "方案": "分红"}]
        assert provider.action_calls == ["000001.SZ"]
    finally:
        unregister_handler(TASK_TYPE)


def test_one_failed_stock_does_not_stop_next_stock(tmp_path):
    db_factory = factory(tmp_path)
    with db_factory() as db:
        db.add_all([
            Stock(symbol="000001.SZ", code="000001", name="平安银行"),
            Stock(symbol="600519.SH", code="600519", name="贵州茅台"),
        ])
        db.commit()
    provider = FakeProvider([
        RuntimeError("remote failed"),
        bars(("2025-01-02", 10)),
    ])
    register_handler(TASK_TYPE, MarketDailyBarsUpdateHandler(
        db_factory, lambda: provider, lambda: DuckDbMarketDataStore(tmp_path / "market.duckdb")
    ))
    try:
        task_id = create(db_factory, "full")
        run_next_task(db_factory)
        with db_factory() as db:
            task = db.get(Task, task_id)
            items = list(db.scalars(select(TaskItem).where(TaskItem.task_id == task_id).order_by(TaskItem.sequence)))
            assert task.status == TaskStatus.PARTIALLY_SUCCEEDED.value
            assert [item.status for item in items] == [
                TaskItemStatus.FAILED.value, TaskItemStatus.SUCCEEDED.value,
            ]
            assert load_json(task.result_json)["failed_stocks"] == 1
    finally:
        unregister_handler(TASK_TYPE)
