import re
import sys
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any

from app.core.settings import settings
from app.db.sqlite import connect_sqlite, ensure_sqlite_schema

SOURCE_TYPE = 'jiuyangongshe_review_image'
SUPPORTED_IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}
HEADER_PATTERN = re.compile(r'(?P<name>[\u4e00-\u9fffA-Za-z0-9（）()·+\-/]+)\*(?P<count>\d+)')
STOCK_CODE_PATTERN = re.compile(r'(?P<code>\d{6}\.(?:SZ|SH))')
BOARD_COUNT_PATTERN = re.compile(r'(?:(\d+)天)?(\d+)板')
TIME_PATTERN = re.compile(r'(\d{1,2}:\d{2}:\d{2})')
CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')

CANONICAL_SECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    '商业航天': ('商业航天', '太空算力', '太空采矿', '航空航天'),
    'AI硬件': ('AI硬件', 'AI服务器', 'AI算力', '算力', '光模块', 'CPO', 'DPU'),
    '国产芯片': ('国产芯片', '半导体', 'AI芯片', '先进封装', '光刻机', '芯片测试', '探针', '铜箔'),
    '绿色电力': ('电力', '绿色电力', '绿电', '算电协同', '氢能', '火电', '风电', '光伏'),
    '电池产业链': ('电池产业链', '锂电池', '钠电', '固态电池', '储能', '复合集流体'),
    '机器人': ('机器人', '人形机器人', '飞行汽车'),
    '影视': ('影视', '影视传媒', '影视游戏', '短剧'),
    '公告驱动': ('公告', '拟收购', '资产注入预期', '年报增长', '季报增长', '年报披露预期'),
    '其他': ('其他',),
}


@dataclass(frozen=True)
class HotSectorImportResult:
    source_file_count: int
    stock_fact_count: int
    sector_mapping_count: int
    daily_sector_count: int
    latest_trade_date: str


@dataclass(frozen=True)
class OCRToken:
    text: str
    score: float
    x1: float
    x2: float
    y1: float
    y2: float

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2


@dataclass(frozen=True)
class ParsedSectorHeader:
    raw_name: str
    canonical_name: str
    declared_count: int
    order_index: int


@dataclass(frozen=True)
class ParsedStockFact:
    trade_date: str
    source_file: str
    stock_code: str
    stock_name: str
    board_count: int | None
    limit_up_time: str
    reason_raw: str
    reason_clean: str
    ocr_confidence: float
    needs_review: bool
    primary_sector_name: str
    primary_sector_alias_hit: str
    primary_sector_order: int
    primary_sector_declared_count: int


@dataclass(frozen=True)
class SectorMappingRecord:
    trade_date: str
    source_file: str
    stock_code: str
    sector_name_canonical: str
    sector_alias_hit: str
    is_primary_sector: bool
    mapping_method: str
    mapping_confidence: float
    needs_review: bool


@dataclass(frozen=True)
class DailySectorAggregate:
    trade_date: str
    sector_name_canonical: str
    source_stock_count: int
    max_board_count: int
    representative_stock_codes: list[str]
    representative_stock_names: list[str]
    heat_score: int
    rank_today: int
    aggregate_confidence: float
    needs_review: bool


@dataclass(frozen=True)
class Recent3DRecord:
    trade_date: str
    sector_name_canonical: str
    days_present_3d: int
    heat_sum_3d: int
    heat_avg_3d: float
    best_rank_3d: int
    latest_rank: int
    trend_tag: str


@dataclass(frozen=True)
class ParsedImage:
    trade_date: str
    source_file: str
    parse_status: str
    parse_notes: str
    stock_facts: list[ParsedStockFact]
    mappings: list[SectorMappingRecord]


def import_hot_sector_images(
    image_dir: Path,
    *,
    year: int,
    sqlite_path: Path | None = None,
    import_batch: str | None = None,
) -> HotSectorImportResult:
    resolved_dir = image_dir.resolve()
    image_files = sorted(
        file_path
        for file_path in resolved_dir.iterdir()
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    )
    if not image_files:
        raise ValueError(f'No supported image files found in {resolved_dir}')

    parsed_images = [_parse_image(file_path, year) for file_path in image_files]
    daily_aggregates = _build_daily_aggregates(parsed_images)
    recent_3d_records = _build_recent_3d_records(daily_aggregates)
    _write_sqlite_data(
        sqlite_path=sqlite_path or settings.sqlite_path,
        import_batch=import_batch or resolved_dir.name,
        parsed_images=parsed_images,
        daily_aggregates=daily_aggregates,
        recent_3d_records=recent_3d_records,
    )

    return HotSectorImportResult(
        source_file_count=len(parsed_images),
        stock_fact_count=sum(len(image.stock_facts) for image in parsed_images),
        sector_mapping_count=sum(len(image.mappings) for image in parsed_images),
        daily_sector_count=len(daily_aggregates),
        latest_trade_date=max((image.trade_date for image in parsed_images), default=''),
    )


def _parse_image(file_path: Path, year: int) -> ParsedImage:
    trade_date = _parse_trade_date_from_filename(file_path, year)
    rows = _group_ocr_rows(_run_ocr(file_path))

    stock_facts: list[ParsedStockFact] = []
    mappings: list[SectorMappingRecord] = []
    current_header = ParsedSectorHeader(
        raw_name='未归类',
        canonical_name='未归类',
        declared_count=0,
        order_index=999,
    )
    header_count = 0

    for row_tokens in rows:
        header = _parse_sector_header(row_tokens)
        if header is not None:
            header_count += 1
            current_header = ParsedSectorHeader(
                raw_name=header.raw_name,
                canonical_name=header.canonical_name,
                declared_count=header.declared_count,
                order_index=header_count,
            )
            continue

        stock_fact = _parse_stock_fact(
            row_tokens=row_tokens,
            current_header=current_header,
            trade_date=trade_date,
            source_file=file_path.name,
        )
        if stock_fact is None:
            continue

        stock_facts.append(stock_fact)
        mappings.extend(_build_sector_mappings(stock_fact))

    review_count = sum(1 for stock in stock_facts if stock.needs_review)
    parse_status = 'needs_review' if review_count else 'parsed'
    parse_notes = f'parsed_stocks={len(stock_facts)}, review_stocks={review_count}, parsed_sectors={header_count}'
    return ParsedImage(
        trade_date=trade_date,
        source_file=file_path.name,
        parse_status=parse_status,
        parse_notes=parse_notes,
        stock_facts=stock_facts,
        mappings=mappings,
    )


def _parse_trade_date_from_filename(file_path: Path, year: int) -> str:
    match = re.fullmatch(r'(\d{2})(\d{2})', file_path.stem)
    if match is None:
        raise ValueError(f'Unsupported hot-sector image filename: {file_path.name}')
    month = int(match.group(1))
    day = int(match.group(2))
    return date(year, month, day).isoformat()


@lru_cache(maxsize=1)
def _get_ocr_engine() -> Any:
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:  # pragma: no cover - exercised in runtime, not in tests
        raise RuntimeError(
            'rapidocr is required for hot-sector image parsing. '
            'Install backend dependencies before importing hot-sector images.'
        ) from exc
    return RapidOCR()


def _run_ocr(file_path: Path) -> list[OCRToken]:
    result = _get_ocr_engine()(str(file_path))
    if not result or result.boxes is None or result.txts is None or result.scores is None:
        return []

    tokens: list[OCRToken] = []
    for box, text, score in zip(result.boxes, result.txts, result.scores):
        cleaned_text = _normalize_text(text)
        if not cleaned_text:
            continue
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        tokens.append(
            OCRToken(
                text=cleaned_text,
                score=float(score),
                x1=min(xs),
                x2=max(xs),
                y1=min(ys),
                y2=max(ys),
            )
        )
    return tokens


def _group_ocr_rows(tokens: list[OCRToken]) -> list[list[OCRToken]]:
    rows: list[dict[str, Any]] = []
    for token in sorted(tokens, key=lambda item: (item.center_y, item.x1)):
        matched_row: dict[str, Any] | None = None
        for row in rows:
            if abs(row['center_y'] - token.center_y) <= 14:
                matched_row = row
                break
        if matched_row is None:
            rows.append({'center_y': token.center_y, 'tokens': [token]})
        else:
            matched_row['tokens'].append(token)
            matched_row['center_y'] = mean(item.center_y for item in matched_row['tokens'])

    grouped_rows: list[list[OCRToken]] = []
    for row in rows:
        row_tokens = sorted(row['tokens'], key=lambda item: item.x1)
        if not any(STOCK_CODE_PATTERN.search(token.text) or HEADER_PATTERN.search(token.text) for token in row_tokens):
            continue
        grouped_rows.append(row_tokens)
    return grouped_rows


def _parse_sector_header(row_tokens: list[OCRToken]) -> ParsedSectorHeader | None:
    for token in row_tokens:
        match = HEADER_PATTERN.search(token.text)
        if match is None:
            continue
        raw_name = match.group('name').strip('（）() ')
        if not raw_name:
            continue
        return ParsedSectorHeader(
            raw_name=raw_name,
            canonical_name=_canonicalize_sector_name(raw_name),
            declared_count=int(match.group('count')),
            order_index=0,
        )
    return None


def _parse_stock_fact(
    *,
    row_tokens: list[OCRToken],
    current_header: ParsedSectorHeader,
    trade_date: str,
    source_file: str,
) -> ParsedStockFact | None:
    code_index = -1
    stock_code = ''
    for index, token in enumerate(row_tokens):
        match = STOCK_CODE_PATTERN.search(token.text)
        if match is None:
            continue
        code_index = index
        stock_code = match.group('code')
        break
    if code_index < 0:
        return None

    board_count = None
    for token in row_tokens[:code_index]:
        match = BOARD_COUNT_PATTERN.search(token.text)
        if match is not None:
            board_count = int(match.group(2))
            break

    stock_name = ''
    for token in row_tokens[code_index + 1 :]:
        if _looks_like_stock_name(token.text):
            stock_name = token.text
            break

    limit_up_time = ''
    for token in row_tokens:
        match = TIME_PATTERN.search(token.text)
        if match is not None:
            limit_up_time = match.group(1)
            break

    reason_tokens = [
        token
        for token in row_tokens
        if token.x1 >= 1120 and not _is_watermark_noise(token.text) and not STOCK_CODE_PATTERN.search(token.text)
    ]
    if not reason_tokens:
        reason_tokens = [
            token
            for token in row_tokens[code_index + 1 :]
            if token.text != stock_name
            and token.text != limit_up_time
            and not _looks_like_number(token.text)
            and not _is_watermark_noise(token.text)
        ]
    reason_raw = ' '.join(token.text for token in reason_tokens).strip()
    reason_clean = _clean_reason_text(reason_raw)

    signal_tokens = [token for token in row_tokens if not _is_watermark_noise(token.text)]
    ocr_confidence = round(mean(token.score for token in signal_tokens), 4) if signal_tokens else 0.0
    needs_review = (
        current_header.canonical_name == '未归类'
        or not stock_name
        or not reason_clean
        or board_count is None
        or not limit_up_time
        or ocr_confidence < 0.78
    )

    return ParsedStockFact(
        trade_date=trade_date,
        source_file=source_file,
        stock_code=stock_code,
        stock_name=stock_name,
        board_count=board_count,
        limit_up_time=limit_up_time,
        reason_raw=reason_raw,
        reason_clean=reason_clean,
        ocr_confidence=ocr_confidence,
        needs_review=needs_review,
        primary_sector_name=current_header.canonical_name,
        primary_sector_alias_hit=current_header.raw_name,
        primary_sector_order=current_header.order_index,
        primary_sector_declared_count=current_header.declared_count,
    )


def _build_sector_mappings(stock_fact: ParsedStockFact) -> list[SectorMappingRecord]:
    mappings = [
        SectorMappingRecord(
            trade_date=stock_fact.trade_date,
            source_file=stock_fact.source_file,
            stock_code=stock_fact.stock_code,
            sector_name_canonical=stock_fact.primary_sector_name,
            sector_alias_hit=stock_fact.primary_sector_alias_hit,
            is_primary_sector=True,
            mapping_method='header',
            mapping_confidence=0.95,
            needs_review=stock_fact.needs_review,
        )
    ]

    secondary_sectors: list[tuple[str, str]] = []
    for part in _split_reason_parts(stock_fact.reason_clean):
        canonical_name = _match_sector_from_text(part)
        if canonical_name is None or canonical_name == stock_fact.primary_sector_name:
            continue
        if any(existing_name == canonical_name for existing_name, _ in secondary_sectors):
            continue
        secondary_sectors.append((canonical_name, part))

    for canonical_name, alias_hit in secondary_sectors:
        mappings.append(
            SectorMappingRecord(
                trade_date=stock_fact.trade_date,
                source_file=stock_fact.source_file,
                stock_code=stock_fact.stock_code,
                sector_name_canonical=canonical_name,
                sector_alias_hit=alias_hit,
                is_primary_sector=False,
                mapping_method='reason_keyword',
                mapping_confidence=0.72,
                needs_review=stock_fact.needs_review,
            )
        )
    return mappings


def _build_daily_aggregates(parsed_images: list[ParsedImage]) -> list[DailySectorAggregate]:
    grouped: dict[tuple[str, str], list[ParsedStockFact]] = {}
    for image in parsed_images:
        for stock_fact in image.stock_facts:
            grouped.setdefault((stock_fact.trade_date, stock_fact.primary_sector_name), []).append(stock_fact)

    ranked_by_date: dict[str, list[DailySectorAggregate]] = {}
    for (trade_date, sector_name), stocks in grouped.items():
        observed_count = len(stocks)
        declared_count = max((stock.primary_sector_declared_count for stock in stocks), default=0)
        max_board_count = max((stock.board_count or 0 for stock in stocks), default=0)
        sorted_stocks = sorted(
            stocks,
            key=lambda stock: (
                -(stock.board_count or 0),
                stock.limit_up_time or '99:99:99',
                -stock.ocr_confidence,
                stock.stock_code,
            ),
        )
        representative_stocks = sorted_stocks[:3]
        sector_order = min(stock.primary_sector_order for stock in stocks)
        heat_basis = max(observed_count, declared_count)
        heat_score = min(99, heat_basis * 10 + max_board_count * 4 + max(0, 8 - sector_order))
        ranked_by_date.setdefault(trade_date, []).append(
            DailySectorAggregate(
                trade_date=trade_date,
                sector_name_canonical=sector_name,
                source_stock_count=observed_count,
                max_board_count=max_board_count,
                representative_stock_codes=[stock.stock_code for stock in representative_stocks],
                representative_stock_names=[stock.stock_name for stock in representative_stocks],
                heat_score=heat_score,
                rank_today=0,
                aggregate_confidence=round(mean(stock.ocr_confidence for stock in stocks), 4),
                needs_review=any(stock.needs_review for stock in stocks),
            )
        )

    aggregates: list[DailySectorAggregate] = []
    for trade_date, daily_aggregates in ranked_by_date.items():
        ranked_daily = sorted(
            daily_aggregates,
            key=lambda item: (-item.heat_score, -item.max_board_count, -item.source_stock_count, item.sector_name_canonical),
        )
        for rank, aggregate in enumerate(ranked_daily, start=1):
            aggregates.append(
                DailySectorAggregate(
                    trade_date=aggregate.trade_date,
                    sector_name_canonical=aggregate.sector_name_canonical,
                    source_stock_count=aggregate.source_stock_count,
                    max_board_count=aggregate.max_board_count,
                    representative_stock_codes=aggregate.representative_stock_codes,
                    representative_stock_names=aggregate.representative_stock_names,
                    heat_score=aggregate.heat_score,
                    rank_today=rank,
                    aggregate_confidence=aggregate.aggregate_confidence,
                    needs_review=aggregate.needs_review,
                )
            )
    return sorted(aggregates, key=lambda item: (item.trade_date, item.rank_today, item.sector_name_canonical))


def _build_recent_3d_records(daily_aggregates: list[DailySectorAggregate]) -> list[Recent3DRecord]:
    aggregates_by_date: dict[str, list[DailySectorAggregate]] = {}
    for aggregate in daily_aggregates:
        aggregates_by_date.setdefault(aggregate.trade_date, []).append(aggregate)

    sorted_dates = sorted(aggregates_by_date)
    recent_records: list[Recent3DRecord] = []
    for index, trade_date in enumerate(sorted_dates):
        window_dates = sorted_dates[max(0, index - 2) : index + 1]
        window_aggregates = [aggregate for current_date in window_dates for aggregate in aggregates_by_date[current_date]]
        for aggregate in aggregates_by_date[trade_date]:
            sector_window = [item for item in window_aggregates if item.sector_name_canonical == aggregate.sector_name_canonical]
            days_present = len(sector_window)
            heat_sum = sum(item.heat_score for item in sector_window)
            best_rank = min(item.rank_today for item in sector_window)
            trend_tag = _build_trend_tag(days_present=days_present, latest_rank=aggregate.rank_today, best_rank=best_rank)
            recent_records.append(
                Recent3DRecord(
                    trade_date=trade_date,
                    sector_name_canonical=aggregate.sector_name_canonical,
                    days_present_3d=days_present,
                    heat_sum_3d=heat_sum,
                    heat_avg_3d=round(heat_sum / days_present, 2),
                    best_rank_3d=best_rank,
                    latest_rank=aggregate.rank_today,
                    trend_tag=trend_tag,
                )
            )
    return recent_records


def _build_trend_tag(*, days_present: int, latest_rank: int, best_rank: int) -> str:
    if days_present <= 1:
        return 'new'
    if latest_rank <= best_rank + 1:
        return 'persistent'
    return 'fading'


def _write_sqlite_data(
    *,
    sqlite_path: Path,
    import_batch: str,
    parsed_images: list[ParsedImage],
    daily_aggregates: list[DailySectorAggregate],
    recent_3d_records: list[Recent3DRecord],
) -> None:
    ensure_sqlite_schema(sqlite_path)
    trade_dates = sorted({image.trade_date for image in parsed_images})
    connection = connect_sqlite(sqlite_path)
    try:
        for table_name in (
            'hot_sector_recent_3d',
            'hot_sector_daily_aggregates',
            'hot_sector_sector_mappings',
            'hot_sector_stock_facts',
            'hot_sector_image_sources',
        ):
            connection.executemany(
                f'DELETE FROM {table_name} WHERE trade_date = ?',
                [(trade_date,) for trade_date in trade_dates],
            )

        connection.executemany(
            '''
            INSERT INTO hot_sector_image_sources (
                trade_date,
                source_file,
                source_type,
                import_batch,
                parse_status,
                parse_notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            ''',
            [
                (
                    image.trade_date,
                    image.source_file,
                    SOURCE_TYPE,
                    import_batch,
                    image.parse_status,
                    image.parse_notes,
                )
                for image in parsed_images
            ],
        )
        connection.executemany(
            '''
            INSERT INTO hot_sector_stock_facts (
                trade_date,
                source_file,
                stock_code,
                stock_name,
                board_count,
                limit_up_time,
                reason_raw,
                reason_clean,
                ocr_confidence,
                needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (
                    stock.trade_date,
                    stock.source_file,
                    stock.stock_code,
                    stock.stock_name,
                    stock.board_count,
                    stock.limit_up_time,
                    stock.reason_raw,
                    stock.reason_clean,
                    stock.ocr_confidence,
                    int(stock.needs_review),
                )
                for image in parsed_images
                for stock in image.stock_facts
            ],
        )
        connection.executemany(
            '''
            INSERT INTO hot_sector_sector_mappings (
                trade_date,
                source_file,
                stock_code,
                sector_name_canonical,
                sector_alias_hit,
                is_primary_sector,
                mapping_method,
                mapping_confidence,
                needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (
                    mapping.trade_date,
                    mapping.source_file,
                    mapping.stock_code,
                    mapping.sector_name_canonical,
                    mapping.sector_alias_hit,
                    int(mapping.is_primary_sector),
                    mapping.mapping_method,
                    mapping.mapping_confidence,
                    int(mapping.needs_review),
                )
                for image in parsed_images
                for mapping in image.mappings
            ],
        )
        connection.executemany(
            '''
            INSERT INTO hot_sector_daily_aggregates (
                trade_date,
                sector_name_canonical,
                source_stock_count,
                max_board_count,
                representative_stock_codes_json,
                representative_stock_names_json,
                heat_score,
                rank_today,
                aggregate_confidence,
                needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (
                    aggregate.trade_date,
                    aggregate.sector_name_canonical,
                    aggregate.source_stock_count,
                    aggregate.max_board_count,
                    _dump_json(aggregate.representative_stock_codes),
                    _dump_json(aggregate.representative_stock_names),
                    aggregate.heat_score,
                    aggregate.rank_today,
                    aggregate.aggregate_confidence,
                    int(aggregate.needs_review),
                )
                for aggregate in daily_aggregates
            ],
        )
        connection.executemany(
            '''
            INSERT INTO hot_sector_recent_3d (
                trade_date,
                sector_name_canonical,
                days_present_3d,
                heat_sum_3d,
                heat_avg_3d,
                best_rank_3d,
                latest_rank,
                trend_tag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            [
                (
                    record.trade_date,
                    record.sector_name_canonical,
                    record.days_present_3d,
                    record.heat_sum_3d,
                    record.heat_avg_3d,
                    record.best_rank_3d,
                    record.latest_rank,
                    record.trend_tag,
                )
                for record in recent_3d_records
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _dump_json(payload: Any) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)


def _normalize_text(text: str) -> str:
    return ' '.join(str(text).replace('\n', ' ').split())


def _looks_like_stock_name(text: str) -> bool:
    if not CHINESE_PATTERN.search(text):
        return False
    if _is_watermark_noise(text):
        return False
    return not any(pattern.search(text) for pattern in (HEADER_PATTERN, STOCK_CODE_PATTERN, TIME_PATTERN)) and not _looks_like_number(text)


def _looks_like_number(text: str) -> bool:
    cleaned = text.strip().strip('()（）')
    if not cleaned:
        return False
    cleaned = cleaned.replace('.', '', 1)
    return cleaned.isdigit()


def _is_watermark_noise(text: str) -> bool:
    lowered = text.lower().replace(' ', '')
    if any(fragment in lowered for fragment in ('www', '.com', 'jiuy', 'gsh', 'luyang', 'ngong', 'ango', 'gongshe', 'she.co', 'he.co')):
        return True
    return not CHINESE_PATTERN.search(text) and any(character.isalpha() for character in lowered)


def _clean_reason_text(reason_raw: str) -> str:
    if not reason_raw:
        return ''
    reason = reason_raw
    reason = re.sub(r'\s*\+\s*', '+', reason)
    reason = re.sub(r'\s+', ' ', reason).strip()
    reason = reason.strip('+')
    return reason


def _split_reason_parts(reason_clean: str) -> list[str]:
    if not reason_clean:
        return []
    return [part.strip('（）() ') for part in reason_clean.split('+') if part.strip('（）() ')]


def _canonicalize_sector_name(raw_name: str) -> str:
    matched = _match_sector_from_text(raw_name)
    return matched or raw_name


def _match_sector_from_text(text: str) -> str | None:
    normalized = text.strip()
    best_match: tuple[int, str] | None = None
    for canonical_name, aliases in CANONICAL_SECTOR_ALIASES.items():
        for alias in aliases:
            if alias in normalized or normalized in alias:
                score = len(alias)
                if best_match is None or score > best_match[0]:
                    best_match = (score, canonical_name)
    return best_match[1] if best_match is not None else None


def main(argv: list[str] | None = None) -> int:
    arguments = argv or sys.argv[1:]
    if len(arguments) not in {2, 3}:
        print(
            'Usage: python -m app.modules.market_data.hot_sector_importer <image-dir> <year> [import-batch]',
            file=sys.stderr,
        )
        return 1

    image_dir = Path(arguments[0])
    year = int(arguments[1])
    import_batch = arguments[2] if len(arguments) == 3 else None
    result = import_hot_sector_images(image_dir, year=year, import_batch=import_batch)
    print(
        'Imported hot-sector images: '
        f'source_files={result.source_file_count}, '
        f'stock_facts={result.stock_fact_count}, '
        f'sector_mappings={result.sector_mapping_count}, '
        f'daily_sectors={result.daily_sector_count}, '
        f'latest_trade_date={result.latest_trade_date}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
