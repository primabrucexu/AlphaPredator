from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.market_data.storage import StoredDailyBar
from app.screening.backtest import run_individual_backtest
from app.screening.executor import execute_screening_rule, execute_screening_rule_with_backtest
from app.screening.models import ScreeningOutcome, StockIdentity, valid_daily_bars
from app.screening.registry import RuleRegistry
from app.screening.rules import register_production_rules
from app.screening.rules.sr001 import (
    FIXED_PARAMETERS,
    MacdPoint,
    SR001Revision2Rule,
    SR001Revision3Rule,
    SR001Rule,
    _MacdAccumulator,
    calculate_macd,
    create_sr001_backtest_session,
    create_sr001_v2_backtest_session,
    create_sr001_v3_backtest_session,
)


STOCK = StockIdentity("000021.SZ", "000021", "深科技")
START = date(2026, 1, 1)


def bar(
    day: int,
    *,
    open: str,
    high: str | None = None,
    low: str | None = None,
    close: str | None = None,
    volume: int = 100,
) -> StoredDailyBar:
    open_price = Decimal(open)
    close_price = Decimal(close if close is not None else open)
    high_price = Decimal(high) if high is not None else max(open_price, close_price) + Decimal("0.2")
    low_price = Decimal(low) if low is not None else min(open_price, close_price) - Decimal("0.2")
    return StoredDailyBar(
        trade_date=START + timedelta(days=day),
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        amount=Decimal("1000"),
    )


def close_bars(values: list[str]) -> list[StoredDailyBar]:
    return [bar(index, open=value) for index, value in enumerate(values)]


def histograms(*values: str) -> tuple[MacdPoint, ...]:
    return tuple(
        MacdPoint(dif=Decimal(0), dea=Decimal(0), histogram=Decimal(value))
        for value in values
    )


def test_sr001_evaluator_matches_c1_and_records_fixed_parameters():
    result = execute_screening_rule(
        SR001Rule(),
        stock=STOCK,
        source_bars=close_bars(["10", "9", "8", "7", "8", "9"]),
        as_of_date=START + timedelta(days=5),
        parameters={},
    )
    assert result.outcome == ScreeningOutcome.MATCHED
    assert result.signal_date == START + timedelta(days=5)
    assert result.parameters == FIXED_PARAMETERS
    assert result.insufficient_history
    assert [(item.condition_id, item.passed) for item in result.evidence] == [
        ("U1", True),
        ("U2", True),
        ("C1", True),
    ]
    assert Decimal(str(result.evidence[-1].values["h_s_minus_2"])) < Decimal(
        str(result.evidence[-1].values["h_s_minus_1"])
    ) < Decimal(str(result.evidence[-1].values["h_s"]))


def test_sr001_evaluator_rejects_scope_and_non_continuous_histogram():
    not_continuous = execute_screening_rule(
        SR001Rule(),
        stock=STOCK,
        source_bars=close_bars(["10", "9", "8", "8", "8"]),
        as_of_date=START + timedelta(days=4),
        parameters={},
    )
    assert not_continuous.outcome == ScreeningOutcome.NOT_MATCHED
    assert not_continuous.evidence[-1].passed is False

    out_of_scope = execute_screening_rule(
        SR001Rule(),
        stock=StockIdentity("300001.SZ", "300001", "特锐德ST"),
        source_bars=close_bars(["10", "9", "8", "7", "8", "9"]),
        as_of_date=START + timedelta(days=5),
        parameters={},
    )
    assert out_of_scope.outcome == ScreeningOutcome.NOT_MATCHED
    assert [(item.condition_id, item.passed) for item in out_of_scope.evidence[:2]] == [
        ("U1", False),
        ("U2", False),
    ]


def test_sr001_marks_short_history_and_rejects_parameter_overrides():
    result = execute_screening_rule(
        SR001Rule(),
        stock=STOCK,
        source_bars=close_bars(["10", "9"]),
        as_of_date=START + timedelta(days=1),
        parameters={},
    )
    assert result.outcome == ScreeningOutcome.NOT_MATCHED
    assert result.insufficient_history
    assert result.evidence[-1].values == {"available_bars": 2, "required_bars": 3}
    with pytest.raises(ValueError, match="固定参数"):
        SR001Rule().validate_parameters({"macd_fast": 9})
    with pytest.raises(ValueError, match="股票名称缺失"):
        execute_screening_rule(
            SR001Rule(),
            stock=StockIdentity("000021.SZ", "000021", ""),
            source_bars=close_bars(["10", "9", "8"]),
            as_of_date=START + timedelta(days=2),
            parameters={},
        )


def test_sr001_production_registration_is_idempotent():
    registry = RuleRegistry()
    register_production_rules(registry)
    register_production_rules(registry)
    assert isinstance(registry.get("SR001", 1), SR001Rule)
    assert registry.get_backtest_factory("SR001", 1) is create_sr001_backtest_session
    assert isinstance(registry.get("SR001", 2), SR001Revision2Rule)
    assert registry.get_backtest_factory("SR001", 2) is create_sr001_v2_backtest_session
    assert isinstance(registry.get("SR001", 3), SR001Revision3Rule)
    assert registry.get_backtest_factory("SR001", 3) is create_sr001_v3_backtest_session
    assert registry.get_latest("SR001").revision == 3


def test_sr001_revision_2_uses_first_three_day_improvement_signal_for_600183(monkeypatch):
    dates = [
        date(2026, 8, 21),
        date(2026, 8, 24),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
        date(2026, 8, 28),
    ]
    source = [StoredDailyBar(
        trade_date=trade_date,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=100,
        amount=Decimal("1000"),
    ) for trade_date in dates]
    windows = {
        date(2026, 8, 27): histograms(
            "-1.7089013891788979",
            "-2.4475092962587333",
            "-2.1674758640267718",
            "-1.6670059723071692",
            "0.4804869159602148",
        ),
        date(2026, 8, 28): histograms(
            "-1.7089013891788979",
            "-2.4475092962587333",
            "-2.1674758640267718",
            "-1.6670059723071692",
            "0.4804869159602148",
            "2.2138614939515757",
        ),
    }

    def fake_macd(bars):
        return windows[bars[-1].trade_date]

    monkeypatch.setattr("app.screening.rules.sr001.calculate_macd", fake_macd)
    on_signal_day = execute_screening_rule(
        SR001Revision2Rule(),
        stock=StockIdentity("600183.SH", "600183", "生益科技"),
        source_bars=source,
        as_of_date=date(2026, 8, 27),
        parameters={},
    )
    after_signal_day = execute_screening_rule(
        SR001Revision2Rule(),
        stock=StockIdentity("600183.SH", "600183", "生益科技"),
        source_bars=source,
        as_of_date=date(2026, 8, 28),
        parameters={},
    )

    assert on_signal_day.outcome == ScreeningOutcome.MATCHED
    assert on_signal_day.signal_date == date(2026, 8, 27)
    assert after_signal_day.outcome == ScreeningOutcome.MATCHED
    assert after_signal_day.signal_date == date(2026, 8, 27)
    assert on_signal_day.evidence[-1].values["h_s_minus_3"] == "-2.4475092962587333"


def test_sr001_revision_2_backtest_buys_600183_after_august_27_signal(monkeypatch):
    dates = [
        date(2026, 8, 21),
        date(2026, 8, 24),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
        date(2026, 8, 28),
    ]
    source = [StoredDailyBar(
        trade_date=trade_date,
        open=Decimal("140.01") if trade_date == date(2026, 8, 28) else Decimal("100"),
        high=Decimal("151.79") if trade_date == date(2026, 8, 28) else Decimal("101"),
        low=Decimal("138.41") if trade_date == date(2026, 8, 28) else Decimal("99"),
        close=Decimal("145.65") if trade_date == date(2026, 8, 28) else Decimal("100"),
        volume=100,
        amount=Decimal("1000"),
    ) for trade_date in dates]
    signal_window = histograms(
        "-1.7089013891788979",
        "-2.4475092962587333",
        "-2.1674758640267718",
        "-1.6670059723071692",
        "0.4804869159602148",
    )

    def fake_update(_session, history):
        if history[-1].trade_date == date(2026, 8, 27):
            return signal_window
        return histograms("0", "0", "0", "0", "0")

    monkeypatch.setattr("app.screening.rules.sr001.SR001BacktestSession._update_macd", fake_update)
    stock = StockIdentity("600183.SH", "600183", "生益科技")
    result = run_individual_backtest(
        rule_id="SR001",
        rule_revision=2,
        parameters=FIXED_PARAMETERS,
        stock=stock,
        source_bars=source,
        start_date=dates[0],
        end_date=dates[-1],
        session=create_sr001_v2_backtest_session(stock, FIXED_PARAMETERS),
    )

    assert result.status == "open_position"
    assert result.open_trade == {
        "signal_date": "2026-08-27",
        "buy_date": "2026-08-28",
        "buy_price": "140.01",
        "remaining_fraction": "1",
        "realized_return": "0",
        "sells": [],
    }


def test_sr001_revision_3_keeps_600183_while_signal_trade_is_open(monkeypatch):
    dates = [
        date(2026, 8, 21),
        date(2026, 8, 24),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
        date(2026, 8, 28),
    ]
    source = [StoredDailyBar(
        trade_date=trade_date,
        open=Decimal("140.01") if trade_date == date(2026, 8, 28) else Decimal("100"),
        high=Decimal("151.79") if trade_date == date(2026, 8, 28) else Decimal("101"),
        low=Decimal("138.41") if trade_date == date(2026, 8, 28) else Decimal("99"),
        close=Decimal("145.65") if trade_date == date(2026, 8, 28) else Decimal("100"),
        volume=100,
        amount=Decimal("1000"),
    ) for trade_date in dates]
    signal_window = histograms(
        "-1.7089013891788979",
        "-2.4475092962587333",
        "-2.1674758640267718",
        "-1.6670059723071692",
        "0.4804869159602148",
    )
    continued_window = (*signal_window, histograms("2.2138614939515757")[0])

    monkeypatch.setattr(
        "app.screening.rules.sr001.calculate_macd",
        lambda _bars: continued_window,
    )

    def fake_update(_session, history):
        if history[-1].trade_date == date(2026, 8, 27):
            return signal_window
        return histograms("0", "0", "0", "0", "0")

    monkeypatch.setattr("app.screening.rules.sr001.SR001BacktestSession._update_macd", fake_update)
    result, backtest = execute_screening_rule_with_backtest(
        SR001Revision3Rule(),
        stock=StockIdentity("600183.SH", "600183", "生益科技"),
        source_bars=source,
        as_of_date=date(2026, 8, 28),
        parameters={},
    )

    assert result.outcome == ScreeningOutcome.MATCHED
    assert result.signal_date == date(2026, 8, 27)
    assert result.evidence[-1].condition_id == "L1"
    assert result.evidence[-1].values["backtest_status"] == "open_position"
    assert backtest is not None
    assert backtest.status == "open_position"


def test_sr001_revision_3_excludes_603468_after_signal_trade_closed():
    prices = [
        (date(2026, 8, 6), "39.60", "45.45", "36.89", "37.49"),
        (date(2026, 8, 7), "31.00", "32.40", "30.67", "30.75"),
        (date(2026, 8, 10), "29.47", "30.30", "28.61", "29.10"),
        (date(2026, 8, 11), "28.65", "28.75", "28.00", "28.09"),
        (date(2026, 8, 12), "27.88", "28.96", "27.60", "28.04"),
        (date(2026, 8, 13), "27.76", "27.76", "26.78", "26.78"),
        (date(2026, 8, 14), "26.65", "26.94", "25.93", "25.93"),
        (date(2026, 8, 17), "25.80", "25.90", "25.42", "25.87"),
        (date(2026, 8, 18), "25.75", "26.23", "25.71", "25.90"),
        (date(2026, 8, 19), "25.65", "25.66", "24.24", "24.36"),
        (date(2026, 8, 20), "24.30", "24.54", "24.12", "24.19"),
        (date(2026, 8, 21), "24.11", "24.11", "23.71", "23.85"),
        (date(2026, 8, 24), "23.84", "23.96", "23.21", "23.68"),
        (date(2026, 8, 25), "23.43", "23.84", "23.35", "23.74"),
        (date(2026, 8, 26), "23.62", "24.05", "23.59", "23.84"),
        (date(2026, 8, 27), "23.82", "24.19", "23.61", "24.01"),
        (date(2026, 8, 28), "23.94", "24.04", "23.81", "23.82"),
    ]
    source = [StoredDailyBar(
        trade_date=trade_date,
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=100,
        amount=Decimal("1000"),
    ) for trade_date, open_price, high, low, close in prices]
    stock = StockIdentity("603468.SH", "603468", "测试股票")

    revision_2 = execute_screening_rule(
        SR001Revision2Rule(),
        stock=stock,
        source_bars=source,
        as_of_date=date(2026, 8, 28),
        parameters={},
    )
    revision_3 = execute_screening_rule(
        SR001Revision3Rule(),
        stock=stock,
        source_bars=source,
        as_of_date=date(2026, 8, 28),
        parameters={},
    )

    assert revision_2.outcome == ScreeningOutcome.MATCHED
    assert revision_2.signal_date == date(2026, 8, 14)
    assert revision_3.outcome == ScreeningOutcome.NOT_MATCHED
    assert revision_3.signal_date is None
    assert revision_3.evidence[-1].condition_id == "L1"
    assert revision_3.evidence[-1].values == {
        "candidate_signal_date": "2026-08-14",
        "backtest_status": "completed",
        "active_signal": False,
    }


def test_sr001_incremental_macd_matches_reference_for_every_prefix():
    bars = valid_daily_bars(close_bars([
        "10", "9.5", "9.8", "9.2", "10.1", "10.6", "10.3", "11.2", "10.9",
    ]))
    fast_alpha = Decimal(2) / Decimal(9)
    slow_alpha = Decimal(2) / Decimal(18)
    signal_alpha = Decimal(2) / Decimal(7)
    fast_ema = bars[0].close
    slow_ema = bars[0].close
    dea = Decimal(0)
    expected = []
    for index, current in enumerate(bars):
        if index:
            fast_ema = fast_alpha * current.close + (Decimal(1) - fast_alpha) * fast_ema
            slow_ema = slow_alpha * current.close + (Decimal(1) - slow_alpha) * slow_ema
        dif = fast_ema - slow_ema
        if index:
            dea = signal_alpha * dif + (Decimal(1) - signal_alpha) * dea
        expected.append(MacdPoint(dif=dif, dea=dea, histogram=Decimal(2) * (dif - dea)))

    accumulator = _MacdAccumulator()
    incremental = tuple(accumulator.update(current) for current in bars)
    assert incremental == tuple(expected)
    for end in range(1, len(bars) + 1):
        assert calculate_macd(bars[:end]) == tuple(expected[:end])


def _fake_macd_for_entry_and(monkeypatch, overrides: dict[int, tuple[MacdPoint, ...]]):
    default = histograms("-3", "-3", "-3")

    def fake(_session, history):
        day = (history[-1].trade_date - START).days
        return overrides.get(day, default)

    monkeypatch.setattr("app.screening.rules.sr001.SR001BacktestSession._update_macd", fake)


def _run(bars: list[StoredDailyBar]):
    return run_individual_backtest(
        rule_id="SR001",
        rule_revision=1,
        parameters=FIXED_PARAMETERS,
        stock=STOCK,
        source_bars=bars,
        start_date=START + timedelta(days=2),
        end_date=bars[-1].trade_date,
        session=create_sr001_backtest_session(STOCK, FIXED_PARAMETERS),
    )


def test_sr001_backtest_updates_macd_once_per_bar(monkeypatch):
    calls = 0
    original = _MacdAccumulator.update

    def counted(accumulator, current):
        nonlocal calls
        calls += 1
        return original(accumulator, current)

    monkeypatch.setattr(_MacdAccumulator, "update", counted)
    bars = close_bars(["10"] * 500)
    result = _run(bars)
    assert result.status == "no_trade"
    assert calls == len(bars)


def test_sr001_buy_waits_through_one_price_limit_up(monkeypatch):
    _fake_macd_for_entry_and(monkeypatch, {2: histograms("-3", "-2", "-1")})
    result = _run([
        bar(0, open="10"),
        bar(1, open="10"),
        bar(2, open="10"),
        bar(3, open="11", high="11", low="11", close="11"),
        bar(4, open="10.8", high="11", low="10.5", close="10.9"),
    ])
    assert result.status == "open_position"
    assert result.open_trade["signal_date"] == "2026-01-03"
    assert result.open_trade["buy_date"] == "2026-01-05"
    assert result.open_trade["buy_price"] == "10.8"


def test_sr001_ex1_wins_over_tp1_and_sells_on_next_bar(monkeypatch):
    _fake_macd_for_entry_and(
        monkeypatch,
        {
            2: histograms("-3", "-2", "-1"),
            4: histograms("0.5", "1", "0.5"),
        },
    )
    result = _run([
        bar(0, open="10"),
        bar(1, open="10"),
        bar(2, open="10"),
        bar(3, open="10", high="10.2", low="9.8", close="10"),
        bar(4, open="10", high="10.8", low="9.8", close="10.6"),
        bar(5, open="10.4", high="10.6", low="10.2", close="10.5"),
    ])
    assert result.status == "completed"
    assert [sale["reason_id"] for sale in result.trades[0]["sells"]] == ["EX1"]
    assert result.trades[0]["sells"][0]["date"] == "2026-01-06"
    assert result.trades[0]["sells"][0]["price"] == "10.4"


def test_sr001_tp1_is_strict_and_executes_only_once(monkeypatch):
    _fake_macd_for_entry_and(monkeypatch, {2: histograms("-3", "-2", "-1")})
    result = _run([
        bar(0, open="10"),
        bar(1, open="10"),
        bar(2, open="10"),
        bar(3, open="10", high="10.2", low="9.8", close="10"),
        bar(4, open="10", high="10.6", low="9.8", close="10.5"),
        bar(5, open="10.2", high="10.8", low="10", close="10.6"),
        bar(6, open="10.4", high="11", low="10.2", close="10.8"),
    ])
    assert result.status == "open_position"
    assert result.open_trade["remaining_fraction"] == "0.5"
    assert [(sale["date"], sale["reason_id"]) for sale in result.open_trade["sells"]] == [
        ("2026-01-06", "TP1")
    ]


def test_sr001_tp1_executes_on_one_price_limit_down(monkeypatch):
    _fake_macd_for_entry_and(monkeypatch, {2: histograms("-3", "-2", "-1")})
    result = _run([
        bar(0, open="10"),
        bar(1, open="10"),
        bar(2, open="10"),
        bar(3, open="10", high="12", low="9.8", close="12"),
        bar(4, open="11", high="11", low="11", close="11"),
    ])
    assert result.status == "open_position"
    assert result.open_trade["remaining_fraction"] == "0.5"
    assert result.open_trade["sells"][0]["reason_id"] == "TP1"
    assert result.open_trade["sells"][0]["price"] == "11"


def test_sr001_sl1_locks_on_limit_down_and_sells_when_tradable(monkeypatch):
    _fake_macd_for_entry_and(monkeypatch, {2: histograms("-3", "-2", "-1")})
    result = _run([
        bar(0, open="10"),
        bar(1, open="10"),
        bar(2, open="10"),
        bar(3, open="10", high="10.2", low="9.8", close="10"),
        bar(4, open="9.4", high="9.4", low="9.4", close="9.4"),
        bar(5, open="9.3", high="9.3", low="9.3", close="9.3"),
        bar(6, open="9.2", high="9.4", low="9", close="9.2"),
    ])
    assert result.status == "completed"
    sale = result.trades[0]["sells"][0]
    assert sale["reason_id"] == "SL1"
    assert sale["date"] == "2026-01-07"
    assert sale["price"] == "9.2"


def test_sr001_intraday_sl1_uses_stop_price(monkeypatch):
    _fake_macd_for_entry_and(monkeypatch, {2: histograms("-3", "-2", "-1")})
    result = _run([
        bar(0, open="10"),
        bar(1, open="10"),
        bar(2, open="10"),
        bar(3, open="10", high="10.2", low="9.8", close="10"),
        bar(4, open="9.8", high="10", low="9.4", close="9.7"),
    ])
    sale = result.trades[0]["sells"][0]
    assert sale["reason_id"] == "SL1"
    assert sale["price"] == "9.5"


def test_sr001_ignores_repeated_entry_signals_while_position_is_active(monkeypatch):
    _fake_macd_for_entry_and(
        monkeypatch,
        {
            2: histograms("-3", "-2", "-1"),
            3: histograms("-3", "-2", "-1"),
            4: histograms("-3", "-2", "-1"),
        },
    )
    result = _run([
        bar(0, open="10"),
        bar(1, open="10"),
        bar(2, open="10"),
        bar(3, open="10"),
        bar(4, open="10"),
    ])
    assert result.status == "open_position"
    assert result.pending_orders == ()
    assert result.open_trade["buy_date"] == "2026-01-04"
