from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, func, select

from app.models.sqlite_models import DailyHotInfo, DailyHotPic, StockList

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


def _model_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, 'model_dump'):
        return row.model_dump()
    return dict(row)


def get_hot_info_trade_dates(session: Session, limit: int) -> list[str]:
    """Return up to *limit* most-recent trade dates that have daily_hot_info records."""
    rows = session.exec(
        select(DailyHotInfo.trade_date)
        .distinct()
        .order_by(DailyHotInfo.trade_date.desc())  # type: ignore[attr-defined]
        .limit(limit)
    ).all()
    return [str(trade_date) for trade_date in reversed(rows)]


def get_hot_info_rows_by_date(session: Session, trade_date: str) -> list[dict[str, Any]]:
    """Return all daily_hot_info rows for *trade_date*."""
    rows = session.exec(
        select(DailyHotInfo)
        .where(DailyHotInfo.trade_date == trade_date)
        .order_by(DailyHotInfo.limit_up_time, DailyHotInfo.stock_code)
    ).all()
    return [_model_to_dict(row) for row in rows]


def get_hot_info_table_rows_by_date(session: Session, trade_date: str) -> list[dict[str, Any]]:
    """Return table-friendly daily_hot_info rows for *trade_date*."""
    rows = session.exec(
        select(DailyHotInfo)
        .where(DailyHotInfo.trade_date == trade_date)
        .order_by(DailyHotInfo.limit_up_time, DailyHotInfo.stock_code)
    ).all()
    return [_model_to_dict(row) for row in rows]


def get_latest_hot_info_trade_date(session: Session) -> str:
    """Return the latest trade_date with any daily_hot_info records."""
    row = session.exec(select(func.max(DailyHotInfo.trade_date))).one()
    return str(row or '')


def get_hot_pic_rows_by_date(session: Session, trade_date: str) -> list[dict[str, Any]]:
    """Return daily_hot_pic rows for *trade_date* ordered by id."""
    rows = session.exec(
        select(DailyHotPic)
        .where(DailyHotPic.trade_date == trade_date)
        .order_by(DailyHotPic.id)
    ).all()
    return [_model_to_dict(row) for row in rows]


def get_limit_up_history_by_stock(session: Session, stock_code: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent limit-up records for a specific stock (desc by trade_date)."""
    rows = session.exec(
        select(DailyHotInfo)
        .where(DailyHotInfo.stock_code == stock_code)
        .order_by(DailyHotInfo.trade_date.desc())  # type: ignore[attr-defined]
        .limit(limit)
    ).all()
    return [_model_to_dict(row) for row in rows]


def get_latest_hot_pic_trade_date(session: Session) -> str:
    """Return the latest trade_date that has daily_hot_pic records."""
    row = session.exec(select(func.max(DailyHotPic.trade_date))).one()
    return str(row or '')


# ---------------------------------------------------------------------------
# Utility: stock_list count helper (unchanged)
# ---------------------------------------------------------------------------


def get_stock_list_active_board_count_rows(session: Session) -> list[dict[str, Any]]:
    rows = session.exec(
        select(StockList.market, func.count())
        .where(StockList.market != '')
        .group_by(StockList.market)
    ).all()
    return [{'market': market, 'cnt': count} for market, count in rows]
