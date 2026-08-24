from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import duckdb

from app.core.config import MARKET_DATA_DATABASE_PATH
from app.market_data.schemas import DailyBar


SCHEMA_VERSION = 1
PRICE_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class StoredDailyBar:
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    amount: Decimal


@dataclass(frozen=True)
class SyncState:
    symbol: str
    adjust: str
    first_trade_date: date
    last_trade_date: date
    last_synced_at: datetime


def _money(value: float, field: str) -> Decimal:
    try:
        result = Decimal(str(value)).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} 不是有效数字") from exc
    if not result.is_finite():
        raise ValueError(f"{field} 不是有限数字")
    return result


def prepare_daily_bars(
    bars: list[DailyBar],
    *,
    start_date: date,
    end_date: date,
) -> list[StoredDailyBar]:
    prepared: list[StoredDailyBar] = []
    previous_date: date | None = None
    for bar in bars:
        try:
            trade_date = date.fromisoformat(bar.date)
        except ValueError as exc:
            raise ValueError(f"无效交易日期：{bar.date}") from exc
        if not start_date <= trade_date <= end_date:
            raise ValueError(f"交易日期超出任务范围：{trade_date}")
        if previous_date is not None and trade_date <= previous_date:
            raise ValueError("交易日期必须严格递增且不能重复")
        prices = {
            "open": _money(bar.open, "open"),
            "high": _money(bar.high, "high"),
            "low": _money(bar.low, "low"),
            "close": _money(bar.close, "close"),
        }
        if any(value <= 0 for value in prices.values()):
            raise ValueError(f"{trade_date} 的 OHLC 必须大于零")
        if prices["low"] > min(prices["open"], prices["close"]) or prices["high"] < max(
            prices["open"], prices["close"]
        ):
            raise ValueError(f"{trade_date} 的 OHLC 价格关系非法")
        volume = Decimal(str(bar.volume))
        if not volume.is_finite() or volume < 0 or volume != volume.to_integral_value():
            raise ValueError(f"{trade_date} 的成交量必须是非负整数")
        amount = _money(bar.amount, "amount")
        if amount < 0:
            raise ValueError(f"{trade_date} 的成交额不能为负数")
        prepared.append(StoredDailyBar(
            trade_date=trade_date,
            open=prices["open"],
            high=prices["high"],
            low=prices["low"],
            close=prices["close"],
            volume=int(volume),
            amount=amount,
        ))
        previous_date = trade_date
    return prepared


class DuckDbMarketDataStore:
    def __init__(self, path: Path = MARKET_DATA_DATABASE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(str(path))
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> DuckDbMarketDataStore:
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()

    def _migrate(self) -> None:
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
        expected = {"market_schema", "daily_bars", "daily_bar_sync_state"}
        if tables and not expected <= tables:
            raise RuntimeError("检测到不兼容的旧 DuckDB 行情库，请迁移或移走后重试")
        if not tables:
            self.connection.execute("BEGIN")
            try:
                self.connection.execute(
                    "CREATE TABLE market_schema (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
                )
                self.connection.execute(
                    """
                    CREATE TABLE daily_bars (
                        symbol VARCHAR NOT NULL,
                        trade_date DATE NOT NULL,
                        open DECIMAL(18, 2) NOT NULL,
                        high DECIMAL(18, 2) NOT NULL,
                        low DECIMAL(18, 2) NOT NULL,
                        close DECIMAL(18, 2) NOT NULL,
                        volume BIGINT NOT NULL,
                        amount DECIMAL(20, 2) NOT NULL,
                        PRIMARY KEY (symbol, trade_date)
                    )
                    """
                )
                self.connection.execute(
                    """
                    CREATE TABLE daily_bar_sync_state (
                        symbol VARCHAR PRIMARY KEY,
                        adjust VARCHAR NOT NULL,
                        first_trade_date DATE NOT NULL,
                        last_trade_date DATE NOT NULL,
                        last_synced_at TIMESTAMP NOT NULL
                    )
                    """
                )
                self.connection.execute(
                    "INSERT INTO market_schema VALUES (?, ?)",
                    [SCHEMA_VERSION, datetime.now(timezone.utc).replace(tzinfo=None)],
                )
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise
            self._validate_schema()
            return
        versions = self.connection.execute("SELECT version FROM market_schema").fetchall()
        if versions != [(SCHEMA_VERSION,)]:
            raise RuntimeError("DuckDB 行情库 schema 版本不兼容，请先执行显式迁移")
        self._validate_schema()

    def _validate_schema(self) -> None:
        expected = {
            "symbol": "VARCHAR",
            "trade_date": "DATE",
            "open": "DECIMAL(18,2)",
            "high": "DECIMAL(18,2)",
            "low": "DECIMAL(18,2)",
            "close": "DECIMAL(18,2)",
            "volume": "BIGINT",
            "amount": "DECIMAL(20,2)",
        }
        actual = {
            row[0]: row[1]
            for row in self.connection.execute("DESCRIBE daily_bars").fetchall()
        }
        if actual != expected:
            raise RuntimeError("DuckDB daily_bars 表结构不兼容，请先执行显式迁移")

    def get_state(self, symbol: str) -> SyncState | None:
        row = self.connection.execute(
            """
            SELECT symbol, adjust, first_trade_date, last_trade_date, last_synced_at
            FROM daily_bar_sync_state WHERE symbol = ?
            """,
            [symbol],
        ).fetchone()
        return SyncState(*row) if row else None

    def recent_bars(self, symbol: str, limit: int = 5) -> list[StoredDailyBar]:
        rows = self.connection.execute(
            """
            SELECT trade_date, open, high, low, close, volume, amount
            FROM daily_bars WHERE symbol = ? ORDER BY trade_date DESC LIMIT ?
            """,
            [symbol, limit],
        ).fetchall()
        return [StoredDailyBar(*row) for row in reversed(rows)]

    @staticmethod
    def _rows(symbol: str, bars: list[StoredDailyBar]) -> list[tuple]:
        return [
            (symbol, bar.trade_date, bar.open, bar.high, bar.low, bar.close, bar.volume, bar.amount)
            for bar in bars
        ]

    def replace_full(self, symbol: str, bars: list[StoredDailyBar]) -> int:
        if not bars:
            raise ValueError("行情源未返回可保存的日线数据")
        self.connection.execute("BEGIN")
        try:
            self.connection.execute("DELETE FROM daily_bars WHERE symbol = ?", [symbol])
            self.connection.executemany(
                "INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                self._rows(symbol, bars),
            )
            count, first_date, last_date = self.connection.execute(
                "SELECT count(*), min(trade_date), max(trade_date) FROM daily_bars WHERE symbol = ?",
                [symbol],
            ).fetchone()
            if count != len(bars) or first_date != bars[0].trade_date or last_date != bars[-1].trade_date:
                raise RuntimeError("全量写入后的行数或日期范围校验失败")
            self._upsert_state(symbol, first_date, last_date)
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return len(bars)

    def append_new(self, symbol: str, bars: list[StoredDailyBar]) -> int:
        state = self.get_state(symbol)
        if state is None:
            raise ValueError("缺少本地同步状态，不能执行增量写入")
        new_bars = [bar for bar in bars if bar.trade_date > state.last_trade_date]
        self.connection.execute("BEGIN")
        try:
            if new_bars:
                self.connection.executemany(
                    "INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    self._rows(symbol, new_bars),
                )
            last_date = new_bars[-1].trade_date if new_bars else state.last_trade_date
            self._upsert_state(symbol, state.first_trade_date, last_date)
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        return len(new_bars)

    def _upsert_state(self, symbol: str, first_date: date, last_date: date) -> None:
        self.connection.execute(
            """
            INSERT INTO daily_bar_sync_state VALUES (?, 'forward', ?, ?, ?)
            ON CONFLICT (symbol) DO UPDATE SET
                adjust = excluded.adjust,
                first_trade_date = excluded.first_trade_date,
                last_trade_date = excluded.last_trade_date,
                last_synced_at = excluded.last_synced_at
            """,
            [symbol, first_date, last_date, datetime.now(timezone.utc).replace(tzinfo=None)],
        )
