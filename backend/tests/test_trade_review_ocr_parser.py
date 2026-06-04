from app.modules.trade_review.ocr_parser import _parse_lines, _strip_num


def test_strip_num_handles_commas_percent_and_invalid_text() -> None:
    assert _strip_num('14,641.39') == 14641.39
    assert _strip_num('17.95%') == 17.95
    assert _strip_num('bad') is None


def test_parse_lines_extracts_review_summary_and_operations() -> None:
    lines = [
        'PingAn',
        '2026\u5e7405\u670801\u65e5 2026\u5e7405\u670803\u65e5',
        '2,628.33 17.95%',
        '\u7d2f\u8ba1\u4e70\u5165',
        '10,000',
        '\u7d2f\u8ba1\u5356\u51fa',
        '12,628.33',
        '\u5efa\u4ed3 2026-05-01 09:44:37',
        '\u4ef7\u683c 10.00',
        '\u6570\u91cf 100',
        '\u91d1\u989d 1,000.00',
        '\u51cf\u4ed3 2026-05-02 10:15:00',
        '\u4ef7\u683c 10.80',
        '\u6570\u91cf 50',
        '\u91d1\u989d 540.00',
        '\u6e05\u4ed3 2026-05-03 14:30:01',
        '\u4ef7\u683c 11.20',
        '\u6570\u91cf 50',
        '\u91d1\u989d 560.00',
    ]

    parsed = _parse_lines(lines)
    assert parsed.stock_name == 'PingAn'
    assert parsed.start_date == '2026-05-01'
    assert parsed.end_date == '2026-05-03'
    assert parsed.realized_pnl == 2628.33
    assert parsed.return_rate == 0.1795
    assert parsed.total_buy_amount == 10000
    assert parsed.total_sell_amount == 12628.33
    assert parsed.status == 'closed'
    assert [op.operation_type for op in parsed.operations] == ['buy', 'reduce', 'sell']
    assert [op.trade_time for op in parsed.operations] == [
        '2026-05-01T09:44:37',
        '2026-05-02T10:15:00',
        '2026-05-03T14:30:01',
    ]


def test_parse_lines_falls_back_to_open_when_only_buy_side_exists() -> None:
    parsed = _parse_lines(
        [
            'Tech',
            '\u5efa\u4ed3 2026-05-01 09:44:37',
            '\u4ef7\u683c 25.50',
            '\u6570\u91cf 200',
            '\u91d1\u989d 5,100.00',
        ]
    )

    assert parsed.status == 'open'
    assert len(parsed.operations) == 1
    assert parsed.operations[0].amount == 5100.0
