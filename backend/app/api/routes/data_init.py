from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.modules.market_data.initializer import read_init_status, start_initialization
from app.modules.market_data.updater import run_daily_update
from app.schemas.data_init import InitStatusResponse, StartInitRequest, UpdateResult

router = APIRouter()


@router.post('/start', response_model=InitStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def start_init(body: StartInitRequest) -> InitStatusResponse:
    """
    Start a full market data initialization in the background.

    Returns 202 if started, 409 if an initialization is already running.
    """
    started = start_initialization(history_days=body.history_days)
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
def daily_update(background_tasks: BackgroundTasks) -> UpdateResult:
    """
    Trigger an incremental update for today's market data.

    The update runs synchronously and returns the result.
    For large markets this may take a few minutes.
    """
    result = run_daily_update()
    return UpdateResult(**result)
