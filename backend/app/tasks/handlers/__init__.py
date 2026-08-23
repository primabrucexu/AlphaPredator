from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.tasks.context import TaskContext
from app.tasks.models import Task, TaskItem


@dataclass(frozen=True)
class TaskItemSpec:
    title: str
    input: dict[str, Any] = field(default_factory=dict)
    total: int | None = None


class TaskItemSkipped(Exception):
    def __init__(self, message: str, result: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.result = result or {}


class TaskHandler(Protocol):
    def build_items(self, task_input: dict[str, Any]) -> Iterable[TaskItemSpec]: ...

    def run_item(self, task: Task, item: TaskItem, context: TaskContext) -> dict | None: ...

    def summarize(self, task: Task, items: list[TaskItem]) -> dict | None: ...


_handlers: dict[str, TaskHandler] = {}


def register_handler(task_type: str, handler: TaskHandler) -> None:
    _handlers[task_type] = handler


def unregister_handler(task_type: str) -> None:
    _handlers.pop(task_type, None)


def get_handler(task_type: str) -> TaskHandler | None:
    return _handlers.get(task_type)
