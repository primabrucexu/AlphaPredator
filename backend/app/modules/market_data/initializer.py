"""
Full-market initializer for Phase 2.9.

Coordinates:
  1. Fetching full A-share spot data from Eastmoney (via data_source.py)
  2. Fetching historical daily bars for every stock
  3. Writing the batch CSVs into the import directory
  4. Calling import_market_data_batch() to persist everything

Progress is tracked in a JSON status file so the front-end can poll it.
"""

from __future__ import annotations

import csv
import json
import logging
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.modules.market_data.data_source import (
    fetch_daily_bars_by_date,
    fetch_spot_snapshot,
    fetch_stock_pool,
    get_default_history_start,
)
from app.modules.market_data.importer import import_market_data_batch

logger = logging.getLogger(__name__)

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def _status_path(status_dir: Path | None) -> Path:
    target = status_dir or settings.init_status_dir
    target.mkdir(parents=True, exist_ok=True)
    return target / 'init_status.json'


def read_init_status(status_dir: Path | None = None) -> dict[str, Any]:
    path = _status_path(status_dir)
    if not path.exists():
        return _idle_status()
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return _idle_status()


def _write_status(status: dict[str, Any], status_dir: Path | None = None) -> None:
    path = _status_path(status_dir)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')


def _idle_status() -> dict[str, Any]:
    return {
        'status': 'idle',
        'trade_date': '',
        'total_stocks': 0,
        'processed_stocks': 0,
        'started_at': '',
        'finished_at': '',
        'error_message': '',
    }


# ---------------------------------------------------------------------------
# Core initializer
# ---------------------------------------------------------------------------


def start_initialization(
    *,
    history_days: int = 60,
    market_filters: list[str] | None = None,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
    daily_bars_parquet_path: Path | None = None,
    market_snapshot_path: Path | None = None,
    status_dir: Path | None = None,
    batch_dir_override: Path | None = None,
) -> bool:
    """
    Attempt to start a full market initialization in a background thread.

    Returns True if the task was started, False if one is already running.
    Raises ValueError if the Tushare token or stock list is not configured.

    Note: *history_days* is used as a fallback only when
    ``settings.tushare_history_start`` is not configured.  In the default setup
    the fixed start date ``settings.tushare_history_start`` (``2024-01-01``)
    takes precedence and *history_days* has no effect.
    """
    from app.modules.market_data.data_source import _get_token, load_stock_universe

    # Precondition: token must be configured
    if not _get_token():
        raise ValueError(
            'Tushare token not configured. '
            'Please set it via the initialization page before starting.'
        )

    # Precondition: stock universe CSV must be uploaded
    try:
        load_stock_universe()
    except FileNotFoundError as exc:
        raise ValueError(str(exc)) from exc

    with _lock:
        current = read_init_status(status_dir)
        if current.get('status') == 'running':
            return False

        _write_status(
            {
                'status': 'running',
                'trade_date': '',
                'total_stocks': 0,
                'processed_stocks': 0,
                'started_at': _now_iso(),
                'finished_at': '',
                'error_message': '',
            },
            status_dir,
        )

    thread = threading.Thread(
        target=_run_initialization,
        kwargs={
            'history_days': history_days,
            'market_filters': market_filters,
            'sqlite_path': sqlite_path,
            'duckdb_path': duckdb_path,
            'daily_bars_parquet_path': daily_bars_parquet_path,
            'market_snapshot_path': market_snapshot_path,
            'status_dir': status_dir,
            'batch_dir_override': batch_dir_override,
        },
        daemon=True,
    )
    thread.start()
    return True


def _run_initialization(
    *,
    history_days: int,
    market_filters: list[str] | None,
    sqlite_path: Path | None,
    duckdb_path: Path | None,
    daily_bars_parquet_path: Path | None,
    market_snapshot_path: Path | None,
    status_dir: Path | None,
    batch_dir_override: Path | None,
) -> None:
    try:
        trade_date = date.today().strftime('%Y-%m-%d')
        # Use the configured history start date, falling back to the history_days approximation
        start_date = settings.tushare_history_start or get_default_history_start(history_days)
        end_date = trade_date

        # ---- Step 1: fetch spot snapshot ----
        logger.info('Initialization: fetching spot snapshot …')
        snapshot_rows = fetch_spot_snapshot(trade_date, market_filters=market_filters)
        stock_pool = fetch_stock_pool(snapshot_rows, market_filters=market_filters)

        # ---- Step 2: enumerate trade dates and fetch bars per date ----
        trade_dates = _get_date_range(start_date, end_date)
        total = len(trade_dates)
        logger.info(
            'Initialization: fetching historical bars for %d calendar days (%s – %s) …',
            total,
            start_date,
            end_date,
        )
        _write_status(
            {
                'status': 'running',
                'trade_date': trade_date,
                'total_stocks': total,
                'processed_stocks': 0,
                'started_at': read_init_status(status_dir).get('started_at', _now_iso()),
                'finished_at': '',
                'error_message': '',
            },
            status_dir,
        )

        all_bars: list[dict[str, Any]] = []
        for idx, td in enumerate(trade_dates):
            bars = fetch_daily_bars_by_date(td, market_filters=market_filters)
            all_bars.extend(bars)
            if (idx + 1) % 10 == 0 or idx + 1 == total:
                _write_status(
                    {
                        'status': 'running',
                        'trade_date': trade_date,
                        'total_stocks': total,
                        'processed_stocks': idx + 1,
                        'started_at': read_init_status(status_dir).get('started_at', _now_iso()),
                        'finished_at': '',
                        'error_message': '',
                    },
                    status_dir,
                )

        # If today's snapshot is empty (e.g., non-trading day), derive snapshots from latest bars.
        if not snapshot_rows:
            snapshot_rows = _derive_snapshots_from_bars(all_bars, stock_pool)

        if not snapshot_rows:
            raise ValueError(
                'No snapshot rows available after fetching data. '
                'Please confirm selected market filters and date range contain trading data.'
            )

        # ---- Step 3: write batch CSVs ----
        batch_dir = batch_dir_override or (settings.market_data_import_dir / f'tushare-{trade_date}')
        _write_batch(
            batch_dir=batch_dir,
            stock_pool=stock_pool,
            daily_snapshots=snapshot_rows,
            daily_bars=all_bars,
        )

        # ---- Step 4: import ----
        logger.info('Initialization: importing batch from %s …', batch_dir)
        import_market_data_batch(
            batch_dir,
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
            daily_bars_parquet_path=daily_bars_parquet_path,
            market_snapshot_path=market_snapshot_path,
        )

        _write_status(
            {
                'status': 'done',
                'trade_date': trade_date,
                'total_stocks': total,
                'processed_stocks': total,
                'started_at': read_init_status(status_dir).get('started_at', _now_iso()),
                'finished_at': _now_iso(),
                'error_message': '',
            },
            status_dir,
        )
        logger.info('Initialization complete: %d date(s) processed, trade_date=%s', total, trade_date)

    except Exception as exc:  # noqa: BLE001
        logger.exception('Initialization failed: %s', exc)
        prev = read_init_status(status_dir)
        _write_status(
            {
                'status': 'error',
                'trade_date': prev.get('trade_date', ''),
                'total_stocks': prev.get('total_stocks', 0),
                'processed_stocks': prev.get('processed_stocks', 0),
                'started_at': prev.get('started_at', ''),
                'finished_at': _now_iso(),
                'error_message': str(exc),
            },
            status_dir,
        )


# ---------------------------------------------------------------------------
# Batch writer helpers
# ---------------------------------------------------------------------------


def _write_batch(
    *,
    batch_dir: Path,
    stock_pool: list[dict[str, Any]],
    daily_snapshots: list[dict[str, Any]],
    daily_bars: list[dict[str, Any]],
) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        batch_dir / 'stock_pool.csv',
        ['stock_code', 'stock_name', 'sectors', 'ai_quick_summary'],
        [{
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'],
            'sectors': r.get('sectors', ''),
            'ai_quick_summary': r.get('ai_quick_summary', ''),
        } for r in stock_pool],
    )

    _write_csv(
        batch_dir / 'daily_stock_snapshots.csv',
        ['trade_date', 'stock_code', 'current_price', 'change_amount', 'change_pct',
         'turnover_amount_billion', 'turnover_rate'],
        [{
            'trade_date': r['trade_date'],
            'stock_code': r['stock_code'],
            'current_price': r['current_price'],
            'change_amount': r['change_amount'],
            'change_pct': r['change_pct'],
            'turnover_amount_billion': r['turnover_amount_billion'],
            'turnover_rate': r['turnover_rate'],
        } for r in daily_snapshots],
    )

    _write_csv(
        batch_dir / 'daily_bars.csv',
        ['stock_code', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume',
         'turnover_amount_billion'],
        [{
            'stock_code': r['stock_code'],
            'trade_date': r['trade_date'],
            'open_price': r['open_price'],
            'high_price': r['high_price'],
            'low_price': r['low_price'],
            'close_price': r['close_price'],
            'volume': r['volume'],
            'turnover_amount_billion': r.get('turnover_amount_billion', 0.0),
        } for r in daily_bars],
    )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _get_date_range(start_date: str, end_date: str) -> list[str]:
    """Return all calendar dates from start_date to end_date inclusive (ISO format)."""
    from datetime import datetime, timedelta

    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    result: list[str] = []
    current = start
    while current <= end:
        result.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return result


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _derive_snapshots_from_bars(
    daily_bars: list[dict[str, Any]],
    stock_pool: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build one snapshot row per stock from the latest available daily bar."""
    if not daily_bars:
        return []

    name_by_code = {row['stock_code']: row.get('stock_name', '') for row in stock_pool}
    bars_by_code: dict[str, list[dict[str, Any]]] = {}
    for row in daily_bars:
        bars_by_code.setdefault(row['stock_code'], []).append(row)

    snapshots: list[dict[str, Any]] = []
    for code, bars in bars_by_code.items():
        ordered = sorted(bars, key=lambda x: x['trade_date'])
        latest = ordered[-1]
        prev_close = float(ordered[-2]['close_price']) if len(ordered) > 1 else float(latest['close_price'])
        current_price = float(latest['close_price'])
        change_amount = current_price - prev_close
        change_pct = 0.0 if prev_close == 0 else (change_amount / prev_close) * 100

        snapshots.append(
            {
                'trade_date': latest['trade_date'],
                'stock_code': code,
                'stock_name': name_by_code.get(code, ''),
                'current_price': round(current_price, 4),
                'change_amount': round(change_amount, 4),
                'change_pct': round(change_pct, 4),
                # Not provided by per-stock daily endpoint in current pipeline.
                'turnover_amount_billion': 0.0,
                'turnover_rate': 0.0,
            }
        )

    return snapshots

