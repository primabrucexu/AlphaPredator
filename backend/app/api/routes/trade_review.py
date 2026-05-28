from fastapi import APIRouter, HTTPException, Query

from app.modules.trade_review.ocr_parser import parse_trade_screenshot
from app.modules.trade_review.service import trade_review_service
from app.schemas.trade_review import (
    CreateTradeReviewRequest,
    MonthlyStatsResponse,
    OcrParseRequest,
    OcrParseResponse,
    TradeReviewDetail,
    TradeReviewListResponse,
    UpdateTradeReviewRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# OCR 解析
# ---------------------------------------------------------------------------

@router.post('/ocr-parse', response_model=OcrParseResponse)
def ocr_parse(req: OcrParseRequest) -> OcrParseResponse:
    """
    接受 base64 图片，用本地 RapidOCR 识别同花顺交易记录，
    返回结构化的交易数据，供前端展示并人工校对后保存。
    """
    try:
        return parse_trade_screenshot(req.image_base64)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'OCR 解析失败：{e}')


# ---------------------------------------------------------------------------
# 复盘记录 CRUD
# ---------------------------------------------------------------------------

@router.get('', response_model=TradeReviewListResponse)
def list_reviews(
    month: str | None = Query(None, description='月份筛选，格式 YYYY-MM'),
    stock_code: str | None = Query(None, description='股票代码筛选'),
    status: str | None = Query(None, description='状态筛选：open / closed'),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TradeReviewListResponse:
    return trade_review_service.list_reviews(
        month=month, stock_code=stock_code, status=status,
        limit=limit, offset=offset,
    )


@router.post('', response_model=TradeReviewDetail, status_code=201)
def create_review(req: CreateTradeReviewRequest) -> TradeReviewDetail:
    return trade_review_service.create_review(req)


@router.get('/{review_id}', response_model=TradeReviewDetail)
def get_review(review_id: str) -> TradeReviewDetail:
    result = trade_review_service.get_review(review_id)
    if not result:
        raise HTTPException(status_code=404, detail='复盘记录不存在')
    return result


@router.put('/{review_id}', response_model=TradeReviewDetail)
def update_review(review_id: str, req: UpdateTradeReviewRequest) -> TradeReviewDetail:
    result = trade_review_service.update_review(review_id, req)
    if not result:
        raise HTTPException(status_code=404, detail='复盘记录不存在')
    return result


@router.delete('/{review_id}', status_code=204)
def delete_review(review_id: str) -> None:
    ok = trade_review_service.delete_review(review_id)
    if not ok:
        raise HTTPException(status_code=404, detail='复盘记录不存在')


# ---------------------------------------------------------------------------
# 月度统计
# ---------------------------------------------------------------------------

@router.get('/monthly/{month_key}', response_model=MonthlyStatsResponse)
def get_monthly_stats(month_key: str) -> MonthlyStatsResponse:
    """
    实时聚合指定月份的复盘统计。month_key 格式：YYYY-MM，如 2026-05。
    """
    return trade_review_service.get_monthly_stats(month_key)

