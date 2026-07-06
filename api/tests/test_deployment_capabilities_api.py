"""The old Capabilities page as a compatibility shim over the Org Library — STORE-1 (ADR-F065).

GET /admin/capabilities returns the catalog inventory (every registry tool group + registry
skill + live playbook) with each one's Library membership (``in_library``; ``enabled`` is the
deprecated alias); PATCH maps the old on/off writes onto the Library (enabled=true ⇒ adopt,
enabled=false ⇒ remove). These prove:

* AdminUser only (a non-admin is 403),
* the inventory lists every code-registry tool group with ``in_library`` (all adopted here,
  from the conftest seed that emulates an upgraded deployment),
* a PATCH enabled=false REMOVES the org_library_entries row; enabled=true ADOPTS it (upsert),
* the boundary rejects an unknown (kind, key) against the registry/DB (422),
* the audit row (``library.update``) carries kinds/keys/counts only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.playbook import Playbook
from app.models.practice_area import OrgLibraryEntry
from app.models.user import User
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration

_URL = "/api/v1/admin/capabilities"


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
    assert [s["kind"] for s in body["sections"]] == ["tool", "skill", "playbook"]
    # Every code-registry tool group is listed, in registry order.
    assert _keys(body, "tool") == ["redlining", "tabular", "ropa", "assessment"]
    # The conftest seed (upgraded-deployment emulation) adopted all four → in_library True,
    # and enabled is the deprecated alias for it.
    for e in _section(body, "tool")["entries"]:
        assert e["in_library"] is True
        assert e["enabled"] == e["in_library"]


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


async def test_patch_rejects_bad_kind_at_schema(client: AsyncClient, admin: User) -> None:
    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "mcp", "key": "x", "enabled": False}]},
    )
    assert resp.status_code == 422  # Literal[skill|tool|playbook] rejects 'mcp'


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
