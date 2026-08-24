from __future__ import annotations

import json
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.database.session import SessionLocal
from app.market_data.provider import get_process_market_provider
from app.market_data.provider.base import MarketDataProvider
from app.market_data.service import StockService
from app.tasks.context import TaskContext
from app.tasks.models import Task, TaskItem, TaskItemStatus

from . import TaskItemSpec


TASK_TYPE = "stock_directory_refresh"


def _result(item: TaskItem) -> dict:
    value = json.loads(item.result_json or "{}")
    return value if isinstance(value, dict) else {}


class StockDirectoryRefreshHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session] = SessionLocal,
        provider_factory: Callable[[], MarketDataProvider] = get_process_market_provider,
    ):
        self.session_factory = session_factory
        self.provider_factory = provider_factory

    def build_items(self, task_input: dict) -> list[TaskItemSpec]:
        return [TaskItemSpec(title="刷新 A 股股票搜索目录")]

    def run_item(self, task: Task, item: TaskItem, context: TaskContext) -> dict:
        context.report_progress(0, None, "正在获取股票目录")
        provider = self.provider_factory()
        try:
            with self.session_factory() as business_db:
                count = StockService(provider).sync_directory(
                    business_db,
                    progress=lambda current, total: context.report_progress(
                        current, total, f"正在更新股票目录：{current}/{total}"
                    ),
                )
            return {"source_count": count, "processed_count": count}
        finally:
            provider.close()

    def summarize(self, task: Task, items: list[TaskItem]) -> dict:
        succeeded = next(
            (item for item in items if item.status == TaskItemStatus.SUCCEEDED.value),
            None,
        )
        result = _result(succeeded) if succeeded is not None else {}
        return {
            "source_count": int(result.get("source_count") or 0),
            "processed_count": int(result.get("processed_count") or 0),
        }
