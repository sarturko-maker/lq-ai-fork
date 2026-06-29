"""N0 + Slice C2 (ADR-F049) — the AsyncPostgresStore setup posture, against a throwaway DB.

Codifies what was verified by hand on a throwaway pgvector container:

* **No index (N0 / degraded path):** ``store.setup()`` with NO index config creates only
  the base ``store`` + ``store_migrations`` tables (no pgvector ``store_vectors``), is
  idempotent (safe on every boot, like the checkpointer), and round-trips.
* **Indexed (Slice C2 / production path):** ``setup()`` WITH an :class:`IndexConfig`
  (:func:`app.agents.store.build_store_index_config` over the embedding provider) ALSO
  builds the pgvector ``store_vectors`` table — non-destructively (it was absent at N0) —
  and ``asearch(query=…)`` ranks items by cosine on real pgvector, the paraphrase-recall
  win N3's tool consumes.

Runs against the conftest ``test_db_url`` throwaway (``lq_ai_test_*``) — NEVER the live dev
DB (CLAUDE.md hard rule); skips when ``DATABASE_URL`` is unset. Hermetic: the indexed test
uses a deterministic concept embedder (no model download).
"""

from __future__ import annotations

from app.agents.checkpointer import _psycopg_dsn
from app.agents.store import build_store_index_config
from tests.agents.embedding_fakes import ConceptEmbeddingProvider


def _pool(test_db_url: str) -> object:
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    return AsyncConnectionPool(
        _psycopg_dsn(test_db_url),
        open=False,
        min_size=1,
        max_size=2,
        # autocommit is mandatory: setup() runs CREATE INDEX CONCURRENTLY.
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    )


async def _tables(pool: object) -> set[str]:
    async with pool.connection() as conn:  # type: ignore[attr-defined]
        cur = await conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('store', 'store_migrations', 'store_vectors')"
        )
        return {row["table_name"] for row in await cur.fetchall()}


async def test_store_setup_is_filter_only_idempotent_and_round_trips(test_db_url: str) -> None:
    from langgraph.store.postgres.aio import AsyncPostgresStore

    pool = _pool(test_db_url)
    await pool.open()  # type: ignore[attr-defined]
    try:
        store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
        await store.setup()
        await store.setup()  # idempotent — second call is a no-op

        # Cross-thread persistence is namespace-keyed, thread-independent:
        # a put under one namespace is gettable by anyone resolving the same one.
        await store.aput(("matter", "p1"), "/note.md", {"content": "hi"})
        got = await store.aget(("matter", "p1"), "/note.md")
        assert got is not None
        assert got.value["content"] == "hi"
        # A different matter namespace is isolated.
        assert await store.aget(("matter", "p2"), "/note.md") is None

        tables = await _tables(pool)
        assert "store" in tables
        assert "store_migrations" in tables
        # No IndexConfig → no pgvector table (the degraded / filter-only path).
        assert "store_vectors" not in tables
    finally:
        await pool.close()  # type: ignore[attr-defined]


async def test_store_setup_with_index_creates_pgvector_and_ranks(test_db_url: str) -> None:
    """Slice C2 production posture: an IndexConfig makes setup() build ``store_vectors`` and
    ``asearch(query=)`` rank by cosine on real pgvector (a paraphrase outranks an off-topic)."""
    from langgraph.store.postgres.aio import AsyncPostgresStore

    pool = _pool(test_db_url)
    await pool.open()  # type: ignore[attr-defined]
    try:
        cfg = build_store_index_config(ConceptEmbeddingProvider())
        store = AsyncPostgresStore(pool, index=cfg)  # type: ignore[arg-type]
        await store.setup()

        await store.aput(("conversation", "t1"), "/a.md", {"content": "from our Manchester office"})
        await store.aput(
            ("conversation", "t2"), "/b.md", {"content": "the fee cap is four percent"}
        )

        # "northern premises" shares NO word with t1, but maps to the same concept → ranks high;
        # t2 (a different concept) stays below the semantic floor → honest separation.
        loc = await store.asearch(("conversation", "t1"), query="northern premises", limit=5)
        fee = await store.asearch(("conversation", "t2"), query="northern premises", limit=5)
        assert loc and loc[0].score is not None and loc[0].score >= 0.6
        assert fee and fee[0].score is not None and fee[0].score < 0.6

        # The pgvector table now exists (non-destructive add over the N0 base tables).
        assert "store_vectors" in await _tables(pool)
    finally:
        await pool.close()  # type: ignore[attr-defined]


async def test_indexed_query_drops_pre_index_rows_but_queryless_read_recovers(
    test_db_url: str,
) -> None:
    """Slice C2 regression guard: a row written BEFORE the index existed has NO store_vectors
    row, so the indexed ``query=`` search INNER-JOINs it away — but a query-LESS read still
    returns it. This is WHY ``_read_thread_transcript`` reads the transcript content WITHOUT a
    query (so pre-C2 conversation history stays findable via the lexical scan once the index
    lands); searching the content with ``query=`` would silently regress N3 recall."""
    from langgraph.store.postgres.aio import AsyncPostgresStore

    ns = ("conversation", "pre")
    # 1) Write the row with NO index (the N0-N3 era posture: no store_vectors row written).
    pool = _pool(test_db_url)
    await pool.open()  # type: ignore[attr-defined]
    try:
        plain = AsyncPostgresStore(pool)  # type: ignore[arg-type]
        await plain.setup()
        await plain.aput(ns, "/a.md", {"content": "from our Manchester office"})
    finally:
        await pool.close()  # type: ignore[attr-defined]

    # 2) Reopen the SAME DB WITH the index (the post-C2 boot: setup() adds store_vectors).
    pool2 = _pool(test_db_url)
    await pool2.open()  # type: ignore[attr-defined]
    try:
        cfg = build_store_index_config(ConceptEmbeddingProvider())
        indexed = AsyncPostgresStore(pool2, index=cfg)  # type: ignore[arg-type]
        await indexed.setup()

        # The query= path INNER-JOINs store_vectors → the un-embedded pre-index row is DROPPED.
        assert await indexed.asearch(ns, query="northern premises", limit=8) == []
        # But the query-LESS read (the content path) still returns it → recall preserved.
        items = await indexed.asearch(ns, limit=8)
        assert items and items[0].value["content"] == "from our Manchester office"
    finally:
        await pool2.close()  # type: ignore[attr-defined]
