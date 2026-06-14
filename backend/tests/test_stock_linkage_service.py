from app.db.duckdb_storage import ensure_duckdb_schema, run_sql
from app.db.sqlite import ensure_sqlite_schema
from app.modules.stock_linkage.service import (
    StockLinkageBacktestRequest,
    create_stock_linkage_backtest_job,
    get_stock_linkage_job,
    run_stock_linkage_backtest,
    start_stock_linkage_backtest_job,
)
from app.repositories.stock_list_repo import StockListRepo


def _insert_5m_rows(duckdb_path):
    rows = [
        # A triggers single_bar_return > 2% and intraday_return_from_pre_close > 3% on 2025-01-02 09:30.
        ('000001.SZ', '2025-01-02 09:30:00', 10, 10.5, 9.9, 10.4, 10.0, 0.4, 4.0, 1000, 100000, False, False, False),
        ('000001.SZ', '2025-01-02 09:35:00', 10.4, 10.5, 10.2, 10.3, 10.4, -0.1, -0.9615, 1000, 100000, False, False, False),
        ('000001.SZ', '2025-01-03 09:30:00', 10.3, 10.4, 10.1, 10.2, 10.3, -0.1, -0.9709, 1000, 100000, False, False, False),
        ('000001.SZ', '2025-01-03 09:35:00', 10.2, 10.3, 10.0, 10.1, 10.2, -0.1, -0.9804, 1000, 100000, False, False, False),
        # B is non-ST and hits 2% from A's t+1 open on T day high and close, plus next day high/close.
        ('000002.SZ', '2025-01-02 09:30:00', 20, 20.1, 19.9, 20.0, 19.8, 0.2, 1.0101, 1000, 100000, False, False, False),
        ('000002.SZ', '2025-01-02 09:35:00', 20.0, 20.7, 20.0, 20.5, 20.0, 0.5, 2.5, 1000, 100000, False, False, False),
        ('000002.SZ', '2025-01-03 09:30:00', 20.5, 20.9, 20.3, 20.8, 20.5, 0.3, 1.4634, 1000, 100000, False, False, False),
        ('000002.SZ', '2025-01-03 09:35:00', 20.8, 21.0, 20.7, 20.9, 20.8, 0.1, 0.4808, 1000, 100000, False, False, False),
        # C is ST and must be excluded from B pool.
        ('000003.SZ', '2025-01-02 09:30:00', 30, 31, 29.9, 30.5, 30.0, 0.5, 1.6667, 1000, 100000, False, False, False),
        ('000003.SZ', '2025-01-02 09:35:00', 30.5, 32, 30.5, 31.5, 30.5, 1.0, 3.2787, 1000, 100000, False, False, False),
    ]
    placeholders = ', '.join(['?'] * 14)
    for row in rows:
        run_sql(
            f'INSERT INTO "5m_level_trade_data" '
            f'(full_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, '
            f'is_up_limit, is_down_limit, is_stop) VALUES ({placeholders})',
            params=list(row),
            duckdb_path=duckdb_path,
        )


def test_run_stock_linkage_backtest_persists_results_for_manual_a(tmp_path):
    sqlite_path = tmp_path / 'alphapredator.sqlite3'
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    ensure_sqlite_schema(sqlite_path)
    ensure_duckdb_schema(duckdb_path)
    StockListRepo(sqlite_path).replace_all(
        [
            ('000001.SZ', '000001', 'A股票', 0, 'AGP', '主板'),
            ('000002.SZ', '000002', 'B股票', 0, 'BGP', '主板'),
            ('000003.SZ', '000003', 'ST股票', 1, 'STGP', '主板'),
        ]
    )
    _insert_5m_rows(duckdb_path)

    summary = run_stock_linkage_backtest(
        StockLinkageBacktestRequest(
            a_select_mode='manual_single',
            manual_a_full_code='000001.SZ',
            start_date='2025-01-02',
            end_date='2025-01-03',
            min_sample_count=1,
        ),
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )

    assert summary.status == 'success'
    assert summary.trigger_event_count >= 2
    assert summary.result_count > 0
    rows = run_sql(
        "SELECT a_full_code, b_full_code, trigger_type, trigger_threshold, observation_type, "
        "target_threshold, sample_count, hit_count, condition_probability, confidence_level "
        "FROM stock_linkage_backtest_result WHERE job_id = ? "
        "AND b_full_code = '000002.SZ' AND observation_type = 't_day_high' AND target_threshold = 0.02 "
        "ORDER BY trigger_type, trigger_threshold",
        params=[summary.job_id],
        duckdb_path=duckdb_path,
    )
    assert rows
    assert all(row[0] == '000001.SZ' for row in rows)
    assert all(row[1] == '000002.SZ' for row in rows)
    assert all(row[6] == 1 for row in rows)
    assert all(row[7] == 1 for row in rows)
    assert all(float(row[8]) == 1.0 for row in rows)

    excluded = run_sql(
        "SELECT COUNT(*) FROM stock_linkage_backtest_result WHERE job_id = ? AND b_full_code = '000003.SZ'",
        params=[summary.job_id],
        duckdb_path=duckdb_path,
    )[0][0]
    assert excluded == 0


def test_create_stock_linkage_backtest_job_persists_pending_job(tmp_path):
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    ensure_duckdb_schema(duckdb_path)

    job = create_stock_linkage_backtest_job(
        StockLinkageBacktestRequest(
            a_select_mode='manual_single',
            manual_a_full_code='000001.SZ',
            start_date='2025-01-02',
            end_date='2025-01-03',
            min_sample_count=30,
            job_name='手动测试',
        ),
        duckdb_path=duckdb_path,
    )

    assert job.status == 'pending'
    assert job.job_name == '手动测试'
    assert job.manual_a_full_code == '000001.SZ'

    stored = get_stock_linkage_job(job.job_id, duckdb_path=duckdb_path)
    assert stored is not None
    assert stored.status == 'pending'
    assert stored.start_date == '2025-01-02'


def test_start_stock_linkage_backtest_job_marks_running_and_uses_background_runner(monkeypatch, tmp_path):
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    job = create_stock_linkage_backtest_job(
        StockLinkageBacktestRequest(
            a_select_mode='manual_single',
            manual_a_full_code='000001.SZ',
            start_date='2025-01-02',
            end_date='2025-01-03',
        ),
        duckdb_path=duckdb_path,
    )
    started_threads = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            started_threads.append({'target': target, 'args': args, 'daemon': daemon})

        def start(self):
            return None

    monkeypatch.setattr('app.modules.stock_linkage.service.threading.Thread', FakeThread)

    started = start_stock_linkage_backtest_job(job.job_id, duckdb_path=duckdb_path)

    assert started is True
    assert get_stock_linkage_job(job.job_id, duckdb_path=duckdb_path).status == 'running'
    assert len(started_threads) == 1
    assert started_threads[0]['args'][0] == job.job_id
    assert started_threads[0]['daemon'] is True


def test_start_stock_linkage_backtest_job_rejects_when_another_job_is_running(monkeypatch, tmp_path):
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    first = create_stock_linkage_backtest_job(
        StockLinkageBacktestRequest(
            a_select_mode='manual_single',
            manual_a_full_code='000001.SZ',
            start_date='2025-01-02',
            end_date='2025-01-03',
        ),
        duckdb_path=duckdb_path,
    )
    second = create_stock_linkage_backtest_job(
        StockLinkageBacktestRequest(
            a_select_mode='manual_single',
            manual_a_full_code='000002.SZ',
            start_date='2025-01-02',
            end_date='2025-01-03',
        ),
        duckdb_path=duckdb_path,
    )

    class FakeThread:
        def __init__(self, target, args, daemon):
            pass

        def start(self):
            return None

    monkeypatch.setattr('app.modules.stock_linkage.service.threading.Thread', FakeThread)

    assert start_stock_linkage_backtest_job(first.job_id, duckdb_path=duckdb_path) is True
    assert start_stock_linkage_backtest_job(second.job_id, duckdb_path=duckdb_path) is False
    assert get_stock_linkage_job(second.job_id, duckdb_path=duckdb_path).status == 'pending'
