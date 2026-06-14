"""Browser selection helpers for Python Playwright."""

from __future__ import annotations

import os
from typing import Any


def get_browser_channel_candidates() -> list[str]:
    """Return local browser channels to try for Playwright Chromium automation."""

    explicit_channel = os.environ.get('PLAYWRIGHT_BROWSER_CHANNEL', '').strip()
    if explicit_channel:
        return [explicit_channel]
    return ['msedge', 'chrome']


def launch_installed_browser(chromium: Any, *, headless: bool) -> Any:
    """Launch an installed Edge/Chrome browser instead of Playwright's bundled Chromium."""

    errors: list[str] = []
    for channel in get_browser_channel_candidates():
        try:
            return chromium.launch(channel=channel, headless=headless)
        except Exception as exc:  # noqa: BLE001
            errors.append(f'{channel}: {exc}')

    detail = ' | '.join(errors)
    raise RuntimeError(
        '未找到可用的本机 Chromium 浏览器。请安装 Microsoft Edge 或 Google Chrome，'
        '或设置 PLAYWRIGHT_BROWSER_CHANNEL 指定浏览器 channel。'
        f'尝试结果：{detail}'
    )
