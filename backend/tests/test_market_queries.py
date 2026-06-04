from pathlib import Path

from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.queries.market_queries import (
    get_hot_info_rows_by_date,
    get_hot_info_table_rows_by_date,
    get_hot_info_trade_dates,
    get_hot_pic_rows_by_date,
    get_latest_hot_info_trade_date,
    get_latest_hot_pic_trade_date,
    get_limit_up_history_by_stock,
    parse_board_count,
)


def _seed_hot_review_tables(sqlite_path: Path) -> None:
    conn = connect_sqlite(sqlite_path)
    try:
        conn.executemany(
            '''
            INSERT INTO daily_hot_info
                (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, source, short_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                ('2026-05-06', '09:31:00', '000001', 'PingAn', '\u9996\u677f', 'Bank', 'reason-1', 'jygs', 'short-1'),
                ('2026-05-07', '10:02:00', '000001', 'PingAn', '2\u8fde\u677f', 'Bank', 'reason-2', 'jygs', 'short-2'),
                ('2026-05-07', '09:45:00', '300001', 'Tech', '3\u8fde\u677f', 'AI', 'reason-3', 'jygs', 'short-3'),
                ('2026-05-08', '14:20:00', '000001', 'PingAn', '4\u8fde\u677f', 'Bank', 'reason-4', 'jygs', 'short-4'),
            ],
        )
        conn.executemany(
            '''
            INSERT INTO daily_hot_pic (trade_date, summary_image_url, source)
            VALUES (?, ?, ?)
            ''',
            [
                ('2026-05-07', 'https://example.com/a.png', 'jygs'),
                ('2026-05-07', 'https://example.com/b.png', 'jygs'),
                ('2026-05-08', 'https://example.com/c.png', 'jygs'),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_parse_board_count_handles_empty_digits_and_chinese() -> None:
    assert parse_board_count('') == 1
    assert parse_board_count('\u9996\u677f') == 1
    assert parse_board_count('-') == 1
    assert parse_board_count('4\u8fde\u677f') == 4
    assert parse_board_count('\u4e24\u5929\u4e24\u677f') == 2
    assert parse_board_count('\u4e09\u8fde\u677f') == 3
    assert parse_board_count('\u5341\u4e00\u8fde\u677f') == 11


def test_hot_query_helpers_read_expected_rows(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'test.sqlite3'
    ensure_sqlite_schema(sqlite_path)
    _seed_hot_review_tables(sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        assert get_hot_info_trade_dates(conn, 2) == ['2026-05-07', '2026-05-08']
        assert get_latest_hot_info_trade_date(conn) == '2026-05-08'
        assert get_latest_hot_pic_trade_date(conn) == '2026-05-08'

        rows = get_hot_info_rows_by_date(conn, '2026-05-07')
        assert [str(row['stock_code']) for row in rows] == ['300001', '000001']
        assert [str(row['limit_up_time']) for row in rows] == ['09:45:00', '10:02:00']

        table_rows = get_hot_info_table_rows_by_date(conn, '2026-05-07')
        assert [str(row['short_reason']) for row in table_rows] == ['short-3', 'short-2']
        assert [str(row['reason']) for row in table_rows] == ['reason-3', 'reason-2']

        pic_rows = get_hot_pic_rows_by_date(conn, '2026-05-07')
        assert [str(row['summary_image_url']) for row in pic_rows] == [
            'https://example.com/a.png',
            'https://example.com/b.png',
        ]

        history_rows = get_limit_up_history_by_stock(conn, '000001', limit=2)
        assert [str(row['trade_date']) for row in history_rows] == ['2026-05-08', '2026-05-07']
        assert [str(row['streak_text']) for row in history_rows] == ['4\u8fde\u677f', '2\u8fde\u677f']
    finally:
        conn.close()
