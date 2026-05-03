from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InitStatusResponse(BaseModel):
    status: str = Field(..., description='idle | running | done | error')
    trade_date: str = Field('', description='最近完成初始化的交易日期')
    total_stocks: int = Field(0, description='本次初始化股票总数')
    processed_stocks: int = Field(0, description='已处理股票数')
    started_at: str = Field('', description='开始时间 (ISO 8601 UTC)')
    finished_at: str = Field('', description='完成时间 (ISO 8601 UTC)')
    error_message: str = Field('', description='错误信息（仅 error 状态时有值）')


MarketBoard = Literal['主板', '创业板', '科创板']

ALL_MARKET_BOARDS: list[MarketBoard] = ['主板', '创业板', '科创板']


class StartInitRequest(BaseModel):
    history_days: int = Field(60, ge=1, le=3650, description='历史行情天数（日历天数近似）')
    market_filters: list[MarketBoard] = Field(
        default_factory=lambda: list(ALL_MARKET_BOARDS),
        description='市场板块筛选：主板 / 创业板 / 科创板（默认全量）',
    )


class UpdateResult(BaseModel):
    trade_date: str
    stock_count: int
    bar_count: int


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
    stock_list_updated_at: str | None = Field(None, description='股票清单最后上传时间（ISO 8601 UTC），未上传则为 null')
    daily_quote_cutoff_time: str | None = Field(None, description='每日行情更新截止时间（ISO 8601）')
    board_counts: dict[str, int] = Field(default_factory=dict, description='各板块当前上市股票数（仅已上传时有值）')
