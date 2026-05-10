from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from zoneinfo import ZoneInfo

from app.core.settings import settings
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema

logger = logging.getLogger(__name__)

_JYGS_BASE_URL = 'https://www.jiuyangongshe.com/action'


class JygsCredentialError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(tz=ZoneInfo('Asia/Shanghai')).isoformat()


def _normalize_stock_code(raw_code: Any) -> str:
    text = str(raw_code or '').strip().lower()
    digits = ''.join(ch for ch in text if ch.isdigit())
    return digits[-6:] if digits else ''


def _post_json(path: str, payload: dict[str, Any], *, cookie: str, timeout: float = 20.0) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = Request(
        url=f'{_JYGS_BASE_URL}{path}',
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Cookie': cookie,
            'User-Agent': 'AlphaPredator/1.0',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read().decode('utf-8')
            return json.loads(data)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f'JYGS request failed for {path}: {exc}') from exc


def get_jygs_auth_status(sqlite_path: Path | None = None) -> dict[str, Any]:
    target = sqlite_path or settings.sqlite_path
    ensure_sqlite_schema(target)
    connection = connect_sqlite(target)
    try:
        row = connection.execute(
            'SELECT auth_cookie, updated_at, last_checked_at, is_valid, last_error FROM jygs_auth WHERE id = 1'
        ).fetchone()
    finally:
        connection.close()

    if not row:
        return {
            'is_configured': False,
            'is_valid': False,
            'updated_at': None,
            'last_checked_at': None,
            'last_error': '',
        }

    cookie = str(row['auth_cookie'] or '').strip()
    return {
        'is_configured': bool(cookie),
        'is_valid': bool(row['is_valid']) and bool(cookie),
        'updated_at': str(row['updated_at'] or '') or None,
        'last_checked_at': str(row['last_checked_at'] or '') or None,
        'last_error': str(row['last_error'] or ''),
    }


def save_jygs_auth_cookie(cookie: str, sqlite_path: Path | None = None) -> dict[str, Any]:
    target = sqlite_path or settings.sqlite_path
    ensure_sqlite_schema(target)
    now = _now_iso()
    connection = connect_sqlite(target)
    try:
        connection.execute(
            '''
            INSERT INTO jygs_auth (id, auth_cookie, updated_at, last_checked_at, is_valid, last_error)
            VALUES (1, ?, ?, '', 0, '')
            ON CONFLICT(id) DO UPDATE SET
                auth_cookie = excluded.auth_cookie,
                updated_at = excluded.updated_at,
                is_valid = 0,
                last_error = ''
            ''',
            [cookie.strip(), now],
        )
        connection.commit()
    finally:
        connection.close()
    return get_jygs_auth_status(target)


def _read_cookie(sqlite_path: Path | None = None) -> str:
    """Read auth cookie, preferring the new file-based SESSION storage."""
    from app.modules.jygs.auth import get_session

    session = get_session()
    if session:
        return f'SESSION={session}'

    # Legacy fallback (older table-based auth storage), kept for compatibility.
    target = sqlite_path or settings.sqlite_path
    ensure_sqlite_schema(target)
    connection = connect_sqlite(target)
    try:
        row = connection.execute(
            'SELECT auth_cookie FROM jygs_auth WHERE id = 1'
        ).fetchone()
    finally:
        connection.close()
    cookie = str(row['auth_cookie'] or '').strip() if row else ''
    if not cookie:
        raise JygsCredentialError('韭研公社登录凭据未配置，请先在数据初始化页面完成登录。')
    return cookie


def check_jygs_auth_available(sqlite_path: Path | None = None) -> dict[str, Any]:
    target = sqlite_path or settings.sqlite_path
    now = _now_iso()
    try:
        cookie = _read_cookie(target)
        trade_date = datetime.now(tz=ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
        payload = _post_json('/api/v1/action/diagram-url', {'date': trade_date}, cookie=cookie)
        err_code = str(payload.get('errCode', ''))
        is_valid = err_code == '0'
        message = '' if is_valid else f'errCode={err_code}'
    except Exception as exc:  # noqa: BLE001
        is_valid = False
        message = str(exc)

    ensure_sqlite_schema(target)
    connection = connect_sqlite(target)
    try:
        connection.execute(
            '''
            INSERT INTO jygs_auth (id, auth_cookie, updated_at, last_checked_at, is_valid, last_error)
            VALUES (1, '', '', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_checked_at = excluded.last_checked_at,
                is_valid = excluded.is_valid,
                last_error = excluded.last_error
            ''',
            [now, 1 if is_valid else 0, message],
        )
        connection.commit()
    finally:
        connection.close()

    result = get_jygs_auth_status(target)
    result['last_error'] = message
    result['is_valid'] = is_valid and result['is_configured']
    return result


def _extract_theme_stock_map(field_payload: dict[str, Any]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for category in field_payload.get('data') or []:
        theme = str(category.get('name') or '').strip()
        if not theme:
            continue
        for stock in category.get('list') or []:
            code = _normalize_stock_code(stock.get('code'))
            if not code:
                continue
            mapping.setdefault(code, set()).add(theme)
    return mapping


def _extract_hot_info_rows(
    trade_date: str,
    list_payload: dict[str, Any],
    theme_map: dict[str, set[str]],
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    seen: set[str] = set()
    for stock in list_payload.get('data') or []:
        code = _normalize_stock_code(stock.get('code'))
        if not code:
            continue
        seen.add(code)
        article = stock.get('article') or {}
        action_info = article.get('action_info') or {}
        rows.append(
            (
                trade_date,
                str(action_info.get('time') or ''),
                int(code),
                str(stock.get('name') or ''),
                str(action_info.get('num') or ''),
                '、'.join(sorted(theme_map.get(code, set()))),
                str(action_info.get('expound') or ''),
                'jygs',
            )
        )

    for code, themes in theme_map.items():
        if code in seen:
            continue
        rows.append((trade_date, '', int(code), '', '', '、'.join(sorted(themes)), '', 'jygs'))
    return rows


def sync_hot_review_by_date(trade_date: str, sqlite_path: Path | None = None) -> dict[str, Any]:
    """Fetch JYGS review data for a date and write unified hot_sector_* tables."""
    from app.modules.market_data.hot_sector_importer import (
        ParsedImage,
        ParsedStockFact,
        SectorMappingRecord,
        _build_daily_aggregates,
        _build_recent_3d_records,
        _write_sqlite_data,
    )

    target = sqlite_path or settings.sqlite_path
    ensure_sqlite_schema(target)
    cookie = _read_cookie(target)

    diagram_payload = _post_json('/api/v1/action/diagram-url', {'date': trade_date}, cookie=cookie)
    field_payload = _post_json('/api/v1/action/field', {'date': trade_date, 'pc': 1}, cookie=cookie)
    list_payload = _post_json(
        '/api/v1/action/list',
        {
            'action_field_id': f'recommend,{trade_date}',
            'pc': 1,
            'start': 1,
            'limit': 200,
            'sort_price': 0,
            'sort_range': 0,
            'sort_time': 0,
        },
        cookie=cookie,
    )

    summary_image_url = str(diagram_payload.get('data') or '').strip()
    theme_map = _extract_theme_stock_map(field_payload)

    # Merge stock rows from list API and theme mapping.
    stock_rows_by_code: dict[str, dict[str, Any]] = {}
    for stock in list_payload.get('data') or []:
        code = _normalize_stock_code(stock.get('code'))
        if not code:
            continue
        stock_rows_by_code[code] = stock
    for code in theme_map:
        stock_rows_by_code.setdefault(code, {})

    source_file = f'jygs_api_{trade_date}'
    stock_facts: list[ParsedStockFact] = []
    mappings: list[SectorMappingRecord] = []

    for code, stock in stock_rows_by_code.items():
        article = stock.get('article') or {}
        action_info = article.get('action_info') or {}
        stock_name = str(stock.get('name') or '').strip()
        streak_text = str(action_info.get('num') or '').strip()
        reason_raw = str(action_info.get('expound') or '').strip()
        limit_up_time = str(action_info.get('time') or '').strip()

        board_match = re.search(r'(\d+)板', streak_text)
        board_count = int(board_match.group(1)) if board_match else None

        sectors = sorted(theme_map.get(code, set()))
        primary_sector = sectors[0] if sectors else '其他'

        stock_facts.append(
            ParsedStockFact(
                trade_date=trade_date,
                source_file=source_file,
                stock_code=code,
                stock_name=stock_name,
                board_count=board_count,
                limit_up_time=limit_up_time,
                reason_raw=reason_raw,
                reason_clean=reason_raw,
                ocr_confidence=1.0,
                needs_review=False,
                primary_sector_name=primary_sector,
                primary_sector_alias_hit=primary_sector,
                primary_sector_order=1,
                primary_sector_declared_count=max(1, len(sectors)),
            )
        )

        sector_list = sectors or [primary_sector]
        for idx, sector_name in enumerate(sector_list):
            mappings.append(
                SectorMappingRecord(
                    trade_date=trade_date,
                    source_file=source_file,
                    stock_code=code,
                    sector_name_canonical=sector_name,
                    sector_alias_hit=sector_name,
                    is_primary_sector=(idx == 0),
                    mapping_method='api_theme',
                    mapping_confidence=1.0,
                    needs_review=False,
                )
            )

    parsed_image = ParsedImage(
        trade_date=trade_date,
        source_file=source_file,
        parse_status='parsed',
        parse_notes=(
            f'from_api=1, summary_image={1 if summary_image_url else 0}, '
            f'parsed_stocks={len(stock_facts)}'
        ),
        stock_facts=stock_facts,
        mappings=mappings,
    )

    daily_aggregates = _build_daily_aggregates([parsed_image])
    recent_3d_records = _build_recent_3d_records(daily_aggregates)
    _write_sqlite_data(
        sqlite_path=target,
        import_batch=f'jygs-api-{trade_date}',
        parsed_images=[parsed_image],
        daily_aggregates=daily_aggregates,
        recent_3d_records=recent_3d_records,
    )

    return {
        'trade_date': trade_date,
        'image_saved': bool(summary_image_url),
        'stock_fact_count': len(stock_facts),
        'sector_mapping_count': len(mappings),
        'daily_sector_count': len(daily_aggregates),
    }


def sync_hot_review_now(sqlite_path: Path | None = None) -> dict[str, Any]:
    trade_date = datetime.now(tz=ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
    return sync_hot_review_by_date(trade_date, sqlite_path=sqlite_path)


def run_incremental_sync_if_due(sqlite_path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(tz=ZoneInfo('Asia/Shanghai'))
    current_slot: str | None = None
    if current.hour == 12 and current.minute == 2:
        current_slot = '12:02'
    elif current.hour == 15 and current.minute == 32:
        current_slot = '15:32'

    if not current_slot:
        return {'triggered': False, 'reason': 'not_in_schedule_window'}

    trade_date = current.strftime('%Y-%m-%d')
    slot_key = f'{trade_date}@{current_slot}'
    target = sqlite_path or settings.sqlite_path
    ensure_sqlite_schema(target)

    connection = connect_sqlite(target)
    try:
        existing = connection.execute(
            'SELECT slot_key FROM jygs_sync_log WHERE slot_key = ?',
            [slot_key],
        ).fetchone()
        if existing:
            return {'triggered': False, 'reason': 'slot_already_synced', 'slot_key': slot_key}
    finally:
        connection.close()

    try:
        result = sync_hot_review_by_date(trade_date, sqlite_path=target)
        status = 'SUCCESS'
        message = ''
    except Exception as exc:  # noqa: BLE001
        result = {'trade_date': trade_date, 'error': str(exc)}
        status = 'FAILED'
        message = str(exc)
        logger.warning('JYGS incremental sync failed: %s', exc)

    connection = connect_sqlite(target)
    try:
        connection.execute(
            '''
            INSERT OR REPLACE INTO jygs_sync_log (slot_key, trade_date, mode, status, message, triggered_at)
            VALUES (?, ?, 'INCREMENTAL', ?, ?, ?)
            ''',
            [slot_key, trade_date, status, message, _now_iso()],
        )
        connection.commit()
    finally:
        connection.close()

    return {'triggered': True, 'slot_key': slot_key, 'status': status, 'result': result}


def auto_login_jygs_with_browser(sqlite_path: Path | None = None, timeout_seconds: int = 300) -> dict[str, Any]:
    """
    启动浏览器打开韭研公社登录页面，等待用户完成登录，然后自动捕获 Cookie 保存到数据库。

    Args:
        sqlite_path: SQLite 数据库路径，默认使用配置中的路径
        timeout_seconds: 等待登录的超时时间（秒），默认 5 分钟

    Returns:
        包含登录结果和保存状态的字典

    Raises:
        RuntimeError: 浏览器操作或登录失败时抛出
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    target = sqlite_path or settings.sqlite_path
    login_url = f'{_JYGS_BASE_URL}/'

    logger.info('Starting auto login for JYGS at %s', login_url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(login_url, wait_until='domcontentloaded')
            logger.info('Waiting for user to login (timeout: %d seconds)...', timeout_seconds)

            deadline = datetime.now(tz=ZoneInfo('Asia/Shanghai')).timestamp() + timeout_seconds
            auth_cookies: list[Any] = []
            while datetime.now(tz=ZoneInfo('Asia/Shanghai')).timestamp() < deadline:
                cookies = context.cookies('https://www.jiuyangongshe.com')
                auth_cookies = [
                    cookie for cookie in cookies
                    if cookie.get('name') and cookie.get('value') and 'jiuyangongshe.com' in str(cookie.get('domain', ''))
                ]
                if auth_cookies:
                    break
                page.wait_for_timeout(1500)

            if not auth_cookies:
                raise RuntimeError('登录超时或未检测到韭研登录态，请确认已完成登录后重试。')

            cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in auth_cookies)
            logger.info('Extracted %d JYGS cookies from browser', len(auth_cookies))

            save_jygs_auth_cookie(cookie_str, sqlite_path=target)
            result = check_jygs_auth_available(sqlite_path=target)
            if not result.get('is_valid'):
                raise RuntimeError(f"已捕获 Cookie 但校验失败：{result.get('last_error') or '未知错误'}")
            return {
                'success': True,
                'message': '登录成功，凭据已保存',
                'cookie_count': len(auth_cookies),
                'auth_status': result,
            }
        except PlaywrightTimeoutError as exc:
            logger.exception('Auto login timed out')
            raise RuntimeError('自动登录等待超时，请重新点击一键登录并在超时前完成登录。') from exc
        except Exception as exc:
            logger.exception('Auto login failed')
            raise RuntimeError(f'自动登录失败: {exc}') from exc
        finally:
            browser.close()


def fetch_and_parse_jygs_review_for_date(trade_date: str) -> int:
    """Fetch and parse JYGS review data for a single trading date.

    Args:
        trade_date: Date in YYYYMMDD or YYYY-MM-DD format

    Returns:
        Number of stock facts processed for that date
    """
    # Normalize task date format.
    if re.fullmatch(r'\d{8}', trade_date):
        normalized_date = f'{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}'
    else:
        normalized_date = trade_date

    logger.info('Fetching JYGS review data for %s', normalized_date)
    result = sync_hot_review_by_date(normalized_date)
    return int(result.get('stock_fact_count', 0))
