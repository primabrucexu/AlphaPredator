from fastapi import APIRouter

from app.api.routes.data_init import router as data_init_router
from app.api.routes.health import router as health_router
from app.api.routes.jygs import router as jygs_router
from app.api.routes.market import router as market_router
from app.api.routes.trade_review import router as trade_review_router

api_router = APIRouter()
api_router.include_router(health_router, prefix='/health', tags=['health'])
api_router.include_router(market_router, prefix='/market', tags=['market'])
api_router.include_router(data_init_router, prefix='/data-init', tags=['data-init'])
api_router.include_router(jygs_router, prefix='/jygs', tags=['韭研公社'])
api_router.include_router(trade_review_router, prefix='/trade-reviews', tags=['交易复盘'])
