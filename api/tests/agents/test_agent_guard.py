"""Guarded dispatch — F0-S4: the minimal chokepoint's brakes and audit.

Drives :func:`app.agents.guard.guarded_dispatch` directly with scripted
ops against the real DB: R6 grant denial, R5 halt-at-the-boundary, the
error path, and the audit row each outcome leaves (counts/types/IDs
only). ``privilege_marked`` must resolve from the bound project —
the security posture Receipts and reviews depend on.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.guard import (
    AgentRunHalted,
    AgentToolNotGranted,
    GuardContext,
    guarded_dispatch,
)
from app.models.agent_run import AgentRun, AgentThread
from app.models.audit import AuditLog
from app.models.project import Project
from app.models.user import User
from app.security import hash_password

pytestmark = pytest.mark.integration


@dataclass
class GuardEnv:
    factory: async_sessionmaker[AsyncSession]
    user_id: uuid.UUID
    run_id: uuid.UUID
    project_id: uuid.UUID
    make_ctx: Callable[[frozenset[str]], GuardContext]


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def guard_env(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[GuardEnv]:
    """Committed user + PRIVILEGED matter + running run; explicit teardown."""
    async with commit_factory() as db:
        user = User(
            email=f"agent-guard-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Agent Guard User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.flush()
        project = Project(
            owner_id=user.id,
            name="Privileged Matter",
            slug=f"priv-{uuid.uuid4().hex[:6]}",
            privileged=True,
            minimum_inference_tier=5,
        )
        db.add(project)
        await db.flush()
        thread = AgentThread(user_id=user.id, project_id=project.id, title="guard tests")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user.id,
            thread_id=thread.id,
            project_id=project.id,
            status="running",
            prompt="guard tests",
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()
        user_id, project_id, run_id = user.id, project.id, run.id

    def make_ctx(granted: frozenset[str]) -> GuardContext:
        return GuardContext(
            session_factory=commit_factory,
            run_id=run_id,
            user_id=user_id,
            project_id=project_id,
            granted=granted,
        )

    yield GuardEnv(
        factory=commit_factory,
        user_id=user_id,
        run_id=run_id,
        project_id=project_id,
        make_ctx=make_ctx,
    )

    async with commit_factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
        await db.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
        await db.execute(delete(AgentThread).where(AgentThread.user_id == user_id))
        await db.execute(delete(Project).where(Project.id == project_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


def _op(result: str = "ok") -> Callable[[AsyncSession], Awaitable[str]]:
    async def op(_db: AsyncSession) -> str:
        return result

    return op


async def _audit_rows(env: GuardEnv) -> list[AuditLog]:
    async with env.factory() as db:
        rows = (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.resource_type == "agent_run",
                    AuditLog.resource_id == str(env.run_id),
                )
                .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
            )
        ).scalars()
        return list(rows)


async def test_granted_dispatch_returns_result_and_audits_success(
    guard_env: GuardEnv,
) -> None:
    ctx = guard_env.make_ctx(frozenset({"search_documents"}))
    result = await guarded_dispatch("search_documents", _op("found 3 passages"), ctx)
    assert result == "found 3 passages"

    rows = await _audit_rows(guard_env)
    assert len(rows) == 1
    assert rows[0].action == "agent_run.tool_call"
    assert rows[0].details == {
        "tool": "search_documents",
        "outcome": "success",
        "result_chars": len("found 3 passages"),
    }


async def test_ungranted_tool_is_denied_and_audited(guard_env: GuardEnv) -> None:
    """R6: a tool outside the run's granted set never executes."""
    executed: list[str] = []

    async def op(_db: AsyncSession) -> str:
        executed.append("ran")
        return "should not happen"

    ctx = guard_env.make_ctx(frozenset({"read_document"}))
    with pytest.raises(AgentToolNotGranted):
        await guarded_dispatch("search_documents", op, ctx)

    assert executed == []
    rows = await _audit_rows(guard_env)
    assert rows[-1].details == {
        "tool": "search_documents",
        "outcome": "tool_not_granted",
    }


async def test_non_running_run_denies_dispatch(guard_env: GuardEnv) -> None:
    """R5: the status re-read at the boundary stops settled/cancelled runs."""
    async with guard_env.factory() as db:
        run = await db.get(AgentRun, guard_env.run_id)
        assert run is not None
        run.status = "cancelled"
        await db.commit()

    ctx = guard_env.make_ctx(frozenset({"search_documents"}))
    with pytest.raises(AgentRunHalted):
        await guarded_dispatch("search_documents", _op(), ctx)

    rows = await _audit_rows(guard_env)
    assert rows[-1].details == {"tool": "search_documents", "outcome": "run_halted"}


async def test_op_error_is_audited_with_type_only_and_reraised(
    guard_env: GuardEnv,
) -> None:
    """Errors audit the exception TYPE, never the message (no content leaks)."""

    async def op(_db: AsyncSession) -> str:
        raise ValueError("clause text that must not reach the audit row")

    ctx = guard_env.make_ctx(frozenset({"read_document"}))
    with pytest.raises(ValueError):
        await guarded_dispatch("read_document", op, ctx)

    rows = await _audit_rows(guard_env)
    assert rows[-1].details == {
        "tool": "read_document",
        "outcome": "error",
        "error_type": "ValueError",
    }
    assert "clause text" not in str(rows[-1].details)


async def test_privileged_matter_marks_the_audit_row(guard_env: GuardEnv) -> None:
    """``privilege_marked`` resolves from the bound project (privileged=True)."""
    ctx = guard_env.make_ctx(frozenset({"search_documents"}))
    await guarded_dispatch("search_documents", _op(), ctx)

    rows = await _audit_rows(guard_env)
    assert rows[-1].privilege_marked is True


class _FlushPoisonedSession:
    """Real session whose ``flush`` dies at the DB layer — and genuinely
    poisons the transaction first (failed DBAPI statement), exactly the
    audit-write failure mode the no-mask guarantee defends against.
    Without the guard's rollback, the next ``commit`` would raise
    PendingRollbackError and mask the tool result (F0-S4 review)."""

    def __init__(self, real: AsyncSession) -> None:
        self._real = real

    async def __aenter__(self) -> _FlushPoisonedSession:
        await self._real.__aenter__()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._real.__aexit__(*exc_info)

    async def flush(self) -> None:
        from sqlalchemy import text

        await self._real.execute(text("SELECT 1/0"))  # raises; tx now failed

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


async def test_audit_failure_never_masks_the_tool_result(
    guard_env: GuardEnv, caplog: pytest.LogCaptureFixture
) -> None:
    """The documented no-mask guarantee, pinned: audit write fails at the
    DB layer → logged loudly, session rolled back, the tool result
    still returned to the model."""
    import logging

    factory = guard_env.factory

    def poisoned_factory() -> _FlushPoisonedSession:
        return _FlushPoisonedSession(factory())

    ctx = GuardContext(
        session_factory=poisoned_factory,  # type: ignore[arg-type]
        run_id=guard_env.run_id,
        user_id=guard_env.user_id,
        project_id=guard_env.project_id,
        granted=frozenset({"search_documents"}),
    )

    with caplog.at_level(logging.ERROR, logger="app.agents.guard"):
        result = await guarded_dispatch("search_documents", _op("the result stands"), ctx)

    assert result == "the result stands"
    assert any("audit write failed" in r.message for r in caplog.records)
    # The row was genuinely lost — observability said so; nothing landed.
    rows = await _audit_rows(guard_env)
    assert rows == []


async def test_granted_dispatch_touches_the_heartbeat(guard_env: GuardEnv) -> None:
    """F1-S1 (ADR-F009): R5 is now a fenced heartbeat touch — a granted
    dispatch proves liveness at tool-boundary cadence, the second
    heartbeat source beside the runner's throttled per-event beat."""
    ctx = guard_env.make_ctx(frozenset({"read_clause"}))
    async with guard_env.factory() as db:
        run = await db.get(AgentRun, guard_env.run_id)
        assert run is not None and run.heartbeat_at is None

    await guarded_dispatch("read_clause", _op("ok"), ctx)

    async with guard_env.factory() as db:
        run = await db.get(AgentRun, guard_env.run_id)
        assert run is not None and run.heartbeat_at is not None


async def test_heartbeat_touch_survives_a_tool_body_error(guard_env: GuardEnv) -> None:
    """F1-S1 review fix: the touch COMMITS before the tool body, so a
    body error (whole-dispatch rollback) cannot undo the liveness
    signal — and the sweep can see it while a slow body runs."""
    ctx = guard_env.make_ctx(frozenset({"read_clause"}))

    async def exploding_op(_db: AsyncSession) -> str:
        raise RuntimeError("tool body failed")

    with pytest.raises(RuntimeError, match="tool body failed"):
        await guarded_dispatch("read_clause", exploding_op, ctx)

    async with guard_env.factory() as db:
        run = await db.get(AgentRun, guard_env.run_id)
        assert run is not None and run.heartbeat_at is not None
