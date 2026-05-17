"""Playwright-based JYGS login helper."""

from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import sync_playwright

from app.core.settings import settings


def login_and_capture_session(timeout_seconds: int = 300) -> dict[str, Any]:
    """Open JYGS web login page and wait for SESSION cookie from a real browser login."""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(f"{settings.jygs_site_url.rstrip('/')}/", wait_until='domcontentloaded')
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                cookies = context.cookies([
                    settings.jygs_site_url,
                    settings.jygs_api_url,
                ])
                session_value = None
                for cookie in cookies:
                    name = str(cookie.get('name', ''))
                    domain = str(cookie.get('domain', ''))
                    value = str(cookie.get('value', ''))
                    if name == 'SESSION' and 'jiuyangongshe.com' in domain and value:
                        session_value = value
                        break
                if session_value:
                    return {
                        'ok': True,
                        'session': session_value,
                        'cookie_count': len(cookies),
                    }
                page.wait_for_timeout(1200)

            raise RuntimeError('登录超时：未检测到 SESSION，请完成网页端登录后重试。')
        finally:
            browser.close()
