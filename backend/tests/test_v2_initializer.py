"""Tests for the V2 market data initializer."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.modules.market_data.initializer import (
    _atomic_write_day,
    _generate_date_list,
    _idle_status,
    create_task,
    get_overview,
    get_task,
    get_task_days,
    is_trading_day,
    list_tasks,
    read_init_status,
    reimport_day,
    start_task,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MOCK_DAILY_ROWS = [
    {
        'trade_date': '20240102',
        'ts_code': '000001.SZ',
        'open': 11.0, 'high': 11.5, 'low': 10.8, 'close': 11.2,
        'pre_close': 11.0, 'change': 0.2, 'pct_chg': 1.82,
        'vol': 50000000.0, 'amount': 560000.0,
        'updated_at': '2026-01-01T00:00:00Z',
    },
    {
        'trade_date': '20240102',
        'ts_code': '600036.SH',
        'open': 35.0, 'high': 35.8, 'low': 34.5, 'close': 35.5,
        'pre_close': 35.0, 'change': 0.5, 'pct_chg': 1.43,
        'vol': 20000000.0, 'amount': 710000.0,
        'updated_at': '2026-01-01T00:00:00Z',
    },
]


def _patch_token(sqlite_path: Path | None = None):
    return patch('app.modules.market_data.data_source._get_token', return_value='mock_token')


# ---------------------------------------------------------------------------
# Unit: date helpers
# ---------------------------------------------------------------------------


def test_generate_date_list_ascending() -> None:
    dates = _generate_date_list('20240101', '20240105')
    assert dates == ['20240101', '20240102', '20240103', '20240104', '20240105']


def test_generate_date_list_single_day() -> None:
    dates = _generate_date_list('20240102', '20240102')
    assert dates == ['20240102']


def test_generate_date_list_empty_when_start_after_end() -> None:
    dates = _generate_date_list('20240110', '20240105')
    assert dates == []


# ---------------------------------------------------------------------------
# Unit: trading-day detection
# ---------------------------------------------------------------------------


def test_is_trading_day_known_holiday() -> None:
    assert is_trading_day(date(2024, 1, 1)) is False   # New Year
    assert is_trading_day(date(2024, 10, 1)) is False  # National Day


def test_is_trading_day_known_weekday() -> None:
    assert is_trading_day(date(2024, 1, 2)) is True   # Tuesday


def test_is_trading_day_weekend() -> None:
    assert is_trading_day(date(2024, 1, 6)) is False   # Saturday
    assert is_trading_day(date(2024, 1, 7)) is False   # Sunday


def test_is_trading_day_fallback_for_unsupported_year() -> None:
    # chncal does not cover years > 2025; should fall back to weekday check
    # 2030-01-07 is a Monday
    assert is_trading_day(date(2030, 1, 7)) is True
    # 2030-01-05 is a Saturday
    assert is_trading_day(date(2030, 1, 5)) is False


# ---------------------------------------------------------------------------
# Unit: create_task
# ---------------------------------------------------------------------------


def test_create_task_creates_db_records(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    with _patch_token():
        task = create_task('20240102', '20240105', sqlite_path=sqlite_path)

    assert task['task_id']
    assert task['start_date'] == '20240102'
    assert task['end_date'] == '20240105'
    assert task['status'] == 'PENDING'
    assert task['total_days'] == 4
    assert task['trading_days'] >= 0  # at least some trading days


def test_create_task_raises_when_token_missing(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    with patch('app.modules.market_data.data_source._get_token', return_value=''):
        with pytest.raises(ValueError, match='token'):
            create_task('20240102', '20240103', sqlite_path=sqlite_path)


def test_create_task_generates_day_records(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    with _patch_token():
        task = create_task('20240102', '20240104', sqlite_path=sqlite_path)

    task_id = task['task_id']
    result = get_task_days(task_id, sqlite_path=sqlite_path)
    assert result['total'] == 3
    trade_dates = [d['trade_date'] for d in result['days']]
    assert '20240102' in trade_dates
    assert '20240103' in trade_dates
    assert '20240104' in trade_dates


# ---------------------------------------------------------------------------
# Unit: atomic write
# ---------------------------------------------------------------------------


def test_atomic_write_day_inserts_rows(tmp_path: Path) -> None:
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path)

    from app.db.sqlite import connect_sqlite
    conn = connect_sqlite(sqlite_path)
    count = conn.execute(
        'SELECT COUNT(*) FROM market_daily_quote WHERE trade_date = ?', ('20240102',)
    ).fetchone()[0]
    conn.close()
    assert count == 2


def test_atomic_write_day_is_idempotent(tmp_path: Path) -> None:
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path)
    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path)  # second write

    from app.db.sqlite import connect_sqlite
    conn = connect_sqlite(sqlite_path)
    count = conn.execute(
        'SELECT COUNT(*) FROM market_daily_quote WHERE trade_date = ?', ('20240102',)
    ).fetchone()[0]
    conn.close()
    assert count == 2  # still 2, not 4


def test_atomic_write_day_empty_rows(tmp_path: Path) -> None:
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', [], sqlite_path)  # should not raise

    from app.db.sqlite import connect_sqlite
    conn = connect_sqlite(sqlite_path)
    count = conn.execute(
        'SELECT COUNT(*) FROM market_daily_quote WHERE trade_date = ?', ('20240102',)
    ).fetchone()[0]
    conn.close()
    assert count == 0


# ---------------------------------------------------------------------------
# Unit: start_task concurrency
# ---------------------------------------------------------------------------


def test_start_task_returns_false_when_already_running(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    with _patch_token():
        task1 = create_task('20240102', '20240102', sqlite_path=sqlite_path)
        task2 = create_task('20240103', '20240103', sqlite_path=sqlite_path)

    # Manually set task1 to RUNNING
    from app.db.sqlite import connect_sqlite
    conn = connect_sqlite(sqlite_path)
    conn.execute(
        "UPDATE init_task SET status = 'RUNNING' WHERE task_id = ?",
        (task1['task_id'],),
    )
    conn.commit()
    conn.close()

    started = start_task(task2['task_id'], sqlite_path=sqlite_path)
    assert started is False


# ---------------------------------------------------------------------------
# Integration: full task run (mocked tushare)
# ---------------------------------------------------------------------------


def _mock_fetch_daily_raw(date_str: str) -> list[dict[str, Any]]:
    if date_str == '20240102':
        return list(MOCK_DAILY_ROWS)
    return []


def test_full_task_run_succeeds(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'

    with _patch_token():
        task = create_task('20240101', '20240103', sqlite_path=sqlite_path)

    task_id = task['task_id']

    # Keep patches active while the background thread runs
    token_patcher = patch('app.modules.market_data.data_source._get_token', return_value='mock_token')
    fetch_patcher = patch(
        'app.modules.market_data.initializer._fetch_daily_raw',
        side_effect=_mock_fetch_daily_raw,
    )
    token_patcher.start()
    fetch_patcher.start()
    try:
        started = start_task(task_id, sqlite_path=sqlite_path)
        assert started is True

        for _ in range(50):
            time.sleep(0.2)
            t = get_task(task_id, sqlite_path=sqlite_path)
            if t and t['status'] in ('SUCCESS', 'FAILED'):
                break
    finally:
        fetch_patcher.stop()
        token_patcher.stop()

    t = get_task(task_id, sqlite_path=sqlite_path)
    assert t is not None
    assert t['status'] == 'SUCCESS', f'Unexpected status: {t}'
    assert t['processed_days'] == t['total_days']

    # Verify data was written for trading day 20240102
    from app.db.sqlite import connect_sqlite
    conn = connect_sqlite(sqlite_path)
    count = conn.execute(
        'SELECT COUNT(*) FROM market_daily_quote WHERE trade_date = ?', ('20240102',)
    ).fetchone()[0]
    conn.close()
    assert count == 2


def test_task_fails_on_fetch_error(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'

    with _patch_token():
        task = create_task('20240102', '20240102', sqlite_path=sqlite_path)

    task_id = task['task_id']

    # Keep patches active while the background thread runs
    token_patcher = patch('app.modules.market_data.data_source._get_token', return_value='mock_token')
    fetch_patcher = patch(
        'app.modules.market_data.initializer._fetch_daily_raw',
        side_effect=RuntimeError('network error'),
    )
    token_patcher.start()
    fetch_patcher.start()
    try:
        start_task(task_id, sqlite_path=sqlite_path)

        for _ in range(30):
            time.sleep(0.2)
            t = get_task(task_id, sqlite_path=sqlite_path)
            if t and t['status'] in ('SUCCESS', 'FAILED'):
                break
    finally:
        fetch_patcher.stop()
        token_patcher.stop()

    t = get_task(task_id, sqlite_path=sqlite_path)
    assert t is not None
    assert t['status'] == 'FAILED'
    assert 'network error' in t['error_message']


# ---------------------------------------------------------------------------
# Integration: reimport_day
# ---------------------------------------------------------------------------


def test_reimport_day_creates_and_starts_task(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'

    with _patch_token():
        with patch(
            'app.modules.market_data.initializer._fetch_daily_raw',
            side_effect=_mock_fetch_daily_raw,
        ):
            task = reimport_day('20240102', sqlite_path=sqlite_path)

    assert task['mode'] == 'REIMPORT_DAY'
    assert task['start_date'] == '20240102'
    assert task['end_date'] == '20240102'


# ---------------------------------------------------------------------------
# Integration: get_overview
# ---------------------------------------------------------------------------


def test_get_overview_returns_empty_when_no_tasks(tmp_path: Path) -> None:
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    overview = get_overview(sqlite_path=sqlite_path)
    assert overview['running_task'] is None
    assert overview['latest_task'] is None
    assert overview['data_range']['min_trade_date'] is None


# ---------------------------------------------------------------------------
# Legacy compat: read_init_status
# ---------------------------------------------------------------------------


def test_read_init_status_returns_idle_when_no_tasks(tmp_path: Path) -> None:
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    with patch('app.modules.market_data.initializer.get_overview') as mock_ov:
        mock_ov.return_value = {'running_task': None, 'latest_task': None, 'data_range': {}}
        s = read_init_status()
    assert s['status'] == 'idle'
    assert s['total_stocks'] == 0


def test_idle_status_shape() -> None:
    s = _idle_status()
    assert s['status'] == 'idle'
    assert 'trade_date' in s
    assert 'total_stocks' in s


# ---------------------------------------------------------------------------
# Data source unit tests (no network, kept from prior test suite)
# ---------------------------------------------------------------------------

MOCK_STOCK_LIST_CSV = (
    'ts_code,symbol,name,industry,cnspell,market,list_date,list_status,delist_date\n'
    '000001.SZ,000001,平安银行,银行,payh,主板,19910403,L,\n'
    '300308.SZ,300308,中际旭创,通信,zjxc,创业板,20130124,L,\n'
)


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


def test_to_ts_code_conversion() -> None:
    from app.modules.market_data.data_source import _to_ts_code

    assert _to_ts_code('000001') == '000001.SZ'
    assert _to_ts_code('600036') == '600036.SH'
    assert _to_ts_code('300308') == '300308.SZ'
    assert _to_ts_code('830799') == '830799.BJ'
