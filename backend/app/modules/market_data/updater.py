"""Daily incremental updater (DuckDB-first).

Daily quote facts are persisted into DuckDB ``daily_bars`` only.
SQLite is used for metadata tables (e.g. stock profiles), not daily quote facts.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.data_source import (
    fetch_daily_bars_by_date,
    fetch_spot_snapshot,
    fetch_stock_pool,
)

logger = logging.getLogger(__name__)


def run_daily_update(
    *,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
    daily_bars_parquet_path: Path | None = None,
    market_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    """
    Fetch today's market data and upsert it into the existing database.

    Returns a dict summarising what was updated.
    """
    target_sqlite = sqlite_path or settings.sqlite_path
    target_snapshot = market_snapshot_path or settings.market_snapshot_path
    target_duckdb = duckdb_path or settings.duckdb_path
    target_parquet = daily_bars_parquet_path or settings.daily_bars_parquet_path

    trade_date = date.today().strftime('%Y-%m-%d')
    logger.info('Daily update: fetching spot snapshot for %s …', trade_date)
    snapshot_rows = fetch_spot_snapshot(trade_date)
    stock_pool = fetch_stock_pool(snapshot_rows)

    # Upsert stock profile metadata only (no daily quote facts in SQLite)
    ensure_sqlite_schema(target_sqlite)
    _upsert_sqlite_profiles(target_sqlite, stock_pool)

    # Fetch today's bars and append to DuckDB / Parquet
    logger.info('Daily update: fetching today\'s bars for %d stocks …', len(stock_pool))
    today_bars = _fetch_today_bars(stock_pool, trade_date)
    _upsert_duckdb(target_duckdb, target_parquet, today_bars)

    # Refresh data-range metadata from DuckDB and rebuild market snapshot JSON
    _update_data_range_meta(target_sqlite, target_duckdb)
    _rebuild_snapshot(target_snapshot, trade_date, snapshot_rows)

    logger.info(
        'Daily update complete: %d stocks, %d bars, trade_date=%s',
        len(stock_pool),
        len(today_bars),
        trade_date,
    )
    return {
        'trade_date': trade_date,
        'stock_count': len(stock_pool),
        'bar_count': len(today_bars),
        'start_trade_date': trade_date,
        'end_trade_date': trade_date,
        'processed_trade_dates': [trade_date],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _upsert_sqlite_profiles(
    sqlite_path: Path,
    stock_pool: list[dict[str, Any]],
) -> None:
    from app.db.sqlite import connect_sqlite
    conn = connect_sqlite(sqlite_path)
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        conn.executemany(
            '''
            INSERT INTO stock_profiles (stock_code, stock_name, sectors_json, ai_quick_summary)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(stock_code) DO UPDATE SET
                stock_name = excluded.stock_name
            ''',
            [
                (
                    r['stock_code'],
                    r['stock_name'],
                    json.dumps(
                        [s.strip() for s in r.get('sectors', '').split('|') if s.strip()],
                        ensure_ascii=False,
                    ),
                    r.get('ai_quick_summary', ''),
                )
                for r in stock_pool
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_today_bars(
    stock_pool: list[dict[str, Any]],
    trade_date: str,
) -> list[dict[str, Any]]:
    """Fetch today's daily bars for all stocks in one bulk API call."""
    return fetch_daily_bars_by_date(trade_date)


def _upsert_duckdb(
    duckdb_path: Path,
    daily_bars_parquet_path: Path,
    today_bars: list[dict[str, Any]],
) -> None:
    if not today_bars:
        return

    from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_parent, ensure_duckdb_schema
    ensure_duckdb_parent(duckdb_path, daily_bars_parquet_path.parent)
    ensure_duckdb_schema(duckdb_path)

    conn = connect_duckdb(duckdb_path)
    try:
        conn.execute('BEGIN TRANSACTION')
        # Delete existing rows for the same (stock_code, trade_date) then insert
        trade_dates = {r['trade_date'] for r in today_bars}
        for td in trade_dates:
            conn.execute('DELETE FROM daily_bars WHERE trade_date = ?', [td])

        conn.executemany(
            'INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [
                (
                    r['stock_code'],
                    r['trade_date'],
                    r['open_price'],
                    r['high_price'],
                    r['low_price'],
                    r['close_price'],
                    r['volume'],
                    r.get('turnover_amount_billion', 0.0),
                    bool(r.get('is_up_limit', False)),
                    bool(r.get('is_down_limit', False)),
                )
                for r in today_bars
            ],
        )

        # Re-export parquet
        daily_bars_parquet_path.unlink(missing_ok=True)
        parquet_path = str(daily_bars_parquet_path).replace('\\', '/').replace("'", "''")
        conn.execute(
            f"COPY (SELECT * FROM daily_bars ORDER BY stock_code, trade_date) TO '{parquet_path}' (FORMAT PARQUET)"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _rebuild_snapshot(
    market_snapshot_path: Path,
    trade_date: str,
    snapshot_rows: list[dict[str, Any]],
) -> None:
    stocks: list[dict[str, Any]] = []
    for r in snapshot_rows:
        stocks.append(
            {
                'stock_code': r['stock_code'],
                'stock_name': r.get('stock_name', ''),
                'current_price': float(r.get('current_price', 0.0) or 0.0),
                'change_amount': float(r.get('change_amount', 0.0) or 0.0),
                'change_pct': float(r.get('change_pct', 0.0) or 0.0),
                'turnover_amount_billion': float(r.get('turnover_amount_billion', 0.0) or 0.0),
                'turnover_rate': float(r.get('turnover_rate', 0.0) or 0.0),
                'sectors': [s.strip() for s in str(r.get('sectors', '')).split('|') if s.strip()],
                'ai_quick_summary': r.get('ai_quick_summary', ''),
                'trade_date': r.get('trade_date', trade_date),
            }
        )

    stocks.sort(key=lambda x: float(x.get('turnover_amount_billion', 0.0) or 0.0), reverse=True)

    summary = {
        'trade_date': trade_date,
        'rising_count': sum(1 for s in stocks if float(s.get('change_pct', 0.0)) >= 0),
        'falling_count': sum(1 for s in stocks if float(s.get('change_pct', 0.0)) < 0),
        'turnover_amount_billion': round(sum(float(s.get('turnover_amount_billion', 0.0)) for s in stocks), 2),
    }

    # Preserve existing hot_sectors from the snapshot if available
    existing_hot_sectors: list[dict[str, Any]] = []
    if market_snapshot_path.exists():
        try:
            payload = json.loads(market_snapshot_path.read_text(encoding='utf-8'))
            existing_hot_sectors = payload.get('hot_sectors', [])
        except Exception:  # noqa: BLE001
            pass

    payload = {
        'summary': summary,
        'hot_sectors': existing_hot_sectors,
        'stocks': stocks,
    }
    market_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    market_snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _update_data_range_meta(sqlite_path: Path, duckdb_path: Path) -> None:
    from app.db.duckdb_storage import connect_duckdb

    dconn = connect_duckdb(duckdb_path)
    try:
        row = dconn.execute(
            '''SELECT MIN(trade_date) AS min_td,
                      MAX(trade_date) AS max_td,
                      COUNT(DISTINCT trade_date) AS cnt
               FROM daily_bars'''
        ).fetchone()
    finally:
        dconn.close()

    if not row or not row[0]:
        return

    conn = connect_sqlite(sqlite_path)
    try:
        conn.execute(
            '''INSERT OR REPLACE INTO data_range_meta
               (dataset, min_trade_date, max_trade_date, trading_day_count, updated_at)
               VALUES ('daily_bars', ?, ?, ?, datetime('now'))''',
            (str(row[0]), str(row[1]), int(row[2])),
        )
        conn.commit()
    finally:
        conn.close()
