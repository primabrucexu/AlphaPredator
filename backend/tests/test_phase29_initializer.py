"""
Tests migrated from the old Phase 2.9 initializer.

The V2 initializer replaces the old CSV-based approach.  This file retains
the following tests that remain relevant after the V2 refactor:
- Updater (run_daily_update): unmodified, still uses the same API.
- Data source helpers (load_stock_universe, _to_ts_code): unchanged utilities.

Tests removed (exercised old CSV-based V1 initializer only):
- test_read_init_status_returns_idle_when_no_file
- test_write_batch_creates_expected_files
- test_start_initialization_runs_and_sets_done
- test_start_initialization_returns_false_when_already_running
- test_start_initialization_raises_when_token_missing
- test_start_initialization_raises_when_stock_list_missing

New V2-specific tests live in test_v2_initializer.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


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
        'turnover_amount_billion': 31.70,
    },
    {
        'stock_code': '300308',
        'trade_date': '2026-05-03',
        'open_price': 165.90,
        'high_price': 168.40,
        'low_price': 164.70,
        'close_price': 167.53,
        'volume': 22860000,
        'turnover_amount_billion': 82.40,
    },
]

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


def _mock_fetch_daily_bars_by_date(trade_date, *, use_uploaded_universe=True, market_filters=None):  # noqa: ARG001
    return list(MOCK_BARS)


# ---------------------------------------------------------------------------
# Updater tests
# ---------------------------------------------------------------------------


def test_run_daily_update_succeeds(tmp_path: Path) -> None:
    from app.db.sqlite import ensure_sqlite_schema
    from app.db.duckdb_storage import ensure_duckdb_parent, ensure_duckdb_schema
    from app.modules.market_data.updater import run_daily_update

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
        patch('app.modules.market_data.updater.fetch_daily_bars_by_date', side_effect=_mock_fetch_daily_bars_by_date),
    ):
        result = run_daily_update(
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
            daily_bars_parquet_path=daily_bars_parquet_path,
            market_snapshot_path=market_snapshot_path,
        )

    assert result['stock_count'] == 2
    assert result['bar_count'] == 2
    assert result['processed_trade_dates'] == [result['trade_date']]
    assert market_snapshot_path.exists()

    payload = json.loads(market_snapshot_path.read_text(encoding='utf-8'))
    assert len(payload['stocks']) == 2
    assert payload['summary']['rising_count'] == 2


# ---------------------------------------------------------------------------
# Data source unit tests
# ---------------------------------------------------------------------------


def test_load_stock_universe_filters_by_market(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from app.modules.market_data.data_source import load_stock_universe

    stock_list_path = tmp_path / 'config' / 'stock_list.csv'
    stock_list_path.parent.mkdir(parents=True, exist_ok=True)
    stock_list_path.write_text(MOCK_STOCK_LIST_CSV, encoding='utf-8')

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
    from unittest.mock import MagicMock

    from app.modules.market_data.data_source import load_stock_universe

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
    assert _to_ts_code('688009') == '688009.SH'
    assert _to_ts_code('830799') == '830799.BJ'
