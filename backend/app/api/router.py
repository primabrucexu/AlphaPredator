from fastapi import APIRouter

from app.jygs.routes import router as jygs_router
from app.market_data.routes import router as market_data_router
from app.tasks.routes import router as tasks_router
from app.watchlist.routes import router as watchlist_router

from .health import router as health_router


api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(market_data_router)
api_router.include_router(watchlist_router)
api_router.include_router(jygs_router)
api_router.include_router(tasks_router)
