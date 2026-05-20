from __future__ import annotations

import io
import json
import logging
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from rapidocr import RapidOCR

from app.core.settings import settings
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.jygs.auth import get_session
from app.modules.jygs.auth_file import load_credentials_from_file, save_credentials_to_file, update_auth_check_status

logger = logging.getLogger(__name__)

_JYGS_BASE_URL = 'https://app.jiuyangongshe.com/jystock-app'
_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0'
)
_SEC_CH_UA = '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"'
_PLATFORM = '3'
_TOKEN = 'e9efd6ecfaa33e89fd1ff9b2aeef23fa'


class JygsCredentialError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(tz=ZoneInfo('Asia/Shanghai')).isoformat()


def _normalize_stock_code(raw_code: Any) -> str:
    text = str(raw_code or '').strip().lower()
    digits = ''.join(ch for ch in text if ch.isdigit())
    return digits[-6:] if digits else ''


def _connect(sqlite_path: Path | None = None) -> Any:
    """Helper to get SQLite connection."""
    target = sqlite_path or settings.sqlite_path
    return connect_sqlite(target)


def _post_json(path: str, payload: dict[str, Any], *, cookie: str, timeout: float = 20.0) -> dict[str, Any]:
    t0 = time.monotonic()
    payload_keys = sorted(payload.keys())
    logger.info('JYGS request start. path=%s timeout=%.1fs payload_keys=%s', path, timeout, payload_keys)
    timestamp_ms = str(int(time.time() * 1000))
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = Request(
        url=f'{_JYGS_BASE_URL}{path}',
        data=body,
        headers={
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Cookie': cookie,
            'DNT': '1',
            'Origin': 'https://www.jiuyangongshe.com',
            'Pragma': 'no-cache',
            'Referer': 'https://www.jiuyangongshe.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'User-Agent': _BROWSER_UA,
            'platform': _PLATFORM,
            'sec-ch-ua': _SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'timestamp': timestamp_ms,
            'token': _TOKEN,
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, 'status', None) or response.getcode()
            content_type = response.headers.get('Content-Type', '')
            raw = response.read()
            data = raw.decode('utf-8', errors='replace')
            logger.info(
                'JYGS request response. path=%s status=%s content_type=%s body_len=%d elapsed_ms=%d',
                path,
                status,
                content_type,
                len(data),
                int((time.monotonic() - t0) * 1000),
            )
            try:
                return json.loads(data)
            except json.JSONDecodeError as exc:
                logger.error(
                    'JYGS JSON decode failed. path=%s status=%s content_type=%s pos=%d line=%d col=%d body_preview=%r',
                    path,
                    status,
                    content_type,
                    exc.pos,
                    exc.lineno,
                    exc.colno,
                    data[:240],
                )
                raise
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'JYGS invalid JSON for {path}: {exc}') from exc
    except (HTTPError, URLError, TimeoutError) as exc:
        logger.error('JYGS request failed. path=%s error=%s elapsed_ms=%d', path, exc,
                     int((time.monotonic() - t0) * 1000))
        raise RuntimeError(f'JYGS request failed for {path}: {exc}') from exc


def get_jygs_auth_status(sqlite_path: Path | None = None) -> dict[str, Any]:
    """获取韭研公社认证状态。

    从 JSON 文件 (data/config/jygs_auth.json) 读取凭据和验证状态信息。
    """
    creds = load_credentials_from_file()

    if not creds or not creds.get('session'):
        return {
            'is_configured': False,
            'is_valid': False,
            'saved_at': None,
            'last_checked_at': None,
            'last_error': '',
        }

    return {
        'is_configured': True,
        'is_valid': creds.get('is_valid', False),
        'saved_at': creds.get('saved_at'),
        'last_checked_at': creds.get('last_checked_at'),
        'last_error': str(creds.get('last_error', '')),
    }


def save_jygs_auth_cookie(cookie: str, sqlite_path: Path | None = None) -> dict[str, Any]:
    """保存韭研公社认证 cookie。

    将 SESSION 认证保存到 JSON 文件 (data/config/jygs_auth.json)。
    """
    # 移除 "SESSION=" 前缀如果存在
    session = cookie.removeprefix('SESSION=').strip()

    try:
        save_credentials_to_file(session)
        logger.info('JYGS auth cookie saved to JSON file.')
        return get_jygs_auth_status(sqlite_path)
    except Exception as exc:
        logger.error('Failed to save JYGS auth cookie: %s', exc)
        return {
            'is_configured': False,
            'is_valid': False,
            'saved_at': None,
            'last_error': str(exc),
        }


def _read_cookie(sqlite_path: Path | None = None) -> str:
    """Read auth cookie from SESSION storage."""
    session = get_session()
    if session:
        return f'SESSION={session}'
    raise JygsCredentialError('韭研公社登录凭据未配置，请先在数据初始化页面完成登录。')


def check_jygs_auth_available(sqlite_path: Path | None = None) -> dict[str, Any]:
    """检查韭研公社认证是否有效。

    调用 API 验证 SESSION，结果保存到 JSON 文件。
    """
    now = _now_iso()
    try:
        cookie = _read_cookie(sqlite_path)
        trade_date = datetime.now(tz=ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
        payload = _post_json('/api/v1/action/diagram-url', {'date': trade_date}, cookie=cookie)
        err_code = str(payload.get('errCode', ''))
        is_valid = err_code == '0'
        message = '' if is_valid else f'errCode={err_code}'
    except Exception as exc:  # noqa: BLE001
        is_valid = False
        message = str(exc)

    # 更新认证状态到 JSON 文件
    update_auth_check_status(is_valid, message)

    result = get_jygs_auth_status(sqlite_path)
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


def _extract_diagram_urls(diagram_payload: dict[str, Any]) -> list[str]:
    raw_data = diagram_payload.get('data')
    if isinstance(raw_data, str):
        value = raw_data.strip()
        return [value] if value else []
    if isinstance(raw_data, list):
        return [str(item).strip() for item in raw_data if str(item).strip()]
    return []


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
                code,  # stock_code as TEXT (6-digit string, e.g. '000711')
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
        rows.append((trade_date, '', code, '', '', '、'.join(sorted(themes)), '', 'jygs'))
    return rows


def sync_hot_review_by_date(trade_date: str, sqlite_path: Path | None = None) -> dict[str, Any]:
    """Fetch JYGS review data for a date and write to daily_hot_pic/daily_hot_info per data-storage.md spec."""
    target = sqlite_path or settings.sqlite_path
    ensure_sqlite_schema(target)
    logger.info('JYGS sync start. trade_date=%s sqlite=%s', trade_date, target)
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

    summary_image_urls = _extract_diagram_urls(diagram_payload)
    theme_map = _extract_theme_stock_map(field_payload)

    # Merge stock rows from list API and theme mapping
    stock_rows_by_code: dict[str, dict[str, Any]] = {}
    for stock in list_payload.get('data') or []:
        code = _normalize_stock_code(stock.get('code'))
        if not code:
            continue
        stock_rows_by_code[code] = stock
    for code in theme_map:
        stock_rows_by_code.setdefault(code, {})

    # Write to daily_hot_pic table (復盤圖片)
    connection = _connect(target)
    try:
        for idx, url in enumerate(summary_image_urls):
            connection.execute(
                'DELETE FROM daily_hot_pic WHERE trade_date = ? AND summary_image_url = ?',
                [trade_date, url],
            )
            connection.execute(
                'INSERT INTO daily_hot_pic (trade_date, summary_image_url, source) VALUES (?, ?, ?)',
                [trade_date, url, 'jygs'],
            )

        # Write to daily_hot_info table (涨停解析)
        connection.execute('DELETE FROM daily_hot_info WHERE trade_date = ?', [trade_date])
        for code, stock in stock_rows_by_code.items():
            article = stock.get('article') or {}
            action_info = article.get('action_info') or {}
            stock_name = str(stock.get('name') or '').strip()
            streak_text = str(action_info.get('num') or '').strip()
            reason_raw = str(action_info.get('expound') or '').strip()
            limit_up_time = str(action_info.get('time') or '').strip()
            hot_theme = '、'.join(sorted(theme_map.get(code, set())))

            connection.execute(
                '''
                INSERT INTO daily_hot_info (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason,
                                            source, short_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                [
                    trade_date,
                    limit_up_time,
                    code,  # stock_code as TEXT (6-digit string, e.g. '000711')
                    stock_name,
                    streak_text,
                    hot_theme,
                    reason_raw,
                    'jygs',
                    '',  # short_reason: placeholder, populated by OCR in a future phase
                ],
            )

        connection.commit()
    finally:
        connection.close()

    logger.info(
        'JYGS sync done. trade_date=%s images=%d stocks=%d',
        trade_date,
        len(summary_image_urls),
        len(stock_rows_by_code),
    )

    return {
        'trade_date': trade_date,
        'image_saved': bool(summary_image_urls),
        'stock_fact_count': len(stock_rows_by_code),
        'images': len(summary_image_urls),
    }





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

    This function:
    1. Syncs hot review data (stocks, themes, images) from JYGS API
    2. Runs OCR on downloaded images to extract text for short_reason field

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
    stock_fact_count = int(result.get('stock_fact_count', 0))

    # Run OCR processing after sync completes
    logger.info('Starting OCR processing for JYGS images. trade_date=%s', normalized_date)
    ocr_result = _process_hot_review_ocr(normalized_date)
    logger.info('OCR processing completed. result=%s', ocr_result)

    return stock_fact_count


def _download_image_data(image_url: str, timeout: float = 10.0) -> bytes | None:
    """Download image from URL to memory. Returns None if download fails."""
    try:
        t0 = time.monotonic()
        logger.debug('Downloading image from %s', image_url)
        request = Request(image_url, headers={'User-Agent': _BROWSER_UA})
        with urlopen(request, timeout=timeout) as response:
            data = response.read()
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.debug('Downloaded image. size=%d bytes elapsed_ms=%d', len(data), elapsed_ms)
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning('Failed to download image from %s: %s', image_url, exc)
        return None


def _ocr_image_to_text(image_data: bytes) -> str:
    """Run OCR on image bytes and extract text. Returns concatenated text or empty string if OCR fails."""
    try:
        t0 = time.monotonic()
        ocr_engine = RapidOCR()
        image_stream = io.BytesIO(image_data)
        img = Image.open(image_stream)

        # RapidOCR returns (results, elapsed_time) tuple
        # results is a list of [bbox, text, confidence] or None if no text detected
        ocr_result = ocr_engine(img)

        # Handle different return formats from RapidOCR
        if isinstance(ocr_result, tuple):
            result, elapsed = ocr_result
        else:
            result = ocr_result
            elapsed = 0

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if not result:
            logger.debug('OCR returned empty result. elapsed_ms=%d', elapsed_ms)
            return ''

        # Concatenate all recognized text lines
        text_lines = []
        for item in result:
            if item and len(item) > 1:
                # item format: [bbox, text, confidence]
                text = str(item[1] or '')
                if text:
                    text_lines.append(text)

        full_text = ''.join(text_lines)
        logger.debug('OCR extracted %d lines, total %d chars. elapsed_ms=%d', len(text_lines), len(full_text),
                     elapsed_ms)

        return full_text
    except Exception as exc:  # noqa: BLE001
        logger.warning('OCR processing failed: %s', exc)
        logger.debug('OCR traceback: %s', traceback.format_exc())
        return ''


def _process_hot_review_ocr(trade_date: str, sqlite_path: Path | None = None) -> dict[str, Any]:
    """Process all images for a trade_date via OCR and update daily_hot_info.short_reason.

    Returns a dict with OCR processing statistics.
    """
    target = sqlite_path or settings.sqlite_path
    logger.info('OCR processing start. trade_date=%s', trade_date)

    connection = _connect(target)
    try:
        # Fetch all images for this trade_date
        cursor = connection.execute(
            'SELECT summary_image_url FROM daily_hot_pic WHERE trade_date = ? ORDER BY summary_image_url',
            [trade_date]
        )
        image_urls = [row[0] for row in cursor.fetchall()]

        if not image_urls:
            logger.info('No images to process for %s', trade_date)
            return {'trade_date': trade_date, 'images_processed': 0, 'ocr_success': 0}

        ocr_success_count = 0

        for idx, image_url in enumerate(image_urls, 1):
            logger.info('Processing image %d/%d: %s', idx, len(image_urls), image_url[:80])

            # Download image to memory
            image_data = _download_image_data(image_url)
            if not image_data:
                logger.warning('Skipped image %d due to download failure', idx)
                continue

            # Run OCR
            ocr_text = _ocr_image_to_text(image_data)
            if not ocr_text:
                logger.warning('Skipped image %d due to empty OCR result', idx)
                continue

            # Truncate to 500 chars (reasonable limit for short_reason field)
            short_reason = ocr_text[:500]

            # Update all daily_hot_info rows for this date with the OCR result
            # (all rows share the same set of daily_hot_pic, so they should all get the same short_reason)
            connection.execute(
                'UPDATE daily_hot_info SET short_reason = ? WHERE trade_date = ? AND short_reason = ?',
                [short_reason, trade_date, '']
            )
            logger.info('Updated short_reason for trade_date=%s with OCR result (len=%d)', trade_date,
                        len(short_reason))
            ocr_success_count += 1
            break  # Only process the first successful image per day (复盤圖片 usually contains full summary)

        connection.commit()
    finally:
        connection.close()

    logger.info('OCR processing done. trade_date=%s images_processed=%d ocr_success=%d',
                trade_date, len(image_urls), ocr_success_count)

    return {
        'trade_date': trade_date,
        'images_processed': len(image_urls),
        'ocr_success': ocr_success_count,
    }
