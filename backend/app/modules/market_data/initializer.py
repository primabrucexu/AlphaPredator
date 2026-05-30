"""Market data initialization V2.

Task types:
- STOCK_LIST_SYNC: Fetch stock list from Mairui and persist to SQLite.  No date
  range iteration; finishes in one step.
- MARKET_DATA (FULL_SYNC): Fetch all historical daily bars for every stock in
  the provided date range.
- MARKET_DATA (INCREMENTAL_SYNC): Automatically detect the latest trade date in
  DuckDB ``day_level_trade_data`` and fetch only newer data.
- JYGS_REVIEW: Fetch and parse JYGS hotlist review data date by date.

Key properties:
- No CSV / file intermediaries; all data flows in-memory -> direct DB write.
- One task may be RUNNING at a time (prevented by _task_lock + DB check).
- Supports explicit task termination and retry.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_parent, ensure_duckdb_schema
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.data_source import _get_mairui_licence, _resolve_stock_universe, \
    _mairui_fetch_history_rows, UnlistedStockSkipError, fetch_daily_bars_by_date, sync_stock_list_to_sqlite
from app.modules.market_data.jygs_review import check_jygs_auth_available, fetch_and_parse_jygs_review_for_date
from app.modules.market_data.limit_rules import compute_limit_fields
from app.repositories.init_task_repo import InitTaskRepo

logger = logging.getLogger(__name__)

_task_lock = threading.Lock()
_scoped_retry_lock = threading.Lock()
_scoped_retry_labels: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _generate_date_list(start_date: str, end_date: str, *, weekdays_only: bool = False) -> list[str]:
    """Return all YYYYMMDD dates from *start_date* to *end_date* inclusive (ascending).

    *weekdays_only*: when True, skip weekends (Saturday=5, Sunday=6).
    Used for JYGS_REVIEW to avoid fetching non-trading days.
    """
    start = datetime.strptime(start_date, '%Y%m%d').date()
    end = datetime.strptime(end_date, '%Y%m%d').date()
    result: list[str] = []
    current = start
    while current <= end:
        if not weekdays_only or current.weekday() < 5:  # 0=Mon … 4=Fri, 5=Sat, 6=Sun
            result.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return result


def _connect(sqlite_path: Path | None = None):
    return connect_sqlite(sqlite_path)


def _connect_duckdb(duckdb_path: Path | None = None):
    target = duckdb_path or settings.duckdb_path
    ensure_duckdb_parent(target)
    ensure_duckdb_schema(target)
    return connect_duckdb(target)


def _ensure_schema(sqlite_path: Path | None = None) -> None:
    ensure_sqlite_schema(sqlite_path)


def _task_repo(sqlite_path: Path | None = None) -> InitTaskRepo:
    return InitTaskRepo(sqlite_path)


def _to_decimal(value: Any, default: str = '0') -> Decimal:
    """Parse provider numeric fields as Decimal to keep exact arithmetic."""
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return Decimal(default)
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_task(
    start_date: str,
    end_date: str,
        mode: str = 'FULL_SYNC',
    task_type: str = 'MARKET_DATA',
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    """Create a new init task record in SQLite and return it as a dict.

    *start_date* / *end_date*: YYYYMMDD format.
    *mode*: Ignored; kept for API backward compat. Time range is determined by task_type.
    *task_type*: ``'STOCK_LIST_SYNC'`` | ``'MARKET_DATA'`` | ``'JYGS_REVIEW'``.

    Raises ValueError if credentials not configured.
    """
    _ensure_schema(sqlite_path)

    # Validate credentials based on task type
    if task_type in ('MARKET_DATA', 'STOCK_LIST_SYNC'):
        if not _get_mairui_licence():
            raise ValueError(
                'Market data credentials not configured. '
                'Please set Mairui licence via the initialization page before starting.'
            )
    elif task_type == 'JYGS_REVIEW':
        try:
            auth_result = check_jygs_auth_available(sqlite_path)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f'韭研公社凭据校验失败，请重新登录后再启动任务。错误：{exc}'
            ) from exc
        if not auth_result.get('is_valid'):
            error = auth_result.get('last_error') or '凭据无效或未登录'
            raise ValueError(
                f'韭研公社凭据无效，请重新登录后再启动任务。错误：{error}'
            )
    else:
        raise ValueError(f'Unknown task_type: {task_type}')

    # Determine total_items based on task type
    if task_type == 'STOCK_LIST_SYNC':
        today = datetime.now().strftime('%Y%m%d')
        start_date = today
        end_date = today
        total_items = 1
    elif task_type == 'JYGS_REVIEW':
        # Date-based loop: total_items = number of weekdays (skip weekends)
        dates = _generate_date_list(start_date, end_date, weekdays_only=True)
        total_items = len(dates)
    else:  # MARKET_DATA
        # Stock-based loop: total_items will be set after resolving stock universe in _run_task
        total_items = 0

    task_id = str(uuid.uuid4())

    repo = _task_repo(sqlite_path)
    repo.create_task_with_days(
        task_id=task_id,
        task_type=task_type,
        start_date=start_date,
        end_date=end_date,
        total_items=total_items,
    )

    task = get_task(task_id, sqlite_path)
    assert task is not None
    return task


def start_task(task_id: str, sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> bool:
    """Start processing a task in a background thread.

    Returns False (without starting) if another task of the same type is already RUNNING.
    Different task types (STOCK_LIST_SYNC / MARKET_DATA / JYGS_REVIEW) may run in parallel.
    """
    repo = _task_repo(sqlite_path)
    with _task_lock:
        task = repo.get_task(task_id)
        if task is None:
            return False
        task_type = task.get('task_type', 'MARKET_DATA')
        if repo.find_running_task_id_by_type(task_type):
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
    """Return recent tasks ordered by latest inserted id descending."""
    _ensure_schema(sqlite_path)
    return _task_repo(sqlite_path).list_tasks(limit)



def reimport_day(trade_date: str, sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> dict[str, Any]:
    """Create and immediately start a one-day MARKET_DATA task for *trade_date* (YYYYMMDD).

    If another task is already RUNNING the new task will remain in PENDING state.
    """
    task = create_task(trade_date, trade_date, task_type='MARKET_DATA', sqlite_path=sqlite_path)
    start_task(task['task_id'], sqlite_path=sqlite_path, duckdb_path=duckdb_path)
    return get_task(task['task_id'], sqlite_path) or task


def retry_task(task_id: str, sqlite_path: Path | None = None, duckdb_path: Path | None = None) -> dict[str, Any] | None:
    """Resume a FAILED/TERMINATED task and restart it.

    Returns the updated task, or None when task doesn't exist / cannot be retried.
    """
    repo = _task_repo(sqlite_path)
    with _task_lock:
        task = repo.get_task(task_id)
        if task is None:
            return None
        status = task.get('status')
        if status not in ('FAILED', 'TERMINATED'):
            return None
        task_type = task.get('task_type', 'MARKET_DATA')
        if repo.find_running_task_id_by_type(task_type):
            return None
        repo.prepare_task_for_resume(task_id, keep_current_label=(status == 'FAILED'))

    started = start_task(task_id, sqlite_path=sqlite_path, duckdb_path=duckdb_path)
    if not started:
        return None
    return get_task(task_id, sqlite_path)


def _normalize_retry_item_label(task_type: str, label: str) -> str:
    text = str(label or '').strip().upper()
    if not text:
        raise ValueError('item_label cannot be empty')
    if task_type == 'MARKET_DATA':
        code = text.split('.')[0].zfill(6)
        if code.startswith('6'):
            return f'{code}.SH'
        if code.startswith(('8', '4')):
            return f'{code}.BJ'
        return f'{code}.SZ'
    if task_type == 'JYGS_REVIEW':
        digits = ''.join(ch for ch in text if ch.isdigit())
        if len(digits) != 8:
            raise ValueError('JYGS_REVIEW item_label must be YYYYMMDD')
        return digits
    return text


def retry_subtask(
        task_id: str,
        item_label: str,
        sqlite_path: Path | None = None,
        duckdb_path: Path | None = None,
) -> dict[str, Any] | None:
    """Create and start a new scoped retry task for one subtask item.

    - MARKET_DATA: retry one stock (item_label: stock code/full_code)
    - JYGS_REVIEW: retry one date (item_label: YYYYMMDD)
    - STOCK_LIST_SYNC: no real subtask dimension; rejected
    """
    parent = get_task(task_id, sqlite_path)
    if not parent:
        return None

    task_type = str(parent.get('task_type') or 'MARKET_DATA')
    if task_type == 'STOCK_LIST_SYNC':
        raise ValueError('STOCK_LIST_SYNC has no retryable subtask item')

    scoped_label = _normalize_retry_item_label(task_type, item_label)

    repo = _task_repo(sqlite_path)
    with _task_lock:
        if repo.find_running_task_id_by_type(task_type):
            return None

    new_task = create_task(
        str(parent.get('start_date') or ''),
        str(parent.get('end_date') or ''),
        task_type=task_type,
        sqlite_path=sqlite_path,
    )

    # Store scoped retry selector in memory so current_label remains a pure
    # progress/checkpoint marker in DB.
    with _scoped_retry_lock:
        _scoped_retry_labels[new_task['task_id']] = scoped_label
    repo.set_total_items(new_task['task_id'], 1)

    started = start_task(new_task['task_id'], sqlite_path=sqlite_path, duckdb_path=duckdb_path)
    if not started:
        with _scoped_retry_lock:
            _scoped_retry_labels.pop(new_task['task_id'], None)
        return None
    return get_task(new_task['task_id'], sqlite_path)


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
    range_row = repo.get_market_data_range()
    return {
        'running_task': running_row,
        'latest_task': latest_row,
        'data_range': {
            'min_trade_date': range_row['min_trade_date'] if range_row else None,
            'max_trade_date': range_row['max_trade_date'] if range_row else None,
        },
    }


# ---------------------------------------------------------------------------
# Background task runner
# ---------------------------------------------------------------------------


def _run_task(task_id: str, sqlite_path: Path | None, duckdb_path: Path | None = None) -> None:
    """Background thread: process task items based on task_type."""
    logger.info('Task %s: started', task_id)
    try:
        task_row = _task_repo(sqlite_path).get_task(task_id)

        if not task_row:
            logger.error('Task %s: not found in DB', task_id)
            return

        task = dict(task_row)
        task_type = task.get('task_type', 'MARKET_DATA')
        with _scoped_retry_lock:
            scoped_retry_label = _scoped_retry_labels.pop(task_id, '').strip().upper()
        resume_label = str(task.get('current_label') or '').strip().upper()
        resume_processed = int(task.get('processed_items') or 0)

        failed_items: list[str] = []
        first_failed_label: str | None = None

        if task_type == 'STOCK_LIST_SYNC':
            # ── 股票列表同步：只调一次 Mairui API ─────────────
            logger.info('Task %s: running stock list sync (force=True)', task_id)
            try:
                df = sync_stock_list_to_sqlite(sqlite_path=sqlite_path, force=True)
                row_count = len(df)
                logger.info('Task %s: stock list sync done, %d rows', task_id, row_count)
                _task_repo(sqlite_path).increment_processed_items(task_id)
            except Exception as exc:
                logger.exception('Task %s: stock list sync failed: %s', task_id, exc)
                _task_repo(sqlite_path).mark_task_failed(task_id, _now_iso(), str(exc))
                return

        elif task_type == 'MARKET_DATA':
            # ── 股票级别行情数据同步 ────────────────────────────────────────────
            start_date = task['start_date']
            end_date = task['end_date']

            all_stocks_df = _resolve_stock_universe(
                market_filters=None,
                sqlite_path=sqlite_path,
                use_uploaded_universe=True,
            )
            stock_list_df = all_stocks_df
            if scoped_retry_label:
                stock_list_df = stock_list_df[
                    stock_list_df['full_code'].astype(str).str.upper() == scoped_retry_label
                    ].copy()
                if stock_list_df.empty:
                    raise RuntimeError(f'Retry stock not found in stock_list: {scoped_retry_label}')
                _task_repo(sqlite_path).set_processed_items(task_id, 0)
            else:
                start_idx = 0
                if resume_label:
                    matched = all_stocks_df.index[
                        all_stocks_df['full_code'].astype(str).str.upper() == resume_label
                        ].tolist()
                    if matched:
                        start_idx = int(matched[0])
                elif resume_processed > 0:
                    start_idx = min(resume_processed, len(all_stocks_df))

                if start_idx > 0:
                    stock_list_df = all_stocks_df.iloc[start_idx:].copy()
                    _task_repo(sqlite_path).set_processed_items(task_id, start_idx)
                else:
                    _task_repo(sqlite_path).set_processed_items(task_id, 0)

            total_stocks = len(stock_list_df)
            logger.info(
                'Task %s: MARKET_DATA, processing %d stocks (%s → %s)',
                task_id, total_stocks, start_date, end_date,
            )

            # Keep total_items as full universe size for stable resume progress.
            _task_repo(sqlite_path).set_total_items(task_id, len(all_stocks_df))

            for idx, (_, stock) in enumerate(stock_list_df.iterrows()):
                if _is_task_terminated(task_id, sqlite_path):
                    logger.info('Task %s: terminated by user after processing %d/%d stocks', task_id, idx, total_stocks)
                    return
                stock_code = str(stock['full_code']).strip().upper()
                if not stock_code:
                    continue
                ok, err = _process_one_stock(task_id, stock_code, start_date, end_date, sqlite_path, duckdb_path)
                if not ok:
                    if first_failed_label is None:
                        first_failed_label = stock_code
                    failed_items.append(f'{stock_code}: {err}')
                    logger.warning('Task %s: continue after stock failure %s', task_id, stock_code)

            logger.info('Task %s: completed %d stocks', task_id, total_stocks)

        else:  # JYGS_REVIEW
            # ── 韭研公社复盘：按日期迭代 ──────────────────────────────────────
            dates = _generate_date_list(task['start_date'], task['end_date'], weekdays_only=True)
            total_dates = len(dates)
            if scoped_retry_label:
                dates = [d for d in dates if d == scoped_retry_label]
                if not dates:
                    raise RuntimeError(
                        f'Retry date {scoped_retry_label} not in task range '
                        f"{task['start_date']}~{task['end_date']}"
                    )

                _task_repo(sqlite_path).set_total_items(task_id, 1)
                _task_repo(sqlite_path).set_processed_items(task_id, 0)
            else:
                start_idx = 0
                if resume_label:
                    try:
                        start_idx = dates.index(resume_label)
                    except ValueError:
                        start_idx = 0
                elif resume_processed > 0:
                    start_idx = min(resume_processed, len(dates))

                if start_idx > 0:
                    dates = dates[start_idx:]
                    _task_repo(sqlite_path).set_processed_items(task_id, start_idx)
                else:
                    _task_repo(sqlite_path).set_processed_items(task_id, 0)
                _task_repo(sqlite_path).set_total_items(task_id, total_dates)
            logger.info(
                'Task %s: started for JYGS_REVIEW, processing %d dates (%s → %s)',
                task_id, len(dates), task['start_date'], task['end_date'],
            )

            for date_str in dates:
                if _is_task_terminated(task_id, sqlite_path):
                    logger.info('Task %s: terminated by user before processing %s', task_id, date_str)
                    return
                ok, err = _process_jygs_review_day(task_id, date_str, sqlite_path)
                if not ok:
                    if first_failed_label is None:
                        first_failed_label = date_str
                    failed_items.append(f'{date_str}: {err}')
                    logger.warning('Task %s: continue after JYGS_REVIEW failure %s', task_id, date_str)

        if failed_items:
            sample = '; '.join(failed_items[:20])
            more = f' ... and {len(failed_items) - 20} more' if len(failed_items) > 20 else ''
            summary = f'{len(failed_items)} subtask(s) failed: {sample}{more}'
            if first_failed_label:
                _task_repo(sqlite_path).set_current_label(task_id, first_failed_label)
            _task_repo(sqlite_path).mark_task_failed(task_id, _now_iso(), summary)
            logger.warning('Task %s: completed with subtask failures (%d)', task_id, len(failed_items))
            return

        # All items processed
        updated = _task_repo(sqlite_path).finalize_task_success_if_running(task_id, _now_iso())

        if not updated:
            logger.info('Task %s: skipped SUCCESS finalization because task is no longer RUNNING', task_id)
            return

        # Only export parquet for MARKET_DATA tasks
        if task_type == 'MARKET_DATA':
            try:
                _export_parquet(duckdb_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning('Task %s: Parquet export failed (non-fatal): %s', task_id, exc)

        logger.info('Task %s: completed successfully', task_id)

    except Exception as exc:
        logger.exception('Task %s: unexpected error: %s', task_id, exc)
        _task_repo(sqlite_path).mark_task_failed(task_id, _now_iso(), str(exc))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _process_one_stock(
    task_id: str,
        stock_code: str,
        start_date: str,
        end_date: str,
    sqlite_path: Path | None,
    duckdb_path: Path | None = None,
) -> tuple[bool, str]:
    """Fetch and write daily bars for a single stock across a date range.

    Returns (True, '') on success, (False, error_message) on failure.
    Note: Progress tracking is done at the task level in _run_task().
    """
    t0 = time.monotonic()

    stock_name = ''
    try:
        conn = _connect(sqlite_path)
        try:
            row = conn.execute(
                'SELECT name FROM stock_list WHERE full_code = ?',
                [stock_code]
            ).fetchone()
            if row:
                stock_name = row['name'] or ''
        finally:
            conn.close()
    except Exception:
        pass

    _task_repo(sqlite_path).set_current_label(task_id, stock_code)

    # Fetch all daily bars for this stock across the entire date range
    logger.info('Task %s: fetching %s [%s ~ %s] …', task_id, stock_code, start_date, end_date)
    try:
        raw_rows = _mairui_fetch_history_rows(stock_code, start_date, end_date)
    except UnlistedStockSkipError as exc:
        logger.info('Task %s: skip %s: %s', task_id, stock_code, exc)
        _task_repo(sqlite_path).increment_processed_items(task_id)
        return True, ''
    except Exception as exc:
        logger.exception('Task %s: fetch failed for %s: %s', task_id, stock_code, exc)
        return False, f'Fetch failed for {stock_code}: {exc}'

    fetch_elapsed = time.monotonic() - t0
    logger.info(
        'Task %s: fetched %s — %d rows in %.1fs',
        task_id, stock_code, len(raw_rows), fetch_elapsed,
    )

    if not raw_rows:
        # No data for this stock in the date range, mark as success anyway
        logger.info('Task %s: %s has no data in range, skip write', task_id, stock_code)
        _task_repo(sqlite_path).increment_processed_items(task_id)
        return True, ''

    # Enrich rows with limit fields
    t1 = time.monotonic()
    updated_at = _now_iso()
    enriched_rows: list[dict[str, Any]] = []
    name_map = {stock_code: stock_name}

    for row in raw_rows:
        try:
            full_code = str(row.get('full_code') or '').strip().upper()
            if not full_code:
                continue
            pre_close = _to_decimal(row.get('pre_close'))
            close = _to_decimal(row.get('close'))
            trade_date_yyyymmdd = str(row['trade_date']).replace('-', '')  # Convert to YYYYMMDD if needed

            limit_fields = compute_limit_fields(
                full_code=full_code,
                trade_date=trade_date_yyyymmdd,
                pre_close=pre_close,
                close=close,
                stock_name=name_map.get(full_code, stock_name),
                list_date=None,
            )

            enriched_row = {
                'trade_date': row['trade_date'],  # Use normalized trade date
                'full_code': full_code,
                'open': _to_decimal(row.get('open')),
                'high': _to_decimal(row.get('high')),
                'low': _to_decimal(row.get('low')),
                'close': close,
                'pre_close': pre_close,
                'change': _to_decimal(row.get('change')),
                'pct_chg': _to_decimal(row.get('pct_chg')),
                'vol': _to_decimal(row.get('vol')),
                'amount': _to_decimal(row.get('amount')),
                'updated_at': updated_at,
            }
            # Add limit fields (with defaults if missing)
            for k, v in limit_fields.items():
                enriched_row[k] = v

            enriched_rows.append(enriched_row)
        except (ValueError, TypeError) as e:
            logger.warning('Task %s: could not enrich row for %s: %s', task_id, stock_code, e)
            continue

    if not enriched_rows:
        logger.warning('Task %s: %s has no valid rows after enrichment', task_id, stock_code)
        _task_repo(sqlite_path).increment_processed_items(task_id)
        return True, ''

    # Write all rows for this stock in a single connection + transaction (bulk)
    write_elapsed_start = time.monotonic()
    try:
        _write_duckdb_stock_bulk(stock_code, start_date, end_date, enriched_rows, duckdb_path)
    except Exception as exc:
        logger.exception('Task %s: write failed for %s: %s', task_id, stock_code, exc)
        return False, f'Write failed for {stock_code}: {exc}'

    write_elapsed = time.monotonic() - write_elapsed_start

    # Count unique dates for logging
    unique_dates = len({r['trade_date'] for r in enriched_rows})
    total_elapsed = time.monotonic() - t0
    logger.info(
        'Task %s: %s done — %d rows written in %d dates (fetch=%.1fs write=%.1fs total=%.1fs)',
        task_id, stock_code, len(enriched_rows), unique_dates, fetch_elapsed, write_elapsed, total_elapsed,
    )
    _task_repo(sqlite_path).increment_processed_items(task_id)
    return True, ''



def _fetch_daily_raw(
    date_str: str,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Fetch full-market daily quote for *date_str* (YYYYMMDD) via the configured data source.

    Routes through the unified multi-source contract in data_source.py, then enriches
    rows with accurate limit-up/down fields via compute_limit_fields().
    Returns rows ready for _write_duckdb_day() with amount already in 亿元.
    """
    # Convert YYYYMMDD → YYYY-MM-DD for the unified data source interface
    trade_date_iso = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'

    logger.info('_fetch_daily_raw start. trade_date=%s', date_str)
    try:
        raw_rows = fetch_daily_bars_by_date(trade_date_iso, sqlite_path=sqlite_path)
    except Exception as exc:
        logger.error('_fetch_daily_raw: data source fetch failed for %s: %s', date_str, exc)
        raise
    logger.info('_fetch_daily_raw raw rows received. trade_date=%s rows=%d', date_str, len(raw_rows))

    # Load stock universe metadata (name only) for limit-field enrichment.
    name_map: dict[str, str] = {}
    try:
        conn = _connect(sqlite_path)
        try:
            univ_rows = conn.execute(
                'SELECT full_code, name FROM stock_list'
            ).fetchall()
            for r in univ_rows:
                ts = r['full_code']
                name_map[ts] = r['name'] or ''
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
    for row in raw_rows:
        try:
            full_code = str(row.get('full_code') or '').strip().upper()
            if not full_code:
                continue
            pre_close = _to_decimal(row.get('pre_close'))
            close = _to_decimal(row.get('close'))
            stock_name = name_map.get(full_code, '')

            limit_fields = compute_limit_fields(
                full_code=full_code,
                trade_date=date_str,
                pre_close=pre_close,
                close=close,
                stock_name=stock_name,
                list_date=None,
            )

            rows.append({
                'trade_date': date_str,
                'full_code': full_code,
                'open': _to_decimal(row.get('open')),
                'high': _to_decimal(row.get('high')),
                'low': _to_decimal(row.get('low')),
                'close': close,
                'pre_close': pre_close,
                'change': _to_decimal(row.get('change')),
                'pct_chg': _to_decimal(row.get('pct_chg')),
                'vol': _to_decimal(row.get('vol')),
                # amount is already in 亿元 from fetch_daily_bars_by_date contract
                'amount': _to_decimal(row.get('amount')),
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


def _write_duckdb_stock_bulk(
        stock_code: str,
        start_date: str,
        end_date: str,
        rows: list[dict[str, Any]],
        duckdb_path: Path | None = None,
) -> None:
    """Write all rows for a single stock across its full date range in one transaction.

    Much faster than calling _write_duckdb_day per date: one connection open, one
    BEGIN/COMMIT, one DELETE (by full_code + date range), one executemany for all rows.

    *start_date* / *end_date*: YYYYMMDD strings used to bound the DELETE.
    """
    if not rows:
        return

    # Convert YYYYMMDD → YYYY-MM-DD for DuckDB storage format
    start_date_str = f'{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}'
    end_date_str = f'{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}'

    duckdb_rows = [
        (
            str(r.get('full_code') or ''),
            # Normalise trade_date: accept both YYYYMMDD and YYYY-MM-DD
            (lambda d: f'{d[:4]}-{d[4:6]}-{d[6:8]}' if len(d) == 8 and '-' not in d else d)(str(r['trade_date'])),
            _to_decimal(r.get('open')),
            _to_decimal(r.get('high')),
            _to_decimal(r.get('low')),
            _to_decimal(r.get('close')),
            _to_decimal(r.get('pre_close')),
            _to_decimal(r.get('change')),
            _to_decimal(r.get('pct_chg')),
            _to_decimal(r.get('vol')),
            _to_decimal(r.get('amount')),
            bool(r.get('is_limit_up', False)),
            bool(r.get('is_limit_down', False)),
        )
        for r in rows
    ]

    conn = _connect_duckdb(duckdb_path)
    try:
        conn.execute('BEGIN TRANSACTION')
        # Delete all existing rows for this stock within the date range (idempotent)
        conn.execute(
            'DELETE FROM day_level_trade_data WHERE full_code = ? AND trade_date BETWEEN ? AND ?',
            [stock_code, start_date_str, end_date_str],
        )
        conn.executemany(
            'INSERT INTO day_level_trade_data ('
            'full_code, trade_date, open, high, low, close, '
            'pre_close, change, pct_chg, vol, amount, is_up_limit, is_down_limit'
            ') VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            duckdb_rows,
        )
        conn.commit()
        logger.debug(
            '_write_duckdb_stock_bulk: %s [%s ~ %s] → %d rows written',
            stock_code, start_date, end_date, len(duckdb_rows),
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _write_duckdb_day(
    date_str: str,
    rows: list[dict[str, Any]],
    duckdb_path: Path | None = None,
) -> None:
    """Write *rows* for *date_str* into DuckDB's ``day_level_trade_data`` table.

    Stores quote rows with canonical ``full_code``.
    - full_code (e.g. '000001.SZ') stored as-is
    - trade_date 'YYYYMMDD' → 'YYYY-MM-DD' for consistent internal format
    - open, high, low, close, pre_close, change, pct_chg from source row
    - vol stored as Decimal (lots)
    - amount in 亿元 (already converted upstream by data_source contract)
    - is_up_limit / is_down_limit from compute_limit_fields output

    Deletes existing rows for the date before inserting (idempotent).
    """
    trade_date_str = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'

    duckdb_rows = [
        (
            str(r.get('full_code') or ''),  # full_code (full format)
            trade_date_str,
            _to_decimal(r.get('open')),
            _to_decimal(r.get('high')),
            _to_decimal(r.get('low')),
            _to_decimal(r.get('close')),
            _to_decimal(r.get('pre_close')),
            _to_decimal(r.get('change')),
            _to_decimal(r.get('pct_chg')),
            _to_decimal(r.get('vol')),
            _to_decimal(r.get('amount')),  # 亿元 (already converted)
            bool(r.get('is_limit_up', False)),  # is_up_limit
            bool(r.get('is_limit_down', False)),  # is_down_limit
        )
        for r in rows
    ]

    conn = _connect_duckdb(duckdb_path)
    try:
        conn.execute('BEGIN TRANSACTION')
        conn.execute('DELETE FROM day_level_trade_data WHERE trade_date = ?', [trade_date_str])
        if duckdb_rows:
            conn.executemany(
                'INSERT INTO day_level_trade_data ('
                'full_code, trade_date, open, high, low, close, '
                'pre_close, change, pct_chg, vol, amount, is_up_limit, is_down_limit'
                ') VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                duckdb_rows,
            )
        written = conn.execute(
            'SELECT COUNT(*) FROM day_level_trade_data WHERE trade_date = ?', [trade_date_str]
        ).fetchone()[0]
        if written != len(duckdb_rows):
            conn.rollback()
            raise RuntimeError(
                f'DuckDB integrity check failed for {trade_date_str}: '
                f'expected {len(duckdb_rows)} rows, got {written}'
            )
        conn.commit()
        logger.debug(
            '_write_duckdb_day: %s → %d rows written to day_level_trade_data', date_str, len(duckdb_rows)
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _export_parquet(duckdb_path: Path | None = None) -> None:
    """Re-export all day_level_trade_data rows from DuckDB to the Parquet fallback file."""
    parquet_path = settings.daily_bars_parquet_path
    target_duckdb = duckdb_path or settings.duckdb_path

    conn = _connect_duckdb(target_duckdb)
    try:
        parquet_path.unlink(missing_ok=True)
        parquet_str = str(parquet_path).replace('\\', '/').replace("'", "''")
        conn.execute(
            f"COPY (SELECT * FROM day_level_trade_data ORDER BY full_code, trade_date) "
            f"TO '{parquet_str}' (FORMAT PARQUET)"
        )
        logger.info('_export_parquet: Parquet file regenerated at %s', parquet_path)
    finally:
        conn.close()


def _is_task_terminated(task_id: str, sqlite_path: Path | None) -> bool:
    return _task_repo(sqlite_path).is_task_terminated(task_id)



def _detect_incremental_start(duckdb_path: Path | None = None) -> str | None:
    """Query day_level_trade_data for MAX(trade_date) and return the next day as YYYYMMDD.

    Returns None if the table is empty (no existing data to build on).
    """
    try:
        conn = _connect_duckdb(duckdb_path)
        try:
            row = conn.execute('SELECT MAX(trade_date) AS max_td FROM day_level_trade_data').fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning('_detect_incremental_start: DuckDB query failed: %s', exc)
        return None

    if not row or not row[0]:
        return None

    max_td_str = str(row[0])  # 'YYYY-MM-DD'
    try:
        max_td = datetime.strptime(max_td_str[:10], '%Y-%m-%d').date()
        next_day = max_td + timedelta(days=1)
        return next_day.strftime('%Y%m%d')
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Batch task support
# ---------------------------------------------------------------------------


def create_batch_tasks(
        start_date: str,
        end_date: str,
        sqlite_path: Path | None = None,
        duckdb_path: Path | None = None,
) -> dict[str, Any]:
    """Create three tasks (STOCK_LIST_SYNC + MARKET_DATA + JYGS_REVIEW) and launch the
    batch coordinator thread.

    Execution order inside the coordinator:
    1. STOCK_LIST_SYNC runs first (synchronously in the coordinator thread).
    2. After STOCK_LIST_SYNC succeeds, MARKET_DATA + JYGS_REVIEW start in parallel.
       If STOCK_LIST_SYNC fails, MARKET_DATA is terminated; JYGS_REVIEW still starts.

    Returns a dict with keys ``stock_list_task``, ``market_data_task``, ``jygs_review_task``.
    Raises ValueError if required credentials are missing.
    """
    _ensure_schema(sqlite_path)
    today = datetime.now().strftime('%Y%m%d')

    stock_task = create_task(today, today, task_type='STOCK_LIST_SYNC', sqlite_path=sqlite_path)
    market_task = create_task(start_date, end_date, task_type='MARKET_DATA', sqlite_path=sqlite_path)
    jygs_task = create_task(start_date, end_date, task_type='JYGS_REVIEW', sqlite_path=sqlite_path)

    coordinator = threading.Thread(
        target=_run_batch_coordinator,
        args=(
            stock_task['task_id'],
            market_task['task_id'],
            jygs_task['task_id'],
            sqlite_path,
            duckdb_path,
        ),
        daemon=True,
    )
    coordinator.start()

    return {
        'stock_list_task': get_task(stock_task['task_id'], sqlite_path) or stock_task,
        'market_data_task': get_task(market_task['task_id'], sqlite_path) or market_task,
        'jygs_review_task': get_task(jygs_task['task_id'], sqlite_path) or jygs_task,
    }


def _run_batch_coordinator(
        stock_task_id: str,
        market_task_id: str,
        jygs_task_id: str,
        sqlite_path: Path | None,
        duckdb_path: Path | None,
) -> None:
    """Batch coordinator: run STOCK_LIST_SYNC first, then start MARKET_DATA + JYGS_REVIEW in parallel."""
    repo = _task_repo(sqlite_path)

    # ── Step 1: run STOCK_LIST_SYNC synchronously in this thread ──────────
    with _task_lock:
        marked = repo.try_mark_task_running(stock_task_id, _now_iso())
    if not marked:
        logger.warning('Batch coordinator: failed to mark STOCK_LIST_SYNC %s as RUNNING', stock_task_id)
        repo.terminate_task(market_task_id, _now_iso())
        repo.terminate_task(jygs_task_id, _now_iso())
        return

    logger.info('Batch coordinator: running STOCK_LIST_SYNC %s', stock_task_id)
    _run_task(stock_task_id, sqlite_path, duckdb_path)

    stock_status = repo.get_task_status(stock_task_id)
    logger.info('Batch coordinator: STOCK_LIST_SYNC %s finished with status %s', stock_task_id, stock_status)

    # ── Step 2: start JYGS_REVIEW (does not depend on stock_list) ─────────
    with _task_lock:
        jygs_marked = repo.try_mark_task_running(jygs_task_id, _now_iso())
    if jygs_marked:
        threading.Thread(
            target=_run_task,
            args=(jygs_task_id, sqlite_path, None),
            daemon=True,
        ).start()
        logger.info('Batch coordinator: started JYGS_REVIEW %s', jygs_task_id)
    else:
        logger.warning('Batch coordinator: could not start JYGS_REVIEW %s', jygs_task_id)

    # ── Step 3: start MARKET_DATA only if STOCK_LIST_SYNC succeeded ───────
    if stock_status == 'SUCCESS':
        with _task_lock:
            market_marked = repo.try_mark_task_running(market_task_id, _now_iso())
        if market_marked:
            threading.Thread(
                target=_run_task,
                args=(market_task_id, sqlite_path, duckdb_path),
                daemon=True,
            ).start()
            logger.info('Batch coordinator: started MARKET_DATA %s', market_task_id)
        else:
            logger.warning('Batch coordinator: could not start MARKET_DATA %s', market_task_id)
    else:
        repo.terminate_task(market_task_id, _now_iso())
        logger.warning(
            'Batch coordinator: STOCK_LIST_SYNC failed (%s), MARKET_DATA %s terminated',
            stock_status, market_task_id,
        )


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def read_init_status(status_dir: Any = None) -> dict[str, Any]:  # noqa: ARG001
    """Return current init state (reads from SQLite)."""
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
            'trade_date': task.get('current_label', ''),
            'total_stocks': task.get('total_items', 0),
            'processed_stocks': task.get('processed_items', 0),
            'started_at': task.get('task_start_date', ''),
            'finished_at': task.get('task_end_date', ''),
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
) -> tuple[bool, str]:
    """Fetch and parse JYGS review data for a single date.

    Returns (True, '') on success (including empty responses).
    Returns (False, error_message) on failure; caller decides whether to continue.
    """
    t0 = time.monotonic()

    # Set current label to the date being processed
    _task_repo(sqlite_path).set_current_label(task_id, date_str)

    try:
        review_count = fetch_and_parse_jygs_review_for_date(date_str)
        elapsed = time.monotonic() - t0

        # Mark date as processed and advance overall task progress
        _task_repo(sqlite_path).increment_processed_items(task_id)

        logger.info(
            'Task %s: %s SUCCESS (parsed %d reviews in %.1fs)',
            task_id, date_str, review_count, elapsed,
        )
        return True, ''

    except Exception as exc:
        elapsed = time.monotonic() - t0
        error_msg = str(exc)[:500]

        logger.error(
            'Task %s: %s FAILED in %.1fs: %s',
            task_id, date_str, elapsed, error_msg,
        )
        return False, error_msg
