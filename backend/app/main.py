from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.api.routes.mcp import mcp as mcp_server
from app.core.logging import configure_logging
from app.core.settings import settings
from app.db.duckdb_storage import ensure_duckdb_parent, ensure_duckdb_schema
from app.db.sqlite import ensure_sqlite_parent, ensure_sqlite_schema

# Apply one logging config so app and uvicorn logs are visible in console.
configure_logging()

mcp_app = mcp_server.http_app(path='/')


def _ensure_localhost_binding() -> None:
    if settings.app_host in {'0.0.0.0', '::'}:
        raise RuntimeError('MCP service is unauthenticated and must bind to 127.0.0.1 or localhost')


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_localhost_binding()
    ensure_sqlite_parent()
    ensure_sqlite_schema()
    ensure_duckdb_parent()
    ensure_duckdb_schema()
    async with mcp_app.lifespan(_):
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
app.mount('/api/mcp', mcp_app)


@app.get('/')
def root() -> dict[str, str]:
    return {'name': 'AlphaPredator API', 'version': '0.1.0'}


def main() -> None:
    uvicorn.run('app.main:app', host=settings.app_host, port=settings.app_port, reload=True, log_config=None)


if __name__ == '__main__':
    main()
