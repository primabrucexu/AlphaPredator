import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status

from app.core.settings import settings
from app.db.sqlite import ensure_sqlite_schema
from app.modules.market_data.data_source import _get_mairui_licence
from app.modules.market_data.initializer import (
    create_task,
    get_overview,
    get_task,
    list_tasks,
    read_init_status,
    reimport_day,
    retry_task,
    start_task,
    terminate_task,
)
from app.modules.market_data.updater import run_daily_update
from app.repositories.stock_list_repo import StockListRepo
from app.schemas.data_init import (
    CreateTaskRequest,
    DataRangeInfo,
    InitOverviewResponse,
    InitStatusResponse,
    InitV2OverviewResponse,
    MairuiLicenceConfigResponse,
    ReimportDayRequest,
    SaveMairuiLicenceRequest,
    TaskResponse,
    UpdateResult,
)

router = APIRouter()


def _mask_licence(licence: str) -> str:
    text = licence.strip()
    if len(text) <= 8:
        return '*' * len(text)
    return f'{text[:4]}...{text[-4:]}'


def _read_mairui_licence_state() -> tuple[str, str]:
    env_licence = os.environ.get('MAIRUI_LICENCE', '').strip()
    if env_licence:
        return env_licence, 'env'

    licence_path = settings.mairui_licence_path
    if licence_path.exists():
        file_licence = _get_mairui_licence().strip()
        if file_licence:
            return file_licence, 'file'

    return '', 'none'


def _load_stock_list_board_counts() -> dict[str, int]:
    """Load stock_list board counts from SQLite."""
    ensure_sqlite_schema()
    repo = StockListRepo()
    return repo.get_board_counts()



# ---------------------------------------------------------------------------
# V2 Initialization endpoints
# ---------------------------------------------------------------------------


@router.get('/licence', response_model=MairuiLicenceConfigResponse)
def get_mairui_licence_config() -> MairuiLicenceConfigResponse:
    """Return current Mairui licence config state for UI rendering."""
    licence, source = _read_mairui_licence_state()
    configured = bool(licence)
    return MairuiLicenceConfigResponse(
        configured=configured,
        masked_licence=_mask_licence(licence) if configured else None,
        source=source,
    )


@router.post('/licence', response_model=MairuiLicenceConfigResponse)
def save_mairui_licence(body: SaveMairuiLicenceRequest) -> MairuiLicenceConfigResponse:
    """Persist Mairui licence to configured file path."""
    licence = body.licence.strip()
    if not licence:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='licence cannot be empty',
        )

    licence_path = settings.mairui_licence_path
    licence_path.parent.mkdir(parents=True, exist_ok=True)
    licence_path.write_text(licence, encoding='utf-8')

    return MairuiLicenceConfigResponse(
        configured=True,
        masked_licence=_mask_licence(licence),
        source='file',
    )


@router.post('/tasks', response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
def create_init_task(body: CreateTaskRequest) -> TaskResponse:
    """Create and immediately start an initialization task.

    Supports three task types:
    - STOCK_LIST_SYNC: Sync stock list from Mairui (no date range needed)
    - MARKET_DATA: Market data load (FULL_SYNC | INCREMENTAL_SYNC)
    - JYGS_REVIEW: JYGS review data fetch

    Returns 202 if started, 409 if another task is already running.
    """
    today = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')

    # STOCK_LIST_SYNC doesn't need a date range; set defaults if not provided
    if body.task_type == 'STOCK_LIST_SYNC':
        start_date = body.start_date or today
        end_date = body.end_date or today
    else:
        start_date = body.start_date
        end_date = body.end_date
        if not start_date or not end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='start_date and end_date are required for this task type',
            )
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='start_date must be <= end_date',
            )

    try:
        task = create_task(
            start_date,
            end_date,
            mode=body.mode,
            task_type=body.task_type,
        )
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




@router.post('/tasks/{task_id}/retry', response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_init_task(task_id: str) -> TaskResponse:
    """Retry a failed task by resetting progress and starting it again."""
    task = retry_task(task_id)
    if task is None:
        existing = get_task(task_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
        if existing.get('status') != 'FAILED':
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Only FAILED tasks can be retried',
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Another initialization task is already running',
        )
    return TaskResponse.from_db_row(task)


@router.post('/tasks/{task_id}/terminate', response_model=TaskResponse)
def terminate_init_task(task_id: str) -> TaskResponse:
    """Terminate a RUNNING/FAILED/PENDING task."""
    task = terminate_task(task_id)
    if task is None:
        existing = get_task(task_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Task not found')
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Only RUNNING/FAILED/PENDING tasks can be terminated',
        )
    return TaskResponse.from_db_row(task)


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
    market_data_configured = bool(_get_mairui_licence())
    board_counts = _load_stock_list_board_counts()

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
        market_data_configured=market_data_configured,
        daily_quote_cutoff_time=daily_quote_cutoff_time,
        board_counts=board_counts,
    )


# ---------------------------------------------------------------------------
# Supplemental endpoints
# ---------------------------------------------------------------------------


@router.get('/status', response_model=InitStatusResponse)
def get_init_status() -> InitStatusResponse:
    """Return the current initialization status."""
    return InitStatusResponse(**read_init_status())


@router.post('/update', response_model=UpdateResult)
def daily_update() -> UpdateResult:
    """Trigger an incremental update for today's market data."""
    result = run_daily_update()
    return UpdateResult(**result)


@router.get('/overview', response_model=InitOverviewResponse)
def get_init_overview() -> InitOverviewResponse:
    """Return a lightweight overview of the initialization state for the homepage."""
    market_data_configured = bool(_get_mairui_licence())
    board_counts = _load_stock_list_board_counts()

    v2 = get_overview()
    # Determine init_completed from V2 task system
    init_completed = (
        (v2.get('latest_task') or {}).get('status') == 'SUCCESS'
    )
    data_range = v2.get('data_range', {})

    cst = ZoneInfo('Asia/Shanghai')
    now_cst = datetime.now(cst)
    cutoff_cst = now_cst.replace(hour=15, minute=30, second=0, microsecond=0)
    daily_quote_cutoff_time = cutoff_cst.isoformat()

    return InitOverviewResponse(
        init_completed=init_completed,
        market_data_configured=market_data_configured,
        daily_quote_cutoff_time=daily_quote_cutoff_time,
        market_data_start_date=data_range.get('min_trade_date'),
        market_data_end_date=data_range.get('max_trade_date'),
        market_data_trading_day_count=data_range.get('trading_day_count', 0),
        board_counts=board_counts,
    )
