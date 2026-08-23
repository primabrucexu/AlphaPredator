from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.session import SessionLocal
from app.jygs.client import fetch_date_records, replace_date_records
from app.tasks.context import TaskContext
from app.tasks.models import Task, TaskItem, TaskItemStatus

from . import TaskItemSkipped, TaskItemSpec


TASK_TYPE = "jygs_limit_up_sync"


def _input(item: TaskItem) -> dict:
    value = json.loads(item.input_json or "{}")
    return value if isinstance(value, dict) else {}


def _result(item: TaskItem) -> dict:
    value = json.loads(item.result_json or "{}")
    return value if isinstance(value, dict) else {}


class JygsLimitUpSyncHandler:
    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal):
        self.session_factory = session_factory

    def build_items(self, task_input: dict) -> list[TaskItemSpec]:
        start = date.fromisoformat(str(task_input["start_date"]))
        end = date.fromisoformat(str(task_input["end_date"]))
        if end < start:
            raise ValueError("结束日期不能早于开始日期")
        items = []
        current = start
        while current <= end:
            trade_date = current.isoformat()
            items.append(TaskItemSpec(
                title=f"同步 {trade_date}",
                input={"trade_date": trade_date},
                total=1,
            ))
            current += timedelta(days=1)
        return items

    def run_item(self, task: Task, item: TaskItem, context: TaskContext) -> dict:
        trade_date = str(_input(item).get("trade_date") or "")
        date.fromisoformat(trade_date)
        context.check_cancelled()
        succeeded = context.db.scalar(
            select(TaskItem.id)
            .join(Task, Task.id == TaskItem.task_id)
            .where(
                Task.task_type == TASK_TYPE,
                TaskItem.status == TaskItemStatus.SUCCEEDED.value,
                func.json_extract(TaskItem.input_json, "$.trade_date") == trade_date,
            )
            .limit(1)
        )
        if succeeded is not None:
            raise TaskItemSkipped(
                "历史同步已成功，已跳过",
                {"trade_date": trade_date, "records": 0, "reason": "already_succeeded"},
            )

        context.check_cancelled()
        with self.session_factory() as business_db:
            records = fetch_date_records(business_db, trade_date)
            context.check_cancelled()
            count = replace_date_records(business_db, trade_date, records)
        return {"trade_date": trade_date, "records": count}

    def summarize(self, task: Task, items: list[TaskItem]) -> dict:
        succeeded = [item for item in items if item.status == TaskItemStatus.SUCCEEDED.value]
        failed = [item for item in items if item.status == TaskItemStatus.FAILED.value]
        skipped = [item for item in items if item.status == TaskItemStatus.SKIPPED.value]
        return {
            "selected_days": len(items),
            "executed_days": len(succeeded) + len(failed),
            "skipped_days": len(skipped),
            "succeeded_days": len(succeeded),
            "failed_days": len(failed),
            "records": sum(int(_result(item).get("records") or 0) for item in succeeded),
        }
