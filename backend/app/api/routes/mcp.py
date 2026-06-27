from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.modules.macd_alert.service import (
    DISCLAIMER,
    create_macd_alert_scan_task,
    get_macd_daily_brief,
    list_macd_alert_backtest_samples as list_macd_alert_backtest_samples_service,
    list_macd_alert_results as list_macd_alert_results_service,
    track_macd_alerts as track_macd_alerts_service,
)
from app.modules.market_data.initializer import create_batch_tasks, get_overview, get_task, start_task


mcp = FastMCP(
    'AlphaPredator',
    instructions=(
        'A-share intelligent stock analysis workstation. '
        'MACD alert tools return technical observations only and do not provide investment advice.'
    ),
)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_alpha_predator_info() -> dict[str, str]:
    """Return basic MCP service information for connectivity verification."""
    return {
        'name': 'AlphaPredator',
        'mcp_status': 'ok',
        'capabilities_stage': 'F06-macd-alert',
    }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_macd_alert_daily_brief(trade_date: str | None = None, limit: int = 10) -> dict:
    """Return a MACD alert daily brief with freshness metadata."""
    safe_limit = max(1, min(int(limit), 30))
    result = get_macd_daily_brief(trade_date=trade_date, limit=safe_limit)
    return {'disclaimer': DISCLAIMER, **result}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_macd_alert_results(
    trade_date: str,
    cross_zone: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List MACD alert results with pagination."""
    safe_limit = max(1, min(int(limit), 100))
    rows = list_macd_alert_results_service(
        trade_date=trade_date,
        cross_zone=cross_zone,
        limit=safe_limit,
        offset=max(0, int(offset)),
    )
    return {'disclaimer': DISCLAIMER, 'items': rows, 'limit': safe_limit, 'offset': max(0, int(offset))}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_macd_alert_backtest_samples(alert_result_id: str, limit: int = 20, offset: int = 0) -> dict:
    """List historical samples for one MACD alert result with pagination."""
    safe_limit = max(1, min(int(limit), 100))
    rows = list_macd_alert_backtest_samples_service(
        alert_result_id=alert_result_id,
        limit=safe_limit,
        offset=max(0, int(offset)),
    )
    return {'disclaimer': DISCLAIMER, 'items': rows, 'limit': safe_limit, 'offset': max(0, int(offset))}


def _today_yyyymmdd() -> str:
    return datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')


def _add_one_day_yyyymmdd(date_str: str) -> str:
    return (datetime.strptime(date_str, '%Y%m%d') + timedelta(days=1)).strftime('%Y%m%d')


@mcp.tool()
def start_market_data_incremental_update(target_end_date: str | None = None) -> dict:
    """Create and start a MARKET_DATA incremental task from the latest successful sync to today."""
    overview = get_overview()
    latest_market_task = overview.get('latest_market_data_task')
    if not latest_market_task:
        return {
            'started': False,
            'task_id': None,
            'start_date': None,
            'end_date': target_end_date or _today_yyyymmdd(),
            'status': 'NO_BASELINE',
            'message': '暂无成功行情同步记录，请先执行一次全量行情同步。',
        }

    end_date = target_end_date or _today_yyyymmdd()
    try:
        start_date = _add_one_day_yyyymmdd(str(latest_market_task['end_date']))
    except (KeyError, ValueError):
        return {
            'started': False,
            'task_id': None,
            'start_date': None,
            'end_date': end_date,
            'status': 'INVALID_BASELINE',
            'message': '最近成功行情任务的截止日期格式异常，无法自动计算增量区间。',
        }

    if start_date > end_date:
        return {
            'started': False,
            'task_id': None,
            'start_date': start_date,
            'end_date': end_date,
            'status': 'UP_TO_DATE',
            'message': '行情已同步到目标日期，无需增量更新。',
        }

    try:
        tasks = create_batch_tasks(start_date, end_date, market_mode='INCREMENTAL_SYNC')
    except ValueError as exc:
        return {
            'started': False,
            'task_id': None,
            'start_date': start_date,
            'end_date': end_date,
            'status': 'ERROR',
            'message': str(exc),
        }

    started = True
    current = tasks['market_data_task']
    return {
        'started': started,
        'task_id': current.get('task_id'),
        'stock_list_task_id': tasks['stock_list_task'].get('task_id'),
        'jygs_review_task_id': tasks['jygs_review_task'].get('task_id'),
        'start_date': current.get('start_date', start_date),
        'end_date': current.get('end_date', end_date),
        'status': current.get('status', 'RUNNING' if started else 'PENDING'),
        'message': '增量行情任务已启动。' if started else '已有同类型初始化任务正在运行，增量任务未启动。',
        'task': current,
    }


@mcp.tool()
def scan_macd_alerts(trade_date: str, green_shrink_days: int = 2) -> dict:
    """Create a background MACD alert scan task for a trade date."""
    task = create_macd_alert_scan_task(trade_date=trade_date, green_shrink_days=green_shrink_days)
    started = start_task(task['task_id'])
    current = get_task(task['task_id']) or task
    return {
        'disclaimer': DISCLAIMER,
        'task': current,
        'started': started,
        'progress_hint': 'Use get_macd_alert_daily_brief or list_macd_alert_results after the task reaches SUCCESS.',
    }


@mcp.tool()
def track_macd_alerts(trade_date: str, source_trade_date: str) -> dict:
    """Track active MACD alerts from a previous trade date."""
    result = track_macd_alerts_service(trade_date=trade_date, source_trade_date=source_trade_date)
    return {'disclaimer': DISCLAIMER, **result}
