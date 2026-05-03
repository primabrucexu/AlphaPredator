"""
Tushare data source adapter.

Fetches A-share market data via Tushare Pro and converts it into
the internal batch format used by import_market_data_batch().

Rate limiting: honours the settings.tushare_rate_limit cap (default 450 req/min).
Stock universe: loaded from the CSV uploaded via the /api/data-init/upload-stock-list
endpoint (settings.stock_list_path).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from datetime import date, timedelta
from typing import Any

import pandas as pd

from app.core.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter (sliding-window, thread-safe)
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_call_timestamps: deque[float] = deque()  # monotonic timestamps of recent calls


def _rate_limited_call(func: Any, **kwargs: Any) -> Any:
    """Call *func* while enforcing the configured requests-per-minute limit."""
    rate_limit = settings.tushare_rate_limit
    window = 60.0  # seconds

    with _rate_lock:
        now = time.monotonic()
        # Drop timestamps older than the window
        while _call_timestamps and now - _call_timestamps[0] >= window:
            _call_timestamps.popleft()

        if len(_call_timestamps) >= rate_limit:
            # Wait until the oldest call falls outside the window
            wait = window - (now - _call_timestamps[0])
            if wait > 0:
                time.sleep(wait)
            # Refresh after sleeping
            now = time.monotonic()
            while _call_timestamps and now - _call_timestamps[0] >= window:
                _call_timestamps.popleft()

        _call_timestamps.append(time.monotonic())

    return func(**kwargs)


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _get_token() -> str:
    """Return the Tushare token from env var or the persisted token file."""
    token = os.environ.get('TUSHARE_TOKEN', '').strip()
    if not token:
        path = settings.tushare_token_path
        if path.exists():
            token = path.read_text(encoding='utf-8').strip()
    return token


def _get_tushare_api() -> Any:
    """Return an initialised Tushare Pro API instance."""
    import tushare as ts

    token = _get_token()
    if not token:
        raise ValueError(
            'Tushare token not configured. '
            'Please set it via the initialization page or the TUSHARE_TOKEN environment variable.'
        )
    ts.set_token(token)
    return ts.pro_api()


# ---------------------------------------------------------------------------
# Stock universe helpers
# ---------------------------------------------------------------------------

# Required columns in the user-uploaded stock list CSV
_REQUIRED_STOCK_LIST_COLS = {'ts_code', 'symbol', 'name', 'market', 'list_status'}

# Supported market board values
MARKET_BOARDS = ('主板', '创业板', '科创板')


def _to_ts_code(symbol: str) -> str:
    """Convert a 6-digit stock symbol to Tushare ts_code (e.g. '000001' → '000001.SZ')."""
    s = str(symbol).zfill(6)
    if s.startswith('6'):
        return s + '.SH'
    if s.startswith('8') or s.startswith('4'):
        return s + '.BJ'
    return s + '.SZ'


def load_stock_universe(market_filters: list[str] | None = None) -> pd.DataFrame:
    """
    Load the uploaded stock universe CSV and optionally filter by market board.

    Raises FileNotFoundError if the stock list has not been uploaded yet.
    """
    path = settings.stock_list_path
    if not path.exists():
        raise FileNotFoundError(
            'Stock universe CSV not found. '
            'Please upload it via the initialization page (上传股票清单 CSV).'
        )

    df = pd.read_csv(path, dtype=str)
    missing = _REQUIRED_STOCK_LIST_COLS - set(df.columns)
    if missing:
        raise ValueError(f'Stock list CSV is missing required columns: {missing}')

    # Only include actively listed stocks
    df = df[df['list_status'].fillna('') == 'L'].copy()

    if market_filters:
        df = df[df['market'].isin(market_filters)].copy()

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Public helpers – return plain Python dicts matching the batch CSV format
# ---------------------------------------------------------------------------


def fetch_spot_snapshot(
    trade_date: str | None = None,
    *,
    market_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch A-share snapshot data from Tushare for a given trade date.

    Loads the stock universe from the uploaded CSV, optionally filtered by
    *market_filters*, then fetches that day's daily data from Tushare.

    Returns a list of dicts with keys:
        stock_code, stock_name, current_price, change_amount, change_pct,
        turnover_amount_billion, turnover_rate, trade_date
    """
    pro = _get_tushare_api()

    universe_df = load_stock_universe(market_filters)
    ts_code_set = set(universe_df['ts_code'].tolist())
    name_map = dict(zip(universe_df['ts_code'], universe_df['name']))
    symbol_map = dict(zip(universe_df['ts_code'], universe_df['symbol']))

    effective_date = trade_date or date.today().strftime('%Y-%m-%d')
    ts_date = effective_date.replace('-', '')

    # Bulk fetch – one API call for the whole market on this date
    daily_df = _rate_limited_call(pro.daily, trade_date=ts_date)
    if daily_df is None or daily_df.empty:
        return []

    # Attempt to enrich with turnover_rate (one extra bulk call)
    try:
        basic_df = _rate_limited_call(
            pro.daily_basic,
            trade_date=ts_date,
            fields='ts_code,turnover_rate',
        )
        if basic_df is not None and not basic_df.empty:
            daily_df = daily_df.merge(basic_df[['ts_code', 'turnover_rate']], on='ts_code', how='left')
        else:
            daily_df['turnover_rate'] = 0.0
    except Exception as exc:  # noqa: BLE001
        logger.warning('fetch_spot_snapshot: failed to fetch turnover_rate from daily_basic: %s', exc)
        daily_df['turnover_rate'] = 0.0

    # Filter to the stock universe
    daily_df = daily_df[daily_df['ts_code'].isin(ts_code_set)].copy()

    rows: list[dict[str, Any]] = []
    for _, row in daily_df.iterrows():
        ts_code = str(row['ts_code'])
        try:
            close = float(row.get('close') or 0)
            if close <= 0:
                continue
            rows.append({
                'stock_code': str(symbol_map.get(ts_code, ts_code.split('.')[0])).zfill(6),
                'stock_name': str(name_map.get(ts_code, '')).strip(),
                'current_price': round(close, 4),
                'change_amount': round(float(row.get('change') or 0), 4),
                'change_pct': round(float(row.get('pct_chg') or 0), 4),
                # Tushare amount is in 千元 (thousand yuan); convert to 亿元 (100M yuan)
                'turnover_amount_billion': round(float(row.get('amount') or 0) / 1e6, 4),
                'turnover_rate': round(float(row.get('turnover_rate') or 0), 4),
                'trade_date': effective_date,
            })
        except (ValueError, TypeError):
            continue

    return rows


def fetch_stock_pool(
    snapshot_rows: list[dict[str, Any]] | None = None,
    *,
    market_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Build a stock pool from a pre-fetched snapshot list (or fetch a new one).

    Returns a list of dicts with keys:
        stock_code, stock_name, sectors, ai_quick_summary
    """
    if snapshot_rows is None:
        snapshot_rows = fetch_spot_snapshot(market_filters=market_filters)

    return [
        {
            'stock_code': row['stock_code'],
            'stock_name': row['stock_name'],
            'sectors': '',
            'ai_quick_summary': '',
        }
        for row in snapshot_rows
    ]


def fetch_daily_bars_for_stock(
    stock_code: str,
    *,
    start_date: str,
    end_date: str,
    adjust: str = 'qfq',
    retry: int = 2,
    delay: float = 0.2,
) -> list[dict[str, Any]]:
    """
    Fetch daily K-line bars for a single stock via Tushare.

    Returns a list of dicts with keys:
        stock_code, trade_date, open_price, high_price, low_price,
        close_price, volume
    """
    pro = _get_tushare_api()
    ts_code = _to_ts_code(stock_code)
    ts_start = start_date.replace('-', '')
    ts_end = end_date.replace('-', '')

    # Tushare adj parameter: 'qfq' for forward-adjusted, 'hfq' for backward, None for raw
    adj: str | None = adjust if adjust in ('qfq', 'hfq') else None

    for attempt in range(retry + 1):
        try:
            df = _rate_limited_call(
                pro.daily,
                ts_code=ts_code,
                start_date=ts_start,
                end_date=ts_end,
                adj=adj,
            )
            break
        except Exception:  # noqa: BLE001
            if attempt < retry:
                time.sleep(delay)
                continue
            return []

    if df is None or df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            # Tushare trade_date is 'YYYYMMDD'; convert to 'YYYY-MM-DD'
            td = str(row['trade_date'])
            trade_date_str = f'{td[:4]}-{td[4:6]}-{td[6:8]}'
            rows.append({
                'stock_code': stock_code,
                'trade_date': trade_date_str,
                'open_price': round(float(row['open']), 4),
                'high_price': round(float(row['high']), 4),
                'low_price': round(float(row['low']), 4),
                'close_price': round(float(row['close']), 4),
                # Tushare vol is in 手 (100-share lots); keep as-is to match AkShare convention
                'volume': int(float(row['vol'])),
            })
        except (ValueError, TypeError):
            continue

    return rows


def get_default_history_start(history_days: int = 60) -> str:
    """Return an ISO date string `history_days` calendar days before today."""
    start = date.today() - timedelta(days=int(history_days * 1.5))
    return start.strftime('%Y-%m-%d')
