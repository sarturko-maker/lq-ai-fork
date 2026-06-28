"""Native memory substrate — the langgraph Postgres :class:`Store` (F2 N0, ADR-F049).

The four-level memory model (CLAUDE.md: company / practice / user / matter)
runs on the framework's own memory tier — a langgraph ``BaseStore`` reached
through a deepagents ``CompositeBackend`` (see :mod:`app.agents.memory_backend`).
This module owns the store instance, exactly mirroring
:mod:`app.agents.checkpointer`:

- one process-global :class:`AsyncPostgresStore` over its **own** psycopg
  connection pool, in the Postgres we already operate (same DB, psycopg3
  driver — so the ``+asyncpg`` dialect marker is stripped via the
  checkpointer's :func:`_psycopg_dsn`);
- its tables (``store``, ``store_migrations``) are created and versioned by
  the library's idempotent ``setup()`` — deliberately NOT alembic-managed
  (alembic owns OUR schema, the library owns its own; the checkpointer's
  stance, ADR-F008);
- the pool MUST be ``autocommit`` — ``setup()``'s base migration runs
  ``CREATE INDEX CONCURRENTLY``, which Postgres forbids inside a transaction;
- **no ``IndexConfig`` at N0** — filter-only. ``setup()`` then creates only the
  base table (no pgvector ``store_vectors``); a later semantic-index slice
  (Slice C) adds the index non-destructively;
- built once, opened/closed from BOTH composition roots that execute runs —
  the FastAPI lifespan (the api) AND the arq worker on_startup (where runs
  actually run). Startup failure is degraded service, never a crash: the
  store stays unset, :func:`get_agent_store` returns ``None``, and the memory
  backend degrades to the non-persistent default (the lifespan's house
  philosophy, mirroring the checkpointer).

Consumers receive the store through a seam (``store_provider`` on
:func:`app.agents.composition.compose_and_execute_run`); tests substitute
:class:`langgraph.store.memory.InMemoryStore` through the same seam, no
monkeypatching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from app.agents.checkpointer import _psycopg_dsn
from app.config import get_settings

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

log = logging.getLogger(__name__)

_store: Any | None = None
_store_pool: Any | None = None


async def init_agent_store() -> None:
    """Open the pool, build the store, run the library's ``setup()``.

    Called once from each composition root (api lifespan + arq worker
    startup). Failures are logged and leave the store unset (degraded: the
    memory backend falls back to the non-persistent default backend) — the
    process must come up even when this fails, matching the checkpointer's
    best-effort startup posture.
    """
    global _store, _store_pool
    if _store is not None:
        return
    try:
        from langgraph.store.postgres.aio import AsyncPostgresStore
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            _psycopg_dsn(get_settings().database_url),
            open=False,
            min_size=1,
            max_size=4,
            # Revalidate pooled connections before handing them out — the dev
            # stack's postgres crash-recovery cycles otherwise wedge stale
            # sockets into the pool forever (the checkpointer's hard-won fix).
            check=AsyncConnectionPool.check_connection,
            # autocommit is MANDATORY: setup()'s base migration runs
            # CREATE INDEX CONCURRENTLY, which cannot run in a transaction.
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        )
        await pool.open()
        try:
            # No IndexConfig → filter-only (N0): setup() creates the base
            # `store` + `store_migrations` tables only, no pgvector column.
            store = AsyncPostgresStore(
                cast("AsyncConnectionPool[AsyncConnection[dict[str, Any]]]", pool)
            )
            await store.setup()
        except BaseException:
            # Don't leak an opened pool when setup fails (checkpointer parity).
            await pool.close()
            raise
        _store_pool, _store = pool, store
        log.info("agent memory store ready (AsyncPostgresStore, filter-only)")
    except Exception:
        log.exception(
            "agent memory store init failed — native memory substrate DISABLED "
            "(runs execute without the /memories backend; the prompt-injection "
            "memory tiers are unaffected)"
        )


async def close_agent_store() -> None:
    """Close the pool on shutdown (best-effort, lifespan finally-block)."""
    global _store, _store_pool
    pool = _store_pool
    _store, _store_pool = None, None
    if pool is not None:
        await pool.close()


def get_agent_store() -> BaseStore | None:
    """The process-global store, or ``None`` when init failed/skipped."""
    return _store
