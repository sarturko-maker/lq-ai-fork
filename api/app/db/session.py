"""Async SQLAlchemy engine + session factory for the api/ service.

The engine is lazily constructed against `settings.database_url` so that
tests (which use the per-run database fixture in tests/conftest.py) can
override the URL via env before the engine is built.

Pattern follows the SQLAlchemy 2.0 async ORM docs:
  https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

`get_db()` is the FastAPI dependency that handlers use; it yields an
`AsyncSession` and closes it after the request.

`check_db()` is a lightweight readiness probe — it issues `SELECT 1` to
confirm the connection is live. Used by `/ready`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

log = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def get_engine() -> AsyncEngine:
    """Return the process-global async engine, building it on first call."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-global async-session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield an AsyncSession scoped to the request.

    Usage in a handler:
        async def handler(db: Annotated[AsyncSession, Depends(get_db)]): ...
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def check_db() -> bool:
    """Readiness check: returns True if the engine can issue `SELECT 1`."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        # Readiness probes never raise; report failure in the response body.
        log.warning("DB readiness check failed: %s", exc)
        return False


async def dispose_engine() -> None:
    """Dispose the engine on shutdown. Safe to call when no engine was built."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
