from __future__ import annotations

from sqlalchemy import Engine, inspect

from .models import Task, TaskItem, TaskWorkerLease


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
