from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.market_data.storage import StoredDailyBar
from app.screening.backtest import (
    BacktestAction,
    BacktestContext,
    BacktestInstruction,
    BacktestPendingOrder,
    IndividualBacktestResult,
    run_individual_backtest,
)
from app.screening.models import (
    JsonValue,
    RuleEvidence,
    RuleEvaluation,
    StockIdentity,
    ValidDailyBar,
)


FAST_PERIOD = 8
SLOW_PERIOD = 17
SIGNAL_PERIOD = 6
WARMUP_BARS = 100
TAKE_PROFIT_RATE = Decimal("0.05")
TAKE_PROFIT_FRACTION = Decimal("0.5")
STOP_LOSS_RATE = Decimal("0.05")

FIXED_PARAMETERS: dict[str, JsonValue] = {
    "macd_fast": FAST_PERIOD,
    "macd_slow": SLOW_PERIOD,
    "macd_signal": SIGNAL_PERIOD,
    "warmup_bars": WARMUP_BARS,
    "take_profit_rate": "0.05",
    "take_profit_fraction": "0.5",
    "stop_loss_rate": "0.05",
}


@dataclass(frozen=True)
class MacdPoint:
    dif: Decimal
    dea: Decimal
    histogram: Decimal


class _MacdAccumulator:
    def __init__(self) -> None:
        self.fast_alpha = Decimal(2) / Decimal(FAST_PERIOD + 1)
        self.slow_alpha = Decimal(2) / Decimal(SLOW_PERIOD + 1)
        self.signal_alpha = Decimal(2) / Decimal(SIGNAL_PERIOD + 1)
        self.fast_ema: Decimal | None = None
        self.slow_ema: Decimal | None = None
        self.dea = Decimal(0)

    def update(self, bar: ValidDailyBar) -> MacdPoint:
        is_first = self.fast_ema is None or self.slow_ema is None
        if is_first:
            self.fast_ema = bar.close
            self.slow_ema = bar.close
        else:
            self.fast_ema = (
                self.fast_alpha * bar.close
                + (Decimal(1) - self.fast_alpha) * self.fast_ema
            )
            self.slow_ema = (
                self.slow_alpha * bar.close
                + (Decimal(1) - self.slow_alpha) * self.slow_ema
            )
        dif = self.fast_ema - self.slow_ema
        if not is_first:
            self.dea = (
                self.signal_alpha * dif
                + (Decimal(1) - self.signal_alpha) * self.dea
            )
        histogram = Decimal(2) * (dif - self.dea)
        return MacdPoint(dif=dif, dea=self.dea, histogram=histogram)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def calculate_macd(bars: tuple[ValidDailyBar, ...]) -> tuple[MacdPoint, ...]:
    accumulator = _MacdAccumulator()
    return tuple(accumulator.update(bar) for bar in bars)


def _scope_evidence(stock: StockIdentity) -> tuple[RuleEvidence, RuleEvidence]:
    if not stock.code.strip():
        raise ValueError("股票代码缺失，无法执行 SR001")
    if not stock.name.strip():
        raise ValueError("股票名称缺失，无法执行 SR001")
    u1 = stock.code.startswith(("60", "00"))
    u2 = "ST" not in stock.name.upper()
    return (
        RuleEvidence("U1", u1, {"code": stock.code, "prefix": stock.code[:2]}),
        RuleEvidence("U2", u2, {"name": stock.name, "contains_st": not u2}),
    )


def _signal_evidence(points: tuple[MacdPoint, ...]) -> RuleEvidence:
    if len(points) < 3:
        return RuleEvidence("C1", False, {"available_bars": len(points), "required_bars": 3})
    first, second, third = (point.histogram for point in points[-3:])
    passed = first < 0 and first <= second <= third and first < third
    return RuleEvidence(
        "C1",
        passed,
        {
            "h_s_minus_2": _decimal_text(first),
            "h_s_minus_1": _decimal_text(second),
            "h_s": _decimal_text(third),
        },
    )


def _signal_evidence_v2(points: tuple[MacdPoint, ...]) -> RuleEvidence:
    if len(points) < 5:
        return RuleEvidence("C1", False, {"available_bars": len(points), "required_bars": 5})
    previous, trough, first, second, third = (
        point.histogram for point in points[-5:]
    )
    passed = (
        trough < 0
        and previous > trough
        and trough <= first <= second <= third
        and trough < third
    )
    return RuleEvidence(
        "C1",
        passed,
        {
            "h_s_minus_4": _decimal_text(previous),
            "h_s_minus_3": _decimal_text(trough),
            "h_s_minus_2": _decimal_text(first),
            "h_s_minus_1": _decimal_text(second),
            "h_s": _decimal_text(third),
        },
    )


def _current_signal_v2(points: tuple[MacdPoint, ...]) -> tuple[RuleEvidence, int | None]:
    for signal_index in range(len(points) - 1, 3, -1):
        evidence = _signal_evidence_v2(points[signal_index - 4:signal_index + 1])
        if evidence.passed:
            continues = all(
                points[index - 1].histogram <= points[index].histogram
                for index in range(signal_index + 1, len(points))
            )
            if continues:
                return evidence, signal_index
            break
    return _signal_evidence_v2(points), None


class SR001Rule:
    rule_id = "SR001"
    revision = 1

    def validate_parameters(self, parameters: dict) -> dict[str, JsonValue]:
        if parameters and parameters != FIXED_PARAMETERS:
            raise ValueError("SR001 revision 1 使用固定参数，不允许覆盖")
        return dict(FIXED_PARAMETERS)

    def evaluate(
        self,
        stock: StockIdentity,
        bars: tuple[ValidDailyBar, ...],
        parameters: dict[str, JsonValue],
    ) -> RuleEvaluation:
        if parameters != FIXED_PARAMETERS:
            raise ValueError("SR001 revision 1 参数与固定定义不一致")
        u1, u2 = _scope_evidence(stock)
        points = calculate_macd(bars)
        c1 = _signal_evidence(points)
        matched = u1.passed and u2.passed and c1.passed
        latest = points[-1]
        return RuleEvaluation(
            matched=matched,
            signal_date=bars[-1].trade_date if matched else None,
            evidence=(u1, u2, c1),
            metrics={
                "dif": _decimal_text(latest.dif),
                "dea": _decimal_text(latest.dea),
                "histogram": _decimal_text(latest.histogram),
                "valid_bar_count": len(bars),
            },
            insufficient_history=len(bars) < WARMUP_BARS,
        )


class SR001Revision2Rule(SR001Rule):
    revision = 2

    def validate_parameters(self, parameters: dict) -> dict[str, JsonValue]:
        if parameters and parameters != FIXED_PARAMETERS:
            raise ValueError("SR001 revision 2 使用固定参数，不允许覆盖")
        return dict(FIXED_PARAMETERS)

    def evaluate(
        self,
        stock: StockIdentity,
        bars: tuple[ValidDailyBar, ...],
        parameters: dict[str, JsonValue],
    ) -> RuleEvaluation:
        if parameters != FIXED_PARAMETERS:
            raise ValueError("SR001 revision 2 参数与固定定义不一致")
        u1, u2 = _scope_evidence(stock)
        points = calculate_macd(bars)
        c1, signal_index = _current_signal_v2(points)
        matched = u1.passed and u2.passed and c1.passed
        latest = points[-1]
        return RuleEvaluation(
            matched=matched,
            signal_date=bars[signal_index].trade_date if matched and signal_index is not None else None,
            evidence=(u1, u2, c1),
            metrics={
                "dif": _decimal_text(latest.dif),
                "dea": _decimal_text(latest.dea),
                "histogram": _decimal_text(latest.histogram),
                "valid_bar_count": len(bars),
            },
            insufficient_history=len(bars) < WARMUP_BARS,
        )


class SR001Revision3Rule(SR001Revision2Rule):
    revision = 3

    def validate_parameters(self, parameters: dict) -> dict[str, JsonValue]:
        if parameters and parameters != FIXED_PARAMETERS:
            raise ValueError("SR001 revision 3 使用固定参数，不允许覆盖")
        return dict(FIXED_PARAMETERS)

    def evaluate_with_backtest(
        self,
        stock: StockIdentity,
        bars: tuple[ValidDailyBar, ...],
        parameters: dict[str, JsonValue],
    ) -> tuple[RuleEvaluation, IndividualBacktestResult | None]:
        if parameters != FIXED_PARAMETERS:
            raise ValueError("SR001 revision 3 参数与固定定义不一致")
        candidate = super().evaluate(stock, bars, parameters)
        if not candidate.matched or candidate.signal_date is None:
            return candidate, None
        source_bars = [StoredDailyBar(
            trade_date=bar.trade_date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            amount=Decimal("0"),
        ) for bar in bars]
        backtest = run_individual_backtest(
            rule_id=self.rule_id,
            rule_revision=self.revision,
            parameters=parameters,
            stock=stock,
            source_bars=source_bars,
            start_date=bars[0].trade_date,
            end_date=bars[-1].trade_date,
            session=create_sr001_v3_backtest_session(stock, parameters),
        )
        signal_text = candidate.signal_date.isoformat()
        open_signal = (
            str(backtest.open_trade.get("signal_date"))
            if backtest.open_trade is not None
            else None
        )
        pending_entry = any(
            order.action == BacktestAction.BUY and order.signal_date == candidate.signal_date
            for order in backtest.pending_orders
        )
        active = open_signal == signal_text or pending_entry
        lifecycle = RuleEvidence(
            "L1",
            active,
            {
                "candidate_signal_date": signal_text,
                "backtest_status": backtest.status,
                "active_signal": active,
            },
        )
        return RuleEvaluation(
            matched=active,
            signal_date=candidate.signal_date if active else None,
            evidence=(*candidate.evidence, lifecycle),
            metrics=candidate.metrics,
            insufficient_history=candidate.insufficient_history,
        ), backtest

    def evaluate(
        self,
        stock: StockIdentity,
        bars: tuple[ValidDailyBar, ...],
        parameters: dict[str, JsonValue],
    ) -> RuleEvaluation:
        evaluation, _ = self.evaluate_with_backtest(stock, bars, parameters)
        return evaluation


def _is_one_price_limit_up(history: tuple[ValidDailyBar, ...]) -> bool:
    if len(history) < 2:
        return False
    bar = history[-1]
    return bar.open == bar.high == bar.low == bar.close and bar.close > history[-2].close


def _is_one_price_limit_down(history: tuple[ValidDailyBar, ...]) -> bool:
    if len(history) < 2:
        return False
    bar = history[-1]
    return bar.open == bar.high == bar.low == bar.close and bar.close < history[-2].close


def _has_ex1(points: tuple[MacdPoint, ...]) -> bool:
    if len(points) < 2:
        return False
    previous, current = points[-2].histogram, points[-1].histogram
    return previous > 0 and current > 0 and current < previous


class SR001BacktestSession:
    def __init__(
        self,
        stock: StockIdentity,
        *,
        signal_evidence: Callable[[tuple[MacdPoint, ...]], RuleEvidence] = _signal_evidence,
        signal_window: int = 3,
    ):
        self.stock = stock
        self._signal_evidence = signal_evidence
        self.entry_signal_date: date | None = None
        self.exit_order: BacktestPendingOrder | None = None
        self.take_profit_executed = False
        self._macd = _MacdAccumulator()
        self._processed_bars = 0
        self._recent_points: deque[MacdPoint] = deque(maxlen=signal_window)

    def _update_macd(self, history: tuple[ValidDailyBar, ...]) -> tuple[MacdPoint, ...]:
        for bar in history[self._processed_bars:]:
            self._recent_points.append(self._macd.update(bar))
        self._processed_bars = len(history)
        return tuple(self._recent_points)

    def _capture_entry_signal(
        self,
        history: tuple[ValidDailyBar, ...],
        points: tuple[MacdPoint, ...],
    ) -> None:
        u1, u2 = _scope_evidence(self.stock)
        if u1.passed and u2.passed and self._signal_evidence(points).passed:
            self.entry_signal_date = history[-1].trade_date

    def _close_position_and_capture_signal(
        self,
        context: BacktestContext,
        *,
        price: Decimal,
        reason_id: str,
        signal_date: date,
        points: tuple[MacdPoint, ...],
    ) -> list[BacktestInstruction]:
        self.exit_order = None
        self.take_profit_executed = False
        self._capture_entry_signal(context.history, points)
        return [BacktestInstruction(BacktestAction.SELL, price, reason_id, signal_date)]

    def on_bar(self, context: BacktestContext) -> list[BacktestInstruction]:
        history = context.history
        bar = context.bar
        points = self._update_macd(history)

        if context.position is None:
            if self.entry_signal_date is not None:
                if _is_one_price_limit_up(history):
                    return []
                signal_date = self.entry_signal_date
                self.entry_signal_date = None
                self.take_profit_executed = False
                if _has_ex1(points):
                    self.exit_order = BacktestPendingOrder(BacktestAction.SELL, "EX1", bar.trade_date)
                return [BacktestInstruction(BacktestAction.BUY, bar.open, "B1", signal_date)]
            self._capture_entry_signal(history, points)
            return []

        if self.exit_order is not None:
            if _is_one_price_limit_down(history):
                return []
            return self._close_position_and_capture_signal(
                context,
                price=bar.open,
                reason_id=self.exit_order.reason_id,
                signal_date=self.exit_order.signal_date,
                points=points,
            )

        stop_price = context.position.buy_price * (Decimal(1) - STOP_LOSS_RATE)
        if bar.open <= stop_price:
            if _is_one_price_limit_down(history):
                self.exit_order = BacktestPendingOrder(BacktestAction.SELL, "SL1", bar.trade_date)
                return []
            return self._close_position_and_capture_signal(
                context,
                price=bar.open,
                reason_id="SL1",
                signal_date=bar.trade_date,
                points=points,
            )
        if bar.low <= stop_price:
            return self._close_position_and_capture_signal(
                context,
                price=stop_price,
                reason_id="SL1",
                signal_date=bar.trade_date,
                points=points,
            )

        if _has_ex1(points):
            self.exit_order = BacktestPendingOrder(BacktestAction.SELL, "EX1", bar.trade_date)
            return []
        if (
            not self.take_profit_executed
            and bar.close / context.position.buy_price - Decimal(1) > TAKE_PROFIT_RATE
        ):
            self.take_profit_executed = True
            return [BacktestInstruction(
                BacktestAction.SELL,
                bar.close,
                "TP1",
                bar.trade_date,
                TAKE_PROFIT_FRACTION,
            )]
        return []

    def pending_orders(self) -> list[BacktestPendingOrder]:
        result: list[BacktestPendingOrder] = []
        if self.entry_signal_date is not None:
            result.append(BacktestPendingOrder(BacktestAction.BUY, "B1", self.entry_signal_date))
        if self.exit_order is not None:
            result.append(self.exit_order)
        return result


def create_sr001_backtest_session(
    stock: StockIdentity,
    parameters: dict[str, JsonValue],
) -> SR001BacktestSession:
    if parameters != FIXED_PARAMETERS:
        raise ValueError("SR001 revision 1 参数与固定定义不一致")
    return SR001BacktestSession(stock)


def create_sr001_v2_backtest_session(
    stock: StockIdentity,
    parameters: dict[str, JsonValue],
) -> SR001BacktestSession:
    if parameters != FIXED_PARAMETERS:
        raise ValueError("SR001 revision 2 参数与固定定义不一致")
    return SR001BacktestSession(
        stock,
        signal_evidence=_signal_evidence_v2,
        signal_window=5,
    )


def create_sr001_v3_backtest_session(
    stock: StockIdentity,
    parameters: dict[str, JsonValue],
) -> SR001BacktestSession:
    if parameters != FIXED_PARAMETERS:
        raise ValueError("SR001 revision 3 参数与固定定义不一致")
    return SR001BacktestSession(
        stock,
        signal_evidence=_signal_evidence_v2,
        signal_window=5,
    )


__all__ = [
    "FIXED_PARAMETERS",
    "SR001BacktestSession",
    "SR001Revision2Rule",
    "SR001Revision3Rule",
    "SR001Rule",
    "calculate_macd",
    "create_sr001_backtest_session",
    "create_sr001_v2_backtest_session",
    "create_sr001_v3_backtest_session",
]
