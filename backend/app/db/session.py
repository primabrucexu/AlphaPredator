from pathlib import Path

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.db.sqlite import get_sqlite_engine


def get_sqlite_session_factory(sqlite_path: Path | None = None) -> sessionmaker:
    """Create a Session factory bound to the configured SQLite engine."""
    engine = get_sqlite_engine(sqlite_path)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
