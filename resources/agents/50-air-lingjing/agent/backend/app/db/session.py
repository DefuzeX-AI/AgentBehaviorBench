"""Database engines and request-scoped session management.

The application uses two database connections:

- `DATABASE_URL` for relatively stable business tables.
- `STREAM_DATABASE_URL` for high-frequency realtime `sim_data`.

Both URLs are SQLite by default and deployment is designed around SQLite only.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for main business database models."""

    pass


class StreamBase(DeclarativeBase):
    """Base class for realtime/stream database models."""

    pass


def _connect_args(database_url: str) -> dict[str, object]:
    """Return driver-specific connection options."""

    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _ensure_sqlite_parent(database_url: str) -> None:
    """Create the parent folder for file-based SQLite URLs."""

    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        return
    sqlite_path = database_url.removeprefix("sqlite:///")
    if sqlite_path and sqlite_path != ":memory:":
        Path(sqlite_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


settings = get_settings()
_ensure_sqlite_parent(settings.database_url)
_ensure_sqlite_parent(settings.stream_database_url)
engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

stream_engine = create_engine(
    settings.stream_database_url,
    echo=settings.database_echo,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args(settings.stream_database_url),
)
StreamSessionLocal = sessionmaker(
    bind=stream_engine,
    autoflush=False,
    autocommit=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for the main business database."""

    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_stream_db() -> Generator[Session, None, None]:
    """FastAPI dependency for realtime/stream data stored outside the main DB."""

    db = StreamSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all_for_local_dev() -> None:
    """Create SQLite tables for both business and stream databases."""

    from app.db import models  # noqa: F401

    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
    if settings.stream_database_url.startswith("sqlite"):
        StreamBase.metadata.create_all(bind=stream_engine)
