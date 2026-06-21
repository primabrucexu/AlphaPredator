from app.db.duckdb_storage import ensure_duckdb_schema, run_sql
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema


def test_ensure_duckdb_schema_only_creates_kline_tables(tmp_path):
    duckdb_path = tmp_path / 'alphapredator.duckdb'

    ensure_duckdb_schema(duckdb_path)

    tables = {
        row[0]
        for row in run_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'",
            duckdb_path=duckdb_path,
        )
    }
    assert '5m_level_trade_data' in tables
    assert 'day_level_trade_data' in tables
    assert 'stock_linkage_backtest_job' not in tables
    assert 'stock_linkage_trigger_event' not in tables
    assert 'stock_linkage_baseline_metric' not in tables
    assert 'stock_linkage_backtest_result' not in tables


def test_sqlite_schema_creates_stock_linkage_tables(tmp_path):
    sqlite_path = tmp_path / 'alphapredator.sqlite3'

    ensure_sqlite_schema(sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        tables = {
            row['name']
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert 'stock_linkage_backtest_job' in tables
    assert 'stock_linkage_trigger_event' in tables
    assert 'stock_linkage_baseline_metric' in tables
    assert 'stock_linkage_backtest_result' in tables


def test_stock_linkage_result_sqlite_schema_has_sorting_metrics(tmp_path):
    sqlite_path = tmp_path / 'alphapredator.sqlite3'

    ensure_sqlite_schema(sqlite_path)

    conn = connect_sqlite(sqlite_path)
    try:
        columns = {
            row['name']
            for row in conn.execute('PRAGMA table_info(stock_linkage_backtest_result)').fetchall()
        }
    finally:
        conn.close()
    assert {
        'condition_probability',
        'baseline_probability',
        'probability_lift',
        'lift_multiple',
        'trigger_coverage_rate',
        'confidence_level',
        'score',
    }.issubset(columns)
