"""Org Library adopt/remove endpoints — STORE-1 (ADR-F065).

POST /admin/library adopts one catalog capability into the org's Library; DELETE
/admin/library/{kind}/{key} removes it. These prove:

* AdminUser only (a non-admin member/viewer is 403, before any lookup),
* adopting a valid capability is 204 and records ``adopted_by``,
* re-adopting an already-adopted capability is 409 (the house attach pattern),
* removing is idempotent (a not-adopted capability is a no-op 204),
* an unknown (kind, key) is rejected 422 per kind (tool/skill/playbook/knowledge),
* the audit rows (``library.adopt`` / ``library.remove``) carry kind/key only.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.knowledge import KnowledgeBase
from app.models.playbook import Playbook
from app.models.practice_area import OrgLibraryEntry
from app.models.user import User
from app.skills import load_registry
from app.skills.registry import MutableSkillRegistry
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration

_URL = "/api/v1/admin/library"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "skills"


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="lib-admin")
    u.is_admin = True
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def member(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="lib-member")


async def _make_playbook(db: AsyncSession) -> Playbook:
    pb = Playbook(name="Lib NDA playbook", contract_type="NDA", description="")
    db.add(pb)
    await db.flush()
    return pb


async def _make_kb(db: AsyncSession, owner: User) -> KnowledgeBase:
    kb = KnowledgeBase(owner_id=owner.id, name="Lib knowledge collection", description="")
    db.add(kb)
    await db.flush()
    return kb


# --- adopt -------------------------------------------------------------------
async def test_adopt_playbook_204_records_admin(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session)
    resp = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "playbook", "key": str(pb.id)}
    )
    assert resp.status_code == 204
    row = (
        await db_session.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "playbook",
                OrgLibraryEntry.capability_key == str(pb.id),
            )
        )
    ).scalar_one()
    assert row.adopted_by == admin.id


async def test_adopt_duplicate_is_409(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session)
    first = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "playbook", "key": str(pb.id)}
    )
    assert first.status_code == 204
    second = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "playbook", "key": str(pb.id)}
    )
    assert second.status_code == 409


async def test_adopt_skill_with_registry_204(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    # A fixture skill (registry-known) that the conftest seed did NOT adopt.
    prior = getattr(app.state, "skill_registry", None)
    app.state.skill_registry = MutableSkillRegistry(load_registry(_FIXTURES_DIR))
    try:
        resp = await client.post(
            _URL, headers=_bearer(admin), json={"kind": "skill", "key": "alpha-test-skill"}
        )
        assert resp.status_code == 204
        row = (
            await db_session.execute(
                select(OrgLibraryEntry).where(
                    OrgLibraryEntry.capability_kind == "skill",
                    OrgLibraryEntry.capability_key == "alpha-test-skill",
                )
            )
        ).scalar_one_or_none()
        assert row is not None
    finally:
        if prior is None:
            delattr(app.state, "skill_registry")
        else:
            app.state.skill_registry = prior


async def test_adopt_unknown_tool_group_is_422(client: AsyncClient, admin: User) -> None:
    resp = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "tool", "key": "not-a-group"}
    )
    assert resp.status_code == 422


async def test_adopt_composition_only_group_as_tool_is_422(
    client: AsyncClient, admin: User
) -> None:
    """F067 B-3: the derived knowledge group is composition-only — it is registered so
    composition can build it, but it is NOT a kind='tool' catalog entry, so adopting it
    as a tool is rejected exactly like an unknown key."""
    resp = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "tool", "key": "knowledge"}
    )
    assert resp.status_code == 422


async def test_adopt_unknown_playbook_is_422(client: AsyncClient, admin: User) -> None:
    resp = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "playbook", "key": str(uuid.uuid4())}
    )
    assert resp.status_code == 422


async def test_adopt_knowledge_base_204_records_admin(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    kb = await _make_kb(db_session, admin)
    resp = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "knowledge", "key": str(kb.id)}
    )
    assert resp.status_code == 204
    row = (
        await db_session.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "knowledge",
                OrgLibraryEntry.capability_key == str(kb.id),
            )
        )
    ).scalar_one()
    assert row.adopted_by == admin.id


async def test_adopt_unknown_knowledge_base_is_422(client: AsyncClient, admin: User) -> None:
    resp = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "knowledge", "key": str(uuid.uuid4())}
    )
    assert resp.status_code == 422


async def test_adopt_archived_knowledge_base_is_422(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    kb = await _make_kb(db_session, admin)
    kb.archived_at = datetime.now(UTC)
    await db_session.flush()
    resp = await client.post(
        _URL, headers=_bearer(admin), json={"kind": "knowledge", "key": str(kb.id)}
    )
    assert resp.status_code == 422


async def test_adopt_skill_without_registry_is_422(client: AsyncClient, admin: User) -> None:
    # No registry installed in the ASGI test ⇒ a skill adopt cannot be validated ⇒ 422.
    prior = getattr(app.state, "skill_registry", None)
    if prior is not None:
        delattr(app.state, "skill_registry")
    try:
        resp = await client.post(
            _URL, headers=_bearer(admin), json={"kind": "skill", "key": "anything"}
        )
        assert resp.status_code == 422
    finally:
        if prior is not None:
            app.state.skill_registry = prior


async def test_adopt_rejects_bad_kind_at_schema(client: AsyncClient, admin: User) -> None:
    resp = await client.post(_URL, headers=_bearer(admin), json={"kind": "mcp", "key": "x"})
    assert resp.status_code == 422  # Literal[skill|tool|playbook|knowledge] rejects 'mcp'


async def test_adopt_requires_admin(
    client: AsyncClient, member: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session)
    resp = await client.post(
        _URL, headers=_bearer(member), json={"kind": "playbook", "key": str(pb.id)}
    )
    assert resp.status_code == 403


async def test_adopt_audit_is_body_free(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session)
    await client.post(_URL, headers=_bearer(admin), json={"kind": "playbook", "key": str(pb.id)})
    row = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "library.adopt"))
    ).scalar_one()
    assert row.details == {"kind": "playbook", "key": str(pb.id)}


# --- remove ------------------------------------------------------------------
async def test_remove_is_idempotent(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    pb = await _make_playbook(db_session)
    await client.post(_URL, headers=_bearer(admin), json={"kind": "playbook", "key": str(pb.id)})

    first = await client.delete(f"{_URL}/playbook/{pb.id}", headers=_bearer(admin))
    assert first.status_code == 204
    gone = (
        await db_session.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "playbook",
                OrgLibraryEntry.capability_key == str(pb.id),
            )
        )
    ).scalar_one_or_none()
    assert gone is None

    # Removing again is a no-op 204.
    again = await client.delete(f"{_URL}/playbook/{pb.id}", headers=_bearer(admin))
    assert again.status_code == 204


async def test_remove_knowledge_base_is_idempotent(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    kb = await _make_kb(db_session, admin)
    await client.post(_URL, headers=_bearer(admin), json={"kind": "knowledge", "key": str(kb.id)})

    first = await client.delete(f"{_URL}/knowledge/{kb.id}", headers=_bearer(admin))
    assert first.status_code == 204
    gone = (
        await db_session.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "knowledge",
                OrgLibraryEntry.capability_key == str(kb.id),
            )
        )
    ).scalar_one_or_none()
    assert gone is None

    # Removing again is a no-op 204.
    again = await client.delete(f"{_URL}/knowledge/{kb.id}", headers=_bearer(admin))
    assert again.status_code == 204


async def test_remove_rejects_bad_kind_at_path(client: AsyncClient, admin: User) -> None:
    resp = await client.delete(f"{_URL}/mcp/x", headers=_bearer(admin))
    assert resp.status_code == 422  # path Literal[skill|tool|playbook|knowledge] rejects 'mcp'


async def test_remove_requires_admin(client: AsyncClient, member: User) -> None:
    resp = await client.delete(f"{_URL}/tool/redlining", headers=_bearer(member))
    assert resp.status_code == 403


async def test_remove_audit_is_body_free(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    await client.delete(f"{_URL}/tool/ropa", headers=_bearer(admin))
    row = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "library.remove"))
    ).scalar_one()
    assert row.details == {"kind": "tool", "key": "ropa"}
