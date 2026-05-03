"""
Eastmoney data source adapter.

Fetches A-share market data via akshare and converts it into
the internal batch format used by import_market_data_batch().
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

import akshare as ak
import pandas as pd


# ---------------------------------------------------------------------------
# Public helpers – return plain Python dicts matching the batch CSV format
# ---------------------------------------------------------------------------


def fetch_spot_snapshot(trade_date: str | None = None) -> list[dict[str, Any]]:
    """
    Fetch today's (or a given date's) A-share spot data from Eastmoney.

    Returns a list of dicts with keys:
        stock_code, stock_name, current_price, change_amount, change_pct,
        turnover_amount_billion, turnover_rate, trade_date
    """
    df: pd.DataFrame = ak.stock_zh_a_spot_em()

    # Standardise column names – akshare returns Chinese column names
    col_map = {
        '代码': 'stock_code',
        '名称': 'stock_name',
        '最新价': 'current_price',
        '涨跌额': 'change_amount',
        '涨跌幅': 'change_pct',
        '换手率': 'turnover_rate',
        '成交额': 'turnover_amount_raw',  # in yuan; convert to billion below
    }
    df = df.rename(columns=col_map)
    required = set(col_map.values())
    if not required.issubset(df.columns):
        missing = required - set(df.columns)
        raise ValueError(f'fetch_spot_snapshot: unexpected akshare columns, missing {missing}')

    effective_date = trade_date or date.today().strftime('%Y-%m-%d')

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            current_price = float(row['current_price'] or 0)
            change_amount = float(row['change_amount'] or 0)
            change_pct = float(row['change_pct'] or 0)
            turnover_rate = float(row['turnover_rate'] or 0)
            turnover_amount_raw = float(row['turnover_amount_raw'] or 0)
        except (ValueError, TypeError):
            continue

        # Skip stocks with zero or invalid price (suspended, delisted, etc.)
        if current_price <= 0:
            continue

        rows.append({
            'stock_code': str(row['stock_code']).zfill(6),
            'stock_name': str(row['stock_name']).strip(),
            'current_price': round(current_price, 4),
            'change_amount': round(change_amount, 4),
            'change_pct': round(change_pct, 4),
            'turnover_amount_billion': round(turnover_amount_raw / 1e8, 4),
            'turnover_rate': round(turnover_rate, 4),
            'trade_date': effective_date,
        })
    return rows


def fetch_stock_pool(snapshot_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """
    Build a stock pool from the spot snapshot or a pre-fetched snapshot list.

    Returns a list of dicts with keys:
        stock_code, stock_name, sectors, ai_quick_summary
    """
    if snapshot_rows is None:
        snapshot_rows = fetch_spot_snapshot()

    return [
        {
            'stock_code': row['stock_code'],
            'stock_name': row['stock_name'],
            'sectors': '',       # sector data not available from spot; leave blank
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
    Fetch daily K-line bars for a single stock.

    Returns a list of dicts with keys:
        stock_code, trade_date, open_price, high_price, low_price,
        close_price, volume
    """
    col_map = {
        '日期': 'trade_date',
        '开盘': 'open_price',
        '最高': 'high_price',
        '最低': 'low_price',
        '收盘': 'close_price',
        '成交量': 'volume',
    }

    for attempt in range(retry + 1):
        try:
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period='daily',
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust=adjust,
            )
            break
        except Exception:  # noqa: BLE001
            if attempt < retry:
                time.sleep(delay)
                continue
            return []

    if df is None or df.empty:
        return []

    df = df.rename(columns=col_map)
    required = {'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume'}
    if not required.issubset(df.columns):
        return []

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            rows.append({
                'stock_code': stock_code,
                'trade_date': str(row['trade_date'])[:10],
                'open_price': round(float(row['open_price']), 4),
                'high_price': round(float(row['high_price']), 4),
                'low_price': round(float(row['low_price']), 4),
                'close_price': round(float(row['close_price']), 4),
                'volume': int(row['volume']),
            })
        except (ValueError, TypeError):
            continue
    return rows


def get_default_history_start(history_days: int = 60) -> str:
    """Return an ISO date string `history_days` trading days before today."""
    # Use calendar days as a simple approximation (trading days ≈ 70% of calendar)
    start = date.today() - timedelta(days=int(history_days * 1.5))
    return start.strftime('%Y-%m-%d')
