from pathlib import Path

from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.service import MarketDataService


def test_market_service_reads_unified_hot_review_tables(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'alphapredator.db'
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    ensure_sqlite_schema(sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        conn.execute(
            '''
            INSERT INTO hot_sector_daily_aggregates (
                trade_date, sector_name_canonical, source_stock_count, max_board_count,
                representative_stock_codes_json, representative_stock_names_json,
                heat_score, rank_today, aggregate_confidence, needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                '2026-05-07', '银行', 1, 2,
                '["000001"]', '["平安银行"]',
                26, 1, 1.0, 0,
            ),
        )
        conn.execute(
            '''
            INSERT INTO hot_sector_recent_3d (
                trade_date, sector_name_canonical, days_present_3d, heat_sum_3d,
                heat_avg_3d, best_rank_3d, latest_rank, trend_tag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            ('2026-05-07', '银行', 2, 40, 20.0, 1, 1, 'persistent'),
        )
        conn.execute(
            '''
            INSERT INTO hot_sector_stock_facts (
                trade_date, source_file, stock_code, stock_name, board_count,
                limit_up_time, reason_raw, reason_clean, ocr_confidence, needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                '2026-05-07', 'jygs_api_2026-05-07', '000001', '平安银行', 2,
                '09:45:00', '测试原因', '测试原因', 1.0, 0,
            ),
        )
        conn.execute(
            '''
            INSERT INTO hot_sector_sector_mappings (
                trade_date, source_file, stock_code, sector_name_canonical, sector_alias_hit,
                is_primary_sector, mapping_method, mapping_confidence, needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                '2026-05-07', 'jygs_api_2026-05-07', '000001', '银行', '银行',
                1, 'api_theme', 1.0, 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    service = MarketDataService(sqlite_path=sqlite_path, duckdb_path=duckdb_path)

    history = service.get_hot_sector_history(days=7)
    assert history.trade_dates == ['2026-05-07']
    assert history.days[0].sectors[0].name == '银行'

    streaks = service.get_limit_up_streaks(trade_date='2026-05-07', min_boards=2)
    assert streaks.trade_date == '2026-05-07'
    assert streaks.streaks[0].stock_code == '000001'
    assert streaks.streaks[0].board_count == 2

