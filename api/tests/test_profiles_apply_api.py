"""B-7a: the profile-apply API (ADR-F067 D4).

Covers the acceptance oracle (apply Commercial on a fresh-org Library → the
G13 first-run cliff is killed: bindings become adopted), idempotency, all-or-
nothing atomicity, the AdminUser + operator fence, and the blank-profile create
path. Mirrors the client/auth setup of tests/test_practice_areas.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.capabilities import KIND_SKILL, KIND_TOOL
from app.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.practice_area import (
    OrgLibraryEntry,
    PracticeArea,
    PracticeAreaSkill,
    PracticeAreaToolGroup,
)
from app.models.user import User
from app.profiles.bootstrap import resolve_profiles_dir
from app.profiles.loader import load_profiles
from app.skills.bootstrap import resolve_skill_dirs
from app.skills.loader import load_registry
from app.skills.registry import MutableSkillRegistry, SkillRegistry
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration

_COMMERCIAL_SKILLS = 10  # +1 ADV-1 (ADR-F084): adversarial-review
_COMMERCIAL_TOOLS = 2


def _real_registries() -> tuple[MutableSkillRegistry, object]:
    settings = get_settings()
    skills_dir, community_dir = resolve_skill_dirs(settings)
    skills = load_registry(skills_dir, community_skills_dir=community_dir)
    profiles = load_profiles(resolve_profiles_dir(settings), skill_registry=skills)
    return MutableSkillRegistry(skills), profiles


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    skill_holder, profile_reg = _real_registries()
    prior_skill = getattr(app.state, "skill_registry", None)
    prior_profile = getattr(app.state, "profile_registry", None)
    app.state.skill_registry = skill_holder
    app.state.profile_registry = profile_reg
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.state.skill_registry = prior_skill
        app.state.profile_registry = prior_profile


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="profiles-admin")
    u.is_admin = True
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def member(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="profiles-member")


@pytest_asyncio.fixture
async def operator(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="profiles-operator")
    u.is_admin = True
    u.role = "operator"
    await db_session.flush()
    return u


async def _empty_library(db: AsyncSession) -> None:
    """Emulate a fresh org: no adopted Library entries (0088's users-empty gate)."""
    await db.execute(delete(OrgLibraryEntry))
    await db.flush()


async def _library_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(OrgLibraryEntry))).scalar_one()


# --- reads --------------------------------------------------------------------


async def test_list_profiles(client: AsyncClient, admin: User) -> None:
    resp = await client.get("/api/v1/profiles", headers=_bearer(admin))
    assert resp.status_code == 200, resp.text
    names = sorted(p["name"] for p in resp.json()["profiles"])
    assert names == ["blank", "commercial", "privacy"]
    commercial = next(p for p in resp.json()["profiles"] if p["name"] == "commercial")
    assert commercial["skill_count"] == _COMMERCIAL_SKILLS
    assert commercial["tool_group_count"] == _COMMERCIAL_TOOLS
    assert commercial["subagent_count"] == 3


async def test_list_profiles_forbidden_for_member(client: AsyncClient, member: User) -> None:
    resp = await client.get("/api/v1/profiles", headers=_bearer(member))
    assert resp.status_code == 403


async def test_get_profile_detail(client: AsyncClient, admin: User) -> None:
    resp = await client.get("/api/v1/profiles/commercial", headers=_bearer(admin))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "area"
    assert body["doctrine"] and "commercial" in body["doctrine"].lower()
    assert len(body["skills"]) == _COMMERCIAL_SKILLS


async def test_get_profile_unknown_404(client: AsyncClient, admin: User) -> None:
    resp = await client.get("/api/v1/profiles/nope", headers=_bearer(admin))
    assert resp.status_code == 404


async def test_apply_unknown_profile_404(client: AsyncClient, admin: User) -> None:
    resp = await client.post("/api/v1/profiles/nope/apply", json={}, headers=_bearer(admin))
    assert resp.status_code == 404


# --- the acceptance oracle (G13) ---------------------------------------------


async def test_apply_commercial_adopts_library_killing_g13(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    """Fresh-org Library is empty ⇒ Commercial's bound caps are inert. Apply
    adopts them, so the agent gets redlining out of the box."""
    await _empty_library(db_session)
    assert await _library_count(db_session) == 0

    resp = await client.post("/api/v1/profiles/commercial/apply", json={}, headers=_bearer(admin))
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["area_created"] is False
    # The area already carried the seed config identical to the manifest.
    assert result["changed_fields"] == []
    assert len(result["adopted"][KIND_SKILL]) == _COMMERCIAL_SKILLS
    assert len(result["adopted"][KIND_TOOL]) == _COMMERCIAL_TOOLS
    # Bindings already seeded ⇒ nothing newly written; adoption was the missing piece.
    assert result["bindings_written"] == {KIND_SKILL: 0, KIND_TOOL: 0}
    assert result["roster_subagents"] == 3

    # The Library now carries exactly the commercial caps; redlining is adopted.
    assert await _library_count(db_session) == _COMMERCIAL_SKILLS + _COMMERCIAL_TOOLS
    adopted_tools = set(
        (
            await db_session.execute(
                select(OrgLibraryEntry.capability_key).where(
                    OrgLibraryEntry.capability_kind == KIND_TOOL
                )
            )
        )
        .scalars()
        .all()
    )
    assert {"redlining", "tabular"} <= adopted_tools


async def test_apply_creates_missing_area_with_bindings(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    """The area-profile-onto-a-MISSING-area path: apply must create the area AND
    bind + adopt against the freshly-flushed area.id (not just overwrite a seed)."""
    area = (
        await db_session.execute(select(PracticeArea).where(PracticeArea.key == "commercial"))
    ).scalar_one()
    area_id = area.id
    await db_session.execute(
        delete(PracticeAreaSkill).where(PracticeAreaSkill.practice_area_id == area_id)
    )
    await db_session.execute(
        delete(PracticeAreaToolGroup).where(PracticeAreaToolGroup.practice_area_id == area_id)
    )
    await db_session.execute(delete(PracticeArea).where(PracticeArea.id == area_id))
    await _empty_library(db_session)

    resp = await client.post("/api/v1/profiles/commercial/apply", json={}, headers=_bearer(admin))
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["area_created"] is True
    assert len(result["adopted"][KIND_SKILL]) == _COMMERCIAL_SKILLS
    assert len(result["adopted"][KIND_TOOL]) == _COMMERCIAL_TOOLS
    assert result["bindings_written"] == {
        KIND_SKILL: _COMMERCIAL_SKILLS,
        KIND_TOOL: _COMMERCIAL_TOOLS,
    }
    assert result["roster_subagents"] == 3

    recreated = (
        await db_session.execute(select(PracticeArea).where(PracticeArea.key == "commercial"))
    ).scalar_one()
    assert recreated.profile_md and "commercial" in recreated.profile_md.lower()
    assert len(recreated.agent_config["subagents"]) == 3
    assert recreated.configured is True
    bound_skills = (
        await db_session.execute(
            select(func.count())
            .select_from(PracticeAreaSkill)
            .where(PracticeAreaSkill.practice_area_id == recreated.id)
        )
    ).scalar_one()
    assert bound_skills == _COMMERCIAL_SKILLS


async def test_apply_is_idempotent(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    await _empty_library(db_session)
    first = await client.post("/api/v1/profiles/commercial/apply", json={}, headers=_bearer(admin))
    assert first.status_code == 200
    # First apply on a fresh Library adopts the full commercial cap set (self-standing,
    # so this test doesn't rely on the G13 test to prove the first apply did work).
    assert len(first.json()["adopted"][KIND_SKILL]) == _COMMERCIAL_SKILLS
    assert len(first.json()["adopted"][KIND_TOOL]) == _COMMERCIAL_TOOLS
    count_after_first = await _library_count(db_session)

    second = await client.post("/api/v1/profiles/commercial/apply", json={}, headers=_bearer(admin))
    assert second.status_code == 200, second.text
    r2 = second.json()
    assert r2["adopted"] == {KIND_SKILL: [], KIND_TOOL: []}
    assert r2["bindings_written"] == {KIND_SKILL: 0, KIND_TOOL: 0}
    assert r2["changed_fields"] == []
    assert await _library_count(db_session) == count_after_first


async def test_apply_is_all_or_nothing_on_drift(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    """A skill that drifted out of the (live) registry after boot → 422, and
    NOT ONE row is adopted (validation precedes the first write)."""
    await _empty_library(db_session)
    full: SkillRegistry = app.state.skill_registry.current()
    reduced = SkillRegistry(
        records={k: v for k, v in full.records.items() if k != "surgical-redline"}
    )
    app.state.skill_registry = MutableSkillRegistry(reduced)
    try:
        resp = await client.post(
            "/api/v1/profiles/commercial/apply", json={}, headers=_bearer(admin)
        )
        assert resp.status_code == 422, resp.text
        assert "surgical-redline" in resp.text
        assert await _library_count(db_session) == 0  # nothing written
    finally:
        app.state.skill_registry = MutableSkillRegistry(full)


# --- authz --------------------------------------------------------------------


async def test_apply_forbidden_for_member(client: AsyncClient, member: User) -> None:
    resp = await client.post("/api/v1/profiles/commercial/apply", json={}, headers=_bearer(member))
    assert resp.status_code == 403


async def test_apply_forbidden_for_operator(client: AsyncClient, operator: User) -> None:
    resp = await client.post(
        "/api/v1/profiles/commercial/apply", json={}, headers=_bearer(operator)
    )
    assert resp.status_code == 403


# --- request-shape guards -----------------------------------------------------


async def test_area_profile_rejects_overrides(client: AsyncClient, admin: User) -> None:
    resp = await client.post(
        "/api/v1/profiles/commercial/apply",
        json={"target_key": "commercial"},
        headers=_bearer(admin),
    )
    assert resp.status_code == 422


# --- blank profile ------------------------------------------------------------


async def test_apply_blank_creates_unconfigured_area(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    resp = await client.post(
        "/api/v1/profiles/blank/apply",
        json={
            "target_key": "investigations",
            "name": "Investigations",
            "unit_label": "Investigation",
        },
        headers=_bearer(admin),
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["area_created"] is True
    assert result["adopted"] == {KIND_SKILL: [], KIND_TOOL: []}
    assert result["roster_subagents"] == 0

    area = (
        await db_session.execute(select(PracticeArea).where(PracticeArea.key == "investigations"))
    ).scalar_one()
    assert area.name == "Investigations"
    assert area.unit_label == "Investigation"
    assert area.profile_md is None
    assert area.configured is False
    assert area.agent_config == {}
    bound = (
        await db_session.execute(
            select(func.count())
            .select_from(PracticeAreaSkill)
            .where(PracticeAreaSkill.practice_area_id == area.id)
        )
    ).scalar_one()
    assert bound == 0


async def test_apply_blank_requires_overrides(client: AsyncClient, admin: User) -> None:
    resp = await client.post("/api/v1/profiles/blank/apply", json={}, headers=_bearer(admin))
    assert resp.status_code == 422


async def test_apply_blank_onto_existing_key_conflicts(client: AsyncClient, admin: User) -> None:
    resp = await client.post(
        "/api/v1/profiles/blank/apply",
        json={"target_key": "commercial", "name": "X", "unit_label": "Matter"},
        headers=_bearer(admin),
    )
    assert resp.status_code == 409
