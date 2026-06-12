"""The run lease protocol — F1-S1 (ADR-F009).

Claim / heartbeat / fenced settlement against the real test database:
these are the writes that make at-most-once execution true, so every
test here is a race-semantics test — first writer wins, zombies are
rejected by rowcount, and nothing ever overwrites a terminal status.

Uses the runner tests' committed-rows pattern (``commit_factory`` +
cascade-delete teardown): the lease helpers open their OWN fresh
sessions from the factory, which the savepoint-bound ``db_session``
fixture cannot serve.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.lease import RunLease, claim_run, heartbeat_run, settle_run
from app.models.agent_run import AgentRun, AgentThread
from app.models.user import User
from app.schemas.agent_runs import AgentRunStatus
from app.security import hash_password

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=test_engine, expire_on_commit=False, class_=AsyncSession
    )


@pytest_asyncio.fixture
async def make_run(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[Callable[..., Awaitable[uuid.UUID]]]:
    """Committed user + thread + run; cascade-delete at teardown."""
    user_ids: list[uuid.UUID] = []

    async def _make(*, status: str = "running") -> uuid.UUID:
        async with commit_factory() as db:
            user = User(
                email=f"agent-lease-{uuid.uuid4().hex[:8]}@example.com",
                display_name="Lease Test User",
                hashed_password=hash_password("correct-horse-battery-staple"),
                is_admin=False,
                mfa_enabled=False,
                must_change_password=False,
            )
            db.add(user)
            await db.flush()
            user_ids.append(user.id)
            thread = AgentThread(user_id=user.id, title="lease test")
            db.add(thread)
            await db.flush()
            run = AgentRun(
                user_id=user.id,
                thread_id=thread.id,
                status=status,
                prompt="lease test",
                model_alias="smart",
                max_steps=20,
            )
            db.add(run)
            await db.commit()
            return run.id

    yield _make

    async with commit_factory() as db:
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


async def _run_row(
    factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID
) -> AgentRun:
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        return run


async def test_claim_stamps_lease_and_heartbeat(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    run_id = await make_run()
    lease = await claim_run(commit_factory, run_id, claimed_by="host:1:abc")
    assert lease is not None
    row = await _run_row(commit_factory, run_id)
    assert row.claimed_by == "host:1:abc"
    assert row.claimed_at is not None
    assert row.heartbeat_at is not None
    assert row.lease_token == lease.token


async def test_second_claim_is_refused(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """The at-most-once belt: even a duplicate delivery under a fresh
    arq job id cannot double-execute a run."""
    run_id = await make_run()
    assert await claim_run(commit_factory, run_id, claimed_by="w1") is not None
    assert await claim_run(commit_factory, run_id, claimed_by="w2") is None


async def test_settled_run_is_not_claimable(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """A run cancelled while queued must be an honest no-op at pickup."""
    run_id = await make_run(status=AgentRunStatus.cancelled.value)
    assert await claim_run(commit_factory, run_id, claimed_by="w1") is None


async def test_heartbeat_lands_only_with_the_live_lease(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    run_id = await make_run()
    lease = await claim_run(commit_factory, run_id, claimed_by="w1")
    assert lease is not None
    assert await heartbeat_run(commit_factory, lease) is True
    # A zombie holding a stale token learns it lost the run.
    zombie = RunLease(run_id=run_id, token=uuid.uuid4(), claimed_by="zombie")
    assert await heartbeat_run(commit_factory, zombie) is False


async def test_heartbeat_detects_settlement_elsewhere(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """The runner's hard-stop signal: cancel/sweep settled the row, the
    next fenced heartbeat hits nothing."""
    run_id = await make_run()
    lease = await claim_run(commit_factory, run_id, claimed_by="w1")
    assert lease is not None
    assert await settle_run(commit_factory, run_id, status=AgentRunStatus.cancelled), (
        "endpoint-style settle (no token) must land on a running row"
    )
    assert await heartbeat_run(commit_factory, lease) is False


async def test_terminal_status_is_monotonic(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """First terminal writer wins; a late 'completed' can never
    downgrade/overwrite a settled run (the zombie-success case)."""
    run_id = await make_run()
    lease = await claim_run(commit_factory, run_id, claimed_by="w1")
    assert lease is not None
    assert await settle_run(commit_factory, run_id, status=AgentRunStatus.cancelled)
    late = await settle_run(
        commit_factory,
        run_id,
        status=AgentRunStatus.completed,
        final_answer="zombie answer",
        lease_token=lease.token,
    )
    assert late is False
    row = await _run_row(commit_factory, run_id)
    assert row.status == AgentRunStatus.cancelled.value
    assert row.final_answer is None


async def test_fenced_settle_rejects_a_stale_token(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    run_id = await make_run()
    assert await claim_run(commit_factory, run_id, claimed_by="w1") is not None
    stale = await settle_run(
        commit_factory,
        run_id,
        status=AgentRunStatus.failed,
        error="zombie write",
        lease_token=uuid.uuid4(),
    )
    assert stale is False
    row = await _run_row(commit_factory, run_id)
    assert row.status == AgentRunStatus.running.value


async def test_heartbeat_uses_the_db_clock(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """heartbeat_at advances on each beat and is stamped by Postgres —
    the sweep compares against now() on the same clock."""
    run_id = await make_run()
    lease = await claim_run(commit_factory, run_id, claimed_by="w1")
    assert lease is not None
    # Push the heartbeat into the past ON THE DB CLOCK, then beat again.
    async with commit_factory() as db:
        pushed = (
            await db.execute(
                text(
                    "UPDATE agent_runs SET heartbeat_at = now() - interval '1 hour' "
                    "WHERE id = :rid RETURNING heartbeat_at"
                ),
                {"rid": run_id},
            )
        ).scalar_one()
        await db.commit()
    assert await heartbeat_run(commit_factory, lease) is True
    second = (await _run_row(commit_factory, run_id)).heartbeat_at
    assert second is not None and second > pushed
