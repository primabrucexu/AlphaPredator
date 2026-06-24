from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.modules.macd_alert.service import (
    create_macd_alert_scan_task,
    list_macd_alert_backtest_samples,
    list_macd_alert_results,
    track_macd_alerts,
    validate_stock_macd_alert,
)
from app.modules.market_data.initializer import get_task, start_task
from app.schemas.macd_alert import (
    MacdAlertScanRequest,
    MacdStockValidateRequest,
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


@router.post('/stock-validate', response_model=dict)
def validate_stock_macd_alert_route(body: MacdStockValidateRequest) -> dict:
    try:
        return validate_stock_macd_alert(
            stock_code=body.stock_code,
            end_date=body.end_date,
            lookback_days=body.lookback_days,
            green_shrink_days=body.green_shrink_days,
            cross_zone=body.cross_zone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get('/results', response_model=list[dict])
def get_macd_alert_results(
    trade_date: str,
    pattern_key: str | None = None,
    cross_zone: str | None = None,
    limit: int = Query(20, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return list_macd_alert_results(
        trade_date=trade_date,
        pattern_key=pattern_key,
        cross_zone=cross_zone,
        limit=limit,
        offset=offset,
    )


_CSV_HEADERS = [
    '股票代码', '股票名称', '类型', '收盘价', '金叉价', '金叉距离%',
    '维持价', '维持距离%', 'DIF', 'DEA', 'MACD柱', '绿柱缩短天数',
    '最近涨停日', '涨停题材', '涨停距今交易日', '题材热度',
    '跟踪状态', '回测样本数', '金叉成功率%', '胜率%', '平均收益率%',
    '评分', '摘要',
]


@router.get('/results/export')
def export_macd_alert_results_csv(trade_date: str) -> StreamingResponse:
    rows = list_macd_alert_results(trade_date=trade_date, limit=10000, offset=0)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_CSV_HEADERS)
    for r in rows:
        writer.writerow([
            r.get('stock_code', ''),
            r.get('stock_name', ''),
            r.get('cross_zone', ''),
            r.get('close_price', ''),
            r.get('next_cross_trigger_price', ''),
            f"{(r.get('cross_trigger_distance_pct') or 0) * 100:.2f}",
            r.get('next_trend_keep_price', ''),
            f"{(r.get('trend_keep_distance_pct') or 0) * 100:.2f}",
            r.get('macd_dif', ''),
            r.get('macd_dea', ''),
            r.get('macd_hist', ''),
            r.get('green_shrink_days', ''),
            r.get('last_limit_up_date', ''),
            r.get('last_limit_up_theme', ''),
            r.get('last_limit_up_days_ago', ''),
            r.get('theme_heat_level', ''),
            r.get('track_status', ''),
            r.get('backtest_sample_count', ''),
            f"{(r.get('backtest_cross_success_rate') or 0) * 100:.2f}",
            f"{(r.get('backtest_win_rate') or 0) * 100:.2f}",
            f"{(r.get('backtest_avg_return_pct') or 0) * 100:.2f}",
            r.get('score', ''),
            r.get('summary', ''),
        ])
    output.seek(0)
    filename = f'macd-alert-{trade_date}.csv'
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@router.get('/results/{alert_id}/backtest-samples', response_model=list[dict])
def get_macd_alert_backtest_samples(
    alert_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return list_macd_alert_backtest_samples(alert_result_id=alert_id, limit=limit, offset=offset)
