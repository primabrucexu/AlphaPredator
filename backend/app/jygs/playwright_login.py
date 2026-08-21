from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import sync_playwright

from .playwright_browser import launch_installed_browser


SITE_URL = "https://www.jiuyangongshe.com/"
API_URL = "https://app.jiuyangongshe.com/"


def login_and_capture_session(timeout_seconds: int = 300) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = launch_installed_browser(playwright.chromium, headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(SITE_URL, wait_until="domcontentloaded")
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                cookies = context.cookies([SITE_URL, API_URL])
                for cookie in cookies:
                    if (
                        str(cookie.get("name")) == "SESSION"
                        and "jiuyangongshe.com" in str(cookie.get("domain"))
                        and cookie.get("value")
                    ):
                        return {"session": str(cookie["value"]), "cookie_count": len(cookies)}
                page.wait_for_timeout(1200)
            raise RuntimeError("登录超时：未检测到 SESSION，请完成网页端登录后重试。")
        finally:
            browser.close()
