from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api.router import api_router
from app.database.models import WatchlistGroup
from app.database.session import Base, SessionLocal, engine
from app.market_data.provider import ThsdkMarketDataProvider


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(WatchlistGroup).where(WatchlistGroup.is_default.is_(True))):
            db.add(WatchlistGroup(name="默认分组", is_default=True))
            db.commit()
    yield
    app.state.market_provider.close()


app = FastAPI(title="AlphaPredator", version="0.1.0", lifespan=lifespan)
app.state.market_provider = ThsdkMarketDataProvider()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


def main() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, workers=1)


if __name__ == "__main__":
    main()
