"""C3a matter-memory pin endpoint tests (ADR-F042).

The ``POST /api/v1/matters/{project_id}/memory/corrections`` endpoint is the ONLY
writer of a ``trust='human-pinned'`` correction. These tests prove:

* the pin is written with ``author`` (``user_id``) from the SESSION — not from any
  request field (B2: the trust label is structurally true, not claimed),
* per-user isolation — a cross-user / archived matter is 404 (never 403),
* reject-at-the-boundary — blank/oversize bodies are 422 (never a DB 500),
* the audit row (``matter_memory.pin``) carries IDs/counts only — never the body.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.matter_memory import CORRECTION_MAX_CHARS
from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.project import MatterMemoryEntry, Project
from app.models.user import User
from app.security import create_access_token, hash_password

pytestmark = pytest.mark.integration


def _override_get_db(db_session: AsyncSession):
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


async def _make_user(db_session: AsyncSession, tag: str) -> User:
    user = User(
        email=f"mm-{tag}-{uuid.uuid4().hex[:8]}@example.com",
        display_name=f"Matter Memory {tag}",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_project(
    db_session: AsyncSession, owner: User, *, archived: bool = False
) -> Project:
    project = Project(
        owner_id=owner.id,
        name="Pin Matter",
        slug=f"pin-{uuid.uuid4().hex[:6]}",
        privileged=False,
        minimum_inference_tier=None,
    )
    db_session.add(project)
    await db_session.flush()
    if archived:
        from datetime import UTC, datetime

        project.archived_at = datetime.now(UTC)
        await db_session.flush()
    return project


@pytest_asyncio.fixture
async def db_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "owner")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "other")


def _h(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email, is_admin=False)}"}


def _url(project_id: uuid.UUID) -> str:
    return f"/api/v1/matters/{project_id}/memory/corrections"


async def test_pin_unauthenticated_401(client: AsyncClient) -> None:
    # The router-level ActiveUser gate fires before the handler — no project needed.
    resp = await client.post(_url(uuid.uuid4()), json={"body_md": "x"})
    assert resp.status_code == 401


async def test_pin_creates_human_pinned_with_session_author(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(
        _url(project.id),
        json={"body_md": "  We are the BUYER; counterparty counsel is Smith Crowell.  "},
        headers=_h(db_user),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["trust"] == "human-pinned"
    assert body["project_id"] == str(project.id)
    # str_strip_whitespace trimmed the body before persist.
    assert body["body_md"] == "We are the BUYER; counterparty counsel is Smith Crowell."

    row = (
        await db_session.execute(
            select(MatterMemoryEntry).where(MatterMemoryEntry.project_id == project.id)
        )
    ).scalar_one()
    assert row.kind == "correction"
    assert row.trust == "human-pinned"
    # Author comes from the session, NOT from any request field (B2).
    assert row.user_id == db_user.id
    assert row.run_id is None


async def test_pin_cross_user_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User, other_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    # other_user does not own the matter → 404, never 403 (no existence leak).
    resp = await client.post(_url(project.id), json={"body_md": "sneaky"}, headers=_h(other_user))
    assert resp.status_code == 404
    # Nothing written.
    rows = (
        (
            await db_session.execute(
                select(MatterMemoryEntry).where(MatterMemoryEntry.project_id == project.id)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


async def test_pin_archived_matter_is_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user, archived=True)
    resp = await client.post(
        _url(project.id), json={"body_md": "for an archived matter"}, headers=_h(db_user)
    )
    assert resp.status_code == 404


async def test_pin_blank_body_is_422(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(_url(project.id), json={"body_md": "   "}, headers=_h(db_user))
    assert resp.status_code == 422


async def test_pin_oversize_body_is_422(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(
        _url(project.id),
        json={"body_md": "x" * (CORRECTION_MAX_CHARS + 1)},
        headers=_h(db_user),
    )
    assert resp.status_code == 422


async def test_pin_audit_carries_no_body(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    marker = "QUOKKA-secret-clause-text"
    resp = await client.post(
        _url(project.id), json={"body_md": f"Pinned fact: {marker}"}, headers=_h(db_user)
    )
    assert resp.status_code == 201, resp.text

    audit = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "matter_memory.pin", AuditLog.user_id == db_user.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    details = str(audit[0].details)
    assert "entry_id" in details and "body_chars" in details
    assert marker not in details  # the correction body never reaches the audit row
