import csv
import json
from pathlib import Path

from app.db.sqlite import connect_sqlite
from app.modules.market_data.hot_sector_importer import OCRToken, import_hot_sector_images
from app.modules.market_data.importer import import_market_data_batch
from app.modules.market_data.service import MarketDataService

STOCK_POOL_ROWS = [
    {
        'stock_code': '300308',
        'stock_name': '中际旭创',
        'sectors': 'AI 算力|CPO',
        'ai_quick_summary': '算力主线延续，趋势与量能共振，但不宜在加速段盲目追高。',
    }
]

DAILY_SNAPSHOT_ROWS = [
    {
        'trade_date': '2026-04-30',
        'stock_code': '300308',
        'current_price': '167.53',
        'change_amount': '5.93',
        'change_pct': '3.66',
        'turnover_amount_billion': '82.40',
        'turnover_rate': '5.24',
    }
]

DAILY_BAR_ROWS = [
    {'stock_code': '300308', 'trade_date': '2026-04-24', 'open_price': '157.60', 'high_price': '160.20', 'low_price': '156.80', 'close_price': '159.40', 'volume': '18320000'},
    {'stock_code': '300308', 'trade_date': '2026-04-25', 'open_price': '159.80', 'high_price': '162.60', 'low_price': '158.90', 'close_price': '161.70', 'volume': '19180000'},
    {'stock_code': '300308', 'trade_date': '2026-04-28', 'open_price': '162.10', 'high_price': '164.30', 'low_price': '160.70', 'close_price': '163.50', 'volume': '20540000'},
    {'stock_code': '300308', 'trade_date': '2026-04-29', 'open_price': '163.80', 'high_price': '166.10', 'low_price': '162.90', 'close_price': '165.40', 'volume': '21490000'},
    {'stock_code': '300308', 'trade_date': '2026-04-30', 'open_price': '165.90', 'high_price': '168.40', 'low_price': '164.70', 'close_price': '167.53', 'volume': '22860000'},
]

HOT_SECTORS_PAYLOAD = {
    'trade_date': '2026-04-30',
    'items': [
        {'name': '算力', 'trend_label': '持续 3 日', 'heat_score': 93},
        {'name': '机器人', 'trend_label': '持续 2 日', 'heat_score': 88},
        {'name': '军工', 'trend_label': '新晋热点', 'heat_score': 74},
    ],
}

FAKE_OCR_ROWS = {
    '0428.png': [
        [(1030, '商业航天*2', 0.98), (1900, 'www.jiuy', 0.50)],
        [(50, '2天2板', 0.97), (230, '002081.SZ', 0.99), (455, '金螳螂', 0.98), (650, '9:30:24', 0.99), (850, '118.7', 0.95), (1030, '5.3', 0.95), (1150, '商业航天+建筑装饰', 0.97)],
        [(1030, 'AI硬件*1', 0.98)],
        [(50, '3天3板', 0.97), (230, '300308.SZ', 0.99), (455, '中际旭创', 0.98), (650, '10:10:10', 0.99), (850, '167.5', 0.95), (1030, '82.4', 0.95), (1150, 'AI服务器+CPO+光模块', 0.97)],
    ],
    '0429.png': [
        [(1030, '商业航天*1', 0.98)],
        [(50, '4天2板', 0.97), (230, '002342.SZ', 0.99), (455, '巨力索具', 0.98), (650, '14:56:51', 0.99), (850, '204.5', 0.95), (1030, '56.7', 0.95), (1150, '商业航天+军工', 0.97)],
        [(1030, 'AI硬件*2', 0.98)],
        [(50, '2天2板', 0.97), (230, '603115.SH', 0.99), (455, '海星股份', 0.98), (650, '10:46:03', 0.99), (850, '117.8', 0.95), (1030, '19.8', 0.95), (1150, 'AI服务器+航空航天', 0.97)],
        [(50, '2天2板', 0.97), (230, '600699.SH', 0.99), (455, '均胜电子', 0.98), (650, '14:27:15', 0.99), (850, '389.0', 0.95), (1030, '28.5', 0.95), (1150, '光模块+人形机器人', 0.97)],
    ],
    '0430.png': [
        [(1030, 'AI硬件*2', 0.98)],
        [(50, '2天2板', 0.97), (230, '301486.SZ', 0.99), (455, '致尚科技', 0.98), (650, '14:10:00', 0.99), (850, '151.5', 0.95), (1030, '41.4', 0.95), (1150, '算力+CPO+机器人', 0.97)],
        [(50, '2天2板', 0.97), (230, '688661.SH', 0.99), (455, '和林微纳', 0.98), (650, '10:40:04', 0.99), (850, '157.1', 0.95), (1030, '13.3', 0.95), (1150, '芯片测试探针+英伟达供应商', 0.97)],
        [(1030, '国产芯片*2', 0.98)],
        [(50, '3天2板', 0.97), (230, '600520.SH', 0.99), (455, '三佳科技', 0.98), (650, '14:55:44', 0.99), (850, '48.3', 0.95), (1030, '8.7', 0.95), (1150, '先进封装+AI芯片+机器人', 0.97)],
        [(50, '3天2板', 0.97), (230, '605298.SH', 0.99), (455, '必得科技', 0.98), (650, '10:04:18', 0.99), (850, '111.0', 0.95), (1030, '1.8', 0.95), (1150, '半导体资产注入预期+高铁', 0.97)],
    ],
}


def _write_csv(file_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with file_path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prepare_market_batch(batch_dir: Path) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(batch_dir / 'stock_pool.csv', ['stock_code', 'stock_name', 'sectors', 'ai_quick_summary'], STOCK_POOL_ROWS)
    _write_csv(
        batch_dir / 'daily_stock_snapshots.csv',
        ['trade_date', 'stock_code', 'current_price', 'change_amount', 'change_pct', 'turnover_amount_billion', 'turnover_rate'],
        DAILY_SNAPSHOT_ROWS,
    )
    _write_csv(
        batch_dir / 'daily_bars.csv',
        ['stock_code', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume'],
        DAILY_BAR_ROWS,
    )
    (batch_dir / 'hot_sectors.json').write_text(json.dumps(HOT_SECTORS_PAYLOAD, ensure_ascii=False, indent=2), encoding='utf-8')


def _build_fake_ocr_tokens(row_specs: list[list[tuple[int, str, float]]]) -> list[OCRToken]:
    tokens: list[OCRToken] = []
    for row_index, row in enumerate(row_specs):
        y1 = 100 + row_index * 60
        y2 = y1 + 24
        for x1, text, score in row:
            tokens.append(
                OCRToken(
                    text=text,
                    score=score,
                    x1=float(x1),
                    x2=float(x1 + max(60, len(text) * 16)),
                    y1=float(y1),
                    y2=float(y2),
                )
            )
    return tokens


def test_import_hot_sector_images_populates_layered_tables_and_overrides_manual_hot_sectors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    batch_dir = tmp_path / 'market-batch'
    image_dir = tmp_path / 'hot-sector-images'
    sqlite_path = tmp_path / 'alphapredator.db'
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    daily_bars_parquet_path = tmp_path / 'parquet' / 'stock_daily_bars.parquet'
    market_snapshot_path = tmp_path / 'parquet' / 'market_snapshot.json'

    _prepare_market_batch(batch_dir)
    import_market_data_batch(
        batch_dir,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        daily_bars_parquet_path=daily_bars_parquet_path,
        market_snapshot_path=market_snapshot_path,
    )

    image_dir.mkdir(parents=True, exist_ok=True)
    for file_name in FAKE_OCR_ROWS:
        (image_dir / file_name).write_bytes(b'fake-image')

    def _fake_run_ocr(file_path: Path) -> list[OCRToken]:
        return _build_fake_ocr_tokens(FAKE_OCR_ROWS[file_path.name])

    monkeypatch.setattr('app.modules.market_data.hot_sector_importer._run_ocr', _fake_run_ocr)

    result = import_hot_sector_images(
        image_dir,
        year=2026,
        sqlite_path=sqlite_path,
        import_batch='phase2-test-batch',
    )

    assert result.source_file_count == 3
    assert result.stock_fact_count == 9
    assert result.sector_mapping_count >= 12
    assert result.daily_sector_count == 6
    assert result.latest_trade_date == '2026-04-30'

    connection = connect_sqlite(sqlite_path)
    try:
        source_count = connection.execute('SELECT COUNT(*) AS count FROM hot_sector_image_sources').fetchone()['count']
        stock_fact_count = connection.execute('SELECT COUNT(*) AS count FROM hot_sector_stock_facts').fetchone()['count']
        mapping_count = connection.execute('SELECT COUNT(*) AS count FROM hot_sector_sector_mappings').fetchone()['count']
        daily_aggregate_count = connection.execute('SELECT COUNT(*) AS count FROM hot_sector_daily_aggregates').fetchone()['count']
        recent_3d_row = connection.execute(
            '''
            SELECT days_present_3d, trend_tag
            FROM hot_sector_recent_3d
            WHERE trade_date = '2026-04-30' AND sector_name_canonical = 'AI硬件'
            '''
        ).fetchone()
        representative_row = connection.execute(
            '''
            SELECT representative_stock_codes_json
            FROM hot_sector_daily_aggregates
            WHERE trade_date = '2026-04-30' AND sector_name_canonical = '国产芯片'
            '''
        ).fetchone()
    finally:
        connection.close()

    assert source_count == 3
    assert stock_fact_count == 9
    assert mapping_count >= 12
    assert daily_aggregate_count == 6
    assert recent_3d_row['days_present_3d'] == 3
    assert recent_3d_row['trend_tag'] == 'persistent'
    assert sorted(json.loads(representative_row['representative_stock_codes_json'])) == ['600520.SH', '605298.SH']

    service = MarketDataService(
        snapshot_path=market_snapshot_path,
        daily_bars_parquet_path=daily_bars_parquet_path,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )
    overview = service.get_market_overview()

    assert overview.summary.trade_date == '2026-04-30'
    assert [sector.trade_date for sector in overview.hot_sectors] == ['2026-04-30', '2026-04-30']
    assert [sector.name for sector in overview.hot_sectors] == ['AI硬件', '国产芯片']
    assert [sector.trend_label for sector in overview.hot_sectors] == ['持续 3 日', '新晋热点']
    assert overview.hot_sectors[0].heat_score > overview.hot_sectors[1].heat_score


def test_market_overview_uses_latest_available_image_date_when_snapshot_date_is_newer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    batch_dir = tmp_path / 'market-batch'
    image_dir = tmp_path / 'hot-sector-images'
    sqlite_path = tmp_path / 'alphapredator.db'
    duckdb_path = tmp_path / 'alphapredator.duckdb'
    daily_bars_parquet_path = tmp_path / 'parquet' / 'stock_daily_bars.parquet'
    market_snapshot_path = tmp_path / 'parquet' / 'market_snapshot.json'

    _prepare_market_batch(batch_dir)
    import_market_data_batch(
        batch_dir,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        daily_bars_parquet_path=daily_bars_parquet_path,
        market_snapshot_path=market_snapshot_path,
    )

    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / '0427.png').write_bytes(b'fake-image')

    def _fake_run_ocr(file_path: Path) -> list[OCRToken]:
        return _build_fake_ocr_tokens(
            [
                [(1030, '商业航天*1', 0.98)],
                [(50, '2天2板', 0.97), (230, '002081.SZ', 0.99), (455, '金螳螂', 0.98), (650, '9:30:24', 0.99), (850, '118.7', 0.95), (1030, '5.3', 0.95), (1150, '商业航天+建筑装饰', 0.97)],
            ]
        )

    monkeypatch.setattr('app.modules.market_data.hot_sector_importer._run_ocr', _fake_run_ocr)

    import_hot_sector_images(
        image_dir,
        year=2026,
        sqlite_path=sqlite_path,
        import_batch='phase2-date-fallback',
    )

    service = MarketDataService(
        snapshot_path=market_snapshot_path,
        daily_bars_parquet_path=daily_bars_parquet_path,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )
    overview = service.get_market_overview()

    assert overview.summary.trade_date == '2026-04-30'
    assert [sector.trade_date for sector in overview.hot_sectors] == ['2026-04-27']
    assert [sector.name for sector in overview.hot_sectors] == ['商业航天']
    assert [sector.trend_label for sector in overview.hot_sectors] == ['新晋热点']
