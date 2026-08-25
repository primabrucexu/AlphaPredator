from __future__ import annotations

from typing import Any

from .config import Config
from .notifier import TaskNotifier


__version__ = "0.1.0"
_notifier: TaskNotifier | None = None


def register(ctx: Any) -> None:
    global _notifier
    if _notifier is not None:
        return
    _notifier = TaskNotifier(ctx, Config.from_env())
    ctx.register_hook("post_tool_call", _notifier.on_post_tool_call)
    _notifier.start()
