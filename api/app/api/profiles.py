"""Profile-apply API — materialise a shipped profile onto a real area (B-7a).

ADR-F067 D4. Three admin endpoints over the boot-loaded profile registry
(``app.state.profile_registry``):

* ``GET  /api/v1/profiles``            — the wizard picker (summaries).
* ``GET  /api/v1/profiles/{name}``     — one profile's full manifest (review).
* ``POST /api/v1/profiles/{name}/apply`` — the transaction: create/patch the
  area + adopt the matching Library entries + write bindings + set the roster +
  set HITL, all-or-nothing, in ONE commit.

The apply endpoint follows the ``publish_user_skill`` law (api/user_skills.py):
one ``commit()`` at the end; validate everything before the first mutation;
``on_conflict_do_nothing`` throughout (idempotent, no mid-sequence rollback); and
it reuses the *pure helpers* of the practice-area write surface — never the
attach/adopt handler bodies, whose ``except IntegrityError: rollback()`` would
nuke the transaction. Operator is fenced (ADR-F064): apply mutates tenant config
+ Library, which is tenant state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.capabilities import KIND_SKILL, KIND_TOOL
from app.api.admin import _OPERATOR_EXCLUDED_MSG
from app.api.dependencies import AdminUser, tenant_admin_visibility
from app.api.practice_areas import _is_configured, _require_registered_group
from app.audit import audit_action
from app.db.session import get_db
from app.errors import Conflict, Forbidden, InternalError, NotFound
from app.models.practice_area import (
    OrgLibraryEntry,
    PracticeArea,
    PracticeAreaSkill,
    PracticeAreaToolGroup,
)
from app.profiles.registry import ProfileRecord, ProfileRegistry
from app.schemas.profiles import (
    ProfileApplyRequest,
    ProfileApplyResult,
    ProfileDetail,
    ProfileListResponse,
    ProfileSummary,
)
from app.skills.registry import MutableSkillRegistry

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _profile_registry(request: Request) -> ProfileRegistry:
    reg: ProfileRegistry | None = getattr(request.app.state, "profile_registry", None)
    if reg is None:  # pragma: no cover - the fail-loud lifespan always installs it
        raise InternalError(message="Profile registry is not initialised.")
    return reg


def _live_skill_names(request: Request) -> set[str]:
    holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    if holder is None:  # pragma: no cover - the lifespan always installs it
        raise InternalError(message="Skill registry is not initialised.")
    return set(holder.current().names())


def _summary(record: ProfileRecord) -> ProfileSummary:
    m = record.manifest
    b = m.bindings
    return ProfileSummary(
        name=m.name,
        kind=m.kind,
        display_name=m.display_name,
        description=m.description,
        area_key=m.area_key,
        unit_label=m.unit_label,
        skill_count=len(b.skills) if b else 0,
        tool_group_count=len(b.tool_groups) if b else 0,
        subagent_count=len(m.agent_config.get("subagents", [])),
    )


def _detail(record: ProfileRecord) -> ProfileDetail:
    m = record.manifest
    b = m.bindings
    return ProfileDetail(
        **_summary(record).model_dump(),
        doctrine=record.doctrine,
        default_tier_floor=m.default_tier_floor,
        default_budget_profile=m.default_budget_profile,
        skills=list(b.skills) if b else [],
        tool_groups=list(b.tool_groups) if b else [],
        agent_config=m.agent_config,
        hitl=m.hitl,
    )


@router.get(
    "",
    response_model=ProfileListResponse,
    summary="List shipped profiles (the setup-wizard picker).",
)
async def list_profiles(admin: AdminUser, request: Request) -> ProfileListResponse:
    """GET /api/v1/profiles — every shipped profile, name-sorted."""
    reg = _profile_registry(request)
    return ProfileListResponse(profiles=[_summary(r) for r in reg.list_records()])


@router.get(
    "/{name}",
    response_model=ProfileDetail,
    summary="Get one shipped profile's full manifest (wizard review).",
)
async def get_profile(name: str, admin: AdminUser, request: Request) -> ProfileDetail:
    """GET /api/v1/profiles/{name} — doctrine, bindings, roster, HITL defaults."""
    record = _profile_registry(request).get(name)
    if record is None:
        raise NotFound("Profile not found.", details={"name": name})
    return _detail(record)


@router.post(
    "/{name}/apply",
    response_model=ProfileApplyResult,
    summary="Apply a profile onto a practice area (admin) — copy-not-link.",
)
async def apply_profile(
    name: str,
    payload: ProfileApplyRequest,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> ProfileApplyResult:
    """POST /api/v1/profiles/{name}/apply — materialise a shipped profile.

    Creates/patches the target area, adopts the matching Library entries, writes
    the skill/tool bindings, and sets the roster + HITL policy — one transaction,
    idempotent, all-or-nothing. On a fresh org this both reproduces the seeded
    area config AND adopts the Library (killing the G13 first-run cliff). Operator
    is fenced (ADR-F064). See the module docstring for the transaction law.

    Re-apply semantics are asymmetric by design: manifest-owned *scalar* fields
    (doctrine/roster/unit/defaults/hitl) are AUTHORITATIVELY overwritten (with the
    changed field names recorded in the audit), while bindings/adoptions are only
    ADDED (`on_conflict_do_nothing`) — apply never strips a skill/tool an admin
    added or detached. It ensures the profile's caps are present, it does not prune.
    """
    # Operator fence: apply mutates tenant config + Library = tenant state.
    if not tenant_admin_visibility(admin):
        raise Forbidden(message=_OPERATOR_EXCLUDED_MSG)

    record = _profile_registry(request).get(name)
    if record is None:
        raise NotFound("Profile not found.", details={"name": name})
    manifest = record.manifest

    # --- resolve target identity + the source-of-truth config -------------------
    if manifest.kind == "area":
        # Identity comes from the manifest; overrides are forbidden (422).
        if (
            payload.target_key is not None
            or payload.name is not None
            or payload.unit_label is not None
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Profile {name!r} is an area profile — its key/name/unit come from the "
                    "manifest; omit target_key/name/unit_label."
                ),
            )
        assert manifest.area_key is not None and manifest.bindings is not None  # kind=='area'
        target_key = manifest.area_key
        target_name = manifest.display_name
        # `unit_label` is a closed Literal on the manifest but a free string on
        # the blank-override path and on the DB column — widen to str | None.
        target_unit: str | None = manifest.unit_label
        doctrine = record.doctrine
        skills = list(manifest.bindings.skills)
        tool_groups = list(manifest.bindings.tool_groups)
        agent_config = manifest.agent_config
        hitl_policy = {k: True for k, enabled in manifest.hitl.items() if enabled}
        tier_floor = manifest.default_tier_floor
        budget_profile = manifest.default_budget_profile
    else:  # blank — the admin names a brand-new area; there is nothing to bind.
        if payload.target_key is None or payload.name is None or payload.unit_label is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Profile {name!r} is the blank profile — target_key, name and "
                    "unit_label are required."
                ),
            )
        target_key = payload.target_key
        target_name = payload.name
        target_unit = payload.unit_label
        doctrine = None
        skills = []
        tool_groups = []
        agent_config = {}
        hitl_policy = {}
        tier_floor = None
        budget_profile = None

    # --- validate bindings against the LIVE registries BEFORE any write ---------
    # The manifest was fully load-validated at boot; the only thing that can drift
    # at runtime is the skill registry (a SIGHUP reload could drop a skill). Refuse
    # the whole apply rather than adopt/bind a skill that no longer resolves.
    if skills:
        known = _live_skill_names(request)
        drifted = sorted(s for s in skills if s not in known)
        if drifted:
            raise HTTPException(
                status_code=422,
                detail=f"Profile binds skill(s) no longer in the registry: {drifted}",
            )
    for group_key in tool_groups:
        _require_registered_group(group_key)  # 404 on unknown/composition-only

    # --- upsert the area (create-or-overwrite manifest-owned fields) ------------
    # FOR UPDATE serialises two concurrent applies to the same area: the second
    # blocks on the row lock until the first commits, then sees the settled state
    # (values are deterministic from the immutable manifest, so it converges).
    area = (
        await db.execute(
            select(PracticeArea).where(PracticeArea.key == target_key).with_for_update()
        )
    ).scalar_one_or_none()
    area_created = False
    changed_fields: list[str] = []

    if area is None:
        next_position = (
            await db.execute(select(func.coalesce(func.max(PracticeArea.position), -1)))
        ).scalar_one() + 1
        area = PracticeArea(
            key=target_key,
            name=target_name,
            unit_label=target_unit,
            profile_md=doctrine,
            default_tier_floor=tier_floor,
            default_budget_profile=budget_profile,
            agent_config=agent_config or {},
            hitl_policy=hitl_policy,
            position=next_position,
        )
        area.configured = _is_configured(area)
        db.add(area)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise Conflict(
                "A practice area with this key already exists.",
                details={"key": target_key},
            ) from exc
        area_created = True
    elif manifest.kind == "blank":
        # Blank only CREATES — refuse to overlay an existing area (no config to copy).
        raise Conflict(
            "A practice area with this key already exists.",
            details={"key": target_key},
        )
    else:
        # Authoritative overwrite of manifest-owned fields; record which changed
        # (names only — Q2 audit-diff). ``configured`` is derived, not tracked.
        for field, new_value in (
            ("name", target_name),
            ("unit_label", target_unit),
            ("profile_md", doctrine),
            ("default_tier_floor", tier_floor),
            ("default_budget_profile", budget_profile),
            ("agent_config", agent_config or {}),
            ("hitl_policy", hitl_policy),
        ):
            if getattr(area, field) != new_value:
                setattr(area, field, new_value)
                changed_fields.append(field)
        area.configured = _is_configured(area)
        if changed_fields:
            # PracticeArea has no `onupdate=` on updated_at (server_default only), so
            # stamp it here on a real edit — mirrors the PATCH handler (SETUP-4a), else
            # a re-applied/manifest-updated area reads stale forever.
            area.updated_at = datetime.now(UTC)

    # --- adopt Library entries + write bindings (idempotent) -------------------
    adopted: dict[str, list[str]] = {KIND_SKILL: [], KIND_TOOL: []}
    for kind, key in [(KIND_SKILL, s) for s in skills] + [(KIND_TOOL, g) for g in tool_groups]:
        stmt = (
            pg_insert(OrgLibraryEntry)
            .values(capability_kind=kind, capability_key=key, adopted_by=admin.id)
            .on_conflict_do_nothing(constraint="pk_org_library_entries")
            .returning(OrgLibraryEntry.capability_key)
        )
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            adopted[kind].append(key)

    bindings_written = {KIND_SKILL: 0, KIND_TOOL: 0}
    for skill_name in skills:
        stmt = (
            pg_insert(PracticeAreaSkill)
            .values(practice_area_id=area.id, skill_name=skill_name)
            .on_conflict_do_nothing(constraint="pk_practice_area_skills")
            .returning(PracticeAreaSkill.skill_name)
        )
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            bindings_written[KIND_SKILL] += 1
    for group_key in tool_groups:
        stmt = (
            pg_insert(PracticeAreaToolGroup)
            .values(practice_area_id=area.id, group_key=group_key)
            .on_conflict_do_nothing(constraint="pk_practice_area_tool_groups")
            .returning(PracticeAreaToolGroup.group_key)
        )
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            bindings_written[KIND_TOOL] += 1

    roster_subagents = len(agent_config.get("subagents", [])) if agent_config else 0
    hitl_tools = len(hitl_policy)

    await audit_action(
        db,
        user_id=admin.id,
        action="profile.apply",
        resource_type="practice_area",
        resource_id=target_key,
        practice_area_id=area.id,
        request=request,
        details={
            "profile": name,
            "target_key": target_key,
            "area_created": area_created,
            "adopted": adopted,
            "adopted_count": len(adopted[KIND_SKILL]) + len(adopted[KIND_TOOL]),
            "skills_bound": bindings_written[KIND_SKILL],
            "tools_bound": bindings_written[KIND_TOOL],
            "roster_subagents": roster_subagents,
            "hitl_tools": hitl_tools,
            "changed_fields": changed_fields,
        },
    )
    await db.commit()

    return ProfileApplyResult(
        profile_name=name,
        target_key=target_key,
        area_created=area_created,
        adopted=adopted,
        bindings_written=bindings_written,
        roster_subagents=roster_subagents,
        hitl_tools=hitl_tools,
        changed_fields=changed_fields,
    )


__all__ = ["router"]
