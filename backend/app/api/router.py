from fastapi import APIRouter

from app.api.routes.data_init import router as data_init_router
from app.api.routes.health import router as health_router
from app.api.routes.jygs import router as jygs_router
from app.api.routes.market import router as market_router

api_router = APIRouter()
api_router.include_router(health_router, prefix='/health', tags=['health'])
api_router.include_router(market_router, prefix='/market', tags=['market'])
api_router.include_router(data_init_router, prefix='/data-init', tags=['data-init'])
api_router.include_router(jygs_router, prefix='/jygs', tags=['韭研公社'])
