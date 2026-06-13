"""Practice-area read endpoint + seed — F1-S2 (fork, ADR-F002).

The test database migrates to alembic head (tests/conftest.py), so the
0053 standard-rows seed is PRESENT here — these tests pin the seeded
contract the cockpit's left rail renders, plus the seed's idempotency
(re-running it on a seeded database inserts nothing).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.practice_area import PracticeArea
from app.models.user import User
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration

_EXPECTED_SEED = [
    # (key, name, unit_label, configured) in position order — migration 0053.
    ("commercial", "Commercial", "Matter", True),
    ("disputes", "Disputes", "Matter", False),
    ("m-and-a", "M&A", "Deal", False),
    ("privacy", "Privacy", "Programme", False),
    ("employment", "Employment", "Matter", False),
]


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await _make_user(db_session, suffix="practice-areas")


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    u = await _make_user(db_session, suffix="practice-areas-admin")
    u.is_admin = True
    await db_session.flush()
    return u


async def test_seed_rows_present_once_with_expected_shape(
    db_session: AsyncSession,
) -> None:
    """Migration 0053 seeded exactly the standard areas, exactly once."""
    rows = (
        (await db_session.execute(select(PracticeArea).order_by(PracticeArea.position)))
        .scalars()
        .all()
    )
    seeded = [r for r in rows if r.key in {k for k, *_ in _EXPECTED_SEED}]
    assert [(r.key, r.name, r.unit_label, r.configured) for r in seeded] == _EXPECTED_SEED
    # The list-equality above is the duplicate guard (a re-seeded key
    # would appear twice and break it); also pin key uniqueness directly.
    assert len({r.key for r in rows}) == len(rows)


async def test_seed_is_idempotent_on_a_seeded_database(
    db_session: AsyncSession,
) -> None:
    """Re-running the 0053 seed against the already-seeded DB is a no-op."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0053", versions / "0053_practice_areas.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0053"] = module
    try:
        spec.loader.exec_module(module)

        before = (
            await db_session.execute(select(func.count()).select_from(PracticeArea))
        ).scalar_one()
        conn = await db_session.connection()
        await conn.run_sync(lambda sync_conn: module._seed(sync_conn))
        after = (
            await db_session.execute(select(func.count()).select_from(PracticeArea))
        ).scalar_one()
        assert after == before
    finally:
        sys.modules.pop("migration_0053", None)


async def test_list_practice_areas_position_order(client: AsyncClient, user: User) -> None:
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    areas = resp.json()["practice_areas"]
    keys = [a["key"] for a in areas]
    assert keys == [k for k, *_ in _EXPECTED_SEED]
    commercial = areas[0]
    assert commercial["configured"] is True
    assert commercial["unit_label"] == "Matter"
    assert {a["key"] for a in areas if a["configured"]} == {"commercial"}


async def test_list_practice_areas_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/practice-areas")
    assert resp.status_code == 401


# --- F1-S3 config vocabulary -------------------------------------------------


async def test_seed_commercial_config_present_and_derived_configured(
    client: AsyncClient, user: User
) -> None:
    """0054 seeded Commercial with a profile + tier floor; ``configured``
    is DERIVED from the profile (F1-S3), and the profile is readable
    (transparency)."""
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    areas = {a["key"]: a for a in resp.json()["practice_areas"]}
    commercial = areas["commercial"]
    assert commercial["configured"] is True
    # No seeded area floor: the only S9-qualified model is tier 4; a stronger
    # area floor would make every Commercial run fail tier_below_minimum
    # (the floor mechanism is proven elsewhere). Operators set one later.
    assert commercial["default_tier_floor"] is None
    assert commercial["profile_md"] and "Commercial" in commercial["profile_md"]
    assert commercial["bound_skills"] == []
    # Inert areas have no profile and derive configured=False.
    assert areas["disputes"]["configured"] is False
    assert areas["disputes"]["profile_md"] is None


async def test_seed_commercial_config_is_idempotent(db_session: AsyncSession) -> None:
    """Re-running _seed_commercial_config never overwrites an edited profile."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0054", versions / "0054_practice_area_config.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0054"] = module
    try:
        spec.loader.exec_module(module)
        # Edit Commercial's profile, then re-run the seed: it must NOT clobber.
        area = (
            await db_session.execute(select(PracticeArea).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        area.profile_md = "operator-edited profile"
        await db_session.flush()
        conn = await db_session.connection()
        await conn.run_sync(lambda sync_conn: module._seed_commercial_config(sync_conn))
        await db_session.refresh(area)
        assert area.profile_md == "operator-edited profile"
    finally:
        sys.modules.pop("migration_0054", None)


async def test_admin_patch_configures_area(client: AsyncClient, admin: User) -> None:
    resp = await client.patch(
        "/api/v1/practice-areas/disputes",
        headers=_bearer(admin),
        json={"profile_md": "You are the Disputes agent.", "default_tier_floor": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["default_tier_floor"] == 1
    assert body["profile_md"] == "You are the Disputes agent."


async def test_admin_patch_accepts_valid_subagents(client: AsyncClient, admin: User) -> None:
    resp = await client.patch(
        "/api/v1/practice-areas/commercial",
        headers=_bearer(admin),
        json={
            "agent_config": {
                "subagents": [
                    {
                        "name": "researcher",
                        "description": "Finds matter passages.",
                        "system_prompt": "Research the documents.",
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    assert resp.json()["agent_config"]["subagents"][0]["name"] == "researcher"


async def test_admin_patch_rejects_model_bearing_subagent(client: AsyncClient, admin: User) -> None:
    """ADR-F010: a subagent ``model`` key (gateway bypass) is rejected and
    never stored."""
    resp = await client.patch(
        "/api/v1/practice-areas/commercial",
        headers=_bearer(admin),
        json={
            "agent_config": {
                "subagents": [
                    {
                        "name": "x",
                        "description": "d",
                        "system_prompt": "p",
                        "model": "openai:gpt-5.5",
                    }
                ]
            }
        },
    )
    assert resp.status_code == 400
    # And nothing was persisted (still no subagents on Commercial).
    read = await client.get("/api/v1/practice-areas", headers=_bearer(admin))
    commercial = next(a for a in read.json()["practice_areas"] if a["key"] == "commercial")
    assert commercial["agent_config"].get("subagents", []) == []


async def test_patch_requires_admin(client: AsyncClient, user: User) -> None:
    resp = await client.patch(
        "/api/v1/practice-areas/commercial",
        headers=_bearer(user),
        json={"profile_md": "nope"},
    )
    assert resp.status_code == 403


async def test_patch_unknown_area_is_404(client: AsyncClient, admin: User) -> None:
    resp = await client.patch(
        "/api/v1/practice-areas/does-not-exist",
        headers=_bearer(admin),
        json={"profile_md": "x"},
    )
    assert resp.status_code == 404


async def test_skill_attach_unknown_skill_is_404(client: AsyncClient, admin: User) -> None:
    resp = await client.post(
        "/api/v1/practice-areas/commercial/skills",
        headers=_bearer(admin),
        json={"skill_name": "no-such-skill-xyz"},
    )
    assert resp.status_code == 404


async def test_skill_attach_requires_admin(client: AsyncClient, user: User) -> None:
    resp = await client.post(
        "/api/v1/practice-areas/commercial/skills",
        headers=_bearer(user),
        json={"skill_name": "anything"},
    )
    assert resp.status_code == 403
