"""N0 (ADR-F049) — the AsyncPostgresStore setup posture, against a throwaway DB.

Codifies what was verified by hand on a throwaway pgvector container this slice:
``store.setup()`` with NO index config creates only the base ``store`` +
``store_migrations`` tables (no pgvector ``store_vectors`` — filter-only is safe;
a later semantic-index slice adds it non-destructively), is idempotent (safe to
call on every boot, like the checkpointer), and round-trips. Runs against the
conftest ``test_db_url`` throwaway (``lq_ai_test_*``) — NEVER the live dev DB
(CLAUDE.md hard rule); skips when ``DATABASE_URL`` is unset.
"""

from __future__ import annotations

from app.agents.checkpointer import _psycopg_dsn


async def test_store_setup_is_filter_only_idempotent_and_round_trips(test_db_url: str) -> None:
    from langgraph.store.postgres.aio import AsyncPostgresStore
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(
        _psycopg_dsn(test_db_url),
        open=False,
        min_size=1,
        max_size=2,
        # autocommit is mandatory: setup() runs CREATE INDEX CONCURRENTLY.
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    )
    await pool.open()
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

        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name IN ('store', 'store_migrations', 'store_vectors')"
            )
            tables = {row["table_name"] for row in await cur.fetchall()}
        assert "store" in tables
        assert "store_migrations" in tables
        # No IndexConfig at N0 → no pgvector table (filter-only).
        assert "store_vectors" not in tables
    finally:
        await pool.close()
