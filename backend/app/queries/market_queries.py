from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Board-count parser (shared between query helpers and service layer)
# ---------------------------------------------------------------------------

_CN_NUM: dict[str, int] = {
    '十五': 15, '十四': 14, '十三': 13, '十二': 12, '十一': 11,
    '十': 10, '九': 9, '八': 8, '七': 7, '六': 6,
    '五': 5, '四': 4, '三': 3, '两': 2, '二': 2, '一': 1,
}


def parse_board_count(streak_text: str) -> int:
    """Derive the board count from a streak_text string.

    Examples:
        ''            → 1 (首板)
        '首板'        → 1
        '两天两板'     → 2
        '三连板'       → 3
        '二连板'       → 2
        '4连板'        → 4
    """
    text = str(streak_text or '').strip()
    if not text or text in ('首板', '首次涨停', '-'):
        return 1
    # Arabic digits take precedence
    m = re.search(r'(\d+)', text)
    if m:
        return max(1, int(m.group(1)))
    # Chinese multi-char (十一…十五 first to avoid partial match)
    for cn, val in _CN_NUM.items():
        if cn in text:
            return val
    return 1


# ---------------------------------------------------------------------------
# New queries: daily_hot_info / daily_hot_pic
# ---------------------------------------------------------------------------


def get_hot_info_trade_dates(connection: Any, limit: int) -> list[str]:
    """Return up to *limit* most-recent trade dates that have daily_hot_info records."""
    rows = connection.execute(
        '''
        SELECT DISTINCT trade_date
        FROM daily_hot_info
        ORDER BY trade_date DESC LIMIT ?
        ''',
        [limit],
    ).fetchall()
    return [str(row['trade_date']) for row in reversed(rows)]


def get_hot_info_rows_by_date(connection: Any, trade_date: str) -> list[Any]:
    """Return all daily_hot_info rows for *trade_date*."""
    return connection.execute(
        '''
        SELECT trade_date, stock_code, name, streak_text, hot_theme, limit_up_time
        FROM daily_hot_info
        WHERE trade_date = ?
        ORDER BY limit_up_time ASC, stock_code ASC
        ''',
        [trade_date],
    ).fetchall()


def get_latest_hot_info_trade_date(connection: Any) -> str:
    """Return the latest trade_date with any daily_hot_info records."""
    row = connection.execute(
        'SELECT MAX(trade_date) AS trade_date FROM daily_hot_info'
    ).fetchone()
    return str(row['trade_date'] or '') if row else ''


def get_hot_pic_rows_by_date(connection: Any, trade_date: str) -> list[Any]:
    """Return daily_hot_pic rows for *trade_date* ordered by id."""
    return connection.execute(
        '''
        SELECT id, trade_date, summary_image_url, source
        FROM daily_hot_pic
        WHERE trade_date = ?
        ORDER BY id ASC
        ''',
        [trade_date],
    ).fetchall()


def get_latest_hot_pic_trade_date(connection: Any) -> str:
    """Return the latest trade_date that has daily_hot_pic records."""
    row = connection.execute(
        'SELECT MAX(trade_date) AS trade_date FROM daily_hot_pic'
    ).fetchone()
    return str(row['trade_date'] or '') if row else ''


# ---------------------------------------------------------------------------
# Utility: stock_list count helper (unchanged)
# ---------------------------------------------------------------------------


def get_stock_list_active_board_count_rows(connection: Any) -> list[Any]:
    return connection.execute(
        '''SELECT market, COUNT(*) AS cnt
           FROM stock_list
           WHERE market != ''
           GROUP BY market'''
    ).fetchall()
