"""Market data initialization V2.

Date-driven approach:
1. Create a task with start_date / end_date (YYYYMMDD format).
2. For each calendar date in the range (ascending order):
   - call tushare pro.daily(trade_date=YYYYMMDD)
   - atomically write rows to DuckDB ``daily_bars`` (delete-then-insert)
   - mark day success even when Tushare returns empty rows
3. Update task status and data-range metadata on completion.

Key properties:
- No CSV / file intermediaries; all data flows in-memory -> direct DB write.
- Single-day atomicity: if fetch/write fails, the day and task are marked FAILED.
- One task may be RUNNING at a time (prevented by _task_lock + DB check).
- Supports explicit task termination and retry.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.repositories.init_task_repo import InitTaskRepo

logger = logging.getLogger(__name__)

_task_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


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


def _task_repo(sqlite_path: Path | None = None) -> InitTaskRepo:
    return InitTaskRepo(sqlite_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_task(
    start_date: str,
    end_date: str,
    mode: str = 'RANGE',
    task_type: str = 'MARKET_DATA',
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    """Create a new init task record in SQLite and return it as a dict.

    *start_date* / *end_date*: YYYYMMDD format.
    *mode*: ``'RANGE'`` for a range import; ``'REIMPORT_DAY'`` for a single day.
    *task_type*: ``'MARKET_DATA'`` or ``'JYGS_REVIEW'``.

    Raises ValueError if credentials not configured (Tushare for MARKET_DATA, JYGS for JYGS_REVIEW).
    """
    _ensure_schema(sqlite_path)

    # Validate credentials based on task type
    if task_type == 'MARKET_DATA':
        from app.modules.market_data.data_source import _get_token
        if not _get_token():
            raise ValueError(
                'Tushare token not configured. '
                'Please set it via the initialization page before starting.'
            )
    elif task_type == 'JYGS_REVIEW':
        from app.modules.jygs.auth import load_credentials
        if not load_credentials():
            raise ValueError(
                'JYGS credentials not configured. '
                'Please login via韭研公社 connection page before starting.'
            )
    else:
        raise ValueError(f'Unknown task_type: {task_type}')

    dates = _generate_date_list(start_date, end_date)
    total_days = len(dates)
    trading_days = total_days

    task_id = str(uuid.uuid4())
    created_at = _now_iso()

    repo = _task_repo(sqlite_path)
    repo.create_task_with_days(
        task_id=task_id,
        task_type=task_type,
        mode=mode,
        start_date=start_date,
        end_date=end_date,
        total_days=total_days,
        trading_days=trading_days,
        created_at=created_at,
        dates=dates,
    )

    task = get_task(task_id, sqlite_path)
    assert task is not None
    return task


def start_task(task_id: str, sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> bool:
    """Start processing a task in a background thread.

    Returns False (without starting) if another task is already RUNNING.
    """
    repo = _task_repo(sqlite_path)
    with _task_lock:
        if repo.find_running_task_id():
            return False
        updated = repo.try_mark_task_running(task_id, _now_iso())

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
    return _task_repo(sqlite_path).get_task(task_id)


def list_tasks(
    limit: int = 20,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return recent tasks ordered by created_at descending."""
    _ensure_schema(sqlite_path)
    return _task_repo(sqlite_path).list_tasks(limit)


def get_task_days(
    task_id: str,
    page: int = 1,
    per_page: int = 50,
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    """Return paginated day details for a task."""
    return _task_repo(sqlite_path).get_task_days_page(task_id, page, per_page)


def reimport_day(trade_date: str, sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> dict[str, Any]:
    """Create and immediately start a REIMPORT_DAY task for *trade_date* (YYYYMMDD).

    If another task is already RUNNING the new task will remain in PENDING state.
    """
    task = create_task(trade_date, trade_date, mode='REIMPORT_DAY', sqlite_path=sqlite_path)
    start_task(task['task_id'], sqlite_path=sqlite_path, duckdb_path=duckdb_path)
    return get_task(task['task_id'], sqlite_path) or task


def retry_task(task_id: str, sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> dict[str, Any] | None:
    """Reset a FAILED task and restart it.

    Returns the updated task, or None when task doesn't exist / cannot be retried.
    """
    repo = _task_repo(sqlite_path)
    with _task_lock:
        status = repo.get_task_status(task_id)
        if status != 'FAILED':
            return None
        if repo.find_running_task_id():
            return None
        repo.reset_task_for_retry(task_id, _now_iso())

    started = start_task(task_id, sqlite_path=sqlite_path, duckdb_path=duckdb_path)
    if not started:
        return None
    return get_task(task_id, sqlite_path)


def terminate_task(task_id: str, sqlite_path: Path | None = None) -> dict[str, Any] | None:
    """Terminate a RUNNING/FAILED/PENDING task and mark it TERMINATED."""
    updated = _task_repo(sqlite_path).terminate_task(task_id, _now_iso())
    if not updated:
        return None
    return get_task(task_id, sqlite_path)


def get_overview(sqlite_path: Path | None = None) -> dict[str, Any]:
    """Return high-level overview: running task, latest finished task, data range."""
    _ensure_schema(sqlite_path)
    repo = _task_repo(sqlite_path)
    running_row = repo.get_running_task()
    latest_row = repo.get_latest_finished_task()
    meta_row = repo.get_data_range_meta()
    return {
        'running_task': running_row,
        'latest_task': latest_row,
        'data_range': {
            'min_trade_date': meta_row['min_trade_date'] if meta_row else None,
            'max_trade_date': meta_row['max_trade_date'] if meta_row else None,
            'trading_day_count': meta_row['trading_day_count'] if meta_row else 0,
        },
    }


# ---------------------------------------------------------------------------
# Background task runner
# ---------------------------------------------------------------------------


def _run_task(task_id: str, sqlite_path: Path | None, duckdb_path: Path | None = None) -> None:
    """Background thread: process every date in the task's date range."""
    logger.info('Task %s: started', task_id)
    try:
        task_row = _task_repo(sqlite_path).get_task(task_id)

        if not task_row:
            logger.error('Task %s: not found in DB', task_id)
            return

        task = dict(task_row)
        task_type = task.get('task_type', 'MARKET_DATA')
        dates = _generate_date_list(task['start_date'], task['end_date'])
        logger.info(
            'Task %s: started for type=%s, processing %d calendar days (%s → %s)',
            task_id, task_type, len(dates), task['start_date'], task['end_date'],
        )

        for date_str in dates:
            if _is_task_terminated(task_id, sqlite_path):
                logger.info('Task %s: terminated by user before processing %s', task_id, date_str)
                return
            # Returns False when the task must be aborted due to a fatal error.
            if not _process_one_day(task_id, date_str, sqlite_path, duckdb_path, task_type):
                return

        # All dates processed
        updated = _task_repo(sqlite_path).finalize_task_success_if_running(task_id, _now_iso())

        if not updated:
            logger.info('Task %s: skipped SUCCESS finalization because task is no longer RUNNING', task_id)
            return

        # Only update data_range_meta and export parquet for MARKET_DATA tasks
        if task_type == 'MARKET_DATA':
            _update_data_range_meta(sqlite_path, duckdb_path)
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
    task_type: str = 'MARKET_DATA',
) -> bool:
    """Process a single calendar date for a running task.

    Returns True on success (including empty fetch responses).
    Returns False when a fatal error occurred and the task must be aborted.
    """
    logger.debug('Task %s: processing %s (type=%s)', task_id, date_str, task_type)

    # Update current_date and set status to RUNNING
    _task_repo(sqlite_path).set_current_date_and_mark_day_running(task_id, date_str, _now_iso())

    # Dispatch to appropriate processor based on task_type
    if task_type == 'JYGS_REVIEW':
        return _process_jygs_review_day(task_id, date_str, sqlite_path)
    else:  # Default to MARKET_DATA
        return _process_trading_day(task_id, date_str, sqlite_path, duckdb_path)


def _process_trading_day(
    task_id: str,
    date_str: str,
    sqlite_path: Path | None,
    duckdb_path: Path | None = None,
) -> bool:
    """Fetch data from Tushare and atomically write it for a single calendar date.

    Empty responses are treated as successful writes of zero rows.
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
    _task_repo(sqlite_path).mark_day_writing(task_id, date_str)

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
    _task_repo(sqlite_path).mark_day_success_and_increment(task_id, date_str, _now_iso(), len(rows))

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
    logger.info('_fetch_daily_raw start. trade_date=%s', date_str)
    df = _rate_limited_call(pro.daily, trade_date=date_str)
    if df is None or df.empty:
        logger.info('_fetch_daily_raw empty response. trade_date=%s', date_str)
        return []
    logger.info('_fetch_daily_raw raw dataframe received. trade_date=%s rows=%d', date_str, len(df))

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
    logger.info('_fetch_daily_raw parsed rows. trade_date=%s rows=%d', date_str, len(rows))
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

    Stores all 13 spec-defined columns:
    - ts_code (e.g. '000001.SZ') stored as-is
    - trade_date 'YYYYMMDD' → 'YYYY-MM-DD' for consistent internal format
    - open, high, low, close, pre_close, change, pct_chg from Tushare row
    - vol stored as float (lots)
    - amount (千元) / 1e6 stored in units matching turnover_amount_billion display
    - is_up_limit / is_down_limit from compute_limit_fields output

    Deletes existing rows for the date before inserting (idempotent).
    """
    trade_date_str = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'

    duckdb_rows = [
        (
            str(r['ts_code']),                            # ts_code (full format)
            trade_date_str,
            float(r['open']),
            float(r['high']),
            float(r['low']),
            float(r['close']),
            float(r.get('pre_close') or 0),
            float(r.get('change') or 0),
            float(r.get('pct_chg') or 0),
            float(r.get('vol') or 0),
            round(float(r.get('amount') or 0)),  # 千元
            bool(r.get('is_limit_up', False)),              # is_up_limit
            bool(r.get('is_limit_down', False)),            # is_down_limit
        )
        for r in rows
    ]

    conn = _connect_duckdb(duckdb_path)
    try:
        conn.execute('BEGIN TRANSACTION')
        conn.execute('DELETE FROM daily_bars WHERE trade_date = ?', [trade_date_str])
        if duckdb_rows:
            conn.executemany(
                'INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
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
            f"COPY (SELECT * FROM daily_bars ORDER BY ts_code, trade_date) "
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
    _task_repo(sqlite_path).mark_day_failed(task_id, date_str, _now_iso(), error_message)


def _mark_task_failed(
    task_id: str,
    error_message: str,
    sqlite_path: Path | None,
) -> None:
    _task_repo(sqlite_path).mark_task_failed(task_id, _now_iso(), error_message)


def _is_task_terminated(task_id: str, sqlite_path: Path | None) -> bool:
    return _task_repo(sqlite_path).is_task_terminated(task_id)


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
            'TERMINATED': 'error',
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


def _process_jygs_review_day(
    task_id: str,
    date_str: str,
    sqlite_path: Path | None,
) -> bool:
    """Fetch and parse JYGS review data for a single date.

    Returns True on success (including empty responses).
    Returns False on fatal error.
    """
    t0 = time.monotonic()

    try:
        # Import here to avoid circular dependency
        from app.modules.market_data.jygs_review import fetch_and_parse_jygs_review_for_date

        review_count = fetch_and_parse_jygs_review_for_date(date_str)
        elapsed = time.monotonic() - t0

        # Mark day as SUCCESS and advance overall task progress.
        _task_repo(sqlite_path).mark_day_success_and_increment(
            task_id,
            date_str,
            _now_iso(),
            review_count,
        )

        logger.info(
            'Task %s: %s SUCCESS (parsed %d reviews in %.1fs)',
            task_id, date_str, review_count, elapsed,
        )
        return True

    except Exception as exc:
        elapsed = time.monotonic() - t0
        error_msg = str(exc)[:500]

        repo = _task_repo(sqlite_path)
        repo.mark_day_failed(task_id, date_str, _now_iso(), error_msg)
        # Keep prior behavior: JYGS day failure is counted as processed and task continues.
        repo.mark_task_progress_processed_only(task_id)

        logger.error(
            'Task %s: %s FAILED in %.1fs: %s',
            task_id, date_str, elapsed, error_msg,
        )
        # Return True to continue processing other days, only False for fatal errors
        return True

