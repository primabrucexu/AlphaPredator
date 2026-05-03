import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.db.duckdb_storage import connect_duckdb
from app.db.sqlite import connect_sqlite
from app.schemas.market import (
    DailyBar,
    HotSectorItem,
    MarketListRow,
    MarketOverviewResponse,
    MarketSummary,
    StockCandidate,
    StockDetailResponse,
    StockIndicatorSeries,
    StockKeyIndicators,
    StockResolveResponse,
    StockTags,
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
        # Enrich daily bars with per-day turnover data from SQLite snapshots
        daily_bars = self._enrich_daily_bars_with_turnover(stock_code, daily_bars)
        payload['daily_bars'] = daily_bars
        payload['trade_date'] = payload.get('trade_date') or (daily_bars[-1]['trade_date'] if daily_bars else '')
        payload['key_indicators'] = self._build_key_indicators(daily_bars)
        # Derive open/high/low/prev_close from latest daily bar
        if daily_bars:
            latest = daily_bars[-1]
            payload['open_price'] = float(latest['open_price'])
            payload['high_price'] = float(latest['high_price'])
            payload['low_price'] = float(latest['low_price'])
        else:
            payload.setdefault('open_price', 0.0)
            payload.setdefault('high_price', 0.0)
            payload.setdefault('low_price', 0.0)
        payload['prev_close'] = round(float(payload['current_price']) - float(payload['change_amount']), 2)
        # Build structured tags (sectors → industry; no concept/region data yet)
        payload['tags'] = {'industry': list(payload.get('sectors', [])), 'concepts': [], 'region': []}
        # Compute indicator series
        payload['indicators'] = self._build_indicator_series(daily_bars)
        return self._build_stock_detail_response(payload)

    def resolve_stock(self, query: str) -> StockResolveResponse:
        """
        Resolve a user query (stock code or pinyin abbreviation) to a unique stock.

        Match priority:
          1. Exact ts_code match (e.g. '000001.SZ')
          2. Exact 6-digit symbol match (e.g. '000001')
          3. Exact cnspell match (case-insensitive)
          4. cnspell prefix match (case-insensitive)

        Returns:
          status='ok' with stock_code/stock_name/match_type on unique match.
          status='not_found' when no match.
          status='ambiguous' with candidates list when multiple matches.
        """
        q = query.strip().upper()
        if not q:
            return StockResolveResponse(status='not_found', message='请输入股票代码或拼音简称')

        if not self._sqlite_path.exists():
            return StockResolveResponse(status='not_found', message='股票清单尚未初始化，请先上传股票清单')

        conn = connect_sqlite(self._sqlite_path)
        try:
            # 1. Exact ts_code match (e.g. '000001.SZ')
            row = conn.execute(
                "SELECT ts_code, name FROM stock_universe WHERE UPPER(ts_code) = ? AND list_status = 'L' LIMIT 1",
                [q],
            ).fetchone()
            if row:
                # ts_code like '000001.SZ' → symbol = first 6 digits
                symbol = str(row['ts_code']).split('.')[0]
                if not self._has_local_market_data(conn, symbol):
                    return StockResolveResponse(
                        status='not_found',
                        message=f'已匹配股票 {symbol} {row["name"]}，但本地暂无行情数据，请先执行重新初始化市场数据。',
                    )
                return StockResolveResponse(
                    status='ok',
                    stock_code=symbol,
                    stock_name=str(row['name']),
                    match_type='code',
                )

            # 2. Exact 6-digit symbol match (e.g. '000001')
            rows = conn.execute(
                "SELECT ts_code, name FROM stock_universe WHERE symbol = ? AND list_status = 'L'",
                [q.zfill(6)],
            ).fetchall()
            raw_rows = rows
            rows = [r for r in raw_rows if self._has_local_market_data(conn, str(r['ts_code']).split('.')[0])]
            if raw_rows and not rows:
                first_symbol = str(raw_rows[0]['ts_code']).split('.')[0]
                return StockResolveResponse(
                    status='not_found',
                    message=f'已匹配股票 {first_symbol} {raw_rows[0]["name"]}，但本地暂无行情数据，请先执行重新初始化市场数据。',
                )
            if len(rows) == 1:
                symbol = str(rows[0]['ts_code']).split('.')[0]
                return StockResolveResponse(
                    status='ok',
                    stock_code=symbol,
                    stock_name=str(rows[0]['name']),
                    match_type='code',
                )
            if len(rows) > 1:
                return StockResolveResponse(
                    status='ambiguous',
                    message='匹配到多只股票，请输入更完整代码/简称',
                    candidates=[
                        StockCandidate(stock_code=str(r['ts_code']).split('.')[0], stock_name=str(r['name']))
                        for r in rows
                    ],
                )

            # 3. Exact cnspell match
            rows = conn.execute(
                "SELECT ts_code, name FROM stock_universe WHERE cnspell = ? AND list_status = 'L'",
                [q],
            ).fetchall()
            raw_rows = rows
            rows = [r for r in raw_rows if self._has_local_market_data(conn, str(r['ts_code']).split('.')[0])]
            if raw_rows and not rows:
                return StockResolveResponse(
                    status='not_found',
                    message='已匹配到股票清单，但本地暂无对应行情数据，请先执行重新初始化市场数据。',
                )
            if len(rows) == 1:
                symbol = str(rows[0]['ts_code']).split('.')[0]
                return StockResolveResponse(
                    status='ok',
                    stock_code=symbol,
                    stock_name=str(rows[0]['name']),
                    match_type='cnspell',
                )
            if len(rows) > 1:
                return StockResolveResponse(
                    status='ambiguous',
                    message='匹配到多只股票，请输入更完整代码/简称',
                    candidates=[
                        StockCandidate(stock_code=str(r['ts_code']).split('.')[0], stock_name=str(r['name']))
                        for r in rows
                    ],
                )

            # 4. cnspell prefix match
            rows = conn.execute(
                "SELECT ts_code, name FROM stock_universe WHERE cnspell LIKE ? AND list_status = 'L' LIMIT 20",
                [q + '%'],
            ).fetchall()
            raw_rows = rows
            rows = [r for r in raw_rows if self._has_local_market_data(conn, str(r['ts_code']).split('.')[0])]
            if raw_rows and not rows:
                return StockResolveResponse(
                    status='not_found',
                    message='已匹配到股票清单，但本地暂无对应行情数据，请先执行重新初始化市场数据。',
                )
            if len(rows) == 1:
                symbol = str(rows[0]['ts_code']).split('.')[0]
                return StockResolveResponse(
                    status='ok',
                    stock_code=symbol,
                    stock_name=str(rows[0]['name']),
                    match_type='cnspell_prefix',
                )
            if len(rows) > 1:
                return StockResolveResponse(
                    status='ambiguous',
                    message='匹配到多只股票，请输入更完整代码/简称',
                    candidates=[
                        StockCandidate(stock_code=str(r['ts_code']).split('.')[0], stock_name=str(r['name']))
                        for r in rows
                    ],
                )

        finally:
            conn.close()

        return StockResolveResponse(status='not_found', message='未找到匹配股票')

    def _has_local_market_data(self, sqlite_conn: Any, stock_code: str) -> bool:
        """Return True when local snapshot or bar data exists for the stock."""
        row = sqlite_conn.execute(
            'SELECT 1 FROM daily_stock_snapshots WHERE stock_code = ? LIMIT 1',
            [stock_code],
        ).fetchone()
        if row:
            return True

        # Snapshot may be missing on partial imports; fallback to bar existence.
        return self._has_stock_daily_bars(stock_code)

    def _has_stock_daily_bars(self, stock_code: str) -> bool:
        if self._duckdb_path.exists():
            connection = connect_duckdb(self._duckdb_path)
            try:
                row = connection.execute(
                    'SELECT 1 FROM daily_bars WHERE stock_code = ? LIMIT 1',
                    [stock_code],
                ).fetchone()
                if row:
                    return True
            except Exception:
                pass
            finally:
                connection.close()

        if self._daily_bars_parquet_path.exists():
            connection = connect_duckdb(self._duckdb_path)
            parquet_path = str(self._daily_bars_parquet_path).replace('\\', '/').replace("'", "''")
            try:
                row = connection.execute(
                    f"SELECT 1 FROM read_parquet('{parquet_path}') WHERE stock_code = ? LIMIT 1",
                    [stock_code],
                ).fetchone()
                if row:
                    return True
            except Exception:
                return False
            finally:
                connection.close()

        return False

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

    def _enrich_daily_bars_with_turnover(
        self, stock_code: str, daily_bars: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Join daily bars with per-day turnover data from SQLite daily_stock_snapshots."""
        if not daily_bars or not self._sqlite_path.exists():
            return daily_bars

        connection = connect_sqlite(self._sqlite_path)
        try:
            rows = connection.execute(
                '''
                SELECT trade_date, turnover_amount_billion, turnover_rate
                FROM daily_stock_snapshots
                WHERE stock_code = ?
                ORDER BY trade_date
                ''',
                [stock_code],
            ).fetchall()
        finally:
            connection.close()

        if not rows:
            return daily_bars

        turnover_map: dict[str, dict[str, float]] = {
            row['trade_date']: {
                'turnover_amount_billion': float(row['turnover_amount_billion']),
                'turnover_rate': float(row['turnover_rate']),
            }
            for row in rows
        }

        enriched = []
        for bar in daily_bars:
            bar = dict(bar)
            td = bar.get('trade_date', '')
            if td in turnover_map:
                bar['turnover_amount_billion'] = turnover_map[td]['turnover_amount_billion']
                bar['turnover_rate'] = turnover_map[td]['turnover_rate']
            enriched.append(bar)
        return enriched

    def _load_stock_daily_bars_from_duckdb(self, stock_code: str) -> list[dict[str, Any]]:
        if not self._duckdb_path.exists():
            return []

        connection = connect_duckdb(self._duckdb_path)
        try:
            rows = connection.execute(
                '''
                SELECT trade_date, open_price, high_price, low_price, close_price, volume,
                       turnover_amount_billion
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
                SELECT trade_date, open_price, high_price, low_price, close_price, volume,
                       COALESCE(turnover_amount_billion, 0.0) AS turnover_amount_billion
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
                'turnover_amount_billion': float(turnover_amount_billion or 0.0),
            }
            for trade_date, open_price, high_price, low_price, close_price, volume, turnover_amount_billion in rows
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

    # ------------------------------------------------------------------
    # Indicator series computation
    # ------------------------------------------------------------------

    def _compute_ma_series(self, values: list[float], window: int) -> list[float | None]:
        n = len(values)
        result: list[float | None] = [None] * n
        for i in range(window - 1, n):
            result[i] = round(sum(values[i - window + 1 : i + 1]) / window, 2)
        return result

    def _compute_ema_series(self, values: list[float], span: int) -> list[float]:
        """Exponential moving average with alpha = 2/(span+1), seeded with first value."""
        alpha = 2.0 / (span + 1)
        result = [0.0] * len(values)
        if not values:
            return result
        result[0] = values[0]
        for i in range(1, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
        return result

    def _compute_kdj_series(
        self,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        n: int = 9,
    ) -> tuple[list[float | None], list[float | None], list[float | None]]:
        """KDJ using Wilder's smoothing (1/3 factor).  Seeds K=D=50."""
        N = len(closes)
        k_vals: list[float | None] = [None] * N
        d_vals: list[float | None] = [None] * N
        j_vals: list[float | None] = [None] * N
        prev_k, prev_d = 50.0, 50.0
        for i in range(n - 1, N):
            h_n = max(highs[i - n + 1 : i + 1])
            l_n = min(lows[i - n + 1 : i + 1])
            rsv = (closes[i] - l_n) / (h_n - l_n) * 100 if h_n != l_n else 50.0
            k = prev_k * 2 / 3 + rsv / 3
            d = prev_d * 2 / 3 + k / 3
            j = 3 * k - 2 * d
            k_vals[i] = round(k, 2)
            d_vals[i] = round(d, 2)
            j_vals[i] = round(j, 2)
            prev_k, prev_d = k, d
        return k_vals, d_vals, j_vals

    def _compute_macd_series(
        self, closes: list[float]
    ) -> tuple[list[float | None], list[float | None], list[float | None]]:
        """MACD(12,26,9). EMA seeded from first close."""
        N = len(closes)
        dif_vals: list[float | None] = [None] * N
        dea_vals: list[float | None] = [None] * N
        hist_vals: list[float | None] = [None] * N
        if N == 0:
            return dif_vals, dea_vals, hist_vals
        ema12 = self._compute_ema_series(closes, 12)
        ema26 = self._compute_ema_series(closes, 26)
        dif_raw = [ema12[i] - ema26[i] for i in range(N)]
        dea_raw = self._compute_ema_series(dif_raw, 9)
        for i in range(N):
            dif_vals[i] = round(dif_raw[i], 4)
            dea_vals[i] = round(dea_raw[i], 4)
            hist_vals[i] = round((dif_raw[i] - dea_raw[i]) * 2, 4)
        return dif_vals, dea_vals, hist_vals

    def _compute_rsi_series(self, closes: list[float], n: int) -> list[float | None]:
        """RSI with Wilder's smoothing.  First valid value at index n."""
        N = len(closes)
        result: list[float | None] = [None] * N
        if N < n + 1:
            return result
        changes = [closes[i] - closes[i - 1] for i in range(1, N)]
        gains = [max(c, 0.0) for c in changes]
        losses = [max(-c, 0.0) for c in changes]
        avg_gain = sum(gains[:n]) / n
        avg_loss = sum(losses[:n]) / n

        def _rsi(gain: float, loss: float) -> float:
            if loss == 0:
                return 100.0
            return round(100 - 100 / (1 + gain / loss), 2)

        result[n] = _rsi(avg_gain, avg_loss)
        for i in range(n + 1, N):
            avg_gain = (avg_gain * (n - 1) + gains[i - 1]) / n
            avg_loss = (avg_loss * (n - 1) + losses[i - 1]) / n
            result[i] = _rsi(avg_gain, avg_loss)
        return result

    def _build_indicator_series(self, daily_bars: list[dict[str, Any]]) -> dict[str, Any]:
        if not daily_bars:
            empty: list[None] = []
            return {
                'ma5': empty, 'ma10': empty, 'ma20': empty, 'ma60': empty,
                'volume_ma5': empty, 'volume_ma10': empty, 'volume_ma20': empty,
                'kdj_k': empty, 'kdj_d': empty, 'kdj_j': empty,
                'macd_dif': empty, 'macd_dea': empty, 'macd_hist': empty,
                'rsi6': empty, 'rsi12': empty, 'rsi24': empty,
            }
        closes = [float(b['close_price']) for b in daily_bars]
        highs = [float(b['high_price']) for b in daily_bars]
        lows = [float(b['low_price']) for b in daily_bars]
        volumes = [float(b['volume']) for b in daily_bars]
        k_vals, d_vals, j_vals = self._compute_kdj_series(highs, lows, closes)
        dif_vals, dea_vals, hist_vals = self._compute_macd_series(closes)
        return {
            'ma5': self._compute_ma_series(closes, 5),
            'ma10': self._compute_ma_series(closes, 10),
            'ma20': self._compute_ma_series(closes, 20),
            'ma60': self._compute_ma_series(closes, 60),
            'volume_ma5': self._compute_ma_series(volumes, 5),
            'volume_ma10': self._compute_ma_series(volumes, 10),
            'volume_ma20': self._compute_ma_series(volumes, 20),
            'kdj_k': k_vals,
            'kdj_d': d_vals,
            'kdj_j': j_vals,
            'macd_dif': dif_vals,
            'macd_dea': dea_vals,
            'macd_hist': hist_vals,
            'rsi6': self._compute_rsi_series(closes, 6),
            'rsi12': self._compute_rsi_series(closes, 12),
            'rsi24': self._compute_rsi_series(closes, 24),
        }

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
            open_price=payload.get('open_price', 0.0),
            prev_close=payload.get('prev_close', 0.0),
            high_price=payload.get('high_price', 0.0),
            low_price=payload.get('low_price', 0.0),
            turnover_amount_billion=payload['turnover_amount_billion'],
            turnover_rate=payload['turnover_rate'],
            sectors=payload['sectors'],
            tags=StockTags(**payload.get('tags', {})),
            ai_quick_summary=payload['ai_quick_summary'],
            key_indicators=StockKeyIndicators(**payload['key_indicators']),
            daily_bars=[DailyBar(**daily_bar) for daily_bar in payload['daily_bars']],
            indicators=StockIndicatorSeries(**payload.get('indicators', {})),
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
        # Sample turnover values are illustrative approximations proportional to volume.
        sample_bars = {
            '000001': [
                {'trade_date': '2026-04-24', 'open_price': 10.92, 'high_price': 11.05, 'low_price': 10.86, 'close_price': 10.97, 'volume': 51230000, 'turnover_amount_billion': 5.64, 'turnover_rate': 0.29},
                {'trade_date': '2026-04-25', 'open_price': 10.98, 'high_price': 11.08, 'low_price': 10.91, 'close_price': 11.02, 'volume': 49820000, 'turnover_amount_billion': 5.49, 'turnover_rate': 0.28},
                {'trade_date': '2026-04-28', 'open_price': 11.03, 'high_price': 11.13, 'low_price': 10.95, 'close_price': 11.08, 'volume': 53410000, 'turnover_amount_billion': 5.93, 'turnover_rate': 0.30},
                {'trade_date': '2026-04-29', 'open_price': 11.06, 'high_price': 11.16, 'low_price': 11.01, 'close_price': 11.12, 'volume': 47650000, 'turnover_amount_billion': 5.30, 'turnover_rate': 0.27},
                {'trade_date': '2026-04-30', 'open_price': 11.13, 'high_price': 11.31, 'low_price': 11.08, 'close_price': 11.28, 'volume': 56340000, 'turnover_amount_billion': 6.23, 'turnover_rate': 0.32},
            ],
            '300308': [
                {'trade_date': '2026-04-24', 'open_price': 157.6, 'high_price': 160.2, 'low_price': 156.8, 'close_price': 159.4, 'volume': 18320000, 'turnover_amount_billion': 29.15, 'turnover_rate': 1.84},
                {'trade_date': '2026-04-25', 'open_price': 159.8, 'high_price': 162.6, 'low_price': 158.9, 'close_price': 161.7, 'volume': 19180000, 'turnover_amount_billion': 31.01, 'turnover_rate': 1.93},
                {'trade_date': '2026-04-28', 'open_price': 162.1, 'high_price': 164.3, 'low_price': 160.7, 'close_price': 163.5, 'volume': 20540000, 'turnover_amount_billion': 33.56, 'turnover_rate': 2.07},
                {'trade_date': '2026-04-29', 'open_price': 163.8, 'high_price': 166.1, 'low_price': 162.9, 'close_price': 165.4, 'volume': 21490000, 'turnover_amount_billion': 35.53, 'turnover_rate': 2.17},
                {'trade_date': '2026-04-30', 'open_price': 165.9, 'high_price': 168.4, 'low_price': 164.7, 'close_price': 167.53, 'volume': 22860000, 'turnover_amount_billion': 38.28, 'turnover_rate': 2.30},
            ],
            '601138': [
                {'trade_date': '2026-04-24', 'open_price': 24.85, 'high_price': 25.14, 'low_price': 24.71, 'close_price': 24.98, 'volume': 72540000, 'turnover_amount_billion': 18.14, 'turnover_rate': 0.73},
                {'trade_date': '2026-04-25', 'open_price': 25.01, 'high_price': 25.33, 'low_price': 24.95, 'close_price': 25.21, 'volume': 74810000, 'turnover_amount_billion': 18.87, 'turnover_rate': 0.75},
                {'trade_date': '2026-04-28', 'open_price': 25.25, 'high_price': 25.64, 'low_price': 25.11, 'close_price': 25.48, 'volume': 78130000, 'turnover_amount_billion': 19.89, 'turnover_rate': 0.79},
                {'trade_date': '2026-04-29', 'open_price': 25.56, 'high_price': 25.92, 'low_price': 25.41, 'close_price': 25.56, 'volume': 76280000, 'turnover_amount_billion': 19.50, 'turnover_rate': 0.77},
                {'trade_date': '2026-04-30', 'open_price': 25.61, 'high_price': 26.28, 'low_price': 25.48, 'close_price': 26.17, 'volume': 80550000, 'turnover_amount_billion': 21.07, 'turnover_rate': 0.84},
            ],
        }
        return sample_bars.get(stock_code, [])


market_data_service = MarketDataService()
