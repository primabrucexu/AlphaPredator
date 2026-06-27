from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import select

from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
from app.db.session import get_sqlite_session_factory
from app.db.sqlite import ensure_sqlite_schema
from app.models.sqlite_models import (
    DailyHotInfo,
    MacdAlertBacktestSample,
    MacdAlertResult,
    StockList,
)
from app.modules.macd_alert.indicators import MacdPoint, compute_macd_points
from app.repositories.init_task_repo import InitTaskRepo

PATTERN_KEY = 'golden_cross_setup'
PATTERN_NAME = '金叉临界'
DISCLAIMER = '以下为技术形态观察结果，不构成买卖建议。'
MACD_ALERT_SCAN_TASK_TYPE = 'MACD_ALERT_SCAN'

_pending_green_shrink_days: dict[str, int] = {}


def _get_green_shrink_days(task_id: str, default: int = 2) -> int:
    return _pending_green_shrink_days.pop(task_id, default)


def _session_factory(sqlite_path: Path | None = None):
    return get_sqlite_session_factory(sqlite_path)


@dataclass(frozen=True)
class DailyBar:
    full_code: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    is_up_limit: bool
    is_down_limit: bool


@dataclass(frozen=True)
class AlertCandidate:
    stock_code: str
    stock_name: str
    full_code: str
    trade_date: str
    close_price: float
    cross_zone: str
    next_cross_trigger_price: float
    cross_trigger_distance_pct: float
    next_limit_up_price: float
    cross_trigger_reachable: bool
    cross_trigger_unreachable_reason: str | None
    next_trend_keep_price: float
    trend_keep_distance_pct: float
    macd: MacdPoint
    green_shrink_days: int
    score: float
    summary: str


def calculate_cross_trigger_price(ema8: float, ema17: float, dea: float) -> float:
    return 9 * dea - 7 * ema8 + 8 * ema17


def calculate_trend_keep_price(ema8: float, ema17: float, dif: float, dea: float) -> float:
    return 9 * (dea + 7 / 5 * (dif - dea)) - 7 * ema8 + 8 * ema17


def _now() -> str:
    return datetime.now().isoformat(sep=' ', timespec='seconds')


def _full_to_code(full_code: str) -> str:
    return full_code.split('.')[0]


def _load_universe(sqlite_path: Path | None, markets: list[str], exclude_st: bool) -> list[dict[str, str]]:
    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        statement = select(StockList)
        if markets:
            statement = statement.where(StockList.market.in_(markets))  # type: ignore[attr-defined]
        if exclude_st:
            statement = statement.where(StockList.is_st == False)  # noqa: E712
        rows = session.exec(statement.order_by(StockList.full_code)).all()
        return [
            {'full_code': row.full_code, 'code': row.code, 'name': row.name}
            for row in rows
        ]


def _load_daily_bars(duckdb_path: Path | None, full_codes: list[str], end_date: str) -> dict[str, list[DailyBar]]:
    if not full_codes:
        return {}
    ensure_duckdb_schema(duckdb_path)
    placeholders = ','.join(['?'] * len(full_codes))
    conn = connect_duckdb(duckdb_path)
    try:
        rows = conn.execute(
            f"""
            SELECT full_code, CAST(trade_date AS VARCHAR), open, high, low, close, pre_close,
                   is_up_limit, is_down_limit
            FROM day_level_trade_data
            WHERE full_code IN ({placeholders})
              AND CAST(trade_date AS DATE) <= CAST(? AS DATE)
            ORDER BY full_code, CAST(trade_date AS DATE)
            """,
            [*full_codes, end_date],
        ).fetchall()
    finally:
        conn.close()
    grouped: dict[str, list[DailyBar]] = {code: [] for code in full_codes}
    for row in rows:
        day = str(row[1])[:10]
        grouped.setdefault(str(row[0]), []).append(
            DailyBar(
                full_code=str(row[0]),
                trade_date=day,
                open=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                close=float(row[5]),
                pre_close=float(row[6] or 0),
                is_up_limit=bool(row[7]),
                is_down_limit=bool(row[8]),
            )
        )
    return grouped


def _is_green_shrinking(points: list[MacdPoint], end_idx: int, green_shrink_days: int) -> bool:
    if end_idx < green_shrink_days:
        return False
    window = points[end_idx - green_shrink_days : end_idx + 1]
    if any(point.hist >= 0 for point in window):
        return False
    return all(abs(window[idx].hist) < abs(window[idx - 1].hist) for idx in range(1, len(window)))


def _cross_zone(point: MacdPoint) -> str:
    if point.dif < 0 and point.dea < 0:
        return 'underwater'
    if point.dif > 0 and point.dea > 0:
        return 'above_zero'
    return 'mixed'


def _limit_up_rate(stock_code: str) -> float:
    if stock_code.startswith(('300', '301', '688')):
        return 0.20
    if stock_code.startswith(('8', '4')):
        return 0.30
    return 0.10


def _make_candidate(
    stock: dict[str, str],
    bars: list[DailyBar],
    idx: int,
    points: list[MacdPoint],
    green_shrink_days: int,
) -> AlertCandidate | None:
    point = points[idx]
    if point.hist >= 0 or point.dif >= point.dea:
        return None
    if not _is_green_shrinking(points, idx, green_shrink_days):
        return None
    zone = _cross_zone(point)
    if zone not in {'underwater', 'above_zero'}:
        return None
    bar = bars[idx]
    cross_price = calculate_cross_trigger_price(point.ema8, point.ema17, point.dea)
    trend_price = calculate_trend_keep_price(point.ema8, point.ema17, point.dif, point.dea)
    close = bar.close
    limit_up = round(close * (1 + _limit_up_rate(stock['code'])), 2)
    reachable = cross_price <= limit_up + 1e-9
    distance = (cross_price / close) - 1
    trend_distance = (trend_price / close) - 1
    score = (0.08 - abs(distance)) * 100
    if not reachable:
        score -= 100
    summary = (
        f"{stock['code']} {stock['name']}连续 {green_shrink_days} 天MACD绿柱缩短，"
        f"若下一交易日收盘价不低于 {cross_price:.2f} 元则形成"
        f"{'水下' if zone == 'underwater' else '水上'}金叉；"
        f"若不低于 {trend_price:.2f} 元则金叉趋势仍在维持。"
    )
    return AlertCandidate(
        stock_code=stock['code'],
        stock_name=stock['name'],
        full_code=stock['full_code'],
        trade_date=bar.trade_date,
        close_price=close,
        cross_zone=zone,
        next_cross_trigger_price=cross_price,
        cross_trigger_distance_pct=distance,
        next_limit_up_price=limit_up,
        cross_trigger_reachable=reachable,
        cross_trigger_unreachable_reason=None if reachable else 'above_limit_up',
        next_trend_keep_price=trend_price,
        trend_keep_distance_pct=trend_distance,
        macd=point,
        green_shrink_days=green_shrink_days,
        score=score,
        summary=summary,
    )


def _find_candidate_on_date(
    stock: dict[str, str],
    bars: list[DailyBar],
    trade_date: str,
    green_shrink_days: int,
) -> tuple[AlertCandidate, list[MacdPoint], int] | None:
    closes = [bar.close for bar in bars]
    points = compute_macd_points(closes)
    for idx, bar in enumerate(bars):
        if bar.trade_date == trade_date:
            candidate = _make_candidate(stock, bars, idx, points, green_shrink_days)
            return (candidate, points, idx) if candidate else None
    return None


def _last_limit_up_info(sqlite_path: Path | None, stock_code: str, trade_date: str, _session: Any = None) -> dict[str, Any]:
    if _session is not None:
        session = _session
        needs_close = False
    else:
        session_factory = _session_factory(sqlite_path)
        session = session_factory()
        needs_close = True
    try:
        row = session.exec(
            select(DailyHotInfo)
            .where(
                DailyHotInfo.stock_code == stock_code,
                DailyHotInfo.trade_date <= trade_date,
            )
            .order_by(DailyHotInfo.trade_date.desc())  # type: ignore[attr-defined]
            .limit(1)
        ).first()
        if row is None:
            return {
                'last_limit_up_date': None,
                'last_limit_up_theme': None,
                'last_limit_up_days_ago': None,
            }
        days = session.exec(
            select(DailyHotInfo.trade_date)
            .distinct()
            .where(
                DailyHotInfo.trade_date > row.trade_date,
                DailyHotInfo.trade_date <= trade_date,
            )
        ).all()
        return {
            'last_limit_up_date': row.trade_date,
            'last_limit_up_theme': row.hot_theme,
            'last_limit_up_days_ago': len(days),
        }
    finally:
        if needs_close:
            session.close()


def _theme_heat(sqlite_path: Path | None, theme: str | None, trade_date: str, window_days: int = 5, _session: Any = None) -> dict[str, Any]:
    if not theme:
        return {'theme_recent_limit_up_count': 0, 'theme_recent_rank': None, 'theme_heat_level': 'none'}
    if _session is not None:
        session = _session
        needs_close = False
    else:
        session_factory = _session_factory(sqlite_path)
        session = session_factory()
        needs_close = True
    try:
        days = list(session.exec(
            select(DailyHotInfo.trade_date)
            .distinct()
            .where(DailyHotInfo.trade_date <= trade_date)
            .order_by(DailyHotInfo.trade_date.desc())  # type: ignore[attr-defined]
            .limit(window_days)
        ).all())
        if not days:
            return {'theme_recent_limit_up_count': 0, 'theme_recent_rank': None, 'theme_heat_level': 'none'}
        rows = session.exec(
            select(DailyHotInfo).where(
                DailyHotInfo.trade_date.in_(days),  # type: ignore[attr-defined]
                DailyHotInfo.hot_theme != '',
            )
        ).all()
    finally:
        if needs_close:
            session.close()
    theme_stocks: dict[str, set[str]] = {}
    for row in rows:
        theme_stocks.setdefault(row.hot_theme, set()).add(row.stock_code)
    counts = sorted(
        [(theme_name, len(stocks)) for theme_name, stocks in theme_stocks.items()],
        key=lambda item: (-item[1], item[0]),
    )
    rank = next((idx + 1 for idx, item in enumerate(counts) if item[0] == theme), None)
    count = next((item[1] for item in counts if item[0] == theme), 0)
    if rank is not None and rank <= 5 and count >= 5:
        level = 'strong'
    elif rank is not None and rank <= 10 and count >= 3:
        level = 'medium'
    elif count > 0:
        level = 'weak'
    else:
        level = 'none'
    return {
        'theme_recent_limit_up_count': count,
        'theme_recent_rank': rank,
        'theme_heat_level': level,
    }


def _build_sample(
    alert_id: str,
    stock: dict[str, str],
    bars: list[DailyBar],
    points: list[MacdPoint],
    idx: int,
    candidate: AlertCandidate,
    sqlite_path: Path | None,
    _session: Any = None,
) -> dict[str, Any]:
    buy_idx = idx + 1
    if buy_idx >= len(bars):
        status = 'insufficient_data'
        buy_bar = None
    else:
        status = 'pending_cross'
        buy_bar = bars[buy_idx]
    t1_status = 't1_data_missing'
    cross_date = None
    cross_type = 'none'
    sell_date = None
    sell_price = None
    sell_reason = None
    return_pct = None
    holding_days = None
    if buy_bar is not None:
        t1_point = points[buy_idx]
        if t1_point.dif >= t1_point.dea:
            t1_status = 't1_cross_confirmed'
        elif buy_bar.close >= candidate.next_trend_keep_price:
            t1_status = 't1_trend_kept'
        else:
            t1_status = 't1_trend_weakened'
        cross_idx = None
        for probe_idx in range(buy_idx, min(len(bars), buy_idx + 5)):
            if points[probe_idx].dif >= points[probe_idx].dea:
                cross_idx = probe_idx
                break
        if cross_idx is None:
            status = 'cross_failed' if len(bars) >= buy_idx + 5 else 'insufficient_data'
        else:
            cross_date = bars[cross_idx].trade_date
            cross_type = _cross_zone(points[cross_idx])
            status = 'cross_success'
            for sell_idx in range(cross_idx, min(len(bars), cross_idx + 10)):
                if points[sell_idx].hist > 0 and sell_idx > 0 and points[sell_idx].hist < points[sell_idx - 1].hist:
                    sell_date = bars[sell_idx].trade_date
                    sell_price = bars[sell_idx].close
                    sell_reason = 'red_shrink'
                    status = 'sold_by_red_shrink'
                    break
            if sell_price is None and len(bars) > cross_idx + 9:
                sell_idx = cross_idx + 9
                sell_date = bars[sell_idx].trade_date
                sell_price = bars[sell_idx].close
                sell_reason = 'timeout'
                status = 'sold_by_timeout'
            if sell_price is not None:
                return_pct = sell_price / buy_bar.open - 1
                holding_days = bars.index(next(bar for bar in bars if bar.trade_date == sell_date)) - buy_idx + 1
    last_limit = _last_limit_up_info(sqlite_path, stock['code'], candidate.trade_date, _session)
    heat = _theme_heat(sqlite_path, last_limit['last_limit_up_theme'], candidate.trade_date, _session=_session)
    created_at = _now()
    return {
        'id': str(uuid.uuid4()),
        'alert_result_id': alert_id,
        'stock_code': stock['code'],
        'stock_name': stock['name'],
        'alert_date': candidate.trade_date,
        'alert_close_price': candidate.close_price,
        'next_cross_trigger_price': candidate.next_cross_trigger_price,
        'cross_trigger_distance_pct': candidate.cross_trigger_distance_pct,
        'next_trend_keep_price': candidate.next_trend_keep_price,
        'trend_keep_distance_pct': candidate.trend_keep_distance_pct,
        'alert_macd_dif': candidate.macd.dif,
        'alert_macd_dea': candidate.macd.dea,
        'alert_macd_hist': candidate.macd.hist,
        'alert_cross_zone': candidate.cross_zone,
        **last_limit,
        'theme_heat_window_days': 5,
        **heat,
        'buy_date': buy_bar.trade_date if buy_bar else None,
        'buy_price': buy_bar.open if buy_bar else None,
        't1_close_price': buy_bar.close if buy_bar else None,
        't1_track_status': t1_status,
        't1_macd_dif': points[buy_idx].dif if buy_bar else None,
        't1_macd_dea': points[buy_idx].dea if buy_bar else None,
        't1_macd_hist': points[buy_idx].hist if buy_bar else None,
        'cross_date': cross_date,
        'cross_type': cross_type,
        'sell_date': sell_date,
        'sell_price': sell_price,
        'sell_reason': sell_reason,
        'return_pct': return_pct,
        'holding_days': holding_days,
        'status': status,
        'created_at': created_at,
    }


def _summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    sample_count = len(samples)
    cross_success = [sample for sample in samples if sample['cross_date']]
    completed = [sample for sample in samples if sample['return_pct'] is not None]
    t1_cross = [sample for sample in samples if sample['t1_track_status'] == 't1_cross_confirmed']
    t1_kept = [sample for sample in samples if sample['t1_track_status'] == 't1_trend_kept']
    t1_weakened = [sample for sample in samples if sample['t1_track_status'] == 't1_trend_weakened']
    returns = [float(sample['return_pct']) for sample in completed]
    holding_days = [int(sample['holding_days']) for sample in completed if sample['holding_days'] is not None]
    trend_keep_base = len(t1_cross) + len(t1_kept) + len(t1_weakened)
    confidence = 'insufficient'
    if sample_count >= 50:
        confidence = 'high'
    elif sample_count >= 30:
        confidence = 'medium'
    elif sample_count >= 10:
        confidence = 'low'
    return {
        'backtest_sample_count': sample_count,
        'backtest_cross_success_count': len(cross_success),
        'backtest_cross_success_rate': len(cross_success) / sample_count if sample_count else None,
        'backtest_t1_cross_confirmed_count': len(t1_cross),
        'backtest_t1_trend_kept_count': len(t1_kept),
        'backtest_t1_trend_weakened_count': len(t1_weakened),
        'backtest_t1_trend_keep_rate': (len(t1_cross) + len(t1_kept)) / trend_keep_base if trend_keep_base else None,
        'backtest_completed_trade_count': len(completed),
        'backtest_profit_trade_count': sum(1 for value in returns if value > 0),
        'backtest_win_rate': sum(1 for value in returns if value > 0) / len(returns) if returns else None,
        'backtest_avg_return_pct': sum(returns) / len(returns) if returns else None,
        'backtest_max_return_pct': max(returns) if returns else None,
        'backtest_max_loss_pct': min(returns) if returns else None,
        'backtest_avg_holding_days': sum(holding_days) / len(holding_days) if holding_days else None,
        'backtest_confidence_level': confidence,
    }


def _build_backtest_samples(
    alert_id: str,
    stock: dict[str, str],
    bars: list[DailyBar],
    current_idx: int,
    current_zone: str,
    green_shrink_days: int,
    sqlite_path: Path | None,
    lookback_days: int = 720,
) -> list[dict[str, Any]]:
    points = compute_macd_points([bar.close for bar in bars])
    samples: list[dict[str, Any]] = []
    start_idx = max(0, current_idx - lookback_days)
    for idx in range(start_idx, current_idx):
        candidate = _make_candidate(stock, bars, idx, points, green_shrink_days)
        if candidate and candidate.cross_zone == current_zone:
            samples.append(_build_sample(alert_id, stock, bars, points, idx, candidate, sqlite_path))
    return samples


def _candidate_to_dict(candidate: AlertCandidate) -> dict[str, Any]:
    return {
        'stock_code': candidate.stock_code,
        'stock_name': candidate.stock_name,
        'full_code': candidate.full_code,
        'trade_date': candidate.trade_date,
        'close_price': candidate.close_price,
        'cross_zone': candidate.cross_zone,
        'next_cross_trigger_price': candidate.next_cross_trigger_price,
        'cross_trigger_distance_pct': candidate.cross_trigger_distance_pct,
        'next_limit_up_price': candidate.next_limit_up_price,
        'cross_trigger_reachable': candidate.cross_trigger_reachable,
        'cross_trigger_unreachable_reason': candidate.cross_trigger_unreachable_reason,
        'next_trend_keep_price': candidate.next_trend_keep_price,
        'trend_keep_distance_pct': candidate.trend_keep_distance_pct,
        'macd_dif': candidate.macd.dif,
        'macd_dea': candidate.macd.dea,
        'macd_hist': candidate.macd.hist,
        'green_shrink_days': candidate.green_shrink_days,
        'score': candidate.score,
        'summary': candidate.summary,
    }


def _load_stock(sqlite_path: Path | None, stock_code: str) -> dict[str, str]:
    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        row = session.exec(select(StockList).where(StockList.code == stock_code)).first()
        if row is None:
            raise ValueError(f'未找到股票代码：{stock_code}')
        return {'full_code': row.full_code, 'code': row.code, 'name': row.name}


def validate_stock_macd_alert(
    *,
    stock_code: str,
    end_date: str,
    lookback_days: int = 720,
    green_shrink_days: int = 2,
    cross_zone: str = 'all',
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
) -> dict[str, Any]:
    if cross_zone not in {'all', 'underwater', 'above_zero', 'mixed'}:
        raise ValueError('cross_zone 仅支持 all/underwater/above_zero/mixed')
    stock = _load_stock(sqlite_path, stock_code)
    bars = _load_daily_bars(duckdb_path, [stock['full_code']], end_date).get(stock['full_code'], [])
    if not bars:
        raise ValueError(f'{stock_code} 在 {end_date} 前没有日线数据')
    current_idx = next((idx for idx, bar in enumerate(bars) if bar.trade_date == end_date), None)
    if current_idx is None:
        current_idx = len(bars) - 1
    effective_end_date = bars[current_idx].trade_date

    points = compute_macd_points([bar.close for bar in bars])
    end_candidate = _make_candidate(stock, bars, current_idx, points, green_shrink_days)
    triggered_on_end_date = end_candidate is not None and (
        cross_zone == 'all' or end_candidate.cross_zone == cross_zone
    )

    start_idx = max(0, current_idx - lookback_days)
    matched: list[tuple[int, AlertCandidate]] = []
    for idx in range(start_idx, current_idx + 1):
        candidate = _make_candidate(stock, bars, idx, points, green_shrink_days)
        if candidate and (cross_zone == 'all' or candidate.cross_zone == cross_zone):
            matched.append((idx, candidate))

    latest_candidate = matched[-1][1] if matched else None
    samples = [
        _build_sample('', stock, bars, points, idx, candidate, sqlite_path)
        for idx, candidate in matched
        if idx < current_idx
    ]
    return {
        'stock_code': stock['code'],
        'stock_name': stock['name'],
        'full_code': stock['full_code'],
        'end_date': effective_end_date,
        'lookback_days': lookback_days,
        'green_shrink_days': green_shrink_days,
        'cross_zone': cross_zone,
        'triggered_on_end_date': triggered_on_end_date,
        'latest_candidate': _candidate_to_dict(latest_candidate) if latest_candidate else None,
        'end_date_candidate': _candidate_to_dict(end_candidate) if end_candidate else None,
        'summary': _summarize_samples(samples),
        'samples': samples,
        'disclaimer': DISCLAIMER,
    }


def _sample_from_dict(sample: dict[str, Any]) -> MacdAlertBacktestSample:
    return MacdAlertBacktestSample(**sample)


def _insert_samples(session: Any, samples: list[dict[str, Any]]) -> None:
    if not samples:
        return
    for sample in samples:
        session.add(_sample_from_dict(sample))


def _upsert_alert(session: Any, candidate: AlertCandidate, stock: dict[str, str], samples_summary: dict[str, Any], sqlite_path: Path | None) -> str:
    now = _now()
    existing = session.exec(
        select(MacdAlertResult).where(
            MacdAlertResult.trade_date == candidate.trade_date,
            MacdAlertResult.stock_code == candidate.stock_code,
            MacdAlertResult.pattern_key == PATTERN_KEY,
            MacdAlertResult.cross_zone == candidate.cross_zone,
        )
    ).first()
    alert_id = existing.id if existing else str(uuid.uuid4())
    created_at = existing.created_at if existing else now
    last_limit = _last_limit_up_info(sqlite_path, stock['code'], candidate.trade_date, session)
    heat = _theme_heat(sqlite_path, last_limit['last_limit_up_theme'], candidate.trade_date, _session=session)
    row = MacdAlertResult(
        id=alert_id,
        trade_date=candidate.trade_date,
        stock_code=candidate.stock_code,
        stock_name=candidate.stock_name,
        pattern_key=PATTERN_KEY,
        pattern_name=PATTERN_NAME,
        cross_zone=candidate.cross_zone,
        close_price=candidate.close_price,
        next_cross_trigger_price=candidate.next_cross_trigger_price,
        cross_trigger_distance_pct=candidate.cross_trigger_distance_pct,
        next_limit_up_price=candidate.next_limit_up_price,
        cross_trigger_reachable=1 if candidate.cross_trigger_reachable else 0,
        cross_trigger_unreachable_reason=candidate.cross_trigger_unreachable_reason,
        next_trend_keep_price=candidate.next_trend_keep_price,
        trend_keep_distance_pct=candidate.trend_keep_distance_pct,
        macd_dif=candidate.macd.dif,
        macd_dea=candidate.macd.dea,
        macd_hist=candidate.macd.hist,
        green_shrink_days=candidate.green_shrink_days,
        **last_limit,
        theme_heat_window_days=5,
        **heat,
        next_track_date=None,
        track_status='pending',
        tracked_close_price=None,
        tracked_macd_dif=None,
        tracked_macd_dea=None,
        tracked_macd_hist=None,
        tracked_at=None,
        backtest_lookback_days=720,
        **samples_summary,
        score=candidate.score,
        summary=candidate.summary,
        status='active',
        created_at=created_at,
        updated_at=now,
    )
    if existing:
        session.delete(existing)
        session.flush()
    session.add(row)
    return alert_id


def scan_macd_alerts(
    *,
    trade_date: str,
    universe_scope: str = 'market',
    markets: list[str] | None = None,
    exclude_st: bool = True,
    green_shrink_days: int = 2,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    if universe_scope != 'market':
        raise ValueError('第一版仅支持 market 股票池')
    target_markets = markets or ['主板']
    stocks = _load_universe(sqlite_path, target_markets, exclude_st)
    task_repo = InitTaskRepo(sqlite_path) if task_id else None
    if task_repo and task_id:
        task_repo.set_total_items(task_id, len(stocks))
        task_repo.set_processed_items(task_id, 0)
    bars_by_code = _load_daily_bars(duckdb_path, [stock['full_code'] for stock in stocks], trade_date)
    matches: list[tuple[dict[str, str], AlertCandidate, list[dict[str, Any]]]] = []
    for stock in stocks:
        if task_repo and task_id:
            if task_repo.is_task_terminated(task_id):
                break
            task_repo.set_current_label(task_id, stock['full_code'])
        bars = bars_by_code.get(stock['full_code'], [])
        found = _find_candidate_on_date(stock, bars, trade_date, green_shrink_days)
        if found:
            candidate, _, idx = found
            samples = _build_backtest_samples(
                '',
                stock,
                bars,
                idx,
                candidate.cross_zone,
                green_shrink_days,
                sqlite_path,
            )
            matches.append((stock, candidate, samples))
        if task_repo and task_id:
            task_repo.increment_processed_items(task_id)

    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        for stock, candidate, samples in matches:
            summary = _summarize_samples(samples)
            alert_id = _upsert_alert(session, candidate, stock, summary, sqlite_path)
            for sample in session.exec(
                select(MacdAlertBacktestSample).where(MacdAlertBacktestSample.alert_result_id == alert_id)
            ).all():
                session.delete(sample)
            fixed_samples = [{**sample, 'alert_result_id': alert_id} for sample in samples]
            _insert_samples(session, fixed_samples)
        session.commit()
    results = list_macd_alert_results(trade_date=trade_date, limit=100, sqlite_path=sqlite_path)
    return {
        'trade_date': trade_date,
        'total_scanned': len(stocks),
        'matched_count': len(matches),
        'report_generatable': True,
        'report_generation_hint': '可按需调用 POST /api/macd-alerts/reports 生成 HTML/PDF 报告。',
        'results': results,
    }


def create_macd_alert_scan_task(
    *,
    trade_date: str,
    universe_scope: str = 'market',
    markets: list[str] | None = None,
    exclude_st: bool = True,
    green_shrink_days: int = 2,
    sqlite_path: Path | None = None,
) -> dict[str, Any]:
    if universe_scope != 'market':
        raise ValueError('第一版仅支持 market 股票池')
    if markets != ['主板']:
        raise ValueError('第一版后台扫描仅支持默认主板股票池')
    if exclude_st is not True:
        raise ValueError('第一版后台扫描默认排除 ST')
    from app.modules.market_data.initializer import create_task

    day = trade_date.replace('-', '')
    task = create_task(day, day, task_type=MACD_ALERT_SCAN_TASK_TYPE, sqlite_path=sqlite_path)
    _pending_green_shrink_days[task['task_id']] = green_shrink_days
    return task


def _load_alert_rows(sqlite_path: Path | None, source_trade_date: str) -> list[Any]:
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        return list(session.exec(
            select(MacdAlertResult)
            .where(MacdAlertResult.trade_date == source_trade_date, MacdAlertResult.status == 'active')
            .order_by(MacdAlertResult.score.desc())  # type: ignore[attr-defined]
        ).all())


def track_macd_alerts(
    *,
    trade_date: str,
    source_trade_date: str,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
) -> dict[str, Any]:
    ensure_sqlite_schema(sqlite_path)
    rows = _load_alert_rows(sqlite_path, source_trade_date)
    full_codes = [f"{row.stock_code}.SH" if str(row.stock_code).startswith('6') else f"{row.stock_code}.SZ" for row in rows]
    bars_by_code = _load_daily_bars(duckdb_path, full_codes, trade_date)
    counts = {'cross_confirmed': 0, 'trend_kept': 0, 'trend_weakened': 0, 'data_missing': 0}
    results = []
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        for row, full_code in zip(rows, full_codes, strict=True):
            bars = bars_by_code.get(full_code, [])
            closes = [bar.close for bar in bars]
            points = compute_macd_points(closes)
            idx = next((bar_idx for bar_idx, bar in enumerate(bars) if bar.trade_date == trade_date), None)
            if idx is None:
                status = 'data_missing'
                close = dif = dea = hist = None
            else:
                point = points[idx]
                close = bars[idx].close
                dif = point.dif
                dea = point.dea
                hist = point.hist
                if point.dif >= point.dea:
                    status = 'cross_confirmed'
                elif close >= float(row.next_trend_keep_price):
                    status = 'trend_kept'
                else:
                    status = 'trend_weakened'
            counts[status] += 1
            row.next_track_date = trade_date
            row.track_status = status
            row.tracked_close_price = close
            row.tracked_macd_dif = dif
            row.tracked_macd_dea = dea
            row.tracked_macd_hist = hist
            now = _now()
            row.tracked_at = now
            row.updated_at = now
            session.add(row)
            results.append({'id': row.id, 'stock_code': row.stock_code, 'track_status': status})
        session.commit()
    return {
        'trade_date': trade_date,
        'source_trade_date': source_trade_date,
        'tracked_count': len(rows),
        'cross_confirmed_count': counts['cross_confirmed'],
        'trend_kept_count': counts['trend_kept'],
        'trend_weakened_count': counts['trend_weakened'],
        'data_missing_count': counts['data_missing'],
        'report_generatable': True,
        'report_generation_hint': '可按需调用 POST /api/macd-alerts/reports 生成 HTML/PDF 报告。',
        'results': results,
    }


def list_macd_alert_results(
    *,
    trade_date: str,
    pattern_key: str | None = None,
    cross_zone: str | None = None,
    limit: int = 20,
    offset: int = 0,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    ensure_sqlite_schema(sqlite_path)
    statement = select(MacdAlertResult).where(MacdAlertResult.trade_date == trade_date)
    if pattern_key:
        statement = statement.where(MacdAlertResult.pattern_key == pattern_key)
    if cross_zone:
        statement = statement.where(MacdAlertResult.cross_zone == cross_zone)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        rows = session.exec(
            statement
            .order_by(
                MacdAlertResult.score.desc(),  # type: ignore[attr-defined]
                MacdAlertResult.cross_trigger_distance_pct,
            )
            .offset(offset)
            .limit(limit)
        ).all()
    return [row.model_dump() for row in rows]


def list_macd_alert_backtest_samples(
    *,
    alert_result_id: str,
    limit: int = 20,
    offset: int = 0,
    sqlite_path: Path | None = None,
) -> list[dict[str, Any]]:
    ensure_sqlite_schema(sqlite_path)
    session_factory = _session_factory(sqlite_path)
    with session_factory() as session:
        rows = session.exec(
            select(MacdAlertBacktestSample)
            .where(MacdAlertBacktestSample.alert_result_id == alert_result_id)
            .order_by(MacdAlertBacktestSample.alert_date.desc())  # type: ignore[attr-defined]
            .offset(offset)
            .limit(limit)
        ).all()
    return [row.model_dump() for row in rows]


def get_latest_trade_date(*, duckdb_path: Path | None = None) -> str | None:
    ensure_duckdb_schema(duckdb_path)
    conn = connect_duckdb(duckdb_path)
    try:
        row = conn.execute(
            "SELECT MAX(CAST(trade_date AS DATE)) FROM day_level_trade_data"
        ).fetchone()
    finally:
        conn.close()
    return str(row[0])[:10] if row and row[0] is not None else None


def get_macd_daily_brief(
    *,
    trade_date: str | None = None,
    limit: int = 10,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
) -> dict[str, Any]:
    latest_trade_date = get_latest_trade_date(duckdb_path=duckdb_path)
    requested_trade_date = trade_date or latest_trade_date
    if requested_trade_date is None:
        return {
            'trade_date': None,
            'latest_trade_date': None,
            'requested_trade_date': trade_date,
            'is_data_fresh': False,
            'data_warning': '本地暂无日线数据，无法生成 MACD 预警日报。',
            'new_alert_count': 0,
            'tracking': {
                'tracked_count': 0,
                'cross_confirmed_count': 0,
                'trend_kept_count': 0,
                'trend_weakened_count': 0,
                'data_missing_count': 0,
            },
            'report_generatable': True,
            'report_generation_hint': '可调用 generate_macd_alert_report 生成 HTML/PDF 报告。',
            'highlights': [],
        }
    alerts = list_macd_alert_results(
        trade_date=requested_trade_date,
        limit=min(limit, 30),
        sqlite_path=sqlite_path,
    )
    tracking_counts = {
        'tracked_count': sum(1 for row in alerts if row.get('track_status') != 'pending'),
        'cross_confirmed_count': sum(1 for row in alerts if row.get('track_status') == 'cross_confirmed'),
        'trend_kept_count': sum(1 for row in alerts if row.get('track_status') == 'trend_kept'),
        'trend_weakened_count': sum(1 for row in alerts if row.get('track_status') == 'trend_weakened'),
        'data_missing_count': sum(1 for row in alerts if row.get('track_status') == 'data_missing'),
    }
    is_data_fresh = latest_trade_date is not None and latest_trade_date >= requested_trade_date
    warning = None
    if latest_trade_date and latest_trade_date < requested_trade_date:
        warning = f'本地最新日线数据为 {latest_trade_date}，请求交易日为 {requested_trade_date}，预警结果可能不可用或过期。'
    return {
        'trade_date': requested_trade_date,
        'latest_trade_date': latest_trade_date,
        'requested_trade_date': requested_trade_date,
        'is_data_fresh': is_data_fresh,
        'data_warning': warning,
        'new_alert_count': len(alerts),
        'tracking': tracking_counts,
        'report_generatable': True,
        'report_generation_hint': '可调用 generate_macd_alert_report 生成 HTML/PDF 报告。',
        'highlights': alerts[: min(limit, 30)],
    }
