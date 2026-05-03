import csv
import json
from pathlib import Path

from app.modules.market_data.importer import import_market_data_batch
from app.modules.market_data.service import MarketDataService


STOCK_POOL_ROWS = [
    {
        'stock_code': '000001',
        'stock_name': '平安银行',
        'sectors': '银行',
        'ai_quick_summary': '量能保持平稳，适合作为防御型观察样本。',
    },
    {
        'stock_code': '300308',
        'stock_name': '中际旭创',
        'sectors': 'AI 算力|CPO',
        'ai_quick_summary': '算力主线延续，趋势与量能共振，但不宜在加速段盲目追高。',
    },
    {
        'stock_code': '601138',
        'stock_name': '工业富联',
        'sectors': '算力|服务器',
        'ai_quick_summary': '板块辨识度较高，适合跟踪是否继续放量突破。',
    },
]

DAILY_SNAPSHOT_ROWS = [
    {
        'trade_date': '2026-04-30',
        'stock_code': '000001',
        'current_price': '11.28',
        'change_amount': '0.14',
        'change_pct': '1.24',
        'turnover_amount_billion': '31.70',
        'turnover_rate': '0.91',
    },
    {
        'trade_date': '2026-04-30',
        'stock_code': '300308',
        'current_price': '167.53',
        'change_amount': '5.93',
        'change_pct': '3.66',
        'turnover_amount_billion': '82.40',
        'turnover_rate': '5.24',
    },
    {
        'trade_date': '2026-04-30',
        'stock_code': '601138',
        'current_price': '26.17',
        'change_amount': '0.61',
        'change_pct': '2.39',
        'turnover_amount_billion': '45.20',
        'turnover_rate': '1.74',
    },
]

DAILY_BAR_ROWS = [
    {'stock_code': '000001', 'trade_date': '2026-04-24', 'open_price': '10.92', 'high_price': '11.05', 'low_price': '10.86', 'close_price': '10.97', 'volume': '51230000', 'turnover_amount_billion': '22.30'},
    {'stock_code': '000001', 'trade_date': '2026-04-25', 'open_price': '10.98', 'high_price': '11.08', 'low_price': '10.91', 'close_price': '11.02', 'volume': '49820000', 'turnover_amount_billion': '21.80'},
    {'stock_code': '000001', 'trade_date': '2026-04-28', 'open_price': '11.03', 'high_price': '11.13', 'low_price': '10.95', 'close_price': '11.08', 'volume': '53410000', 'turnover_amount_billion': '23.50'},
    {'stock_code': '000001', 'trade_date': '2026-04-29', 'open_price': '11.06', 'high_price': '11.16', 'low_price': '11.01', 'close_price': '11.12', 'volume': '47650000', 'turnover_amount_billion': '20.90'},
    {'stock_code': '000001', 'trade_date': '2026-04-30', 'open_price': '11.13', 'high_price': '11.31', 'low_price': '11.08', 'close_price': '11.28', 'volume': '56340000', 'turnover_amount_billion': '31.70'},
    {'stock_code': '300308', 'trade_date': '2026-04-24', 'open_price': '157.60', 'high_price': '160.20', 'low_price': '156.80', 'close_price': '159.40', 'volume': '18320000', 'turnover_amount_billion': '58.30'},
    {'stock_code': '300308', 'trade_date': '2026-04-25', 'open_price': '159.80', 'high_price': '162.60', 'low_price': '158.90', 'close_price': '161.70', 'volume': '19180000', 'turnover_amount_billion': '61.50'},
    {'stock_code': '300308', 'trade_date': '2026-04-28', 'open_price': '162.10', 'high_price': '164.30', 'low_price': '160.70', 'close_price': '163.50', 'volume': '20540000', 'turnover_amount_billion': '67.20'},
    {'stock_code': '300308', 'trade_date': '2026-04-29', 'open_price': '163.80', 'high_price': '166.10', 'low_price': '162.90', 'close_price': '165.40', 'volume': '21490000', 'turnover_amount_billion': '70.80'},
    {'stock_code': '300308', 'trade_date': '2026-04-30', 'open_price': '165.90', 'high_price': '168.40', 'low_price': '164.70', 'close_price': '167.53', 'volume': '22860000', 'turnover_amount_billion': '82.40'},
    {'stock_code': '601138', 'trade_date': '2026-04-24', 'open_price': '24.85', 'high_price': '25.14', 'low_price': '24.71', 'close_price': '24.98', 'volume': '72540000', 'turnover_amount_billion': '36.10'},
    {'stock_code': '601138', 'trade_date': '2026-04-25', 'open_price': '25.01', 'high_price': '25.33', 'low_price': '24.95', 'close_price': '25.21', 'volume': '74810000', 'turnover_amount_billion': '37.50'},
    {'stock_code': '601138', 'trade_date': '2026-04-28', 'open_price': '25.25', 'high_price': '25.64', 'low_price': '25.11', 'close_price': '25.48', 'volume': '78130000', 'turnover_amount_billion': '39.80'},
    {'stock_code': '601138', 'trade_date': '2026-04-29', 'open_price': '25.56', 'high_price': '25.92', 'low_price': '25.41', 'close_price': '25.56', 'volume': '76280000', 'turnover_amount_billion': '38.70'},
    {'stock_code': '601138', 'trade_date': '2026-04-30', 'open_price': '25.61', 'high_price': '26.28', 'low_price': '25.48', 'close_price': '26.17', 'volume': '80550000', 'turnover_amount_billion': '45.20'},
]

HOT_SECTORS_PAYLOAD = {
    'trade_date': '2026-04-30',
    'items': [
        {'name': '算力', 'trend_label': '持续 3 日', 'heat_score': 93},
        {'name': '机器人', 'trend_label': '持续 2 日', 'heat_score': 88},
        {'name': '军工', 'trend_label': '新晋热点', 'heat_score': 74},
    ],
}


def _write_csv(file_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with file_path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _prepare_batch_dir(batch_dir: Path) -> None:
    batch_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(batch_dir / 'stock_pool.csv', ['stock_code', 'stock_name', 'sectors', 'ai_quick_summary'], STOCK_POOL_ROWS)
    _write_csv(
        batch_dir / 'daily_stock_snapshots.csv',
        ['trade_date', 'stock_code', 'current_price', 'change_amount', 'change_pct', 'turnover_amount_billion', 'turnover_rate'],
        DAILY_SNAPSHOT_ROWS,
    )
    _write_csv(
        batch_dir / 'daily_bars.csv',
        ['stock_code', 'trade_date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume', 'turnover_amount_billion'],
        DAILY_BAR_ROWS,
    )
    (batch_dir / 'hot_sectors.json').write_text(json.dumps(HOT_SECTORS_PAYLOAD, ensure_ascii=False, indent=2), encoding='utf-8')


def test_import_market_data_batch_populates_local_store(tmp_path: Path) -> None:
    batch_dir = tmp_path / 'batch'
    sqlite_path = tmp_path / 'sqlite' / 'alphapredator.db'
    duckdb_path = tmp_path / 'duckdb' / 'alphapredator.duckdb'
    daily_bars_parquet_path = tmp_path / 'parquet' / 'stock_daily_bars.parquet'
    market_snapshot_path = tmp_path / 'parquet' / 'market_snapshot.json'
    _prepare_batch_dir(batch_dir)

    result = import_market_data_batch(
        batch_dir,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
        daily_bars_parquet_path=daily_bars_parquet_path,
        market_snapshot_path=market_snapshot_path,
    )

    assert result.stock_count == 3
    assert result.snapshot_row_count == 3
    assert result.daily_bar_count == 15
    assert result.hot_sector_count == 3
    assert result.latest_trade_date == '2026-04-30'
    assert sqlite_path.exists()
    assert duckdb_path.exists()
    assert daily_bars_parquet_path.exists()
    assert market_snapshot_path.exists()

    service = MarketDataService(
        snapshot_path=market_snapshot_path,
        daily_bars_parquet_path=daily_bars_parquet_path,
        sqlite_path=sqlite_path,
        duckdb_path=duckdb_path,
    )

    overview = service.get_market_overview()
    assert overview.summary.trade_date == '2026-04-30'
    assert overview.summary.rising_count == 3
    assert overview.summary.falling_count == 0
    assert round(overview.summary.turnover_amount_billion, 2) == 159.3
    assert [stock.stock_code for stock in overview.stocks] == ['300308', '601138', '000001']
    assert [sector.name for sector in overview.hot_sectors] == ['算力', '机器人', '军工']

    detail = service.get_stock_detail('300308')
    assert detail.trade_date == '2026-04-30'
    assert detail.stock_name == '中际旭创'
    assert detail.sectors == ['AI 算力', 'CPO']
    assert detail.key_indicators.ma5 == 163.51
    assert detail.key_indicators.ma10 is None
    assert detail.key_indicators.ma20 is None
    assert detail.key_indicators.avg_volume_5d == 20478000
    assert len(detail.daily_bars) == 5
    assert detail.daily_bars[-1].close_price == 167.53
    # Verify turnover_amount_billion is populated from daily_bars
    assert detail.daily_bars[-1].turnover_amount_billion == 82.40
