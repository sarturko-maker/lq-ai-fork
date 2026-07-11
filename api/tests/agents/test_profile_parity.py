"""B-7a parity oracle (ADR-F067 D4): the shipped Commercial/Privacy manifests
reproduce today's seeded-effective state, field-for-field.

Both sides are real sources — the manifest (file) and the migrated test DB's
seeded ``practice_areas`` row — so a byte drift in either the doctrine, the
roster ``system_prompt``s, the unit vocabulary, or the bindings breaks CI. This
is the drift guard that keeps the manifests from silently diverging from the
seed migrations (0053/0054/0066/0067/0072/0073/0056/0086) as they evolve.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.capabilities import KIND_SKILL, KIND_TOOL, RECOMMENDED_LIBRARY_SETS
from app.config import get_settings
from app.models.practice_area import PracticeArea, PracticeAreaSkill, PracticeAreaToolGroup
from app.profiles.bootstrap import resolve_profiles_dir
from app.profiles.loader import load_profiles
from app.skills.bootstrap import resolve_skill_dirs
from app.skills.loader import load_registry

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def profile_registry() -> Any:
    settings = get_settings()
    skills_dir, community_dir = resolve_skill_dirs(settings)
    skills = load_registry(skills_dir, community_skills_dir=community_dir)
    return load_profiles(resolve_profiles_dir(settings), skill_registry=skills)


async def _seeded_bindings(db: AsyncSession, area_id: Any) -> tuple[set[str], set[str]]:
    skills = set(
        (
            await db.execute(
                select(PracticeAreaSkill.skill_name).where(
                    PracticeAreaSkill.practice_area_id == area_id
                )
            )
        )
        .scalars()
        .all()
    )
    tools = set(
        (
            await db.execute(
                select(PracticeAreaToolGroup.group_key).where(
                    PracticeAreaToolGroup.practice_area_id == area_id
                )
            )
        )
        .scalars()
        .all()
    )
    return skills, tools


@pytest.mark.parametrize("key", ["commercial", "privacy"])
async def test_manifest_reproduces_seeded_state(
    db_session: AsyncSession, profile_registry: Any, key: str
) -> None:
    record = profile_registry.get(key)
    assert record is not None, f"missing shipped profile {key!r}"
    manifest = record.manifest
    area = (
        await db_session.execute(select(PracticeArea).where(PracticeArea.key == key))
    ).scalar_one()

    # (a) doctrine — exact string parity with the seeded profile_md.
    assert record.doctrine == area.profile_md

    # (b) roster — deep-equal pins the three long system_prompt strings too.
    assert manifest.agent_config == area.agent_config

    # (c) scalars.
    assert manifest.unit_label == area.unit_label
    assert manifest.default_tier_floor == area.default_tier_floor
    assert manifest.default_budget_profile == area.default_budget_profile
    assert manifest.display_name == area.name
    seeded_hitl = {k for k, v in (area.hitl_policy or {}).items() if v}
    manifest_hitl = {k for k, v in manifest.hitl.items() if v}
    assert manifest_hitl == seeded_hitl

    # (d) bindings parity: manifest == seeded DB bindings == RECOMMENDED constant.
    assert manifest.bindings is not None
    seeded_skills, seeded_tools = await _seeded_bindings(db_session, area.id)
    assert set(manifest.bindings.skills) == seeded_skills
    assert set(manifest.bindings.tool_groups) == seeded_tools
    recommended = RECOMMENDED_LIBRARY_SETS[key]
    assert set(manifest.bindings.skills) == set(recommended[KIND_SKILL])
    assert set(manifest.bindings.tool_groups) == set(recommended.get(KIND_TOOL, ()))
