from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
import sys

import pytest

from app.market_data.provider.base import (
    MarketDataNoDataError,
    is_at_price_limit,
    limit_percent,
    normalize_symbol,
)
from app.market_data.provider.thsdk import (
    ThsdkMarketDataProvider,
    symbol_to_thscode,
    thscode_to_symbol,
)
from app.market_data.provider.credentials import load_ths_credentials
from app.market_data.provider.base import MarketDataError


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
    captured = {}
    def fake_call(*args, **kwargs):
        captured.update({"args": args, "kwargs": kwargs})
        return [
        {"时间": "2026-01-01 00:00:00", "开盘价": 10, "最高价": 10.2, "最低价": 9.9, "收盘价": 10, "成交量": 1, "总金额": 10},
        {"时间": "2026-01-02 00:00:00", "开盘价": 10, "最高价": 11, "最低价": 10, "收盘价": 11, "成交量": 2, "总金额": 20},
        {"时间": "2026-01-03 00:00:00", "开盘价": 11, "最高价": 11.2, "最低价": 10.8, "收盘价": 11.1, "成交量": 3, "总金额": 30},
        ]
    provider._call = fake_call
    bars = provider.get_daily_bars("600519.SH", count=2)
    assert len(bars) == 2
    assert bars[0].date == "2026-01-02"
    assert bars[0].previous_close == 10
    assert bars[0].is_limit_up is True
    assert captured["kwargs"] == {"interval": "day", "adjust": "forward", "count": 2}


def test_thsdk_daily_bars_support_forward_adjusted_date_range():
    provider = ThsdkMarketDataProvider()
    captured = {}
    provider._call = lambda *args, **kwargs: captured.update({"args": args, "kwargs": kwargs}) or []

    with pytest.raises(MarketDataNoDataError, match="未返回日 K 数据"):
        provider.get_daily_bars("600519.SH", start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))

    assert captured["kwargs"]["adjust"] == "forward"
    assert captured["kwargs"]["interval"] == "day"
    assert captured["kwargs"]["start_time"] == datetime(2024, 1, 1, 0, 0)
    assert captured["kwargs"]["end_time"] == datetime(2024, 12, 31, 23, 59, 59, 999999)
    assert "count" not in captured["kwargs"]


def test_thsdk_not_data_error_has_explicit_type():
    provider = ThsdkMarketDataProvider(minimum_interval_seconds=0)
    provider._client = SimpleNamespace(
        klines=lambda *args, **kwargs: SimpleNamespace(
            success=False,
            error="[thsdk]QueryData错误:not data",
            data=None,
        ),
    )

    with pytest.raises(MarketDataNoDataError, match="not data"):
        provider.get_daily_bars(
            "600519.SH",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )


def test_thsdk_quote_merges_extended_market_fields():
    provider = ThsdkMarketDataProvider()
    query_keys = []

    def fake_call(*args, **kwargs):
        query_keys.append(kwargs["query_key"])
        if kwargs["query_key"] == "基础数据":
            return [{
                "名称": "工商银行", "价格": 7.80, "昨收价": 7.67, "开盘价": 7.71,
                "最高价": 7.83, "最低价": 7.70, "成交量": 462590970, "总金额": 3594980100,
            }]
        return [{
            "量比": 1.4554, "换手率": 0.1716, "市盈率TTM": 7.4862,
            "总市值": 2779968800000, "流通市值": 2102975300000,
        }]

    provider._call = fake_call
    quote = provider.get_quote("601398.SH")

    assert query_keys == ["基础数据", "扩展2"]
    assert quote.name == "工商银行"
    assert quote.volume_ratio == 1.4554
    assert quote.turnover_rate == 0.1716
    assert quote.pe_ttm == 7.4862
    assert quote.total_market_cap == 2779968800000
    assert quote.float_market_cap == 2102975300000


def test_credentials_require_username_and_password(tmp_path):
    path = tmp_path / "credentials.json"
    assert load_ths_credentials(path) is None
    path.write_text('{"username": "user", "password": "pass"}', encoding="utf-8")
    assert load_ths_credentials(path) == {"username": "user", "password": "pass"}
    path.write_text('{"username": "user"}', encoding="utf-8")
    with pytest.raises(MarketDataError, match="password"):
        load_ths_credentials(path)


def test_thsdk_uses_credentials_without_mac_and_spaces_bottom_calls(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text('{"username": "user", "password": "pass"}', encoding="utf-8")
    created = []

    class Client:
        def __init__(self, config):
            created.append(config)

        def connect(self):
            return SimpleNamespace(success=True, error="")

        def stock_cn_lists(self):
            return SimpleNamespace(success=True, error="", data=[])

        def disconnect(self):
            return None

    monkeypatch.setitem(sys.modules, "thsdk", SimpleNamespace(THS=Client))
    times = iter([0.0, 0.01, 0.05])
    sleeps = []
    monkeypatch.setattr("app.market_data.provider.thsdk.time_module.monotonic", lambda: next(times))
    monkeypatch.setattr("app.market_data.provider.thsdk.time_module.sleep", sleeps.append)
    provider = ThsdkMarketDataProvider(credentials_path=path)

    provider.list_stocks()

    assert created == [{"username": "user", "password": "pass"}]
    assert "mac" not in created[0]
    assert sleeps[0] == pytest.approx(0.04)
    assert __import__("logging").getLogger("thsdk.base").disabled is True


def test_thsdk_errors_redact_credentials(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text('{"username": "private-user", "password": "private-pass"}', encoding="utf-8")

    class Client:
        def __init__(self, _config):
            pass

        def connect(self):
            raise RuntimeError("private-user private-pass")

    monkeypatch.setitem(sys.modules, "thsdk", SimpleNamespace(THS=Client))
    provider = ThsdkMarketDataProvider(credentials_path=path, minimum_interval_seconds=0)
    with pytest.raises(MarketDataError) as error:
        provider.connect()
    assert "private-user" not in str(error.value)
    assert "private-pass" not in str(error.value)
