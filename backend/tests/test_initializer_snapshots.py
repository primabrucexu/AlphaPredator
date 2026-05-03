from app.modules.market_data.initializer import _derive_snapshots_from_bars


def test_derive_snapshots_from_bars_uses_latest_trade_date_and_change_fields():
    stock_pool = [
        {'stock_code': '000001', 'stock_name': '平安银行'},
        {'stock_code': '000002', 'stock_name': '万科A'},
    ]
    daily_bars = [
        {
            'stock_code': '000001',
            'trade_date': '2026-05-01',
            'open_price': 10,
            'high_price': 10.5,
            'low_price': 9.8,
            'close_price': 10,
            'volume': 1000,
        },
        {
            'stock_code': '000001',
            'trade_date': '2026-05-02',
            'open_price': 10.1,
            'high_price': 11,
            'low_price': 10,
            'close_price': 11,
            'volume': 1200,
        },
        {
            'stock_code': '000002',
            'trade_date': '2026-05-02',
            'open_price': 20,
            'high_price': 20.2,
            'low_price': 19.5,
            'close_price': 19.8,
            'volume': 900,
        },
    ]

    snapshots = _derive_snapshots_from_bars(daily_bars, stock_pool)
    by_code = {row['stock_code']: row for row in snapshots}

    assert len(snapshots) == 2
    assert by_code['000001']['trade_date'] == '2026-05-02'
    assert by_code['000001']['current_price'] == 11.0
    assert by_code['000001']['change_amount'] == 1.0
    assert by_code['000001']['change_pct'] == 10.0

    assert by_code['000002']['trade_date'] == '2026-05-02'
    assert by_code['000002']['current_price'] == 19.8
    # Single bar fallback: no previous close, change should be 0
    assert by_code['000002']['change_amount'] == 0.0
    assert by_code['000002']['change_pct'] == 0.0


def test_derive_snapshots_from_bars_returns_empty_for_empty_input():
    assert _derive_snapshots_from_bars([], []) == []

