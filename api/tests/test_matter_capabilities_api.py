"""Capability-panel endpoint tests — per-matter capability toggles (ADR-F054).

GET returns the area's available capabilities with each one's resolved on/off state;
PUT writes the lawyer's sparse toggles. These prove:

* defaults are all-on (a never-touched matter behaves like today),
* a PUT toggle is persisted with ``set_by`` from the session and reflected on GET,
* per-user isolation — cross-user / unfiled matters behave correctly (404 / empty),
* the boundary rejects an unknown / non-toggleable (MCP) / unbound capability (422),
* the audit row (``matter.capability_toggle``) carries counts/kinds/keys only.

The skill registry is not installed in this ASGI test, so the skills SECTION is empty
here by design (graceful None registry) — skill enable/disable is covered by the pure
``test_capabilities`` tests and the composition tests (which inject a registry).
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
from app.models.playbook import Playbook
from app.models.practice_area import PracticeArea, PracticeAreaPlaybook
from app.models.project import MatterCapabilityToggle, Project
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
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="cap-owner")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="cap-other")


async def _commercial_area_id(db: AsyncSession) -> uuid.UUID:
    return (
        await db.execute(select(PracticeArea.id).where(PracticeArea.key == "commercial"))
    ).scalar_one()


async def _make_matter(db: AsyncSession, owner: User, *, area_id: uuid.UUID | None) -> Project:
    project = Project(
        owner_id=owner.id,
        name="Capability Matter",
        slug=f"cap-{uuid.uuid4().hex[:6]}",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=area_id,
    )
    db.add(project)
    await db.flush()
    return project


async def _bind_playbook(db: AsyncSession, area_id: uuid.UUID, *, name: str) -> Playbook:
    pb = Playbook(name=name, contract_type="NDA", description="Preferred NDA positions.")
    db.add(pb)
    await db.flush()
    db.add(PracticeAreaPlaybook(practice_area_id=area_id, playbook_id=pb.id))
    await db.flush()
    return pb


def _url(project_id: uuid.UUID) -> str:
    return f"/api/v1/matters/{project_id}/capabilities"


def _section(body: dict, kind: str) -> dict:
    return next(s for s in body["sections"] if s["kind"] == kind)


def _entry(body: dict, kind: str, key: str) -> dict:
    return next(e for e in _section(body, kind)["entries"] if e["capability_key"] == key)


# --- GET ---------------------------------------------------------------------
async def test_get_commercial_defaults_all_on(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    pb = await _bind_playbook(db_session, area_id, name="NDA playbook")
    matter = await _make_matter(db_session, user, area_id=area_id)

    resp = await client.get(_url(matter.id), headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["practice_area_key"] == "commercial"
    assert [s["kind"] for s in body["sections"]] == ["playbook", "skill", "tool", "mcp"]

    # Redlining tool group is available + enabled by default.
    redlining = _entry(body, "tool", "redlining")
    assert redlining["available"] is True and redlining["enabled"] is True

    # The bound playbook is available + enabled by default.
    playbook = _entry(body, "playbook", str(pb.id))
    assert playbook["enabled"] is True and "NDA playbook" in playbook["label"]

    # MCP is the disabled placeholder.
    mcp = _entry(body, "mcp", "mcp")
    assert mcp["available"] is False and mcp["toggleable"] is False and mcp["enabled"] is False


async def test_get_unfiled_matter_returns_only_mcp(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    matter = await _make_matter(db_session, user, area_id=None)
    resp = await client.get(_url(matter.id), headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["practice_area_key"] is None
    nonempty = {s["kind"]: len(s["entries"]) for s in body["sections"]}
    assert nonempty == {"playbook": 0, "skill": 0, "tool": 0, "mcp": 1}


async def test_get_cross_user_matter_is_404(
    client: AsyncClient, db_session: AsyncSession, user: User, other_user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)
    resp = await client.get(_url(matter.id), headers=_bearer(other_user))
    assert resp.status_code == 404


async def test_get_unknown_matter_is_404(client: AsyncClient, user: User) -> None:
    resp = await client.get(_url(uuid.uuid4()), headers=_bearer(user))
    assert resp.status_code == 404


# --- PUT ---------------------------------------------------------------------
async def test_put_disables_tool_then_get_reflects(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)

    resp = await client.patch(
        _url(matter.id),
        headers=_bearer(user),
        json={"toggles": [{"kind": "tool", "key": "redlining", "enabled": False}]},
    )
    assert resp.status_code == 200
    assert _entry(resp.json(), "tool", "redlining")["enabled"] is False

    # Persisted with set_by from the session.
    row = (
        await db_session.execute(
            select(MatterCapabilityToggle).where(
                MatterCapabilityToggle.project_id == matter.id,
                MatterCapabilityToggle.capability_kind == "tool",
                MatterCapabilityToggle.capability_key == "redlining",
            )
        )
    ).scalar_one()
    assert row.enabled is False and row.set_by == user.id

    # A fresh GET reflects the override.
    body = (await client.get(_url(matter.id), headers=_bearer(user))).json()
    assert _entry(body, "tool", "redlining")["enabled"] is False


async def test_put_upsert_is_idempotent(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)
    body = {"toggles": [{"kind": "tool", "key": "redlining", "enabled": False}]}

    await client.patch(_url(matter.id), headers=_bearer(user), json=body)
    # Flip it back on, then off again — still exactly one row.
    await client.patch(
        _url(matter.id),
        headers=_bearer(user),
        json={"toggles": [{"kind": "tool", "key": "redlining", "enabled": True}]},
    )
    await client.patch(_url(matter.id), headers=_bearer(user), json=body)

    rows = (
        (
            await db_session.execute(
                select(MatterCapabilityToggle).where(MatterCapabilityToggle.project_id == matter.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1 and rows[0].enabled is False


async def test_put_rejects_unknown_capability(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)
    resp = await client.patch(
        _url(matter.id),
        headers=_bearer(user),
        json={"toggles": [{"kind": "skill", "key": "does-not-exist", "enabled": False}]},
    )
    assert resp.status_code == 422


async def test_put_rejects_wrong_area_tool(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    # ROPA is a Privacy group; it is not toggleable on a Commercial matter.
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)
    resp = await client.patch(
        _url(matter.id),
        headers=_bearer(user),
        json={"toggles": [{"kind": "tool", "key": "ropa", "enabled": False}]},
    )
    assert resp.status_code == 422


async def test_put_rejects_mcp_toggle(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)
    # 'mcp' is not an accepted kind (Literal) → 422 at the schema boundary.
    resp = await client.patch(
        _url(matter.id),
        headers=_bearer(user),
        json={"toggles": [{"kind": "mcp", "key": "mcp", "enabled": True}]},
    )
    assert resp.status_code == 422


async def test_put_rejects_unbound_playbook(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)
    # A real playbook that exists but is NOT bound to the area is not available.
    other = Playbook(name="Unbound", contract_type="MSA", description="")
    db_session.add(other)
    await db_session.flush()
    resp = await client.patch(
        _url(matter.id),
        headers=_bearer(user),
        json={"toggles": [{"kind": "playbook", "key": str(other.id), "enabled": False}]},
    )
    assert resp.status_code == 422


async def test_put_cross_user_matter_is_404(
    client: AsyncClient, db_session: AsyncSession, user: User, other_user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)
    resp = await client.patch(
        _url(matter.id),
        headers=_bearer(other_user),
        json={"toggles": [{"kind": "tool", "key": "redlining", "enabled": False}]},
    )
    assert resp.status_code == 404


async def test_put_writes_one_audit_row_with_no_content(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)
    await client.patch(
        _url(matter.id),
        headers=_bearer(user),
        json={"toggles": [{"kind": "tool", "key": "redlining", "enabled": False}]},
    )
    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.resource_type == "project",
                    AuditLog.resource_id == str(matter.id),
                    AuditLog.action == "matter.capability_toggle",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].details["toggle_count"] == 1
    # Keys are identifiers, not content; no free text leaks.
    assert rows[0].details["toggles"] == [{"kind": "tool", "key": "redlining", "enabled": False}]


async def test_put_isolated_per_matter(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    area_id = await _commercial_area_id(db_session)
    matter_a = await _make_matter(db_session, user, area_id=area_id)
    matter_b = await _make_matter(db_session, user, area_id=area_id)
    await client.patch(
        _url(matter_a.id),
        headers=_bearer(user),
        json={"toggles": [{"kind": "tool", "key": "redlining", "enabled": False}]},
    )
    # Matter B is untouched — redlining still enabled.
    body_b = (await client.get(_url(matter_b.id), headers=_bearer(user))).json()
    assert _entry(body_b, "tool", "redlining")["enabled"] is True


# --- SETUP-4a: Level-0 (deployment-wide) narrowing reflected in the panel (ADR-F062) ---
async def test_level0_disabled_tool_group_absent_from_panel(
    client: AsyncClient, db_session: AsyncSession, user: User
) -> None:
    """A deployment-disabled tool group vanishes from the matter panel entirely (one
    chokepoint: build_area_inventory) — the panel shows exactly what the agent gets."""
    from app.models.practice_area import DeploymentCapabilityToggle

    area_id = await _commercial_area_id(db_session)
    matter = await _make_matter(db_session, user, area_id=area_id)

    # Baseline: redlining is present.
    before = await client.get(_url(matter.id), headers=_bearer(user))
    tool_keys_before = [e["capability_key"] for e in _section(before.json(), "tool")["entries"]]
    assert "redlining" in tool_keys_before

    # Disable redlining deployment-wide → it disappears from the panel.
    db_session.add(
        DeploymentCapabilityToggle(
            capability_kind="tool", capability_key="redlining", enabled=False
        )
    )
    await db_session.flush()
    after = await client.get(_url(matter.id), headers=_bearer(user))
    tool_keys_after = [e["capability_key"] for e in _section(after.json(), "tool")["entries"]]
    assert "redlining" not in tool_keys_after
    assert "tabular" in tool_keys_after  # other groups unaffected
