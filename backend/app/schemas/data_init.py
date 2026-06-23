from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Base schemas
# ---------------------------------------------------------------------------


class InitStatusResponse(BaseModel):
    status: str = Field(..., description='idle | running | done | error')
    trade_date: str = Field('', description='当前处理日期')
    total_stocks: int = Field(0, description='总任务项数量')
    processed_stocks: int = Field(0, description='已处理任务项数量')
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


class MairuiLicenceConfigResponse(BaseModel):
    configured: bool = Field(False, description='麦蕊 licence 是否已配置')
    masked_licence: str | None = Field(None, description='脱敏后的 licence，用于页面展示')
    source: str = Field('none', description='配置来源：file | none')
    rate_limit_per_minute: int = Field(..., ge=1, description='麦蕊请求速率限制（次/分钟）')
    fetch_concurrency: int = Field(..., ge=1, description='行情数据并发拉取数量')


class SaveMairuiLicenceRequest(BaseModel):
    licence: str = Field('', description='麦蕊 licence 原文；留空时保留现有配置')
    rate_limit_per_minute: int = Field(..., ge=1, description='麦蕊请求速率限制（次/分钟）')
    fetch_concurrency: int | None = Field(None, ge=1, description='兼容旧前端字段；新任务并发由请求速率自动推导')



# ---------------------------------------------------------------------------
# Phase 2.10: Init overview (homepage status panel)
# ---------------------------------------------------------------------------


class InitOverviewResponse(BaseModel):
    init_completed: bool = Field(..., description='是否已完成初始化（status=done）')
    market_data_configured: bool = Field(..., description='行情数据源凭据是否已配置')
    daily_quote_cutoff_time: str | None = Field(None, description='每日行情更新截止时间（ISO 8601）')
    market_data_start_date: str | None = Field(None, description='本地已入库行情起始交易日（YYYY-MM-DD）')
    market_data_end_date: str | None = Field(None, description='本地已入库行情截止交易日（YYYY-MM-DD）')
    market_data_trading_day_count: int = Field(0, description='本地已入库行情交易日数量')
    market_data_last_sync_start_date: str | None = Field(None, description='最近成功行情同步任务的起始日期（YYYYMMDD）')
    market_data_last_sync_end_date: str | None = Field(None, description='最近成功行情同步任务的截止日期（YYYYMMDD）')
    market_data_last_sync_finished_at: str | None = Field(None, description='最近成功行情同步任务完成时间（ISO 8601）')
    board_counts: dict[str, int] = Field(default_factory=dict, description='各板块当前上市股票数')


# ---------------------------------------------------------------------------
# V2 init schemas
# ---------------------------------------------------------------------------


class CreateTaskRequest(BaseModel):
    start_date: str = Field(
        '',
        pattern=r'^(\d{8}|)$',
        description='导入起始日期（YYYYMMDD）；STOCK_LIST_SYNC 可留空，后端自动填当日',
    )
    end_date: str = Field(
        '',
        pattern=r'^(\d{8}|)$',
        description='导入截止日期（YYYYMMDD）；STOCK_LIST_SYNC 可留空',
    )
    mode: str = Field('FULL_SYNC', description='任务模式：FULL_SYNC | INCREMENTAL_SYNC | RANGE（旧别名）')
    task_type: str = Field('MARKET_DATA', description='任务类型：STOCK_LIST_SYNC | MARKET_DATA | MARKET_DATA_5M | JYGS_REVIEW | MACD_ALERT_SCAN')


class TaskResponse(BaseModel):
    task_id: str
    task_type: str = Field('MARKET_DATA', description='任务类型：STOCK_LIST_SYNC | MARKET_DATA | MARKET_DATA_5M | JYGS_REVIEW | MACD_ALERT_SCAN')
    start_date: str
    end_date: str
    status: str = Field(..., description='PENDING | RUNNING | SUCCESS | FAILED | TERMINATED')
    total_items: int
    processed_items: int
    current_label: str = Field('', description='当前处理项标签')
    error_message: str = ''
    task_start_date: str = ''
    task_end_date: str = ''
    progress_percent: float = Field(0.0, description='整体进度百分比（0–100）')

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> 'TaskResponse':
        total = row.get('total_items', 0)
        processed = row.get('processed_items', 0)
        pct = round(processed / total * 100, 1) if total > 0 else 0.0
        return cls(
            task_id=row['task_id'],
            task_type=row.get('task_type', 'MARKET_DATA'),
            start_date=row.get('start_date', ''),
            end_date=row.get('end_date', ''),
            status=row.get('status', 'PENDING'),
            total_items=total,
            processed_items=processed,
            current_label=row.get('current_label', ''),
            error_message=row.get('error_message', ''),
            task_start_date=row.get('task_start_date', ''),
            task_end_date=row.get('task_end_date', ''),
            progress_percent=pct,
        )


class TaskDayItem(BaseModel):
    task_id: str
    trade_date: str
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


class RetrySubtaskRequest(BaseModel):
    item_label: str = Field(..., min_length=1, description='子任务标识：MARKET_DATA/MARKET_DATA_5M=股票代码, JYGS_REVIEW=YYYYMMDD')


class TaskItemsResponse(BaseModel):
    """任务处理进度快照：基于 task_info 合成。"""
    task_id: str
    task_type: str
    label_type: str = Field('', description='处理单元类型：stock | date | sync')
    label_name: str = Field('', description='处理单元中文名称，如"股票代码"')
    total_items: int
    processed_items: int
    current_label: str = ''
    status: str
    error_message: str = ''
    progress_percent: float = 0.0


class DataRangeInfo(BaseModel):
    min_trade_date: str | None = None
    max_trade_date: str | None = None
    trading_day_count: int = 0


class BatchTaskRequest(BaseModel):
    start_date: str = Field(
        ...,
        pattern=r'^\d{8}$',
        description='MARKET_DATA / JYGS_REVIEW 共用的起始日期（YYYYMMDD）',
    )
    end_date: str = Field(
        ...,
        pattern=r'^\d{8}$',
        description='MARKET_DATA / JYGS_REVIEW 共用的截止日期（YYYYMMDD）',
    )


class BatchTaskResponse(BaseModel):
    stock_list_task: TaskResponse
    market_data_task: TaskResponse
    jygs_review_task: TaskResponse


class InitV2OverviewResponse(BaseModel):
    running_task: TaskResponse | None = None
    latest_task: TaskResponse | None = None
    latest_market_data_task: TaskResponse | None = None
    data_range: DataRangeInfo = Field(default_factory=DataRangeInfo)
    market_data_configured: bool = False
    daily_quote_cutoff_time: str | None = None
    board_counts: dict[str, int] = Field(default_factory=dict)
