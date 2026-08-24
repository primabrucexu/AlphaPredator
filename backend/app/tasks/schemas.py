from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskRead(BaseModel):
    id: int
    task_type: str
    scheduling_policy: str
    title: str
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    progress: int | None
    status_message: str
    input: dict[str, Any]
    result: dict[str, Any]
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime
    cancel_requested_at: datetime | None


class TaskItemRead(BaseModel):
    id: int
    task_id: int
    sequence: int
    title: str
    status: str
    current: int | None
    total: int | None
    progress: int | None
    status_message: str
    result: dict[str, Any]
    error: str
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class TaskPage(BaseModel):
    items: list[TaskRead]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class TaskItemPage(BaseModel):
    items: list[TaskItemRead]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class ActiveTaskCount(BaseModel):
    count: int


class JygsLimitUpTaskCreate(BaseModel):
    start_date: date
    end_date: date


class MarketDailyBarsTaskCreate(BaseModel):
    mode: Literal["incremental", "full"]
