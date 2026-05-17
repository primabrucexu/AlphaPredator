from pathlib import Path

from sqlmodel import select

from app.db.session import get_sqlite_session_factory
from app.db.sqlite import ensure_sqlite_schema
from app.models.sqlite_models import (
    DataRangeMeta,
    JygsSyncLog,
    StockList,
    StockProfile,
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
            select(StockList).where(StockList.full_code == '000001.SZ')
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
        sync_log = JygsSyncLog(
            slot_key='2026-05-10:daily',
            trade_date='2026-05-10',
            mode='daily',
            status='SUCCESS',
            message='ok',
            triggered_at='2026-05-10T08:30:00+08:00',
        )
        session.add(task)
        session.add(sync_log)
        session.commit()

        stored_task = session.execute(
            select(TaskInfo).where(TaskInfo.task_id == 'task-001')
        ).scalars().one()
        stored_log = session.execute(
            select(JygsSyncLog).where(JygsSyncLog.slot_key == '2026-05-10:daily')
        ).scalars().one()

        assert stored_task.total_items == 4
        assert stored_log.status == 'SUCCESS'
