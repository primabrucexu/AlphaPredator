from pathlib import Path
import ast

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


def test_sqlite_schema_does_not_create_task_item_info(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'schema-no-task-item.db'
    ensure_sqlite_schema(sqlite_path)

    session_factory = get_sqlite_session_factory(sqlite_path)
    with session_factory() as session:
        row = session.connection().exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'task_item_info'"
        ).fetchone()

    assert row is None


def test_sqlite_schema_creates_macd_alert_tables(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'schema-macd-alert.db'
    ensure_sqlite_schema(sqlite_path)

    session_factory = get_sqlite_session_factory(sqlite_path)
    with session_factory() as session:
        rows = session.connection().exec_driver_sql(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                'macd_alert_result',
                'macd_alert_backtest_sample',
                'macd_alert_report'
              )
            """
        ).fetchall()

    assert {row[0] for row in rows} == {
        'macd_alert_result',
        'macd_alert_backtest_sample',
        'macd_alert_report',
    }


def test_production_sqlite_business_access_uses_orm() -> None:
    """Business code must not bypass ORM for SQLite access."""
    app_root = Path(__file__).parents[1] / 'app'
    allowed_files = {
        app_root / 'db' / 'sqlite.py',
        app_root / 'db' / 'duckdb_storage.py',
    }
    violations: list[str] = []

    for path in app_root.rglob('*.py'):
        if path in allowed_files:
            continue
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name for alias in node.names}
                if 'sqlite3' in imported:
                    violations.append(f'{path.relative_to(app_root.parent)} imports sqlite3')
            if isinstance(node, ast.ImportFrom) and node.module == 'app.db.sqlite':
                imported = {alias.name for alias in node.names}
                if 'connect_sqlite' in imported:
                    violations.append(f'{path.relative_to(app_root.parent)} imports connect_sqlite')

    assert violations == []
