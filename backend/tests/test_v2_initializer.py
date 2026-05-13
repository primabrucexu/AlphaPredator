"""Tests for the V2 market data initializer."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.modules.market_data.initializer import (
    _atomic_write_day,
    _generate_date_list,
    _idle_status,
    _write_duckdb_day,
    create_task,
    get_overview,
    get_task,
    get_task_days,
    read_init_status,
    reimport_day,
    retry_task,
    start_task,
    terminate_task,
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
        'is_st': 0, 'st_source': '',
        'limit_up_price': 12.1, 'limit_down_price': 9.9, 'limit_pct': 0.10,
        'is_limit_up': 0, 'is_limit_down': 0,
        'limit_rule': 'MAIN', 'limit_status': 'NORMAL', 'limit_rule_version': 'V1',
    },
    {
        'trade_date': '20240102',
        'ts_code': '600036.SH',
        'open': 35.0, 'high': 35.8, 'low': 34.5, 'close': 35.5,
        'pre_close': 35.0, 'change': 0.5, 'pct_chg': 1.43,
        'vol': 20000000.0, 'amount': 710000.0,
        'updated_at': '2026-01-01T00:00:00Z',
        'is_st': 0, 'st_source': '',
        'limit_up_price': 38.5, 'limit_down_price': 31.5, 'limit_pct': 0.10,
        'is_limit_up': 0, 'is_limit_down': 0,
        'limit_rule': 'MAIN', 'limit_status': 'NORMAL', 'limit_rule_version': 'V1',
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
    assert task['trading_days'] == task['total_days']


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
    from app.db.duckdb_storage import connect_duckdb
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)


    dconn = connect_duckdb(duckdb_path)
    duckdb_count = dconn.execute(
        "SELECT COUNT(*) FROM daily_bars WHERE trade_date = '2024-01-02'"
    ).fetchone()[0]
    dconn.close()
    assert duckdb_count == 2


def test_atomic_write_day_also_writes_duckdb(tmp_path: Path) -> None:
    """_atomic_write_day must populate DuckDB daily_bars for detail-page queries."""
    from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_schema(duckdb_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)

    conn = connect_duckdb(duckdb_path)
    rows = conn.execute(
        "SELECT ts_code, trade_date, open, close, vol, amount "
        "FROM daily_bars WHERE trade_date = '2024-01-02' ORDER BY ts_code"
    ).fetchall()
    conn.close()

    assert len(rows) == 2, f'Expected 2 DuckDB rows, got {len(rows)}'
    # First row: 000001.SZ stored as-is
    assert rows[0][0] == '000001.SZ'
    assert rows[0][1] == '2024-01-02'
    assert rows[0][2] == pytest.approx(11.0)    # open
    assert rows[0][3] == pytest.approx(11.2)    # close
    assert rows[0][4] == pytest.approx(50000000.0)   # vol (float)
    # amount = 560000 千元 / 1e6 = 0.56
    assert rows[0][5] == pytest.approx(0.56, abs=0.001)


def test_write_duckdb_day_direct(tmp_path: Path) -> None:
    """_write_duckdb_day stores full ts_code and converts trade_date to YYYY-MM-DD."""
    from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_duckdb_schema(duckdb_path)

    _write_duckdb_day('20240102', MOCK_DAILY_ROWS, duckdb_path)

    conn = connect_duckdb(duckdb_path)
    rows = conn.execute(
        "SELECT ts_code, trade_date FROM daily_bars ORDER BY ts_code"
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0][0] == '000001.SZ'
    assert rows[0][1] == '2024-01-02'
    assert rows[1][0] == '600036.SH'
    assert rows[1][1] == '2024-01-02'


def test_write_duckdb_day_idempotent(tmp_path: Path) -> None:
    """Writing the same day twice should result in 2 rows, not 4."""
    from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_duckdb_schema(duckdb_path)

    _write_duckdb_day('20240102', MOCK_DAILY_ROWS, duckdb_path)
    _write_duckdb_day('20240102', MOCK_DAILY_ROWS, duckdb_path)

    conn = connect_duckdb(duckdb_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM daily_bars WHERE trade_date = '2024-01-02'"
    ).fetchone()[0]
    conn.close()
    assert count == 2


def test_atomic_write_day_persists_limit_fields(tmp_path: Path) -> None:
    from app.db.duckdb_storage import connect_duckdb
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)


    dconn = connect_duckdb(duckdb_path)
    row = dconn.execute(
        "SELECT ts_code, trade_date, close FROM daily_bars "
        "WHERE ts_code = '000001.SZ' AND trade_date = '2024-01-02'"
    ).fetchone()
    dconn.close()
    assert row is not None


def test_atomic_write_day_is_idempotent(tmp_path: Path) -> None:
    from app.db.duckdb_storage import connect_duckdb
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)
    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)  # second write

    conn = connect_duckdb(duckdb_path)
    count = conn.execute("SELECT COUNT(*) FROM daily_bars WHERE trade_date = '2024-01-02'").fetchone()[0]
    conn.close()
    assert count == 2  # still 2, not 4


def test_atomic_write_day_empty_rows(tmp_path: Path) -> None:
    from app.db.duckdb_storage import connect_duckdb
    from app.db.sqlite import ensure_sqlite_schema
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', [], sqlite_path, duckdb_path)  # should not raise

    conn = connect_duckdb(duckdb_path)
    count = conn.execute("SELECT COUNT(*) FROM daily_bars WHERE trade_date = '2024-01-02'").fetchone()[0]
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


def test_retry_task_restarts_failed_task(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'

    with _patch_token():
        task = create_task('20240102', '20240102', sqlite_path=sqlite_path)

    task_id = task['task_id']

    token_patcher = patch('app.modules.market_data.data_source._get_token', return_value='mock_token')
    fail_fetch = patch(
        'app.modules.market_data.initializer._fetch_daily_raw',
        side_effect=RuntimeError('first run failed'),
    )
    token_patcher.start()
    fail_fetch.start()
    try:
        started = start_task(task_id, sqlite_path=sqlite_path)
        assert started is True
        for _ in range(30):
            time.sleep(0.2)
            t = get_task(task_id, sqlite_path=sqlite_path)
            if t and t['status'] == 'FAILED':
                break
    finally:
        fail_fetch.stop()
        token_patcher.stop()

    success_fetch = patch(
        'app.modules.market_data.initializer._fetch_daily_raw',
        side_effect=_mock_fetch_daily_raw,
    )
    token_patcher = patch('app.modules.market_data.data_source._get_token', return_value='mock_token')
    token_patcher.start()
    success_fetch.start()
    try:
        retried = retry_task(task_id, sqlite_path=sqlite_path)
        assert retried is not None
        for _ in range(50):
            time.sleep(0.2)
            t = get_task(task_id, sqlite_path=sqlite_path)
            if t and t['status'] in ('SUCCESS', 'FAILED'):
                break
    finally:
        success_fetch.stop()
        token_patcher.stop()

    final_task = get_task(task_id, sqlite_path=sqlite_path)
    assert final_task is not None
    assert final_task['status'] == 'SUCCESS'


def test_terminate_task_marks_task_terminated(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'

    with _patch_token():
        task = create_task('20240102', '20240102', sqlite_path=sqlite_path)

    terminated = terminate_task(task['task_id'], sqlite_path=sqlite_path)
    assert terminated is not None
    assert terminated['status'] == 'TERMINATED'


# ---------------------------------------------------------------------------
# Integration: full task run (mocked tushare)
# ---------------------------------------------------------------------------


def _mock_fetch_daily_raw(date_str: str, sqlite_path: Any = None) -> list[dict[str, Any]]:
    # 20240102 is a trading day; everything else returns empty (non-trading)
    if date_str == '20240102':
        return list(MOCK_DAILY_ROWS)
    return []


def test_full_task_run_succeeds(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'

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
        started = start_task(task_id, sqlite_path=sqlite_path, duckdb_path=duckdb_path)
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


    # Verify data was also written to DuckDB for detail-page queries
    from app.db.duckdb_storage import connect_duckdb
    dconn = connect_duckdb(duckdb_path)
    dcount = dconn.execute(
        "SELECT COUNT(*) FROM daily_bars WHERE trade_date = '2024-01-02'"
    ).fetchone()[0]
    dconn.close()
    assert dcount == 2, f'Expected 2 DuckDB rows for 2024-01-02, got {dcount}'


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


def test_load_stock_list_filters_by_market(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from app.modules.market_data.data_source import load_stock_list

    stock_list_path = tmp_path / 'config' / 'stock_list.csv'
    stock_list_path.parent.mkdir(parents=True, exist_ok=True)
    stock_list_path.write_text(MOCK_STOCK_LIST_CSV, encoding='utf-8')

    mock_settings = MagicMock()
    mock_settings.stock_list_path = stock_list_path

    with patch('app.modules.market_data.data_source.settings', mock_settings):
        df_all = load_stock_list()
        assert len(df_all) == 2

        df_main = load_stock_list(market_filters=['主板'])
        assert len(df_main) == 1
        assert df_main.iloc[0]['symbol'] == '000001'


def test_to_ts_code_conversion() -> None:
    from app.modules.market_data.data_source import _to_ts_code

    assert _to_ts_code('000001') == '000001.SZ'
    assert _to_ts_code('600036') == '600036.SH'
    assert _to_ts_code('300308') == '300308.SZ'
    assert _to_ts_code('830799') == '830799.BJ'
