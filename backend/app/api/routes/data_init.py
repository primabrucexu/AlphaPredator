from fastapi import APIRouter, HTTPException, Query, UploadFile, status

from app.core.settings import settings
from app.modules.market_data.initializer import (
    create_task,
    get_overview,
    get_task,
    get_task_days,
    list_tasks,
    read_init_status,
    reimport_day,
    start_task,
)
from app.modules.market_data.updater import run_daily_update
from app.schemas.data_init import (
    CreateTaskRequest,
    DataRangeInfo,
    InitOverviewResponse,
    InitStatusResponse,
    InitV2OverviewResponse,
    ReimportDayRequest,
    SaveTokenRequest,
    StockListUploadResponse,
    TaskDayItem,
    TaskDaysResponse,
    TaskResponse,
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
    """Return whether the Tushare token is currently configured."""
    from app.modules.market_data.data_source import _get_token
    return TokenConfigResponse(is_configured=bool(_get_token()))


@router.post('/token', response_model=TokenConfigResponse)
def save_token_config(body: SaveTokenRequest) -> TokenConfigResponse:
    """Save the Tushare API token to the local token file."""
    token_path = settings.tushare_token_path
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(body.token.strip(), encoding='utf-8')
    return TokenConfigResponse(is_configured=True)


# ---------------------------------------------------------------------------
# Stock list upload
# ---------------------------------------------------------------------------


@router.post('/upload-stock-list', response_model=StockListUploadResponse)
async def upload_stock_list(file: UploadFile) -> StockListUploadResponse:
    """Upload the stock universe CSV file."""
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

    dest = settings.stock_list_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(contents)

    from datetime import datetime, timezone

    from app.db.sqlite import connect_sqlite, ensure_sqlite_schema

    uploaded_at = datetime.now(timezone.utc).isoformat()
    ensure_sqlite_schema()
    conn = connect_sqlite()
    try:
        conn.execute('DELETE FROM stock_universe')
        fill_cols = {c: '' for c in ['cnspell', 'market', 'list_status', 'list_date', 'delist_date']
                     if c not in df.columns}
        for col, default in fill_cols.items():
            df[col] = default
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

    total = len(df)
    active_df = df[df['list_status'].fillna('') == 'L']
    active = len(active_df)
    boards: dict[str, int] = {}
    market_active = active_df[active_df['market'].notna() & (active_df['market'].str.strip() != '')]
    for board, grp in market_active.groupby('market'):
        boards[str(board)] = len(grp)

    return StockListUploadResponse(total_stocks=total, active_stocks=active, boards=boards)


# ---------------------------------------------------------------------------
# V2 Initialization endpoints
# ---------------------------------------------------------------------------


@router.post('/tasks', response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
def create_init_task(body: CreateTaskRequest) -> TaskResponse:
    """Create and immediately start a market data initialization task.

    Preconditions (returns 400 if not met):
    - Tushare token must be configured.

    Returns 202 if started, 409 if another task is already running.
    """
    if body.start_date > body.end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='start_date must be <= end_date',
        )

    try:
        task = create_task(body.start_date, body.end_date, mode=body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    started = start_task(task['task_id'])
    if not started:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Another initialization task is already running',
        )

    task = get_task(task['task_id']) or task
    return TaskResponse.from_db_row(task)


@router.get('/tasks', response_model=list[TaskResponse])
def list_init_tasks(limit: int = Query(20, ge=1, le=100)) -> list[TaskResponse]:
    """Return recent init tasks ordered by created_at descending."""
    tasks = list_tasks(limit=limit)
    return [TaskResponse.from_db_row(t) for t in tasks]


@router.get('/tasks/{task_id}', response_model=TaskResponse)
def get_init_task(task_id: str) -> TaskResponse:
    """Return the current status and progress of an init task."""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
    return TaskResponse.from_db_row(task)


@router.get('/tasks/{task_id}/days', response_model=TaskDaysResponse)
def get_init_task_days(
    task_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> TaskDaysResponse:
    """Return paginated per-day execution details for an init task."""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')

    result = get_task_days(task_id, page=page, per_page=per_page)
    days = [
        TaskDayItem(
            task_id=d['task_id'],
            trade_date=d['trade_date'],
            is_trading_day=bool(d['is_trading_day']),
            status=d['status'],
            row_count=d.get('row_count', 0),
            started_at=d.get('started_at', ''),
            finished_at=d.get('finished_at', ''),
            error_message=d.get('error_message', ''),
        )
        for d in result['days']
    ]
    return TaskDaysResponse(
        task_id=task_id,
        total=result['total'],
        page=result['page'],
        per_page=result['per_page'],
        days=days,
    )


@router.post('/reimport-day', response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
def reimport_day_endpoint(body: ReimportDayRequest) -> TaskResponse:
    """Trigger a REIMPORT_DAY task for the specified trading day (YYYYMMDD).

    The import is idempotent: existing data for that day is deleted and
    rewritten within a single transaction.

    Returns 409 if another task is already running.
    """
    try:
        task = reimport_day(body.trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if task.get('status') == 'PENDING':
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Another initialization task is already running',
        )

    return TaskResponse.from_db_row(task)


# ---------------------------------------------------------------------------
# V2 Overview
# ---------------------------------------------------------------------------


@router.get('/init/overview', response_model=InitV2OverviewResponse)
def get_init_v2_overview() -> InitV2OverviewResponse:
    """Return the full V2 initialization overview."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
    from app.modules.market_data.data_source import _get_token

    token_configured = bool(_get_token())
    stock_list_path = settings.stock_list_path
    stock_list_uploaded = stock_list_path.exists()

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

        if not stock_list_updated_at:
            from datetime import timezone
            mtime = stock_list_path.stat().st_mtime
            stock_list_updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    cst = ZoneInfo('Asia/Shanghai')
    now_cst = datetime.now(cst)
    cutoff_cst = now_cst.replace(hour=15, minute=30, second=0, microsecond=0)
    daily_quote_cutoff_time = cutoff_cst.isoformat()

    v2 = get_overview()
    running = v2.get('running_task')
    latest = v2.get('latest_task')
    dr = v2.get('data_range', {})

    return InitV2OverviewResponse(
        running_task=TaskResponse.from_db_row(running) if running else None,
        latest_task=TaskResponse.from_db_row(latest) if latest else None,
        data_range=DataRangeInfo(
            min_trade_date=dr.get('min_trade_date'),
            max_trade_date=dr.get('max_trade_date'),
            trading_day_count=dr.get('trading_day_count', 0),
        ),
        token_configured=token_configured,
        stock_list_uploaded=stock_list_uploaded,
        stock_list_updated_at=stock_list_updated_at,
        daily_quote_cutoff_time=daily_quote_cutoff_time,
        board_counts=board_counts,
    )


# ---------------------------------------------------------------------------
# Legacy endpoints (kept for backward compatibility)
# ---------------------------------------------------------------------------


@router.get('/status', response_model=InitStatusResponse)
def get_init_status() -> InitStatusResponse:
    """Return the current initialization status (legacy format)."""
    return InitStatusResponse(**read_init_status())


@router.post('/update', response_model=UpdateResult)
def daily_update() -> UpdateResult:
    """Trigger an incremental update for today's market data."""
    result = run_daily_update()
    return UpdateResult(**result)


@router.get('/overview', response_model=InitOverviewResponse)
def get_init_overview() -> InitOverviewResponse:
    """Return a lightweight overview of the initialization state for the homepage."""
    from datetime import datetime, timezone

    from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
    from app.modules.market_data.data_source import _get_token

    token_configured = bool(_get_token())
    stock_list_path = settings.stock_list_path
    stock_list_uploaded = stock_list_path.exists()

    # Determine init_completed from V2 task system
    v2 = get_overview()
    init_completed = (
        (v2.get('latest_task') or {}).get('status') == 'SUCCESS'
    )

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

        if not stock_list_updated_at:
            mtime = stock_list_path.stat().st_mtime
            stock_list_updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

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
