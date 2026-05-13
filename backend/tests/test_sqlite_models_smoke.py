from pathlib import Path

from sqlmodel import select

from app.db.session import get_sqlite_session_factory
from app.db.sqlite import ensure_sqlite_schema
from app.models.sqlite_models import (
    DataRangeMeta,
    InitTask,
    InitTaskDay,
    JygsSyncLog,
    StockList,
    StockProfile,
)


def test_sqlite_model_smoke_crud(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'orm-smoke.db'
    ensure_sqlite_schema(sqlite_path)

    session_factory = get_sqlite_session_factory(sqlite_path)
    with session_factory() as session:
        session.add(
            StockList(
                ts_code='000001.SZ',
                symbol='000001',
                name='平安银行',
                cnspell='PAYH',
                market='SZ',
                list_status='L',
                list_date='19910403',
                delist_date='',
                uploaded_at='2026-05-10T00:00:00Z',
            )
        )
        session.add(
            StockProfile(
                stock_code='000001',
                stock_name='平安银行',
                sectors_json='["银行"]',
                ai_quick_summary='示例摘要',
            )
        )
        session.add(
            DataRangeMeta(
                dataset='daily_bars',
                min_trade_date='2024-01-02',
                max_trade_date='2026-05-09',
                trading_day_count=600,
                updated_at='2026-05-10T00:00:00Z',
            )
        )
        session.commit()

        stock = session.execute(
            select(StockList).where(StockList.ts_code == '000001.SZ')
        ).scalars().one()
        profile = session.execute(
            select(StockProfile).where(StockProfile.stock_code == '000001')
        ).scalars().one()
        meta = session.execute(
            select(DataRangeMeta).where(DataRangeMeta.dataset == 'daily_bars')
        ).scalars().one()

        assert stock.name == '平安银行'
        assert profile.stock_name == '平安银行'
        assert meta.trading_day_count == 600


def test_sqlite_task_models_smoke(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'orm-task-smoke.db'
    ensure_sqlite_schema(sqlite_path)

    session_factory = get_sqlite_session_factory(sqlite_path)
    with session_factory() as session:
        task = InitTask(
            task_id='task-001',
            task_type='MARKET_DATA',
            mode='RANGE',
            start_date='20240102',
            end_date='20240105',
            status='PENDING',
            total_days=4,
            processed_days=0,
            trading_days=4,
            done_trading_days=0,
            created_at='2026-05-10T00:00:00Z',
        )
        day = InitTaskDay(
            task_id='task-001',
            trade_date='20240102',
            is_trading_day=1,
            status='PENDING',
            row_count=0,
        )
        sync_log = JygsSyncLog(
            slot_key='2026-05-10:daily',
            trade_date='2026-05-10',
            mode='daily',
            status='SUCCESS',
            message='ok',
            triggered_at='2026-05-10T08:30:00+08:00',
        )
        session.add(task)
        session.add(day)
        session.add(sync_log)
        session.commit()

        stored_task = session.execute(
            select(InitTask).where(InitTask.task_id == 'task-001')
        ).scalars().one()
        stored_day = session.execute(
            select(InitTaskDay).where(InitTaskDay.task_id == 'task-001')
        ).scalars().one()
        stored_log = session.execute(
            select(JygsSyncLog).where(JygsSyncLog.slot_key == '2026-05-10:daily')
        ).scalars().one()

        assert stored_task.total_days == 4
        assert stored_day.trade_date == '20240102'
        assert stored_log.status == 'SUCCESS'
