from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.db.duckdb_storage import connect_duckdb, ensure_duckdb_schema
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.market_data.initializer import create_task, get_task
from app.modules.macd_alert.service import (
    calculate_cross_trigger_price,
    calculate_trend_keep_price,
    scan_macd_alerts,
    track_macd_alerts,
    validate_stock_macd_alert,
)
from app.modules.macd_alert.indicators import compute_macd_points


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
