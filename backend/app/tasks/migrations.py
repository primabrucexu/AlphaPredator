from __future__ import annotations

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
    created = False
    with engine.begin() as connection:
        for table in (
            ModeScreeningStockResult.__table__,
            ModeScreeningTradeResult.__table__,
            ModeScreeningSaleResult.__table__,
        ):
            if not inspect(connection).has_table(table.name):
                table.create(connection)
                created = True
    return created
