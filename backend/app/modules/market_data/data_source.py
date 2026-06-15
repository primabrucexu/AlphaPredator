"""
Mairui data source adapter.

Fetches A-share market data via Mairui and converts it into
the internal batch format used by import_market_data_batch().

Rate limiting: token bucket controlled by the Mairui JSON config.
Stock universe: fetched from Mairui remote API.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import pandas as pd
from pypinyin import Style, lazy_pinyin

from app.core.settings import settings
from app.db.sqlite import ensure_sqlite_schema
from app.modules.market_data.mairui_config import load_mairui_config
from app.repositories.stock_list_repo import StockListRepo

logger = logging.getLogger(__name__)


class UnlistedStockSkipError(RuntimeError):
    """Raised when a stock is not yet listed and should be skipped."""


# ---------------------------------------------------------------------------
# Rate limiter (token bucket, thread-safe)
# ---------------------------------------------------------------------------


class _TokenBucket:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: float | None = None
        self._updated_at: float | None = None

    def acquire(self) -> float:
        """Wait until one request token is available and return total wait seconds."""
        rate_per_minute = load_mairui_config().rate_limit_per_minute
        if rate_per_minute <= 0:
            raise ValueError('rate_limit_per_minute must be greater than 0')

        capacity = float(rate_per_minute)
        refill_per_second = capacity / 60.0
        total_wait = 0.0

        with self._lock:
            while True:
                now = time.monotonic()
                if self._tokens is None or self._updated_at is None:
                    self._tokens = capacity
                    self._updated_at = now
                else:
                    elapsed = max(0.0, now - self._updated_at)
                    self._tokens = min(capacity, self._tokens + elapsed * refill_per_second)
                    self._updated_at = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return total_wait

                missing_tokens = 1.0 - self._tokens
                wait = missing_tokens / refill_per_second
                total_wait += wait
                time.sleep(wait)


_market_data_token_bucket = _TokenBucket()


def _acquire_market_data_token() -> float:
    return _market_data_token_bucket.acquire()


def _rate_limited_call(func: Any, **kwargs: Any) -> Any:
    """Call *func* while enforcing the configured requests-per-minute limit."""
    rate_wait = _acquire_market_data_token()
    rate_limit = load_mairui_config().rate_limit_per_minute
    if rate_wait > 0:
        logger.debug(
            'Market data rate limiter waited %.3fs before %s (rate_limit=%d/min)',
            rate_wait,
            getattr(func, '__name__', str(func)),
            rate_limit,
        )
    try:
        return func(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            'Rate-limited call failed. func=%s trade_date=%s full_code=%s start_date=%s end_date=%s error=%s',
            getattr(func, '__name__', str(func)),
            kwargs.get('trade_date'),
            kwargs.get('full_code'),
            kwargs.get('start_date'),
            kwargs.get('end_date'),
            exc,
        )
        raise


def _redact_mairui_url(url: str) -> str:
    split = urllib_parse.urlsplit(url)
    path_parts = split.path.split('/')
    if path_parts and path_parts[-1]:
        path_parts[-1] = '<licence>'
    return urllib_parse.urlunsplit((split.scheme, split.netloc, '/'.join(path_parts), split.query, split.fragment))


def _mairui_http_status_message(status_code: int) -> str:
    return {
        404: 'api_error',
        503: 'request_rate_limit_exceeded',
        101: 'request_quota_exceeded',
        102: 'licence_error',
    }.get(status_code, 'http_error')


def _read_http_error_body(exc: urllib_error.HTTPError) -> str:
    try:
        body = exc.read()
    except Exception:  # noqa: BLE001
        return ''
    if not body:
        return ''
    return body.decode('utf-8', errors='replace') if isinstance(body, bytes) else str(body)


def _rate_limited_http_get(url: str) -> Any:
    rate_limit = load_mairui_config().rate_limit_per_minute
    request_start = time.monotonic()
    rate_wait = _acquire_market_data_token()
    network_start = time.monotonic()
    try:
        with urllib_request.urlopen(url, timeout=30) as response:
            payload = response.read()
            status_code = int(getattr(response, 'status', 200) or 200)
    except urllib_error.HTTPError as exc:
        finished_at = time.monotonic()
        status_code = int(exc.code)
        log = logger.warning if status_code == 503 else logger.error
        body = _read_http_error_body(exc)
        if body:
            log(
                'Mairui HTTP error endpoint=%s status_code=%d meaning=%s rate_limit=%d/min '
                'rate_wait=%.3fs network=%.3fs total=%.3fs body=%s',
                _redact_mairui_url(url),
                status_code,
                _mairui_http_status_message(status_code),
                rate_limit,
                rate_wait,
                finished_at - network_start,
                finished_at - request_start,
                body,
            )
        else:
            log(
                'Mairui HTTP error endpoint=%s status_code=%d meaning=%s rate_limit=%d/min '
                'rate_wait=%.3fs network=%.3fs total=%.3fs',
                _redact_mairui_url(url),
                status_code,
                _mairui_http_status_message(status_code),
                rate_limit,
                rate_wait,
                finished_at - network_start,
                finished_at - request_start,
            )
        raise
    finished_at = time.monotonic()
    logger.debug(
        'Mairui HTTP request endpoint=%s status_code=%d',
        _redact_mairui_url(url),
        status_code,
    )
    return payload


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _get_mairui_licence() -> str:
    return load_mairui_config().licence


def _get_market_data_source() -> str:
    configured = settings.market_data_source.strip().lower()
    if configured == 'mairui':
        return configured
    if _get_mairui_licence():
        return 'mairui'
    return 'mairui'


def _normalize_trade_date(value: str) -> str:
    text = str(value).strip().replace('/', '-').replace('.', '-')
    if not text:
        return ''
    if len(text) >= 10 and text[4] == '-' and text[7] == '-':
        return text[:10]
    digits = ''.join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f'{digits[:4]}-{digits[4:6]}-{digits[6:8]}'
    return text[:10]


def _normalize_trade_datetime(value: str) -> str:
    text = str(value).strip().replace('/', '-').replace('.', '-')
    digits = ''.join(ch for ch in text if ch.isdigit())
    if len(digits) >= 14:
        return (
            f'{digits[:4]}-{digits[4:6]}-{digits[6:8]} '
            f'{digits[8:10]}:{digits[10:12]}:{digits[12:14]}'
        )
    if len(digits) == 12:
        return f'{digits[:4]}-{digits[4:6]}-{digits[6:8]} {digits[8:10]}:{digits[10:12]}:00'
    if len(text) >= 19 and text[4] == '-' and text[7] == '-':
        return text[:19]
    date_part = _normalize_trade_date(text)
    return f'{date_part} 00:00:00' if date_part else ''


def _market_board_from_code(stock_code: str) -> str:
    digits = str(stock_code).split('.')[0].zfill(6)
    if digits.startswith('920') or digits.startswith(('8', '4')):
        return '北交所'
    if digits.startswith(('688', '689')):
        return '科创板'
    if digits.startswith(('300', '301')):
        return '创业板'
    if digits.startswith(('60', '00')):
        return '主板'
    return '主板'


def _to_cnspell(name: str) -> str:
    text = str(name or '').strip()
    if not text:
        return ''

    parts: list[str] = []
    for char in text:
        if char.isascii() and char.isalpha():
            parts.append(char.upper())
            continue

        letters = lazy_pinyin(char, style=Style.FIRST_LETTER, strict=False, errors='ignore')
        parts.extend(str(item).upper() for item in letters if str(item).isalpha())
    return ''.join(parts)


def _normalize_market_code(stock_code: str) -> str:
    code = str(stock_code).strip().upper()
    if '.' in code:
        return code
    code = code.zfill(6)
    if code.startswith('6'):
        return f'{code}.SH'
    if code.startswith(('8', '4')):
        return f'{code}.BJ'
    return f'{code}.SZ'


def _is_mairui_data_missing(payload: Any) -> bool:
    return isinstance(payload, dict) and str(payload.get('error') or '').strip() == '数据不存在'


def _raise_for_unexpected_history_payload(payload: Any, market_code: str, label: str) -> None:
    if _is_mairui_data_missing(payload):
        raise UnlistedStockSkipError(f'{market_code} has no Mairui history data (数据不存在)')
    payload_preview = repr(payload)
    raise RuntimeError(
        f'Unexpected Mairui {label} payload for {market_code}: '
        f'expected list, got {type(payload).__name__} → {payload_preview}'
    )


def _build_mairui_url(path: str, *, params: dict[str, Any] | None = None) -> str:
    url = f"{settings.mairui_base_url.rstrip('/')}/{path.lstrip('/')}"
    if params:
        query = urllib_parse.urlencode({k: v for k, v in params.items() if v not in (None, '')})
        if query:
            url = f'{url}?{query}'
    return url


def _mairui_get_json(path: str, *, params: dict[str, Any] | None = None) -> Any:
    url = _build_mairui_url(path, params=params)
    try:
        raw = _rate_limited_http_get(url)
    except urllib_error.URLError as exc:  # noqa: BLE001
        logger.error('Mairui request failed: %s', _redact_mairui_url(url))
        raise RuntimeError(f'Mairui request failed: {exc}') from exc
    try:
        return json.loads(raw.decode('utf-8'))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f'Invalid Mairui JSON response from {url}') from exc


def _mairui_rows_to_stock_list_frame(rows: list[dict[str, Any]]):
    normalized: list[dict[str, Any]] = []
    for row in rows:
        full_code = str(row.get('dm', '')).strip().upper()
        if not full_code:
            continue
        code = full_code.split('.')[0].zfill(6)
        name = str(row.get('mc', '')).strip()
        normalized.append(
            {
                'full_code': full_code,
                'code': code,
                'name': name,
                'is_st': 'ST' in name.upper(),
                'cnspell': _to_cnspell(name),
                'market': _market_board_from_code(code),
            }
        )
    return pd.DataFrame(
        normalized,
        columns=['full_code', 'code', 'name', 'is_st', 'cnspell', 'market'],
    )


def _mairui_fetch_stock_list() -> Any:
    licence = _get_mairui_licence()
    if not licence:
        raise ValueError('Mairui licence not configured. Please save it in the initialization page.')
    payload = _mairui_get_json(f'hslt/list/{licence}')
    if not isinstance(payload, list):
        raise RuntimeError('Unexpected Mairui stock list payload')
    return _mairui_rows_to_stock_list_frame([row for row in payload if isinstance(row, dict)])


def _mairui_fetch_history_rows(stock_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Fetch daily K-line data for a stock across a date range.

    Args:
        stock_code: Stock code (e.g., '000001' or '000001.SZ')
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of daily bar dicts for all dates in [start_date, end_date]
    """
    licence = _get_mairui_licence()
    if not licence:
        raise ValueError('Mairui licence not configured. Please save it in the initialization page.')
    market_code = _normalize_market_code(stock_code)

    payload = _mairui_get_json(
        f'hsstock/history/{market_code}/d/n/{licence}',
        params={'st': start_date.replace('-', ''), 'et': end_date.replace('-', '')},
    )
    if not isinstance(payload, list):
        _raise_for_unexpected_history_payload(payload, market_code, 'kline')

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        normalized_trade_date = _normalize_trade_date(str(item.get('t', '')).strip())
        close = float(item.get('c') or 0.0)
        pre_close = float(item.get('pc') or 0.0)
        change = close - pre_close if pre_close else float(item.get('c') or 0.0)
        pct_chg = round((change / pre_close * 100), 4) if pre_close else 0.0
        rows.append(
            {
                'full_code': market_code,
                'trade_date': normalized_trade_date,
                'open': float(item.get('o') or 0.0),
                'high': float(item.get('h') or 0.0),
                'low': float(item.get('l') or 0.0),
                'close': close,
                'pre_close': pre_close,
                'change': round(change, 4),
                'pct_chg': pct_chg,
                'vol': float(item.get('v') or 0.0),
                # Mairui amount 'a' is in 元; convert to 亿元 for internal contract
                'amount': round(float(item.get('a') or 0.0) / 1e8, 4),
                'is_up_limit': False,
                'is_down_limit': False,
            }
        )
    return rows


def fetch_5m_history_rows(stock_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Fetch 5-minute K-line data for one stock across a date range."""
    licence = _get_mairui_licence()
    if not licence:
        raise ValueError('Mairui licence not configured. Please save it in the initialization page.')
    market_code = _normalize_market_code(stock_code)

    payload = _mairui_get_json(
        f'hsstock/history/{market_code}/5/n/{licence}',
        params={'st': start_date.replace('-', ''), 'et': end_date.replace('-', '')},
    )
    if not isinstance(payload, list):
        _raise_for_unexpected_history_payload(payload, market_code, '5m kline')

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        close = float(item.get('c') or 0.0)
        pre_close = float(item.get('pc') or item.get('yc') or 0.0)
        change = close - pre_close if pre_close else close
        pct_chg = round(change / pre_close * 100, 4) if pre_close else 0.0
        rows.append(
            {
                'full_code': market_code,
                'trade_date': _normalize_trade_datetime(str(item.get('t', '')).strip()),
                'open': float(item.get('o') or 0.0),
                'high': float(item.get('h') or 0.0),
                'low': float(item.get('l') or 0.0),
                'close': close,
                'pre_close': pre_close,
                'change': round(change, 4),
                'pct_chg': pct_chg,
                'vol': float(item.get('v') or 0.0),
                'amount': float(item.get('a') or 0.0),
                'is_up_limit': False,
                'is_down_limit': False,
                'is_stop': False,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Stock list helpers
# ---------------------------------------------------------------------------

# Required columns in the normalized stock list frame
_REQUIRED_STOCK_LIST_COLS = {'full_code', 'code', 'name', 'is_st', 'cnspell', 'market'}

# Supported market board values
MARKET_BOARDS = ('主板', '创业板', '科创板', '北交所')


def _to_full_code(code: str) -> str:
    """Convert a 6-digit stock code to full_code (e.g. '000001' -> '000001.SZ')."""
    s = str(code).zfill(6)
    if s.startswith('6'):
        return s + '.SH'
    if s.startswith('8') or s.startswith('4'):
        return s + '.BJ'
    return s + '.SZ'



def load_stock_list(market_filters: list[str] | None = None) -> pd.DataFrame:
    """
    Load stock list from the configured remote provider and optionally filter by market board.
    """
    try:
        df = _mairui_fetch_stock_list()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f'Failed to load stock list from Mairui: {exc}') from exc

    missing = _REQUIRED_STOCK_LIST_COLS - set(df.columns)
    if missing:
        raise ValueError(f'Stock list payload is missing required columns: {missing}')

    if market_filters:
        df = df[df['market'].isin(market_filters)].copy()

    return df.reset_index(drop=True)


def load_stock_list_from_sqlite(
        market_filters: list[str] | None = None,
        *,
        sqlite_path: Any = None,
) -> pd.DataFrame:
    repo = StockListRepo(sqlite_path)
    conn = repo._connect()
    try:
        rows = conn.execute(
            '''
            SELECT full_code, code, name, is_st, cnspell, market
            FROM stock_list
            ORDER BY full_code
            '''
        ).fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(
        [dict(row) for row in rows],
        columns=['full_code', 'code', 'name', 'is_st', 'cnspell', 'market'],
    )
    if df.empty:
        return df
    if market_filters:
        df = df[df['market'].isin(market_filters)].copy()
    return df.reset_index(drop=True)


def sync_stock_list_to_sqlite(
        *,
        sqlite_path: Any = None,
        market_filters: list[str] | None = None,
        force: bool = False,
) -> pd.DataFrame:
    """Fetch stock list from Mairui and persist it into SQLite stock_list.

    If the remote provider returns an empty list the existing SQLite data is
    kept unchanged (replaces nothing) and the empty DataFrame is returned.

    *force*: when True, skip the row-count equality check and always write,
    even if the incoming count matches the stored count.  Use this when a
    task explicitly requests a fresh sync.
    """
    target_sqlite = sqlite_path or settings.sqlite_path
    ensure_sqlite_schema(target_sqlite)

    df = load_stock_list(market_filters=market_filters)

    if df.empty:
        logger.warning(
            'sync_stock_list_to_sqlite: Mairui returned 0 stocks – '
            'keeping existing stock_list data unchanged'
        )
        return df

    rows_to_insert = [
        (
            str(row['full_code']).strip(),
            str(row['code']).strip(),
            str(row['name']).strip(),
            int(bool(row.get('is_st', False))),
            str(row.get('cnspell') or '').strip().upper(),
            str(row.get('market') or '').strip(),
        )
        for _, row in df.iterrows()
    ]

    repo = StockListRepo(target_sqlite)
    existing_count = repo.count_rows()
    incoming_count = len(rows_to_insert)
    if not force and existing_count == incoming_count:
        logger.info(
            'sync_stock_list_to_sqlite: stock_list already up-to-date '
            '(%d rows), skipping write',
            existing_count,
        )
        return df

    logger.info(
        'sync_stock_list_to_sqlite: updating stock_list %d → %d rows',
        existing_count,
        incoming_count,
    )
    repo.replace_all(rows_to_insert)
    return df


def _resolve_stock_universe(
        *,
        market_filters: list[str] | None = None,
        sqlite_path: Any = None,
        use_uploaded_universe: bool = True,
) -> pd.DataFrame:
    if use_uploaded_universe:
        df = load_stock_list_from_sqlite(market_filters=market_filters, sqlite_path=sqlite_path)
        if not df.empty:
            return df
        synced_df = sync_stock_list_to_sqlite(sqlite_path=sqlite_path)
        if market_filters:
            synced_df = synced_df[synced_df['market'].isin(market_filters)].copy()
        return synced_df.reset_index(drop=True)
    return load_stock_list(market_filters=market_filters)


# ---------------------------------------------------------------------------
# Public helpers – return plain Python dicts matching the batch CSV format
# ---------------------------------------------------------------------------


def fetch_spot_snapshot(
    trade_date: str | None = None,
    *,
    market_filters: list[str] | None = None,
        sqlite_path: Any = None,
) -> list[dict[str, Any]]:
    """
    Fetch A-share snapshot data from Mairui for a given trade date.

    Loads stock list from the configured provider, optionally filtered by
    *market_filters*, then fetches that day's daily data.

    Returns a list of dicts with keys:
        stock_code, stock_name, current_price, change_amount, change_pct,
        turnover_amount_billion, turnover_rate, trade_date
    """
    effective_date = trade_date or date.today().strftime('%Y-%m-%d')
    daily_rows = fetch_daily_bars_by_date(
        effective_date,
        market_filters=market_filters,
        sqlite_path=sqlite_path,
    )
    stock_list_df = _resolve_stock_universe(
        market_filters=market_filters,
        sqlite_path=sqlite_path,
        use_uploaded_universe=True,
    )
    name_map = dict(zip(stock_list_df['full_code'], stock_list_df['name']))
    code_map = dict(zip(stock_list_df['full_code'], stock_list_df['code']))

    rows: list[dict[str, Any]] = []
    for row in daily_rows:
        close = float(row.get('close') or 0)
        if close <= 0:
            continue
        full_code = str(row['full_code'])
        rows.append({
            'stock_code': str(code_map.get(full_code, full_code.split('.')[0])).zfill(6),
            'stock_name': str(name_map.get(full_code, '')).strip(),
            'current_price': round(close, 4),
            'change_amount': round(float(row.get('change') or 0), 4),
            'change_pct': round(float(row.get('pct_chg') or 0), 4),
            'turnover_amount_billion': round(float(row.get('amount') or 0), 4),
            'turnover_rate': 0.0,
            'trade_date': effective_date,
        })

    return rows


def fetch_stock_pool(
    snapshot_rows: list[dict[str, Any]] | None = None,
    *,
    market_filters: list[str] | None = None,
        sqlite_path: Any = None,
) -> list[dict[str, Any]]:
    """
    Build a stock pool from a pre-fetched snapshot list (or fetch a new one).

    Returns a list of dicts with keys:
        stock_code, stock_name, sectors, ai_quick_summary
    """
    if snapshot_rows:
        return [
            {
                'stock_code': row['stock_code'],
                'stock_name': row['stock_name'],
                'sectors': '',
                'ai_quick_summary': '',
            }
            for row in snapshot_rows
        ]

    # Fallback for non-trading days or empty snapshot responses: use provider stock list
    stock_list_df = _resolve_stock_universe(
        market_filters=market_filters,
        sqlite_path=sqlite_path,
        use_uploaded_universe=True,
    )
    return [
        {
            'stock_code': str(row['code']).zfill(6),
            'stock_name': str(row['name']).strip(),
            'sectors': '',
            'ai_quick_summary': '',
        }
        for _, row in stock_list_df.iterrows()
    ]



def fetch_daily_bars_by_date(
    trade_date: str,
    *,
    use_uploaded_universe: bool = True,
    market_filters: list[str] | None = None,
        sqlite_path: Any = None,
) -> list[dict[str, Any]]:
    """
    Fetch daily K-line bars for the whole market for a given trade_date.

    Returns a list of dicts with keys matching the daily_bars DB schema:
        full_code, trade_date, open, high, low, close, pre_close, change, pct_chg,
        vol, amount (元/1e8 -> 亿元), is_up_limit, is_down_limit
    """
    target_date = _normalize_trade_date(trade_date)
    stock_list_df = _resolve_stock_universe(
        market_filters=market_filters,
        sqlite_path=sqlite_path,
        use_uploaded_universe=use_uploaded_universe,
    )
    if stock_list_df.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, stock in stock_list_df.iterrows():
        full_code = str(stock['full_code']).strip().upper()
        if not full_code:
            continue
        try:
            stock_rows = _mairui_fetch_history_rows(full_code, target_date, target_date)
        except Exception as exc:  # noqa: BLE001
            logger.warning('Mairui history fetch failed for %s on %s: %s', full_code, target_date, exc)
            continue
        for row in stock_rows:
            if row['trade_date'] != target_date:
                continue
            rows.append(row)
    return rows
