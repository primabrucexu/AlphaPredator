from pathlib import Path

from sqlmodel import select

from app.db.session import get_sqlite_session_factory
from app.db.sqlite import ensure_sqlite_schema
from app.models.sqlite_models import (
    StockList,
    TaskInfo,
)


def test_sqlite_model_smoke_crud(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'orm-smoke.db'
    ensure_sqlite_schema(sqlite_path)

    session_factory = get_sqlite_session_factory(sqlite_path)
    with session_factory() as session:
        session.add(
            StockList(
                full_code='000001.SZ',
                code='000001',
                name='平安银行',
                is_st=False,
                cnspell='PAYH',
                market='主板',
            )
        )
        session.commit()

        stock = session.execute(
            select(StockList).where(StockList.full_code == '000001.SZ')
        ).scalars().one()

        assert stock.name == '平安银行'


def test_sqlite_task_models_smoke(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'orm-task-smoke.db'
    ensure_sqlite_schema(sqlite_path)

    session_factory = get_sqlite_session_factory(sqlite_path)
    with session_factory() as session:
        task = TaskInfo(
            task_id='task-001',
            task_type='MARKET_DATA',
            start_date='20240102',
            end_date='20240105',
            status='PENDING',
            total_items=4,
            processed_items=0,
            current_label='000001',
            error_message='',
            task_start_date='2026-05-10T00:00:00Z',
            task_end_date='',
        )
        session.add(task)
        session.commit()

        stored_task = session.execute(
            select(TaskInfo).where(TaskInfo.task_id == 'task-001')
        ).scalars().one()

        assert stored_task.total_items == 4
