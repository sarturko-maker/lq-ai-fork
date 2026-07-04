"""Deployment-wide (Level 0) capability toggle endpoints — SETUP-4a (ADR-F062).

GET /admin/capabilities returns the whole-deployment inventory (every registry tool
group + registry skill + live playbook) with each one's effective Level-0 enabled state;
PATCH writes the org-admin's sparse toggles. These prove:

* AdminUser only (a non-admin is 403),
* the inventory lists every code-registry tool group (skills empty here — no registry
  installed in the ASGI test, the graceful-None posture),
* a PATCH toggle is persisted and reflected on the echoed GET (Level 0 narrows),
* the boundary rejects an unknown (kind, key) against the registry/DB (422),
* the audit row (``deployment.capability_toggle``) carries kinds/keys/enabled only.
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
from app.models.practice_area import DeploymentCapabilityToggle
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


async def test_get_lists_registry_tool_groups(client: AsyncClient, admin: User) -> None:
    resp = await client.get(_URL, headers=_bearer(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert [s["kind"] for s in body["sections"]] == ["tool", "skill", "playbook"]
    # Every code-registry tool group is listed, in registry order, all enabled by default.
    assert _keys(body, "tool") == ["redlining", "tabular", "ropa", "assessment"]
    assert all(e["enabled"] for e in _section(body, "tool")["entries"])


async def test_get_requires_admin(client: AsyncClient, user: User) -> None:
    resp = await client.get(_URL, headers=_bearer(user))
    assert resp.status_code == 403


async def test_patch_disables_a_tool_group_and_persists(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "tool", "key": "ropa", "enabled": False}]},
    )
    assert resp.status_code == 200
    # The echoed inventory reflects the disable.
    ropa = next(
        e for e in _section(resp.json(), "tool")["entries"] if e["capability_key"] == "ropa"
    )
    assert ropa["enabled"] is False
    # Persisted with set_by from the session.
    row = (
        await db_session.execute(
            select(DeploymentCapabilityToggle).where(
                DeploymentCapabilityToggle.capability_kind == "tool",
                DeploymentCapabilityToggle.capability_key == "ropa",
            )
        )
    ).scalar_one()
    assert row.enabled is False and row.set_by == admin.id


async def test_patch_re_enable_is_upsert(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
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
                select(DeploymentCapabilityToggle).where(
                    DeploymentCapabilityToggle.capability_key == "tabular"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].enabled is True  # upsert, not a second row


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


async def test_patch_accepts_live_playbook(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    pb = Playbook(name="Dep Test Book", contract_type="NDA", description="")
    db_session.add(pb)
    await db_session.flush()
    resp = await client.patch(
        _URL,
        headers=_bearer(admin),
        json={"toggles": [{"kind": "playbook", "key": str(pb.id), "enabled": False}]},
    )
    assert resp.status_code == 200


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
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "deployment.capability_toggle")
        )
    ).scalar_one()
    # kinds/keys/enabled only — no values/content.
    assert row.details["toggle_count"] == 1
    assert row.details["toggles"] == [{"kind": "tool", "key": "ropa", "enabled": False}]
