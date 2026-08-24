from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.lifespan import combine_lifespans

from app.api.router import api_router
from app.database.migrations import migrate_legacy_tags, migrate_legacy_watchlists, migrate_stock_tag_order, sync_tagged_stocks_to_watchlist
from app.database.session import Base, SessionLocal, engine
from app.market_data.provider import close_process_market_provider, get_process_market_provider
from app.mcp_server import mcp_app
from app.tasks.migrations import migrate_task_tables
from app.tasks.handlers.production import register_production_handlers
from app.tasks.process import start_worker_process
from app.tasks.service import next_pending_task


register_production_handlers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_legacy_watchlists(engine)
    migrate_legacy_tags(engine)
    migrate_stock_tag_order(engine)
    migrate_task_tables(engine)
    Base.metadata.create_all(engine)
    sync_tagged_stocks_to_watchlist(engine)
    with SessionLocal() as session:
        if next_pending_task(session) is not None:
            start_worker_process()
    yield
    close_process_market_provider()


app = FastAPI(
    title="AlphaPredator",
    version="0.1.0",
    lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
)
app.state.market_provider = get_process_market_provider()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.mount("/api/mcp", mcp_app)


def main() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, workers=1, reload=True)


if __name__ == "__main__":
    main()
