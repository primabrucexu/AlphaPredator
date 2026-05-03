"""Tests for the Phase 2.9 initializer and updater (using mocked data source)."""

import io
import json
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

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

# Minimal stock list CSV for testing
MOCK_STOCK_LIST_CSV = (
    'ts_code,symbol,name,industry,cnspell,market,list_date,list_status,delist_date\n'
    '000001.SZ,000001,平安银行,银行,payh,主板,19910403,L,\n'
    '300308.SZ,300308,中际旭创,通信,zjxc,创业板,20130124,L,\n'
)


def _mock_fetch_spot_snapshot(trade_date=None, *, market_filters=None):  # noqa: ARG001
    return MOCK_SNAPSHOT_ROWS


def _mock_fetch_stock_pool(snapshot_rows=None, *, market_filters=None):
    rows = snapshot_rows or MOCK_SNAPSHOT_ROWS
    return [
        {'stock_code': r['stock_code'], 'stock_name': r['stock_name'], 'sectors': '', 'ai_quick_summary': ''}
        for r in rows
    ]


def _mock_fetch_daily_bars(code, *, start_date, end_date, **_kwargs):  # noqa: ARG001
    return [b for b in MOCK_BARS if b['stock_code'] == code]


def _write_mock_stock_list(tmp_path: Path) -> Path:
    """Write a minimal stock list CSV and configure settings to use it."""
    stock_list_path = tmp_path / 'config' / 'stock_list.csv'
    stock_list_path.parent.mkdir(parents=True, exist_ok=True)
    stock_list_path.write_text(MOCK_STOCK_LIST_CSV, encoding='utf-8')
    return stock_list_path


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

    # Use patcher.start()/stop() so mocks stay active while the background thread runs
    patchers = [
        patch('app.modules.market_data.data_source._get_token', return_value='mock_token'),
        patch('app.modules.market_data.data_source.load_stock_universe'),
        patch('app.modules.market_data.initializer.fetch_spot_snapshot', side_effect=_mock_fetch_spot_snapshot),
        patch('app.modules.market_data.initializer.fetch_stock_pool', side_effect=_mock_fetch_stock_pool),
        patch('app.modules.market_data.initializer.fetch_daily_bars_for_stock', side_effect=_mock_fetch_daily_bars),
    ]
    for p in patchers:
        p.start()

    try:
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
    finally:
        for p in patchers:
            p.stop()

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

    with (
        patch('app.modules.market_data.data_source._get_token', return_value='mock_token'),
        patch('app.modules.market_data.data_source.load_stock_universe'),
    ):
        started = start_initialization(status_dir=status_dir)
    assert started is False


def test_start_initialization_raises_when_token_missing(tmp_path: Path) -> None:
    import os

    env_backup = os.environ.pop('TUSHARE_TOKEN', None)
    try:
        with patch('app.modules.market_data.data_source._get_token', return_value=''):
            with pytest.raises(ValueError, match='token'):
                start_initialization()
    finally:
        if env_backup is not None:
            os.environ['TUSHARE_TOKEN'] = env_backup


def test_start_initialization_raises_when_stock_list_missing(tmp_path: Path) -> None:
    with (
        patch('app.modules.market_data.data_source._get_token', return_value='mock_token'),
        patch(
            'app.modules.market_data.data_source.load_stock_universe',
            side_effect=FileNotFoundError('Stock universe CSV not found.'),
        ),
    ):
        with pytest.raises(ValueError, match='Stock universe'):
            start_initialization()


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


# ---------------------------------------------------------------------------
# Data source unit tests (no network)
# ---------------------------------------------------------------------------


def test_load_stock_universe_filters_by_market(tmp_path: Path) -> None:
    from app.modules.market_data.data_source import load_stock_universe

    stock_list_path = tmp_path / 'config' / 'stock_list.csv'
    stock_list_path.parent.mkdir(parents=True, exist_ok=True)
    stock_list_path.write_text(MOCK_STOCK_LIST_CSV, encoding='utf-8')

    from unittest.mock import MagicMock
    mock_settings = MagicMock()
    mock_settings.stock_list_path = stock_list_path

    with patch('app.modules.market_data.data_source.settings', mock_settings):
        df_all = load_stock_universe()
        assert len(df_all) == 2

        df_main = load_stock_universe(market_filters=['主板'])
        assert len(df_main) == 1
        assert df_main.iloc[0]['symbol'] == '000001'

        df_cyb = load_stock_universe(market_filters=['创业板'])
        assert len(df_cyb) == 1
        assert df_cyb.iloc[0]['symbol'] == '300308'


def test_load_stock_universe_raises_when_file_missing(tmp_path: Path) -> None:
    from app.modules.market_data.data_source import load_stock_universe
    from unittest.mock import MagicMock

    mock_settings = MagicMock()
    mock_settings.stock_list_path = tmp_path / 'no_such_file.csv'

    with patch('app.modules.market_data.data_source.settings', mock_settings):
        with pytest.raises(FileNotFoundError):
            load_stock_universe()


def test_to_ts_code_conversion() -> None:
    from app.modules.market_data.data_source import _to_ts_code

    assert _to_ts_code('000001') == '000001.SZ'
    assert _to_ts_code('600036') == '600036.SH'
    assert _to_ts_code('300308') == '300308.SZ'
    assert _to_ts_code('688009') == '688009.SH'  # 科创板 (starts with 6)
    assert _to_ts_code('830799') == '830799.BJ'  # 北交所
