from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.modules.macd_alert.service import (
    list_macd_alert_backtest_samples,
    list_macd_alert_results,
    scan_macd_alerts,
    track_macd_alerts,
)
from app.schemas.macd_alert import (
    MacdAlertScanRequest,
    MacdAlertScanResponse,
    MacdAlertTrackRequest,
    MacdAlertTrackResponse,
)

router = APIRouter()


@router.post('/scan', response_model=MacdAlertScanResponse)
def scan_macd_alert(body: MacdAlertScanRequest) -> MacdAlertScanResponse:
    try:
        result = scan_macd_alerts(
            trade_date=body.trade_date,
            universe_scope=body.universe_scope,
            markets=body.markets,
            exclude_st=body.exclude_st,
            green_shrink_days=body.green_shrink_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return MacdAlertScanResponse(**result)


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
