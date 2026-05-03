from pydantic import BaseModel, Field


class InitStatusResponse(BaseModel):
    status: str = Field(..., description='idle | running | done | error')
    trade_date: str = Field('', description='最近完成初始化的交易日期')
    total_stocks: int = Field(0, description='本次初始化股票总数')
    processed_stocks: int = Field(0, description='已处理股票数')
    started_at: str = Field('', description='开始时间 (ISO 8601 UTC)')
    finished_at: str = Field('', description='完成时间 (ISO 8601 UTC)')
    error_message: str = Field('', description='错误信息（仅 error 状态时有值）')


class StartInitRequest(BaseModel):
    history_days: int = Field(60, ge=1, le=365, description='历史行情天数（日历天数近似）')


class UpdateResult(BaseModel):
    trade_date: str
    stock_count: int
    bar_count: int
