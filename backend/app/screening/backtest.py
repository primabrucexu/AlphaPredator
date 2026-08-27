from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from app.market_data.storage import StoredDailyBar

from .models import JsonValue, StockIdentity, ValidDailyBar, valid_daily_bars


class BacktestAction(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class BacktestInstruction:
    action: BacktestAction
    price: Decimal
    reason_id: str
    signal_date: date
    fraction: Decimal = Decimal("1")


@dataclass(frozen=True)
class BacktestPendingOrder:
    action: BacktestAction
    reason_id: str
    signal_date: date

    def to_dict(self) -> dict[str, str]:
        return {
            "action": self.action.value,
            "reason_id": self.reason_id,
            "signal_date": self.signal_date.isoformat(),
        }


@dataclass(frozen=True)
class PositionView:
    buy_date: date
    buy_price: Decimal
    remaining_fraction: Decimal


@dataclass(frozen=True)
class BacktestContext:
    stock: StockIdentity
    start_date: date
    end_date: date
    history: tuple[ValidDailyBar, ...]
    position: PositionView | None

    @property
    def bar(self) -> ValidDailyBar:
        return self.history[-1]


class BacktestSession(Protocol):
    def on_bar(self, context: BacktestContext) -> list[BacktestInstruction]: ...

    def pending_orders(self) -> list[BacktestPendingOrder]: ...


@dataclass(frozen=True)
class IndividualBacktestResult:
    rule_id: str
    rule_revision: int
    parameters: dict[str, JsonValue]
    stock: StockIdentity
    start_date: date
    end_date: date
    data_start_date: date | None
    data_end_date: date | None
    status: str
    trades: tuple[dict[str, Any], ...]
    open_trade: dict[str, Any] | None
    pending_orders: tuple[BacktestPendingOrder, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": "individual",
            "rule_id": self.rule_id,
            "rule_revision": self.rule_revision,
            "parameters": self.parameters,
            "symbol": self.stock.symbol,
            "code": self.stock.code,
            "name": self.stock.name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "data_start_date": self.data_start_date.isoformat() if self.data_start_date else None,
            "data_end_date": self.data_end_date.isoformat() if self.data_end_date else None,
            "status": self.status,
            "completed_trades": len(self.trades),
            "trades": list(self.trades),
            "open_trade": self.open_trade,
            "pending_orders": [order.to_dict() for order in self.pending_orders],
        }


def _decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _position_view(position: dict[str, Any] | None) -> PositionView | None:
    if position is None:
        return None
    return PositionView(
        buy_date=position["buy_date"],
        buy_price=position["buy_price"],
        remaining_fraction=position["remaining_fraction"],
    )


def _validate_instruction(
    instruction: BacktestInstruction,
    bar: ValidDailyBar,
    start_date: date,
) -> None:
    if instruction.action not in {BacktestAction.BUY, BacktestAction.SELL}:
        raise ValueError("交易动作必须是 buy 或 sell")
    if not instruction.reason_id.strip():
        raise ValueError("交易原因编号不能为空")
    if instruction.signal_date < start_date:
        raise ValueError("交易信号日期不能早于回测开始日期")
    if instruction.signal_date > bar.trade_date:
        raise ValueError("交易指令使用了未来信号日期")
    if not instruction.price.is_finite() or instruction.price <= 0:
        raise ValueError("交易价格必须为正的有限数值")
    if instruction.price < bar.low or instruction.price > bar.high:
        raise ValueError("交易价格超出当日最高价和最低价范围")
    if not instruction.fraction.is_finite() or not Decimal("0") < instruction.fraction <= Decimal("1"):
        raise ValueError("交易比例必须大于 0 且不超过 1")


def run_individual_backtest(
    *,
    rule_id: str,
    rule_revision: int,
    parameters: dict[str, JsonValue],
    stock: StockIdentity,
    source_bars: list[StoredDailyBar],
    start_date: date,
    end_date: date,
    session: BacktestSession,
) -> IndividualBacktestResult:
    if start_date > end_date:
        raise ValueError("回测开始日期不能晚于结束日期")
    bars = valid_daily_bars([bar for bar in source_bars if bar.trade_date <= end_date])
    in_range = [index for index, bar in enumerate(bars) if bar.trade_date >= start_date]
    if not in_range:
        raise ValueError("回测区间内没有有效日 K")

    position: dict[str, Any] | None = None
    completed: list[dict[str, Any]] = []
    for index in in_range:
        bar = bars[index]
        context = BacktestContext(
            stock=stock,
            start_date=start_date,
            end_date=end_date,
            history=bars[: index + 1],
            position=_position_view(position),
        )
        for instruction in session.on_bar(context):
            _validate_instruction(instruction, bar, start_date)
            if instruction.action == BacktestAction.BUY:
                if position is not None:
                    raise ValueError("同一股票只能存在一笔活动交易")
                if instruction.fraction != Decimal("1"):
                    raise ValueError("个股回测买入比例必须为 1")
                position = {
                    "signal_date": instruction.signal_date,
                    "buy_date": bar.trade_date,
                    "buy_price": instruction.price,
                    "remaining_fraction": Decimal("1"),
                    "realized_return": Decimal("0"),
                    "sells": [],
                }
                continue
            if position is None:
                raise ValueError("没有活动持仓时不能卖出")
            if bar.trade_date <= position["buy_date"]:
                raise ValueError("A 股回测不允许在买入日卖出")
            sold_fraction = position["remaining_fraction"] * instruction.fraction
            sell_return = instruction.price / position["buy_price"] - Decimal("1")
            position["realized_return"] += sold_fraction * sell_return
            position["remaining_fraction"] -= sold_fraction
            position["sells"].append({
                "date": bar.trade_date.isoformat(),
                "reason_id": instruction.reason_id,
                "price": _decimal(instruction.price),
                "fraction_of_original": _decimal(sold_fraction),
                "return_rate": _decimal(sell_return),
            })
            if position["remaining_fraction"] == 0:
                completed.append({
                    "signal_date": position["signal_date"].isoformat(),
                    "buy_date": position["buy_date"].isoformat(),
                    "buy_price": _decimal(position["buy_price"]),
                    "sells": position["sells"],
                    "realized_return": _decimal(position["realized_return"]),
                })
                position = None

    pending_orders = tuple(session.pending_orders())
    for order in pending_orders:
        if order.action not in {BacktestAction.BUY, BacktestAction.SELL}:
            raise ValueError("待成交动作必须是 buy 或 sell")
        if not order.reason_id.strip():
            raise ValueError("待成交原因编号不能为空")
        if order.signal_date < start_date:
            raise ValueError("待成交信号日期不能早于回测开始日期")
        if order.signal_date > end_date:
            raise ValueError("待成交订单使用了未来信号日期")
        if position is None and order.action == BacktestAction.SELL:
            raise ValueError("没有活动持仓时不能保留待卖出订单")
        if position is not None and order.action == BacktestAction.BUY:
            raise ValueError("已有活动持仓时不能保留待买入订单")
    open_trade = None
    if position is not None:
        open_trade = {
            "signal_date": position["signal_date"].isoformat(),
            "buy_date": position["buy_date"].isoformat(),
            "buy_price": _decimal(position["buy_price"]),
            "remaining_fraction": _decimal(position["remaining_fraction"]),
            "realized_return": _decimal(position["realized_return"]),
            "sells": position["sells"],
        }
    if open_trade is not None:
        status = "open_position"
    elif any(order.action == BacktestAction.BUY for order in pending_orders):
        status = "pending_entry"
    elif completed:
        status = "completed"
    else:
        status = "no_trade"
    return IndividualBacktestResult(
        rule_id=rule_id,
        rule_revision=rule_revision,
        parameters=parameters,
        stock=stock,
        start_date=start_date,
        end_date=end_date,
        data_start_date=bars[0].trade_date,
        data_end_date=bars[-1].trade_date,
        status=status,
        trades=tuple(completed),
        open_trade=open_trade,
        pending_orders=pending_orders,
    )
