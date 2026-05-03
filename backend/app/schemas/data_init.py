from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Legacy schemas (kept for backward compatibility)
# ---------------------------------------------------------------------------


class InitStatusResponse(BaseModel):
    status: str = Field(..., description='idle | running | done | error')
    trade_date: str = Field('', description='当前处理日期')
    total_stocks: int = Field(0, description='总天数（兼容字段）')
    processed_stocks: int = Field(0, description='已处理天数（兼容字段）')
    started_at: str = Field('', description='开始时间 (ISO 8601 UTC)')
    finished_at: str = Field('', description='完成时间 (ISO 8601 UTC)')
    error_message: str = Field('', description='错误信息')


MarketBoard = Literal['主板', '创业板', '科创板', '北交所']

ALL_MARKET_BOARDS: list[MarketBoard] = ['主板', '创业板', '科创板', '北交所']


class UpdateResult(BaseModel):
    trade_date: str
    stock_count: int
    bar_count: int
    start_trade_date: str = Field('', description='补齐区间起始交易日')
    end_trade_date: str = Field('', description='补齐区间结束交易日')
    processed_trade_dates: list[str] = Field(default_factory=list, description='已补齐的交易日列表')


class TokenConfigResponse(BaseModel):
    is_configured: bool = Field(..., description='Tushare token 是否已配置')


class SaveTokenRequest(BaseModel):
    token: str = Field(..., min_length=1, description='Tushare API token')


class StockListUploadResponse(BaseModel):
    total_stocks: int = Field(..., description='CSV 中股票总数（含退市）')
    active_stocks: int = Field(..., description='当前上市股票数（list_status=L）')
    boards: dict[str, int] = Field(..., description='各板块上市股票数量')


# ---------------------------------------------------------------------------
# Phase 2.10: Init overview (homepage status panel)
# ---------------------------------------------------------------------------


class InitOverviewResponse(BaseModel):
    init_completed: bool = Field(..., description='是否已完成初始化（status=done）')
    token_configured: bool = Field(..., description='Tushare token 是否已配置')
    stock_list_uploaded: bool = Field(..., description='股票清单 CSV 是否已上传')
    stock_list_updated_at: str | None = Field(None, description='股票清单最后上传时间（ISO 8601 UTC）')
    daily_quote_cutoff_time: str | None = Field(None, description='每日行情更新截止时间（ISO 8601）')
    board_counts: dict[str, int] = Field(default_factory=dict, description='各板块当前上市股票数')


# ---------------------------------------------------------------------------
# V2 init schemas
# ---------------------------------------------------------------------------


class CreateTaskRequest(BaseModel):
    start_date: str = Field(
        ...,
        pattern=r'^\d{8}$',
        description='导入起始日期（YYYYMMDD）',
    )
    end_date: str = Field(
        ...,
        pattern=r'^\d{8}$',
        description='导入截止日期（YYYYMMDD）',
    )
    mode: str = Field('RANGE', description='任务模式：RANGE | REIMPORT_DAY')


class TaskResponse(BaseModel):
    task_id: str
    mode: str
    start_date: str
    end_date: str
    status: str = Field(..., description='PENDING | RUNNING | SUCCESS | FAILED')
    total_days: int
    processed_days: int
    trading_days: int
    done_trading_days: int
    current_date: str = Field('', description='当前正在处理的日期（YYYYMMDD）')
    error_message: str = ''
    created_at: str = ''
    started_at: str = ''
    finished_at: str = ''
    progress_percent: float = Field(0.0, description='整体进度百分比（0–100）')

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> 'TaskResponse':
        total = row.get('total_days', 0)
        processed = row.get('processed_days', 0)
        pct = round(processed / total * 100, 1) if total > 0 else 0.0
        return cls(
            task_id=row['task_id'],
            mode=row.get('mode', 'RANGE'),
            start_date=row.get('start_date', ''),
            end_date=row.get('end_date', ''),
            status=row.get('status', 'PENDING'),
            total_days=total,
            processed_days=processed,
            trading_days=row.get('trading_days', 0),
            done_trading_days=row.get('done_trading_days', 0),
            current_date=row.get('current_date', ''),
            error_message=row.get('error_message', ''),
            created_at=row.get('created_at', ''),
            started_at=row.get('started_at', ''),
            finished_at=row.get('finished_at', ''),
            progress_percent=pct,
        )


class TaskDayItem(BaseModel):
    task_id: str
    trade_date: str
    is_trading_day: bool
    status: str
    row_count: int = 0
    started_at: str = ''
    finished_at: str = ''
    error_message: str = ''


class TaskDaysResponse(BaseModel):
    task_id: str
    total: int
    page: int
    per_page: int
    days: list[TaskDayItem]


class ReimportDayRequest(BaseModel):
    trade_date: str = Field(
        ...,
        pattern=r'^\d{8}$',
        description='需要重导的交易日（YYYYMMDD）',
    )


class DataRangeInfo(BaseModel):
    min_trade_date: str | None = None
    max_trade_date: str | None = None
    trading_day_count: int = 0


class InitV2OverviewResponse(BaseModel):
    running_task: TaskResponse | None = None
    latest_task: TaskResponse | None = None
    data_range: DataRangeInfo = Field(default_factory=DataRangeInfo)
    token_configured: bool = False
    stock_list_uploaded: bool = False
    stock_list_updated_at: str | None = None
    daily_quote_cutoff_time: str | None = None
    board_counts: dict[str, int] = Field(default_factory=dict)
