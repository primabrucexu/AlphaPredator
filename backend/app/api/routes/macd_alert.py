from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.macd_alert.service import (
    create_macd_alert_scan_task,
    list_macd_alert_backtest_samples,
    list_macd_alert_results,
    track_macd_alerts,
)
from app.modules.market_data.initializer import get_task, start_task
from app.schemas.macd_alert import (
    MacdAlertScanRequest,
    MacdAlertTrackRequest,
    MacdAlertTrackResponse,
)
from app.schemas.data_init import TaskResponse

router = APIRouter()


@router.post('/scan', response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
def scan_macd_alert(body: MacdAlertScanRequest) -> TaskResponse:
    try:
        task = create_macd_alert_scan_task(
            trade_date=body.trade_date,
            universe_scope=body.universe_scope,
            markets=body.markets,
            exclude_st=body.exclude_st,
            green_shrink_days=body.green_shrink_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    started = start_task(task['task_id'])
    if not started:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='已有 MACD 预警扫描任务正在运行')
    task = get_task(task['task_id']) or task
    return TaskResponse.from_db_row(task)


@router.post('/track', response_model=MacdAlertTrackResponse)
def track_macd_alert(body: MacdAlertTrackRequest) -> MacdAlertTrackResponse:
    result = track_macd_alerts(trade_date=body.trade_date, source_trade_date=body.source_trade_date)
    return MacdAlertTrackResponse(**result)


@router.get('/results', response_model=list[dict])
def get_macd_alert_results(
    trade_date: str,
    pattern_key: str | None = None,
    cross_zone: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return list_macd_alert_results(
        trade_date=trade_date,
        pattern_key=pattern_key,
        cross_zone=cross_zone,
        limit=limit,
        offset=offset,
    )


@router.get('/results/{alert_id}/backtest-samples', response_model=list[dict])
def get_macd_alert_backtest_samples(
    alert_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return list_macd_alert_backtest_samples(alert_result_id=alert_id, limit=limit, offset=offset)
