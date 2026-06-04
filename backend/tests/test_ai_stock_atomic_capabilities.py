from decimal import Decimal
from pathlib import Path

import pytest

from app.db.duckdb_storage import ensure_duckdb_schema, connect_duckdb
from app.db.sqlite import ensure_sqlite_schema, connect_sqlite
from app.modules.ai_stock.atomic_capabilities import AtomicCapabilities


def _prepare_test_dbs(tmp_path: Path) -> tuple[Path, Path]:
    sqlite_path = tmp_path / 'test.sqlite3'
    duckdb_path = tmp_path / 'test.duckdb'
    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_schema(duckdb_path)

    sqlite_conn = connect_sqlite(sqlite_path)
    try:
        sqlite_conn.execute(
            '''
            INSERT INTO stock_list (full_code, code, name, is_st, cnspell, market)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            ['000001.SZ', '000001', '平安银行', 0, 'payh', '主板'],
        )
        sqlite_conn.commit()
    finally:
        sqlite_conn.close()

    duck_conn = connect_duckdb(duckdb_path)
    try:
        duck_conn.execute(
            '''
            INSERT INTO day_level_trade_data
                (full_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, is_up_limit, is_down_limit)
            VALUES
                ('000001.SZ', '2026-05-26', 10.00, 10.30, 9.95, 10.20, 10.00, 0.20, 0.0200, 1000, 10000, FALSE, FALSE),
                ('000001.SZ', '2026-05-27', 10.20, 10.60, 10.18, 10.60, 10.20, 0.40, 0.0392, 2000, 22000, TRUE, FALSE),
                ('000001.SZ', '2026-05-28', 10.50, 10.55, 10.00, 10.10, 10.60, -0.50, -0.0471, 800, 9000, FALSE, FALSE)
            '''
        )
    finally:
        duck_conn.close()
    return sqlite_path, duckdb_path


def _insert_daily_hot_info(
    sqlite_path: Path,
    *,
    trade_date: str,
    stock_code: str,
    hot_theme: str,
) -> None:
    sqlite_conn = connect_sqlite(sqlite_path)
    try:
        sqlite_conn.execute(
            '''
            INSERT INTO daily_hot_info
                (trade_date, limit_up_time, stock_code, name, streak_text, hot_theme, reason, source, short_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [trade_date, '09:30:00', stock_code, '平安银行', '首板', hot_theme, 'test', 'jygs', ''],
        )
        sqlite_conn.commit()
    finally:
        sqlite_conn.close()


def test_atomic_capabilities_decimal_and_basic_rules(tmp_path: Path) -> None:
    sqlite_path, duckdb_path = _prepare_test_dbs(tmp_path)
    _insert_daily_hot_info(sqlite_path, trade_date='2026-05-28', stock_code='000001', hot_theme='银行+金融科技')
    _insert_daily_hot_info(sqlite_path, trade_date='2026-05-27', stock_code='000001', hot_theme='银行')
    caps = AtomicCapabilities(sqlite_path=sqlite_path, duckdb_path=duckdb_path)

    assert caps.is_trade_day('2026-05-28') is True
    assert caps.prev_trade_day('2026-05-28') == '2026-05-27'
    assert caps.is_st('000001', '2026-05-28') is False
    assert caps.is_limit_up('000001', '2026-05-27') is True
    assert caps.limit_up_count('000001', '2026-05-28', 3) == 1
    assert caps.days_since_last_limit_up('000001', '2026-05-28', 3) == 1

    close = caps.close_price('000001', '2026-05-28')
    turnover = caps.turnover('000001', '2026-05-28')
    pct_chg = caps.pct_chg('000001', '2026-05-28')
    ma3 = caps.ma('000001', '2026-05-28', 3)
    avg_turnover = caps.avg_turnover('000001', '2026-05-28', 3)
    drawdown = caps.drawdown_from_peak('000001', '2026-05-28', 3)

    assert isinstance(close, Decimal)
    assert isinstance(turnover, Decimal)
    assert isinstance(pct_chg, Decimal)
    assert isinstance(ma3, Decimal)
    assert isinstance(avg_turnover, Decimal)
    assert isinstance(drawdown, Decimal)

    assert close == Decimal('10.100000')
    assert caps.is_above_ma('000001', '2026-05-28', 3) is False
    assert caps.rolling_avg_volume('000001', '2026-05-28', 3) == Decimal('1266.666666666666666666666667')
    assert caps.volume_ratio('000001', '2026-05-28', 3) == Decimal('0.6315789473684210526315789472')
    assert caps.limit_up_streak('000001', '2026-05-28') == 0
    assert caps.limit_up_streak('000001', '2026-05-27') == 1

    assert caps.retest_days_after_limit_up('000001', '2026-05-28', 10) == 1
    assert caps.retest_drawdown_after_limit_up('000001', '2026-05-28', 10) == Decimal('0.05660377358490566037735849057')
    assert caps.retest_volume_ratio_after_limit_up('000001', '2026-05-28', 10) == Decimal('0.4')
    assert caps.close_near_high_ratio('000001', '2026-05-28') == Decimal('0.1818181818181818181818181818')
    assert caps.gap_open_ratio('000001', '2026-05-28') == Decimal('-0.009433962264150943396226415094')
    assert caps.is_breakout_day('000001', '2026-05-28') is False
    assert caps.is_failed_breakout('000001', '2026-05-28', 2) is False
    assert caps.hot_theme_score('000001', '2026-05-28', 3) == Decimal('2.5')
    assert caps.liquidity_level('000001', '2026-05-28', 3) == 1

    assert caps.forward_return('000001', '2026-05-26', 2) == Decimal('-0.009803921568627450980392156863')
    assert caps.max_drawdown_forward('000001', '2026-05-26', 2) == Decimal('0.05660377358490566037735849057')
    assert caps.distribution_risk_flag('000001', '2026-05-28', 3) is False
    assert caps.volatility_regime('000001', '2026-05-28', 3) == 'low'
    assert caps.event_risk_flag('000001', '2026-05-28') is False


def test_atomic_capabilities_validate_inputs_and_missing_data(tmp_path: Path) -> None:
    sqlite_path, duckdb_path = _prepare_test_dbs(tmp_path)
    caps = AtomicCapabilities(sqlite_path=sqlite_path, duckdb_path=duckdb_path)

    with pytest.raises(ValueError, match='stock_code is required'):
        caps.close_price('', '2026-05-28')
    with pytest.raises(ValueError, match='invalid stock_code'):
        caps.close_price('ABC', '2026-05-28')
    with pytest.raises(ValueError, match='invalid trade_date'):
        caps.is_trade_day('20260528')
    with pytest.raises(ValueError, match='n must be > 0'):
        caps.prev_trade_day('2026-05-28', 0)
    with pytest.raises(ValueError, match='window must be > 0'):
        caps.limit_up_count('000001', '2026-05-28', 0)
    with pytest.raises(ValueError, match='horizon must be > 0'):
        caps.forward_return('000001', '2026-05-28', 0)
    with pytest.raises(ValueError, match='stock not found in stock_list: 999999'):
        caps.is_st('999999', '2026-05-28')
    with pytest.raises(ValueError, match='not enough previous trade days before 2026-05-26'):
        caps.prev_trade_day('2026-05-26')
    with pytest.raises(ValueError, match='daily row not found'):
        caps.close_price('000001', '2026-05-30')


def test_atomic_capabilities_return_none_or_fallback_on_short_windows(tmp_path: Path) -> None:
    sqlite_path, duckdb_path = _prepare_test_dbs(tmp_path)
    caps = AtomicCapabilities(sqlite_path=sqlite_path, duckdb_path=duckdb_path)

    assert caps.days_since_last_limit_up('000001', '2026-05-26', 1) is None
    assert caps.ma('000001', '2026-05-28', 5) is None
    assert caps.is_above_ma('000001', '2026-05-28', 5) is False
    assert caps.rolling_avg_volume('000001', '2026-05-28', 5) is None
    assert caps.volume_ratio('000001', '2026-05-28', 5) is None
    assert caps.amplitude('000001', '2026-05-28', 5) is None
    assert caps.avg_turnover('000001', '2026-05-28', 5) is None
    assert caps.forward_return('000001', '2026-05-28', 2) is None
    assert caps.max_drawdown_forward('000001', '2026-05-28', 2) is None
    assert caps.volatility_regime('000001', '2026-05-28', 5) == 'unknown'
    assert caps.hot_theme_score('000001', '2026-05-28', 3) == Decimal('0')


def test_atomic_capabilities_accept_full_code_and_prev_trade_offsets(tmp_path: Path) -> None:
    sqlite_path, duckdb_path = _prepare_test_dbs(tmp_path)
    caps = AtomicCapabilities(sqlite_path=sqlite_path, duckdb_path=duckdb_path)

    assert caps.close_price('000001.SZ', '2026-05-28') == Decimal('10.100000')
    assert caps.prev_trade_day('2026-05-28', 2) == '2026-05-26'
