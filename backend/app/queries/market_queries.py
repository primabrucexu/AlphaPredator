from __future__ import annotations

from typing import Any


def get_hot_sector_trade_dates(connection: Any, limit: int) -> list[str]:
    rows = connection.execute(
        '''
        SELECT trade_date
        FROM hot_sector_daily_aggregates
        GROUP BY trade_date
        ORDER BY trade_date DESC LIMIT ?
        ''',
        [limit],
    ).fetchall()
    return [str(row['trade_date']) for row in reversed(rows)]


def get_hot_sector_rows_by_date(connection: Any, trade_date: str) -> list[Any]:
    return connection.execute(
        '''
        SELECT daily.sector_name_canonical AS name,
               daily.heat_score,
               daily.rank_today,
               daily.max_board_count,
               recent.trend_tag,
               recent.days_present_3d
        FROM hot_sector_daily_aggregates AS daily
                 LEFT JOIN hot_sector_recent_3d AS recent
                           ON recent.trade_date = daily.trade_date
                               AND recent.sector_name_canonical = daily.sector_name_canonical
        WHERE daily.trade_date = ?
        ORDER BY daily.rank_today ASC, daily.sector_name_canonical ASC
        ''',
        [trade_date],
    ).fetchall()


def get_latest_limit_up_trade_date(connection: Any) -> str:
    row = connection.execute(
        'SELECT MAX(trade_date) AS trade_date FROM hot_sector_stock_facts'
    ).fetchone()
    return str(row['trade_date'] or '') if row else ''


def get_limit_up_streak_rows(connection: Any, trade_date: str, min_boards: int) -> list[Any]:
    return connection.execute(
        '''
        SELECT facts.trade_date,
               facts.stock_code,
               facts.stock_name,
               COALESCE(facts.board_count, 0)                  AS board_count,
               facts.limit_up_time,
               COALESCE(primary_map.sector_name_canonical, '') AS hot_theme
        FROM hot_sector_stock_facts AS facts
                 LEFT JOIN hot_sector_sector_mappings AS primary_map
                           ON primary_map.trade_date = facts.trade_date
                               AND primary_map.source_file = facts.source_file
                               AND primary_map.stock_code = facts.stock_code
                               AND primary_map.is_primary_sector = 1
        WHERE facts.trade_date = ?
          AND COALESCE(facts.board_count, 0) >= ?
        ORDER BY COALESCE(facts.board_count, 0) DESC,
                 facts.limit_up_time ASC,
                 facts.stock_code ASC
        ''',
        [trade_date, min_boards],
    ).fetchall()


def get_stock_list_latest_uploaded_at(connection: Any) -> str | None:
    row = connection.execute(
        'SELECT MAX(uploaded_at) AS uploaded_at FROM stock_list'
    ).fetchone()
    if not row or not row['uploaded_at']:
        return None
    return str(row['uploaded_at'])


def get_stock_list_active_board_count_rows(connection: Any) -> list[Any]:
    return connection.execute(
        '''SELECT market, COUNT(*) AS cnt
           FROM stock_list
           WHERE list_status = 'L'
             AND market != ''
           GROUP BY market'''
    ).fetchall()
