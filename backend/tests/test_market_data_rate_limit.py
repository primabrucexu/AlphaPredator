from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch

import pytest

from app.modules.market_data import data_source


def _config(rate_limit_per_minute: int):
    return type('Config', (), {'rate_limit_per_minute': rate_limit_per_minute})()


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
        patch('app.modules.market_data.data_source.load_mairui_config', return_value=_config(1000)),
        patch('app.modules.market_data.data_source.time.monotonic', side_effect=fake_monotonic),
        patch('app.modules.market_data.data_source.time.sleep', side_effect=fake_sleep),
    ):
        for _ in range(1000):
            assert bucket.acquire() == 0.0
        waited = bucket.acquire()

    assert sleeps == [pytest.approx(0.06)]
    assert waited == pytest.approx(0.06)


def test_token_bucket_rejects_non_positive_settings_rate() -> None:
    bucket = data_source._TokenBucket()

    with patch('app.modules.market_data.data_source.load_mairui_config', return_value=_config(0)):
        with pytest.raises(ValueError, match='rate_limit_per_minute'):
            bucket.acquire()


def test_rate_limited_call_uses_shared_token_bucket() -> None:
    calls: list[str] = []

    def fake_api_call(**kwargs):  # noqa: ANN003
        return {'ok': True, **kwargs}

    def fake_acquire() -> float:
        calls.append('acquire')
        return 0.0

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

    def fake_acquire() -> float:
        calls.append('acquire')
        return 0.0

    with (
        patch('app.modules.market_data.data_source._acquire_market_data_token', side_effect=fake_acquire),
        patch('app.modules.market_data.data_source.urllib_request.urlopen', return_value=FakeResponse()),
    ):
        result = data_source._rate_limited_http_get('https://example.test/data')

    assert calls == ['acquire']
    assert result == b'{"ok": true}'


def test_rate_limited_http_get_logs_redacted_timing(caplog: pytest.LogCaptureFixture) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    monotonic_values = iter([10.0, 10.2, 10.5])

    with (
        caplog.at_level('DEBUG', logger='app.modules.market_data.data_source'),
        patch('app.modules.market_data.data_source.load_mairui_config', return_value=_config(1000)),
        patch('app.modules.market_data.data_source._acquire_market_data_token', return_value=0.2),
        patch('app.modules.market_data.data_source.time.monotonic', side_effect=lambda: next(monotonic_values)),
        patch('app.modules.market_data.data_source.urllib_request.urlopen', return_value=FakeResponse()),
    ):
        data_source._rate_limited_http_get('https://api.mairui.club/hslt/list/secret-licence')

    messages = '\n'.join(record.getMessage() for record in caplog.records)
    assert 'status_code=200' in messages
    assert 'rate_limit=1000/min' not in messages
    assert 'rate_wait=' not in messages
    assert 'network=' not in messages
    assert 'total=' not in messages
    assert 'secret-licence' not in messages
    assert '<licence>' in messages


def test_rate_limited_http_get_logs_http_status_with_body(caplog: pytest.LogCaptureFixture) -> None:
    error = HTTPError(
        url='https://api.mairui.club/hsstock/history/000001.SZ/d/n/secret-licence',
        code=503,
        msg='Service Unavailable',
        hdrs=None,
        fp=BytesIO(b'{"error":"too many requests"}'),
    )
    monotonic_values = iter([10.0, 10.1, 10.3])

    with (
        caplog.at_level('WARNING', logger='app.modules.market_data.data_source'),
        patch('app.modules.market_data.data_source.load_mairui_config', return_value=_config(1000)),
        patch('app.modules.market_data.data_source._acquire_market_data_token', return_value=0.1),
        patch('app.modules.market_data.data_source.time.monotonic', side_effect=lambda: next(monotonic_values)),
        patch('app.modules.market_data.data_source.urllib_request.urlopen', side_effect=error),
    ):
        with pytest.raises(HTTPError):
            data_source._rate_limited_http_get(
                'https://api.mairui.club/hsstock/history/000001.SZ/d/n/secret-licence'
            )

    messages = '\n'.join(record.getMessage() for record in caplog.records)
    assert 'status_code=503' in messages
    assert 'meaning=request_rate_limit_exceeded' in messages
    assert 'rate_limit=1000/min' in messages
    assert 'secret-licence' not in messages
    assert 'body={"error":"too many requests"}' in messages


def test_mairui_get_json_wraps_http_error_as_fatal() -> None:
    error = HTTPError(
        url='https://api.mairui.club/hsstock/history/000001.SZ/d/n/secret-licence',
        code=503,
        msg='Service Unavailable',
        hdrs=None,
        fp=BytesIO(b'{"error":"too many requests"}'),
    )

    with patch('app.modules.market_data.data_source._rate_limited_http_get', side_effect=error):
        with pytest.raises(data_source.MairuiHttpStatusError, match='503'):
            data_source._mairui_get_json('hsstock/history/000001.SZ/d/n/secret-licence')
