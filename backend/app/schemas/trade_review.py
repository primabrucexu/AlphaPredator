from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 操作明细
# ---------------------------------------------------------------------------

class OperationItem(BaseModel):
    id: Optional[str] = None
    review_id: Optional[str] = None
    trade_time: str = Field(..., description='操作时间，ISO格式精确到秒')
    operation_type: str = Field(
        ..., description='操作类型：buy/sell/add/reduce/t_buy/t_sell'
    )
    price: float = Field(..., description='成交价格（元）')
    quantity: int = Field(..., description='成交数量（股）')
    amount: float = Field(..., description='成交金额（元）')
    source: str = Field('manual', description='来源：ocr/manual/import')
    note: str = Field('', description='备注')
    sort_index: Optional[int] = None


# ---------------------------------------------------------------------------
# 关键决策备注
# ---------------------------------------------------------------------------

class DecisionNoteItem(BaseModel):
    id: Optional[str] = None
    review_id: Optional[str] = None
    related_operation_id: Optional[str] = None
    decision_type: str = Field(
        ..., description='决策类型：add/reduce/sell/t/other'
    )
    decision_time: str = Field(..., description='决策时间，ISO格式')
    reason: str = Field('', description='决策原因')


# ---------------------------------------------------------------------------
# 复盘主记录
# ---------------------------------------------------------------------------

class TradeReviewSessionBase(BaseModel):
    stock_code: str
    stock_name: str
    start_date: str = Field(..., description='建仓日期，YYYY-MM-DD')
    end_date: Optional[str] = Field(None, description='清仓���期，持仓中则为空')
    status: str = Field('open', description='open（持仓中）/ closed（已清仓）')
    total_buy_amount: Optional[float] = None
    total_sell_amount: Optional[float] = None
    realized_pnl: Optional[float] = None
    return_rate: Optional[float] = None
    entry_reason: str = ''
    entry_expectation: str = ''
    reflection_did_well: str = ''
    reflection_did_poorly: str = ''
    reflection_redo_plan: str = ''


class CreateTradeReviewRequest(TradeReviewSessionBase):
    operations: list[OperationItem] = []
    decision_notes: list[DecisionNoteItem] = []


class UpdateTradeReviewRequest(TradeReviewSessionBase):
    operations: list[OperationItem] = []
    decision_notes: list[DecisionNoteItem] = []


class TradeReviewSessionItem(TradeReviewSessionBase):
    id: str
    ai_status: str
    created_at: str
    updated_at: str


class TradeReviewDetail(TradeReviewSessionItem):
    operations: list[OperationItem] = []
    decision_notes: list[DecisionNoteItem] = []
    ai_result: Optional[dict[str, Any]] = None


class TradeReviewListResponse(BaseModel):
    total: int
    items: list[TradeReviewSessionItem]


# ---------------------------------------------------------------------------
# 月度统计
# ---------------------------------------------------------------------------

class MonthlyStatsResponse(BaseModel):
    month_key: str
    trade_count: int
    win_count: int
    loss_count: int
    realized_pnl: float
    average_return_rate: Optional[float]
    max_gain: Optional[float]
    max_loss: Optional[float]
    reviews: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# OCR 解析
# ---------------------------------------------------------------------------

class OcrParseRequest(BaseModel):
    image_base64: str = Field(..., description='base64 编码的图片内容（不含 data:xxx;base64, 前缀）')
    mime_type: str = Field('image/jpeg', description='图片 MIME 类型')


class OcrOperationItem(BaseModel):
    trade_time: str
    operation_type: str
    price: float
    quantity: int
    amount: float


class OcrParseResponse(BaseModel):
    stock_name: Optional[str] = None
    stock_code: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    total_buy_amount: Optional[float] = None
    total_sell_amount: Optional[float] = None
    realized_pnl: Optional[float] = None
    return_rate: Optional[float] = None
    operations: list[OcrOperationItem] = []
    raw_lines: list[str] = Field([], description='OCR 识别出的全部文本行，用于调试')

