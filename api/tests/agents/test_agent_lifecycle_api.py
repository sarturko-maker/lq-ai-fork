"""Cancel + thread-delete endpoints — F1-S1 (ADR-F009).

POST /agents/runs/{run_id}/cancel: settle-first, idempotent, audited,
404-not-403 cross-user. DELETE /agents/threads/{thread_id}: cascades
runs/steps, deletes the checkpoint lineage through the saver's own API,
409 while a run is live.

Reuses the runs-API test helpers (committed via the shared savepoint
``db_session``; the endpoints run in the same transaction). The arq
abort helper is replaced at the module seam — the queue transport is
not under test here (its semantics are pinned in
tests/agents/test_agent_lease.py and live verification).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import agent_runs as agent_runs_module
from app.db.session import get_db
from app.main import app
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.agent_runs import AgentRunStatus
from tests.agents.test_agent_runs_api import (
    _bearer,
    _make_run,
    _make_thread,
    _make_user,
    _override_get_db,
    _put_checkpoint,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def user_a(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="lifecycle-a")


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="lifecycle-b")


@pytest_asyncio.fixture
async def thread_saver() -> AsyncIterator[InMemorySaver]:
    saver = InMemorySaver()
    app.dependency_overrides[agent_runs_module.get_checkpointer_dep] = lambda: saver
    yield saver
    app.dependency_overrides.pop(agent_runs_module.get_checkpointer_dep, None)


# ---------------------------------------------------------------------------
# POST /agents/runs/{run_id}/cancel
# ---------------------------------------------------------------------------


async def test_cancel_settles_a_running_run_and_audits(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    run = await _make_run(db_session, user=user_a, status="running")
    aborted: list[uuid.UUID] = []

    async def fake_abort(run_id: uuid.UUID) -> None:
        aborted.append(run_id)

    with patch.object(agent_runs_module, "abort_agent_run_job", new=fake_abort):
        resp = await client.post(
            f"/api/v1/agents/runs/{run.id}/cancel", headers=_bearer(user_a)
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["finished_at"] is not None
    assert aborted == [run.id]
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "agent_run.cancel",
                AuditLog.resource_id == str(run.id),
            )
        )
    ).scalar_one()
    assert audit.user_id == user_a.id
    assert audit.details == {"from_status": "running"}


@pytest.mark.parametrize(
    "settled_status", ["completed", "failed", "cancelled", "cap_exceeded"]
)
async def test_cancel_is_an_idempotent_noop_on_settled_runs(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    settled_status: str,
) -> None:
    """The finish-vs-cancel race is common and not an error (Letta
    pattern): return the real terminal state, write no audit row,
    signal no abort."""
    run = await _make_run(db_session, user=user_a, status=settled_status)

    async def exploding_abort(run_id: uuid.UUID) -> None:  # pragma: no cover
        raise AssertionError("abort must not be signalled for a settled run")

    with patch.object(agent_runs_module, "abort_agent_run_job", new=exploding_abort):
        resp = await client.post(
            f"/api/v1/agents/runs/{run.id}/cancel", headers=_bearer(user_a)
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == settled_status
    audit_rows = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "agent_run.cancel",
                    AuditLog.resource_id == str(run.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert audit_rows == []


async def test_cancel_cross_user_and_unknown_return_404(
    client: AsyncClient, db_session: AsyncSession, user_a: User, user_b: User
) -> None:
    run = await _make_run(db_session, user=user_a, status="running")
    resp = await client.post(
        f"/api/v1/agents/runs/{run.id}/cancel", headers=_bearer(user_b)
    )
    assert resp.status_code == 404  # never 403 — no existence disclosure
    resp = await client.post(
        f"/api/v1/agents/runs/{uuid.uuid4()}/cancel", headers=_bearer(user_a)
    )
    assert resp.status_code == 404
    # And the run is untouched.
    await db_session.refresh(run)
    assert run.status == AgentRunStatus.running.value


# ---------------------------------------------------------------------------
# DELETE /agents/threads/{thread_id}
# ---------------------------------------------------------------------------


async def test_delete_thread_cascades_and_deletes_checkpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    thread = await _make_thread(db_session, user=user_a)
    run = await _make_run(db_session, user=user_a, status="completed", thread=thread)
    db_session.add(
        AgentRunStep(run_id=run.id, seq=1, kind="model_turn", summary="answer")
    )
    await db_session.flush()
    await _put_checkpoint(thread_saver, thread.id)

    resp = await client.delete(
        f"/api/v1/agents/threads/{thread.id}", headers=_bearer(user_a)
    )

    assert resp.status_code == 204
    # The DB-level cascade deleted rows the session's identity map still
    # caches (the ORM declares no relationship edges) — capture the ids,
    # then expire, then re-read.
    thread_id, run_id = thread.id, run.id
    db_session.expire_all()
    assert (await db_session.get(AgentThread, thread_id)) is None
    assert (await db_session.get(AgentRun, run_id)) is None
    steps = (
        (
            await db_session.execute(
                select(AgentRunStep).where(AgentRunStep.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    assert steps == []
    # The checkpoint lineage is gone through the saver's own API.
    config: dict[str, Any] = {"configurable": {"thread_id": str(thread_id)}}
    assert await thread_saver.aget_tuple(config) is None
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "agent_thread.delete",
                AuditLog.resource_id == str(thread_id),
            )
        )
    ).scalar_one()
    assert audit.details == {"runs_deleted": 1}


async def test_delete_thread_refuses_while_a_run_is_live(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    thread = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status="running", thread=thread)

    resp = await client.delete(
        f"/api/v1/agents/threads/{thread.id}", headers=_bearer(user_a)
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "thread_busy"
    assert (await db_session.get(AgentThread, thread.id)) is not None


async def test_delete_thread_cross_user_and_unknown_return_404(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
    thread_saver: InMemorySaver,
) -> None:
    thread = await _make_thread(db_session, user=user_a)
    resp = await client.delete(
        f"/api/v1/agents/threads/{thread.id}", headers=_bearer(user_b)
    )
    assert resp.status_code == 404  # never 403
    resp = await client.delete(
        f"/api/v1/agents/threads/{uuid.uuid4()}", headers=_bearer(user_a)
    )
    assert resp.status_code == 404
    assert (await db_session.get(AgentThread, thread.id)) is not None


async def test_delete_thread_survives_a_checkpoint_delete_failure(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
) -> None:
    """Best-effort checkpoint cleanup: the row delete stands; the daily
    GC cron is the durable backstop."""

    class ExplodingSaver(InMemorySaver):
        async def adelete_thread(self, thread_id: str) -> None:
            raise RuntimeError("checkpoint backend down")

    saver = ExplodingSaver()
    app.dependency_overrides[agent_runs_module.get_checkpointer_dep] = lambda: saver
    try:
        thread = await _make_thread(db_session, user=user_a)
        await _make_run(db_session, user=user_a, status="completed", thread=thread)
        resp = await client.delete(
            f"/api/v1/agents/threads/{thread.id}", headers=_bearer(user_a)
        )
    finally:
        app.dependency_overrides.pop(agent_runs_module.get_checkpointer_dep, None)

    assert resp.status_code == 204
    assert (await db_session.get(AgentThread, thread.id)) is None
