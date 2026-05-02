import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.db.duckdb import connect_duckdb
from app.db.sqlite import connect_sqlite
from app.schemas.market import (
    DailyBar,
    HotSectorItem,
    MarketListRow,
    MarketOverviewResponse,
    MarketSummary,
    StockDetailResponse,
    StockKeyIndicators,
)


class MarketDataService:
    def __init__(
        self,
        snapshot_path: Path | None = None,
        daily_bars_parquet_path: Path | None = None,
        sqlite_path: Path | None = None,
        duckdb_path: Path | None = None,
    ) -> None:
        self._snapshot_path = snapshot_path or settings.market_snapshot_path
        self._daily_bars_parquet_path = daily_bars_parquet_path or settings.daily_bars_parquet_path
        self._sqlite_path = sqlite_path or settings.sqlite_path
        self._duckdb_path = duckdb_path or settings.duckdb_path

    def get_market_overview(self) -> MarketOverviewResponse:
        payload = (
            self._load_market_overview_payload_from_sqlite()
            or self._load_market_overview_payload_from_snapshot()
            or self._sample_market_overview_payload()
        )
        return self._build_market_overview_response(payload)

    def get_stock_detail(self, stock_code: str) -> StockDetailResponse:
        payload = (
            self._load_stock_detail_payload_from_sqlite(stock_code)
            or self._load_stock_detail_payload_from_snapshot(stock_code)
            or self._sample_stock_detail_payload(stock_code)
        )
        daily_bars = self._load_stock_daily_bars(stock_code) or self._sample_daily_bars(stock_code)
        payload['daily_bars'] = daily_bars
        payload['trade_date'] = payload.get('trade_date') or (daily_bars[-1]['trade_date'] if daily_bars else '')
        payload['key_indicators'] = self._build_key_indicators(daily_bars)
        return self._build_stock_detail_response(payload)

    def _load_market_overview_payload_from_sqlite(self) -> dict[str, Any] | None:
        if not self._sqlite_path.exists():
            return None

        connection = connect_sqlite(self._sqlite_path)
        try:
            latest_trade_date_row = connection.execute(
                'SELECT MAX(trade_date) AS trade_date FROM daily_stock_snapshots'
            ).fetchone()
            latest_trade_date = str(latest_trade_date_row['trade_date'] or '').strip() if latest_trade_date_row else ''
            if not latest_trade_date:
                return None

            stock_rows = connection.execute(
                '''
                SELECT
                    snapshots.trade_date,
                    snapshots.stock_code,
                    profiles.stock_name,
                    profiles.sectors_json,
                    profiles.ai_quick_summary,
                    snapshots.current_price,
                    snapshots.change_amount,
                    snapshots.change_pct,
                    snapshots.turnover_amount_billion,
                    snapshots.turnover_rate
                FROM daily_stock_snapshots AS snapshots
                JOIN stock_profiles AS profiles
                  ON profiles.stock_code = snapshots.stock_code
                WHERE snapshots.trade_date = ?
                ORDER BY snapshots.turnover_amount_billion DESC, snapshots.stock_code ASC
                ''',
                [latest_trade_date],
            ).fetchall()
            if not stock_rows:
                return None

            hot_sector_rows = self._load_hot_sectors_from_image_pipeline(connection, latest_trade_date)
            if not hot_sector_rows:
                hot_sector_rows = connection.execute(
                    '''
                    SELECT trade_date, name, trend_label, heat_score
                    FROM hot_sector_snapshots
                    WHERE trade_date = ?
                    ORDER BY heat_score DESC, name ASC
                    ''',
                    [latest_trade_date],
                ).fetchall()
        finally:
            connection.close()

        stocks = []
        for row in stock_rows:
            stocks.append(
                {
                    'trade_date': row['trade_date'],
                    'stock_code': row['stock_code'],
                    'stock_name': row['stock_name'],
                    'current_price': row['current_price'],
                    'change_amount': row['change_amount'],
                    'change_pct': row['change_pct'],
                    'turnover_amount_billion': row['turnover_amount_billion'],
                    'turnover_rate': row['turnover_rate'],
                    'sectors': self._parse_sectors_json(row['sectors_json']),
                    'ai_quick_summary': row['ai_quick_summary'],
                }
            )

        return {
            'summary': {
                'trade_date': latest_trade_date,
                'rising_count': sum(1 for stock in stocks if stock['change_pct'] >= 0),
                'falling_count': sum(1 for stock in stocks if stock['change_pct'] < 0),
                'turnover_amount_billion': round(
                    sum(float(stock['turnover_amount_billion']) for stock in stocks),
                    2,
                ),
            },
            'hot_sectors': [dict(row) for row in hot_sector_rows],
            'stocks': stocks,
        }

    def _load_hot_sectors_from_image_pipeline(self, connection: Any, trade_date: str) -> list[dict[str, Any]]:
        preferred_trade_date_row = connection.execute(
            '''
            SELECT MAX(trade_date) AS trade_date
            FROM hot_sector_daily_aggregates
            WHERE trade_date <= ?
            ''',
            [trade_date],
        ).fetchone()
        target_trade_date = str(preferred_trade_date_row['trade_date'] or '').strip() if preferred_trade_date_row else ''
        if not target_trade_date:
            latest_trade_date_row = connection.execute(
                'SELECT MAX(trade_date) AS trade_date FROM hot_sector_daily_aggregates'
            ).fetchone()
            target_trade_date = str(latest_trade_date_row['trade_date'] or '').strip() if latest_trade_date_row else ''
        if not target_trade_date:
            return []

        rows = connection.execute(
            '''
            SELECT
                daily.trade_date,
                daily.sector_name_canonical AS name,
                daily.heat_score,
                recent.days_present_3d,
                recent.trend_tag
            FROM hot_sector_daily_aggregates AS daily
            LEFT JOIN hot_sector_recent_3d AS recent
              ON recent.trade_date = daily.trade_date
             AND recent.sector_name_canonical = daily.sector_name_canonical
            WHERE daily.trade_date = ?
            ORDER BY daily.rank_today ASC, daily.sector_name_canonical ASC
            ''',
            [target_trade_date],
        ).fetchall()
        return [
            {
                'trade_date': row['trade_date'],
                'name': row['name'],
                'trend_label': self._build_trend_label(row['trend_tag'], row['days_present_3d']),
                'heat_score': row['heat_score'],
            }
            for row in rows
        ]

    def _build_trend_label(self, trend_tag: str | None, days_present_3d: int | None) -> str:
        if trend_tag == 'persistent' and days_present_3d:
            return f'持续 {days_present_3d} 日'
        if trend_tag == 'fading':
            return '热度回落'
        return '新晋热点'

    def _load_stock_detail_payload_from_sqlite(self, stock_code: str) -> dict[str, Any] | None:
        if not self._sqlite_path.exists():
            return None

        connection = connect_sqlite(self._sqlite_path)
        try:
            row = connection.execute(
                '''
                SELECT
                    snapshots.trade_date,
                    snapshots.stock_code,
                    profiles.stock_name,
                    profiles.sectors_json,
                    profiles.ai_quick_summary,
                    snapshots.current_price,
                    snapshots.change_amount,
                    snapshots.change_pct,
                    snapshots.turnover_amount_billion,
                    snapshots.turnover_rate
                FROM daily_stock_snapshots AS snapshots
                JOIN stock_profiles AS profiles
                  ON profiles.stock_code = snapshots.stock_code
                WHERE snapshots.stock_code = ?
                ORDER BY snapshots.trade_date DESC
                LIMIT 1
                ''',
                [stock_code],
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        return {
            'trade_date': row['trade_date'],
            'stock_code': row['stock_code'],
            'stock_name': row['stock_name'],
            'current_price': row['current_price'],
            'change_amount': row['change_amount'],
            'change_pct': row['change_pct'],
            'turnover_amount_billion': row['turnover_amount_billion'],
            'turnover_rate': row['turnover_rate'],
            'sectors': self._parse_sectors_json(row['sectors_json']),
            'ai_quick_summary': row['ai_quick_summary'],
        }

    def _load_market_overview_payload_from_snapshot(self) -> dict[str, Any] | None:
        snapshot = self._load_local_snapshot()
        if snapshot is None:
            return None

        summary = snapshot.get('summary')
        hot_sectors = snapshot.get('hot_sectors')
        stocks = snapshot.get('stocks')
        if not isinstance(summary, dict) or not isinstance(hot_sectors, list) or not isinstance(stocks, list):
            return None

        trade_date = summary.get('trade_date')
        if not trade_date and stocks:
            first_stock = stocks[0]
            if isinstance(first_stock, dict):
                trade_date = first_stock.get('trade_date')

        return {
            'summary': {
                'trade_date': str(trade_date or ''),
                'rising_count': summary.get('rising_count', 0),
                'falling_count': summary.get('falling_count', 0),
                'turnover_amount_billion': summary.get('turnover_amount_billion', 0.0),
            },
            'hot_sectors': hot_sectors,
            'stocks': stocks,
        }

    def _load_stock_detail_payload_from_snapshot(self, stock_code: str) -> dict[str, Any] | None:
        snapshot = self._load_local_snapshot()
        if snapshot is None:
            return None

        stocks = snapshot.get('stocks')
        if not isinstance(stocks, list):
            return None

        for stock in stocks:
            if isinstance(stock, dict) and stock.get('stock_code') == stock_code:
                stock_payload = dict(stock)
                stock_payload.setdefault('trade_date', snapshot.get('summary', {}).get('trade_date', ''))
                return stock_payload
        return None

    def _load_local_snapshot(self) -> dict[str, Any] | None:
        if not self._snapshot_path.exists():
            return None

        try:
            with self._snapshot_path.open('r', encoding='utf-8') as file:
                payload = json.load(file)
        except (JSONDecodeError, OSError):
            return None

        return payload if isinstance(payload, dict) else None

    def _load_stock_daily_bars(self, stock_code: str) -> list[dict[str, Any]]:
        rows = self._load_stock_daily_bars_from_duckdb(stock_code)
        if rows:
            return rows
        return self._load_stock_daily_bars_from_parquet(stock_code)

    def _load_stock_daily_bars_from_duckdb(self, stock_code: str) -> list[dict[str, Any]]:
        if not self._duckdb_path.exists():
            return []

        connection = connect_duckdb(self._duckdb_path)
        try:
            rows = connection.execute(
                '''
                SELECT trade_date, open_price, high_price, low_price, close_price, volume
                FROM daily_bars
                WHERE stock_code = ?
                ORDER BY trade_date
                ''',
                [stock_code],
            ).fetchall()
        except Exception:
            return []
        finally:
            connection.close()

        return self._serialize_daily_bar_rows(rows)

    def _load_stock_daily_bars_from_parquet(self, stock_code: str) -> list[dict[str, Any]]:
        if not self._daily_bars_parquet_path.exists():
            return []

        connection = connect_duckdb(self._duckdb_path)
        parquet_path = str(self._daily_bars_parquet_path).replace('\\', '/').replace("'", "''")
        try:
            rows = connection.execute(
                f'''
                SELECT trade_date, open_price, high_price, low_price, close_price, volume
                FROM read_parquet('{parquet_path}')
                WHERE stock_code = ?
                ORDER BY trade_date
                ''',
                [stock_code],
            ).fetchall()
        finally:
            connection.close()

        return self._serialize_daily_bar_rows(rows)

    def _serialize_daily_bar_rows(self, rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
        return [
            {
                'trade_date': trade_date,
                'open_price': open_price,
                'high_price': high_price,
                'low_price': low_price,
                'close_price': close_price,
                'volume': volume,
            }
            for trade_date, open_price, high_price, low_price, close_price, volume in rows
        ]

    def _parse_sectors_json(self, sectors_json: str | None) -> list[str]:
        if not sectors_json:
            return []
        try:
            payload = json.loads(sectors_json)
        except JSONDecodeError:
            return []
        return [str(item) for item in payload] if isinstance(payload, list) else []

    def _build_key_indicators(self, daily_bars: list[dict[str, Any]]) -> dict[str, Any]:
        closes = [float(bar['close_price']) for bar in daily_bars]
        volumes = [int(bar['volume']) for bar in daily_bars]
        return {
            'ma5': self._rolling_average(closes, 5),
            'ma10': self._rolling_average(closes, 10),
            'ma20': self._rolling_average(closes, 20),
            'avg_volume_5d': self._rolling_average_int(volumes, 5),
        }

    def _rolling_average(self, values: list[float], window: int) -> float | None:
        if len(values) < window:
            return None
        return round(sum(values[-window:]) / window, 2)

    def _rolling_average_int(self, values: list[int], window: int) -> int | None:
        if len(values) < window:
            return None
        return int(round(sum(values[-window:]) / window))

    def _build_market_overview_response(self, payload: dict[str, Any]) -> MarketOverviewResponse:
        return MarketOverviewResponse(
            summary=MarketSummary(**payload['summary']),
            hot_sectors=[HotSectorItem(**sector) for sector in payload['hot_sectors']],
            stocks=[
                MarketListRow(
                    stock_code=stock['stock_code'],
                    stock_name=stock['stock_name'],
                    current_price=stock['current_price'],
                    change_amount=stock['change_amount'],
                    change_pct=stock['change_pct'],
                    turnover_amount_billion=stock['turnover_amount_billion'],
                    turnover_rate=stock['turnover_rate'],
                )
                for stock in payload['stocks']
            ],
        )

    def _build_stock_detail_response(self, payload: dict[str, Any]) -> StockDetailResponse:
        return StockDetailResponse(
            trade_date=payload['trade_date'],
            stock_code=payload['stock_code'],
            stock_name=payload['stock_name'],
            current_price=payload['current_price'],
            change_amount=payload['change_amount'],
            change_pct=payload['change_pct'],
            turnover_amount_billion=payload['turnover_amount_billion'],
            turnover_rate=payload['turnover_rate'],
            sectors=payload['sectors'],
            ai_quick_summary=payload['ai_quick_summary'],
            key_indicators=StockKeyIndicators(**payload['key_indicators']),
            daily_bars=[DailyBar(**daily_bar) for daily_bar in payload['daily_bars']],
        )

    def _sample_market_overview_payload(self) -> dict[str, Any]:
        return {
            'summary': {
                'trade_date': '2026-04-30',
                'rising_count': 3187,
                'falling_count': 1732,
                'turnover_amount_billion': 10243,
            },
            'hot_sectors': [
                {'trade_date': '2026-04-30', 'name': '机器人', 'trend_label': '持续 3 日', 'heat_score': 92},
                {'trade_date': '2026-04-30', 'name': '算力', 'trend_label': '持续 2 日', 'heat_score': 84},
                {'trade_date': '2026-04-30', 'name': '军工', 'trend_label': '新晋热点', 'heat_score': 73},
            ],
            'stocks': [
                {
                    'trade_date': '2026-04-30',
                    'stock_code': '000001',
                    'stock_name': '平安银行',
                    'current_price': 11.28,
                    'change_amount': 0.14,
                    'change_pct': 1.24,
                    'turnover_amount_billion': 31.7,
                    'turnover_rate': 0.91,
                    'sectors': ['银行'],
                    'ai_quick_summary': '波动较小，更适合作为基准观察样本。',
                },
                {
                    'trade_date': '2026-04-30',
                    'stock_code': '300308',
                    'stock_name': '中际旭创',
                    'current_price': 167.53,
                    'change_amount': 5.93,
                    'change_pct': 3.66,
                    'turnover_amount_billion': 82.4,
                    'turnover_rate': 5.24,
                    'sectors': ['AI 算力', 'CPO'],
                    'ai_quick_summary': '当前更适合观察主线延续与量能承接，不急于追高。',
                },
                {
                    'trade_date': '2026-04-30',
                    'stock_code': '601138',
                    'stock_name': '工业富联',
                    'current_price': 26.17,
                    'change_amount': 0.61,
                    'change_pct': 2.39,
                    'turnover_amount_billion': 45.2,
                    'turnover_rate': 1.74,
                    'sectors': ['算力', '服务器'],
                    'ai_quick_summary': '趋势维持偏强，但更适合等待回踩后的确认。',
                },
            ],
        }

    def _sample_stock_detail_payload(self, stock_code: str) -> dict[str, Any]:
        for stock in self._sample_market_overview_payload()['stocks']:
            if stock['stock_code'] == stock_code:
                return stock

        return {
            'trade_date': '2026-04-30',
            'stock_code': stock_code,
            'stock_name': '示例股票',
            'current_price': 0.0,
            'change_amount': 0.0,
            'change_pct': 0.0,
            'turnover_amount_billion': 0.0,
            'turnover_rate': 0.0,
            'sectors': ['待补充'],
            'ai_quick_summary': '当前暂无该股票的本地分析结论。',
        }

    def _sample_daily_bars(self, stock_code: str) -> list[dict[str, Any]]:
        sample_bars = {
            '000001': [
                {'trade_date': '2026-04-24', 'open_price': 10.92, 'high_price': 11.05, 'low_price': 10.86, 'close_price': 10.97, 'volume': 51230000},
                {'trade_date': '2026-04-25', 'open_price': 10.98, 'high_price': 11.08, 'low_price': 10.91, 'close_price': 11.02, 'volume': 49820000},
                {'trade_date': '2026-04-28', 'open_price': 11.03, 'high_price': 11.13, 'low_price': 10.95, 'close_price': 11.08, 'volume': 53410000},
                {'trade_date': '2026-04-29', 'open_price': 11.06, 'high_price': 11.16, 'low_price': 11.01, 'close_price': 11.12, 'volume': 47650000},
                {'trade_date': '2026-04-30', 'open_price': 11.13, 'high_price': 11.31, 'low_price': 11.08, 'close_price': 11.28, 'volume': 56340000},
            ],
            '300308': [
                {'trade_date': '2026-04-24', 'open_price': 157.6, 'high_price': 160.2, 'low_price': 156.8, 'close_price': 159.4, 'volume': 18320000},
                {'trade_date': '2026-04-25', 'open_price': 159.8, 'high_price': 162.6, 'low_price': 158.9, 'close_price': 161.7, 'volume': 19180000},
                {'trade_date': '2026-04-28', 'open_price': 162.1, 'high_price': 164.3, 'low_price': 160.7, 'close_price': 163.5, 'volume': 20540000},
                {'trade_date': '2026-04-29', 'open_price': 163.8, 'high_price': 166.1, 'low_price': 162.9, 'close_price': 165.4, 'volume': 21490000},
                {'trade_date': '2026-04-30', 'open_price': 165.9, 'high_price': 168.4, 'low_price': 164.7, 'close_price': 167.53, 'volume': 22860000},
            ],
            '601138': [
                {'trade_date': '2026-04-24', 'open_price': 24.85, 'high_price': 25.14, 'low_price': 24.71, 'close_price': 24.98, 'volume': 72540000},
                {'trade_date': '2026-04-25', 'open_price': 25.01, 'high_price': 25.33, 'low_price': 24.95, 'close_price': 25.21, 'volume': 74810000},
                {'trade_date': '2026-04-28', 'open_price': 25.25, 'high_price': 25.64, 'low_price': 25.11, 'close_price': 25.48, 'volume': 78130000},
                {'trade_date': '2026-04-29', 'open_price': 25.56, 'high_price': 25.92, 'low_price': 25.41, 'close_price': 25.56, 'volume': 76280000},
                {'trade_date': '2026-04-30', 'open_price': 25.61, 'high_price': 26.28, 'low_price': 25.48, 'close_price': 26.17, 'volume': 80550000},
            ],
        }
        return sample_bars.get(stock_code, [])


market_data_service = MarketDataService()
