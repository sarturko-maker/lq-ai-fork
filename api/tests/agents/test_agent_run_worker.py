"""Agent-run worker: orphan sweep, at-most-once job, hard-stop — F1-S1.

Drives the CORE functions (:func:`run_orphan_sweep`,
:func:`execute_run_job`) directly against the test DB — the
autonomous-worker ``_run_idle_sweep`` testing pattern. The arq wrappers
add only process-global wiring.

The kill -9 scenario itself is verified LIVE on the dev stack (see
docs/fork/evidence/f1-s1/); here we prove every rule the sweep applies
and every write the job makes, deterministically.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.lease import RunLease, claim_run
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.agent_runs import AgentRunStatus
from app.security import hash_password
from app.workers.agent_run_worker import execute_run_job, run_orphan_sweep

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def make_run(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[Callable[..., Awaitable[uuid.UUID]]]:
    user_ids: list[uuid.UUID] = []

    async def _make(*, status: str = "running") -> uuid.UUID:
        async with commit_factory() as db:
            user = User(
                email=f"agent-sweep-{uuid.uuid4().hex[:8]}@example.com",
                display_name="Sweep Test User",
                hashed_password=hash_password("correct-horse-battery-staple"),
                is_admin=False,
                mfa_enabled=False,
                must_change_password=False,
            )
            db.add(user)
            await db.flush()
            user_ids.append(user.id)
            thread = AgentThread(user_id=user.id, title="sweep test")
            db.add(thread)
            await db.flush()
            run = AgentRun(
                user_id=user.id,
                thread_id=thread.id,
                status=status,
                prompt="sweep test",
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


async def _age_row(
    factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID, *, set_sql: str
) -> None:
    """Backdate lease/heartbeat columns ON THE DB CLOCK."""
    async with factory() as db:
        await db.execute(
            text(f"UPDATE agent_runs SET {set_sql} WHERE id = :rid"),
            {"rid": run_id},
        )
        await db.commit()


async def _row(factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID) -> AgentRun:
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        return run


async def _sweep(factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    return await run_orphan_sweep(factory, orphan_after_seconds=120.0, claim_grace_seconds=300.0)


# ---------------------------------------------------------------------------
# run_orphan_sweep
# ---------------------------------------------------------------------------


async def test_sweep_settles_stale_heartbeat_run_with_audit(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    run_id = await make_run()
    assert await claim_run(commit_factory, run_id, claimed_by="dead-worker") is not None
    await _age_row(commit_factory, run_id, set_sql="heartbeat_at = now() - interval '10 minutes'")

    result = await _sweep(commit_factory)

    assert result["swept"] == 1
    row = await _row(commit_factory, run_id)
    assert row.status == AgentRunStatus.failed.value
    assert row.error is not None and row.error.startswith("orphaned: worker heartbeat stale")
    assert "dead-worker" in row.error
    assert row.finished_at is not None
    async with commit_factory() as db:
        audit = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "agent_run.orphan_settled",
                    AuditLog.resource_id == str(run_id),
                )
            )
        ).scalar_one()
        assert audit.details is not None and audit.details["reason"] == "stale_heartbeat"
        await db.execute(delete(AuditLog).where(AuditLog.id == audit.id))
        await db.commit()


async def test_sweep_leaves_live_claimed_runs_alone(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    run_id = await make_run()
    assert await claim_run(commit_factory, run_id, claimed_by="live-worker") is not None

    result = await _sweep(commit_factory)

    assert result["swept"] == 0
    assert (await _row(commit_factory, run_id)).status == AgentRunStatus.running.value


async def test_sweep_settles_unclaimed_run_past_grace(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Lost enqueue / worker death before claim / pre-F1-S1 legacy rows:
    no heartbeat exists to read, so age-since-start decides."""
    run_id = await make_run()
    await _age_row(commit_factory, run_id, set_sql="started_at = now() - interval '10 minutes'")

    result = await _sweep(commit_factory)

    assert result["swept"] == 1
    row = await _row(commit_factory, run_id)
    assert row.status == AgentRunStatus.failed.value
    assert row.error == "orphaned: never claimed by a worker"
    async with commit_factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.resource_id == str(run_id)))
        await db.commit()


async def test_sweep_respects_the_claim_grace_window(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """A freshly-created run waiting for a worker slot must NOT be eaten
    (the OpenClaw startup-cutoff lesson)."""
    run_id = await make_run()

    result = await _sweep(commit_factory)

    assert result["swept"] == 0
    assert (await _row(commit_factory, run_id)).status == AgentRunStatus.running.value


async def test_sweep_never_touches_settled_rows(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    run_id = await make_run(status=AgentRunStatus.completed.value)
    await _age_row(
        commit_factory,
        run_id,
        set_sql=(
            "started_at = now() - interval '1 day', "
            "claimed_at = now() - interval '1 day', "
            "heartbeat_at = now() - interval '1 day'"
        ),
    )

    result = await _sweep(commit_factory)

    assert result["swept"] == 0
    assert (await _row(commit_factory, run_id)).status == AgentRunStatus.completed.value


# ---------------------------------------------------------------------------
# execute_run_job
# ---------------------------------------------------------------------------


async def test_job_claims_then_composes_with_the_lease(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    run_id = await make_run()
    seen: dict[str, Any] = {}

    async def fake_compose(*, run_id: uuid.UUID, lease: RunLease) -> None:
        seen["run_id"] = run_id
        seen["lease"] = lease

    result = await execute_run_job(commit_factory, run_id, claimed_by="w1", compose=fake_compose)

    assert result["executed"] is True
    assert seen["run_id"] == run_id
    assert isinstance(seen["lease"], RunLease)
    row = await _row(commit_factory, run_id)
    assert row.claimed_by == "w1"
    assert row.lease_token == seen["lease"].token


async def test_job_is_a_noop_when_the_run_was_settled_while_queued(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Cancel-while-queued: the job must not execute anything."""
    run_id = await make_run(status=AgentRunStatus.cancelled.value)
    composed = False

    async def fake_compose(**_kwargs: Any) -> None:
        nonlocal composed
        composed = True

    result = await execute_run_job(commit_factory, run_id, claimed_by="w1", compose=fake_compose)

    assert result["executed"] is False
    assert composed is False
    assert (await _row(commit_factory, run_id)).status == AgentRunStatus.cancelled.value


async def test_job_settles_the_row_on_worker_interruption(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """arq abort / SIGTERM shutdown (CancelledError is a BaseException):
    settle before re-raise — a graceful deploy is never a silent orphan
    factory."""
    run_id = await make_run()

    async def cancelled_compose(**_kwargs: Any) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await execute_run_job(commit_factory, run_id, claimed_by="w1", compose=cancelled_compose)

    row = await _row(commit_factory, run_id)
    assert row.status == AgentRunStatus.failed.value
    assert row.error is not None and row.error.startswith("run interrupted")


async def test_job_interruption_never_overwrites_a_cancel(
    commit_factory: async_sessionmaker[AsyncSession],
    make_run: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """The abort-after-cancel race: the endpoint already settled the row
    as 'cancelled'; the job's interrupted-settle must lose (fenced +
    monotonic), keeping the user-visible state honest."""
    run_id = await make_run()
    from app.agents.lease import settle_run

    async def compose_then_cancelled(*, run_id: uuid.UUID, lease: RunLease) -> None:
        # Simulate the cancel endpoint winning mid-flight, then the
        # arq abort's CancelledError arriving.
        await settle_run(commit_factory, run_id, status=AgentRunStatus.cancelled)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await execute_run_job(
            commit_factory, run_id, claimed_by="w1", compose=compose_then_cancelled
        )

    assert (await _row(commit_factory, run_id)).status == AgentRunStatus.cancelled.value
