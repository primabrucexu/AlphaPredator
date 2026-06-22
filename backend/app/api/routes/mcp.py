from __future__ import annotations

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
from app.modules.market_data.initializer import get_task, start_task


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
