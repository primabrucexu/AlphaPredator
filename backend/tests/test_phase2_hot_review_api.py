"""Phase 2 hot-review API tests.

All assertions are based on the authoritative data model tables:
  - daily_hot_pic  (复盘图片)
  - daily_hot_info (涨停解析)

The legacy hot_sector_* tables are no longer tested here.
"""
from pathlib import Path

from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.service import MarketDataService


def _seed_hot_data(sqlite_path: Path, trade_date: str = '2026-05-07') -> None:
    """Insert sample data into daily_hot_pic and daily_hot_info."""
    conn = connect_sqlite(sqlite_path)
    try:
        conn.execute(
            'INSERT INTO daily_hot_pic (trade_date, summary_image_url, source) VALUES (?, ?, ?)',
            (trade_date, 'https://example.com/review-1.png', 'jygs'),
        )
        conn.execute(
            'INSERT INTO daily_hot_pic (trade_date, summary_image_url, source) VALUES (?, ?, ?)',
            (trade_date, 'https://example.com/review-2.png', 'jygs'),
        )
        # 2-board streak
        conn.execute(
            '''
            INSERT INTO daily_hot_info
            (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, source, short_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (trade_date, '09:45:00', 1, '平安银行', '两天两板', '银行', '季报增长', 'jygs', ''),
        )
        # 3-board streak, different theme
        conn.execute(
            '''
            INSERT INTO daily_hot_info
            (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, source, short_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (trade_date, '10:02:00', 300001, '某科技', '三连板', '半导体', '国产替代', 'jygs', ''),
        )
        # first-board stock should be excluded from min_boards=2 query
        conn.execute(
            '''
            INSERT INTO daily_hot_info
            (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, source, short_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (trade_date, '14:55:00', 600001, '某银行', '首板', '银行', '利好', 'jygs', ''),
        )
        conn.commit()
    finally:
        conn.close()


def test_service_reads_hot_review_images_from_daily_hot_pic(tmp_path: Path) -> None:
    """get_hot_review_images() must read from daily_hot_pic."""
    sqlite_path = tmp_path / 'alphapredator.db'
    ensure_sqlite_schema(sqlite_path)
    _seed_hot_data(sqlite_path)

    service = MarketDataService(sqlite_path=sqlite_path, duckdb_path=tmp_path / 'duck.db')
    images = service.get_hot_review_images(trade_date='2026-05-07')

    assert images.trade_date == '2026-05-07'
    urls = [img.url for img in images.images]
    assert 'https://example.com/review-1.png' in urls
    assert 'https://example.com/review-2.png' in urls
    assert len(urls) == 2


def test_service_reads_limit_up_streaks_from_daily_hot_info(tmp_path: Path) -> None:
    """get_limit_up_streaks() must derive board_count from streak_text in daily_hot_info."""
    sqlite_path = tmp_path / 'alphapredator.db'
    ensure_sqlite_schema(sqlite_path)
    _seed_hot_data(sqlite_path)

    service = MarketDataService(sqlite_path=sqlite_path, duckdb_path=tmp_path / 'duck.db')
    streaks = service.get_limit_up_streaks(trade_date='2026-05-07', min_boards=2)

    assert streaks.trade_date == '2026-05-07'
    codes = [s.stock_code for s in streaks.streaks]
    # 平安银行 (2-board) and 某科技 (3-board) should be present
    assert '1' in codes or '000001' in codes or '1' in codes
    assert all(s.board_count >= 2 for s in streaks.streaks)
    # 某科技 (3-board) should rank before 平安银行 (2-board)
    board_counts = [s.board_count for s in streaks.streaks]
    assert board_counts == sorted(board_counts, reverse=True)
    # first-board stock (600001) must be excluded
    assert '600001' not in codes


def test_service_reads_hot_sector_history_from_daily_hot_info(tmp_path: Path) -> None:
    """get_hot_sector_history() must aggregate themes from daily_hot_info."""
    sqlite_path = tmp_path / 'alphapredator.db'
    ensure_sqlite_schema(sqlite_path)
    _seed_hot_data(sqlite_path)

    service = MarketDataService(sqlite_path=sqlite_path, duckdb_path=tmp_path / 'duck.db')
    history = service.get_hot_sector_history(days=7)

    assert history.trade_dates == ['2026-05-07']
    sector_names = [s.name for s in history.days[0].sectors]
    assert '银行' in sector_names
    assert '半导体' in sector_names
    # 银行 has 2 stocks, 半导体 has 1 → 银行 should rank first
    bank = next(s for s in history.days[0].sectors if s.name == '银行')
    assert bank.heat_score == 2
    assert bank.rank_today == 1


def test_daily_hot_pic_schema_has_correct_columns(tmp_path: Path) -> None:
    """Verify that daily_hot_pic table has the columns defined in AlphaPredator.dbml."""
    sqlite_path = tmp_path / 'alphapredator.db'
    ensure_sqlite_schema(sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        cols = {row[1] for row in conn.execute('PRAGMA table_info(daily_hot_pic)').fetchall()}
    finally:
        conn.close()

    assert {'id', 'trade_date', 'summary_image_url', 'source'}.issubset(cols)


def test_daily_hot_info_schema_has_short_reason(tmp_path: Path) -> None:
    """Verify that daily_hot_info includes the short_reason column per AlphaPredator.dbml."""
    sqlite_path = tmp_path / 'alphapredator.db'
    ensure_sqlite_schema(sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        cols = {row[1] for row in conn.execute('PRAGMA table_info(daily_hot_info)').fetchall()}
    finally:
        conn.close()

    required = {'id', 'trade_date', 'limit_up_time', 'stock_code', 'name',
                'streak_text', 'hot_theme', 'reason', 'source', 'short_reason'}
    assert required.issubset(cols), f'Missing columns: {required - cols}'
