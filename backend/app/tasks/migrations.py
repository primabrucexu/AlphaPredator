from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import Engine, inspect

from .models import (
    ModeScreeningSaleResult,
    ModeScreeningStockResult,
    ModeScreeningTradeResult,
    Task,
    TaskItem,
    TaskWorkerLease,
)
from .mode_screening_state import derive_mode_screening_current_state


def migrate_task_tables(engine: Engine) -> bool:
    """Create the additive F002 tables and singleton lease row."""
    created = False
    with engine.begin() as connection:
        for table in (Task.__table__, TaskItem.__table__, TaskWorkerLease.__table__):
            if not inspect(connection).has_table(table.name):
                table.create(connection)
                created = True
        connection.exec_driver_sql(
            "INSERT OR IGNORE INTO task_worker_lease (id, owner_id) VALUES (1, '')"
        )
    return created


def migrate_task_public_uuids(engine: Engine) -> bool:
    """Add and backfill the public task UUID without changing integer keys."""
    changed = False
    with engine.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table(Task.__tablename__):
            return False
        columns = {column["name"] for column in inspector.get_columns(Task.__tablename__)}
        if "uuid" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE tasks ADD COLUMN uuid VARCHAR(36) NOT NULL DEFAULT ''"
            )
            changed = True

        rows = connection.exec_driver_sql("SELECT id, uuid FROM tasks ORDER BY id").all()
        seen: set[str] = set()
        for task_id, value in rows:
            public_uuid = str(value or "").strip().lower()
            if not public_uuid or public_uuid in seen:
                public_uuid = str(uuid4())
                connection.exec_driver_sql(
                    "UPDATE tasks SET uuid = ? WHERE id = ?",
                    (public_uuid, task_id),
                )
                changed = True
            seen.add(public_uuid)

        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_tasks_uuid ON tasks (uuid)"
        )
    return changed


def migrate_mode_screening_results(engine: Engine) -> bool:
    """Create additive F006.4 result tables without changing existing tasks."""
    changed = False
    with engine.begin() as connection:
        for table in (
            ModeScreeningStockResult.__table__,
            ModeScreeningTradeResult.__table__,
            ModeScreeningSaleResult.__table__,
        ):
            if not inspect(connection).has_table(table.name):
                table.create(connection)
                changed = True
        columns = {
            column["name"]
            for column in inspect(connection).get_columns(ModeScreeningStockResult.__tablename__)
        }
        if "current_state" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE mode_screening_stock_results "
                "ADD COLUMN current_state VARCHAR(32) NOT NULL DEFAULT 'completed'"
            )
            rows = connection.exec_driver_sql(
                """
                SELECT id, backtest_status, as_of_date, open_trade_json, pending_orders_json
                FROM mode_screening_stock_results
                """
            ).all()
            for result_id, backtest_status, as_of_date, open_trade_json, pending_orders_json in rows:
                try:
                    open_trade = json.loads(open_trade_json)
                except (json.JSONDecodeError, TypeError):
                    open_trade = None
                try:
                    pending_orders = json.loads(pending_orders_json)
                except (json.JSONDecodeError, TypeError):
                    pending_orders = []
                current_state = derive_mode_screening_current_state(
                    backtest_status=str(backtest_status),
                    as_of_date=str(as_of_date),
                    open_trade=open_trade if isinstance(open_trade, dict) else None,
                    pending_orders=pending_orders if isinstance(pending_orders, list) else [],
                )
                connection.exec_driver_sql(
                    "UPDATE mode_screening_stock_results SET current_state = ? WHERE id = ?",
                    (current_state, result_id),
                )
            changed = True
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_mode_screening_results_task_state "
            "ON mode_screening_stock_results (task_id, current_state)"
        )
    return changed
