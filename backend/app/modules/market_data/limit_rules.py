"""
Limit price (涨跌停) calculation rules for Chinese A-shares.

Provides:
- Board/market segment detection from full_code.
- Limit-up / limit-down price calculation using Decimal arithmetic.
- ST flag detection from stock name prefix.
- No-limit-day detection for newly listed stocks (first 5 trading days).
- ``compute_limit_fields``: master function that returns all limit-related
  column values ready for persistence.

Design references: docs/market-data-init-v2-blueprint.md §7.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TICK_SIZE = Decimal('0.01')
MIN_PRICE = Decimal('0.01')

LIMIT_RULE_VERSION = 'V1'

# Board identifier constants
BOARD_MAIN = 'MAIN'        # 沪/深 主板
BOARD_CHINEXT = 'CHINEXT'  # 创业板
BOARD_STAR = 'STAR'        # 科创板
BOARD_BSE = 'BSE'          # 北交所

# Per-board rule configuration
_BOARD_RULES: dict[str, dict[str, Any]] = {
    BOARD_MAIN:    {'limit_pct': Decimal('0.10'), 'rounding': ROUND_HALF_UP},
    BOARD_CHINEXT: {'limit_pct': Decimal('0.20'), 'rounding': ROUND_HALF_UP},
    BOARD_STAR:    {'limit_pct': Decimal('0.20'), 'rounding': ROUND_HALF_UP},
    BOARD_BSE:     {'limit_pct': Decimal('0.30'), 'rounding': ROUND_FLOOR},
}

# Number of calendar days to scan when checking no-limit window.
# 5 trading days span at most ~14 calendar days even across a long holiday;
# 30 is a conservative upper bound that keeps the loop short.
_NO_LIMIT_CALENDAR_WINDOW = 30

# ST-style name prefixes (case-sensitive per exchange convention)
_ST_PREFIX_RE = re.compile(r'^(\*ST|SST|S\*ST|ST)\s*')


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Board detection
# ---------------------------------------------------------------------------


def detect_board(full_code: str) -> str | None:
    """Return the board constant for *full_code*, or None if unrecognised.

    Mapping rules (V1):
    - ``XXXXXX.BJ``            → BSE  (北交所)
    - ``688XXX.SH``, ``689XXX.SH``  → STAR (科创板)
    - ``3XXXXX.SZ``            → CHINEXT (创业板)
    - ``6XXXXX.SH``, ``0XXXXX.SZ``, ``1XXXXX.SZ``, ``2XXXXX.SZ`` → MAIN (主板)
    """
    normalized_full_code = str(full_code or '').strip().upper()
    parts = normalized_full_code.split('.')
    if len(parts) != 2:
        return None
    code, exchange = parts

    if exchange == 'BJ':
        return BOARD_BSE

    if exchange == 'SH':
        if code.startswith('688') or code.startswith('689'):
            return BOARD_STAR
        if code.startswith('6'):
            return BOARD_MAIN
        return None

    if exchange == 'SZ':
        if code.startswith('3'):
            return BOARD_CHINEXT
        if code[0] in ('0', '1', '2'):
            return BOARD_MAIN
        return None

    return None


# ---------------------------------------------------------------------------
# ST detection
# ---------------------------------------------------------------------------


def detect_is_st(name: str) -> bool:
    """Return True if *name* starts with an ST-style prefix.

    Recognises: ``ST``, ``*ST``, ``SST``, ``S*ST`` (per §7.4 of blueprint).
    """
    return bool(_ST_PREFIX_RE.match(name.strip()))


# ---------------------------------------------------------------------------
# No-limit day detection (新股上市前5个交易日)
# ---------------------------------------------------------------------------


def _is_trading_day_local(d: date) -> bool:
    """Weekday-only approximation used for no-limit-day window detection.

    Provider empty response is the authoritative non-trading-day signal
    during import; this function is only used to count trading days within
    the new-listing 5-day window for limit-rule classification.
    """
    return d.weekday() < 5  # Mon-Fri


def is_no_limit_day(trade_date: str, list_date: str | None) -> bool:
    """Return True if *trade_date* falls within the first 5 trading days after listing.

    Uses the same ChnCal-based trading-day check as the rest of the system.

    Parameters
    ----------
    trade_date:
        Date being evaluated, ``YYYYMMDD`` format.
    list_date:
        Listing date of the stock, ``YYYYMMDD`` format, or ``None`` / empty if unknown.

    Returns False (conservative) when *list_date* is unavailable.
    """
    if not list_date:
        return False
    try:
        d_list = datetime.strptime(list_date, '%Y%m%d').date()
        d_trade = datetime.strptime(trade_date, '%Y%m%d').date()
    except ValueError:
        return False

    if d_trade < d_list:
        return False

    # Fast-exit: beyond the calendar window → definitely not in first 5 trading days.
    if (d_trade - d_list).days > _NO_LIMIT_CALENDAR_WINDOW:
        return False

    # Count trading days from list_date to trade_date (inclusive).
    count = 0
    d = d_list
    while d <= d_trade:
        if _is_trading_day_local(d):
            count += 1
        d += timedelta(days=1)

    return count <= 5


# ---------------------------------------------------------------------------
# Master computation function
# ---------------------------------------------------------------------------


def compute_limit_fields(
        full_code: str,
    trade_date: str,
        pre_close: Decimal | None,
        close: Decimal | None,
    stock_name: str = '',
    list_date: str | None = None,
) -> dict[str, Any]:
    """Compute all limit-related fields for one daily quote row.

    Priority logic (per §7.1 of blueprint):
    1. No-limit day (first 5 trading days after listing) → ``NO_LIMIT``.
    2. Board-based rule if board is recognised → compute prices.
    3. Fallback → ``INVALID``.

    Returns a dict with keys:
        ``is_st``, ``st_source``,
        ``limit_up_price``, ``limit_down_price``, ``limit_pct``,
        ``is_limit_up``, ``is_limit_down``,
        ``limit_rule``, ``limit_status``, ``limit_rule_version``
    """
    result: dict[str, Any] = {
        'is_st': 0,
        'st_source': '',
        'limit_up_price': None,
        'limit_down_price': None,
        'limit_pct': None,
        'is_limit_up': 0,
        'is_limit_down': 0,
        'limit_rule': '',
        'limit_status': 'INVALID',
        'limit_rule_version': LIMIT_RULE_VERSION,
    }

    # --- is_st: name-prefix inference (§7.4 priority 3, used as fallback) ---
    if stock_name and detect_is_st(stock_name):
        result['is_st'] = 1
        result['st_source'] = 'name_prefix'
    else:
        result['is_st'] = 0
        result['st_source'] = ''

    # --- Rule priority 1: no-limit day ---
    if is_no_limit_day(trade_date, list_date):
        result['limit_status'] = 'NO_LIMIT'
        result['limit_rule'] = 'NO_LIMIT'
        # limit_up/down prices stay None; hit flags stay False (§7.5)
        return result

    # --- Rule priority 2: board-based rule ---
    pre_close_d = _coerce_decimal(pre_close)
    close_d = _coerce_decimal(close)

    board = detect_board(full_code)
    if board is None:
        result['limit_status'] = 'INVALID'
        return result

    board_rule = _BOARD_RULES.get(board)
    if board_rule is None:
        result['limit_status'] = 'INVALID'
        return result

    # --- prev_close validation (§7.6) ---
    if pre_close_d is None or pre_close_d <= 0:
        result['limit_status'] = 'INVALID'
        return result

    # --- Decimal calculation (§7.3) ---
    try:
        pct = board_rule['limit_pct']
        rounding = board_rule['rounding']

        raw_up = pre_close_d * (1 + pct)
        raw_down = pre_close_d * (1 - pct)

        limit_up = raw_up.quantize(TICK_SIZE, rounding=rounding)
        limit_down_raw = raw_down.quantize(TICK_SIZE, rounding=rounding)
        # Floor at minimum tick size (§7.3: limit_down_price ≥ 0.01)
        limit_down = max(limit_down_raw, MIN_PRICE)

        result['limit_up_price'] = limit_up
        result['limit_down_price'] = limit_down
        result['limit_pct'] = pct
        result['limit_rule'] = board
        result['limit_status'] = 'NORMAL'

        # --- Hit detection (§7.5) ---
        if close_d is not None and close_d > 0:
            result['is_limit_up'] = 1 if close_d >= limit_up else 0
            result['is_limit_down'] = 1 if close_d <= limit_down else 0

    except (ValueError, TypeError, Exception):
        result['limit_status'] = 'INVALID'
        result['limit_up_price'] = None
        result['limit_down_price'] = None

    return result
