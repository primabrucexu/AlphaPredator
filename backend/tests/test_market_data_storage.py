from __future__ import annotations

from datetime import date
from decimal import Decimal

import duckdb
import pytest

from app.market_data.schemas import DailyBar
from app.market_data.storage import DuckDbMarketDataStore, StoredDailyBar, prepare_daily_bars


def bar(day: str, close: float = 10, *, volume: float = 100, amount: float = 1000) -> DailyBar:
    return DailyBar(
        date=day,
        open=close,
        high=close + 0.2,
        low=close - 0.2,
        close=close,
        volume=volume,
        amount=amount,
    )


def test_duckdb_schema_and_decimal_quantization(tmp_path):
    path = tmp_path / "market.duckdb"
    with DuckDbMarketDataStore(path) as store:
        prepared = prepare_daily_bars(
            [bar("2025-01-02", 10.126, amount=1000.126)],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 3),
        )
        store.replace_full("000001.SZ", prepared)
        saved = store.recent_bars("000001.SZ")
        assert saved[0].close == Decimal("10.13")
        assert saved[0].amount == Decimal("1000.13")
        columns = {row[0]: row[1] for row in store.connection.execute("DESCRIBE daily_bars").fetchall()}
        assert columns["open"] == "DECIMAL(18,2)"
        assert columns["amount"] == "DECIMAL(20,2)"
        assert columns["volume"] == "BIGINT"


def test_incremental_append_is_idempotent(tmp_path):
    with DuckDbMarketDataStore(tmp_path / "market.duckdb") as store:
        assert store.coverage() == (None, None)
        initial = prepare_daily_bars(
            [bar("2025-01-02"), bar("2025-01-03", 10.2)],
            start_date=date(2025, 1, 1), end_date=date(2025, 1, 4),
        )
        fetched = prepare_daily_bars(
            [bar("2025-01-02"), bar("2025-01-03", 10.2), bar("2025-01-04", 10.3)],
            start_date=date(2025, 1, 2), end_date=date(2025, 1, 4),
        )
        store.replace_full("000001.SZ", initial)
        assert store.append_new("000001.SZ", fetched) == 1
        assert store.append_new("000001.SZ", fetched) == 0
        assert len(store.recent_bars("000001.SZ", 10)) == 3
        assert store.coverage() == (date(2025, 1, 2), date(2025, 1, 4))


def test_full_replace_rolls_back_when_insert_fails(tmp_path):
    with DuckDbMarketDataStore(tmp_path / "market.duckdb") as store:
        initial = prepare_daily_bars(
            [bar("2025-01-02")], start_date=date(2025, 1, 1), end_date=date(2025, 1, 2)
        )
        store.replace_full("000001.SZ", initial)
        oversized = StoredDailyBar(
            date(2025, 1, 3), Decimal("10000000000000000.00"),
            Decimal("10000000000000000.00"), Decimal("10000000000000000.00"),
            Decimal("10000000000000000.00"), 1, Decimal("1.00"),
        )
        with pytest.raises(Exception):
            store.replace_full("000001.SZ", [oversized])
        saved = store.recent_bars("000001.SZ")
        assert [row.trade_date for row in saved] == [date(2025, 1, 2)]


def test_incompatible_existing_duckdb_is_rejected(tmp_path):
    path = tmp_path / "old.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute("CREATE TABLE old_daily_bars (symbol VARCHAR)")
    connection.close()
    with pytest.raises(RuntimeError, match="不兼容"):
        DuckDbMarketDataStore(path)


def test_unknown_schema_version_is_rejected(tmp_path):
    path = tmp_path / "future.duckdb"
    DuckDbMarketDataStore(path).close()
    connection = duckdb.connect(str(path))
    connection.execute("UPDATE market_schema SET version = 999")
    connection.close()
    with pytest.raises(RuntimeError, match="schema 版本不兼容"):
        DuckDbMarketDataStore(path)


def test_daily_bar_validation_rejects_duplicates_and_fractional_volume():
    with pytest.raises(ValueError, match="严格递增"):
        prepare_daily_bars(
            [bar("2025-01-02"), bar("2025-01-02")],
            start_date=date(2025, 1, 1), end_date=date(2025, 1, 2),
        )
    with pytest.raises(ValueError, match="非负整数"):
        prepare_daily_bars(
            [bar("2025-01-02", volume=1.5)],
            start_date=date(2025, 1, 1), end_date=date(2025, 1, 2),
        )
