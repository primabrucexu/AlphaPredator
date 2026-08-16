from __future__ import annotations

import pytest

from app.market_data.provider.base import (
    is_at_price_limit,
    limit_percent,
    normalize_symbol,
)
from app.market_data.provider.thsdk import (
    ThsdkMarketDataProvider,
    symbol_to_thscode,
    thscode_to_symbol,
)


@pytest.mark.parametrize(("raw", "symbol", "thscode"), [
    ("600519", "600519.SH", "USHA600519"),
    ("000001", "000001.SZ", "USZA000001"),
    ("920001", "920001.BJ", "USTM920001"),
])
def test_symbol_conversion(raw, symbol, thscode):
    assert normalize_symbol(raw) == symbol
    assert symbol_to_thscode(symbol) == thscode
    assert thscode_to_symbol(thscode) == symbol


def test_invalid_symbol_is_rejected():
    with pytest.raises(ValueError):
        normalize_symbol("abc")


def test_limit_rules_cover_boards_and_st():
    assert limit_percent("600519.SH") == 0.10
    assert limit_percent("300750.SZ") == 0.20
    assert limit_percent("688001.SH") == 0.20
    assert limit_percent("920001.BJ") == 0.30
    assert limit_percent("600001.SH", "ST示例") == 0.05
    assert is_at_price_limit(11.0, 10.0, 0.10) == (True, False)
    assert is_at_price_limit(9.0, 10.0, 0.10) == (False, True)


def test_thsdk_daily_bars_are_normalized_and_limited():
    provider = ThsdkMarketDataProvider()
    provider._call = lambda *_args, **_kwargs: [
        {"时间": "2026-01-01 00:00:00", "开盘价": 10, "最高价": 10.2, "最低价": 9.9, "收盘价": 10, "成交量": 1, "总金额": 10},
        {"时间": "2026-01-02 00:00:00", "开盘价": 10, "最高价": 11, "最低价": 10, "收盘价": 11, "成交量": 2, "总金额": 20},
        {"时间": "2026-01-03 00:00:00", "开盘价": 11, "最高价": 11.2, "最低价": 10.8, "收盘价": 11.1, "成交量": 3, "总金额": 30},
    ]
    bars = provider.get_daily_bars("600519.SH", count=2)
    assert len(bars) == 2
    assert bars[0].date == "2026-01-02"
    assert bars[0].previous_close == 10
    assert bars[0].is_limit_up is True
