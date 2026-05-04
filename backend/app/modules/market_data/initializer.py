"""
Market data initialization V2.

Date-driven approach:
1. Create a task with start_date / end_date (YYYYMMDD format).
2. For each calendar date in the range (ascending order):
   a. Check whether it is a Chinese stock-market trading day (via ChnCal).
   b. Non-trading days -> mark SKIPPED_NON_TRADING, advance progress counter.
   c. Trading days -> call tushare pro.daily(trade_date=YYYYMMDD), write the
      result atomically to DuckDB ``daily_bars`` (delete-then-insert),
      validate row count, then commit.
3. Update task status and data-range metadata on completion.

Key properties:
- No CSV / file intermediaries; all data flows in-memory -> direct DB write.
- Single-day atomicity: if write or integrity check fails, the day is rolled
  back and the whole task is marked FAILED (resumable via reimport-day).
- One task may be RUNNING at a time (prevented by _task_lock + DB check).
- Idempotent: reimporting a day deletes existing rows then rewrites them.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.settings import settings

logger = logging.getLogger(__name__)

_task_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def is_trading_day(d: date) -> bool:
    """Return True if *d* is a Chinese A-share market trading day.

    Uses ChnCal for supported years; falls back to weekday-only check for
    years outside ChnCal's coverage window.
    """
    try:
        import chncal
        return chncal.is_tradeday(d)
    except (NotImplementedError, Exception):
        # ChnCal does not cover this year; weekday-only approximation.
        return d.weekday() < 5  # Mon-Fri


def _generate_date_list(start_date: str, end_date: str) -> list[str]:
    """Return all YYYYMMDD dates from *start_date* to *end_date* inclusive (ascending)."""
    start = datetime.strptime(start_date, '%Y%m%d').date()
    end = datetime.strptime(end_date, '%Y%m%d').date()
    result: list[str] = []
    current = start
    while current <= end:
        result.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return result


def _connect(sqlite_path: Path | None = None):
    from app.db.sqlite import connect_sqlite
    return connect_sqlite(sqlite_path)


def _connect_duckdb(duckdb_path: Path | None = None):
    from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_parent, ensure_duckdb_schema
    target = duckdb_path or settings.duckdb_path
    ensure_duckdb_parent(target)
    ensure_duckdb_schema(target)
    return connect_duckdb(target)


def _ensure_schema(sqlite_path: Path | None = None) -> None:
    from app.db.sqlite import ensure_sqlite_schema
    ensure_sqlite_schema(sqlite_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_task(
    start_date: str,
    end_date: str,
    mode: str = 'RANGE',
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    """Create a new init task record in SQLite and return it as a dict.

    *start_date* / *end_date*: YYYYMMDD format.
    *mode*: ``'RANGE'`` for a range import; ``'REIMPORT_DAY'`` for a single day.
    Raises ValueError if the Tushare token is not configured.
    """
    _ensure_schema(sqlite_path)

    from app.modules.market_data.data_source import _get_token
    if not _get_token():
        raise ValueError(
            'Tushare token not configured. '
            'Please set it via the initialization page before starting.'
        )

    dates = _generate_date_list(start_date, end_date)
    total_days = len(dates)
    trading_days = sum(
        1 for d in dates
        if is_trading_day(datetime.strptime(d, '%Y%m%d').date())
    )

    task_id = str(uuid.uuid4())
    created_at = _now_iso()

    conn = _connect(sqlite_path)
    try:
        conn.execute(
            '''
            INSERT INTO init_task (
                task_id, mode, start_date, end_date, status,
                total_days, processed_days, trading_days, done_trading_days,
                current_date, error_message, created_at, started_at, finished_at
            ) VALUES (?, ?, ?, ?, 'PENDING', ?, 0, ?, 0, '', '', ?, '', '')
            ''',
            (task_id, mode, start_date, end_date, total_days, trading_days, created_at),
        )
        conn.executemany(
            '''
            INSERT INTO init_task_day
                (task_id, trade_date, is_trading_day, status, row_count,
                 started_at, finished_at, error_message)
            VALUES (?, ?, ?, 'PENDING', 0, '', '', '')
            ''',
            [
                (
                    task_id,
                    d,
                    1 if is_trading_day(datetime.strptime(d, '%Y%m%d').date()) else 0,
                )
                for d in dates
            ],
        )
        conn.commit()
    finally:
        conn.close()

    task = get_task(task_id, sqlite_path)
    assert task is not None
    return task


def start_task(task_id: str, sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> bool:
    """Start processing a task in a background thread.

    Returns False (without starting) if another task is already RUNNING.
    """
    with _task_lock:
        conn = _connect(sqlite_path)
        try:
            row = conn.execute(
                "SELECT task_id FROM init_task WHERE status = 'RUNNING' LIMIT 1"
            ).fetchone()
            if row:
                return False

            updated = conn.execute(
                '''
                UPDATE init_task SET status = 'RUNNING', started_at = ?
                WHERE task_id = ? AND status IN ('PENDING', 'FAILED')
                ''',
                (_now_iso(), task_id),
            ).rowcount
            conn.commit()
        finally:
            conn.close()

    if not updated:
        return False

    thread = threading.Thread(
        target=_run_task,
        args=(task_id, sqlite_path, duckdb_path),
        daemon=True,
    )
    thread.start()
    return True


def get_task(task_id: str, sqlite_path: Path | None = None) -> dict[str, Any] | None:
    """Return the task record as a dict, or None if not found."""
    conn = _connect(sqlite_path)
    try:
        row = conn.execute(
            'SELECT * FROM init_task WHERE task_id = ?', (task_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_tasks(
    limit: int = 20,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return recent tasks ordered by created_at descending."""
    _ensure_schema(sqlite_path)
    conn = _connect(sqlite_path)
    try:
        rows = conn.execute(
            'SELECT * FROM init_task ORDER BY created_at DESC LIMIT ?', (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_task_days(
    task_id: str,
    page: int = 1,
    per_page: int = 50,
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    """Return paginated day details for a task."""
    offset = (page - 1) * per_page
    conn = _connect(sqlite_path)
    try:
        total = conn.execute(
            'SELECT COUNT(*) FROM init_task_day WHERE task_id = ?', (task_id,)
        ).fetchone()[0]
        rows = conn.execute(
            '''
            SELECT * FROM init_task_day
            WHERE task_id = ?
            ORDER BY trade_date ASC
            LIMIT ? OFFSET ?
            ''',
            (task_id, per_page, offset),
        ).fetchall()
        return {
            'task_id': task_id,
            'total': total,
            'page': page,
            'per_page': per_page,
            'days': [dict(r) for r in rows],
        }
    finally:
        conn.close()


def reimport_day(trade_date: str, sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> dict[str, Any]:
    """Create and immediately start a REIMPORT_DAY task for *trade_date* (YYYYMMDD).

    If another task is already RUNNING the new task will remain in PENDING state.
    """
    task = create_task(trade_date, trade_date, mode='REIMPORT_DAY', sqlite_path=sqlite_path)
    start_task(task['task_id'], sqlite_path=sqlite_path, duckdb_path=duckdb_path)
    return get_task(task['task_id'], sqlite_path) or task


def get_overview(sqlite_path: Path | None = None) -> dict[str, Any]:
    """Return high-level overview: running task, latest finished task, data range."""
    _ensure_schema(sqlite_path)
    conn = _connect(sqlite_path)
    try:
        running_row = conn.execute(
            "SELECT * FROM init_task WHERE status = 'RUNNING' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        latest_row = conn.execute(
            "SELECT * FROM init_task WHERE status IN ('SUCCESS', 'FAILED') "
            "ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        meta_row = conn.execute(
            "SELECT * FROM data_range_meta WHERE dataset = 'daily_bars'"
        ).fetchone()
        if not meta_row:
            meta_row = conn.execute(
                "SELECT * FROM data_range_meta WHERE dataset = 'market_daily_quote'"
            ).fetchone()
        return {
            'running_task': dict(running_row) if running_row else None,
            'latest_task': dict(latest_row) if latest_row else None,
            'data_range': {
                'min_trade_date': meta_row['min_trade_date'] if meta_row else None,
                'max_trade_date': meta_row['max_trade_date'] if meta_row else None,
                'trading_day_count': meta_row['trading_day_count'] if meta_row else 0,
            },
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Background task runner
# ---------------------------------------------------------------------------


def _run_task(task_id: str, sqlite_path: Path | None, duckdb_path: Path | None = None) -> None:
    """Background thread: process every date in the task's date range."""
    logger.info('Task %s: started', task_id)
    try:
        conn = _connect(sqlite_path)
        try:
            task_row = conn.execute(
                'SELECT * FROM init_task WHERE task_id = ?', (task_id,)
            ).fetchone()
        finally:
            conn.close()

        if not task_row:
            logger.error('Task %s: not found in DB', task_id)
            return

        dates = _generate_date_list(task_row['start_date'], task_row['end_date'])
        logger.info(
            'Task %s: processing %d calendar days (%s → %s)',
            task_id, len(dates), task_row['start_date'], task_row['end_date'],
        )

        for date_str in dates:
            # Returns False when the task must be aborted due to a fatal error.
            if not _process_one_day(task_id, date_str, sqlite_path, duckdb_path):
                return

        # All dates processed
        conn = _connect(sqlite_path)
        try:
            conn.execute(
                '''UPDATE init_task
                   SET status = 'SUCCESS', finished_at = ?, current_date = ''
                   WHERE task_id = ?''',
                (_now_iso(), task_id),
            )
            conn.commit()
        finally:
            conn.close()

        _update_data_range_meta(sqlite_path, duckdb_path)

        # Regenerate Parquet from DuckDB so the fallback read path is also up to date.
        try:
            _export_parquet(duckdb_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning('Task %s: Parquet export failed (non-fatal): %s', task_id, exc)
        logger.info('Task %s: completed successfully', task_id)

    except Exception as exc:
        logger.exception('Task %s: unexpected error: %s', task_id, exc)
        _mark_task_failed(task_id, str(exc), sqlite_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _process_one_day(
    task_id: str,
    date_str: str,
    sqlite_path: Path | None,
    duckdb_path: Path | None = None,
) -> bool:
    """Process a single calendar date for a running task.

    Returns True on success (or skip for non-trading day).
    Returns False when a fatal error occurred and the task must be aborted.
    """
    d = datetime.strptime(date_str, '%Y%m%d').date()
    trading = is_trading_day(d)

    logger.debug('Task %s: %s is_trading_day=%s', task_id, date_str, trading)

    # Update current_date and day status
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            'UPDATE init_task SET current_date = ? WHERE task_id = ?',
            (date_str, task_id),
        )
        conn.execute(
            '''UPDATE init_task_day SET started_at = ?, status = ?
               WHERE task_id = ? AND trade_date = ?''',
            (
                _now_iso(),
                'FETCHING' if trading else 'SKIPPED_NON_TRADING',
                task_id,
                date_str,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if not trading:
        return _skip_non_trading_day(task_id, date_str, sqlite_path)

    return _process_trading_day(task_id, date_str, sqlite_path, duckdb_path)


def _skip_non_trading_day(
    task_id: str,
    date_str: str,
    sqlite_path: Path | None,
) -> bool:
    """Mark a non-trading day as skipped and increment the processed counter."""
    logger.debug('Task %s: %s skipped (non-trading day)', task_id, date_str)
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            'UPDATE init_task_day SET finished_at = ? WHERE task_id = ? AND trade_date = ?',
            (_now_iso(), task_id, date_str),
        )
        conn.execute(
            'UPDATE init_task SET processed_days = processed_days + 1 WHERE task_id = ?',
            (task_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return True


def _process_trading_day(
    task_id: str,
    date_str: str,
    sqlite_path: Path | None,
    duckdb_path: Path | None = None,
) -> bool:
    """Fetch data from Tushare and atomically write it for a single trading day.

    Returns True on success, False on any fatal error.
    """
    t0 = time.monotonic()

    # Fetch
    logger.info('Task %s: fetching %s …', task_id, date_str)
    try:
        rows = _fetch_daily_raw(date_str, sqlite_path)
    except Exception as exc:
        logger.exception('Task %s: fetch failed for %s: %s', task_id, date_str, exc)
        _mark_day_failed(task_id, date_str, str(exc), sqlite_path)
        _mark_task_failed(task_id, f'Fetch failed on {date_str}: {exc}', sqlite_path)
        return False

    fetch_elapsed = time.monotonic() - t0
    logger.info(
        'Task %s: fetched %s — %d rows in %.1fs',
        task_id, date_str, len(rows), fetch_elapsed,
    )

    # Mark as WRITING
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            "UPDATE init_task_day SET status = 'WRITING' WHERE task_id = ? AND trade_date = ?",
            (task_id, date_str),
        )
        conn.commit()
    finally:
        conn.close()

    # Write atomically (SQLite + DuckDB)
    t1 = time.monotonic()
    try:
        _atomic_write_day(date_str, rows, sqlite_path, duckdb_path)
    except Exception as exc:
        logger.exception('Task %s: write failed for %s: %s', task_id, date_str, exc)
        _mark_day_failed(task_id, date_str, str(exc), sqlite_path)
        _mark_task_failed(task_id, f'Write failed on {date_str}: {exc}', sqlite_path)
        return False

    write_elapsed = time.monotonic() - t1

    # Day succeeded
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            '''UPDATE init_task_day
               SET status = 'SUCCESS', finished_at = ?, row_count = ?
               WHERE task_id = ? AND trade_date = ?''',
            (_now_iso(), len(rows), task_id, date_str),
        )
        conn.execute(
            '''UPDATE init_task
               SET processed_days = processed_days + 1,
                   done_trading_days = done_trading_days + 1
               WHERE task_id = ?''',
            (task_id,),
        )
        conn.commit()
    finally:
        conn.close()

    total_elapsed = time.monotonic() - t0
    logger.info(
        'Task %s: %s done — %d rows written (fetch=%.1fs write=%.1fs total=%.1fs)',
        task_id, date_str, len(rows), fetch_elapsed, write_elapsed, total_elapsed,
    )
    return True


def _fetch_daily_raw(
    date_str: str,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Fetch full-market daily quote from Tushare for *date_str* (YYYYMMDD).

    Returns a list of row dicts matching the fetched Tushare daily quote columns,
    including computed limit-up/down prices and ST flags.
    """
    from app.modules.market_data.data_source import _get_tushare_api, _rate_limited_call
    from app.modules.market_data.limit_rules import compute_limit_fields

    pro = _get_tushare_api()
    df = _rate_limited_call(pro.daily, trade_date=date_str)
    if df is None or df.empty:
        return []

    # Load stock universe metadata (name, list_date) for limit-field enrichment.
    # Gracefully skip when the stock_list table is empty or unavailable.
    name_map: dict[str, str] = {}
    list_date_map: dict[str, str] = {}
    try:
        conn = _connect(sqlite_path)
        try:
            univ_rows = conn.execute(
                'SELECT ts_code, name, list_date FROM stock_list'
            ).fetchall()
            for r in univ_rows:
                ts = r['ts_code']
                name_map[ts] = r['name'] or ''
                list_date_map[ts] = r['list_date'] or ''
        finally:
            conn.close()
    except Exception as _exc:  # noqa: BLE001
        logger.warning(
            '_fetch_daily_raw: could not load stock universe for %s, '
            'limit-field enrichment will be partial: %s',
            date_str, _exc,
        )

    updated_at = _now_iso()
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        try:
            ts_code = str(row['ts_code'])
            pre_close = float(row.get('pre_close') or 0)
            close = float(row.get('close') or 0)
            stock_name = name_map.get(ts_code, '')
            list_date = list_date_map.get(ts_code) or None

            limit_fields = compute_limit_fields(
                ts_code=ts_code,
                trade_date=date_str,
                pre_close=pre_close,
                close=close,
                stock_name=stock_name,
                list_date=list_date,
            )

            rows.append({
                'trade_date': date_str,
                'ts_code': ts_code,
                'open': float(row.get('open') or 0),
                'high': float(row.get('high') or 0),
                'low': float(row.get('low') or 0),
                'close': close,
                'pre_close': pre_close,
                'change': float(row.get('change') or 0),
                'pct_chg': float(row.get('pct_chg') or 0),
                'vol': float(row.get('vol') or 0),
                'amount': float(row.get('amount') or 0),
                'updated_at': updated_at,
                **limit_fields,
            })
        except (ValueError, TypeError):
            continue
    return rows


def _atomic_write_day(
    date_str: str,
    rows: list[dict[str, Any]],
    sqlite_path: Path | None,
    duckdb_path: Path | None = None,
) -> None:
    """Delete existing DuckDB rows for *date_str* then insert *rows* atomically.

    V2 keeps daily market quotes in DuckDB only; SQLite is reserved for task
    status / metadata tables.
    """
    _write_duckdb_day(date_str, rows, duckdb_path)


def _write_duckdb_day(
    date_str: str,
    rows: list[dict[str, Any]],
    duckdb_path: Path | None = None,
) -> None:
    """Write *rows* for *date_str* into DuckDB's ``daily_bars`` table.

    Maps fetched Tushare daily quote fields to the daily_bars schema:
    - ts_code (e.g. '000001.SZ') → stock_code ('000001')
    - trade_date 'YYYYMMDD' → 'YYYY-MM-DD'
    - open/high/low/close → open_price/high_price/low_price/close_price
    - vol (lots) → volume (integer)
    - amount (千元) / 1e6 → turnover_amount_billion

    Deletes existing rows for the date before inserting (idempotent).
    """
    trade_date_str = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'

    duckdb_rows = [
        (
            str(r['ts_code']).split('.')[0].zfill(6),  # stock_code
            trade_date_str,
            float(r['open']),
            float(r['high']),
            float(r['low']),
            float(r['close']),
            int(float(r['vol'])),
            round(float(r.get('amount') or 0) / 1e6, 4),
            bool(r.get('is_limit_up', False)),   # is_up_limit
            bool(r.get('is_limit_down', False)),  # is_down_limit
        )
        for r in rows
    ]

    conn = _connect_duckdb(duckdb_path)
    try:
        conn.execute('BEGIN TRANSACTION')
        conn.execute('DELETE FROM daily_bars WHERE trade_date = ?', [trade_date_str])
        if duckdb_rows:
            conn.executemany(
                'INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                duckdb_rows,
            )
        written = conn.execute(
            'SELECT COUNT(*) FROM daily_bars WHERE trade_date = ?', [trade_date_str]
        ).fetchone()[0]
        if written != len(duckdb_rows):
            conn.rollback()
            raise RuntimeError(
                f'DuckDB integrity check failed for {trade_date_str}: '
                f'expected {len(duckdb_rows)} rows, got {written}'
            )
        conn.commit()
        logger.debug(
            '_write_duckdb_day: %s → %d rows written to daily_bars', date_str, len(duckdb_rows)
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _export_parquet(duckdb_path: Path | None = None) -> None:
    """Re-export all daily_bars rows from DuckDB to the Parquet fallback file."""
    from app.core.settings import settings as _settings
    parquet_path = _settings.daily_bars_parquet_path
    target_duckdb = duckdb_path or _settings.duckdb_path

    conn = _connect_duckdb(target_duckdb)
    try:
        parquet_path.unlink(missing_ok=True)
        parquet_str = str(parquet_path).replace('\\', '/').replace("'", "''")
        conn.execute(
            f"COPY (SELECT * FROM daily_bars ORDER BY stock_code, trade_date) "
            f"TO '{parquet_str}' (FORMAT PARQUET)"
        )
        logger.info('_export_parquet: Parquet file regenerated at %s', parquet_path)
    finally:
        conn.close()


def _mark_day_failed(
    task_id: str,
    date_str: str,
    error_message: str,
    sqlite_path: Path | None,
) -> None:
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            '''UPDATE init_task_day
               SET status = 'FAILED', finished_at = ?, error_message = ?
               WHERE task_id = ? AND trade_date = ?''',
            (_now_iso(), error_message, task_id, date_str),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_task_failed(
    task_id: str,
    error_message: str,
    sqlite_path: Path | None,
) -> None:
    conn = _connect(sqlite_path)
    try:
        conn.execute(
            '''UPDATE init_task
               SET status = 'FAILED', finished_at = ?, error_message = ?
               WHERE task_id = ?''',
            (_now_iso(), error_message, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def _update_data_range_meta(sqlite_path: Path | None, duckdb_path: Path | None = None) -> None:
    """Refresh data_range_meta from DuckDB daily_bars contents."""
    dconn = _connect_duckdb(duckdb_path)
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

    conn = _connect(sqlite_path)
    try:
        conn.execute(
                '''INSERT OR REPLACE INTO data_range_meta
                   (dataset, min_trade_date, max_trade_date, trading_day_count, updated_at)
                   VALUES ('daily_bars', ?, ?, ?, ?)''',
                (str(row[0]), str(row[1]), int(row[2]), _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Legacy compatibility shim (supports old /status endpoint)
# ---------------------------------------------------------------------------


def read_init_status(status_dir: Any = None) -> dict[str, Any]:  # noqa: ARG001
    """Return current init state in the legacy format (reads from SQLite)."""
    try:
        overview = get_overview()
        task = overview.get('running_task') or overview.get('latest_task')
        if not task:
            return _idle_status()
        status_map = {
            'PENDING': 'idle',
            'RUNNING': 'running',
            'SUCCESS': 'done',
            'FAILED': 'error',
        }
        return {
            'status': status_map.get(task['status'], 'idle'),
            'trade_date': task.get('current_date', ''),
            'total_stocks': task.get('total_days', 0),
            'processed_stocks': task.get('processed_days', 0),
            'started_at': task.get('started_at', ''),
            'finished_at': task.get('finished_at', ''),
            'error_message': task.get('error_message', ''),
        }
    except Exception:  # noqa: BLE001
        return _idle_status()


def _idle_status() -> dict[str, Any]:
    return {
        'status': 'idle',
        'trade_date': '',
        'total_stocks': 0,
        'processed_stocks': 0,
        'started_at': '',
        'finished_at': '',
        'error_message': '',
    }
