from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.settings import settings
from app.db.duckdb import ensure_duckdb_parent, ensure_duckdb_schema
from app.db.sqlite import ensure_sqlite_parent, ensure_sqlite_schema


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_sqlite_parent()
    ensure_sqlite_schema()
    ensure_duckdb_parent()
    ensure_duckdb_schema()
    yield


app = FastAPI(
    title='AlphaPredator API',
    version='0.1.0',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(api_router, prefix='/api')


@app.get('/')
def root() -> dict[str, str]:
    return {'name': 'AlphaPredator API', 'version': '0.1.0'}
