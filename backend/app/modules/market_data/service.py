import json
from datetime import date, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.db.duckdb_storage import connect_duckdb
from app.db.session import get_sqlite_session_factory
from app.modules.market_data.data_source import _to_full_code
from app.queries.market_queries import (
    get_hot_info_rows_by_date,
    get_hot_info_table_rows_by_date,
    get_hot_info_trade_dates,
    get_latest_hot_info_trade_date,
    get_hot_pic_rows_by_date,
    get_latest_hot_pic_trade_date,
    get_limit_up_history_by_stock,
    parse_board_count,
)
from app.repositories.market_metadata_repo import MarketMetadataRepo
from app.repositories.stock_list_repo import StockListRepo
from app.schemas.market import (
    DailyBar,
    HotSectorAggregatedItem,
    HotSectorAggregatedResponse,
    HotSectorHistoryDay,
    HotSectorHistoryResponse,
    HotSectorHistorySector,
    HotReviewImageItem,
    HotReviewImagesResponse,
    HotReviewTableResponse,
    HotReviewTableRow,
    HotSectorItem,
    LimitUpStreakItem,
    LimitUpStreaksResponse,
    MarketListRow,
    MarketOverviewResponse,
    MarketSummary,
    StockCandidate,
    StockDetailResponse,
    StockBarsRangeResponse,
    StockIndicatorSeries,
    StockKeyIndicators,
    StockLimitUpHistoryRow,
    StockLimitUpHistoryResponse,
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
        self._stock_list_repo = StockListRepo(self._sqlite_path)
        self._metadata_repo = MarketMetadataRepo(self._sqlite_path)

    def _session_factory(self):
        return get_sqlite_session_factory(self._sqlite_path)

    def get_market_overview(self) -> MarketOverviewResponse:
        payload = (
            self._load_market_overview_payload_from_duckdb()
            or self._load_market_overview_payload_from_snapshot()
            or self._sample_market_overview_payload()
        )
        return self._build_market_overview_response(payload)

    def get_stock_detail(self, stock_code: str) -> StockDetailResponse:
        payload = (
            self._load_stock_detail_payload_from_duckdb(stock_code)
            or self._load_stock_detail_payload_from_snapshot(stock_code)
            or self._sample_stock_detail_payload(stock_code)
        )
        daily_bars = self._load_stock_daily_bars_range(stock_code, months=6) or self._sample_daily_bars(stock_code)
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
        payload['has_more_before'] = self._has_more_daily_bars_before(
            stock_code,
            daily_bars[0]['trade_date'] if daily_bars else None,
        )
        return self._build_stock_detail_response(payload)

    def get_stock_bars_range(
            self,
            stock_code: str,
            months: int = 6,
            end_date: str | None = None,
    ) -> StockBarsRangeResponse:
        target_months = max(1, min(months, 120))
        daily_bars = self._load_stock_daily_bars_range(stock_code, months=target_months, end_date=end_date)
        daily_bars = self._enrich_daily_bars_with_turnover(stock_code, daily_bars)
        indicators = self._build_indicator_series(daily_bars)
        has_more_before = self._has_more_daily_bars_before(
            stock_code,
            daily_bars[0]['trade_date'] if daily_bars else None,
        )
        return StockBarsRangeResponse(
            stock_code=stock_code,
            months=target_months,
            end_date=end_date,
            has_more_before=has_more_before,
            daily_bars=[DailyBar(**daily_bar) for daily_bar in daily_bars],
            indicators=StockIndicatorSeries(**indicators),
        )

    @staticmethod
    def _is_st_stock(name: str) -> bool:
        """Return True if the stock name indicates an ST stock (contains 'ST')."""
        return 'ST' in name.upper()

    @staticmethod
    def _is_st_row(row: Any) -> bool:
        """Return True if a daily_hot_info row is ST-related.

        Checks both ``name`` (stock name) and ``hot_theme`` because many rows
        have an empty ``name`` but still belong to the 'ST板块' theme.
        """
        name = str(row['name'] or '').strip()
        hot_theme = str(row['hot_theme'] or '').strip()
        return 'ST' in name.upper() or 'ST' in hot_theme.upper()

    def get_hot_sector_history(self, days: int = 7, exclude_st: bool = True) -> HotSectorHistoryResponse:
        if not self._sqlite_path.exists():
            return HotSectorHistoryResponse()

        target_days = max(1, min(days, 60))
        session_factory = self._session_factory()
        with session_factory() as session:
            trade_dates = get_hot_info_trade_dates(session, target_days)
            if not trade_dates:
                return HotSectorHistoryResponse()

            days_payload: list[HotSectorHistoryDay] = []
            for trade_date in trade_dates:
                rows = get_hot_info_rows_by_date(session, trade_date)
                sectors = self._build_hot_sector_history_sectors(rows, exclude_st=exclude_st)
                days_payload.append(HotSectorHistoryDay(trade_date=trade_date, sectors=sectors))

        return HotSectorHistoryResponse(trade_dates=trade_dates, days=days_payload)

    def get_limit_up_streaks(
        self,
        trade_date: str | None = None,
        min_boards: int = 2,
        exclude_st: bool = True,
    ) -> LimitUpStreaksResponse:
        if not self._sqlite_path.exists():
            return LimitUpStreaksResponse(trade_date=trade_date or '', streaks=[])

        target_min_boards = max(1, min(min_boards, 20))
        session_factory = self._session_factory()
        with session_factory() as session:
            target_trade_date = trade_date
            if not target_trade_date:
                target_trade_date = get_latest_hot_info_trade_date(session)

            if not target_trade_date:
                return LimitUpStreaksResponse(trade_date='', streaks=[])

            rows = get_hot_info_rows_by_date(session, target_trade_date)
            streak_rows: list[dict[str, Any]] = []
            for row in rows:
                stock_name = str(row['name'] or '')
                if exclude_st and self._is_st_row(row):
                    continue
                board_count = parse_board_count(str(row['streak_text'] or ''))
                if board_count < target_min_boards:
                    continue
                stock_code = str(row['stock_code'] or '').strip()
                if stock_code.isdigit():
                    stock_code = stock_code.zfill(6)
                streak_rows.append(
                    {
                        'trade_date': str(row['trade_date']),
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'board_count': board_count,
                        'limit_up_time': str(row['limit_up_time'] or ''),
                        'hot_theme': str(row['hot_theme'] or ''),
                    }
                )
            streak_rows.sort(key=lambda item: (-item['board_count'], item['limit_up_time'], item['stock_code']))

            streaks = [LimitUpStreakItem(**row) for row in streak_rows]

        return LimitUpStreaksResponse(trade_date=target_trade_date, streaks=streaks)

    def get_hot_review_images(self, trade_date: str | None = None) -> HotReviewImagesResponse:
        if not self._sqlite_path.exists():
            return HotReviewImagesResponse(trade_date=trade_date or '', images=[])

        session_factory = self._session_factory()
        with session_factory() as session:
            target_trade_date = trade_date
            if not target_trade_date:
                target_trade_date = get_latest_hot_pic_trade_date(session)

            if not target_trade_date:
                return HotReviewImagesResponse(trade_date='', images=[])

            rows = get_hot_pic_rows_by_date(session, target_trade_date)
            images = [
                HotReviewImageItem(
                    url=str(row['summary_image_url'] or ''),
                    source_file=str(row['source'] or ''),
                )
                for row in rows
                if str(row['summary_image_url'] or '').strip()
            ]

        return HotReviewImagesResponse(trade_date=target_trade_date, images=images)

    def get_hot_review_table(self, trade_date: str | None = None, exclude_st: bool = True) -> HotReviewTableResponse:
        if not self._sqlite_path.exists():
            return HotReviewTableResponse(trade_date=trade_date or '', rows=[])

        session_factory = self._session_factory()
        with session_factory() as session:
            target_trade_date = trade_date or get_latest_hot_info_trade_date(session)
            if not target_trade_date:
                return HotReviewTableResponse(trade_date='', rows=[])

            db_rows = get_hot_info_table_rows_by_date(session, target_trade_date)
            table_rows: list[HotReviewTableRow] = []
            for row in db_rows:
                stock_name = str(row['name'] or '').strip()
                if exclude_st and self._is_st_row(row):
                    continue
                stock_code = str(row['stock_code'] or '').strip()
                if stock_code.isdigit():
                    stock_code = stock_code.zfill(6)
                table_rows.append(
                    HotReviewTableRow(
                        trade_date=str(row['trade_date'] or ''),
                        stock_code=stock_code,
                        stock_name=stock_name,
                        limit_up_time=str(row['limit_up_time'] or ''),
                        streak_text=str(row['streak_text'] or ''),
                        hot_theme=str(row['hot_theme'] or ''),
                        reason=str(row['reason'] or ''),
                        short_reason=str(row['short_reason'] or ''),
                    )
                )

        return HotReviewTableResponse(trade_date=target_trade_date, rows=table_rows)

    def get_stock_limit_up_history(
        self,
        stock_code: str,
        limit: int = 20,
    ) -> StockLimitUpHistoryResponse:
        """Return recent limit-up records for a specific stock from daily_hot_info."""
        if not self._sqlite_path.exists():
            return StockLimitUpHistoryResponse(stock_code=stock_code, rows=[])

        # Normalize stock_code to 6-digit string
        normalized_code = str(stock_code or '').strip()
        if normalized_code.isdigit():
            normalized_code = normalized_code.zfill(6)

        session_factory = self._session_factory()
        with session_factory() as session:
            db_rows = get_limit_up_history_by_stock(session, normalized_code, limit=limit)
            rows: list[StockLimitUpHistoryRow] = []
            for row in db_rows:
                rows.append(
                    StockLimitUpHistoryRow(
                        trade_date=str(row['trade_date'] or ''),
                        limit_up_time=str(row['limit_up_time'] or ''),
                        streak_text=str(row['streak_text'] or ''),
                        hot_theme=str(row['hot_theme'] or ''),
                        reason=str(row['reason'] or ''),
                        short_reason=str(row['short_reason'] or ''),
                    )
                )

        return StockLimitUpHistoryResponse(stock_code=normalized_code, rows=rows)

    def get_hot_sector_aggregated(
        exclude_st: bool = True,
    ) -> HotSectorAggregatedResponse:
        """返回多个时间窗口内各板块去重涨停家数。

        同一只股票在同一个窗口内只统计一次。
        ``windows`` 默认 [5, 10, 20]，单位为交易日。
        """
        if windows is None:
            windows = [5, 10, 20]

        if not self._sqlite_path.exists():
            return HotSectorAggregatedResponse(windows=windows, sectors=[])

        max_days = max(windows)
        session_factory = self._session_factory()
        with session_factory() as session:
            # 获取最近 max_days 个交易日（有数据的）
            trade_dates = get_hot_info_trade_dates(session, max_days)
            if not trade_dates:
                return HotSectorAggregatedResponse(windows=windows, sectors=[])

            # 按日期顺序（升序）收集每天数据
            # sector_stocks_by_date[trade_date][sector] = {stock_code, ...}
            dated_rows: list[tuple[str, str, str]] = []  # (trade_date, sector, stock_code)
            for trade_date in trade_dates:
                rows = get_hot_info_rows_by_date(session, trade_date)
                for row in rows:
                    if exclude_st and self._is_st_row(row):
                        continue
                    stock_code = str(row['stock_code'] or '').strip()
                    if not stock_code:
                        continue
                    hot_theme = str(row['hot_theme'] or '').strip()
                    if not hot_theme:
                        continue
                    # 拆分多板块（如 "AI芯片、创新药"）
                    for sector in hot_theme.split('、'):
                        sector = sector.strip()
                        if sector:
                            dated_rows.append((trade_date, sector, stock_code))

        # 按各窗口聚合去重
        # trade_dates 已是升序，取最后 W 个日期作为窗口
        result_map: dict[str, dict[str, set[str]]] = {}  # sector → {window_str → set<stock_code>}
        for w in windows:
            window_dates = set(trade_dates[-w:]) if len(trade_dates) >= w else set(trade_dates)
            w_str = str(w)
            for trade_date, sector, stock_code in dated_rows:
                if trade_date not in window_dates:
                    continue
                if sector not in result_map:
                    result_map[sector] = {}
                if w_str not in result_map[sector]:
                    result_map[sector][w_str] = set()
                result_map[sector][w_str].add(stock_code)

        # 按最大窗口去重数降序排列
        max_w_str = str(max(windows))
        sectors_sorted = sorted(
            result_map.items(),
            key=lambda kv: -len(kv[1].get(max_w_str, set())),
        )

        sectors = [
            HotSectorAggregatedItem(
                name=sector,
                counts={w_str: len(stocks) for w_str, stocks in counts.items()},
            )
            for sector, counts in sectors_sorted
        ]
        return HotSectorAggregatedResponse(windows=windows, sectors=sectors)

    def _build_hot_sector_history_sectors(self, rows: list[Any], exclude_st: bool = True) -> list[HotSectorHistorySector]:
        stats: dict[str, dict[str, int]] = {}
        for row in rows:
            if exclude_st and self._is_st_row(row):
                continue
            sector_name = str(row['hot_theme'] or '').strip()
            if not sector_name:
                continue
            item = stats.setdefault(sector_name, {'heat_score': 0, 'max_board_count': 0})
            item['heat_score'] += 1
            item['max_board_count'] = max(item['max_board_count'], parse_board_count(str(row['streak_text'] or '')))

        ordered = sorted(stats.items(), key=lambda pair: (-pair[1]['heat_score'], pair[0]))
        return [
            HotSectorHistorySector(
                name=name,
                heat_score=payload['heat_score'],
                trend_tag=None,
                trend_label=self._build_trend_label(None, None),
                rank_today=int(index),
                max_board_count=payload['max_board_count'],
            )
            for index, (name, payload) in enumerate(ordered, start=1)
        ]

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

        # 1. Exact ts_code match (e.g. '000001.SZ')
        row = self._stock_list_repo.get_by_full_code_upper(q)
        if row:
            symbol = str(row['code']).zfill(6)
            if not self._has_local_market_data(symbol):
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
        raw_rows = self._stock_list_repo.list_by_code(q.zfill(6))
        rows = [r for r in raw_rows if self._has_local_market_data(str(r['code']).zfill(6))]
        if raw_rows and not rows:
            first_symbol = str(raw_rows[0]['code']).zfill(6)
            return StockResolveResponse(
                status='not_found',
                message=f'已匹配股票 {first_symbol} {raw_rows[0]["name"]}，但本地暂无行情数据，请先执行重新初始化市场数据。',
            )
        if len(rows) == 1:
            symbol = str(rows[0]['code']).zfill(6)
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
                    StockCandidate(stock_code=str(r['code']).zfill(6), stock_name=str(r['name']))
                    for r in rows
                ],
            )

        # 3. Exact cnspell match
        raw_rows = self._stock_list_repo.list_by_cnspell_exact(q)
        rows = [r for r in raw_rows if self._has_local_market_data(str(r['code']).zfill(6))]
        if raw_rows and not rows:
            return StockResolveResponse(
                status='not_found',
                message='已匹配到股票清单，但本地暂无对应行情数据，请先执行重新初始化市场数据。',
            )
        if len(rows) == 1:
            symbol = str(rows[0]['code']).zfill(6)
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
                    StockCandidate(stock_code=str(r['code']).zfill(6), stock_name=str(r['name']))
                    for r in rows
                ],
            )

        # 4. cnspell prefix match
        raw_rows = self._stock_list_repo.list_by_cnspell_prefix(q, limit=20)
        rows = [r for r in raw_rows if self._has_local_market_data(str(r['code']).zfill(6))]
        if raw_rows and not rows:
            return StockResolveResponse(
                status='not_found',
                message='已匹配到股票清单，但本地暂无对应行情数据，请先执行重新初始化市场数据。',
            )
        if len(rows) == 1:
            symbol = str(rows[0]['code']).zfill(6)
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
                    StockCandidate(stock_code=str(r['code']).zfill(6), stock_name=str(r['name']))
                    for r in rows
                ],
            )

        return StockResolveResponse(status='not_found', message='未找到匹配股票')

    def search_stocks(self, query: str, limit: int = 10) -> list[StockCandidate]:
        """Return up to *limit* candidates matching the query prefix.

        - Pure digits  → prefix match on symbol (stock code)
        - Letters/mixed → prefix match on cnspell (pinyin abbreviation)

        Only stocks that have local daily bars in DuckDB are returned.
        """
        q = query.strip().upper()
        if not q or not self._sqlite_path.exists():
            return []

        rows = self._stock_list_repo.list_for_search(q, limit * 3)

        if not rows:
            return []

        symbols = [str(r['code']).zfill(6) for r in rows]
        stocks_with_data = self._get_stocks_with_data(symbols)

        candidates = [
            StockCandidate(
                stock_code=str(r['code']).zfill(6),
                stock_name=str(r['name']),
            )
            for r in rows
            if str(r['code']).zfill(6) in stocks_with_data
        ]
        return candidates[:limit]

    def _get_stocks_with_data(self, symbols: list[str]) -> set[str]:
        """Return the subset of *symbols* that have at least one local daily bar."""
        if not symbols or not self._duckdb_path.exists():
            return set()
        full_codes = [_to_full_code(symbol) for symbol in symbols]
        connection = connect_duckdb(self._duckdb_path)
        try:
            placeholders = ','.join(['?' for _ in full_codes])
            rows = connection.execute(
                f"SELECT DISTINCT SPLIT_PART(full_code, '.', 1) AS stock_code "
                f'FROM day_level_trade_data WHERE full_code IN ({placeholders})',
                full_codes,
            ).fetchall()
            return {row[0] for row in rows}
        except Exception:
            return set()
        finally:
            connection.close()

    def _has_local_market_data(self, stock_code: str) -> bool:
        """Return True when local daily bars exist in DuckDB for the stock."""
        return self._has_stock_daily_bars(stock_code)

    def _has_stock_daily_bars(self, stock_code: str) -> bool:
        if self._duckdb_path.exists():
            full_code = self._to_query_full_code(stock_code)
            connection = connect_duckdb(self._duckdb_path)
            try:
                row = connection.execute(
                    'SELECT 1 FROM day_level_trade_data WHERE full_code = ? LIMIT 1',
                    [full_code],
                ).fetchone()
                if row:
                    return True
            except Exception:
                pass
            finally:
                connection.close()

        return False

    def _load_market_overview_payload_from_duckdb(self) -> dict[str, Any] | None:
        if not self._duckdb_path.exists():
            return None

        connection = connect_duckdb(self._duckdb_path)
        try:
            latest_trade_date_row = connection.execute(
                'SELECT MAX(trade_date) AS trade_date FROM day_level_trade_data'
            ).fetchone()
            latest_trade_date = str(latest_trade_date_row[0] or '').strip() if latest_trade_date_row else ''
            if not latest_trade_date:
                return None

            stock_rows = connection.execute(
                '''
                SELECT
                    full_code,
                    trade_date,
                    close,
                    amount,
                    pre_close
                FROM day_level_trade_data
                WHERE trade_date = ?
                ORDER BY amount DESC, full_code ASC
                ''',
                [latest_trade_date],
            ).fetchall()
            if not stock_rows:
                return None
        finally:
            connection.close()

        name_map = self._load_stock_name_map()

        stocks = []
        for row in stock_rows:
            full_code = str(row[0])
            stock_code = full_code.split('.')[0]
            trade_date = str(row[1])
            current_price = float(row[2])
            turnover_amount_billion = float(row[3] or 0.0)
            prev_close = float(row[4]) if row[4] is not None else current_price
            change_amount = round(current_price - prev_close, 4)
            change_pct = 0.0 if prev_close == 0 else round(change_amount / prev_close * 100, 4)
            stocks.append(
                {
                    'trade_date': trade_date,
                    'stock_code': stock_code,
                    'stock_name': name_map.get(stock_code, stock_code),
                    'current_price': current_price,
                    'change_amount': change_amount,
                    'change_pct': change_pct,
                    'turnover_amount_billion': turnover_amount_billion,
                    'turnover_rate': 0.0,
                    'sectors': [],
                    'ai_quick_summary': '',
                }
            )

        hot_sectors = self._load_hot_sectors_from_sqlite(latest_trade_date)
        if not hot_sectors:
            # Fallback: read hot_sectors from the market snapshot JSON (written by importer/updater)
            snapshot = self._load_local_snapshot()
            if snapshot:
                hot_sectors = snapshot.get('hot_sectors', [])

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
            'hot_sectors': hot_sectors,
            'stocks': stocks,
        }

    def _load_hot_sectors_from_sqlite(self, trade_date: str) -> list[dict[str, Any]]:
        """Load hot sectors for *trade_date* from SQLite daily_hot_info if available."""
        if not self._sqlite_path.exists():
            return []

        session_factory = self._session_factory()
        with session_factory() as session:
            rows = get_hot_info_rows_by_date(session, trade_date)

        return [
            {
                'trade_date': trade_date,
                'name': sector.name,
                'trend_label': sector.trend_label or '新晋热点',
                'heat_score': sector.heat_score,
            }
            for sector in self._build_hot_sector_history_sectors(rows)
        ]

    def _build_trend_label(self, trend_tag: str | None, days_present_3d: int | None) -> str:
        if trend_tag == 'persistent' and days_present_3d:
            return f'持续 {days_present_3d} 日'
        if trend_tag == 'fading':
            return '热度回落'
        return '新晋热点'

    def _load_stock_detail_payload_from_duckdb(self, stock_code: str) -> dict[str, Any] | None:
        if not self._duckdb_path.exists():
            return None

        full_code = self._to_query_full_code(stock_code)
        connection = connect_duckdb(self._duckdb_path)
        try:
            row = connection.execute(
                '''
                SELECT
                    trade_date,
                    open AS open_price,
                    high AS high_price,
                    low AS low_price,
                    close AS close_price,
                    amount AS turnover_amount_billion,
                    pre_close
                FROM day_level_trade_data
                WHERE full_code = ?
                ORDER BY trade_date DESC
                LIMIT 1
                ''',
                [full_code],
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None

        stock_name = self._load_stock_name_map().get(stock_code, stock_code)
        current_price = float(row[4])
        prev_close = float(row[6]) if row[6] is not None else current_price
        change_amount = round(current_price - prev_close, 4)
        change_pct = 0.0 if prev_close == 0 else round(change_amount / prev_close * 100, 4)

        return {
            'trade_date': str(row[0]),
            'stock_code': stock_code,
            'stock_name': stock_name,
            'current_price': current_price,
            'change_amount': change_amount,
            'change_pct': change_pct,
            'open_price': float(row[1]),
            'high_price': float(row[2]),
            'low_price': float(row[3]),
            'turnover_amount_billion': float(row[5] or 0.0),
            'turnover_rate': 0.0,
            'sectors': [],
            'ai_quick_summary': '',
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
        return self._load_stock_daily_bars_from_duckdb(stock_code)

    def _shift_months(self, date_text: str, months: int) -> str:
        target = datetime.strptime(date_text, '%Y-%m-%d').date()
        year = target.year
        month = target.month - months
        while month <= 0:
            year -= 1
            month += 12
        day = min(target.day, 28)
        return date(year, month, day).strftime('%Y-%m-%d')

    def _latest_trade_date_for_stock(self, stock_code: str) -> str | None:
        if not self._duckdb_path.exists():
            return None
        full_code = self._to_query_full_code(stock_code)
        connection = connect_duckdb(self._duckdb_path)
        try:
            row = connection.execute(
                '''
                SELECT MAX(trade_date)
                FROM day_level_trade_data
                WHERE full_code = ?
                ''',
                [full_code],
            ).fetchone()
        finally:
            connection.close()
        return str(row[0]) if row and row[0] else None

    def _load_stock_daily_bars_range(
            self,
            stock_code: str,
            *,
            months: int,
            end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        target_end_date = end_date or self._latest_trade_date_for_stock(stock_code)
        if not target_end_date:
            return []
        start_date = self._shift_months(target_end_date, months)

        if not self._duckdb_path.exists():
            return []

        full_code = self._to_query_full_code(stock_code)
        connection = connect_duckdb(self._duckdb_path)
        try:
            rows = connection.execute(
                '''
                SELECT trade_date, open AS open_price, high AS high_price, low AS low_price, close AS close_price, pre_close, change AS change_amount, pct_chg AS change_pct, vol AS volume, amount AS turnover_amount_billion, COALESCE (is_up_limit, FALSE) AS is_up_limit, COALESCE (is_down_limit, FALSE) AS is_down_limit
                FROM day_level_trade_data
                WHERE full_code = ?
                  AND trade_date >= ?
                  AND trade_date <= ?
                ORDER BY trade_date
                ''',
                [full_code, start_date, target_end_date],
            ).fetchall()
        except Exception:
            return []
        finally:
            connection.close()

        return self._serialize_daily_bar_rows(rows)

    def _has_more_daily_bars_before(self, stock_code: str, oldest_trade_date: str | None) -> bool:
        if not oldest_trade_date or not self._duckdb_path.exists():
            return False
        full_code = self._to_query_full_code(stock_code)
        connection = connect_duckdb(self._duckdb_path)
        try:
            row = connection.execute(
                '''
                SELECT 1
                FROM day_level_trade_data
                WHERE full_code = ?
                  AND trade_date < ? LIMIT 1
                ''',
                [full_code, oldest_trade_date],
            ).fetchone()
            return bool(row)
        except Exception:
            return False
        finally:
            connection.close()

    def _enrich_daily_bars_with_turnover(
        self, stock_code: str, daily_bars: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """No-op: daily_stock_snapshots table has been removed; turnover_rate stays 0.0."""
        return daily_bars


    def _load_stock_daily_bars_from_duckdb(self, stock_code: str) -> list[dict[str, Any]]:
        if not self._duckdb_path.exists():
            return []

        full_code = self._to_query_full_code(stock_code)
        connection = connect_duckdb(self._duckdb_path)
        try:
            rows = connection.execute(
                '''
                SELECT trade_date,
                       open AS open_price,
                       high AS high_price,
                       low AS low_price,
                       close AS close_price, pre_close, change AS change_amount, pct_chg AS change_pct,
                       vol AS volume,
                       amount AS turnover_amount_billion,
                       COALESCE(is_up_limit, FALSE) AS is_up_limit,
                       COALESCE(is_down_limit, FALSE) AS is_down_limit
                FROM day_level_trade_data
                WHERE full_code = ?
                ORDER BY trade_date
                ''',
                [full_code],
            ).fetchall()
        except Exception:
            return []
        finally:
            connection.close()

        return self._serialize_daily_bar_rows(rows)

    def _load_stock_daily_bars_from_parquet(self, stock_code: str) -> list[dict[str, Any]]:
        if not self._daily_bars_parquet_path.exists():
            return []

        full_code = self._to_query_full_code(stock_code)
        connection = connect_duckdb(self._duckdb_path)
        parquet_path = str(self._daily_bars_parquet_path).replace('\\', '/').replace("'", "''")
        try:
            rows = connection.execute(
                f'''
                SELECT trade_date,
                       open AS open_price,
                       high AS high_price,
                       low AS low_price,
                       close AS close_price,
                       pre_close,
                       change AS change_amount,
                       pct_chg AS change_pct,
                       vol AS volume,
                       COALESCE(amount, 0.0) AS turnover_amount_billion,
                       COALESCE(is_up_limit, FALSE) AS is_up_limit,
                       COALESCE(is_down_limit, FALSE) AS is_down_limit
                FROM read_parquet('{parquet_path}')
                WHERE full_code = ?
                ORDER BY trade_date
                ''',
                [full_code],
            ).fetchall()
        finally:
            connection.close()

        return self._serialize_daily_bar_rows(rows)

    def _to_query_full_code(self, stock_code: str) -> str:
        normalized = str(stock_code or '').strip().upper()
        if '.' in normalized:
            return normalized
        return _to_full_code(normalized)

    def _load_stock_name_map(self) -> dict[str, str]:
        if not self._sqlite_path.exists():
            return {}
        return self._metadata_repo.build_stock_name_map()


    def _serialize_daily_bar_rows(self, rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
        return [
            {
                'trade_date': trade_date,
                'open_price': open_price,
                'high_price': high_price,
                'low_price': low_price,
                'close_price': close_price,
                'pre_close': float(pre_close) if pre_close is not None else None,
                'change_amount': float(change_amount) if change_amount is not None else None,
                'change_pct': float(change_pct) if change_pct is not None else None,
                'volume': int(round(float(volume or 0))),
                'turnover_amount_billion': float(turnover_amount_billion or 0.0),
                'is_up_limit': bool(is_up_limit),
                'is_down_limit': bool(is_down_limit),
            }
            for trade_date, open_price, high_price, low_price, close_price,
            pre_close, change_amount, change_pct, volume,
                turnover_amount_billion, is_up_limit, is_down_limit in rows
        ]


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

    def _compute_expma_series(self, values: list[float], span: int) -> list[float | None]:
        return [round(v, 2) for v in self._compute_ema_series(values, span)]

    def _compute_kdj_series(
        self,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        n: int = 6,
        k_period: int = 3,
        d_period: int = 3,
    ) -> tuple[list[float | None], list[float | None], list[float | None]]:
        """KDJ(6,3,3). Seeds K=D=50."""
        N = len(closes)
        k_vals: list[float | None] = [None] * N
        d_vals: list[float | None] = [None] * N
        j_vals: list[float | None] = [None] * N
        prev_k, prev_d = 50.0, 50.0
        for i in range(n - 1, N):
            h_n = max(highs[i - n + 1 : i + 1])
            l_n = min(lows[i - n + 1 : i + 1])
            rsv = (closes[i] - l_n) / (h_n - l_n) * 100 if h_n != l_n else 50.0
            k = prev_k * (k_period - 1) / k_period + rsv / k_period
            d = prev_d * (d_period - 1) / d_period + k / d_period
            j = 3 * k - 2 * d
            k_vals[i] = round(k, 2)
            d_vals[i] = round(d, 2)
            j_vals[i] = round(j, 2)
            prev_k, prev_d = k, d
        return k_vals, d_vals, j_vals

    def _compute_macd_series(
        self, closes: list[float]
    ) -> tuple[list[float | None], list[float | None], list[float | None]]:
        """MACD(8,17,6). EMA seeded from first close."""
        N = len(closes)
        dif_vals: list[float | None] = [None] * N
        dea_vals: list[float | None] = [None] * N
        hist_vals: list[float | None] = [None] * N
        if N == 0:
            return dif_vals, dea_vals, hist_vals
        ema8 = self._compute_ema_series(closes, 8)
        ema17 = self._compute_ema_series(closes, 17)
        dif_raw = [ema8[i] - ema17[i] for i in range(N)]
        dea_raw = self._compute_ema_series(dif_raw, 6)
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
                'expma8': empty, 'expma17': empty, 'expma21': empty, 'expma55': empty,
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
            'expma8': self._compute_expma_series(closes, 8),
            'expma17': self._compute_expma_series(closes, 17),
            'expma21': self._compute_expma_series(closes, 21),
            'expma55': self._compute_expma_series(closes, 55),
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
            has_more_before=bool(payload.get('has_more_before', False)),
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
