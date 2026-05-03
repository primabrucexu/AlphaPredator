from fastapi import APIRouter, HTTPException, UploadFile, status

from app.core.settings import settings
from app.modules.market_data.initializer import read_init_status, start_initialization
from app.modules.market_data.updater import run_daily_update
from app.schemas.data_init import (
    InitOverviewResponse,
    InitStatusResponse,
    SaveTokenRequest,
    StartInitRequest,
    StockListUploadResponse,
    TokenConfigResponse,
    UpdateResult,
)

router = APIRouter()


def _read_stock_list_csv(contents: bytes):
    """Read uploaded stock list CSV with common encoding fallbacks."""
    import io

    import pandas as pd

    encodings = ('utf-8-sig', 'utf-8', 'gb18030', 'gbk')
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return pd.read_csv(io.BytesIO(contents), dtype=str, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

    raise ValueError(
        'Failed to parse CSV with supported encodings '
        f"{encodings}. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# Token configuration
# ---------------------------------------------------------------------------


@router.get('/token', response_model=TokenConfigResponse)
def get_token_config() -> TokenConfigResponse:
    """Return whether the Tushare token is currently configured (never returns the token itself)."""
    from app.modules.market_data.data_source import _get_token
    return TokenConfigResponse(is_configured=bool(_get_token()))


@router.post('/token', response_model=TokenConfigResponse)
def save_token_config(body: SaveTokenRequest) -> TokenConfigResponse:
    """
    Save the Tushare API token to the local token file.

    The token is persisted server-side only and is never echoed back.
    """
    token_path = settings.tushare_token_path
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(body.token.strip(), encoding='utf-8')
    return TokenConfigResponse(is_configured=True)


# ---------------------------------------------------------------------------
# Stock list upload
# ---------------------------------------------------------------------------


@router.post('/upload-stock-list', response_model=StockListUploadResponse)
async def upload_stock_list(file: UploadFile) -> StockListUploadResponse:
    """
    Upload the stock universe CSV file.

    The file must have a header row with at least these columns:
        ts_code, symbol, name, market, list_status, list_date, delist_date

    The file is persisted server-side and used as the source for all subsequent
    initialization runs.
    """
    from app.modules.market_data.data_source import _REQUIRED_STOCK_LIST_COLS

    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Only CSV files are accepted.',
        )

    contents = await file.read()
    try:
        df = _read_stock_list_csv(contents)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    missing = _REQUIRED_STOCK_LIST_COLS - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f'CSV is missing required columns: {sorted(missing)}',
        )

    # Persist raw CSV to configured path
    dest = settings.stock_list_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(contents)

    # Persist to stock_universe table for fast lookup (including cnspell for pinyin search)
    from datetime import datetime, timezone

    from app.db.sqlite import connect_sqlite, ensure_sqlite_schema

    uploaded_at = datetime.now(timezone.utc).isoformat()
    ensure_sqlite_schema()
    conn = connect_sqlite()
    try:
        conn.execute('DELETE FROM stock_universe')
        # Build insert rows using vectorised pandas operations for performance
        fill_cols = {c: '' for c in ['cnspell', 'market', 'list_status', 'list_date', 'delist_date']
                     if c not in df.columns}
        for col, default in fill_cols.items():
            df[col] = default
        # Normalise cnspell to uppercase
        df['cnspell'] = df['cnspell'].fillna('').astype(str).str.strip().str.upper()
        rows_to_insert = [
            (
                str(r.ts_code or '').strip(),
                str(r.symbol or '').strip(),
                str(r.name or '').strip(),
                str(r.cnspell or ''),
                str(r.market or '').strip(),
                str(r.list_status or '').strip(),
                str(r.list_date or '').strip(),
                str(r.delist_date or '').strip(),
                uploaded_at,
            )
            for r in df[['ts_code', 'symbol', 'name', 'cnspell', 'market',
                          'list_status', 'list_date', 'delist_date']].itertuples(index=False)
        ]
        conn.executemany(
            '''INSERT OR REPLACE INTO stock_universe
               (ts_code, symbol, name, cnspell, market, list_status, list_date, delist_date, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            rows_to_insert,
        )
        conn.commit()
    finally:
        conn.close()

    # Compute stats
    total = len(df)
    active_df = df[df['list_status'].fillna('') == 'L']
    active = len(active_df)
    boards: dict[str, int] = {}
    # Exclude rows with null/empty market value to avoid NaN board names
    market_active = active_df[active_df['market'].notna() & (active_df['market'].str.strip() != '')]
    for board, grp in market_active.groupby('market'):
        boards[str(board)] = len(grp)

    return StockListUploadResponse(total_stocks=total, active_stocks=active, boards=boards)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@router.post('/start', response_model=InitStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def start_init(body: StartInitRequest) -> InitStatusResponse:
    """
    Start a full market data initialization in the background.

    Preconditions (returns 400 if not met):
    - Tushare token must be configured.
    - Stock universe CSV must have been uploaded.

    Returns 202 if started, 409 if an initialization is already running.
    """
    try:
        started = start_initialization(
            history_days=body.history_days,
            market_filters=list(body.market_filters) if body.market_filters else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not started:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Initialization already running',
        )
    current = read_init_status()
    return InitStatusResponse(**current)


@router.get('/status', response_model=InitStatusResponse)
def get_init_status() -> InitStatusResponse:
    """Return the current initialization status."""
    return InitStatusResponse(**read_init_status())


@router.post('/update', response_model=UpdateResult)
def daily_update() -> UpdateResult:
    """
    Trigger an incremental update for today's market data.

    The update runs synchronously and returns the result.
    For large markets this may take a few minutes.
    """
    result = run_daily_update()
    return UpdateResult(**result)


# ---------------------------------------------------------------------------
# Phase 2.10: Init overview (homepage status panel)
# ---------------------------------------------------------------------------


@router.get('/overview', response_model=InitOverviewResponse)
def get_init_overview() -> InitOverviewResponse:
    """
    Return a lightweight overview of the initialization state for the homepage.

    Includes:
    - Whether a Tushare token is configured.
    - Whether the stock universe CSV has been uploaded.
    - Whether initialization has completed (status=done).
    - Stock list update timestamp and per-board active stock counts.
    - Daily quote cutoff time (15:30 CST on today's date).
    """
    from datetime import datetime, timezone

    from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
    from app.modules.market_data.data_source import _get_token

    token_configured = bool(_get_token())
    stock_list_path = settings.stock_list_path
    stock_list_uploaded = stock_list_path.exists()

    init_status_data = read_init_status()
    init_completed = init_status_data.get('status') == 'done'

    stock_list_updated_at: str | None = None
    board_counts: dict[str, int] = {}

    if stock_list_uploaded:
        ensure_sqlite_schema()
        conn = connect_sqlite()
        try:
            row = conn.execute(
                'SELECT MAX(uploaded_at) AS uploaded_at FROM stock_universe'
            ).fetchone()
            if row and row['uploaded_at']:
                stock_list_updated_at = str(row['uploaded_at'])

            board_rows = conn.execute(
                '''SELECT market, COUNT(*) AS cnt
                   FROM stock_universe
                   WHERE list_status = 'L' AND market != ''
                   GROUP BY market'''
            ).fetchall()
            for br in board_rows:
                board_counts[str(br['market'])] = int(br['cnt'])
        finally:
            conn.close()

        # Fallback: use file mtime if no uploaded_at in DB
        if not stock_list_updated_at:
            mtime = stock_list_path.stat().st_mtime
            stock_list_updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    # Daily quote cutoff: 15:30 CST on today's date.
    # CST = UTC+8, so 15:30 CST = 07:30 UTC.  We express the cutoff in local
    # Shanghai time using a fixed +08:00 offset (China Standard Time has no DST).
    from zoneinfo import ZoneInfo
    cst = ZoneInfo('Asia/Shanghai')
    now_cst = datetime.now(cst)
    cutoff_cst = now_cst.replace(hour=15, minute=30, second=0, microsecond=0)
    daily_quote_cutoff_time = cutoff_cst.isoformat()

    return InitOverviewResponse(
        init_completed=init_completed,
        token_configured=token_configured,
        stock_list_uploaded=stock_list_uploaded,
        stock_list_updated_at=stock_list_updated_at,
        daily_quote_cutoff_time=daily_quote_cutoff_time,
        board_counts=board_counts,
    )
