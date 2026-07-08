"""The old Capabilities page as a compatibility shim over the Org Library — STORE-1 (ADR-F065).

GET /admin/capabilities returns the catalog inventory (every registry tool group + registry
skill + live playbook + non-archived knowledge collection, ADR-F067 D1) with each one's
Library membership (``in_library``; ``enabled`` is the deprecated alias); PATCH maps the old
on/off writes onto the Library (enabled=true ⇒ adopt, enabled=false ⇒ remove). These prove:

* AdminUser only (a non-admin is 403),
* the inventory lists every code-registry tool group with ``in_library`` (all adopted here,
  from the conftest seed that emulates an upgraded deployment),
* a PATCH enabled=false REMOVES the org_library_entries row; enabled=true ADOPTS it (upsert),
* the boundary rejects an unknown (kind, key) against the registry/DB (422),
* the audit row (``library.update``) carries kinds/keys/counts only.
"""

from __future__ import annotations

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

_URL = "/api/v1/admin/capabilities"
_REAL_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="depcap-user")


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="depcap-admin")
    u.is_admin = True
    await db_session.flush()
    return u


def _section(body: dict, kind: str) -> dict:
    return next(s for s in body["sections"] if s["kind"] == kind)


def _keys(body: dict, kind: str) -> list[str]:
    return [e["capability_key"] for e in _section(body, kind)["entries"]]


async def test_get_lists_registry_tool_groups_with_library_membership(
    client: AsyncClient, admin: User
) -> None:
    resp = await client.get(_URL, headers=_bearer(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert [s["kind"] for s in body["sections"]] == ["tool", "skill", "playbook", "knowledge"]
    # Every code-registry tool group is listed, in registry order.
    assert _keys(body, "tool") == ["redlining", "tabular", "ropa", "assessment"]
    # The conftest seed (upgraded-deployment emulation) adopted all four → in_library True,
    # and enabled is the deprecated alias for it.
    for e in _section(body, "tool")["entries"]:
        assert e["in_library"] is True
        assert e["enabled"] == e["in_library"]


async def test_tool_entries_carry_recommended_for_and_source(
    client: AsyncClient, admin: User
) -> None:
    """STORE-2 D-A: additive `source`/`recommended_for` fields on tool entries.

    Tool entries are `source="built-in"` always (no adopt/registry state affects
    provenance); `recommended_for` is sourced from `RECOMMENDED_LIBRARY_SETS`
    (commercial -> redlining+tabular, privacy -> ropa+assessment).
    """
    resp = await client.get(_URL, headers=_bearer(admin))
    body = resp.json()
    by_key = {e["capability_key"]: e for e in _section(body, "tool")["entries"]}
    assert by_key["redlining"]["source"] == "built-in"
    assert by_key["redlining"]["recommended_for"] == ["commercial"]
    assert by_key["tabular"]["recommended_for"] == ["commercial"]
    assert by_key["ropa"]["recommended_for"] == ["privacy"]
    assert by_key["assessment"]["recommended_for"] == ["privacy"]
    # A tool group has no author/version — those are skill-only fields.
    assert by_key["redlining"]["author"] is None
    assert by_key["redlining"]["version"] is None


async def test_skill_entries_carry_provenance_from_the_real_registry(
    client: AsyncClient, admin: User
) -> None:
    """A real built-in skill's source/author/version/tags/recommended_for surface."""
    if not _REAL_SKILLS_DIR.is_dir():
        pytest.skip(f"real skills directory not present: {_REAL_SKILLS_DIR}")

    prior = getattr(app.state, "skill_registry", None)
    app.state.skill_registry = MutableSkillRegistry(load_registry(_REAL_SKILLS_DIR))
    try:
        resp = await client.get(_URL, headers=_bearer(admin))
        body = resp.json()
        by_key = {e["capability_key"]: e for e in _section(body, "skill")["entries"]}
        nda = by_key["nda-review"]
        assert nda["source"] == "built-in"
        assert nda["author"] == "LegalQuants"
        assert nda["version"] == "1.0.1"
        assert set(nda["recommended_for"]) == {"commercial", "m-and-a", "employment"}
    finally:
        if prior is None:
            delattr(app.state, "skill_registry")
        else:
            app.state.skill_registry = prior


async def test_playbook_entries_have_no_source(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    """Playbooks carry no provenance field today (D-A) — `source` stays None."""
    pb = Playbook(name="Prov Test Book", contract_type="NDA", description="")
    db_session.add(pb)
    await db_session.flush()
    resp = await client.get(_URL, headers=_bearer(admin))
    body = resp.json()
    entry = next(
        e for e in _section(body, "playbook")["entries"] if e["capability_key"] == str(pb.id)
    )
    assert entry["source"] is None
    assert entry["recommended_for"] == []


async def test_knowledge_entries_have_no_source_and_skip_archived(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    """Knowledge collections carry no provenance field either (mirrors playbooks, D-A) —
    `source` stays None; an archived collection is dropped from the inventory entirely
    (ADR-F067 D1, same drift-drop posture as a deleted playbook)."""
    live = KnowledgeBase(owner_id=admin.id, name="Prov Test KB", description="")
    archived = KnowledgeBase(owner_id=admin.id, name="Archived KB", description="")
    archived.archived_at = datetime.now(UTC)
    db_session.add_all([live, archived])
    await db_session.flush()
    resp = await client.get(_URL, headers=_bearer(admin))
    body = resp.json()
    keys = _keys(body, "knowledge")
    assert str(live.id) in keys
    assert str(archived.id) not in keys
    entry = next(
        e for e in _section(body, "knowledge")["entries"] if e["capability_key"] == str(live.id)
    )
    assert entry["label"] == "Prov Test KB"
    assert entry["source"] is None
    assert entry["recommended_for"] == []


async def test_get_requires_admin(client: AsyncClient, user: User) -> None:
    resp = await client.get(_URL, headers=_bearer(user))
    assert resp.status_code == 403


async def test_patch_disable_removes_from_library(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "tool", "key": "ropa", "enabled": False}]},
    )
    assert resp.status_code == 200
    # The echoed inventory reflects the removal.
    ropa = next(
        e for e in _section(resp.json(), "tool")["entries"] if e["capability_key"] == "ropa"
    )
    assert ropa["in_library"] is False and ropa["enabled"] is False
    # The Library row is gone (removed, not disable-flagged).
    row = (
        await db_session.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "tool",
                OrgLibraryEntry.capability_key == "ropa",
            )
        )
    ).scalar_one_or_none()
    assert row is None


async def test_patch_adopt_then_remove_is_single_row(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    # Remove tabular, then re-adopt it: exactly one Library row, present.
    await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "tool", "key": "tabular", "enabled": False}]},
    )
    await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "tool", "key": "tabular", "enabled": True}]},
    )
    rows = (
        (
            await db_session.execute(
                select(OrgLibraryEntry).where(
                    OrgLibraryEntry.capability_kind == "tool",
                    OrgLibraryEntry.capability_key == "tabular",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].adopted_by == admin.id  # upsert, records the admin


async def test_patch_rejects_unknown_tool_group(client: AsyncClient, admin: User) -> None:
    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "tool", "key": "not-a-group", "enabled": False}]},
    )
    assert resp.status_code == 422


async def test_patch_rejects_unknown_playbook(client: AsyncClient, admin: User) -> None:
    import uuid

    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "playbook", "key": str(uuid.uuid4()), "enabled": False}]},
    )
    assert resp.status_code == 422


async def test_patch_rejects_unknown_knowledge_base(client: AsyncClient, admin: User) -> None:
    import uuid

    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "knowledge", "key": str(uuid.uuid4()), "enabled": False}]},
    )
    assert resp.status_code == 422


async def test_patch_rejects_bad_kind_at_schema(client: AsyncClient, admin: User) -> None:
    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "mcp", "key": "x", "enabled": False}]},
    )
    assert resp.status_code == 422  # Literal[skill|tool|playbook|knowledge] rejects 'mcp'


async def test_patch_adopts_live_playbook(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    pb = Playbook(name="Dep Test Book", contract_type="NDA", description="")
    db_session.add(pb)
    await db_session.flush()
    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "playbook", "key": str(pb.id), "enabled": True}]},
    )
    assert resp.status_code == 200
    row = (
        await db_session.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "playbook",
                OrgLibraryEntry.capability_key == str(pb.id),
            )
        )
    ).scalar_one_or_none()
    assert row is not None


async def test_patch_adopts_live_knowledge_base(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    kb = KnowledgeBase(owner_id=admin.id, name="Dep Test KB", description="")
    db_session.add(kb)
    await db_session.flush()
    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "knowledge", "key": str(kb.id), "enabled": True}]},
    )
    assert resp.status_code == 200
    row = (
        await db_session.execute(
            select(OrgLibraryEntry).where(
                OrgLibraryEntry.capability_kind == "knowledge",
                OrgLibraryEntry.capability_key == str(kb.id),
            )
        )
    ).scalar_one_or_none()
    assert row is not None


async def test_patch_requires_admin(client: AsyncClient, user: User) -> None:
    resp = await client.patch(
        _URL,
        headers=_bearer(user),
        json={"toggles": [{"kind": "tool", "key": "ropa", "enabled": False}]},
    )
    assert resp.status_code == 403


async def test_patch_audit_is_body_free(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "tool", "key": "ropa", "enabled": False}]},
    )
    row = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "library.update"))
    ).scalar_one()
    # kinds/keys/counts only — no values/content.
    assert row.details["removed_count"] == 1
    assert row.details["adopted_count"] == 0
    assert row.details["removed"] == [{"kind": "tool", "key": "ropa"}]
