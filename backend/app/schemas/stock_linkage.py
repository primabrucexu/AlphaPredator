from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.stock_linkage.models import StockLinkageBacktestRequest


class StockLinkageBacktestCreateRequest(BaseModel):
    a_select_mode: str = Field(..., description='A选择模式：manual_single / hot_limit_top')
    manual_a_full_code: str | None = Field(None, description='手动指定A股票完整代码')
    hot_top_n: int | None = Field(None, ge=1, le=200, description='热点复盘高频涨停股Top N')
    start_date: str = Field('2025-01-01', description='回测开始日期 YYYY-MM-DD')
    end_date: str = Field(..., description='回测结束日期 YYYY-MM-DD')
    min_sample_count: int = Field(30, ge=1, le=10000, description='最低样本数门槛')
    job_name: str | None = Field(None, max_length=255, description='任务名称')

    @field_validator('start_date', 'end_date')
    @classmethod
    def validate_date_text(cls, value: str) -> str:
        datetime.strptime(value, '%Y-%m-%d')
        return value

    def to_service_request(self) -> StockLinkageBacktestRequest:
        return StockLinkageBacktestRequest(
            a_select_mode=self.a_select_mode,
            manual_a_full_code=self.manual_a_full_code,
            hot_top_n=self.hot_top_n,
            start_date=self.start_date,
            end_date=self.end_date,
            min_sample_count=self.min_sample_count,
            job_name=self.job_name,
        )


class StockLinkageBacktestSummaryResponse(BaseModel):
    job_id: str
    status: str
    trigger_event_count: int
    baseline_count: int
    result_count: int


class StockLinkageBacktestJobResponse(BaseModel):
    job_id: str
    job_name: str | None
    a_select_mode: str
    manual_a_full_code: str | None
    hot_top_n: int | None
    start_date: str
    end_date: str
    min_sample_count: int
    status: str
    error_message: str | None
    created_at: str
    updated_at: str
    finished_at: str | None


class StockLinkageBacktestResultResponse(BaseModel):
    job_id: str
    a_full_code: str
    b_full_code: str
    trigger_type: str
    trigger_threshold: float
    observation_type: str
    target_threshold: float
    sample_count: int
    hit_count: int
    condition_probability: float
    baseline_probability: float
    probability_lift: float
    lift_multiple: float | None
    trigger_coverage_rate: float
    confidence_level: str
    score: float
