from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.modules.market_data import data_source


def test_rate_limited_call_caps_at_45_per_minute() -> None:
    # Pretend we already made 45 calls inside the last minute.
    data_source._call_timestamps.clear()
    data_source._call_timestamps.extend(float(x) for x in range(50, 95))

    sleeps: list[float] = []
    monotonic_values = iter([100.0, 110.1])

    def fake_monotonic() -> float:
        return next(monotonic_values)

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    called: list[bool] = []

    def fake_api_call(**kwargs):  # noqa: ANN003
        called.append(True)
        return {'ok': True, **kwargs}

    with (
        patch.object(data_source, 'settings', SimpleNamespace(tushare_rate_limit=999)),
        patch('app.modules.market_data.data_source.time.monotonic', side_effect=fake_monotonic),
        patch('app.modules.market_data.data_source.time.sleep', side_effect=fake_sleep),
    ):
        result = data_source._rate_limited_call(fake_api_call, trade_date='20240102')

    assert called == [True]
    assert result['ok'] is True
    assert sleeps and sleeps[0] >= 9.9

    data_source._call_timestamps.clear()
