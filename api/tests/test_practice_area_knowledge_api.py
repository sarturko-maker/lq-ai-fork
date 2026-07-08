"""Admin knowledge-collection attach/detach to a practice area (ADR-F067 D1, B-3).

Mirrors the playbook/tool-group attach/detach surfaces: a knowledge collection bound to
an area becomes AVAILABLE to the area's runs (the guarded ``search_knowledge`` tool
searches every bound + adopted collection). Admin-only; validated against the
(non-archived) ``knowledge_bases`` rows; the collection must also be adopted into the
Org Library (ADR-F065 D4, 422, distinct from the 404-unknown/archived check); re-attach
is 409; detach is idempotent; audit rows carry ids only.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.knowledge import KnowledgeBase
from app.models.practice_area import OrgLibraryEntry, PracticeArea, PracticeAreaKnowledgeBase
from app.models.user import User
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="pa-kb-admin")
    u.is_admin = True
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="pa-kb-user")


async def _make_kb(
    db: AsyncSession, owner: User, *, adopt: bool = True, archived: bool = False
) -> KnowledgeBase:
    """A knowledge collection owned by ``owner``. ``adopt`` (default) also adds it to the
    Org Library so the attach passes the ADR-F065 D4 Library check — the not-adopted path
    is tested with ``adopt=False``. ``archived`` sets ``archived_at`` — the 404 path."""
    kb = KnowledgeBase(owner_id=owner.id, name="Company handbook", description="HR policies.")
    if archived:
        kb.archived_at = datetime.now(UTC)
    db.add(kb)
    await db.flush()
    if adopt:
        db.add(OrgLibraryEntry(capability_kind="knowledge", capability_key=str(kb.id)))
        await db.flush()
    return kb


def _url(key: str) -> str:
    return f"/api/v1/practice-areas/{key}/knowledge-bases"


async def test_attach_creates_binding(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    kb = await _make_kb(db_session, admin)
    resp = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    assert resp.status_code == 204

    area_id = (
        await db_session.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
    ).scalar_one()
    binding = (
        await db_session.execute(
            select(PracticeAreaKnowledgeBase).where(
                PracticeAreaKnowledgeBase.practice_area_id == area_id,
                PracticeAreaKnowledgeBase.knowledge_base_id == kb.id,
            )
        )
    ).scalar_one_or_none()
    assert binding is not None


async def test_read_model_includes_bound_knowledge_base(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    """The area read model (``GET /practice-areas``) gains ``bound_knowledge_bases``
    (id + name) alongside ``bound_playbooks``/``bound_tool_groups``."""
    kb = await _make_kb(db_session, admin)
    attach = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    assert attach.status_code == 204

    resp = await client.get("/api/v1/practice-areas", headers=_bearer(admin))
    assert resp.status_code == 200
    row = next(a for a in resp.json()["practice_areas"] if a["key"] == "commercial")
    assert row["bound_knowledge_bases"] == [{"id": str(kb.id), "name": kb.name}]


async def test_attach_unknown_kb_is_404(client: AsyncClient, admin: User) -> None:
    resp = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404


async def test_attach_archived_kb_is_404(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    kb = await _make_kb(db_session, admin, archived=True)
    resp = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    assert resp.status_code == 404


async def test_attach_not_in_library_is_422(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    """ADR-F065 D4: a live but NOT-adopted collection is a 422 pointing at the Store — a
    DISTINCT layer from the 404-unknown/archived check above."""
    kb = await _make_kb(db_session, admin, adopt=False)
    resp = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    assert resp.status_code == 422


async def test_attach_unknown_area_is_404(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    kb = await _make_kb(db_session, admin)
    resp = await client.post(
        _url("no-such-area"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    assert resp.status_code == 404


async def test_attach_requires_admin(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    kb = await _make_kb(db_session, user)
    resp = await client.post(
        _url("commercial"), headers=_bearer(user), json={"knowledge_base_id": str(kb.id)}
    )
    assert resp.status_code == 403


async def test_reattach_is_409(client: AsyncClient, db_session: AsyncSession, admin: User) -> None:
    kb = await _make_kb(db_session, admin)
    first = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    assert first.status_code == 204
    second = await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    assert second.status_code == 409


async def test_detach_removes_binding_and_is_idempotent(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    kb = await _make_kb(db_session, admin)
    await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )

    detach = await client.delete(f"{_url('commercial')}/{kb.id}", headers=_bearer(admin))
    assert detach.status_code == 204

    area_id = (
        await db_session.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
    ).scalar_one()
    gone = (
        await db_session.execute(
            select(PracticeAreaKnowledgeBase).where(
                PracticeAreaKnowledgeBase.practice_area_id == area_id,
                PracticeAreaKnowledgeBase.knowledge_base_id == kb.id,
            )
        )
    ).scalar_one_or_none()
    assert gone is None

    # Detaching again is a no-op 204.
    again = await client.delete(f"{_url('commercial')}/{kb.id}", headers=_bearer(admin))
    assert again.status_code == 204


async def test_attach_audit_is_ids_only(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    kb = await _make_kb(db_session, admin)
    await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    row = (
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.action == "practice_area.knowledge_attach")
                .order_by(AuditLog.timestamp.desc())
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert row.resource_id == "commercial"
    assert row.details == {"knowledge_base_id": str(kb.id)}


async def test_detach_audit_is_ids_only(
    client: AsyncClient, db_session: AsyncSession, admin: User
) -> None:
    kb = await _make_kb(db_session, admin)
    await client.post(
        _url("commercial"), headers=_bearer(admin), json={"knowledge_base_id": str(kb.id)}
    )
    await client.delete(f"{_url('commercial')}/{kb.id}", headers=_bearer(admin))
    row = (
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.action == "practice_area.knowledge_detach")
                .order_by(AuditLog.timestamp.desc())
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert row.resource_id == "commercial"
    assert row.details == {"knowledge_base_id": str(kb.id)}
