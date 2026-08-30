from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class Config:
    mcp_server_name: str
    api_url: str
    api_key: str
    poll_seconds: float
    database_path: Path

    @property
    def create_tool_names(self) -> frozenset[str]:
        prefix = f"mcp_{self.mcp_server_name}_"
        return frozenset({
            f"{prefix}create_stock_directory_refresh_task",
            f"{prefix}create_market_daily_bars_update_task",
            f"{prefix}retry_failed_market_daily_bars_task",
            f"{prefix}create_sr001_mode_screening_task",
        })

    @property
    def get_task_tool_name(self) -> str:
        return f"mcp_{self.mcp_server_name}_get_task"

    @classmethod
    def from_env(cls) -> "Config":
        hermes_home = Path(os.getenv("HERMES_HOME", "").strip() or Path.home() / ".hermes")
        data_dir = hermes_home / "plugin-data"
        return cls(
            mcp_server_name=os.getenv("ALPHAPREDATOR_MCP_SERVER_NAME", "ap").strip() or "ap",
            api_url=os.getenv(
                "ALPHAPREDATOR_HERMES_API_URL", "http://127.0.0.1:8642"
            ).strip().rstrip("/"),
            api_key=os.getenv("API_SERVER_KEY", ""),
            poll_seconds=_positive_float("ALPHAPREDATOR_TASK_POLL_SECONDS", 5.0),
            database_path=data_dir / "alphapredator-task-notifier.sqlite3",
        )
