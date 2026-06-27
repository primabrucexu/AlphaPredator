from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class MacdAlertScanRequest(BaseModel):
    trade_date: str = Field(..., description='扫描交易日 YYYY-MM-DD')
    universe_scope: str = Field('market', description='股票池范围，第一版仅支持 market')
    markets: list[str] = Field(default_factory=lambda: ['主板'], description='市场板块')
    exclude_st: bool = Field(True, description='是否排除 ST')
    green_shrink_days: int = Field(2, ge=1, le=10, description='连续绿柱缩短天数')

    @field_validator('trade_date')
    @classmethod
    def validate_trade_date(cls, value: str) -> str:
        datetime.strptime(value, '%Y-%m-%d')
        return value


class MacdAlertTrackRequest(BaseModel):
    trade_date: str = Field(..., description='跟踪交易日 YYYY-MM-DD')
    source_trade_date: str = Field(..., description='来源预警交易日 YYYY-MM-DD')

    @field_validator('trade_date', 'source_trade_date')
    @classmethod
    def validate_trade_date(cls, value: str) -> str:
        datetime.strptime(value, '%Y-%m-%d')
        return value


class MacdStockValidateRequest(BaseModel):
    stock_code: str = Field(..., min_length=6, max_length=6, description='6位股票代码')
    end_date: str = Field(..., description='验证截止交易日 YYYY-MM-DD')
    lookback_days: int = Field(720, ge=30, le=3000, description='回看交易日数量')
    green_shrink_days: int = Field(2, ge=1, le=10, description='连续绿柱缩短天数')
    cross_zone: str = Field('all', description='形态范围：all/underwater/above_zero/mixed')

    @field_validator('stock_code', mode='before')
    @classmethod
    def normalize_stock_code(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if len(normalized) == 8 and normalized[:2] in {'SH', 'SZ', 'BJ'}:
            return normalized[2:]
        if len(normalized) == 9 and normalized[6:] in {'.SH', '.SZ', '.BJ'}:
            return normalized[:6]
        return normalized

    @field_validator('end_date')
    @classmethod
    def validate_end_date(cls, value: str) -> str:
        datetime.strptime(value, '%Y-%m-%d')
        return value


class MacdAlertScanResponse(BaseModel):
    trade_date: str
    total_scanned: int
    matched_count: int
    report_generatable: bool
    report_generation_hint: str
    results: list[dict]


class MacdAlertTrackResponse(BaseModel):
    trade_date: str
    source_trade_date: str
    tracked_count: int
    cross_confirmed_count: int
    trend_kept_count: int
    trend_weakened_count: int
    data_missing_count: int
    report_generatable: bool
    report_generation_hint: str
    results: list[dict]
