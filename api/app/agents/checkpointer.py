"""Durable agent state — the langgraph Postgres checkpointer (F0-S5, ADR-F008).

One process-global :class:`AsyncPostgresSaver` over its own psycopg
connection pool, living in the Postgres we already operate. The saver is
keyed by ``configurable.thread_id = str(agent_threads.id)`` — one
checkpoint lineage per conversation. Its tables are created and
versioned by the library's ``setup()`` (it keeps an internal migrations
table and is idempotent); they are deliberately NOT alembic-managed —
alembic owns OUR schema, the library owns its own.

Lifecycle mirrors :mod:`app.db.session`: built once, opened/closed from
the lifespan (the composition root — CLAUDE.md DI rules). Startup
failure is degraded service, not a crash (the lifespan's house
philosophy): :func:`get_agent_checkpointer` then returns ``None``, new
runs execute WITHOUT persistence (single-shot, exactly the F0-S4
behavior), and follow-ups are refused because the continuability check
requires existing checkpoint state (ADR-F008) — degradation is honest,
never silent context loss.

Consumers receive the saver through seams (``checkpointer_provider`` on
:func:`app.agents.composition.compose_and_execute_run`; FastAPI dependency
on the thread endpoints) —
tests substitute :class:`langgraph.checkpoint.memory.InMemorySaver`
through the same seams, no monkeypatching.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, cast

from langchain_core.runnables import RunnableConfig

from app.config import get_settings

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

log = logging.getLogger(__name__)

_saver: Any | None = None
_pool: Any | None = None


def _psycopg_dsn(database_url: str) -> str:
    """The SQLAlchemy URL (``postgresql+asyncpg://``) as a psycopg DSN.

    The checkpointer's pool speaks psycopg3 directly — same database,
    different driver — so the ``+asyncpg`` dialect marker must go.
    """
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def init_agent_checkpointer() -> None:
    """Open the pool, build the saver, run the library's ``setup()``.

    Called once from the lifespan. Failures are logged and leave the
    saver unset (degraded: no multi-turn persistence) — the api must
    come up even when this fails, matching the lifespan's best-effort
    startup posture.
    """
    global _saver, _pool
    if _saver is not None:
        return
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            _psycopg_dsn(get_settings().database_url),
            open=False,
            min_size=1,
            max_size=4,
            # Revalidate pooled connections before handing them out — the
            # dev stack's postgres crash-recovery cycles (HANDOFF gotcha)
            # otherwise wedge stale sockets into the pool forever.
            check=AsyncConnectionPool.check_connection,
            # AsyncPostgresSaver's documented connection requirements.
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        )
        await pool.open()
        try:
            # The kwargs above make every pooled connection produce dict
            # rows; the pool's generic parameter can't see that, so
            # assert it here.
            saver = AsyncPostgresSaver(
                cast("AsyncConnectionPool[AsyncConnection[dict[str, Any]]]", pool)
            )
            await saver.setup()
        except BaseException:
            # Don't leak an opened pool when setup fails (F0-S5 review).
            await pool.close()
            raise
        _pool, _saver = pool, saver
        log.info("agent checkpointer ready (AsyncPostgresSaver)")
    except Exception:
        log.exception(
            "agent checkpointer init failed — multi-turn persistence DISABLED "
            "(new runs execute single-shot; follow-ups will be refused)"
        )


async def close_agent_checkpointer() -> None:
    """Close the pool on shutdown (best-effort, lifespan finally-block)."""
    global _saver, _pool
    pool = _pool
    _saver, _pool = None, None
    if pool is not None:
        await pool.close()


def get_agent_checkpointer() -> BaseCheckpointSaver | None:
    """The process-global saver, or ``None`` when init failed/skipped."""
    return _saver


def thread_config(thread_id: uuid.UUID) -> RunnableConfig:
    """The runnable config addressing one conversation's checkpoint state."""
    return {"configurable": {"thread_id": str(thread_id)}}


async def has_checkpoint(checkpointer: BaseCheckpointSaver | None, thread_id: uuid.UUID) -> bool:
    """True when durable state exists for the thread (ADR-F008).

    Follow-ups REQUIRE this: a thread without checkpoint state (pre-S5
    backfill, or a run executed while persistence was degraded) cannot
    honestly continue — the agent would not remember the conversation it
    claims to be continuing.
    """
    if checkpointer is None:
        return False
    return await checkpointer.aget_tuple(thread_config(thread_id)) is not None
