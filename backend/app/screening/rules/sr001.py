from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.screening.backtest import (
    BacktestAction,
    BacktestContext,
    BacktestInstruction,
    BacktestPendingOrder,
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


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def calculate_macd(bars: tuple[ValidDailyBar, ...]) -> tuple[MacdPoint, ...]:
    if not bars:
        return ()
    fast_alpha = Decimal(2) / Decimal(FAST_PERIOD + 1)
    slow_alpha = Decimal(2) / Decimal(SLOW_PERIOD + 1)
    signal_alpha = Decimal(2) / Decimal(SIGNAL_PERIOD + 1)
    fast_ema = bars[0].close
    slow_ema = bars[0].close
    dea = Decimal(0)
    result: list[MacdPoint] = []
    for index, bar in enumerate(bars):
        if index:
            fast_ema = fast_alpha * bar.close + (Decimal(1) - fast_alpha) * fast_ema
            slow_ema = slow_alpha * bar.close + (Decimal(1) - slow_alpha) * slow_ema
        dif = fast_ema - slow_ema
        if index:
            dea = signal_alpha * dif + (Decimal(1) - signal_alpha) * dea
        histogram = Decimal(2) * (dif - dea)
        result.append(MacdPoint(dif=dif, dea=dea, histogram=histogram))
    return tuple(result)


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


def _has_entry_signal(stock: StockIdentity, history: tuple[ValidDailyBar, ...]) -> bool:
    evaluation = SR001Rule().evaluate(stock, history, FIXED_PARAMETERS)
    return evaluation.matched


def _has_ex1(points: tuple[MacdPoint, ...]) -> bool:
    if len(points) < 2:
        return False
    previous, current = points[-2].histogram, points[-1].histogram
    return previous > 0 and current > 0 and current < previous


class SR001BacktestSession:
    def __init__(self, stock: StockIdentity):
        self.stock = stock
        self.entry_signal_date: date | None = None
        self.exit_order: BacktestPendingOrder | None = None
        self.take_profit_executed = False

    def _capture_entry_signal(self, history: tuple[ValidDailyBar, ...]) -> None:
        if _has_entry_signal(self.stock, history):
            self.entry_signal_date = history[-1].trade_date

    def _close_position_and_capture_signal(
        self,
        context: BacktestContext,
        *,
        price: Decimal,
        reason_id: str,
        signal_date: date,
    ) -> list[BacktestInstruction]:
        self.exit_order = None
        self.take_profit_executed = False
        self._capture_entry_signal(context.history)
        return [BacktestInstruction(BacktestAction.SELL, price, reason_id, signal_date)]

    def on_bar(self, context: BacktestContext) -> list[BacktestInstruction]:
        history = context.history
        bar = context.bar
        points = calculate_macd(history)

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
            self._capture_entry_signal(history)
            return []

        if self.exit_order is not None:
            if _is_one_price_limit_down(history):
                return []
            return self._close_position_and_capture_signal(
                context,
                price=bar.open,
                reason_id=self.exit_order.reason_id,
                signal_date=self.exit_order.signal_date,
            )

        stop_price = context.position.buy_price * (Decimal(1) - STOP_LOSS_RATE)
        if bar.open <= stop_price:
            if _is_one_price_limit_down(history):
                self.exit_order = BacktestPendingOrder(BacktestAction.SELL, "SL1", bar.trade_date)
                return []
            return self._close_position_and_capture_signal(
                context, price=bar.open, reason_id="SL1", signal_date=bar.trade_date
            )
        if bar.low <= stop_price:
            return self._close_position_and_capture_signal(
                context, price=stop_price, reason_id="SL1", signal_date=bar.trade_date
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


__all__ = [
    "FIXED_PARAMETERS",
    "SR001BacktestSession",
    "SR001Rule",
    "calculate_macd",
    "create_sr001_backtest_session",
]
