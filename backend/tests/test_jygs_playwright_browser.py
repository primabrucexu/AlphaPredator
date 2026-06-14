import os
import unittest
from unittest.mock import patch

from app.modules.jygs.playwright_browser import get_browser_channel_candidates, launch_installed_browser


class _FakeChromium:
    def __init__(self, failing_channels: set[str] | None = None) -> None:
        self.failing_channels = failing_channels or set()
        self.launch_calls: list[dict] = []

    def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        channel = kwargs.get('channel')
        if channel in self.failing_channels:
            raise RuntimeError(f'{channel} unavailable')
        return {'channel': channel}


class JygsPlaywrightBrowserTest(unittest.TestCase):
    def test_get_browser_channel_candidates_defaults_to_installed_browsers(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_browser_channel_candidates(), ['msedge', 'chrome'])

    def test_get_browser_channel_candidates_honors_override(self) -> None:
        with patch.dict(os.environ, {'PLAYWRIGHT_BROWSER_CHANNEL': 'chrome'}, clear=True):
            self.assertEqual(get_browser_channel_candidates(), ['chrome'])

    def test_launch_installed_browser_tries_edge_then_chrome(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            chromium = _FakeChromium(failing_channels={'msedge'})

            browser = launch_installed_browser(chromium, headless=False)

        self.assertEqual(browser, {'channel': 'chrome'})
        self.assertEqual(
            chromium.launch_calls,
            [
                {'channel': 'msedge', 'headless': False},
                {'channel': 'chrome', 'headless': False},
            ],
        )


if __name__ == '__main__':
    unittest.main()
