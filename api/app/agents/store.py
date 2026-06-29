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
- its tables (``store``, ``store_migrations`` and — since Slice C2 — the pgvector
  ``store_vectors`` + ``vector_migrations``) are created and versioned by the
  library's idempotent ``setup()`` — deliberately NOT alembic-managed (alembic
  owns OUR schema, the library owns its own; the checkpointer's stance, ADR-F008);
- the pool MUST be ``autocommit`` — ``setup()``'s base migration runs
  ``CREATE INDEX CONCURRENTLY``, which Postgres forbids inside a transaction;
- **semantic index since Slice C2** (ADR-F049): an :class:`IndexConfig` over the
  Slice-C1 :class:`EmbeddingProvider` (local door, 768-dim, $0) makes
  ``store.asearch(query=…)`` rank by cosine similarity — lighting up cross-thread
  conversation recall (N3) and memory-tier semantic search. ``setup()`` builds the
  pgvector ``store_vectors`` table non-destructively (N0 left it absent). Embedding is
  SYMMETRIC: :func:`build_store_index_config` passes a plain async embed callable, and
  ``langgraph`` wraps it (``ensure_embeddings``) so ``aembed_query`` routes to the SAME
  function as ``aembed_documents`` — so bge's query-instruction asymmetry (the C1
  *document* path) does not apply here regardless of which method a store calls (the
  AsyncPostgresStore in fact embeds the query via ``aembed_documents``; verified
  in-container);
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
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from app.agents.checkpointer import _psycopg_dsn
from app.config import get_settings
from app.knowledge.embedding_provider import EmbeddingProvider, get_embedding_provider

if TYPE_CHECKING:
    from langgraph.store.base import BaseStore, IndexConfig
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

log = logging.getLogger(__name__)

_store: Any | None = None
_store_pool: Any | None = None

# The single JSON value field the Store embeds — every memory/conversation write
# goes through deepagents' StoreBackend, which puts ``{"content": <text>, …}``; we
# embed only that field (NOT created_at/encoding) so the vector is the text itself.
_INDEX_FIELD = "content"


def build_store_index_config(provider: EmbeddingProvider) -> IndexConfig:
    """The Store's semantic-index config over an :class:`EmbeddingProvider` (Slice C2).

    Shared by BOTH composition roots (via :func:`init_agent_store`, production
    ``AsyncPostgresStore``) AND tests (which build an ``InMemoryStore`` through the
    same helper) — so the index the tests exercise is byte-identical to production's.

    The embed callable is a plain async ``AEmbeddingsFunc``. ``langgraph`` wraps it via
    ``ensure_embeddings`` into an ``EmbeddingsLambda`` whose ``aembed_query`` and
    ``aembed_documents`` BOTH route to this same function (``(await afunc([text]))[0]``
    for the query) — so embedding is symmetric (passage-mode for both sides) no matter
    which method a store calls, and there is no query/passage split to honor. (bge's
    query-instruction asymmetry is the C1 *document* path; it is intentionally not
    applied to the Store. The AsyncPostgresStore in fact embeds the query via
    ``aembed_documents``; the InMemoryStore via ``aembed_query`` — both land here.)
    """

    async def _embed(texts: Sequence[str]) -> list[list[float]]:
        return await provider.embed(list(texts))

    return {"dims": provider.dim, "embed": _embed, "fields": [_INDEX_FIELD]}


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
            # IndexConfig over the local embedding provider (Slice C2): setup()
            # creates the base `store`/`store_migrations` AND the pgvector
            # `store_vectors`/`vector_migrations` tables, enabling semantic asearch.
            # Resolving the provider here does NOT load the model (lazy on first
            # embed) — startup stays cheap; the local door is $0/no-key.
            index_config = build_store_index_config(get_embedding_provider())
            store = AsyncPostgresStore(
                cast("AsyncConnectionPool[AsyncConnection[dict[str, Any]]]", pool),
                # AsyncPostgresStore types ``index`` as PostgresIndexConfig — a total=False
                # superset of our IndexConfig (it adds optional ann_index_config/distance);
                # the base dict is not statically assignable, so bridge the variance gap.
                index=cast("Any", index_config),
            )
            await store.setup()
        except BaseException:
            # Don't leak an opened pool when setup fails (checkpointer parity).
            await pool.close()
            raise
        _store_pool, _store = pool, store
        log.info("agent memory store ready (AsyncPostgresStore, semantic index)")
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
