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

import numpy as np
from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from rapidocr import RapidOCR
from sqlmodel import select

from app.core.settings import settings
from app.db.session import get_sqlite_session_factory
from app.db.sqlite import ensure_sqlite_schema
from app.models.sqlite_models import DailyHotInfo, DailyHotPic, StockList
from app.modules.jygs.auth import get_session
from app.modules.jygs.auth_file import load_credentials_from_file, save_credentials_to_file, update_auth_check_status
from app.modules.jygs.playwright_browser import launch_installed_browser
from app.modules.jygs.request_headers import build_jygs_headers

logger = logging.getLogger(__name__)

_JYGS_BASE_URL = 'https://app.jiuyangongshe.com/jystock-app'
_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0'
)


class JygsCredentialError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(tz=ZoneInfo('Asia/Shanghai')).isoformat()


def _normalize_stock_code(raw_code: Any) -> str:
    text = str(raw_code or '').strip().lower()
    digits = ''.join(ch for ch in text if ch.isdigit())
    return digits[-6:] if digits else ''


def _session_factory(sqlite_path: Path | None = None):
    target = sqlite_path or settings.sqlite_path
    return get_sqlite_session_factory(target)


def _post_json(path: str, payload: dict[str, Any], *, cookie: str = '', timeout: float = 20.0) -> dict[str, Any]:
    t0 = time.monotonic()
    payload_keys = sorted(payload.keys())
    logger.info('JYGS request start. path=%s timeout=%.1fs payload_keys=%s', path, timeout, payload_keys)
    session = cookie.removeprefix('SESSION=').strip() if cookie else None
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = Request(
        url=f'{_JYGS_BASE_URL}{path}',
        data=body,
        headers=build_jygs_headers(session=session),
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
        msg = str(payload.get('msg', '')).strip()
        message = '' if is_valid else f'errCode={err_code} {msg}'.strip()
    except Exception as exc:  # noqa: BLE001
        is_valid = False
        message = str(exc)

    # 更新认证状态到 JSON 文件
    update_auth_check_status(is_valid, message)

    result = get_jygs_auth_status(sqlite_path)
    result['last_error'] = message
    result['is_valid'] = is_valid and result['is_configured']
    return result


def _extract_theme_stock_map(
    field_payload: dict[str, Any],
) -> tuple[dict[str, set[str]], dict[str, dict[str, Any]]]:
    """从 /action/field 响应提取题材映射和完整股票数据。

    /action/field 和 /action/list 共用同一 StockItem 结构，
    field 里每个 category.list 已包含 article.action_info（time/num/expound）。

    Returns:
        theme_map:        code → set of theme names
        stock_data_map:   code → 完整 StockItem dict（含 name, article.action_info）
    """
    theme_map: dict[str, set[str]] = {}
    stock_data_map: dict[str, dict[str, Any]] = {}
    for category in field_payload.get('data') or []:
        theme = str(category.get('name') or '').strip()
        if not theme:
            continue
        for stock in category.get('list') or []:
            code = _normalize_stock_code(stock.get('code'))
            if not code:
                continue
            theme_map.setdefault(code, set()).add(theme)
            # 保留第一次遇到的完整 StockItem（含 article.action_info）
            if code not in stock_data_map:
                stock_data_map[code] = stock
    return theme_map, stock_data_map


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

    summary_image_urls = _extract_diagram_urls(diagram_payload)
    theme_map, stock_rows_by_code = _extract_theme_stock_map(field_payload)

    session_factory = _session_factory(target)
    with session_factory() as session:
        # Write to daily_hot_pic table (復盤圖片)
        for idx, url in enumerate(summary_image_urls):
            existing_pic = session.exec(
                select(DailyHotPic).where(
                    DailyHotPic.trade_date == trade_date,
                    DailyHotPic.summary_image_url == url,
                )
            ).first()
            if existing_pic:
                session.delete(existing_pic)
            session.add(
                DailyHotPic(
                    trade_date=trade_date,
                    summary_image_url=url,
                    source='jygs',
                )
            )

        # Write to daily_hot_info table (涨停解析)
        existing_infos = session.exec(
            select(DailyHotInfo).where(DailyHotInfo.trade_date == trade_date)
        ).all()
        for info in existing_infos:
            session.delete(info)
        for code, stock in stock_rows_by_code.items():
            article = stock.get('article') or {}
            action_info = article.get('action_info') or {}
            # field API 和 list API 共用 StockItem 结构，name/action_info 均来自同一路径
            stock_name = str(stock.get('name') or '').strip()
            streak_text = str(action_info.get('num') or '').strip()
            reason_raw = str(action_info.get('expound') or '').strip()
            limit_up_time = str(action_info.get('time') or '').strip()
            hot_theme = '、'.join(sorted(theme_map.get(code, set())))

            session.add(
                DailyHotInfo(
                    trade_date=trade_date,
                    limit_up_time=limit_up_time,
                    stock_code=code,
                    name=stock_name,
                    streak_text=streak_text,
                    hot_theme=hot_theme,
                    reason=reason_raw,
                    source='jygs',
                    short_reason='',
                )
            )

        # name 仍为空时从 stock_list 保底（field 某些 category 不返回 list，导致 stock_data_map 无此股）
        empty_name_infos = session.exec(
            select(DailyHotInfo).where(
                DailyHotInfo.trade_date == trade_date,
                DailyHotInfo.name == '',
            )
        ).all()
        for info in empty_name_infos:
            stock = session.exec(
                select(StockList).where(StockList.code == info.stock_code).limit(1)
            ).first()
            if stock:
                info.name = stock.name
                session.add(info)

        session.commit()

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
        browser = launch_installed_browser(p.chromium, headless=False)
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


def _parse_ocr_stock_summaries(image_data: bytes) -> dict[str, str]:
    """从复盘简图中按行解析每只股票的涨停关键词（short_reason）。

    图片为表格格式，每行包含：股票代码、涨停时间、涨停关键词，如：
      "002552.SZ  09:25:00  HVLP铜箔+业绩预增+河西金矿+互联网金融"

    使用 bounding box 的 Y 坐标将文本块聚类成行，
    在包含股票代码（6位数字）的行中，取最右侧有意义的非时间/非代码文本作为关键词。

    注意：涨停时间（limit_up_time）从 /action/field API 的 time 字段获取，不在此处解析。

    Returns:
        {6位股票代码: 涨停关键词}，无法解析时返回空 dict。
    """
    _STOCK_CODE_PAT = re.compile(r'(\d{6})[.\s]?[A-Za-z0-9]{2}')
    _SKIP_PAT = re.compile(r'^[\d:\.\-/;]+$')  # 纯数字/时间/分隔符
    Y_THRESHOLD = 20  # 同行 Y 偏差像素阈值

    try:
        t0 = time.monotonic()
        ocr_engine = RapidOCR()
        img = Image.open(io.BytesIO(image_data))
        result = ocr_engine(img)

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if not hasattr(result, 'txts') or not result.txts or not hasattr(result, 'boxes'):
            logger.debug('OCR returned no structured result. elapsed_ms=%d', elapsed_ms)
            return {}

        txts = result.txts
        boxes = result.boxes

        # 构建 (text, center_y, center_x) 列表
        items = [
            {
                'txt': str(txt),
                'y': float(np.mean(boxes[i][:, 1])),
                'x': float(np.mean(boxes[i][:, 0])),
            }
            for i, txt in enumerate(txts)
        ]
        items.sort(key=lambda x: x['y'])

        # 按行聚类
        rows: list[list[dict]] = []
        cur: list[dict] = [items[0]] if items else []
        for item in items[1:]:
            if abs(item['y'] - cur[-1]['y']) <= Y_THRESHOLD:
                cur.append(item)
            else:
                if cur:
                    rows.append(sorted(cur, key=lambda x: x['x']))
                cur = [item]
        if cur:
            rows.append(sorted(cur, key=lambda x: x['x']))

        # 从每行提取股票代码和最右侧关键词
        stock_summaries: dict[str, str] = {}
        for row in rows:
            row_texts = [item['txt'] for item in row]

            # 找股票代码（取第一个匹配）
            stock_code = None
            for txt in row_texts:
                m = _STOCK_CODE_PAT.search(txt)
                if m:
                    stock_code = m.group(1)
                    break
            if not stock_code:
                continue

            # 从右往左找第一个有意义的文本作为关键词
            row_summary = ''
            for item in reversed(row):
                t = item['txt'].strip()
                if not t or len(t) <= 2:
                    continue
                if _SKIP_PAT.match(t):  # 纯数字/时间
                    continue
                if _STOCK_CODE_PAT.search(t):  # 股票代码本身
                    continue
                row_summary = t
                break

            if row_summary:
                stock_summaries[stock_code] = row_summary

        logger.debug(
            'OCR parsed %d stock summaries from image. elapsed_ms=%d',
            len(stock_summaries), elapsed_ms,
        )
        return stock_summaries

    except Exception as exc:  # noqa: BLE001
        logger.warning('OCR stock summary parsing failed: %s', exc)
        logger.debug('OCR traceback: %s', traceback.format_exc())
        return {}


def _process_hot_review_ocr(trade_date: str, sqlite_path: Path | None = None) -> dict[str, Any]:
    """Process all images for a trade_date via OCR and update daily_hot_info.short_reason.

    每只股票的 short_reason 存储其在图片对应行的涨停关键词（最右列），
    而非整张图片的 OCR 文本。

    Returns a dict with OCR processing statistics.
    """
    target = sqlite_path or settings.sqlite_path
    logger.info('OCR processing start. trade_date=%s', trade_date)

    session_factory = _session_factory(target)
    with session_factory() as session:
        pics = session.exec(
            select(DailyHotPic)
            .where(DailyHotPic.trade_date == trade_date)
            .order_by(DailyHotPic.summary_image_url)
        )
        image_urls = [pic.summary_image_url for pic in pics]

        if not image_urls:
            logger.info('No images to process for %s', trade_date)
            return {'trade_date': trade_date, 'images_processed': 0, 'ocr_success': 0}

        # 合并所有图片的解析结果（通常只有一张图）
        merged: dict[str, str] = {}
        ocr_success_count = 0
        for idx, image_url in enumerate(image_urls, 1):
            logger.info('Processing image %d/%d: %s', idx, len(image_urls), image_url[:80])
            image_data = _download_image_data(image_url)
            if not image_data:
                logger.warning('Skipped image %d due to download failure', idx)
                continue
            summaries = _parse_ocr_stock_summaries(image_data)
            if summaries:
                merged.update(summaries)
                ocr_success_count += 1
            else:
                logger.warning('Skipped image %d: no stock summaries parsed', idx)

        # 按股票代码逐行更新 short_reason（涨停时间由 /action/field API 提供，不在此处更新）
        updated = 0
        for stock_code, summary in merged.items():
            infos = session.exec(
                select(DailyHotInfo).where(
                    DailyHotInfo.trade_date == trade_date,
                    DailyHotInfo.stock_code == stock_code,
                )
            ).all()
            for info in infos:
                info.short_reason = summary
                session.add(info)
                updated += 1

        session.commit()
        logger.info(
            'OCR done. trade_date=%s images=%d ocr_success=%d stocks_updated=%d',
            trade_date, len(image_urls), ocr_success_count, updated,
        )


    return {
        'trade_date': trade_date,
        'images_processed': len(image_urls),
        'ocr_success': ocr_success_count,
    }
