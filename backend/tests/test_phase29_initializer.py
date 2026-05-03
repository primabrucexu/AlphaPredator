"""Tests for the Phase 2.9 initializer and updater (using mocked data source)."""

import json
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.modules.market_data.initializer import (
    _idle_status,
    _write_batch,
    read_init_status,
    start_initialization,
)
from app.modules.market_data.updater import run_daily_update


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MOCK_SNAPSHOT_ROWS = [
    {
        'stock_code': '000001',
        'stock_name': '平安银行',
        'current_price': 11.28,
        'change_amount': 0.14,
        'change_pct': 1.24,
        'turnover_amount_billion': 31.70,
        'turnover_rate': 0.91,
        'trade_date': '2026-05-03',
    },
    {
        'stock_code': '300308',
        'stock_name': '中际旭创',
        'current_price': 167.53,
        'change_amount': 5.93,
        'change_pct': 3.66,
        'turnover_amount_billion': 82.40,
        'turnover_rate': 5.24,
        'trade_date': '2026-05-03',
    },
]

MOCK_BARS = [
    {
        'stock_code': '000001',
        'trade_date': '2026-05-03',
        'open_price': 11.13,
        'high_price': 11.31,
        'low_price': 11.08,
        'close_price': 11.28,
        'volume': 56340000,
    },
    {
        'stock_code': '300308',
        'trade_date': '2026-05-03',
        'open_price': 165.90,
        'high_price': 168.40,
        'low_price': 164.70,
        'close_price': 167.53,
        'volume': 22860000,
    },
]


def _mock_fetch_spot_snapshot(trade_date=None):  # noqa: ARG001
    return MOCK_SNAPSHOT_ROWS


def _mock_fetch_stock_pool(snapshot_rows=None):
    rows = snapshot_rows or MOCK_SNAPSHOT_ROWS
    return [
        {'stock_code': r['stock_code'], 'stock_name': r['stock_name'], 'sectors': '', 'ai_quick_summary': ''}
        for r in rows
    ]


def _mock_fetch_daily_bars(code, *, start_date, end_date, **_kwargs):  # noqa: ARG001
    return [b for b in MOCK_BARS if b['stock_code'] == code]


# ---------------------------------------------------------------------------
# Initializer tests
# ---------------------------------------------------------------------------


def test_read_init_status_returns_idle_when_no_file(tmp_path: Path) -> None:
    status = read_init_status(tmp_path)
    assert status['status'] == 'idle'
    assert status['total_stocks'] == 0


def test_write_batch_creates_expected_files(tmp_path: Path) -> None:
    stock_pool = [
        {'stock_code': '000001', 'stock_name': '平安银行', 'sectors': '', 'ai_quick_summary': ''},
    ]
    daily_snapshots = [
        {
            'stock_code': '000001',
            'stock_name': '平安银行',
            'current_price': 11.28,
            'change_amount': 0.14,
            'change_pct': 1.24,
            'turnover_amount_billion': 31.70,
            'turnover_rate': 0.91,
            'trade_date': '2026-05-03',
        }
    ]
    daily_bars = [
        {
            'stock_code': '000001',
            'trade_date': '2026-05-03',
            'open_price': 11.13,
            'high_price': 11.31,
            'low_price': 11.08,
            'close_price': 11.28,
            'volume': 56340000,
        }
    ]
    batch_dir = tmp_path / 'batch'
    _write_batch(
        batch_dir=batch_dir,
        stock_pool=stock_pool,
        daily_snapshots=daily_snapshots,
        daily_bars=daily_bars,
    )

    assert (batch_dir / 'stock_pool.csv').exists()
    assert (batch_dir / 'daily_stock_snapshots.csv').exists()
    assert (batch_dir / 'daily_bars.csv').exists()

    content = (batch_dir / 'stock_pool.csv').read_text(encoding='utf-8')
    assert '000001' in content
    assert '平安银行' in content


def test_start_initialization_runs_and_sets_done(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'sqlite' / 'alphapredator.db'
    duckdb_path = tmp_path / 'duckdb' / 'alphapredator.duckdb'
    daily_bars_parquet_path = tmp_path / 'parquet' / 'stock_daily_bars.parquet'
    market_snapshot_path = tmp_path / 'parquet' / 'market_snapshot.json'
    status_dir = tmp_path / 'status'
    batch_dir = tmp_path / 'batch'

    with (
        patch('app.modules.market_data.initializer.fetch_spot_snapshot', side_effect=_mock_fetch_spot_snapshot),
        patch('app.modules.market_data.initializer.fetch_stock_pool', side_effect=_mock_fetch_stock_pool),
        patch('app.modules.market_data.initializer.fetch_daily_bars_for_stock', side_effect=_mock_fetch_daily_bars),
    ):
        started = start_initialization(
            history_days=1,
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
            daily_bars_parquet_path=daily_bars_parquet_path,
            market_snapshot_path=market_snapshot_path,
            status_dir=status_dir,
            batch_dir_override=batch_dir,
        )

    assert started is True

    # Wait for background thread to finish (max 10 s)
    for _ in range(50):
        time.sleep(0.2)
        status = read_init_status(status_dir)
        if status['status'] in ('done', 'error'):
            break

    status = read_init_status(status_dir)
    assert status['status'] == 'done', f"Expected done, got: {status}"
    assert status['total_stocks'] == 2
    assert status['processed_stocks'] == 2
    assert sqlite_path.exists()
    assert market_snapshot_path.exists()


def test_start_initialization_returns_false_when_already_running(tmp_path: Path) -> None:
    status_dir = tmp_path / 'status'
    status_dir.mkdir(parents=True)
    (status_dir / 'init_status.json').write_text(
        json.dumps({'status': 'running', 'total_stocks': 100, 'processed_stocks': 10,
                    'trade_date': '', 'started_at': '', 'finished_at': '', 'error_message': ''}),
        encoding='utf-8',
    )

    started = start_initialization(status_dir=status_dir)
    assert started is False


# ---------------------------------------------------------------------------
# Updater tests
# ---------------------------------------------------------------------------


def test_run_daily_update_succeeds(tmp_path: Path) -> None:
    from app.db.sqlite import ensure_sqlite_schema
    from app.db.duckdb import ensure_duckdb_parent, ensure_duckdb_schema

    sqlite_path = tmp_path / 'sqlite' / 'alphapredator.db'
    duckdb_path = tmp_path / 'duckdb' / 'alphapredator.duckdb'
    daily_bars_parquet_path = tmp_path / 'parquet' / 'stock_daily_bars.parquet'
    market_snapshot_path = tmp_path / 'parquet' / 'market_snapshot.json'

    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_parent(duckdb_path, daily_bars_parquet_path.parent)
    ensure_duckdb_schema(duckdb_path)

    with (
        patch('app.modules.market_data.updater.fetch_spot_snapshot', side_effect=_mock_fetch_spot_snapshot),
        patch('app.modules.market_data.updater.fetch_stock_pool', side_effect=_mock_fetch_stock_pool),
        patch('app.modules.market_data.updater.fetch_daily_bars_for_stock', side_effect=_mock_fetch_daily_bars),
    ):
        result = run_daily_update(
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
            daily_bars_parquet_path=daily_bars_parquet_path,
            market_snapshot_path=market_snapshot_path,
        )

    assert result['stock_count'] == 2
    assert result['bar_count'] == 2
    assert market_snapshot_path.exists()

    payload = json.loads(market_snapshot_path.read_text(encoding='utf-8'))
    assert len(payload['stocks']) == 2
    assert payload['summary']['rising_count'] == 2
