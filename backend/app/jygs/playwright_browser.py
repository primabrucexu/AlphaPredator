from __future__ import annotations

import os
from typing import Any


def browser_channel_candidates() -> list[str]:
    configured = os.getenv("PLAYWRIGHT_BROWSER_CHANNEL", "").strip()
    return [configured] if configured else ["msedge", "chrome"]


def launch_installed_browser(chromium: Any, *, headless: bool) -> Any:
    errors: list[str] = []
    for channel in browser_channel_candidates():
        try:
            return chromium.launch(channel=channel, headless=headless)
        except Exception as exc:
            errors.append(f"{channel}: {exc}")
    raise RuntimeError(
        "未找到可用的 Microsoft Edge 或 Google Chrome。"
        "可通过 PLAYWRIGHT_BROWSER_CHANNEL 指定浏览器。"
        f"尝试结果：{' | '.join(errors)}"
    )
