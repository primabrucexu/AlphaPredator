"""Tests for the V2 market data initializer."""

from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.data_source import _to_full_code, load_stock_list
from app.modules.market_data.initializer import (
    _atomic_write_day,
    _generate_date_list,
    _idle_status,
    _write_duckdb_day,
    create_task,
    get_overview,
    get_task,
    get_latest_task_by_type,
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
        'full_code': '000001.SZ',
        'open': 11.0, 'high': 11.5, 'low': 10.8, 'close': 11.2,
        'pre_close': 11.0, 'change': 0.2, 'pct_chg': 1.82,
        'vol': 50000000.0, 'amount': 0.56,
        'updated_at': '2026-01-01T00:00:00Z',
        'is_st': 0, 'st_source': '',
        'limit_up_price': 12.1, 'limit_down_price': 9.9, 'limit_pct': 0.10,
        'is_limit_up': 0, 'is_limit_down': 0,
        'limit_rule': 'MAIN', 'limit_status': 'NORMAL', 'limit_rule_version': 'V1',
    },
    {
        'trade_date': '20240102',
        'full_code': '600036.SH',
        'open': 35.0, 'high': 35.8, 'low': 34.5, 'close': 35.5,
        'pre_close': 35.0, 'change': 0.5, 'pct_chg': 1.43,
        'vol': 20000000.0, 'amount': 0.71,
        'updated_at': '2026-01-01T00:00:00Z',
        'is_st': 0, 'st_source': '',
        'limit_up_price': 38.5, 'limit_down_price': 31.5, 'limit_pct': 0.10,
        'is_limit_up': 0, 'is_limit_down': 0,
        'limit_rule': 'MAIN', 'limit_status': 'NORMAL', 'limit_rule_version': 'V1',
    },
]

# Mock data for per-stock range queries (new flow)
MOCK_STOCK_DATA = {
    '000001.SZ': [
        {
            'trade_date': '2024-01-01',
            'full_code': '000001.SZ',
            'open': 10.5, 'high': 11.0, 'low': 10.2, 'close': 10.8,
            'pre_close': 10.5, 'change': 0.3, 'pct_chg': 2.86,
            'vol': 40000000.0, 'amount': 0.43,
        },
        {
            'trade_date': '2024-01-02',
            'full_code': '000001.SZ',
            'open': 11.0, 'high': 11.5, 'low': 10.8, 'close': 11.2,
            'pre_close': 10.8, 'change': 0.4, 'pct_chg': 3.70,
            'vol': 50000000.0, 'amount': 0.56,
        },
        {
            'trade_date': '2024-01-03',
            'full_code': '000001.SZ',
            'open': 11.2, 'high': 11.8, 'low': 11.1, 'close': 11.5,
            'pre_close': 11.2, 'change': 0.3, 'pct_chg': 2.68,
            'vol': 45000000.0, 'amount': 0.52,
        },
    ],
    '600036.SH': [
        {
            'trade_date': '2024-01-01',
            'full_code': '600036.SH',
            'open': 34.5, 'high': 35.2, 'low': 34.0, 'close': 35.0,
            'pre_close': 34.5, 'change': 0.5, 'pct_chg': 1.45,
            'vol': 18000000.0, 'amount': 0.63,
        },
        {
            'trade_date': '2024-01-02',
            'full_code': '600036.SH',
            'open': 35.0, 'high': 35.8, 'low': 34.5, 'close': 35.5,
            'pre_close': 35.0, 'change': 0.5, 'pct_chg': 1.43,
            'vol': 20000000.0, 'amount': 0.71,
        },
        {
            'trade_date': '2024-01-03',
            'full_code': '600036.SH',
            'open': 35.5, 'high': 36.2, 'low': 35.3, 'close': 36.0,
            'pre_close': 35.5, 'change': 0.5, 'pct_chg': 1.41,
            'vol': 19000000.0, 'amount': 0.68,
        },
    ],
}


def _patch_licence(sqlite_path: Path | None = None):
    return patch('app.modules.market_data.initializer._get_mairui_licence', return_value='mock_licence')


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


def test_generate_date_list_weekdays_only_skips_weekends() -> None:
    # 20240101 (Mon) ~ 20240107 (Sun): 5 weekdays + 2 weekend days
    dates = _generate_date_list('20240101', '20240107', weekdays_only=True)
    assert dates == ['20240101', '20240102', '20240103', '20240104', '20240105']
    # Saturday 20240106 and Sunday 20240107 are skipped


# ---------------------------------------------------------------------------
# Unit: create_task
# ---------------------------------------------------------------------------


def test_create_task_creates_db_records(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    with _patch_licence():
        task = create_task('20240102', '20240105', sqlite_path=sqlite_path)

    assert task['task_id']
    assert task['task_type'] == 'MARKET_DATA'
    assert task['start_date'] == '20240102'
    assert task['end_date'] == '20240105'
    assert task['status'] == 'PENDING'
    assert task['total_items'] == 0
    assert task['processed_items'] == 0
    assert task['current_label'] == ''


def test_create_task_raises_when_licence_missing(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    with patch('app.modules.market_data.initializer._get_mairui_licence', return_value=''):
        with pytest.raises(ValueError, match='licence'):
            create_task('20240102', '20240103', sqlite_path=sqlite_path)


def test_create_task_sets_total_items_for_jygs_review(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    with patch('app.modules.market_data.initializer.check_jygs_auth_available', return_value={'is_valid': True}):
        task = create_task('20240102', '20240104', task_type='JYGS_REVIEW', sqlite_path=sqlite_path)

    assert task['task_type'] == 'JYGS_REVIEW'
    assert task['total_items'] == 3
    assert task['processed_items'] == 0


# ---------------------------------------------------------------------------
# Unit: atomic write
# ---------------------------------------------------------------------------


def test_atomic_write_day_inserts_rows(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)


    dconn = connect_duckdb(duckdb_path)
    duckdb_count = dconn.execute(
        "SELECT COUNT(*) FROM day_level_trade_data WHERE trade_date = '2024-01-02'"
    ).fetchone()[0]
    dconn.close()
    assert duckdb_count == 2


def test_atomic_write_day_also_writes_duckdb(tmp_path: Path) -> None:
    """_atomic_write_day must populate DuckDB day_level_trade_data for detail-page queries."""
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_schema(duckdb_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)

    conn = connect_duckdb(duckdb_path)
    rows = conn.execute(
        "SELECT full_code, trade_date, open, close, vol, amount "
        "FROM day_level_trade_data WHERE trade_date = '2024-01-02' ORDER BY full_code"
    ).fetchall()
    conn.close()

    assert len(rows) == 2, f'Expected 2 DuckDB rows, got {len(rows)}'
    # First row: 000001.SZ stored as-is
    assert rows[0][0] == '000001.SZ'
    assert rows[0][1] == '2024-01-02'
    assert rows[0][2] == Decimal('11.000000')  # open
    assert rows[0][3] == Decimal('11.200000')  # close
    assert rows[0][4] == Decimal('50000000.000000')  # vol
    # amount already follows the unified contract (亿元)
    assert rows[0][5] == Decimal('0.560000')


def test_write_duckdb_day_direct(tmp_path: Path) -> None:
    """_write_duckdb_day stores full_code and converts trade_date to YYYY-MM-DD."""
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_duckdb_schema(duckdb_path)

    _write_duckdb_day('20240102', MOCK_DAILY_ROWS, duckdb_path)

    conn = connect_duckdb(duckdb_path)
    rows = conn.execute(
        "SELECT full_code, trade_date FROM day_level_trade_data ORDER BY full_code"
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0][0] == '000001.SZ'
    assert rows[0][1] == '2024-01-02'
    assert rows[1][0] == '600036.SH'
    assert rows[1][1] == '2024-01-02'


def test_write_duckdb_day_idempotent(tmp_path: Path) -> None:
    """Writing the same day twice should result in 2 rows, not 4."""
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_duckdb_schema(duckdb_path)

    _write_duckdb_day('20240102', MOCK_DAILY_ROWS, duckdb_path)
    _write_duckdb_day('20240102', MOCK_DAILY_ROWS, duckdb_path)

    conn = connect_duckdb(duckdb_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM day_level_trade_data WHERE trade_date = '2024-01-02'"
    ).fetchone()[0]
    conn.close()
    assert count == 2


def test_atomic_write_day_persists_limit_fields(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)


    dconn = connect_duckdb(duckdb_path)
    row = dconn.execute(
        "SELECT full_code, trade_date, close FROM day_level_trade_data "
        "WHERE full_code = '000001.SZ' AND trade_date = '2024-01-02'"
    ).fetchone()
    dconn.close()
    assert row is not None


def test_atomic_write_day_is_idempotent(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)
    _atomic_write_day('20240102', MOCK_DAILY_ROWS, sqlite_path, duckdb_path)  # second write

    conn = connect_duckdb(duckdb_path)
    count = conn.execute("SELECT COUNT(*) FROM day_level_trade_data WHERE trade_date = '2024-01-02'").fetchone()[0]
    conn.close()
    assert count == 2  # still 2, not 4


def test_atomic_write_day_empty_rows(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)

    _atomic_write_day('20240102', [], sqlite_path, duckdb_path)  # should not raise

    conn = connect_duckdb(duckdb_path)
    count = conn.execute("SELECT COUNT(*) FROM day_level_trade_data WHERE trade_date = '2024-01-02'").fetchone()[0]
    conn.close()
    assert count == 0


# ---------------------------------------------------------------------------
# Unit: start_task concurrency
# ---------------------------------------------------------------------------


def test_start_task_returns_false_when_already_running(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    with _patch_licence():
        task1 = create_task('20240102', '20240102', sqlite_path=sqlite_path)
        task2 = create_task('20240103', '20240103', sqlite_path=sqlite_path)

    # Manually set task1 to RUNNING
    conn = connect_sqlite(sqlite_path)
    conn.execute(
        "UPDATE task_info SET status = 'RUNNING' WHERE task_id = ?",
        (task1['task_id'],),
    )
    conn.commit()
    conn.close()

    started = start_task(task2['task_id'], sqlite_path=sqlite_path)
    assert started is False


def test_retry_task_restarts_failed_task(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'

    with _patch_licence():
        task = create_task('20240102', '20240102', sqlite_path=sqlite_path)

    task_id = task['task_id']

    licence_patcher = patch('app.modules.market_data.initializer._get_mairui_licence', return_value='mock_licence')
    sync_patcher = patch('app.modules.market_data.initializer.sync_stock_list_to_sqlite')
    universe_patcher = patch(
        'app.modules.market_data.initializer._resolve_stock_universe',
        side_effect=_mock_resolve_stock_universe,
    )
    fail_fetch = patch(
        'app.modules.market_data.initializer._mairui_fetch_history_rows',
        side_effect=RuntimeError('first run failed'),
    )
    licence_patcher.start()
    sync_patcher.start()
    universe_patcher.start()
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
        universe_patcher.stop()
        sync_patcher.stop()
        licence_patcher.stop()

    success_fetch = patch(
        'app.modules.market_data.initializer._mairui_fetch_history_rows',
        side_effect=_mock_mairui_fetch_history_rows,
    )
    universe_patcher = patch(
        'app.modules.market_data.initializer._resolve_stock_universe',
        side_effect=_mock_resolve_stock_universe,
    )
    licence_patcher = patch('app.modules.market_data.initializer._get_mairui_licence', return_value='mock_licence')
    sync_patcher = patch('app.modules.market_data.initializer.sync_stock_list_to_sqlite')
    licence_patcher.start()
    sync_patcher.start()
    universe_patcher.start()
    success_fetch.start()
    try:
        retried = retry_task(task_id, sqlite_path=sqlite_path, duckdb_path=duckdb_path)
        assert retried is not None
        for _ in range(50):
            time.sleep(0.2)
            t = get_task(task_id, sqlite_path=sqlite_path)
            if t and t['status'] in ('SUCCESS', 'FAILED'):
                break
    finally:
        success_fetch.stop()
        universe_patcher.stop()
        sync_patcher.stop()
        licence_patcher.stop()

    final_task = get_task(task_id, sqlite_path=sqlite_path)
    assert final_task is not None
    assert final_task['status'] == 'SUCCESS'


def test_terminate_task_marks_task_terminated(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'

    with _patch_licence():
        task = create_task('20240102', '20240102', sqlite_path=sqlite_path)

    terminated = terminate_task(task['task_id'], sqlite_path=sqlite_path)
    assert terminated is not None
    assert terminated['status'] == 'TERMINATED'


# ---------------------------------------------------------------------------
# Integration: full task run (mocked provider)
# ---------------------------------------------------------------------------


def _mock_fetch_daily_raw(date_str: str, sqlite_path: Any = None) -> list[dict[str, Any]]:
    # For JYGS_REVIEW flow (legacy, date-based)
    # 20240102 is a trading day; everything else returns empty (non-trading)
    if date_str == '20240102':
        return list(MOCK_DAILY_ROWS)
    return []


def _mock_resolve_stock_universe(market_filters: Any = None, sqlite_path: Any = None,
                                 use_uploaded_universe: bool = True) -> Any:
    # Return a DataFrame with test stock list
    return pd.DataFrame([
        {'full_code': '000001.SZ', 'code': '000001', 'name': '平安银行'},
        {'full_code': '600036.SH', 'code': '600036', 'name': '招商银行'},
    ])


def _mock_mairui_fetch_history_rows(stock_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    # For MARKET_DATA flow (new, stock-based range query)
    # Note: dates from initializer are in YYYYMMDD format
    if stock_code in MOCK_STOCK_DATA:
        # Filter by date range
        result = []
        for row in MOCK_STOCK_DATA[stock_code]:
            # Convert row date from YYYY-MM-DD to YYYYMMDD for comparison
            td = row['trade_date'].replace('-', '')
            if start_date <= td <= end_date:
                result.append(row)
        return result
    return []


def test_full_task_run_succeeds(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'

    with _patch_licence():
        task = create_task('20240101', '20240103', sqlite_path=sqlite_path)

    task_id = task['task_id']

    # Keep patches active while the background thread runs
    licence_patcher = patch('app.modules.market_data.initializer._get_mairui_licence', return_value='mock_licence')
    sync_patcher = patch('app.modules.market_data.initializer.sync_stock_list_to_sqlite')
    universe_patcher = patch(
        'app.modules.market_data.initializer._resolve_stock_universe',
        side_effect=_mock_resolve_stock_universe,
    )
    fetch_patcher = patch(
        'app.modules.market_data.initializer._mairui_fetch_history_rows',
        side_effect=_mock_mairui_fetch_history_rows,
    )
    licence_patcher.start()
    sync_patcher.start()
    universe_patcher.start()
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
        universe_patcher.stop()
        sync_patcher.stop()
        licence_patcher.stop()

    t = get_task(task_id, sqlite_path=sqlite_path)
    assert t is not None
    assert t['status'] == 'SUCCESS', f'Unexpected status: {t}'
    assert t['total_items'] == 2
    assert t['processed_items'] == 2
    assert t['current_label'] == ''
    assert t['task_start_date'] != ''
    assert t['task_end_date'] != ''


    # Verify data was also written to DuckDB for detail-page queries
    dconn = connect_duckdb(duckdb_path)
    dcount = dconn.execute(
        "SELECT COUNT(*) FROM day_level_trade_data WHERE trade_date = '2024-01-02'"
    ).fetchone()[0]
    dconn.close()
    assert dcount >= 1, f'Expected at least 1 DuckDB row for 2024-01-02, got {dcount}'


def test_task_fails_on_fetch_error(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'

    with _patch_licence():
        task = create_task('20240102', '20240102', sqlite_path=sqlite_path)

    task_id = task['task_id']

    # Keep patches active while the background thread runs
    licence_patcher = patch('app.modules.market_data.initializer._get_mairui_licence', return_value='mock_licence')
    sync_patcher = patch('app.modules.market_data.initializer.sync_stock_list_to_sqlite')
    universe_patcher = patch(
        'app.modules.market_data.initializer._resolve_stock_universe',
        side_effect=_mock_resolve_stock_universe,
    )
    fetch_patcher = patch(
        'app.modules.market_data.initializer._mairui_fetch_history_rows',
        side_effect=RuntimeError('network error'),
    )
    licence_patcher.start()
    sync_patcher.start()
    universe_patcher.start()
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
        universe_patcher.stop()
        sync_patcher.stop()
        licence_patcher.stop()

    t = get_task(task_id, sqlite_path=sqlite_path)
    assert t is not None
    assert t['status'] == 'FAILED'
    assert 'network error' in t['error_message']


# ---------------------------------------------------------------------------
# Integration: reimport_day
# ---------------------------------------------------------------------------


def test_reimport_day_creates_and_starts_task(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    duckdb_path = tmp_path / 'test.duckdb'

    with _patch_licence():
        with patch(
                'app.modules.market_data.initializer.sync_stock_list_to_sqlite',
        ), patch(
            'app.modules.market_data.initializer._resolve_stock_universe',
            side_effect=_mock_resolve_stock_universe,
        ), patch(
            'app.modules.market_data.initializer._mairui_fetch_history_rows',
            side_effect=_mock_mairui_fetch_history_rows,
        ):
            task = reimport_day('20240102', sqlite_path=sqlite_path, duckdb_path=duckdb_path)

    assert task['task_type'] == 'MARKET_DATA'
    assert task['start_date'] == '20240102'
    assert task['end_date'] == '20240102'


# ---------------------------------------------------------------------------
# Integration: get_overview
# ---------------------------------------------------------------------------


def test_get_overview_returns_empty_when_no_tasks(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    overview = get_overview(sqlite_path=sqlite_path)
    assert overview['running_task'] is None
    assert overview['latest_task'] is None
    assert overview['latest_market_data_task'] is None
    assert overview['data_range']['min_trade_date'] is None


def test_get_overview_returns_latest_successful_market_data_task(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    with _patch_licence(), patch(
        'app.modules.market_data.initializer.check_jygs_auth_available',
        return_value={'is_valid': True},
    ):
        older_market = create_task('20240101', '20240131', sqlite_path=sqlite_path)
        jygs_task = create_task('20240201', '20240229', task_type='JYGS_REVIEW', sqlite_path=sqlite_path)
        latest_market = create_task('20240301', '20240331', sqlite_path=sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        conn.execute(
            "UPDATE task_info SET status = 'SUCCESS', task_end_date = ? WHERE task_id = ?",
            ('2024-02-01T10:00:00Z', older_market['task_id']),
        )
        conn.execute(
            "UPDATE task_info SET status = 'SUCCESS', task_end_date = ? WHERE task_id = ?",
            ('2024-03-01T10:00:00Z', jygs_task['task_id']),
        )
        conn.execute(
            "UPDATE task_info SET status = 'SUCCESS', task_end_date = ? WHERE task_id = ?",
            ('2024-04-01T10:00:00Z', latest_market['task_id']),
        )
        conn.commit()
    finally:
        conn.close()

    overview = get_overview(sqlite_path=sqlite_path)

    assert overview['latest_market_data_task']['task_id'] == latest_market['task_id']
    assert overview['latest_market_data_task']['start_date'] == '20240301'
    assert overview['latest_market_data_task']['end_date'] == '20240331'
    assert overview['latest_market_data_task']['task_end_date'] == '2024-04-01T10:00:00Z'


def test_get_latest_task_by_type_returns_newest_created_task_for_type(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    with _patch_licence(), patch(
        'app.modules.market_data.initializer.check_jygs_auth_available',
        return_value={'is_valid': True},
    ):
        first_market = create_task('20240101', '20240131', sqlite_path=sqlite_path)
        create_task('20240201', '20240229', task_type='JYGS_REVIEW', sqlite_path=sqlite_path)
        latest_market = create_task('20240301', '20240331', sqlite_path=sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        conn.execute(
            "UPDATE task_info SET status = 'FAILED', task_end_date = ? WHERE task_id = ?",
            ('2024-04-01T10:00:00Z', latest_market['task_id']),
        )
        conn.commit()
    finally:
        conn.close()

    task = get_latest_task_by_type('MARKET_DATA', sqlite_path=sqlite_path)

    assert task is not None
    assert task['task_id'] == latest_market['task_id']
    assert task['task_id'] != first_market['task_id']
    assert task['status'] == 'FAILED'


def test_get_latest_task_by_type_returns_none_when_type_has_no_tasks(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.db'
    ensure_sqlite_schema(sqlite_path)

    with _patch_licence():
        create_task('20240101', '20240131', sqlite_path=sqlite_path)

    assert get_latest_task_by_type('JYGS_REVIEW', sqlite_path=sqlite_path) is None


# ---------------------------------------------------------------------------
# Legacy compat: read_init_status
# ---------------------------------------------------------------------------


def test_read_init_status_returns_idle_when_no_tasks(tmp_path: Path) -> None:
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

def test_load_stock_list_filters_by_market(tmp_path: Path) -> None:
    mock_df = pd.DataFrame(
        [
            {'full_code': '000001.SZ', 'code': '000001', 'name': '平安银行', 'is_st': False, 'cnspell': 'PAYH',
             'market': '主板'},
            {'full_code': '300308.SZ', 'code': '300308', 'name': '中际旭创', 'is_st': False, 'cnspell': 'ZJXC',
             'market': '创业板'},
        ]
    )

    with (
        patch('app.modules.market_data.data_source._mairui_fetch_stock_list', return_value=mock_df),
    ):
        df_all = load_stock_list()
        assert len(df_all) == 2

        df_main = load_stock_list(market_filters=['主板'])
        assert len(df_main) == 1
        assert next(iter(df_main['code'])) == '000001'


def test_to_full_code_conversion() -> None:
    assert _to_full_code('000001') == '000001.SZ'
    assert _to_full_code('600036') == '600036.SH'
    assert _to_full_code('300308') == '300308.SZ'
    assert _to_full_code('830799') == '830799.BJ'
