"""Async SQLAlchemy engine + session factory for the gateway service.

The gateway needs DB access only for the ``inference_routing_log`` writer
(B4); it is *not* a general-purpose ORM consumer. We deliberately use a
thin SQL-only API (``sqlalchemy.text`` + parameter binding) instead of
declarative models, so the gateway doesn't carry ORM definitions for
tables it doesn't own. The schema authority is ``api/`` (which holds the
Alembic migrations and ORM models); the gateway is a writer-only consumer
of one table.

The ``DATABASE_URL`` environment variable is read at first-use. When it
is unset (the typical state in pure-unit-test runs or in a degraded
deployment) the writer becomes a no-op — see
:class:`app.routing_log.NullRoutingLogWriter`. The gateway must not refuse
to serve traffic just because the audit log is unreachable; the route
handler logs a warning instead so operators see the gap.

Why a separate engine from ``api/``
-----------------------------------

Each subsystem is a self-contained service per CLAUDE.md. The gateway
maintains its own connection pool, sized for its inference workload
(short rows, frequent inserts), independent of api/'s longer-running
session patterns. Both pools point at the same database; pgbouncer (or
the operator's connection-pooling layer) is what eventually consolidates
them.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

logger = logging.getLogger(__name__)


__all__ = [
    "DATABASE_URL_ENV",
    "DatabaseUnavailable",
    "build_engine",
    "engine_or_none",
    "ping",
]


DATABASE_URL_ENV = "DATABASE_URL"
"""Environment variable consulted for the SQLAlchemy async URL.

Same name as ``api/`` for operator simplicity; one ``.env`` value covers
both subsystems. The gateway expects the ``postgresql+asyncpg://`` form
(matching what the migration runner uses)."""


class DatabaseUnavailable(RuntimeError):
    """Raised when a DB-required operation is requested but no engine exists.

    The gateway's data path doesn't *require* the DB — if the DB is not
    configured, routing still works; we just can't write the audit row.
    Code that needs the DB and only the DB (e.g., tests) raises this; the
    routing-log writer never raises it (it falls back to a no-op writer).
    """


def build_engine(database_url: str) -> AsyncEngine:
    """Build a fresh async engine pointed at ``database_url``.

    Uses small pool defaults appropriate for the gateway's workload —
    every inference request inserts one row, so the pool sizes track
    request concurrency, not long-lived sessions. Operators can tune via
    SQLAlchemy URL query parameters or env-var overrides without changing
    code.
    """

    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        future=True,
    )


def engine_or_none() -> AsyncEngine | None:
    """Return an engine if ``DATABASE_URL`` is set; otherwise ``None``.

    Callers (notably the lifespan) use the ``None`` case to wire the
    no-op writer rather than failing startup.
    """

    url = os.environ.get(DATABASE_URL_ENV)
    if not url:
        return None
    return build_engine(url)


async def ping(engine: AsyncEngine) -> bool:
    """Issue ``SELECT 1`` against ``engine``; return ``True`` on success."""

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("gateway DB ping failed: %s", exc)
        return False


@asynccontextmanager
async def acquire_connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """Yield an async connection from the engine's pool.

    Thin wrapper for symmetry with the rest of the codebase. The writer
    uses this to scope a transaction to a single inference request.
    """

    async with engine.connect() as conn, conn.begin():
        yield conn
