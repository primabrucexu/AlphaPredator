from app.db.duckdb_storage import ensure_duckdb_schema, run_sql


def test_ensure_duckdb_schema_creates_stock_linkage_tables(tmp_path):
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
    assert 'stock_linkage_backtest_job' in tables
    assert 'stock_linkage_trigger_event' in tables
    assert 'stock_linkage_baseline_metric' in tables
    assert 'stock_linkage_backtest_result' in tables


def test_stock_linkage_result_schema_has_sorting_metrics(tmp_path):
    duckdb_path = tmp_path / 'alphapredator.duckdb'

    ensure_duckdb_schema(duckdb_path)

    columns = {
        row[0]
        for row in run_sql(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'stock_linkage_backtest_result'",
            duckdb_path=duckdb_path,
        )
    }
    assert {
        'condition_probability',
        'baseline_probability',
        'probability_lift',
        'lift_multiple',
        'trigger_coverage_rate',
        'confidence_level',
        'score',
    }.issubset(columns)
