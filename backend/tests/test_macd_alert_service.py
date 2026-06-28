from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.initializer import create_task, get_task
from app.modules.macd_alert.indicators import MacdPoint, compute_macd_points
from app.modules.macd_alert import service as macd_alert_service
from app.modules.macd_alert.service import (
    AlertCandidate,
    DailyBar,
    _build_backtest_samples,
    _build_sample,
    _recent_limit_ups,
    _summarize_samples,
    calculate_cross_trigger_price,
    calculate_trend_keep_price,
    create_macd_alert_scan_task,
    scan_macd_alerts,
    track_macd_alerts,
    validate_stock_macd_alert,
)


def test_recent_limit_ups_returns_latest_three_with_theme_and_preferred_short_reason() -> None:
    tmp_path = _workspace_tmp_dir('macd-recent-limit-ups')
    sqlite_path = tmp_path / 'macd-alert.db'
    ensure_sqlite_schema(sqlite_path)
    conn = connect_sqlite(sqlite_path)
    try:
        conn.executemany(
            """
            INSERT INTO daily_hot_info
            (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, short_reason, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ('2026-01-02', '09:30', '000001', '测试一号', '首板', '机器人', '机器人长描述', '', 'test'),
                ('2026-01-04', '09:30', '000001', '测试一号', '首板', '算力', '算力长描述', '算力短描述', 'test'),
                ('2026-01-06', '09:30', '000001', '测试一号', '首板', '电力', '电力长描述', '电力短描述', 'test'),
                ('2026-01-08', '09:30', '000001', '测试一号', '首板', '芯片', '芯片长描述', '芯片短描述', 'test'),
                ('2026-01-09', '09:30', '000002', '测试二号', '首板', '无关', '无关描述', '无关短描述', 'test'),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    rows = _recent_limit_ups(sqlite_path, '000001', '2026-01-07')

    assert rows == [
        {'trade_date': '2026-01-06', 'theme': '电力', 'description': '电力短描述'},
        {'trade_date': '2026-01-04', 'theme': '算力', 'description': '算力短描述'},
        {'trade_date': '2026-01-02', 'theme': '机器人', 'description': '机器人长描述'},
    ]


def test_backtest_summary_only_uses_post_cross_returns_for_win_rate_and_average_return() -> None:
    samples = [
        {
            'cross_date': None,
            'return_pct': -0.20,
            'holding_days': 4,
            't1_track_status': 't1_trend_weakened',
        },
        {
            'cross_date': '2026-01-03',
            'return_pct': 0.10,
            'holding_days': 2,
            't1_track_status': 't1_cross_confirmed',
        },
        {
            'cross_date': '2026-01-04',
            'return_pct': None,
            'holding_days': None,
            't1_track_status': 't1_trend_kept',
        },
    ]

    summary = _summarize_samples(samples)

    assert summary['backtest_cross_success_count'] == 2
    assert summary['backtest_completed_trade_count'] == 1
    assert summary['backtest_profit_trade_count'] == 1
    assert summary['backtest_win_rate'] == pytest.approx(1.0)
    assert summary['backtest_avg_return_pct'] == pytest.approx(0.10)
    assert summary['backtest_max_loss_pct'] == pytest.approx(0.10)
    assert summary['backtest_avg_holding_days'] == pytest.approx(2.0)


def _workspace_tmp_dir(name: str) -> Path:
    path = Path('tmp') / f'{name}-{uuid.uuid4().hex}'
    path.mkdir(parents=True, exist_ok=False)
    return path


def _seed_stock_list(sqlite_path: Path) -> None:
    ensure_sqlite_schema(sqlite_path)
    conn = connect_sqlite(sqlite_path)
    try:
        conn.executemany(
            """
            INSERT INTO stock_list (full_code, code, name, is_st, market)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ('000001.SZ', '000001', '测试一号', 0, '主板'),
                ('000002.SZ', '000002', '测试二号', 0, '主板'),
            ],
        )
        conn.executemany(
            """
            INSERT INTO daily_hot_info
            (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ('2026-01-05', '09:30', '000001', '测试一号', '首板', '机器人', '测试原因', 'test'),
                ('2026-01-06', '09:30', '000002', '测试二号', '首板', '机器人', '测试原因', 'test'),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _seed_daily_bars(duckdb_path: Path, closes: list[float], *, code: str = '000001.SZ') -> None:
    ensure_duckdb_schema(duckdb_path)
    conn = connect_duckdb(duckdb_path)
    try:
        rows = []
        for idx, close in enumerate(closes, start=1):
            day = f'2026-01-{idx:02d}'
            rows.append(
                [
                    code,
                    day,
                    close - 0.2,
                    close + 0.3,
                    close - 0.5,
                    close,
                    close - 0.1,
                    0,
                    0,
                    1000,
                    100000,
                    False,
                    False,
                ]
            )
        conn.executemany(
            """
            INSERT INTO day_level_trade_data
            (full_code, trade_date, open, high, low, close, pre_close, change, pct_chg,
             vol, amount, is_up_limit, is_down_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    finally:
        conn.close()


def test_backtest_sample_sells_before_cross_when_broken_trend_is_not_repaired() -> None:
    stock = {'full_code': '000001.SZ', 'code': '000001', 'name': '测试一号'}
    bars = [
        DailyBar('000001.SZ', '2026-01-01', 10.0, 10.2, 9.8, 10.0, 9.9, False, False),
        DailyBar('000001.SZ', '2026-01-02', 10.0, 10.2, 9.8, 9.9, 10.0, False, False),
        DailyBar('000001.SZ', '2026-01-03', 9.8, 10.0, 9.6, 9.7, 9.9, False, False),
        DailyBar('000001.SZ', '2026-01-04', 9.6, 9.8, 9.4, 9.5, 9.7, False, False),
        DailyBar('000001.SZ', '2026-01-05', 9.4, 9.6, 9.2, 9.3, 9.5, False, False),
    ]
    points = [
        MacdPoint(10.0, 10.1, -0.20, -0.10, -0.20),
        MacdPoint(9.9, 10.0, -0.22, -0.10, -0.24),
        MacdPoint(9.8, 9.9, -0.24, -0.10, -0.28),
        MacdPoint(9.7, 9.8, -0.26, -0.10, -0.32),
        MacdPoint(9.6, 9.7, -0.28, -0.10, -0.36),
    ]
    candidate = AlertCandidate(
        stock_code='000001',
        stock_name='测试一号',
        full_code='000001.SZ',
        trade_date='2026-01-01',
        close_price=10.0,
        cross_zone='underwater',
        next_cross_trigger_price=10.5,
        cross_trigger_distance_pct=0.05,
        next_limit_up_price=11.0,
        cross_trigger_reachable=True,
        cross_trigger_unreachable_reason=None,
        next_trend_keep_price=9.95,
        trend_keep_distance_pct=-0.005,
        macd=points[0],
        green_shrink_days=2,
        score=1.0,
        summary='测试预警',
    )

    sample = _build_sample('', stock, bars, points, 0, candidate, None)

    assert sample['cross_date'] is None
    assert sample['sell_date'] == '2026-01-05'
    assert sample['sell_price'] == pytest.approx(9.3)
    assert sample['sell_reason'] == 'trend_broken'
    assert sample['return_pct'] == pytest.approx(9.3 / 10.0 - 1)
    assert sample['holding_days'] == 4


def test_backtest_sample_keeps_observing_when_broken_trend_is_repaired_before_cross() -> None:
    stock = {'full_code': '000001.SZ', 'code': '000001', 'name': '测试一号'}
    bars = [
        DailyBar('000001.SZ', '2026-01-01', 10.0, 10.2, 9.8, 10.0, 9.9, False, False),
        DailyBar('000001.SZ', '2026-01-02', 10.0, 10.2, 9.8, 9.9, 10.0, False, False),
        DailyBar('000001.SZ', '2026-01-03', 9.8, 10.0, 9.6, 9.8, 9.9, False, False),
        DailyBar('000001.SZ', '2026-01-04', 9.8, 10.1, 9.7, 10.0, 9.8, False, False),
        DailyBar('000001.SZ', '2026-01-05', 10.0, 10.4, 9.9, 10.2, 10.0, False, False),
        DailyBar('000001.SZ', '2026-01-06', 10.2, 10.6, 10.1, 10.5, 10.2, False, False),
    ]
    points = [
        MacdPoint(10.0, 10.1, -0.20, -0.10, -0.20),
        MacdPoint(9.9, 10.0, -0.22, -0.10, -0.24),
        MacdPoint(9.8, 9.9, -0.20, -0.10, -0.20),
        MacdPoint(9.9, 9.95, -0.16, -0.10, -0.12),
        MacdPoint(10.1, 10.0, 0.02, -0.02, 0.08),
        MacdPoint(10.3, 10.1, 0.08, 0.00, 0.16),
    ]
    candidate = AlertCandidate(
        stock_code='000001',
        stock_name='测试一号',
        full_code='000001.SZ',
        trade_date='2026-01-01',
        close_price=10.0,
        cross_zone='underwater',
        next_cross_trigger_price=10.5,
        cross_trigger_distance_pct=0.05,
        next_limit_up_price=11.0,
        cross_trigger_reachable=True,
        cross_trigger_unreachable_reason=None,
        next_trend_keep_price=9.95,
        trend_keep_distance_pct=-0.005,
        macd=points[0],
        green_shrink_days=2,
        score=1.0,
        summary='测试预警',
    )

    sample = _build_sample('', stock, bars, points, 0, candidate, None)

    assert sample['cross_date'] == '2026-01-05'
    assert sample['sell_date'] is None
    assert sample['sell_reason'] is None
    assert sample['status'] == 'cross_success'


def test_backtest_sample_sells_when_macd_bar_shrinks_after_cross() -> None:
    stock = {'full_code': '000001.SZ', 'code': '000001', 'name': '测试一号'}
    bars = [
        DailyBar('000001.SZ', '2026-01-01', 10.0, 10.2, 9.8, 10.0, 9.9, False, False),
        DailyBar('000001.SZ', '2026-01-02', 10.0, 10.2, 9.8, 10.1, 10.0, False, False),
        DailyBar('000001.SZ', '2026-01-03', 10.0, 10.1, 9.7, 9.8, 10.1, False, False),
        DailyBar('000001.SZ', '2026-01-04', 9.8, 10.0, 9.6, 9.7, 9.8, False, False),
    ]
    points = [
        MacdPoint(10.0, 10.1, -0.08, -0.07, -0.02),
        MacdPoint(10.1, 10.1, -0.06, -0.07, 0.02),
        MacdPoint(9.9, 10.0, -0.09, -0.08, -0.02),
        MacdPoint(9.8, 9.9, -0.10, -0.08, -0.04),
    ]
    candidate = AlertCandidate(
        stock_code='000001',
        stock_name='测试一号',
        full_code='000001.SZ',
        trade_date='2026-01-01',
        close_price=10.0,
        cross_zone='underwater',
        next_cross_trigger_price=10.0,
        cross_trigger_distance_pct=0.0,
        next_limit_up_price=11.0,
        cross_trigger_reachable=True,
        cross_trigger_unreachable_reason=None,
        next_trend_keep_price=9.8,
        trend_keep_distance_pct=-0.02,
        macd=points[0],
        green_shrink_days=2,
        score=1.0,
        summary='测试预警',
    )

    sample = _build_sample('', stock, bars, points, 0, candidate, None)

    assert sample['cross_date'] == '2026-01-02'
    assert sample['sell_date'] == '2026-01-03'
    assert sample['sell_price'] == pytest.approx(9.8)
    assert sample['sell_reason'] == 'macd_bar_shrink'
    assert sample['return_pct'] == pytest.approx(9.8 / 10.0 - 1)
    assert sample['holding_days'] == 2
    assert sample['status'] == 'sold_by_red_shrink'


def test_backtest_sample_sells_when_cross_timeout_without_active_broken_trend() -> None:
    stock = {'full_code': '000001.SZ', 'code': '000001', 'name': '测试一号'}
    bars = [
        DailyBar('000001.SZ', '2026-01-01', 20.0, 20.2, 19.8, 20.0, 19.9, False, False),
        DailyBar('000001.SZ', '2026-01-02', 19.8, 20.0, 19.0, 19.1, 20.0, False, False),
        DailyBar('000001.SZ', '2026-01-03', 19.0, 19.5, 18.8, 19.4, 19.1, False, False),
        DailyBar('000001.SZ', '2026-01-04', 19.5, 20.1, 19.4, 20.0, 19.4, False, False),
        DailyBar('000001.SZ', '2026-01-05', 20.2, 20.3, 19.8, 20.0, 20.0, False, False),
        DailyBar('000001.SZ', '2026-01-06', 20.0, 20.2, 19.7, 19.8, 20.0, False, False),
        DailyBar('000001.SZ', '2026-01-07', 19.8, 20.0, 19.6, 19.7, 19.8, False, False),
        DailyBar('000001.SZ', '2026-01-08', 19.7, 20.0, 19.6, 19.9, 19.7, False, False),
        DailyBar('000001.SZ', '2026-01-09', 19.8, 20.0, 19.7, 19.8, 19.9, False, False),
        DailyBar('000001.SZ', '2026-01-10', 19.8, 19.9, 19.4, 19.5, 19.8, False, False),
    ]
    points = [
        MacdPoint(20.0, 20.2, -0.46, -0.20, -0.52),
        MacdPoint(19.4, 19.9, -0.60, -0.31, -0.58),
        MacdPoint(19.5, 19.8, -0.65, -0.41, -0.48),
        MacdPoint(19.7, 19.7, -0.60, -0.46, -0.28),
        MacdPoint(19.8, 19.7, -0.54, -0.49, -0.10),
        MacdPoint(19.8, 19.7, -0.51, -0.50, -0.02),
        MacdPoint(19.8, 19.7, -0.46, -0.49, 0.06),
        MacdPoint(19.9, 19.8, -0.42, -0.47, 0.10),
        MacdPoint(19.8, 19.8, -0.43, -0.46, 0.06),
        MacdPoint(19.7, 19.8, -0.45, -0.46, 0.02),
    ]
    candidate = AlertCandidate(
        stock_code='000001',
        stock_name='测试一号',
        full_code='000001.SZ',
        trade_date='2026-01-01',
        close_price=20.0,
        cross_zone='underwater',
        next_cross_trigger_price=22.7,
        cross_trigger_distance_pct=0.135,
        next_limit_up_price=22.0,
        cross_trigger_reachable=False,
        cross_trigger_unreachable_reason='above_limit_up',
        next_trend_keep_price=19.4,
        trend_keep_distance_pct=-0.03,
        macd=points[0],
        green_shrink_days=2,
        score=-100.0,
        summary='测试预警',
    )

    sample = _build_sample('', stock, bars, points, 0, candidate, None)

    assert sample['buy_date'] == '2026-01-02'
    assert sample['buy_price'] == pytest.approx(19.8)
    assert sample['cross_date'] is None
    assert sample['sell_date'] == '2026-01-06'
    assert sample['sell_price'] == pytest.approx(19.8)
    assert sample['sell_reason'] == 'cross_timeout'
    assert sample['return_pct'] == pytest.approx(19.8 / 19.8 - 1)
    assert sample['holding_days'] == 5
    assert sample['status'] == 'cross_failed'


def test_backtest_samples_count_continuous_alert_range_once(monkeypatch: pytest.MonkeyPatch) -> None:
    stock = {'full_code': '000001.SZ', 'code': '000001', 'name': '测试一号'}
    bars = [
        DailyBar('000001.SZ', '2026-01-01', 10.0, 10.2, 9.8, 10.0, 9.9, False, False),
        DailyBar('000001.SZ', '2026-01-02', 10.0, 10.2, 9.8, 9.9, 10.0, False, False),
        DailyBar('000001.SZ', '2026-01-03', 9.9, 10.1, 9.7, 9.8, 9.9, False, False),
        DailyBar('000001.SZ', '2026-01-04', 9.8, 10.0, 9.6, 9.7, 9.8, False, False),
        DailyBar('000001.SZ', '2026-01-05', 9.7, 9.9, 9.5, 9.6, 9.7, False, False),
    ]
    points = compute_macd_points([bar.close for bar in bars])

    def fake_make_candidate(
        stock_arg: dict[str, str],
        bars_arg: list[DailyBar],
        idx: int,
        points_arg: list[MacdPoint],
        green_shrink_days: int,
    ) -> AlertCandidate | None:
        if idx not in {1, 2, 3}:
            return None
        return AlertCandidate(
            stock_code=stock_arg['code'],
            stock_name=stock_arg['name'],
            full_code=stock_arg['full_code'],
            trade_date=bars_arg[idx].trade_date,
            close_price=bars_arg[idx].close,
            cross_zone='underwater',
            next_cross_trigger_price=10.5,
            cross_trigger_distance_pct=0.05,
            next_limit_up_price=11.0,
            cross_trigger_reachable=True,
            cross_trigger_unreachable_reason=None,
            next_trend_keep_price=9.5,
            trend_keep_distance_pct=-0.03,
            macd=points_arg[idx],
            green_shrink_days=green_shrink_days,
            score=1.0,
            summary='测试预警',
        )

    monkeypatch.setattr(macd_alert_service, '_make_candidate', fake_make_candidate)

    samples = _build_backtest_samples('', stock, bars, 4, 'underwater', 2, None)

    assert [sample['alert_date'] for sample in samples] == ['2026-01-02']


def test_macd_trigger_price_formula_matches_f06_design() -> None:
    closes = [10, 9.7, 9.4, 9.1, 8.8, 8.7, 8.65, 8.63]
    points = compute_macd_points(closes)
    latest = points[-1]

    cross_price = calculate_cross_trigger_price(latest.ema8, latest.ema17, latest.dea)
    trend_price = calculate_trend_keep_price(latest.ema8, latest.ema17, latest.dif, latest.dea)

    assert cross_price == pytest.approx(9 * latest.dea - 7 * latest.ema8 + 8 * latest.ema17)
    assert trend_price == pytest.approx(
        9 * (latest.dea + 7 / 5 * (latest.dif - latest.dea)) - 7 * latest.ema8 + 8 * latest.ema17
    )


def test_scan_macd_alerts_is_idempotent_and_writes_backtest_summary() -> None:
    tmp_path = _workspace_tmp_dir('macd-alert-service')
    sqlite_path = tmp_path / 'macd-alert.db'
    duckdb_path = tmp_path / 'macd-alert.duckdb'
    _seed_stock_list(sqlite_path)
    _seed_daily_bars(duckdb_path, [10, 9.6, 9.2, 8.8, 8.5, 8.35, 8.3, 8.28, 8.27, 8.27])

    first = scan_macd_alerts(
        trade_date='2026-01-10',
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        green_shrink_days=2,
    )
    second = scan_macd_alerts(
        trade_date='2026-01-10',
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        green_shrink_days=2,
    )

    assert first['matched_count'] == 1
    assert second['matched_count'] == 1

    conn = connect_sqlite(sqlite_path)
    try:
        alert_rows = conn.execute('SELECT * FROM macd_alert_result').fetchall()
        sample_rows = conn.execute('SELECT * FROM macd_alert_backtest_sample').fetchall()
    finally:
        conn.close()

    assert len(alert_rows) == 1
    assert alert_rows[0]['stock_code'] == '000001'
    assert alert_rows[0]['pattern_key'] == 'golden_cross_setup'
    assert alert_rows[0]['backtest_sample_count'] >= 0
    assert len(sample_rows) == alert_rows[0]['backtest_sample_count']


def test_scan_macd_alerts_uses_latest_available_bar_before_non_trading_date() -> None:
    tmp_path = _workspace_tmp_dir('macd-alert-scan-non-trading')
    sqlite_path = tmp_path / 'macd-alert.db'
    duckdb_path = tmp_path / 'macd-alert.duckdb'
    _seed_stock_list(sqlite_path)
    _seed_daily_bars(duckdb_path, [10, 9.6, 9.2, 8.8, 8.5, 8.35, 8.3, 8.28, 8.27, 8.27])

    result = scan_macd_alerts(
        trade_date='2026-01-12',
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        green_shrink_days=2,
    )

    assert result['requested_trade_date'] == '2026-01-12'
    assert result['trade_date'] == '2026-01-10'
    assert result['matched_count'] == 1

    conn = connect_sqlite(sqlite_path)
    try:
        row = conn.execute('SELECT trade_date, stock_code FROM macd_alert_result').fetchone()
    finally:
        conn.close()

    assert row['trade_date'] == '2026-01-10'
    assert row['stock_code'] == '000001'


def test_create_macd_alert_scan_task_uses_effective_trade_date() -> None:
    tmp_path = _workspace_tmp_dir('macd-task-effective-date')
    sqlite_path = tmp_path / 'macd-alert.db'
    duckdb_path = tmp_path / 'macd-alert.duckdb'
    _seed_stock_list(sqlite_path)
    _seed_daily_bars(duckdb_path, [10, 9.6, 9.2, 8.8, 8.5, 8.35, 8.3, 8.28, 8.27, 8.27])

    task = create_macd_alert_scan_task(
        trade_date='2026-01-12',
        universe_scope='market',
        markets=['主板'],
        exclude_st=True,
        green_shrink_days=2,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )

    assert task['start_date'] == '20260110'
    assert task['end_date'] == '20260110'


def test_create_macd_alert_scan_task_uses_default_main_board_when_markets_omitted() -> None:
    tmp_path = _workspace_tmp_dir('macd-task-default-market')
    sqlite_path = tmp_path / 'macd-alert.db'
    duckdb_path = tmp_path / 'macd-alert.duckdb'
    _seed_stock_list(sqlite_path)
    _seed_daily_bars(duckdb_path, [10, 9.6, 9.2, 8.8, 8.5, 8.35, 8.3, 8.28, 8.27, 8.27])

    task = create_macd_alert_scan_task(
        trade_date='2026-01-12',
        universe_scope='market',
        exclude_st=True,
        green_shrink_days=2,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )

    assert task['task_type'] == 'MACD_ALERT_SCAN'
    assert task['start_date'] == '20260110'
    assert task['end_date'] == '20260110'


def test_track_macd_alerts_updates_trend_status() -> None:
    tmp_path = _workspace_tmp_dir('macd-track')
    sqlite_path = tmp_path / 'macd-track.db'
    duckdb_path = tmp_path / 'macd-track.duckdb'
    _seed_stock_list(sqlite_path)
    _seed_daily_bars(duckdb_path, [10, 9.6, 9.2, 8.8, 8.5, 8.35, 8.3, 8.28, 8.27, 8.27, 8.5])

    scan_macd_alerts(
        trade_date='2026-01-10',
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        green_shrink_days=2,
    )

    tracked = track_macd_alerts(
        trade_date='2026-01-11',
        source_trade_date='2026-01-10',
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )

    assert tracked['tracked_count'] == 1
    assert tracked['cross_confirmed_count'] + tracked['trend_kept_count'] >= 1

    conn = connect_sqlite(sqlite_path)
    try:
        row = conn.execute('SELECT track_status, tracked_close_price FROM macd_alert_result').fetchone()
    finally:
        conn.close()

    assert row['track_status'] in {'cross_confirmed', 'trend_kept'}
    assert row['tracked_close_price'] == pytest.approx(8.5)


def test_scan_macd_alerts_updates_task_progress() -> None:
    tmp_path = _workspace_tmp_dir('macd-progress')
    sqlite_path = tmp_path / 'macd-progress.db'
    duckdb_path = tmp_path / 'macd-progress.duckdb'
    _seed_stock_list(sqlite_path)
    _seed_daily_bars(duckdb_path, [10, 9.6, 9.2, 8.8, 8.5, 8.35, 8.3, 8.28, 8.27, 8.27])
    _seed_daily_bars(duckdb_path, [10, 10.1, 10.2, 10.3, 10.4, 10.5], code='000002.SZ')
    task = create_task('20260110', '20260110', task_type='MACD_ALERT_SCAN', sqlite_path=sqlite_path)

    scan_macd_alerts(
        trade_date='2026-01-10',
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        green_shrink_days=2,
        task_id=task['task_id'],
    )

    updated = get_task(task['task_id'], sqlite_path=sqlite_path)
    assert updated is not None
    assert updated['total_items'] == 2
    assert updated['processed_items'] == 2
    assert updated['current_label'] == '000002.SZ'


def test_validate_stock_macd_alert_returns_ephemeral_samples() -> None:
    tmp_path = _workspace_tmp_dir('macd-validate')
    sqlite_path = tmp_path / 'macd-validate.db'
    duckdb_path = tmp_path / 'macd-validate.duckdb'
    _seed_stock_list(sqlite_path)
    _seed_daily_bars(duckdb_path, [10, 9.6, 9.2, 8.8, 8.5, 8.35, 8.3, 8.28, 8.27, 8.27, 8.5])

    result = validate_stock_macd_alert(
        stock_code='000001',
        end_date='2026-01-10',
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        green_shrink_days=2,
        lookback_days=720,
    )

    assert result['stock_code'] == '000001'
    assert result['stock_name'] == '测试一号'
    assert result['end_date'] == '2026-01-10'
    assert result['triggered_on_end_date'] is True
    assert result['latest_candidate']['trade_date'] == '2026-01-10'
    assert result['latest_candidate']['cross_zone'] in {'underwater', 'above_zero'}
    assert result['summary']['backtest_sample_count'] >= 0
    assert len(result['samples']) == result['summary']['backtest_sample_count']

    conn = connect_sqlite(sqlite_path)
    try:
        alert_count = conn.execute('SELECT COUNT(*) FROM macd_alert_result').fetchone()[0]
        sample_count = conn.execute('SELECT COUNT(*) FROM macd_alert_backtest_sample').fetchone()[0]
    finally:
        conn.close()

    assert alert_count == 0
    assert sample_count == 0


def test_validate_stock_macd_alert_uses_latest_bar_before_non_trading_end_date() -> None:
    tmp_path = _workspace_tmp_dir('macd-validate-non-trading')
    sqlite_path = tmp_path / 'macd-validate.db'
    duckdb_path = tmp_path / 'macd-validate.duckdb'
    _seed_stock_list(sqlite_path)
    _seed_daily_bars(duckdb_path, [10, 9.6, 9.2, 8.8, 8.5, 8.35, 8.3, 8.28, 8.27, 8.27, 8.5])

    result = validate_stock_macd_alert(
        stock_code='000001',
        end_date='2026-01-12',
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        green_shrink_days=2,
        lookback_days=720,
    )

    assert result['end_date'] == '2026-01-11'
