from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.stock_linkage.service import (
    create_stock_linkage_backtest_job,
    get_stock_linkage_job,
    list_stock_linkage_jobs,
    list_stock_linkage_results,
    start_stock_linkage_backtest_job,
)
from app.schemas.stock_linkage import (
    StockLinkageBacktestCreateRequest,
    StockLinkageBacktestJobResponse,
    StockLinkageBacktestResultResponse,
)

router = APIRouter()


@router.post('/backtests', response_model=StockLinkageBacktestJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_stock_linkage_backtest(body: StockLinkageBacktestCreateRequest) -> StockLinkageBacktestJobResponse:
    try:
        job = create_stock_linkage_backtest_job(body.to_service_request())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if not start_stock_linkage_backtest_job(job.job_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='已有联动回测任务正在运行，请稍后再试')
    return StockLinkageBacktestJobResponse(**job.__dict__)


@router.get('/backtests', response_model=list[StockLinkageBacktestJobResponse])
def list_stock_linkage_backtests(
    limit: int = Query(20, ge=1, le=100),
) -> list[StockLinkageBacktestJobResponse]:
    return [StockLinkageBacktestJobResponse(**job.__dict__) for job in list_stock_linkage_jobs(limit=limit)]


@router.get('/backtests/{job_id}', response_model=StockLinkageBacktestJobResponse)
def get_stock_linkage_backtest(job_id: str) -> StockLinkageBacktestJobResponse:
    job = get_stock_linkage_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='联动回测任务不存在')
    return StockLinkageBacktestJobResponse(**job.__dict__)


@router.get('/backtests/{job_id}/results', response_model=list[StockLinkageBacktestResultResponse])
def get_stock_linkage_backtest_results(
    job_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[StockLinkageBacktestResultResponse]:
    rows = list_stock_linkage_results(job_id, limit=limit, offset=offset)
    return [StockLinkageBacktestResultResponse(**row) for row in rows]
