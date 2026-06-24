"""
Tests migrated from the old Phase 2.9 initializer.

The V2 initializer replaces the old CSV-based approach.  This file retains
the following tests that remain relevant after the V2 refactor:
- Updater (run_daily_update): unmodified, still uses the same API.
- Data source helpers (load_stock_list, _to_full_code): unchanged utilities.

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

import pandas as pd
import pytest

from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_parent, ensure_duckdb_schema
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.data_source import _market_board_from_code, _to_full_code, load_stock_list, \
    sync_stock_list_to_sqlite
from app.modules.market_data.updater import run_daily_update
from app.repositories.stock_list_repo import StockListRepo

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
        'full_code': '000001.SZ',
        'trade_date': '2026-05-03',
        'open': 11.13,
        'high': 11.31,
        'low': 11.08,
        'close': 11.28,
        'pre_close': 11.14,
        'change': 0.14,
        'pct_chg': 1.26,
        'vol': 56340000.0,
        'amount': 31.70,
        'is_up_limit': False,
        'is_down_limit': False,
    },
    {
        'full_code': '300308.SZ',
        'trade_date': '2026-05-03',
        'open': 165.90,
        'high': 168.40,
        'low': 164.70,
        'close': 167.53,
        'pre_close': 161.60,
        'change': 5.93,
        'pct_chg': 3.67,
        'vol': 22860000.0,
        'amount': 82.40,
        'is_up_limit': False,
        'is_down_limit': False,
    },
]

MOCK_STOCK_LIST_CSV = (
    'full_code,code,name,is_st,cnspell,market\n'
    '000001.SZ,000001,平安银行,0,payh,主板\n'
    '300308.SZ,300308,中际旭创,0,zjxc,创业板\n'
)


def _mock_fetch_spot_snapshot(trade_date=None, *, market_filters=None, sqlite_path=None):  # noqa: ARG001
    return MOCK_SNAPSHOT_ROWS


def _mock_fetch_stock_pool(snapshot_rows=None, *, market_filters=None, sqlite_path=None):  # noqa: ARG001
    rows = snapshot_rows or MOCK_SNAPSHOT_ROWS
    return [
        {'stock_code': r['stock_code'], 'stock_name': r['stock_name'], 'sectors': '', 'ai_quick_summary': ''}
        for r in rows
    ]


def _mock_fetch_daily_bars_by_date(trade_date, *, use_uploaded_universe=True, market_filters=None,
                                   sqlite_path=None):  # noqa: ARG001
    return list(MOCK_BARS)


# ---------------------------------------------------------------------------
# Updater tests
# ---------------------------------------------------------------------------


def test_run_daily_update_succeeds(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'alphapredator.db'
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    daily_bars_parquet_path = tmp_path / 'parquet' / 'stock_daily_bars.parquet'
    market_snapshot_path = tmp_path / 'parquet' / 'market_snapshot.json'

    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_parent(duckdb_path, daily_bars_parquet_path.parent)
    ensure_duckdb_schema(duckdb_path)

    with (
        patch('app.modules.market_data.updater.sync_stock_list_to_sqlite'),
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

    conn = connect_sqlite(sqlite_path)
    try:
        stock_list_count = conn.execute('SELECT COUNT(*) FROM stock_list').fetchone()[0]
    finally:
        conn.close()
    assert stock_list_count == 0


def test_run_daily_update_skips_limit_flags_for_forward_adjusted_daily_data(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'alphapredator.db'
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    daily_bars_parquet_path = tmp_path / 'parquet' / 'stock_daily_bars.parquet'
    market_snapshot_path = tmp_path / 'parquet' / 'market_snapshot.json'
    bars = [
        {
            **MOCK_BARS[0],
            'is_up_limit': True,
            'is_down_limit': True,
        }
    ]

    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_parent(duckdb_path, daily_bars_parquet_path.parent)
    ensure_duckdb_schema(duckdb_path)

    with (
        patch('app.modules.market_data.updater.sync_stock_list_to_sqlite'),
        patch('app.modules.market_data.updater.fetch_spot_snapshot', side_effect=_mock_fetch_spot_snapshot),
        patch('app.modules.market_data.updater.fetch_stock_pool', side_effect=_mock_fetch_stock_pool),
        patch('app.modules.market_data.updater.fetch_daily_bars_by_date', return_value=bars),
    ):
        run_daily_update(
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
            daily_bars_parquet_path=daily_bars_parquet_path,
            market_snapshot_path=market_snapshot_path,
        )

    conn = connect_duckdb(duckdb_path)
    saved = conn.execute(
        "SELECT is_up_limit, is_down_limit FROM day_level_trade_data "
        "WHERE full_code = '000001.SZ'"
    ).fetchone()
    conn.close()

    assert saved == (False, False)


# ---------------------------------------------------------------------------
# Data source unit tests
# ---------------------------------------------------------------------------


def test_load_stock_list_filters_by_market(tmp_path: Path) -> None:
    mock_df = pd.DataFrame(
        [
            {'full_code': '000001.SZ', 'code': '000001', 'name': '平安银行', 'is_st': False, 'cnspell': 'PAYH',
             'market': '主板'},
            {'full_code': '300308.SZ', 'code': '300308', 'name': '中际旭创', 'is_st': False, 'cnspell': 'ZJXC',
             'market': '创业板'},
        ]
    )

    with patch('app.modules.market_data.data_source._mairui_fetch_stock_list', return_value=mock_df):
        df_all = load_stock_list()
        assert len(df_all) == 2

        df_main = load_stock_list(market_filters=['主板'])
        assert len(df_main) == 1
        assert next(iter(df_main['code'])) == '000001'

        df_cyb = load_stock_list(market_filters=['创业板'])
        assert len(df_cyb) == 1
        assert next(iter(df_cyb['code'])) == '300308'


def test_load_stock_list_raises_when_provider_unavailable() -> None:
    with patch(
            'app.modules.market_data.data_source._mairui_fetch_stock_list',
            side_effect=RuntimeError('provider unavailable'),
    ):
        with pytest.raises(RuntimeError):
            load_stock_list()


def test_to_full_code_conversion() -> None:
    assert _to_full_code('000001') == '000001.SZ'
    assert _to_full_code('600036') == '600036.SH'
    assert _to_full_code('300308') == '300308.SZ'
    assert _to_full_code('688009') == '688009.SH'
    assert _to_full_code('830799') == '830799.BJ'


def test_market_board_from_code_matches_latest_doc_rules() -> None:
    assert _market_board_from_code('000001') == '主板'
    assert _market_board_from_code('600036') == '主板'
    assert _market_board_from_code('300308') == '创业板'
    assert _market_board_from_code('301183') == '创业板'
    assert _market_board_from_code('688009') == '科创板'
    assert _market_board_from_code('689009') == '科创板'
    assert _market_board_from_code('920001') == '北交所'


def test_sync_stock_list_to_sqlite_persists_rows(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'alphapredator.db'
    mock_df = pd.DataFrame(
        [
            {'full_code': '000001.SZ', 'code': '000001', 'name': '平安银行', 'is_st': False, 'cnspell': '',
             'market': '主板'},
            {'full_code': '688009.SH', 'code': '688009', 'name': '中国通号', 'is_st': False, 'cnspell': '',
             'market': '科创板'},
        ]
    )

    with patch('app.modules.market_data.data_source._mairui_fetch_stock_list', return_value=mock_df):
        synced_df = sync_stock_list_to_sqlite(sqlite_path=sqlite_path)

    assert len(synced_df) == 2
    repo = StockListRepo(sqlite_path)
    assert repo.get_by_full_code_upper('000001.SZ') is not None
    assert repo.count_rows() == 2
    assert repo.get_board_counts() == {'主板': 1, '科创板': 1}
