"""SQLAlchemy 2.0 engine, session factory and FastAPI DB dependency.

Engine and session factory are created lazily so the API can start (and /health
can answer) even when DATABASE_URL is missing.
"""
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


class DatabaseNotConfiguredError(RuntimeError):
    """DATABASE_URL is empty. Subclasses RuntimeError for backward compatibility."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

# Supabase Supavisor transaction mode listens on 6543 and does not support
# server-side prepared statements; session mode (5432) does.
_TRANSACTION_POOLER_PORT = 6543


def _connect_args(url: str) -> dict:
    args: dict = {"connect_timeout": 10}
    if urlparse(url.replace("postgresql+psycopg", "postgresql")).port == _TRANSACTION_POOLER_PORT:
        args["prepare_threshold"] = None
    return args


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise DatabaseNotConfiguredError("DATABASE_URL is not configured")
        url = settings.sqlalchemy_url
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            connect_args=_connect_args(url),
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def dispose_engine() -> None:
    """Close pooled connections (application shutdown). Next use recreates the engine."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency. Callers commit explicitly; errors roll back."""
    db = get_session_factory()()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts/jobs: commit on success, rollback on error."""
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
