from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_SUCCEEDED = "PARTIALLY_SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskItemStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class SchedulingPolicy(StrEnum):
    COMPUTE = "COMPUTE"
    EXCLUSIVE_UPDATE = "EXCLUSIVE_UPDATE"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=lambda: str(uuid4()))
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    scheduling_policy: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), index=True, default=TaskStatus.PENDING.value)
    total_items: Mapped[int] = mapped_column(default=0)
    completed_items: Mapped[int] = mapped_column(default=0)
    failed_items: Mapped[int] = mapped_column(default=0)
    progress: Mapped[int | None] = mapped_column(default=0)
    status_message: Mapped[str] = mapped_column(Text, default="")
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)
    cancel_requested_at: Mapped[datetime | None]


class TaskItem(Base):
    __tablename__ = "task_items"
    __table_args__ = (UniqueConstraint("task_id", "sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int]
    title: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), index=True, default=TaskItemStatus.PENDING.value)
    current: Mapped[int | None] = mapped_column(default=0)
    total: Mapped[int | None]
    progress: Mapped[int | None] = mapped_column(default=0)
    status_message: Mapped[str] = mapped_column(Text, default="")
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class TaskWorkerLease(Base):
    __tablename__ = "task_worker_lease"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    owner_id: Mapped[str] = mapped_column(String(64), default="")
    acquired_at: Mapped[datetime | None]
    heartbeat_at: Mapped[datetime | None]


class ModeScreeningStockResult(Base):
    __tablename__ = "mode_screening_stock_results"
    __table_args__ = (
        UniqueConstraint("task_id", "symbol"),
        UniqueConstraint("task_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    task_item_id: Mapped[int] = mapped_column(
        ForeignKey("task_items.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    code: Mapped[str] = mapped_column(String(6))
    name: Mapped[str] = mapped_column(String(64))
    as_of_date: Mapped[str] = mapped_column(String(10))
    data_start_date: Mapped[str | None] = mapped_column(String(10))
    data_end_date: Mapped[str | None] = mapped_column(String(10))
    signal_date: Mapped[str | None] = mapped_column(String(10))
    insufficient_history: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    backtest_status: Mapped[str] = mapped_column(String(32))
    current_state: Mapped[str] = mapped_column(String(32), default="completed")
    completed_trades: Mapped[int] = mapped_column(default=0)
    winning_trades: Mapped[int] = mapped_column(default=0)
    losing_trades: Mapped[int] = mapped_column(default=0)
    flat_trades: Mapped[int] = mapped_column(default=0)
    win_rate: Mapped[str | None] = mapped_column(String(64))
    average_return: Mapped[str | None] = mapped_column(String(64))
    maximum_return: Mapped[str | None] = mapped_column(String(64))
    minimum_return: Mapped[str | None] = mapped_column(String(64))
    open_trade_json: Mapped[str] = mapped_column(Text, default="null")
    pending_orders_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class ModeScreeningTradeResult(Base):
    __tablename__ = "mode_screening_trade_results"
    __table_args__ = (UniqueConstraint("stock_result_id", "sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_result_id: Mapped[int] = mapped_column(
        ForeignKey("mode_screening_stock_results.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int]
    signal_date: Mapped[str] = mapped_column(String(10))
    buy_date: Mapped[str] = mapped_column(String(10))
    buy_price: Mapped[str] = mapped_column(String(64))
    realized_return: Mapped[str] = mapped_column(String(64))


class ModeScreeningSaleResult(Base):
    __tablename__ = "mode_screening_sale_results"
    __table_args__ = (UniqueConstraint("trade_result_id", "sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_result_id: Mapped[int] = mapped_column(
        ForeignKey("mode_screening_trade_results.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int]
    trade_date: Mapped[str] = mapped_column(String(10))
    reason_id: Mapped[str] = mapped_column(String(32))
    price: Mapped[str] = mapped_column(String(64))
    fraction_of_original: Mapped[str] = mapped_column(String(64))
    return_rate: Mapped[str] = mapped_column(String(64))
