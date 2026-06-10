"""Integration tests for the F0-S2 agent-runs API.

Covers:
- POST /agents/runs: 202 + persisted row + background scheduling, 422
  validation, 401 unauthenticated.
- GET /agents/runs/{run_id}: detail + ordered steps, cross-user 404,
  missing 404.
- GET /agents/runs: newest-first pagination, cross-user isolation.

The background runner is no-op'd at the module seam (house style — see
``tests/test_playbooks_endpoints.py``); the runner itself is covered by
``tests/agents/test_agent_runner.py``.
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import agent_runs as agent_runs_module
from app.db.session import get_db
from app.main import app
from app.models.agent_run import AgentRun, AgentRunStep
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


async def _make_run(
    db: AsyncSession,
    *,
    user: User,
    status: str = "running",
    started_at: datetime | None = None,
) -> AgentRun:
    run = AgentRun(
        user_id=user.id,
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
            json={"prompt": "Summarise the indemnity.", "model_alias": "fast", "max_steps": 5},
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
    assert [s["kind"] for s in body["steps"]] == ["model_turn", "tool_call", "tool_result"]
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
