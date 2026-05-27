from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _ensure_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    database_path = database_url.replace("sqlite:///", "", 1)
    if database_path == ":memory:":
        return

    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_directory(settings.database_url)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
