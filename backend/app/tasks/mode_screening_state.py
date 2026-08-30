from __future__ import annotations

from typing import Any


CURRENT_OPPORTUNITY_STATES = {
    "pending_entry",
    "bought_today",
    "holding",
    "take_profit",
    "pending_exit",
}


def derive_mode_screening_current_state(
    *,
    backtest_status: str,
    as_of_date: str,
    open_trade: dict[str, Any] | None,
    pending_orders: list[dict[str, Any]],
) -> str:
    if backtest_status == "pending_entry":
        return "pending_entry"
    if backtest_status != "open_position" or open_trade is None:
        return "completed"
    if any(order.get("action") == "sell" for order in pending_orders):
        return "pending_exit"
    sells = open_trade.get("sells")
    if isinstance(sells, list) and any(
        isinstance(sale, dict) and sale.get("reason_id") == "TP1"
        for sale in sells
    ):
        return "take_profit"
    if open_trade.get("buy_date") == as_of_date:
        return "bought_today"
    return "holding"
