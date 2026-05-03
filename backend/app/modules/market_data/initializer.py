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
    fetch_daily_bars_for_stock,
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
    """
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
    sqlite_path: Path | None,
    duckdb_path: Path | None,
    daily_bars_parquet_path: Path | None,
    market_snapshot_path: Path | None,
    status_dir: Path | None,
    batch_dir_override: Path | None,
) -> None:
    try:
        trade_date = date.today().strftime('%Y-%m-%d')
        start_date = get_default_history_start(history_days)
        end_date = trade_date

        # ---- Step 1: fetch spot snapshot ----
        logger.info('Initialization: fetching spot snapshot …')
        snapshot_rows = fetch_spot_snapshot(trade_date)
        stock_pool = fetch_stock_pool(snapshot_rows)

        total = len(stock_pool)
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

        # ---- Step 2: fetch historical bars per stock ----
        logger.info('Initialization: fetching historical bars for %d stocks …', total)
        all_bars: list[dict[str, Any]] = []
        for idx, stock in enumerate(stock_pool):
            code = stock['stock_code']
            bars = fetch_daily_bars_for_stock(code, start_date=start_date, end_date=end_date)
            all_bars.extend(bars)
            if (idx + 1) % 50 == 0 or idx + 1 == total:
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
            time.sleep(0.05)  # gentle rate-limiting

        # ---- Step 3: write batch CSVs ----
        batch_dir = batch_dir_override or (settings.market_data_import_dir / f'eastmoney-{trade_date}')
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
        logger.info('Initialization complete: %d stocks, trade_date=%s', total, trade_date)

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
        ['stock_code', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume'],
        [{
            'stock_code': r['stock_code'],
            'trade_date': r['trade_date'],
            'open_price': r['open_price'],
            'high_price': r['high_price'],
            'low_price': r['low_price'],
            'close_price': r['close_price'],
            'volume': r['volume'],
        } for r in daily_bars],
    )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
