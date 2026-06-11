"""Integration tests for the F0-S2/F0-S5 agent-runs + threads API.

Covers:
- POST /agents/runs: 202 + persisted row + background scheduling, 422
  validation, 401 unauthenticated; thread creation and follow-up rules
  (404 / 409 thread_busy / 409 thread_not_continuable / 422 — ADR-F008).
- GET /agents/runs/{run_id}: detail + ordered steps, cross-user 404,
  missing 404.
- GET /agents/runs: newest-first pagination, cross-user isolation.
- GET /agents/threads + /agents/threads/{id}: conversation list/detail,
  cross-user 404, ``continuable``.

The background runner is no-op'd at the module seam (house style — see
``tests/test_playbooks_endpoints.py``); the runner itself is covered by
``tests/agents/test_agent_runner.py``, the real multi-turn composition
by ``tests/agents/test_agent_composition.py``. The checkpointer reaches
the endpoints through ``get_checkpointer_dep`` and is overridden with an
``InMemorySaver`` here — the house DI pattern, no monkeypatching.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import agent_runs as agent_runs_module
from app.db.session import get_db
from app.main import app
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.project import Project
from app.models.user import User
from app.security import create_access_token, hash_password

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _override_get_db(db_session: AsyncSession) -> Any:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    return _override


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


async def _make_user(db: AsyncSession, *, suffix: str = "") -> User:
    user = User(
        email=f"agent-runs-{suffix or uuid.uuid4().hex[:8]}@example.com",
        display_name=f"Agent Runs User {suffix}".strip(),
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def user_a(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="a")


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="b")


def _bearer(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


async def _make_thread(
    db: AsyncSession,
    *,
    user: User,
    project_id: uuid.UUID | None = None,
    title: str = "test conversation",
    last_run_at: datetime | None = None,
) -> AgentThread:
    thread = AgentThread(
        user_id=user.id,
        project_id=project_id,
        title=title,
        last_run_at=last_run_at or datetime.now(UTC),
    )
    db.add(thread)
    await db.flush()
    await db.refresh(thread)
    return thread


async def _make_run(
    db: AsyncSession,
    *,
    user: User,
    status: str = "running",
    started_at: datetime | None = None,
    thread: AgentThread | None = None,
) -> AgentRun:
    if thread is None:
        thread = await _make_thread(db, user=user)
    run = AgentRun(
        user_id=user.id,
        thread_id=thread.id,
        project_id=thread.project_id,
        status=status,
        prompt="What is the liability cap?",
        model_alias="smart",
        max_steps=20,
        started_at=started_at or datetime.now(UTC),
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def _noop_background(**_kwargs: Any) -> None:
    """Replaces ``_run_in_background`` so endpoint tests don't run the agent."""


@pytest_asyncio.fixture
async def thread_saver() -> AsyncIterator[InMemorySaver]:
    """In-memory checkpointer injected through the endpoint's DI seam."""
    saver = InMemorySaver()
    app.dependency_overrides[agent_runs_module.get_checkpointer_dep] = lambda: saver
    yield saver
    app.dependency_overrides.pop(agent_runs_module.get_checkpointer_dep, None)


async def _put_checkpoint(saver: InMemorySaver, thread_id: uuid.UUID) -> None:
    """Persist a minimal checkpoint so the thread counts as continuable."""
    config = {"configurable": {"thread_id": str(thread_id), "checkpoint_ns": ""}}
    await saver.aput(config, empty_checkpoint(), {}, {})


async def _make_project(db: AsyncSession, *, owner: User, archived: bool = False) -> Project:
    project = Project(
        owner_id=owner.id,
        name=f"Matter {uuid.uuid4().hex[:6]}",
        slug=f"matter-{uuid.uuid4().hex[:6]}",
        archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(project)
    await db.flush()
    return project


# ---------------------------------------------------------------------------
# POST /agents/runs
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_run_returns_202_with_running_row(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
) -> None:
    """202 with the persisted row at status='running' and defaults applied."""
    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "What is the liability cap?"},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["prompt"] == "What is the liability cap?"
    assert body["model_alias"] == "smart"
    assert body["max_steps"] == 20
    assert body["purpose"] == "agent_loop"
    assert body["final_answer"] is None
    assert body["finished_at"] is None
    assert body["user_id"] == str(user_a.id)

    row = (
        await db_session.execute(select(AgentRun).where(AgentRun.id == uuid.UUID(body["id"])))
    ).scalar_one()
    assert row.user_id == user_a.id
    assert row.status == "running"


@pytest.mark.integration
async def test_create_run_honours_model_alias_and_max_steps(
    client: AsyncClient,
    user_a: User,
) -> None:
    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={
                "prompt": "Summarise the indemnity.",
                "model_alias": "fast",
                "max_steps": 5,
            },
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["model_alias"] == "fast"
    assert body["max_steps"] == 5


@pytest.mark.integration
@pytest.mark.parametrize(
    "payload",
    [
        {},  # prompt required
        {"prompt": ""},  # min_length=1
        {"prompt": "x", "max_steps": 0},  # ge=1
        {"prompt": "x", "max_steps": 101},  # le=100
        {"prompt": "x", "model_alias": ""},  # min_length=1
    ],
)
async def test_create_run_rejects_invalid_bodies(
    client: AsyncClient,
    user_a: User,
    payload: dict[str, Any],
) -> None:
    """Boundary validation: reject, don't sanitize (CLAUDE.md)."""
    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post("/api/v1/agents/runs", headers=_bearer(user_a), json=payload)
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
async def test_create_run_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/agents/runs", json={"prompt": "x"})
    assert resp.status_code == 401


@pytest.mark.integration
async def test_create_run_429_at_concurrent_running_cap(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
) -> None:
    """3 runs already at 'running' → 429 with detail 'too_many_running_runs'.

    Interim flood brake (F1 R4 budgets + arq replace it); the cap is
    per-user, so another user's running runs are irrelevant.
    """
    for _ in range(3):
        await _make_run(db_session, user=user_a, status="running")

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "one too many"},
        )

    assert resp.status_code == 429, resp.text
    assert resp.json()["detail"] == "too_many_running_runs"


@pytest.mark.integration
async def test_create_run_cap_ignores_terminal_runs(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
) -> None:
    """Only status='running' counts toward the cap — terminal rows don't."""
    for _ in range(2):
        await _make_run(db_session, user=user_a, status="running")
    for terminal in ("completed", "failed", "cap_exceeded"):
        await _make_run(db_session, user=user_a, status=terminal)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "third running run is fine"},
        )

    assert resp.status_code == 202, resp.text


# ---------------------------------------------------------------------------
# POST /agents/runs — matter binding (F0-S4)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_run_binds_owned_active_project(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
) -> None:
    """An owned, active matter binds: 202 with project_id persisted."""
    project = await _make_project(db_session, owner=user_a)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={
                "prompt": "What is the liability cap?",
                "project_id": str(project.id),
            },
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["project_id"] == str(project.id)
    row = (
        await db_session.execute(select(AgentRun).where(AgentRun.id == uuid.UUID(body["id"])))
    ).scalar_one()
    assert row.project_id == project.id


@pytest.mark.integration
async def test_create_run_without_project_id_is_unbound(
    client: AsyncClient,
    user_a: User,
) -> None:
    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "blank workspace"},
        )
    assert resp.status_code == 202, resp.text
    assert resp.json()["project_id"] is None


@pytest.mark.integration
async def test_create_run_cross_user_project_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
) -> None:
    """Another user's matter id is 404 — never 403 (no existence leak)."""
    project = await _make_project(db_session, owner=user_a)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_b),
            json={"prompt": "not my matter", "project_id": str(project.id)},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "project not found"


@pytest.mark.integration
async def test_create_run_archived_project_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
) -> None:
    project = await _make_project(db_session, owner=user_a, archived=True)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "archived matter", "project_id": str(project.id)},
        )
    assert resp.status_code == 404


@pytest.mark.integration
async def test_create_run_unknown_project_returns_404(
    client: AsyncClient,
    user_a: User,
) -> None:
    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "ghost matter", "project_id": str(uuid.uuid4())},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /agents/runs/{run_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_run_returns_run_with_ordered_steps(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
) -> None:
    """Detail returns the run plus steps in seq order — the poller contract."""
    run = await _make_run(db_session, user=user_a, status="completed")
    # Insert deliberately out of order; the endpoint must sort by seq.
    for seq, kind, name in [
        (3, "tool_result", "read_clause"),
        (1, "model_turn", None),
        (2, "tool_call", "read_clause"),
    ]:
        db_session.add(
            AgentRunStep(run_id=run.id, seq=seq, kind=kind, name=name, summary=f"step {seq}")
        )
    await db_session.flush()

    resp = await client.get(f"/api/v1/agents/runs/{run.id}", headers=_bearer(user_a))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run"]["id"] == str(run.id)
    assert body["run"]["status"] == "completed"
    assert [s["seq"] for s in body["steps"]] == [1, 2, 3]
    assert [s["kind"] for s in body["steps"]] == [
        "model_turn",
        "tool_call",
        "tool_result",
    ]
    assert body["steps"][1]["name"] == "read_clause"


@pytest.mark.integration
async def test_get_run_cross_user_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
) -> None:
    """Another user's run id is 404 — never 403 (no existence leak)."""
    run = await _make_run(db_session, user=user_a)

    resp = await client.get(f"/api/v1/agents/runs/{run.id}", headers=_bearer(user_b))
    assert resp.status_code == 404


@pytest.mark.integration
async def test_get_run_missing_returns_404(
    client: AsyncClient,
    user_a: User,
) -> None:
    resp = await client.get(f"/api/v1/agents/runs/{uuid.uuid4()}", headers=_bearer(user_a))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /agents/runs
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_list_runs_newest_first_paginated_and_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
) -> None:
    base = datetime.now(UTC)
    runs = [
        await _make_run(db_session, user=user_a, started_at=base - timedelta(minutes=i))
        for i in range(3)
    ]  # runs[0] newest
    await _make_run(db_session, user=user_b)

    resp = await client.get("/api/v1/agents/runs", headers=_bearer(user_a))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_count"] == 3
    assert [r["id"] for r in body["runs"]] == [str(r.id) for r in runs]

    # Pagination envelope.
    resp = await client.get("/api/v1/agents/runs?limit=1&offset=1", headers=_bearer(user_a))
    body = resp.json()
    assert body["total_count"] == 3
    assert body["limit"] == 1 and body["offset"] == 1
    assert [r["id"] for r in body["runs"]] == [str(runs[1].id)]

    # user_b sees only their own run.
    resp = await client.get("/api/v1/agents/runs", headers=_bearer(user_b))
    assert resp.json()["total_count"] == 1


# ---------------------------------------------------------------------------
# POST /agents/runs — threads and follow-ups (F0-S5, ADR-F008)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_create_run_creates_thread_with_bounded_title(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
) -> None:
    """A first message creates its conversation: thread row, title from
    the prompt (bounded to 120 chars), run linked to it."""
    long_prompt = "Summarise the indemnity. " * 20  # > 120 chars
    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": long_prompt},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    thread = (
        await db_session.execute(
            select(AgentThread).where(AgentThread.id == uuid.UUID(body["thread_id"]))
        )
    ).scalar_one()
    assert thread.user_id == user_a.id
    assert thread.title == long_prompt[:120]
    assert thread.project_id is None


@pytest.mark.integration
async def test_follow_up_continues_thread_and_inherits_binding(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    """A follow-up on a completed thread with checkpoint state: 202, the
    run joins the thread and inherits ITS matter binding (no project_id
    in the request)."""
    project = await _make_project(db_session, owner=user_a)
    thread = await _make_thread(db_session, user=user_a, project_id=project.id)
    await _make_run(db_session, user=user_a, status="completed", thread=thread)
    await _put_checkpoint(thread_saver, thread.id)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "And the indemnity?", "thread_id": str(thread.id)},
        )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["thread_id"] == str(thread.id)
    assert body["project_id"] == str(project.id)  # inherited from the thread


@pytest.mark.integration
async def test_follow_up_rejects_project_id_override(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    """422: the binding is the THREAD's — a follow-up cannot rebind."""
    project = await _make_project(db_session, owner=user_a)
    thread = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status="completed", thread=thread)
    await _put_checkpoint(thread_saver, thread.id)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={
                "prompt": "rebind attempt",
                "thread_id": str(thread.id),
                "project_id": str(project.id),
            },
        )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_follow_up_cross_user_thread_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
    thread_saver: InMemorySaver,
) -> None:
    """Another user's thread id is 404 — never 403 (no existence leak)."""
    thread = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status="completed", thread=thread)
    await _put_checkpoint(thread_saver, thread.id)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_b),
            json={"prompt": "not my thread", "thread_id": str(thread.id)},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "thread not found"


@pytest.mark.integration
async def test_follow_up_on_busy_thread_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    thread = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status="running", thread=thread)
    await _put_checkpoint(thread_saver, thread.id)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "impatient", "thread_id": str(thread.id)},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "thread_busy"


@pytest.mark.integration
@pytest.mark.parametrize("latest_status", ["failed", "cap_exceeded", "cancelled"])
async def test_follow_up_on_interrupted_thread_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
    latest_status: str,
) -> None:
    """An interrupted loop can strand dangling tool calls in checkpoint
    state — follow-ups are refused until a repair pathway exists."""
    thread = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status=latest_status, thread=thread)
    await _put_checkpoint(thread_saver, thread.id)

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "continue anyway?", "thread_id": str(thread.id)},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "thread_not_continuable"


@pytest.mark.integration
async def test_follow_up_on_archived_matter_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    """Archiving the conversation's Matter after turn 1 must refuse the
    follow-up (409 matter_archived) — accepting it would silently run
    unbound while the UI still presents the binding (F0-S5 review)."""
    project = await _make_project(db_session, owner=user_a)
    thread = await _make_thread(db_session, user=user_a, project_id=project.id)
    await _make_run(db_session, user=user_a, status="completed", thread=thread)
    await _put_checkpoint(thread_saver, thread.id)
    project.archived_at = datetime.now(UTC)
    await db_session.flush()

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "still grounded?", "thread_id": str(thread.id)},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "matter_archived"

    # The thread detail mirrors the refusal: composer greys out honestly.
    detail = await client.get(f"/api/v1/agents/threads/{thread.id}", headers=_bearer(user_a))
    assert detail.json()["continuable"] is False


@pytest.mark.integration
async def test_follow_up_without_checkpoint_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    """Completed run but NO persisted state (pre-S5 backfill, or a run
    executed while persistence was degraded): the agent would not
    remember the conversation — refuse honestly."""
    thread = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status="completed", thread=thread)
    # No _put_checkpoint — the saver knows nothing about this thread.

    with patch.object(agent_runs_module, "_run_in_background", new=_noop_background):
        resp = await client.post(
            "/api/v1/agents/runs",
            headers=_bearer(user_a),
            json={"prompt": "remember me?", "thread_id": str(thread.id)},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "thread_not_continuable"


# ---------------------------------------------------------------------------
# GET /agents/threads
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_list_threads_newest_activity_first_with_status_badges(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
) -> None:
    base = datetime.now(UTC)
    old = await _make_thread(
        db_session, user=user_a, title="old chat", last_run_at=base - timedelta(hours=1)
    )
    await _make_run(db_session, user=user_a, status="completed", thread=old)
    fresh = await _make_thread(db_session, user=user_a, title="fresh chat", last_run_at=base)
    await _make_run(
        db_session,
        user=user_a,
        status="completed",
        thread=fresh,
        started_at=base - timedelta(minutes=5),
    )
    await _make_run(db_session, user=user_a, status="running", thread=fresh, started_at=base)
    await _make_thread(db_session, user=user_b, title="not yours")

    resp = await client.get("/api/v1/agents/threads", headers=_bearer(user_a))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_count"] == 2
    assert [t["title"] for t in body["threads"]] == ["fresh chat", "old chat"]
    # Badge = the NEWEST run's status.
    assert body["threads"][0]["last_run_status"] == "running"
    assert body["threads"][1]["last_run_status"] == "completed"

    # user_b sees only their own thread.
    resp = await client.get("/api/v1/agents/threads", headers=_bearer(user_b))
    assert resp.json()["total_count"] == 1


@pytest.mark.integration
async def test_list_threads_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/agents/threads")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /agents/threads/{thread_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_get_thread_returns_runs_oldest_first_with_steps(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    base = datetime.now(UTC)
    thread = await _make_thread(db_session, user=user_a)
    run1 = await _make_run(
        db_session,
        user=user_a,
        status="completed",
        thread=thread,
        started_at=base - timedelta(minutes=5),
    )
    run2 = await _make_run(
        db_session, user=user_a, status="completed", thread=thread, started_at=base
    )
    db_session.add(
        AgentRunStep(run_id=run1.id, seq=1, kind="model_turn", name=None, summary="turn 1")
    )
    db_session.add(
        AgentRunStep(run_id=run2.id, seq=1, kind="model_turn", name=None, summary="turn 2")
    )
    await db_session.flush()
    await _put_checkpoint(thread_saver, thread.id)

    resp = await client.get(f"/api/v1/agents/threads/{thread.id}", headers=_bearer(user_a))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["thread"]["id"] == str(thread.id)
    assert body["thread"]["last_run_status"] == "completed"
    assert [r["run"]["id"] for r in body["runs"]] == [str(run1.id), str(run2.id)]
    assert [r["steps"][0]["summary"] for r in body["runs"]] == ["turn 1", "turn 2"]
    assert body["continuable"] is True


@pytest.mark.integration
async def test_get_thread_not_continuable_while_running_or_without_checkpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    thread_saver: InMemorySaver,
) -> None:
    # Completed but no checkpoint state → not continuable.
    no_state = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status="completed", thread=no_state)
    resp = await client.get(f"/api/v1/agents/threads/{no_state.id}", headers=_bearer(user_a))
    assert resp.json()["continuable"] is False

    # Running → not continuable (even with state).
    busy = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status="running", thread=busy)
    await _put_checkpoint(thread_saver, busy.id)
    resp = await client.get(f"/api/v1/agents/threads/{busy.id}", headers=_bearer(user_a))
    assert resp.json()["continuable"] is False


@pytest.mark.integration
async def test_get_thread_cross_user_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
) -> None:
    thread = await _make_thread(db_session, user=user_a)
    resp = await client.get(f"/api/v1/agents/threads/{thread.id}", headers=_bearer(user_b))
    assert resp.status_code == 404


@pytest.mark.integration
async def test_one_running_run_per_thread_is_db_enforced(
    db_session: AsyncSession,
    user_a: User,
) -> None:
    """The partial unique index closes the check-then-insert race: a
    second running run on the same thread cannot be persisted, however
    the API races (ADR-F008)."""
    from sqlalchemy.exc import IntegrityError

    thread = await _make_thread(db_session, user=user_a)
    await _make_run(db_session, user=user_a, status="running", thread=thread)
    with pytest.raises(IntegrityError):
        await _make_run(db_session, user=user_a, status="running", thread=thread)
    await db_session.rollback()
