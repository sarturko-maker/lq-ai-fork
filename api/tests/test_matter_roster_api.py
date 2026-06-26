"""Matter authorship-roster endpoint tests (ADR-F048).

The human-authenticated who-is-who surface — the only writer of a ``trust='confirmed'``
participant. These tests prove:

* a create/edit is written ``trust='confirmed'`` with ``user_id`` from the SESSION
  (B2: the trust label is structurally true, not claimed),
* per-user isolation — a cross-user / archived matter is 404 (never 403); the
  id+project lookup 404s a cross-matter entry id,
* a partial edit applies only the present fields and (re)confirms the entry,
* retire is soft (drops off the active roster, second retire 404s),
* the composite ``GET /matters/{id}/memory`` embeds the active roster,
* reject-at-the-boundary — a bad ``side`` is 422,
* the audit rows (``matter_roster.*``) carry IDs/side only — never the name/role text.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.project import MatterParticipant, Project
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
        email=f"ros-{tag}-{uuid.uuid4().hex[:8]}@example.com",
        display_name=f"Roster {tag}",
        hashed_password=hash_password("correct-horse-battery-staple"),
        is_admin=False,
        mfa_enabled=False,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_project(db_session: AsyncSession, owner: User) -> Project:
    project = Project(
        owner_id=owner.id,
        name="Roster Matter",
        slug=f"ros-{uuid.uuid4().hex[:6]}",
        privileged=False,
        minimum_inference_tier=None,
    )
    db_session.add(project)
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


def _roster_url(project_id: uuid.UUID) -> str:
    return f"/api/v1/matters/{project_id}/roster"


async def test_create_unauthenticated_401(client: AsyncClient) -> None:
    resp = await client.post(_roster_url(uuid.uuid4()), json={"display_name": "X", "side": "ours"})
    assert resp.status_code == 401


async def test_create_writes_confirmed_with_session_author(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(
        _roster_url(project.id),
        json={
            "display_name": "Jane Smith",
            "side": "ours",
            "role_label": "Lead counsel",
            "organization": "Acme LLP",
            "aliases": ["Jane Smith", "jsmith@acme.com"],
            "source_citation": "From the engagement letter",
        },
        headers=_h(db_user),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["side"] == "ours"
    assert body["trust"] == "confirmed"
    assert body["role_label"] == "Lead counsel"
    # The display name is matched implicitly, not duplicated into aliases.
    assert "jsmith@acme.com" in body["aliases"]
    assert "Jane Smith" not in body["aliases"]

    row = (
        await db_session.execute(
            select(MatterParticipant).where(MatterParticipant.project_id == project.id)
        )
    ).scalar_one()
    assert row.trust == "confirmed"
    assert row.user_id == db_user.id  # author from the session, never a request field


async def test_create_cross_user_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User, other_user: User
) -> None:
    project = await _make_project(db_session, other_user)  # not the caller's
    resp = await client.post(
        _roster_url(project.id),
        json={"display_name": "X", "side": "ours"},
        headers=_h(db_user),
    )
    assert resp.status_code == 404


async def test_create_rejects_invalid_side_422(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(
        _roster_url(project.id),
        json={"display_name": "X", "side": "enemy"},
        headers=_h(db_user),
    )
    assert resp.status_code == 422


async def test_update_partial_confirms_and_keeps_other_fields(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    # Seed an agent-inferred row directly.
    entry = MatterParticipant(
        project_id=project.id,
        user_id=db_user.id,
        display_name="Mark Counsel",
        side="unknown",
        aliases=["mc@beta.com"],
        trust="inferred",
    )
    db_session.add(entry)
    await db_session.flush()

    resp = await client.patch(
        f"{_roster_url(project.id)}/{entry.id}",
        json={"side": "counterparty"},  # only side
        headers=_h(db_user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["side"] == "counterparty"
    assert body["trust"] == "confirmed"  # a human edit confirms it
    assert body["display_name"] == "Mark Counsel"  # untouched field preserved
    assert "mc@beta.com" in body["aliases"]


async def test_update_replaces_aliases(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    entry = MatterParticipant(
        project_id=project.id,
        user_id=db_user.id,
        display_name="Jane Smith",
        side="ours",
        aliases=["old@acme.com"],
        trust="confirmed",
    )
    db_session.add(entry)
    await db_session.flush()

    resp = await client.patch(
        f"{_roster_url(project.id)}/{entry.id}",
        json={"aliases": ["new@acme.com", "Jane Smith"]},
        headers=_h(db_user),
    )
    assert resp.status_code == 200, resp.text
    aliases = resp.json()["aliases"]
    assert aliases == ["new@acme.com"]  # replaced; display name excluded


async def test_update_rename_with_aliases_preserves_old_name(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    """SF2: a simultaneous rename + aliases edit (what the panel always sends) must keep
    the OLD name as an alias so prior edits under it still match."""
    project = await _make_project(db_session, db_user)
    entry = MatterParticipant(
        project_id=project.id,
        user_id=db_user.id,
        display_name="Jane",
        side="ours",
        aliases=["jsmith@acme.com"],
        trust="inferred",
    )
    db_session.add(entry)
    await db_session.flush()

    resp = await client.patch(
        f"{_roster_url(project.id)}/{entry.id}",
        json={"display_name": "Jane Smith", "aliases": ["jsmith@acme.com"]},
        headers=_h(db_user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["display_name"] == "Jane Smith"
    # The old display name 'Jane' is folded into aliases (not clobbered by the replace).
    assert "Jane" in body["aliases"]
    assert "jsmith@acme.com" in body["aliases"]


async def test_retire_is_soft_then_404(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    entry = MatterParticipant(
        project_id=project.id,
        user_id=db_user.id,
        display_name="Temp Person",
        side="unknown",
        trust="inferred",
    )
    db_session.add(entry)
    await db_session.flush()
    entry_id = entry.id

    resp = await client.post(f"{_roster_url(project.id)}/{entry_id}/retire", headers=_h(db_user))
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == str(entry_id)

    # The row is soft-retired (still present, superseded_at set) but reads as absent.
    row = (
        await db_session.execute(select(MatterParticipant).where(MatterParticipant.id == entry_id))
    ).scalar_one()
    assert row.superseded_at is not None

    # A second retire 404s (an already-retired entry reads as absent).
    again = await client.post(f"{_roster_url(project.id)}/{entry_id}/retire", headers=_h(db_user))
    assert again.status_code == 404


async def test_composite_memory_get_includes_roster(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    created = await client.post(
        _roster_url(project.id),
        json={"display_name": "Jane Smith", "side": "ours"},
        headers=_h(db_user),
    )
    assert created.status_code == 201

    resp = await client.get(f"/api/v1/matters/{project.id}/memory", headers=_h(db_user))
    assert resp.status_code == 200, resp.text
    roster = resp.json()["roster"]
    assert len(roster) == 1
    assert roster[0]["display_name"] == "Jane Smith"
    assert roster[0]["side"] == "ours"


async def test_audit_carries_ids_and_side_only(
    client: AsyncClient, db_session: AsyncSession, db_user: User
) -> None:
    project = await _make_project(db_session, db_user)
    resp = await client.post(
        _roster_url(project.id),
        json={"display_name": "Jane Secret-Name", "side": "ours", "role_label": "Secret-Role"},
        headers=_h(db_user),
    )
    assert resp.status_code == 201

    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "matter_roster.create",
                    AuditLog.user_id == db_user.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    details = str(rows[0].details)
    assert "side" in details and "entry_id" in details
    assert "Secret-Name" not in details  # no name text
    assert "Secret-Role" not in details  # no role text
