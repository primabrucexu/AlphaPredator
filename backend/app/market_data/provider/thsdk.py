from __future__ import annotations

import logging
import threading
import time as time_module
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from app.market_data.schemas import DailyBar, Quote, StockSummary

from .base import (
    MarketDataError,
    MarketDataNoDataError,
    is_at_price_limit,
    limit_percent,
    normalize_symbol,
)
from .credentials import load_ths_credentials


def symbol_to_thscode(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    code, exchange = normalized.split(".")
    return {"SH": "USHA", "SZ": "USZA", "BJ": "USTM"}[exchange] + code


def thscode_to_symbol(value: str) -> str:
    text = value.strip().upper()
    if len(text) != 10:
        raise ValueError(f"无效 THSCODE: {value}")
    exchange = {"USHA": "SH", "USZA": "SZ", "USTM": "BJ"}.get(text[:4])
    if not exchange or not text[4:].isdigit():
        raise ValueError(f"不支持的 THSCODE: {value}")
    return f"{text[4:]}.{exchange}"


def _number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


class ThsdkMarketDataProvider:
    def __init__(
        self,
        *,
        credentials_path: Path | None = None,
        minimum_interval_seconds: float = 0.05,
    ) -> None:
        self._client: Any | None = None
        self._lock = threading.RLock()
        self._credentials_path = credentials_path
        self._minimum_interval_seconds = minimum_interval_seconds
        self._last_call_at: float | None = None
        self._secrets: tuple[str, ...] = ()

    def _redact(self, value: object) -> str:
        message = str(value)
        for secret in self._secrets:
            message = message.replace(secret, "<redacted>")
        return message

    def _wait_for_slot(self) -> None:
        if self._last_call_at is not None:
            wait = self._minimum_interval_seconds - (time_module.monotonic() - self._last_call_at)
            if wait > 0:
                time_module.sleep(wait)
        self._last_call_at = time_module.monotonic()

    def connect(self) -> None:
        with self._lock:
            if self._client is not None:
                return
            try:
                logging.getLogger("thsdk.base").disabled = True
                from thsdk import THS
                credentials = (
                    load_ths_credentials(self._credentials_path)
                    if self._credentials_path is not None
                    else load_ths_credentials()
                )
                self._secrets = (
                    (credentials["username"], credentials["password"])
                    if credentials is not None
                    else ()
                )
                client = THS(credentials) if credentials is not None else THS()
                self._wait_for_slot()
                response = client.connect()
            except Exception as exc:
                raise MarketDataError(f"thsdk 连接失败：{self._redact(exc)}") from exc
            if not response.success:
                client.disconnect()
                raise MarketDataError(f"thsdk 连接失败：{self._redact(response.error)}")
            self._client = client

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.disconnect()
                self._client = None

    def _call(self, method: str, *args, **kwargs):
        with self._lock:
            self.connect()
            try:
                self._wait_for_slot()
                response = getattr(self._client, method)(*args, **kwargs)
            except Exception as exc:
                self.close()
                raise MarketDataError(f"thsdk 调用 {method} 失败：{self._redact(exc)}") from exc
            if not response.success:
                error = self._redact(response.error) if response.error else ""
                if "not data" in error.lower():
                    raise MarketDataNoDataError(error or "thsdk 未返回数据")
                raise MarketDataError(
                    error or f"thsdk 调用 {method} 失败"
                )
            return response.data or []

    @staticmethod
    def _stock(row: dict[str, Any]) -> StockSummary | None:
        raw = str(row.get("THSCODE") or row.get("代码") or row.get("Code") or "")
        try:
            symbol = thscode_to_symbol(raw) if raw[:4] in {"USHA", "USZA", "USTM"} else normalize_symbol(raw)
        except ValueError:
            return None
        return StockSummary(symbol=symbol, code=symbol[:6], name=str(row.get("Name") or row.get("名称") or ""))

    def search_stocks(self, keyword: str) -> list[StockSummary]:
        rows = self._call("search_symbols", keyword)
        return [stock for row in rows if isinstance(row, dict) and (stock := self._stock(row))]

    def list_stocks(self) -> list[StockSummary]:
        rows = self._call("stock_cn_lists")
        return [stock for row in rows if isinstance(row, dict) and (stock := self._stock(row))]

    def get_quote(self, symbol: str) -> Quote:
        normalized = normalize_symbol(symbol)
        rows = self._call("market_data_cn", symbol_to_thscode(normalized), query_key="基础数据")
        if not rows or not isinstance(rows[0], dict):
            raise MarketDataError("行情源未返回最新行情")
        row = rows[0]
        extended_rows = self._call("market_data_cn", symbol_to_thscode(normalized), query_key="扩展2")
        extended = extended_rows[0] if extended_rows and isinstance(extended_rows[0], dict) else {}
        price = _number(row, "价格", "最新价")
        previous = _number(row, "昨收价", "昨收")
        change = price - previous if price is not None and previous is not None else _number(extended, "涨跌")
        percent = change / previous * 100 if change is not None and previous else _number(extended, "涨幅", "涨跌幅")
        return Quote(
            symbol=normalized,
            name=str(row.get("名称") or ""),
            price=price,
            change=change,
            change_percent=percent,
            previous_close=previous,
            open=_number(row, "开盘价", "开盘"),
            high=_number(row, "最高价", "最高"),
            low=_number(row, "最低价", "最低"),
            volume=_number(row, "成交量"),
            amount=_number(row, "总金额", "成交额"),
            volume_ratio=_number(extended, "量比"),
            turnover_rate=_number(extended, "换手率"),
            pe_ttm=_number(extended, "市盈率TTM"),
            total_market_cap=_number(extended, "总市值"),
            float_market_cap=_number(extended, "流通市值"),
            timestamp=datetime.now().astimezone().isoformat(),
        )

    def get_daily_bars(
        self,
        symbol: str,
        count: int = 250,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyBar]:
        normalized = normalize_symbol(symbol)
        query = {"interval": "day", "adjust": "forward"}
        if start_date is not None and end_date is not None:
            query.update(
                start_time=datetime.combine(start_date, time.min),
                end_time=datetime.combine(end_date, time.max),
            )
        else:
            query["count"] = count
        rows = self._call("klines", symbol_to_thscode(normalized), **query)
        if not rows:
            raise MarketDataNoDataError("thsdk 未返回日 K 数据")
        bars: list[DailyBar] = []
        previous: float | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            close = _number(row, "收盘价", "收盘")
            open_price = _number(row, "开盘价", "开盘")
            high = _number(row, "最高价", "最高")
            low = _number(row, "最低价", "最低")
            if None in (close, open_price, high, low):
                continue
            explicit_previous = _number(row, "昨收价", "昨收")
            prior = explicit_previous if explicit_previous is not None else previous
            up, down = is_at_price_limit(close, prior, limit_percent(normalized, str(row.get("名称") or "")))
            raw_date = row.get("时间") or row.get("日期") or ""
            bars.append(DailyBar(
                date=str(raw_date)[:10], open=open_price, high=high, low=low, close=close,
                volume=_number(row, "成交量") or 0, amount=_number(row, "总金额", "成交额") or 0,
                previous_close=prior, is_limit_up=up, is_limit_down=down,
            ))
            previous = close
        return bars if start_date is not None else bars[-count:]

    def corporate_action(self, symbol: str) -> list[dict[str, Any]]:
        rows = self._call("corporate_action", symbol_to_thscode(symbol))
        return [row for row in rows if isinstance(row, dict)]
