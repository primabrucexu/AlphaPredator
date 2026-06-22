from __future__ import annotations

import math
import threading
import uuid
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlmodel import select

from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
from app.db.session import get_sqlite_session_factory
from app.db.sqlite import ensure_sqlite_schema
from app.models.sqlite_models import (
    DailyHotInfo,
    StockLinkageBacktestJob as StockLinkageBacktestJobRow,
    StockLinkageBacktestResult,
    StockLinkageBaselineMetric,
    StockLinkageTriggerEvent,
    StockList,
)
from app.modules.stock_linkage.constants import (
    A_INTRADAY_THRESHOLDS,
    A_SINGLE_BAR_THRESHOLDS,
    B_TARGET_THRESHOLDS,
    HOT_LIMIT_TOP,
    INTRADAY_RETURN_FROM_PRE_CLOSE,
    MANUAL_SINGLE,
    NEXT_DAY_CLOSE,
    NEXT_DAY_HIGH,
    OBSERVATION_TYPES,
    SINGLE_BAR_RETURN,
    T_DAY_CLOSE,
    T_DAY_HIGH,
)
from app.modules.stock_linkage.models import (
    FiveMinuteBar,
    StockLinkageBacktestJob,
    StockLinkageBacktestRequest,
    StockLinkageBacktestSummary,
    TriggerEvent,
)

_stock_linkage_lock = threading.Lock()


def _session_factory(sqlite_path: Path | None = None):
    return get_sqlite_session_factory(sqlite_path)


def _parse_date(value: str) -> date:
    return datetime.strptime(value, '%Y-%m-%d').date()


def _validate_request(request: StockLinkageBacktestRequest) -> None:
    start = _parse_date(request.start_date)
    end = _parse_date(request.end_date)
    if start > end:
        raise ValueError('start_date must be <= end_date')
    if (end - start).days > 730:
        raise ValueError('单个回测任务的时间范围最长不超过2年')
    if request.min_sample_count < 1:
        raise ValueError('min_sample_count must be positive')
    if request.a_select_mode == MANUAL_SINGLE and not request.manual_a_full_code:
        raise ValueError('manual_a_full_code is required for manual_single mode')
    if request.a_select_mode == HOT_LIMIT_TOP and not request.hot_top_n:
        raise ValueError('hot_top_n is required for hot_limit_top mode')
    if request.a_select_mode not in {MANUAL_SINGLE, HOT_LIMIT_TOP}:
        raise ValueError(f'Unsupported a_select_mode: {request.a_select_mode}')


def _list_non_st_full_codes(sqlite_path: Path | None) -> list[str]:
    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        rows = session.exec(
            select(StockList)
            .where(StockList.is_st == False)  # noqa: E712
            .order_by(StockList.full_code)
        ).all()
        return [row.full_code for row in rows]


def _select_a_codes(request: StockLinkageBacktestRequest, sqlite_path: Path | None) -> list[str]:
    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        if request.a_select_mode == MANUAL_SINGLE:
            row = session.exec(
                select(StockList)
                .where(
                    StockList.full_code == str(request.manual_a_full_code).upper(),
                    StockList.is_st == False,  # noqa: E712
                )
                .limit(1)
            ).first()
            return [row.full_code] if row else []

        hot_rows = session.exec(
            select(DailyHotInfo).where(
                DailyHotInfo.trade_date >= request.end_date[:4] + '-01-01',
                DailyHotInfo.trade_date <= request.end_date,
            )
        ).all()
        counts: dict[str, int] = defaultdict(int)
        stock_by_code = {
            row.code: row
            for row in session.exec(
                select(StockList).where(StockList.is_st == False)  # noqa: E712
            ).all()
        }
        for hot_row in hot_rows:
            stock = stock_by_code.get(hot_row.stock_code)
            if stock:
                counts[stock.full_code] += 1
        return [
            full_code
            for full_code, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
                : int(request.hot_top_n or 20)
            ]
        ]


def _load_5m_bars(duckdb_path: Path | None, full_codes: list[str], start_date: str, end_date: str) -> dict[str, dict[str, list[FiveMinuteBar]]]:
    if not full_codes:
        return {}
    placeholders = ','.join(['?'] * len(full_codes))
    conn = connect_duckdb(duckdb_path)
    try:
        rows = conn.execute(
            f'''
            SELECT
                full_code,
                CAST(trade_date AS VARCHAR) AS trade_time,
                CAST(trade_date AS DATE) AS trade_day,
                row_number() OVER (PARTITION BY full_code, CAST(trade_date AS DATE) ORDER BY trade_date) AS bar_index,
                open, high, low, close, pre_close, is_stop
            FROM "5m_level_trade_data"
            WHERE full_code IN ({placeholders})
              AND CAST(trade_date AS DATE) >= ?
              AND CAST(trade_date AS DATE) <= (CAST(? AS DATE) + INTERVAL 7 DAY)
            ORDER BY full_code, trade_date
            ''',
            [*full_codes, start_date, end_date],
        ).fetchall()
    finally:
        conn.close()

    grouped: dict[str, dict[str, list[FiveMinuteBar]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        trade_day = str(row[2])
        if ' ' in trade_day:
            trade_day = trade_day.split(' ')[0]
        bar = FiveMinuteBar(
            full_code=str(row[0]),
            trade_date=str(row[1]),
            trade_day=trade_day,
            bar_index=int(row[3]),
            open=float(row[4]),
            high=float(row[5]),
            low=float(row[6]),
            close=float(row[7]),
            pre_close=float(row[8]),
            is_stop=bool(row[9]),
        )
        grouped[bar.full_code][bar.trade_day].append(bar)
    return {code: dict(days) for code, days in grouped.items()}


def _next_trade_day(days: list[str], current_day: str) -> str | None:
    for day in days:
        if day > current_day:
            return day
    return None


def _find_triggers(a_code: str, bars_by_day: dict[str, list[FiveMinuteBar]], start_date: str, end_date: str) -> list[TriggerEvent]:
    events: list[TriggerEvent] = []
    for trade_day, bars in sorted(bars_by_day.items()):
        if trade_day < start_date or trade_day > end_date:
            continue
        active_bars = [bar for bar in bars if not bar.is_stop]
        if not active_bars:
            continue
        day_pre_close = active_bars[0].pre_close
        for threshold in A_SINGLE_BAR_THRESHOLDS:
            for bar in active_bars:
                if bar.open and (bar.close - bar.open) / bar.open > threshold:
                    events.append(
                        TriggerEvent(a_code, trade_day, bar.trade_date, bar.bar_index, SINGLE_BAR_RETURN, threshold,
                                     (bar.close - bar.open) / bar.open)
                    )
                    break
        if day_pre_close:
            for threshold in A_INTRADAY_THRESHOLDS:
                for bar in active_bars:
                    if (bar.close - day_pre_close) / day_pre_close > threshold:
                        events.append(
                            TriggerEvent(a_code, trade_day, bar.trade_date, bar.bar_index,
                                         INTRADAY_RETURN_FROM_PRE_CLOSE, threshold,
                                         (bar.close - day_pre_close) / day_pre_close)
                        )
                        break
    return events


def _observe_from_buy(
    bars_by_day: dict[str, list[FiveMinuteBar]],
    trade_day: str,
    bar_index: int,
    ordered_days: list[str],
) -> dict[str, float] | None:
    day_bars = bars_by_day.get(trade_day, [])
    next_idx = bar_index
    if next_idx >= len(day_bars):
        return None
    buy_price = day_bars[next_idx].open
    if not buy_price:
        return None
    remaining = [bar for bar in day_bars[next_idx:] if not bar.is_stop]
    if not remaining:
        return None
    next_day = _next_trade_day(ordered_days, trade_day)
    next_day_bars = [bar for bar in bars_by_day.get(next_day or '', []) if not bar.is_stop]
    if not next_day_bars:
        return None

    return {
        T_DAY_HIGH: (max(bar.high for bar in remaining) - buy_price) / buy_price,
        T_DAY_CLOSE: (remaining[-1].close - buy_price) / buy_price,
        NEXT_DAY_HIGH: (max(bar.high for bar in next_day_bars) - buy_price) / buy_price,
        NEXT_DAY_CLOSE: (next_day_bars[-1].close - buy_price) / buy_price,
    }


def _confidence(sample_count: int, coverage: float, min_sample_count: int) -> str:
    if sample_count < min_sample_count:
        return 'insufficient'
    if sample_count >= 50 and coverage >= 0.2:
        return 'high'
    if sample_count >= 30 and coverage >= 0.1:
        return 'medium'
    if sample_count >= 20:
        return 'low'
    return 'insufficient'


def _build_job_row(request: StockLinkageBacktestRequest, job_id: str, status: str, error: str = '') -> StockLinkageBacktestJobRow:
    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    return StockLinkageBacktestJobRow(
        id=job_id,
        job_name=request.job_name,
        a_select_mode=request.a_select_mode,
        manual_a_full_code=request.manual_a_full_code,
        hot_top_n=request.hot_top_n,
        start_date=request.start_date,
        end_date=request.end_date,
        min_sample_count=request.min_sample_count,
        status=status,
        error_message=error,
        created_at=now,
        updated_at=now,
        finished_at=now if status in {'success', 'failed'} else None,
    )


def _row_to_job(row: StockLinkageBacktestJobRow) -> StockLinkageBacktestJob:
    return StockLinkageBacktestJob(
        job_id=row.id,
        job_name=row.job_name,
        a_select_mode=row.a_select_mode,
        manual_a_full_code=row.manual_a_full_code,
        hot_top_n=row.hot_top_n,
        start_date=row.start_date[:10],
        end_date=row.end_date[:10],
        min_sample_count=row.min_sample_count,
        status=row.status,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
        finished_at=row.finished_at,
    )


def _job_to_request(job: StockLinkageBacktestJob) -> StockLinkageBacktestRequest:
    return StockLinkageBacktestRequest(
        a_select_mode=job.a_select_mode,
        manual_a_full_code=job.manual_a_full_code,
        hot_top_n=job.hot_top_n,
        start_date=job.start_date,
        end_date=job.end_date,
        min_sample_count=job.min_sample_count,
        job_name=job.job_name,
    )


def create_stock_linkage_backtest_job(
    request: StockLinkageBacktestRequest,
    *,
    sqlite_path: Path | None = None,
) -> StockLinkageBacktestJob:
    _validate_request(request)
    ensure_sqlite_schema(sqlite_path)
    job_id = str(uuid.uuid4())
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        session.add(_build_job_row(request, job_id, 'pending'))
        session.commit()
    job = get_stock_linkage_job(job_id, sqlite_path=sqlite_path)
    assert job is not None
    return job

def get_stock_linkage_job(
    job_id: str,
    *,
    sqlite_path: Path | None = None,
) -> StockLinkageBacktestJob | None:
    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        row = session.get(StockLinkageBacktestJobRow, job_id)
    return _row_to_job(row) if row else None

def list_stock_linkage_jobs(
    *,
    limit: int = 20,
    sqlite_path: Path | None = None,
) -> list[StockLinkageBacktestJob]:
    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        rows = session.exec(
            select(StockLinkageBacktestJobRow)
            .order_by(StockLinkageBacktestJobRow.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        ).all()
    return [_row_to_job(row) for row in rows]

def _find_running_stock_linkage_job_id(session: Any) -> str | None:
    row = session.exec(
        select(StockLinkageBacktestJobRow)
        .where(StockLinkageBacktestJobRow.status == 'running')
        .order_by(StockLinkageBacktestJobRow.created_at)
        .limit(1)
    ).first()
    return row.id if row else None


def _mark_job_status(session: Any, job_id: str, status: str, error_message: str | None = None) -> None:
    now = datetime.now().isoformat(sep=' ', timespec='seconds')
    finished_at = now if status in {'success', 'failed'} else None
    row = session.get(StockLinkageBacktestJobRow, job_id)
    if row:
        row.status = status
        row.error_message = error_message
        row.updated_at = now
        row.finished_at = finished_at
        session.add(row)


def start_stock_linkage_backtest_job(
    job_id: str,
    *,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
) -> bool:
    ensure_sqlite_schema(sqlite_path)
    with _stock_linkage_lock:
        session_factory = _session_factory(sqlite_path)
        with session_factory() as session:
            if _find_running_stock_linkage_job_id(session):
                return False
            job = get_stock_linkage_job(job_id, sqlite_path=sqlite_path)
            if job is None or job.status != 'pending':
                return False
            _mark_job_status(session, job_id, 'running')
            session.commit()

    thread = threading.Thread(
        target=_run_stock_linkage_job,
        args=(job_id, sqlite_path, duckdb_path),
        daemon=True,
    )
    thread.start()
    return True

def _run_stock_linkage_job(
    job_id: str,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
) -> None:
    job = get_stock_linkage_job(job_id, sqlite_path=sqlite_path)
    if job is None:
        return
    try:
        run_stock_linkage_backtest(
            _job_to_request(job),
            sqlite_path=sqlite_path,
            duckdb_path=duckdb_path,
            job_id=job_id,
        )
        session_factory = _session_factory(sqlite_path)
        with session_factory() as session:
            _mark_job_status(session, job_id, 'success')
            session.commit()
    except Exception as exc:  # noqa: BLE001
        session_factory = _session_factory(sqlite_path)
        with session_factory() as session:
            _mark_job_status(session, job_id, 'failed', str(exc)[:1000])
            session.commit()

def run_stock_linkage_backtest(
    request: StockLinkageBacktestRequest,
    *,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
    job_id: str | None = None,
) -> StockLinkageBacktestSummary:
    _validate_request(request)
    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_schema(duckdb_path)

    target_job_id = job_id or str(uuid.uuid4())
    b_codes = _list_non_st_full_codes(sqlite_path)
    a_codes = _select_a_codes(request, sqlite_path)
    all_codes = sorted(set(a_codes + b_codes))
    bars = _load_5m_bars(duckdb_path, all_codes, request.start_date, request.end_date)

    events: list[TriggerEvent] = []
    effective_days_by_a: dict[str, int] = {}
    for a_code in a_codes:
        a_bars = bars.get(a_code, {})
        effective_days = [day for day in a_bars if request.start_date <= day <= request.end_date]
        effective_days_by_a[a_code] = len(effective_days)
        events.extend(_find_triggers(a_code, a_bars, request.start_date, request.end_date))

    baseline: dict[tuple[str, str, float], tuple[int, int, float]] = {}
    for b_code in b_codes:
        b_bars = bars.get(b_code, {})
        ordered_days = sorted(b_bars)
        observations: list[dict[str, float]] = []
        for day, day_bars in b_bars.items():
            if day < request.start_date or day > request.end_date:
                continue
            for idx in range(len(day_bars) - 1):
                observed = _observe_from_buy(b_bars, day, idx + 1, ordered_days)
                if observed:
                    observations.append(observed)
        for observation_type in OBSERVATION_TYPES:
            for threshold in B_TARGET_THRESHOLDS:
                sample_count = len(observations)
                hit_count = sum(1 for observed in observations if observed[observation_type] > threshold)
                probability = hit_count / sample_count if sample_count else 0.0
                baseline[(b_code, observation_type, threshold)] = (sample_count, hit_count, probability)

    result_rows: list[list[Any]] = []
    for a_code in a_codes:
        a_events = [event for event in events if event.a_full_code == a_code]
        trigger_days_by_condition: dict[tuple[str, float], set[str]] = defaultdict(set)
        for event in a_events:
            trigger_days_by_condition[(event.trigger_type, event.trigger_threshold)].add(event.trade_date)

        for b_code in b_codes:
            if b_code == a_code:
                continue
            b_bars = bars.get(b_code, {})
            ordered_days = sorted(b_bars)
            observations_by_condition: dict[tuple[str, float], list[dict[str, float]]] = defaultdict(list)
            for event in a_events:
                observed = _observe_from_buy(b_bars, event.trade_date, event.bar_index, ordered_days)
                if observed:
                    observations_by_condition[(event.trigger_type, event.trigger_threshold)].append(observed)

            for (trigger_type, trigger_threshold), observations in observations_by_condition.items():
                effective_days = effective_days_by_a.get(a_code, 0)
                coverage = (
                    len(trigger_days_by_condition[(trigger_type, trigger_threshold)]) / effective_days
                    if effective_days else 0.0
                )
                for observation_type in OBSERVATION_TYPES:
                    for target_threshold in B_TARGET_THRESHOLDS:
                        sample_count = len(observations)
                        hit_count = sum(1 for observed in observations if observed[observation_type] > target_threshold)
                        condition_probability = hit_count / sample_count if sample_count else 0.0
                        baseline_probability = baseline.get((b_code, observation_type, target_threshold), (0, 0, 0.0))[2]
                        probability_lift = condition_probability - baseline_probability
                        lift_multiple = (
                            condition_probability / baseline_probability
                            if baseline_probability else None
                        )
                        confidence = _confidence(sample_count, coverage, request.min_sample_count)
                        score = probability_lift * math.log(sample_count + 1)
                        result_rows.append(
                            [
                                str(uuid.uuid4()),
                                target_job_id,
                                a_code,
                                b_code,
                                trigger_type,
                                trigger_threshold,
                                observation_type,
                                target_threshold,
                                sample_count,
                                hit_count,
                                condition_probability,
                                baseline_probability,
                                probability_lift,
                                lift_multiple,
                                coverage,
                                confidence,
                                score,
                                datetime.now().isoformat(sep=' ', timespec='seconds'),
                            ]
                        )

    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        if job_id is None:
            session.add(_build_job_row(request, target_job_id, 'success'))
        else:
            for row in session.exec(
                select(StockLinkageTriggerEvent).where(StockLinkageTriggerEvent.job_id == target_job_id)
            ).all():
                session.delete(row)
            for row in session.exec(
                select(StockLinkageBaselineMetric).where(StockLinkageBaselineMetric.job_id == target_job_id)
            ).all():
                session.delete(row)
            for row in session.exec(
                select(StockLinkageBacktestResult).where(StockLinkageBacktestResult.job_id == target_job_id)
            ).all():
                session.delete(row)
        trigger_rows = [
                StockLinkageTriggerEvent(
                    id=str(uuid.uuid4()),
                    job_id=target_job_id,
                    a_full_code=event.a_full_code,
                    trade_date=event.trade_date,
                    bar_time=event.bar_time,
                    bar_index=event.bar_index,
                    trigger_type=event.trigger_type,
                    trigger_threshold=event.trigger_threshold,
                    trigger_return=event.trigger_return,
                )
                for event in events
            ]
        for trigger_row in trigger_rows:
            session.add(trigger_row)
        for (b_code, observation_type, threshold), (sample, hits, probability) in baseline.items():
            session.add(
                StockLinkageBaselineMetric(
                    id=str(uuid.uuid4()),
                    job_id=target_job_id,
                    b_full_code=b_code,
                    observation_type=observation_type,
                    target_threshold=threshold,
                    baseline_sample_count=sample,
                    baseline_hit_count=hits,
                    baseline_probability=probability,
                )
            )
        for row in result_rows:
            session.add(
                StockLinkageBacktestResult(
                    id=row[0],
                    job_id=row[1],
                    a_full_code=row[2],
                    b_full_code=row[3],
                    trigger_type=row[4],
                    trigger_threshold=row[5],
                    observation_type=row[6],
                    target_threshold=row[7],
                    sample_count=row[8],
                    hit_count=row[9],
                    condition_probability=row[10],
                    baseline_probability=row[11],
                    probability_lift=row[12],
                    lift_multiple=row[13],
                    trigger_coverage_rate=row[14],
                    confidence_level=row[15],
                    score=row[16],
                    created_at=row[17],
                )
            )
        session.commit()

    return StockLinkageBacktestSummary(
        job_id=target_job_id,
        status='success',
        trigger_event_count=len(events),
        baseline_count=len(baseline),
        result_count=len(result_rows),
    )


def list_stock_linkage_results(
    job_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        rows = session.exec(
            select(StockLinkageBacktestResult)
            .where(StockLinkageBacktestResult.job_id == job_id)
            .order_by(
                StockLinkageBacktestResult.score.desc(),  # type: ignore[attr-defined]
                StockLinkageBacktestResult.probability_lift.desc(),  # type: ignore[attr-defined]
                StockLinkageBacktestResult.condition_probability.desc(),  # type: ignore[attr-defined]
            )
            .offset(offset)
            .limit(limit)
        ).all()

    return [
        {
            'job_id': row.job_id,
            'a_full_code': row.a_full_code,
            'b_full_code': row.b_full_code,
            'trigger_type': row.trigger_type,
            'trigger_threshold': row.trigger_threshold,
            'observation_type': row.observation_type,
            'target_threshold': row.target_threshold,
            'sample_count': row.sample_count,
            'hit_count': row.hit_count,
            'condition_probability': row.condition_probability,
            'baseline_probability': row.baseline_probability,
            'probability_lift': row.probability_lift,
            'lift_multiple': row.lift_multiple,
            'trigger_coverage_rate': row.trigger_coverage_rate,
            'confidence_level': row.confidence_level,
            'score': row.score,
        }
        for row in rows
    ]
