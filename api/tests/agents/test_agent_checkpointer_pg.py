"""The REAL Postgres checkpointer wiring — F0-S5 (ADR-F008).

The multi-turn semantics are proven against ``InMemorySaver`` in
``test_agent_composition.py``; what that cannot prove is OUR wiring of
``AsyncPostgresSaver``: the DSN conversion, the pool's connection kwargs
(autocommit / dict_row / prepare_threshold), the idempotent ``setup()``,
and that a follow-up run restores state that crossed a real Postgres
round trip. These tests drive exactly that against the test database.

Requires the ``psycopg[binary]`` runtime (pyproject F0-S5) — skipped
with a clear message when the libpq implementation is absent (an image
built before the dependency landed).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.checkpointer import _psycopg_dsn, has_checkpoint
from app.agents.composition import compose_and_execute_run
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.user import User
from app.security import hash_password
from tests.agents.fakes import ScriptedToolCallingModel, final_message

pytest.importorskip(
    "psycopg_pool", reason="psycopg[binary] runtime not installed (pre-F0-S5 image)"
)
try:  # psycopg imports but cannot operate without a libpq implementation
    from psycopg import pq  # noqa: F401
except ImportError:  # pragma: no cover - environment-dependent
    pytest.skip("psycopg has no libpq implementation", allow_module_level=True)

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from tests.agents.test_agent_composition import CapturingBuilder

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest_asyncio.fixture
async def pg_saver(test_db_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    """AsyncPostgresSaver against the test DB — the production wiring."""
    pool: AsyncConnectionPool = AsyncConnectionPool(
        _psycopg_dsn(test_db_url),
        open=False,
        min_size=1,
        max_size=2,
        check=AsyncConnectionPool.check_connection,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    await saver.setup()  # idempotent — its own migrations table (ADR-F008)
    try:
        yield saver
    finally:
        await pool.close()


def test_psycopg_dsn_strips_the_asyncpg_dialect() -> None:
    assert (
        _psycopg_dsn("postgresql+asyncpg://u:p@host:5432/db")
        == "postgresql://u:p@host:5432/db"
    )
    # Already-plain DSNs pass through untouched.
    assert _psycopg_dsn("postgresql://u:p@host/db") == "postgresql://u:p@host/db"


async def test_has_checkpoint_false_for_unknown_thread(
    pg_saver: AsyncPostgresSaver,
) -> None:
    assert await has_checkpoint(pg_saver, uuid.uuid4()) is False
    assert await has_checkpoint(None, uuid.uuid4()) is False  # degraded mode


async def test_follow_up_restores_state_through_postgres(
    pg_saver: AsyncPostgresSaver, test_engine: AsyncEngine
) -> None:
    """End to end on the REAL saver: run 1 persists the conversation,
    run 2 (a fresh agent build) sees it after a Postgres round trip."""
    factory = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as db:
        user = User(
            email=f"agent-pg-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Checkpointer PG User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        thread = AgentThread(user_id=user.id, title="pg multi-turn")
        db.add(thread)
        await db.commit()
        user_id, thread_id = user.id, thread.id

    async def make_run(prompt: str) -> uuid.UUID:
        async with factory() as db:
            run = AgentRun(
                user_id=user_id,
                thread_id=thread_id,
                status="running",
                prompt=prompt,
                model_alias="smart",
                max_steps=20,
            )
            db.add(run)
            await db.commit()
            return run.id

    try:
        run1 = await make_run("Remember: the password is swordfish.")
        await compose_and_execute_run(
            run_id=run1,
            model_builder=CapturingBuilder(
                model=ScriptedToolCallingModel(responses=[final_message("Noted.")])
            ),
            session_factory_provider=lambda: factory,
            checkpointer_provider=lambda: pg_saver,
        )
        assert await has_checkpoint(pg_saver, thread_id) is True

        second_model = ScriptedToolCallingModel(responses=[final_message("swordfish")])
        run2 = await make_run("What was the password?")
        await compose_and_execute_run(
            run_id=run2,
            model_builder=CapturingBuilder(model=second_model),
            session_factory_provider=lambda: factory,
            checkpointer_provider=lambda: pg_saver,
        )

        async with factory() as db:
            statuses = (
                (
                    await db.execute(
                        select(AgentRun.status).where(AgentRun.thread_id == thread_id)
                    )
                )
                .scalars()
                .all()
            )
        assert statuses == ["completed", "completed"]
        joined = "\n".join(str(m.content) for m in second_model.seen_messages[0])
        assert "the password is swordfish" in joined  # state crossed Postgres
    finally:
        # F1-S1 review fix: also delete the checkpoint lineage — leaking
        # it couples the GC test below to this test's leftovers.
        await pg_saver.adelete_thread(str(thread_id))
        async with factory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
            await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


async def test_checkpoint_gc_deletes_only_orphaned_lineages(
    pg_saver: AsyncPostgresSaver, test_engine: AsyncEngine
) -> None:
    """F1-S1 retention: a lineage whose agent_threads row is gone (user
    cascade, failed best-effort delete) is removed through the saver's
    own API; a LIVE thread's lineage is untouched."""
    from langgraph.checkpoint.base import empty_checkpoint

    from app.workers.agent_run_worker import run_checkpoint_gc

    factory = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, class_=AsyncSession
    )
    orphan_thread_id = str(uuid.uuid4())
    orphan_config = {
        "configurable": {"thread_id": orphan_thread_id, "checkpoint_ns": ""}
    }
    await pg_saver.aput(orphan_config, empty_checkpoint(), {}, {})

    async with factory() as db:
        user = User(
            email=f"agent-gc-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Checkpoint GC User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        thread = AgentThread(user_id=user.id, title="gc live thread")
        db.add(thread)
        await db.commit()
        user_id, live_thread_id = user.id, thread.id
    live_config = {
        "configurable": {"thread_id": str(live_thread_id), "checkpoint_ns": ""}
    }
    await pg_saver.aput(live_config, empty_checkpoint(), {}, {})

    try:
        result = await run_checkpoint_gc(factory, pg_saver)
        assert result["skipped"] is False
        assert result["deleted_threads"] == 1  # exactly OUR orphan
        assert await pg_saver.aget_tuple(orphan_config) is None
        assert await pg_saver.aget_tuple(live_config) is not None
    finally:
        # Idempotent — safe after GC already removed it; keeps an
        # assertion failure from stranding the orphan for the session.
        await pg_saver.adelete_thread(orphan_thread_id)
        await pg_saver.adelete_thread(str(live_thread_id))
        async with factory() as db:
            await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


async def test_checkpoint_gc_skips_when_degraded() -> None:
    """No checkpointer (init failed) → honest skip, never a crash."""
    from app.workers.agent_run_worker import run_checkpoint_gc

    result = await run_checkpoint_gc(None, None)  # factory unused when skipped
    assert result == {"deleted_threads": 0, "skipped": True}
