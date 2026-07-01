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
from app.models.practice_area import PracticeArea, PracticeAreaSkill
from app.models.user import User
from tests.agents.test_agent_runs_api import _bearer, _make_user, _override_get_db

pytestmark = pytest.mark.integration

_EXPECTED_SEED = [
    # (key, name, unit_label, configured) in position order. Identity/unit for the
    # first five are migration 0053; ``configured`` reflects the profile seeds —
    # Commercial in 0054, the next four in 0055 (UX-B-2). AI Compliance (position 6)
    # is introduced already-configured by 0084 (AIC-0, ADR-F057) — the EU AI Act
    # module home. So all six read configured.
    ("commercial", "Commercial", "Matter", True),
    ("disputes", "Disputes", "Matter", True),
    ("m-and-a", "M&A", "Deal", True),
    ("privacy", "Privacy", "Programme", True),
    ("employment", "Employment", "Matter", True),
    ("ai-compliance", "AI Compliance", "Programme", True),
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
    # All six areas carry a seeded profile (Commercial 0054, the next four 0055,
    # AI Compliance 0084), so all derive configured=True.
    assert {a["key"] for a in areas if a["configured"]} == {
        "commercial",
        "disputes",
        "m-and-a",
        "privacy",
        "employment",
        "ai-compliance",
    }


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
    # UX-B-3 (0056): Commercial now carries its default skill bindings.
    assert "contract-qa" in commercial["bound_skills"]
    assert "nda-review" in commercial["bound_skills"]
    # F2 Tabular T3 (0083): Commercial carries the tabular-review discoverability skill.
    assert "tabular-review" in commercial["bound_skills"]
    # C7b (0073): Commercial carries the drafter/reviewer fan-out roster (the 0057
    # document-researcher extended with clause-drafter + clause-reviewer).
    subagents = commercial["agent_config"].get("subagents", [])
    assert [s["name"] for s in subagents] == [
        "document-researcher",
        "clause-drafter",
        "clause-reviewer",
    ]
    bound = set(commercial["bound_skills"])
    for sub in subagents:
        assert set(sub.get("skills", [])) <= bound  # ⊆ area (ADR-F017)
        assert "model" not in sub  # inherits the gateway-bound parent (ADR-F010)


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


# --- UX-B-2 default-area profiles (migration 0055) ---------------------------


async def test_default_area_profiles_present_and_derived_configured(
    client: AsyncClient, user: User
) -> None:
    """0055 gave Disputes/M&A/Privacy/Employment a profile; each derives
    ``configured=True``, seeds no area tier floor and no subagents, and the
    profiles are readable (transparency) and calibrated (clarify-before-guess).
    """
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    areas = {a["key"]: a for a in resp.json()["practice_areas"]}
    for key in ("disputes", "m-and-a", "privacy", "employment"):
        area = areas[key]
        assert area["configured"] is True, key
        assert area["profile_md"] and area["profile_md"].strip(), key
        # Calibrated to the UX-B-1 baseline: every profile carries the
        # ground-and-cite + clarify-before-guess disciplines.
        assert "cite" in area["profile_md"].lower(), key
        assert "clarifying question" in area["profile_md"].lower(), key
        # No area floor (M3 is tier 4) and no live subagents (deferred to UX-B-4).
        assert area["default_tier_floor"] is None, key
        assert area["agent_config"] == {}, key
    # Privacy's profile is forward-looking (the modules / Oscar-Privacy home).
    assert "module" in areas["privacy"]["profile_md"].lower()


async def test_default_area_profiles_seed_is_idempotent(db_session: AsyncSession) -> None:
    """Re-running _seed_default_area_profiles never overwrites an edited profile."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0055", versions / "0055_default_area_profiles.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0055"] = module
    try:
        spec.loader.exec_module(module)
        # Edit Disputes' profile, then re-run the seed: it must NOT clobber.
        area = (
            await db_session.execute(select(PracticeArea).where(PracticeArea.key == "disputes"))
        ).scalar_one()
        area.profile_md = "operator-edited disputes profile"
        await db_session.flush()
        conn = await db_session.connection()
        await conn.run_sync(lambda sync_conn: module._seed_default_area_profiles(sync_conn))
        await db_session.refresh(area)
        assert area.profile_md == "operator-edited disputes profile"
    finally:
        sys.modules.pop("migration_0055", None)


# --- AIC-0 AI Compliance area (migration 0084, ADR-F057) ---------------------


async def test_ai_compliance_area_present_and_configured(client: AsyncClient, user: User) -> None:
    """0084 (AIC-0) introduces AI Compliance already-configured: it renders a
    composer, carries the EU-AI-Act doctrine (incl. the ADR-F057 presence-gate
    discipline that a risk classification is a legal determination the model does
    not assert), seeds no area tier floor and no subagents.
    """
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    areas = {a["key"]: a for a in resp.json()["practice_areas"]}
    area = areas["ai-compliance"]
    assert area["name"] == "AI Compliance"
    assert area["unit_label"] == "Programme"
    assert area["configured"] is True
    profile = area["profile_md"]
    assert profile and profile.strip()
    # The module's defining discipline (ADR-F057): the tier is a legal determination
    # owned by the engine, not asserted by the model.
    assert "legal determination" in profile.lower()
    # Same UX-B-1 calibration as the other areas (ground/cite + clarify-before-guess).
    assert "cite" in profile.lower()
    assert "clarifying question" in profile.lower()
    # No area floor (only tier 4 is qualified) and no live subagents yet.
    assert area["default_tier_floor"] is None
    assert area["agent_config"] == {}


async def test_ai_compliance_area_seed_is_idempotent(db_session: AsyncSession) -> None:
    """Re-running the 0084 seed never duplicates the row or clobbers an edit."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0084", versions / "0084_seed_ai_compliance_area.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0084"] = module
    try:
        spec.loader.exec_module(module)
        area = (
            await db_session.execute(
                select(PracticeArea).where(PracticeArea.key == "ai-compliance")
            )
        ).scalar_one()
        area.profile_md = "operator-edited ai-compliance profile"
        await db_session.flush()
        before = (
            await db_session.execute(select(func.count()).select_from(PracticeArea))
        ).scalar_one()
        conn = await db_session.connection()
        await conn.run_sync(lambda sync_conn: module._seed_ai_compliance_area(sync_conn))
        after = (
            await db_session.execute(select(func.count()).select_from(PracticeArea))
        ).scalar_one()
        await db_session.refresh(area)
        # Key exists ⇒ insert skipped: no duplicate, edit preserved.
        assert after == before
        assert area.profile_md == "operator-edited ai-compliance profile"
    finally:
        sys.modules.pop("migration_0084", None)


# --- UX-B-3 default-area skill bindings (migration 0056) ---------------------


async def test_default_area_skill_bindings_present(client: AsyncClient, user: User) -> None:
    """0056 bound a focused, relevant skill set to each area by default."""
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    areas = {a["key"]: a for a in resp.json()["practice_areas"]}
    expected = {
        "commercial": {
            "msa-review-commercial-purchase",
            "msa-review-saas",
            "contract-qa",
            "nda-review",
            "deal-review",  # C7b (0073): the reconciliation craft skill
        },
        "privacy": {"dpa-checklist-review", "vendor-privacy-policy-first-pass", "contract-qa"},
        "m-and-a": {"nda-review", "contract-qa", "contract-snapshot"},
        "disputes": {"contract-qa", "action-items-from-client-alert"},
        "employment": {"contract-qa", "nda-review", "action-items-from-client-alert"},
    }
    for key, want in expected.items():
        assert want <= set(areas[key]["bound_skills"]), key


async def test_commercial_surgical_redline_skill_and_doctrine(
    client: AsyncClient, user: User
) -> None:
    """C8 (0067, ADR-F041): the surgical-redline skill is bound to Commercial and the
    redline doctrine points at the shipped tools/skill — the stale C0 "lands in a
    later slice" line is gone (guards the 0067 never-clobber refresh against a silent
    transcription no-op)."""
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    commercial = {a["key"]: a for a in resp.json()["practice_areas"]}["commercial"]

    assert "surgical-redline" in commercial["bound_skills"]
    profile = commercial["profile_md"]
    assert "surgical-redline" in profile
    assert "preview_redline" in profile
    assert "lands in a later slice" not in profile  # the stale 0066 tail was refreshed


async def test_commercial_surgical_redline_migration_is_idempotent(
    db_session: AsyncSession,
) -> None:
    """Re-running the 0067 seed (skill binding + doctrine refresh) is a no-op: no
    duplicate binding, and the already-refreshed profile_md is untouched (the old
    0066 tail is gone, so the REPLACE matches nothing)."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0067", versions / "0067_commercial_surgical_redline_skill.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0067"] = module
    try:
        spec.loader.exec_module(module)
        area_id = (
            await db_session.execute(
                select(PracticeArea.id).where(PracticeArea.key == "commercial")
            )
        ).scalar_one()

        async def _binding_count() -> int:
            return (
                await db_session.execute(
                    select(func.count())
                    .select_from(PracticeAreaSkill)
                    .where(
                        PracticeAreaSkill.practice_area_id == area_id,
                        PracticeAreaSkill.skill_name == "surgical-redline",
                    )
                )
            ).scalar_one()

        async def _profile() -> str:
            return (
                await db_session.execute(
                    select(PracticeArea.profile_md).where(PracticeArea.key == "commercial")
                )
            ).scalar_one()

        before_count = await _binding_count()
        before_profile = await _profile()
        assert before_count == 1  # the head migration bound it once
        assert "preview_redline" in before_profile  # and refreshed the doctrine

        conn = await db_session.connection()
        await conn.run_sync(lambda c: module._bind_surgical_redline_skill(c))
        await conn.run_sync(lambda c: module._refresh_redline_doctrine(c))

        assert await _binding_count() == 1  # no duplicate binding
        assert await _profile() == before_profile  # doctrine unchanged (new tail present)

        # The other half of never-clobber: an operator-edited redline paragraph
        # (neither the verbatim 0066 nor the C8 tail present) is left untouched.
        edited = "Commercial agent. Operator-rewritten redline guidance: do as instructed."
        area = (
            await db_session.execute(select(PracticeArea).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        area.profile_md = edited
        await db_session.flush()
        await conn.run_sync(lambda c: module._refresh_redline_doctrine(c))
        assert await _profile() == edited  # operator edit preserved (REPLACE matched nothing)
    finally:
        sys.modules.pop("migration_0067", None)


async def test_commercial_negotiation_review_skill_and_doctrine(
    client: AsyncClient, user: User
) -> None:
    """C5b-2 (0072, ADR-F041): the negotiation-review skill is bound to Commercial and the
    negotiation doctrine points at the shipped tools/skill — the stale 0066 "accept,
    reject, or counter" paragraph (no comment verbs, no tool) is gone (guards the 0072
    never-clobber refresh against a silent transcription no-op)."""
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    commercial = {a["key"]: a for a in resp.json()["practice_areas"]}["commercial"]

    assert "negotiation-review" in commercial["bound_skills"]
    profile = commercial["profile_md"]
    assert "negotiation-review" in profile
    assert "respond_to_counterparty" in profile
    assert "extract_counterparty_position" in profile
    # the stale 0066 paragraph body was refreshed (its exact phrasing is gone)
    assert "classify **every** change as **accept**, **reject**, or **counter**" not in profile


async def test_commercial_negotiation_review_migration_is_idempotent(
    db_session: AsyncSession,
) -> None:
    """Re-running the 0072 seed (skill binding + doctrine refresh) is a no-op: no
    duplicate binding, and the already-refreshed profile_md is untouched (the old 0066
    paragraph is gone, so the REPLACE matches nothing)."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0072", versions / "0072_commercial_negotiation_review_skill.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0072"] = module
    try:
        spec.loader.exec_module(module)
        area_id = (
            await db_session.execute(
                select(PracticeArea.id).where(PracticeArea.key == "commercial")
            )
        ).scalar_one()

        async def _binding_count() -> int:
            return (
                await db_session.execute(
                    select(func.count())
                    .select_from(PracticeAreaSkill)
                    .where(
                        PracticeAreaSkill.practice_area_id == area_id,
                        PracticeAreaSkill.skill_name == "negotiation-review",
                    )
                )
            ).scalar_one()

        async def _profile() -> str:
            return (
                await db_session.execute(
                    select(PracticeArea.profile_md).where(PracticeArea.key == "commercial")
                )
            ).scalar_one()

        before_count = await _binding_count()
        before_profile = await _profile()
        assert before_count == 1  # the head migration bound it once
        assert "respond_to_counterparty" in before_profile  # and refreshed the doctrine

        conn = await db_session.connection()
        await conn.run_sync(lambda c: module._bind_negotiation_review_skill(c))
        await conn.run_sync(lambda c: module._refresh_negotiation_doctrine(c))

        assert await _binding_count() == 1  # no duplicate binding
        assert await _profile() == before_profile  # doctrine unchanged (new tail present)

        # The other half of never-clobber: an operator-edited negotiation paragraph
        # (neither the verbatim 0066 nor the C5b-2 tail present) is left untouched.
        edited = "Commercial agent. Operator-rewritten negotiation guidance: do as instructed."
        area = (
            await db_session.execute(select(PracticeArea).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        area.profile_md = edited
        await db_session.flush()
        await conn.run_sync(lambda c: module._refresh_negotiation_doctrine(c))
        assert await _profile() == edited  # operator edit preserved (REPLACE matched nothing)
    finally:
        sys.modules.pop("migration_0072", None)


async def test_default_area_skill_bindings_seed_is_idempotent(db_session: AsyncSession) -> None:
    """Re-running the 0056 seed inserts no duplicates and never disturbs an
    operator-attached skill."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0056", versions / "0056_default_area_skill_bindings.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0056"] = module
    try:
        spec.loader.exec_module(module)
        area_id = (
            await db_session.execute(
                select(PracticeArea.id).where(PracticeArea.key == "commercial")
            )
        ).scalar_one()

        async def _count() -> int:
            return (
                await db_session.execute(
                    select(func.count())
                    .select_from(PracticeAreaSkill)
                    .where(PracticeAreaSkill.practice_area_id == area_id)
                )
            ).scalar_one()

        # An operator attaches an extra skill the defaults don't include.
        db_session.add(PracticeAreaSkill(practice_area_id=area_id, skill_name="comms-improver"))
        await db_session.flush()
        before = await _count()

        conn = await db_session.connection()
        await conn.run_sync(lambda sync_conn: module._seed_default_area_skill_bindings(sync_conn))

        assert await _count() == before  # no duplicate inserts
        names = (
            (
                await db_session.execute(
                    select(PracticeAreaSkill.skill_name).where(
                        PracticeAreaSkill.practice_area_id == area_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "comms-improver" in names  # operator attachment survived
    finally:
        sys.modules.pop("migration_0056", None)


# --- UX-B-4 Commercial subagent (migration 0057) -----------------------------


async def test_commercial_subagent_seed_is_idempotent(db_session: AsyncSession) -> None:
    """Re-running the 0057 seed never clobbers an operator-edited agent_config
    (it writes only where agent_config is still the empty default)."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0057", versions / "0057_commercial_subagent.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0057"] = module
    try:
        spec.loader.exec_module(module)
        area = (
            await db_session.execute(select(PracticeArea).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        # An operator edits the config; re-running the seed must NOT clobber it
        # (the WHERE agent_config = '{}' guard misses a non-empty config).
        edited = {
            "subagents": [{"name": "operator-edit", "description": "d", "system_prompt": "p"}]
        }
        area.agent_config = edited
        await db_session.flush()
        conn = await db_session.connection()
        await conn.run_sync(lambda sync_conn: module._seed_commercial_subagent(sync_conn))
        await db_session.refresh(area)
        assert area.agent_config == edited
    finally:
        sys.modules.pop("migration_0057", None)


# --- C7b drafter/reviewer roster + deal-review binding (migration 0073) -------


async def test_commercial_roster_migration_is_idempotent(db_session: AsyncSession) -> None:
    """C7b (0073): the roster extension + deal-review binding reconciles and never-clobbers.
    The verbatim 0057 config upgrades to the drafter/reviewer roster; a re-run is a no-op
    (no duplicate binding, config unchanged); an operator-edited agent_config is preserved
    (the UPDATE matches only the verbatim 0057 value)."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0073", versions / "0073_commercial_roster_and_reconciliation.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0073"] = module
    try:
        spec.loader.exec_module(module)
        area_id = (
            await db_session.execute(
                select(PracticeArea.id).where(PracticeArea.key == "commercial")
            )
        ).scalar_one()

        async def _binding_count() -> int:
            return (
                await db_session.execute(
                    select(func.count())
                    .select_from(PracticeAreaSkill)
                    .where(
                        PracticeAreaSkill.practice_area_id == area_id,
                        PracticeAreaSkill.skill_name == "deal-review",
                    )
                )
            ).scalar_one()

        area = (
            await db_session.execute(select(PracticeArea).where(PracticeArea.key == "commercial"))
        ).scalar_one()
        roster = ["document-researcher", "clause-drafter", "clause-reviewer"]
        # The head migration already extended the roster + bound deal-review once.
        assert [s["name"] for s in area.agent_config["subagents"]] == roster
        assert await _binding_count() == 1

        conn = await db_session.connection()
        # Re-run: idempotent — config already holds the roster (≠ the 0057 value) and the
        # binding NOT EXISTS guard skips the dup.
        await conn.run_sync(lambda c: module._extend_commercial_roster(c))
        await conn.run_sync(lambda c: module._bind_deal_review_skill(c))
        await db_session.refresh(area)
        assert [s["name"] for s in area.agent_config["subagents"]] == roster
        assert await _binding_count() == 1  # no duplicate binding

        # The reconciling swap upgrades a row still carrying the verbatim 0057 config.
        area.agent_config = module._OLD_COMMERCIAL_AGENT_CONFIG
        await db_session.flush()
        await conn.run_sync(lambda c: module._extend_commercial_roster(c))
        await db_session.refresh(area)
        assert area.agent_config == module._NEW_COMMERCIAL_AGENT_CONFIG

        # Never-clobber: an operator-edited config (≠ the 0057 value) is left untouched.
        edited = {
            "subagents": [{"name": "operator-edit", "description": "d", "system_prompt": "p"}]
        }
        area.agent_config = edited
        await db_session.flush()
        await conn.run_sync(lambda c: module._extend_commercial_roster(c))
        await db_session.refresh(area)
        assert area.agent_config == edited
    finally:
        sys.modules.pop("migration_0073", None)


async def test_admin_patch_rejects_subagent_skill_outside_area(
    client: AsyncClient, admin: User
) -> None:
    """ADR-F017: a subagent may reference only skills BOUND to the area. A skill
    bound elsewhere (dpa-checklist-review → privacy, not commercial) is rejected."""
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
                        "skills": ["dpa-checklist-review"],
                    }
                ]
            }
        },
    )
    assert resp.status_code == 400
    read = await client.get("/api/v1/practice-areas", headers=_bearer(admin))
    commercial = next(a for a in read.json()["practice_areas"] if a["key"] == "commercial")
    assert "x" not in [s["name"] for s in commercial["agent_config"].get("subagents", [])]


async def test_admin_patch_accepts_subagent_with_area_bound_skill(
    client: AsyncClient, admin: User
) -> None:
    """ADR-F017: a subagent declaring a skill the area binds (nda-review →
    commercial, 0056) is accepted and stored."""
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
                        "skills": ["nda-review"],
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    assert resp.json()["agent_config"]["subagents"][0]["skills"] == ["nda-review"]


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
    # And the bad subagent was not persisted — Commercial still carries only its
    # seeded roster (0057 document-researcher + 0073 clause-drafter/clause-reviewer),
    # never the rejected "x".
    read = await client.get("/api/v1/practice-areas", headers=_bearer(admin))
    commercial = next(a for a in read.json()["practice_areas"] if a["key"] == "commercial")
    names = [s["name"] for s in commercial["agent_config"].get("subagents", [])]
    assert "x" not in names


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


# --- C0 Commercial lawyer-method doctrine (migration 0066, ADR-F028) ---------


async def test_commercial_doctrine_profile_present(client: AsyncClient, user: User) -> None:
    """0066 replaced Commercial's short 0054 seed with the source-grounded
    lawyer-method doctrine (commercial-lawyer-method.md §§2-5,7-10): deal triage,
    the four controlling review skills, surgical redlining, accept/reject/counter,
    jurisdiction-competence escalation, and the universal receipts. Readable via
    the API (transparency rule)."""
    resp = await client.get("/api/v1/practice-areas", headers=_bearer(user))
    assert resp.status_code == 200
    areas = {a["key"]: a for a in resp.json()["practice_areas"]}
    profile = areas["commercial"]["profile_md"]
    assert profile
    # The four controlling review skills are named (the C0 convention).
    for skill in (
        "nda-review",
        "msa-review-commercial-purchase",
        "msa-review-saas",
        "contract-qa",
    ):
        assert skill in profile, skill
    # The doctrine pillars.
    for marker in (
        "controlling",
        "advisory only",
        "smallest change",
        "Items requiring human judgment",
        "accept",
        "counter",
        "jurisdiction",
        "escalate",
        "clarifying question",
    ):
        assert marker in profile, marker
    # Orthogonal assessment layers — the doctrine must NOT impose one severity
    # scale (would corrupt QA verdicts / snapshot confidence — ADR-F028 3B).
    assert "layered" in profile.lower()


async def test_commercial_doctrine_seed_updates_old_and_never_clobbers_edit(
    db_session: AsyncSession,
) -> None:
    """0066's seed UPDATES a row still carrying the verbatim 0054 profile to the
    doctrine, but NEVER overwrites an operator's admin-PATCH edit — the WHERE
    guard matches only the old seed value (0054/0055 check-before-write
    precedent)."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    spec = importlib.util.spec_from_file_location(
        "migration_0066", versions / "0066_commercial_profile_doctrine.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_0066"] = module
    try:
        spec.loader.exec_module(module)
        area = (
            await db_session.execute(select(PracticeArea).where(PracticeArea.key == "commercial"))
        ).scalar_one()

        # A row still on the 0054 seed → the migration upgrades it to the doctrine.
        area.profile_md = module._OLD_PROFILE_MD
        await db_session.flush()
        conn = await db_session.connection()
        await conn.run_sync(lambda c: module._seed_commercial_doctrine(c))
        await db_session.refresh(area)
        assert area.profile_md == module._COMMERCIAL_DOCTRINE_MD

        # An operator edit is preserved (the guard misses a non-seed value).
        area.profile_md = "operator-edited commercial profile"
        await db_session.flush()
        conn = await db_session.connection()
        await conn.run_sync(lambda c: module._seed_commercial_doctrine(c))
        await db_session.refresh(area)
        assert area.profile_md == "operator-edited commercial profile"
    finally:
        sys.modules.pop("migration_0066", None)
