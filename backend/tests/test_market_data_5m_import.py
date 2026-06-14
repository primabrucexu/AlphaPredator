from unittest.mock import patch

from app.db.duckdb_storage import ensure_duckdb_schema, run_sql
from app.modules.market_data.data_source import fetch_5m_history_rows
from app.modules.market_data.initializer import write_duckdb_5m_stock_bulk


def test_fetch_5m_history_rows_reuses_history_endpoint_with_5m_interval():
    payload = [
        {'t': '20250102093000', 'o': 10, 'h': 10.5, 'l': 9.9, 'c': 10.3, 'pc': 10.0, 'v': 1200, 'a': 123456},
        {'t': '20250102093500', 'o': 10.3, 'h': 10.8, 'l': 10.2, 'c': 10.6, 'pc': 10.3, 'v': 1400, 'a': 234567},
    ]

    with (
        patch('app.modules.market_data.data_source._get_mairui_licence', return_value='LICENCE'),
        patch('app.modules.market_data.data_source._is_unlisted_new_stock', return_value=False),
        patch('app.modules.market_data.data_source._mairui_get_json', return_value=payload) as get_json,
    ):
        rows = fetch_5m_history_rows('000001.SZ', '2025-01-02', '2025-01-02')

    get_json.assert_called_once_with(
        'hsstock/history/000001.SZ/5/n/LICENCE',
        params={'st': '20250102', 'et': '20250102'},
    )
    assert rows == [
        {
            'full_code': '000001.SZ',
            'trade_date': '2025-01-02 09:30:00',
            'open': 10.0,
            'high': 10.5,
            'low': 9.9,
            'close': 10.3,
            'pre_close': 10.0,
            'change': 0.3,
            'pct_chg': 3.0,
            'vol': 1200.0,
            'amount': 123456.0,
            'is_up_limit': False,
            'is_down_limit': False,
            'is_stop': False,
        },
        {
            'full_code': '000001.SZ',
            'trade_date': '2025-01-02 09:35:00',
            'open': 10.3,
            'high': 10.8,
            'low': 10.2,
            'close': 10.6,
            'pre_close': 10.3,
            'change': 0.3,
            'pct_chg': 2.9126,
            'vol': 1400.0,
            'amount': 234567.0,
            'is_up_limit': False,
            'is_down_limit': False,
            'is_stop': False,
        },
    ]


def test_write_duckdb_5m_stock_bulk_replaces_stock_range(tmp_path):
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    ensure_duckdb_schema(duckdb_path)

    first_rows = [
        {
            'full_code': '000001.SZ',
            'trade_date': '2025-01-02 09:30:00',
            'open': 10,
            'high': 10.5,
            'low': 9.9,
            'close': 10.3,
            'pre_close': 10,
            'change': 0.3,
            'pct_chg': 3,
            'vol': 100,
            'amount': 1000,
            'is_up_limit': False,
            'is_down_limit': False,
            'is_stop': False,
        }
    ]
    second_rows = [{**first_rows[0], 'close': 10.4, 'change': 0.4, 'pct_chg': 4}]

    write_duckdb_5m_stock_bulk('000001.SZ', first_rows, '20250102', '20250102', duckdb_path)
    write_duckdb_5m_stock_bulk('000001.SZ', second_rows, '20250102', '20250102', duckdb_path)

    rows = run_sql(
        'SELECT full_code, CAST(trade_date AS VARCHAR), close FROM "5m_level_trade_data" ORDER BY trade_date',
        duckdb_path=duckdb_path,
    )
    assert rows == [('000001.SZ', '2025-01-02 09:30:00', rows[0][2])]
    assert float(rows[0][2]) == 10.4
