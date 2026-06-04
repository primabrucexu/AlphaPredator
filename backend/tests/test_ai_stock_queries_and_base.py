from decimal import Decimal
from pathlib import Path

from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.ai_stock.base import AtomicBase, to_decimal
from app.modules.ai_stock.queries import AtomicQueries


def _prepare_test_dbs(tmp_path: Path) -> tuple[Path, Path]:
    sqlite_path = tmp_path / 'test.sqlite3'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_schema(duckdb_path)

    sqlite_conn = connect_sqlite(sqlite_path)
    try:
        sqlite_conn.executemany(
            '''
            INSERT INTO stock_list (full_code, code, name, is_st, cnspell, market)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            [
                ('000001.SZ', '000001', 'PingAn', 0, 'PAYH', 'main'),
                ('000002.SZ', '000002', 'Vanke', 1, 'WKGF', 'main'),
            ],
        )
        sqlite_conn.executemany(
            '''
            INSERT INTO daily_hot_info
                (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, source, short_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                ('2026-05-28', '09:30:00', '000001', 'PingAn', '\u9996\u677f', 'Bank+Fintech', 'r1', 'jygs', ''),
                ('2026-05-27', '09:30:00', '000001', 'PingAn', '2\u8fde\u677f', 'Bank', 'r2', 'jygs', ''),
            ],
        )
        sqlite_conn.commit()
    finally:
        sqlite_conn.close()

    duck_conn = connect_duckdb(duckdb_path)
    try:
        duck_conn.execute(
            '''
            INSERT INTO day_level_trade_data
                (full_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, is_up_limit, is_down_limit)
            VALUES
                ('000001.SZ', '2026-05-26', 10.00, 10.30, 9.95, 10.20, 10.00, 0.20, 0.0200, 1000, 10000, FALSE, FALSE),
                ('000001.SZ', '2026-05-27', 10.20, 10.60, 10.18, 10.60, 10.20, 0.40, 0.0392, 2000, 22000, TRUE, FALSE),
                ('000001.SZ', '2026-05-28', 10.50, 10.55, 10.00, 10.10, 10.60, -0.50, -0.0471, 800, 9000, FALSE, FALSE)
            '''
        )
    finally:
        duck_conn.close()
    return sqlite_path, duckdb_path


def test_atomic_queries_cover_duckdb_and_sqlite_lookups(tmp_path: Path) -> None:
    sqlite_path, duckdb_path = _prepare_test_dbs(tmp_path)
    queries = AtomicQueries(sqlite_path=sqlite_path, duckdb_path=duckdb_path)

    day_row = queries.get_day_row('000001.SZ', '2026-05-28')
    assert day_row is not None
    assert str(day_row[0]) == '2026-05-28'
    assert queries.has_trade_day('2026-05-27') is True
    assert queries.has_trade_day('2026-05-30') is False
    assert queries.get_prev_trade_days('2026-05-28', 2) == ['2026-05-27', '2026-05-26']

    recent_rows = queries.get_recent_rows('000001.SZ', '2026-05-28', 2)
    assert [str(row[0]) for row in recent_rows] == ['2026-05-28', '2026-05-27']

    forward_rows = queries.get_forward_rows('000001.SZ', '2026-05-27', 2)
    assert [str(row[0]) for row in forward_rows] == ['2026-05-27', '2026-05-28']

    assert queries.get_stock_is_st('000001') is False
    assert queries.get_stock_is_st('000002') is True
    assert queries.get_stock_is_st('999999') is None
    assert queries.get_stock_name('000001') == 'PingAn'
    assert queries.get_stock_name('999999') is None
    assert queries.get_hot_themes('000001', '2026-05-28', 3) == ['Bank+Fintech', 'Bank']


def test_atomic_base_normalization_and_row_conversion(tmp_path: Path) -> None:
    sqlite_path, duckdb_path = _prepare_test_dbs(tmp_path)
    base = AtomicBase(sqlite_path=sqlite_path, duckdb_path=duckdb_path)

    assert to_decimal(1.23) == Decimal('1.23')
    assert to_decimal(Decimal('2.5')) == Decimal('2.5')
    assert base._normalize_stock_code('1') == '000001'
    assert base._normalize_stock_code('000001.SZ') == '000001'
    assert base._normalize_trade_date('2026-05-28') == '2026-05-28'
    assert base._stock_name('000001') == 'PingAn'

    row = base._get_row_for_day('000001', '2026-05-28')
    assert row is not None
    assert row.trade_date == '2026-05-28'
    assert row.close_price == Decimal('10.100000')

    recent = base._get_recent_rows('000001', '2026-05-28', 2)
    assert [item.trade_date for item in recent] == ['2026-05-28', '2026-05-27']

    forward = base._get_forward_rows('000001', '2026-05-27', 2)
    assert [item.trade_date for item in forward] == ['2026-05-27', '2026-05-28']
