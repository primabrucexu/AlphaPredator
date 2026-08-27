from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.models import Stock
from app.database.session import Base, get_session
from app.market_data.storage import StoredDailyBar
from app.screening.backtest import BacktestAction, BacktestInstruction
from app.screening.models import RuleEvaluation
from app.screening.registry import RuleRegistry
from app.tasks.handlers import register_handler
from app.tasks.handlers.individual_backtest import IndividualBacktestHandler
from app.tasks.handlers.production import register_production_handlers
from app.tasks.handlers.screening import ScreeningRuleExecuteHandler
from app.tasks.models import SchedulingPolicy, Task, TaskItem, TaskStatus
from app.tasks.runner import run_next_task
from app.tasks.service import create_task, load_json


def make_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def bars():
    return [
        StoredDailyBar(
            trade_date=date(2026, 1, 1) + timedelta(days=index),
            open=Decimal("10"), high=Decimal("12"), low=Decimal("9"),
            close=Decimal("11"), volume=100, amount=Decimal("1000"),
        )
        for index in range(3)
    ]


class FakeStore:
    def __init__(self):
        self.closed = False

    def daily_bars(self, symbol, *, end_date):
        return [item for item in bars() if item.trade_date <= end_date]

    def close(self):
        self.closed = True


class TestRule:
    rule_id = "TEST"
    revision = 1

    def validate_parameters(self, parameters):
        return {"enabled": bool(parameters.get("enabled", True))}

    def evaluate(self, stock, source, parameters):
        return RuleEvaluation(
            matched=parameters["enabled"] and stock.code.startswith("00"),
            signal_date=source[-1].trade_date,
            evidence=(),
            metrics={"bar_count": len(source)},
        )


class TestBacktestSession:
    def on_bar(self, context):
        if context.bar.trade_date == date(2026, 1, 1):
            return [BacktestInstruction(
                BacktestAction.BUY, context.bar.open, "B1", context.bar.trade_date
            )]
        if context.bar.trade_date == date(2026, 1, 2):
            return [BacktestInstruction(
                BacktestAction.SELL, context.bar.close, "EX1", context.bar.trade_date
            )]
        return []

    def pending_orders(self):
        return []


def registry():
    result = RuleRegistry()
    result.register(TestRule(), backtest_factory=lambda _stock, _parameters: TestBacktestSession())
    return result


def make_client(factory):
    app = FastAPI()
    app.include_router(api_router)

    def session_override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = session_override
    return TestClient(app)


def test_screening_task_uses_one_stable_item_per_stock_and_worker_store():
    factory = make_factory()
    store = FakeStore()
    handler = ScreeningRuleExecuteHandler(
        registry=registry(), session_factory=factory, store_factory=lambda: store
    )
    register_handler("screening_rule_execute", handler)
    try:
        with factory() as db:
            db.add_all([
                Stock(symbol="000001.SZ", code="000001", name="平安银行"),
                Stock(symbol="600519.SH", code="600519", name="贵州茅台"),
            ])
            db.commit()
            task = create_task(
                db,
                task_type="screening_rule_execute",
                scheduling_policy=SchedulingPolicy.COMPUTE,
                title="test screening",
                input={
                    "rule_id": "TEST",
                    "rule_revision": 1,
                    "parameters": {"enabled": True},
                    "as_of_date": "2026-01-03",
                },
                start_worker=lambda: None,
            )
            task_id = task.id
            items = list(db.scalars(select(TaskItem).where(TaskItem.task_id == task_id).order_by(TaskItem.sequence)))
            assert [load_json(item.input_json)["symbol"] for item in items] == ["000001.SZ", "600519.SH"]
            assert not store.closed

        assert run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            assert task.status == TaskStatus.SUCCEEDED.value
            result = load_json(task.result_json)
            assert result["matched_stocks"] == 1
            assert result["matches"] == [{
                "symbol": "000001.SZ",
                "code": "000001",
                "name": "平安银行",
                "data_end_date": "2026-01-03",
                "signal_date": "2026-01-03",
                "evidence": [],
                "metrics": {"bar_count": 3},
                "insufficient_history": False,
            }]
        assert store.closed
    finally:
        register_production_handlers()


def test_individual_backtest_task_has_one_item_and_reuses_registered_rule():
    factory = make_factory()
    store = FakeStore()
    handler = IndividualBacktestHandler(
        registry=registry(), session_factory=factory, store_factory=lambda: store
    )
    register_handler("individual_backtest", handler)
    try:
        with factory() as db:
            db.add(Stock(symbol="000001.SZ", code="000001", name="平安银行"))
            db.commit()
            task = create_task(
                db,
                task_type="individual_backtest",
                scheduling_policy=SchedulingPolicy.COMPUTE,
                title="test backtest",
                input={
                    "rule_id": "TEST",
                    "rule_revision": 1,
                    "parameters": {},
                    "symbol": "000001.SZ",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-03",
                },
                start_worker=lambda: None,
            )
            task_id = task.id
            assert task.total_items == 1

        assert run_next_task(factory)
        with factory() as db:
            task = db.get(Task, task_id)
            result = load_json(task.result_json)
            assert task.status == TaskStatus.SUCCEEDED.value
            assert result["mode"] == "individual"
            assert result["completed_trades"] == 1
        assert store.closed
    finally:
        register_production_handlers()


def test_rest_entries_only_plan_compute_tasks_and_normalize_symbols(monkeypatch):
    factory = make_factory()
    rules = registry()
    register_handler(
        "screening_rule_execute",
        ScreeningRuleExecuteHandler(registry=rules, session_factory=factory),
    )
    register_handler(
        "individual_backtest",
        IndividualBacktestHandler(registry=rules, session_factory=factory),
    )
    monkeypatch.setattr("app.tasks.routes.start_worker_process", lambda: None)
    try:
        with factory() as db:
            db.add(Stock(symbol="000001.SZ", code="000001", name="平安银行"))
            db.commit()
        client = make_client(factory)
        screening = client.post("/api/tasks/screening-rule-execute", json={
            "rule_id": "TEST",
            "rule_revision": 1,
            "parameters": {},
            "as_of_date": "2026-01-03",
            "symbols": ["000001"],
        })
        assert screening.status_code == 202
        assert screening.json()["scheduling_policy"] == SchedulingPolicy.COMPUTE.value
        assert screening.json()["input"]["symbols"] == ["000001.SZ"]

        backtest = client.post("/api/tasks/individual-backtest", json={
            "rule_id": "TEST",
            "rule_revision": 1,
            "parameters": {},
            "symbol": "000001",
            "start_date": "2026-01-01",
            "end_date": "2026-01-03",
        })
        assert backtest.status_code == 202
        assert backtest.json()["scheduling_policy"] == SchedulingPolicy.COMPUTE.value
        assert backtest.json()["input"]["symbol"] == "000001.SZ"
    finally:
        register_production_handlers()
