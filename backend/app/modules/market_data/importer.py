import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.db.duckdb import connect_duckdb, ensure_duckdb_parent, ensure_duckdb_schema
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema


@dataclass(frozen=True)
class ImportResult:
    stock_count: int
    snapshot_row_count: int
    daily_bar_count: int
    hot_sector_count: int
    latest_trade_date: str


REQUIRED_STOCK_POOL_FIELDS = {'stock_code', 'stock_name', 'sectors', 'ai_quick_summary'}
REQUIRED_DAILY_SNAPSHOT_FIELDS = {
    'trade_date',
    'stock_code',
    'current_price',
    'change_amount',
    'change_pct',
    'turnover_amount_billion',
    'turnover_rate',
}
REQUIRED_DAILY_BAR_FIELDS = {
    'stock_code',
    'trade_date',
    'open_price',
    'high_price',
    'low_price',
    'close_price',
    'volume',
}


def import_market_data_batch(
    batch_dir: Path,
    *,
    sqlite_path: Path | None = None,
    duckdb_path: Path | None = None,
    daily_bars_parquet_path: Path | None = None,
    market_snapshot_path: Path | None = None,
) -> ImportResult:
    target_sqlite_path = sqlite_path or settings.sqlite_path
    target_duckdb_path = duckdb_path or settings.duckdb_path
    target_daily_bars_parquet_path = daily_bars_parquet_path or settings.daily_bars_parquet_path
    target_market_snapshot_path = market_snapshot_path or settings.market_snapshot_path
    resolved_batch_dir = batch_dir.resolve()

    stock_pool_path = resolved_batch_dir / 'stock_pool.csv'
    daily_snapshot_path = resolved_batch_dir / 'daily_stock_snapshots.csv'
    daily_bars_path = resolved_batch_dir / 'daily_bars.csv'
    hot_sectors_path = resolved_batch_dir / 'hot_sectors.json'

    stock_profiles = _read_stock_profiles(stock_pool_path)
    daily_snapshots = _read_daily_snapshots(daily_snapshot_path)
    daily_bars = _read_daily_bars(daily_bars_path)
    hot_sectors = _read_hot_sectors(hot_sectors_path)

    latest_trade_date = max((row['trade_date'] for row in daily_snapshots), default='')
    if not latest_trade_date:
        raise ValueError('daily_stock_snapshots.csv must contain at least one row')

    ensure_sqlite_schema(target_sqlite_path)
    ensure_duckdb_parent(target_duckdb_path, target_daily_bars_parquet_path.parent)
    ensure_duckdb_schema(target_duckdb_path)

    _write_sqlite_data(
        sqlite_path=target_sqlite_path,
        stock_profiles=stock_profiles,
        daily_snapshots=daily_snapshots,
        hot_sectors=hot_sectors,
    )
    _write_duckdb_data(
        duckdb_path=target_duckdb_path,
        daily_bars=daily_bars,
        daily_bars_parquet_path=target_daily_bars_parquet_path,
    )
    _write_market_snapshot(
        market_snapshot_path=target_market_snapshot_path,
        stock_profiles=stock_profiles,
        daily_snapshots=daily_snapshots,
        hot_sectors=hot_sectors,
        latest_trade_date=latest_trade_date,
    )

    return ImportResult(
        stock_count=len(stock_profiles),
        snapshot_row_count=len(daily_snapshots),
        daily_bar_count=len(daily_bars),
        hot_sector_count=len(hot_sectors),
        latest_trade_date=latest_trade_date,
    )


def _read_stock_profiles(file_path: Path) -> list[dict[str, Any]]:
    rows = _read_csv_rows(file_path, REQUIRED_STOCK_POOL_FIELDS)
    return [
        {
            'stock_code': row['stock_code'].strip(),
            'stock_name': row['stock_name'].strip(),
            'sectors': [item.strip() for item in row['sectors'].split('|') if item.strip()],
            'ai_quick_summary': row['ai_quick_summary'].strip(),
        }
        for row in rows
    ]


def _read_daily_snapshots(file_path: Path) -> list[dict[str, Any]]:
    rows = _read_csv_rows(file_path, REQUIRED_DAILY_SNAPSHOT_FIELDS)
    return [
        {
            'trade_date': row['trade_date'].strip(),
            'stock_code': row['stock_code'].strip(),
            'current_price': float(row['current_price']),
            'change_amount': float(row['change_amount']),
            'change_pct': float(row['change_pct']),
            'turnover_amount_billion': float(row['turnover_amount_billion']),
            'turnover_rate': float(row['turnover_rate']),
        }
        for row in rows
    ]


def _read_daily_bars(file_path: Path) -> list[dict[str, Any]]:
    rows = _read_csv_rows(file_path, REQUIRED_DAILY_BAR_FIELDS)
    return [
        {
            'stock_code': row['stock_code'].strip(),
            'trade_date': row['trade_date'].strip(),
            'open_price': float(row['open_price']),
            'high_price': float(row['high_price']),
            'low_price': float(row['low_price']),
            'close_price': float(row['close_price']),
            'volume': int(row['volume']),
        }
        for row in rows
    ]


def _read_hot_sectors(file_path: Path) -> list[dict[str, Any]]:
    if not file_path.exists():
        return []

    payload = json.loads(file_path.read_text(encoding='utf-8'))
    if isinstance(payload, dict):
        inherited_trade_date = str(payload.get('trade_date', '')).strip()
        items = payload.get('items', [])
    elif isinstance(payload, list):
        inherited_trade_date = ''
        items = payload
    else:
        raise ValueError('hot_sectors.json must be a JSON object or array')

    if not isinstance(items, list):
        raise ValueError('hot_sectors.json items must be a list')

    hot_sectors: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('hot_sectors.json items must be objects')
        trade_date = str(item.get('trade_date') or inherited_trade_date).strip()
        name = str(item.get('name', '')).strip()
        trend_label = str(item.get('trend_label', '')).strip()
        heat_score = item.get('heat_score')
        if not trade_date or not name or not trend_label or heat_score is None:
            raise ValueError('each hot sector item must include trade_date, name, trend_label, and heat_score')
        hot_sectors.append(
            {
                'trade_date': trade_date,
                'name': name,
                'trend_label': trend_label,
                'heat_score': int(heat_score),
            }
        )
    return hot_sectors


def _read_csv_rows(file_path: Path, required_fields: set[str]) -> list[dict[str, str]]:
    if not file_path.exists():
        raise FileNotFoundError(f'Missing required file: {file_path}')

    with file_path.open('r', encoding='utf-8', newline='') as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        missing_fields = sorted(required_fields - fieldnames)
        if missing_fields:
            raise ValueError(f'{file_path.name} is missing required columns: {", ".join(missing_fields)}')
        return [dict(row) for row in reader]


def _write_sqlite_data(
    *,
    sqlite_path: Path,
    stock_profiles: list[dict[str, Any]],
    daily_snapshots: list[dict[str, Any]],
    hot_sectors: list[dict[str, Any]],
) -> None:
    connection = connect_sqlite(sqlite_path)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('DELETE FROM focus_stock_entries')
        connection.execute('DELETE FROM hot_sector_snapshots')
        connection.execute('DELETE FROM daily_stock_snapshots')
        connection.execute('DELETE FROM stock_profiles')
        connection.executemany(
            '''
            INSERT INTO stock_profiles (stock_code, stock_name, sectors_json, ai_quick_summary)
            VALUES (?, ?, ?, ?)
            ''',
            [
                (
                    row['stock_code'],
                    row['stock_name'],
                    json.dumps(row['sectors'], ensure_ascii=False),
                    row['ai_quick_summary'],
                )
                for row in stock_profiles
            ],
        )
        connection.executemany(
            '''
            INSERT INTO daily_stock_snapshots (
                trade_date,
                stock_code,
                current_price,
                change_amount,
                change_pct,
                turnover_amount_billion,
                turnover_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (
                    row['trade_date'],
                    row['stock_code'],
                    row['current_price'],
                    row['change_amount'],
                    row['change_pct'],
                    row['turnover_amount_billion'],
                    row['turnover_rate'],
                )
                for row in daily_snapshots
            ],
        )
        if hot_sectors:
            connection.executemany(
                '''
                INSERT INTO hot_sector_snapshots (trade_date, name, trend_label, heat_score)
                VALUES (?, ?, ?, ?)
                ''',
                [
                    (
                        row['trade_date'],
                        row['name'],
                        row['trend_label'],
                        row['heat_score'],
                    )
                    for row in hot_sectors
                ],
            )
        connection.commit()
    finally:
        connection.close()


def _write_duckdb_data(*, duckdb_path: Path, daily_bars: list[dict[str, Any]], daily_bars_parquet_path: Path) -> None:
    connection = connect_duckdb(duckdb_path)
    try:
        connection.execute('DELETE FROM daily_bars')
        if daily_bars:
            connection.executemany(
                'INSERT INTO daily_bars VALUES (?, ?, ?, ?, ?, ?, ?)',
                [
                    (
                        row['stock_code'],
                        row['trade_date'],
                        row['open_price'],
                        row['high_price'],
                        row['low_price'],
                        row['close_price'],
                        row['volume'],
                    )
                    for row in daily_bars
                ],
            )
        daily_bars_parquet_path.unlink(missing_ok=True)
        parquet_path = str(daily_bars_parquet_path).replace('\\', '/').replace("'", "''")
        connection.execute(f"COPY (SELECT * FROM daily_bars ORDER BY stock_code, trade_date) TO '{parquet_path}' (FORMAT PARQUET)")
    finally:
        connection.close()


def _write_market_snapshot(
    *,
    market_snapshot_path: Path,
    stock_profiles: list[dict[str, Any]],
    daily_snapshots: list[dict[str, Any]],
    hot_sectors: list[dict[str, Any]],
    latest_trade_date: str,
) -> None:
    latest_snapshot_rows = [row for row in daily_snapshots if row['trade_date'] == latest_trade_date]
    profile_by_code = {row['stock_code']: row for row in stock_profiles}
    stock_rows = []
    for snapshot_row in latest_snapshot_rows:
        profile = profile_by_code.get(snapshot_row['stock_code'])
        if profile is None:
            continue
        stock_rows.append(
            {
                'stock_code': snapshot_row['stock_code'],
                'stock_name': profile['stock_name'],
                'current_price': snapshot_row['current_price'],
                'change_amount': snapshot_row['change_amount'],
                'change_pct': snapshot_row['change_pct'],
                'turnover_amount_billion': snapshot_row['turnover_amount_billion'],
                'turnover_rate': snapshot_row['turnover_rate'],
                'sectors': profile['sectors'],
                'ai_quick_summary': profile['ai_quick_summary'],
                'trade_date': latest_trade_date,
            }
        )

    stock_rows.sort(key=lambda row: row['turnover_amount_billion'], reverse=True)
    latest_hot_sectors = [row for row in hot_sectors if row['trade_date'] == latest_trade_date]
    latest_hot_sectors.sort(key=lambda row: row['heat_score'], reverse=True)

    payload = {
        'summary': {
            'trade_date': latest_trade_date,
            'rising_count': sum(1 for row in latest_snapshot_rows if row['change_pct'] >= 0),
            'falling_count': sum(1 for row in latest_snapshot_rows if row['change_pct'] < 0),
            'turnover_amount_billion': round(sum(row['turnover_amount_billion'] for row in latest_snapshot_rows), 2),
        },
        'hot_sectors': latest_hot_sectors,
        'stocks': stock_rows,
    }
    market_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    market_snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def main(argv: list[str] | None = None) -> int:
    arguments = argv or sys.argv[1:]
    if len(arguments) != 1:
        print('Usage: python -m app.modules.market_data.importer <batch-dir>', file=sys.stderr)
        return 1

    result = import_market_data_batch(Path(arguments[0]))
    print(
        'Imported market data batch: '
        f'stocks={result.stock_count}, '
        f'snapshots={result.snapshot_row_count}, '
        f'daily_bars={result.daily_bar_count}, '
        f'hot_sectors={result.hot_sector_count}, '
        f'latest_trade_date={result.latest_trade_date}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
