from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.market_data import data_source


def test_token_bucket_uses_settings_rate_without_300_cap() -> None:
    bucket = data_source._TokenBucket()
    now = {'value': 100.0}
    sleeps: list[float] = []

    def fake_monotonic() -> float:
        return now['value']

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now['value'] += seconds

    with (
        patch.object(data_source, 'settings', SimpleNamespace(market_data_rate_limit=1000)),
        patch('app.modules.market_data.data_source.time.monotonic', side_effect=fake_monotonic),
        patch('app.modules.market_data.data_source.time.sleep', side_effect=fake_sleep),
    ):
        for _ in range(1000):
            bucket.acquire()
        bucket.acquire()

    assert sleeps == [pytest.approx(0.06)]


def test_token_bucket_rejects_non_positive_settings_rate() -> None:
    bucket = data_source._TokenBucket()

    with patch.object(data_source, 'settings', SimpleNamespace(market_data_rate_limit=0)):
        with pytest.raises(ValueError, match='market_data_rate_limit'):
            bucket.acquire()


def test_rate_limited_call_uses_shared_token_bucket() -> None:
    calls: list[str] = []

    def fake_api_call(**kwargs):  # noqa: ANN003
        return {'ok': True, **kwargs}

    def fake_acquire() -> None:
        calls.append('acquire')

    with patch('app.modules.market_data.data_source._acquire_market_data_token', side_effect=fake_acquire):
        result = data_source._rate_limited_call(fake_api_call, trade_date='20240102')

    assert calls == ['acquire']
    assert result == {'ok': True, 'trade_date': '20240102'}


def test_rate_limited_http_get_uses_shared_token_bucket() -> None:
    calls: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_acquire() -> None:
        calls.append('acquire')

    with (
        patch('app.modules.market_data.data_source._acquire_market_data_token', side_effect=fake_acquire),
        patch('app.modules.market_data.data_source.urllib_request.urlopen', return_value=FakeResponse()),
    ):
        result = data_source._rate_limited_http_get('https://example.test/data')

    assert calls == ['acquire']
    assert result == b'{"ok": true}'
