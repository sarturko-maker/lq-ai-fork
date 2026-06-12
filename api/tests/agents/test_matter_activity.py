"""GET /agents/matters rollup + threads filters — F1-S2 (fork, ADR-F002).

The cockpit's one-call matters surface: per-matter thread counts, last
activity, newest-run status (across ALL the matter's threads), the
unfiled-bucket summary, and the new ``project_id``/``unfiled`` filters
on the threads list. Settled rows only (ADR-F004); owner-scoped.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.project import Project
from app.models.user import User
from tests.agents.test_agent_runs_api import (
    _bearer,
    _make_project,
    _make_run,
    _make_thread,
    _make_user,
    _override_get_db,
)

pytestmark = pytest.mark.integration

_NOW = datetime.now(UTC)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def user_a(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="matters-a")


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="matters-b")


# ---------------------------------------------------------------------------
# GET /agents/matters
# ---------------------------------------------------------------------------


async def test_matters_rollup_counts_and_newest_status(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    """Two threads on one matter: count=2, status = the NEWEST run's
    across both threads (not the newest thread's only run)."""
    project = await _make_project(db_session, owner=user_a)
    t_old = await _make_thread(
        db_session,
        user=user_a,
        project_id=project.id,
        last_run_at=_NOW - timedelta(hours=2),
    )
    t_new = await _make_thread(
        db_session,
        user=user_a,
        project_id=project.id,
        last_run_at=_NOW - timedelta(minutes=5),
    )
    await _make_run(
        db_session,
        user=user_a,
        status="completed",
        thread=t_old,
        started_at=_NOW - timedelta(hours=2),
    )
    await _make_run(
        db_session,
        user=user_a,
        status="failed",
        thread=t_new,
        started_at=_NOW - timedelta(minutes=5),
    )

    resp = await client.get("/api/v1/agents/matters", headers=_bearer(user_a))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["matters"]) == 1
    matter = body["matters"][0]
    assert matter["project_id"] == str(project.id)
    assert matter["name"] == project.name
    assert matter["thread_count"] == 2
    assert matter["last_run_status"] == "failed"
    assert matter["last_run_at"] is not None
    assert body["unfiled"]["thread_count"] == 0
    assert body["unfiled"]["last_run_status"] is None


async def test_matters_includes_quiet_matters_after_active_ones(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    """A matter with no conversations still lists (0 / None / None),
    ordered after matters with activity."""
    quiet = await _make_project(db_session, owner=user_a)
    active = await _make_project(db_session, owner=user_a)
    thread = await _make_thread(db_session, user=user_a, project_id=active.id, last_run_at=_NOW)
    await _make_run(db_session, user=user_a, status="running", thread=thread, started_at=_NOW)

    resp = await client.get("/api/v1/agents/matters", headers=_bearer(user_a))
    assert resp.status_code == 200
    matters = resp.json()["matters"]
    assert [m["project_id"] for m in matters] == [str(active.id), str(quiet.id)]
    assert matters[0]["last_run_status"] == "running"
    assert matters[1] == {
        **matters[1],
        "thread_count": 0,
        "last_run_at": None,
        "last_run_status": None,
    }


async def test_matters_excludes_archived_and_sandbox(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    """Archived/sandbox matters are absent AND their threads are neither
    listed nor counted as unfiled (the documented contract) — the unfiled
    bucket is strictly the project_id-IS-NULL set, not "everything not
    shown". Un-archiving restores the matter with its rollup intact."""
    archived = await _make_project(db_session, owner=user_a, archived=True)
    sandbox = Project(
        owner_id=user_a.id,
        name="Sandbox",
        slug=f"sandbox-{uuid.uuid4().hex[:6]}",
        is_sandbox=True,
    )
    db_session.add(sandbox)
    await db_session.flush()
    archived_thread = await _make_thread(
        db_session, user=user_a, project_id=archived.id, last_run_at=_NOW
    )
    await _make_run(
        db_session,
        user=user_a,
        status="completed",
        thread=archived_thread,
        started_at=_NOW,
    )
    sandbox_thread = await _make_thread(
        db_session, user=user_a, project_id=sandbox.id, last_run_at=_NOW
    )
    await _make_run(
        db_session,
        user=user_a,
        status="completed",
        thread=sandbox_thread,
        started_at=_NOW,
    )

    resp = await client.get("/api/v1/agents/matters", headers=_bearer(user_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["matters"] == []
    assert body["unfiled"]["thread_count"] == 0
    assert body["unfiled"]["last_run_status"] is None

    # Un-archiving restores the matter WITH its rollup.
    archived.archived_at = None
    await db_session.flush()
    resp = await client.get("/api/v1/agents/matters", headers=_bearer(user_a))
    body = resp.json()
    assert [m["project_id"] for m in body["matters"]] == [str(archived.id)]
    assert body["matters"][0]["thread_count"] == 1
    assert body["matters"][0]["last_run_status"] == "completed"


async def test_unfiled_summary_rolls_up_unbound_threads(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    t1 = await _make_thread(db_session, user=user_a, last_run_at=_NOW - timedelta(hours=1))
    t2 = await _make_thread(db_session, user=user_a, last_run_at=_NOW)
    await _make_run(
        db_session,
        user=user_a,
        status="completed",
        thread=t1,
        started_at=_NOW - timedelta(hours=1),
    )
    await _make_run(db_session, user=user_a, status="cancelled", thread=t2, started_at=_NOW)

    resp = await client.get("/api/v1/agents/matters", headers=_bearer(user_a))
    assert resp.status_code == 200
    unfiled = resp.json()["unfiled"]
    assert unfiled["thread_count"] == 2
    assert unfiled["last_run_status"] == "cancelled"
    assert unfiled["last_run_at"] is not None


async def test_matters_scoped_to_owner(
    client: AsyncClient, db_session: AsyncSession, user_a: User, user_b: User
) -> None:
    """user_b's matters and unfiled threads never leak into user_a's rollup."""
    project_b = await _make_project(db_session, owner=user_b)
    thread_b = await _make_thread(db_session, user=user_b, project_id=project_b.id)
    await _make_run(db_session, user=user_b, status="running", thread=thread_b)
    await _make_thread(db_session, user=user_b)  # unfiled, user_b's

    resp = await client.get("/api/v1/agents/matters", headers=_bearer(user_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["matters"] == []
    assert body["unfiled"]["thread_count"] == 0


# ---------------------------------------------------------------------------
# GET /agents/threads filters
# ---------------------------------------------------------------------------


async def test_threads_filter_by_project_id(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    project = await _make_project(db_session, owner=user_a)
    filed = await _make_thread(db_session, user=user_a, project_id=project.id)
    await _make_thread(db_session, user=user_a)  # unfiled — must not match

    resp = await client.get(
        "/api/v1/agents/threads",
        params={"project_id": str(project.id)},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert [t["id"] for t in body["threads"]] == [str(filed.id)]


async def test_threads_filter_unfiled(
    client: AsyncClient, db_session: AsyncSession, user_a: User
) -> None:
    project = await _make_project(db_session, owner=user_a)
    await _make_thread(db_session, user=user_a, project_id=project.id)
    unbound = await _make_thread(db_session, user=user_a)

    resp = await client.get(
        "/api/v1/agents/threads", params={"unfiled": "true"}, headers=_bearer(user_a)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 1
    assert [t["id"] for t in body["threads"]] == [str(unbound.id)]


async def test_threads_filters_are_mutually_exclusive(client: AsyncClient, user_a: User) -> None:
    resp = await client.get(
        "/api/v1/agents/threads",
        params={"project_id": str(uuid.uuid4()), "unfiled": "true"},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 422


async def test_threads_filter_foreign_project_matches_nothing(
    client: AsyncClient, db_session: AsyncSession, user_a: User, user_b: User
) -> None:
    """Filtering by another user's project id returns an empty page —
    the filter never confirms foreign ids exist (no existence leak)."""
    project_b = await _make_project(db_session, owner=user_b)
    await _make_thread(db_session, user=user_b, project_id=project_b.id)

    resp = await client.get(
        "/api/v1/agents/threads",
        params={"project_id": str(project_b.id)},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 0
