from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from app.market_data.schemas import DailyBar, Quote, StockSummary


class MarketDataError(RuntimeError):
    pass


class MarketDataProvider(Protocol):
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def search_stocks(self, keyword: str) -> list[StockSummary]: ...
    def list_stocks(self) -> list[StockSummary]: ...
    def get_quote(self, symbol: str) -> Quote: ...
    def get_daily_bars(
        self,
        symbol: str,
        count: int = 250,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyBar]: ...
    def corporate_action(self, symbol: str) -> list[dict[str, Any]]: ...


def normalize_symbol(value: str) -> str:
    text = value.strip().upper()
    if len(text) == 9 and text[6] == "." and text[:6].isdigit() and text[7:] in {"SH", "SZ", "BJ"}:
        return text
    if text.isdigit() and len(text) == 6:
        if text.startswith(("4", "8", "9")):
            return f"{text}.BJ"
        if text.startswith(("5", "6", "9")):
            return f"{text}.SH"
        return f"{text}.SZ"
    raise ValueError("股票代码必须是六位数字或 CODE.SH/CODE.SZ/CODE.BJ 格式")


def limit_percent(symbol: str, name: str = "") -> float:
    code = normalize_symbol(symbol)[:6]
    if "ST" in name.upper():
        return 0.05
    if code.startswith(("300", "301", "688")):
        return 0.20
    if normalize_symbol(symbol).endswith(".BJ"):
        return 0.30
    return 0.10


def is_at_price_limit(close: float, previous_close: float | None, pct: float) -> tuple[bool, bool]:
    if not previous_close or previous_close <= 0:
        return False, False
    upper = round(previous_close * (1 + pct) + 1e-8, 2)
    lower = round(previous_close * (1 - pct) + 1e-8, 2)
    return close >= upper, close <= lower
