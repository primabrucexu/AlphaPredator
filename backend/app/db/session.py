from collections.abc import Generator
from pathlib import Path

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.db.sqlite import get_sqlite_engine


def get_sqlite_session_factory(sqlite_path: Path | None = None) -> sessionmaker:
    """Create a Session factory bound to the configured SQLite engine."""
    engine = get_sqlite_engine(sqlite_path)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_sqlite_session(sqlite_path: Path | None = None) -> Generator[Session, None, None]:
    """FastAPI-friendly dependency generator for SQLite sessions."""
    session_factory = get_sqlite_session_factory(sqlite_path)
    with session_factory() as session:
        yield session
