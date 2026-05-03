from fastapi import APIRouter, HTTPException, UploadFile, status

from app.core.settings import settings
from app.modules.market_data.initializer import read_init_status, start_initialization
from app.modules.market_data.updater import run_daily_update
from app.schemas.data_init import (
    InitStatusResponse,
    SaveTokenRequest,
    StartInitRequest,
    StockListUploadResponse,
    TokenConfigResponse,
    UpdateResult,
)

router = APIRouter()


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
    import io

    import pandas as pd

    from app.modules.market_data.data_source import _REQUIRED_STOCK_LIST_COLS

    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Only CSV files are accepted.',
        )

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents), dtype=str)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f'Failed to parse CSV: {exc}',
        ) from exc

    missing = _REQUIRED_STOCK_LIST_COLS - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f'CSV is missing required columns: {sorted(missing)}',
        )

    # Persist to configured path
    dest = settings.stock_list_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(contents)

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
