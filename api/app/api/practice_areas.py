"""Practice-area endpoints — F1-S2 reads + F1-S3 config/admin (fork, ADR-F002/F004/F010).

* ``GET /api/v1/practice-areas`` — bearer-authed read for every active user
  (transparency, PRD §1.3): the cockpit's left rail with each area's honest
  configured state, plus the area profile and config (an agent instruction
  must be readable in the UI or the source — CLAUDE.md). ``configured`` is
  DERIVED from real config in F1-S3.
* ``PATCH /api/v1/practice-areas/{key}`` — ADMIN config write (profile,
  default tier floor, declarative agent_config). ``agent_config`` is
  shape-validated by the area renderer; a forbidden subagent ``model`` key
  (gateway bypass, ADR-F010) is a 400.
* ``POST``/``DELETE`` ``/{key}/skills`` — ADMIN attach/detach of a
  filesystem-canonical skill (by name; registry-validated).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.area_agent import build_area_subagents
from app.agents.capabilities import TOOL_GROUP_REGISTRY
from app.api.dependencies import ActiveUser, AdminUser
from app.audit import audit_action
from app.db.session import get_db
from app.errors import Conflict, NotFound, ValidationError
from app.models.playbook import Playbook
from app.models.practice_area import (
    PracticeArea,
    PracticeAreaPlaybook,
    PracticeAreaSkill,
    PracticeAreaToolGroup,
)
from app.models.project import Project
from app.schemas.practice_areas import (
    PlaybookAttachRequest,
    PracticeAreaConfigUpdate,
    PracticeAreaCreate,
    PracticeAreaListResponse,
    PracticeAreaRead,
    SkillAttachRequest,
    ToolGroupAttachRequest,
)
from app.skills.registry import MutableSkillRegistry

router = APIRouter(prefix="/practice-areas", tags=["practice-areas"])


def _registry(request: Request) -> MutableSkillRegistry:
    holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    if holder is None:  # pragma: no cover - lifespan always installs it
        raise NotFound("Skill registry is not initialised.")
    return holder


def _is_configured(area: PracticeArea) -> bool:
    """An area is configured ⇔ it has a non-empty profile the agent builds
    from (F1-S3 derives ``configured`` from real config, not the seed)."""
    return bool(area.profile_md and area.profile_md.strip())


async def _bound_skill_names(db: AsyncSession, area_id: uuid.UUID) -> list[str]:
    rows = (
        (
            await db.execute(
                select(PracticeAreaSkill.skill_name)
                .where(PracticeAreaSkill.practice_area_id == area_id)
                .order_by(PracticeAreaSkill.skill_name)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _to_read(area: PracticeArea, bound_skills: list[str]) -> PracticeAreaRead:
    return PracticeAreaRead(
        id=area.id,
        key=area.key,
        name=area.name,
        unit_label=area.unit_label,
        configured=_is_configured(area),
        position=area.position,
        profile_md=area.profile_md,
        default_tier_floor=area.default_tier_floor,
        agent_config=area.agent_config or {},
        bound_skills=bound_skills,
        created_at=area.created_at,
        updated_at=area.updated_at,
    )


async def _load_area_or_404(db: AsyncSession, key: str) -> PracticeArea:
    area = (
        await db.execute(select(PracticeArea).where(PracticeArea.key == key))
    ).scalar_one_or_none()
    if area is None:
        # 404, never 403/existence-leak (CLAUDE.md).
        raise NotFound("practice area not found", details={"key": key})
    return area


@router.get(
    "",
    response_model=PracticeAreaListResponse,
    summary="List practice areas (cockpit left rail), position order.",
)
async def list_practice_areas(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PracticeAreaListResponse:
    """GET /api/v1/practice-areas

    Deployment-wide curated list (single-org model — NORTH-STAR invariant
    4: no per-tenant scoping), ordered by ``position`` then ``key``.
    """
    rows = (
        (await db.execute(select(PracticeArea).order_by(PracticeArea.position, PracticeArea.key)))
        .scalars()
        .all()
    )
    out: list[PracticeAreaRead] = []
    for area in rows:
        out.append(_to_read(area, await _bound_skill_names(db, area.id)))
    return PracticeAreaListResponse(practice_areas=out)


@router.patch(
    "/{key}",
    response_model=PracticeAreaRead,
    summary="Configure a practice area (admin).",
)
async def update_practice_area_config(
    key: str,
    payload: PracticeAreaConfigUpdate,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> PracticeAreaRead:
    """PATCH /api/v1/practice-areas/{key} — partial config update (admin).

    ``agent_config`` is shape-validated by the area renderer before write:
    an invalid subagent spec, an unsupported key, or a forbidden ``model``
    key (ADR-F010 — gateway bypass) is rejected as a 400, never persisted.
    """
    area = await _load_area_or_404(db, key)

    fields = payload.model_dump(exclude_unset=True)
    if "profile_md" in fields:
        area.profile_md = fields["profile_md"]
    if "default_tier_floor" in fields:
        area.default_tier_floor = fields["default_tier_floor"]
    if "agent_config" in fields:
        cfg = fields["agent_config"] or {}
        # Validate the declarative shape (raises ValueError on bad subagent
        # specs / forbidden model key). Treat area config as untrusted input.
        # UX-B-4 (ADR-F017): a subagent may reference only skills BOUND TO THIS
        # AREA — its isolated source is a subset of the area source — so validate
        # against the area's bound names (themselves the registry-known set the
        # attach endpoint admits). A subagent skill outside the area's set is
        # rejected here, never stored as a dangling reference. Best-effort: with
        # no bound skills the area can carry no skill-bearing subagent, so an
        # empty allow-list correctly rejects any subagent `skills`.
        area_bound = await _bound_skill_names(db, area.id)
        try:
            build_area_subagents(cfg, known_skill_names=area_bound)
        except ValueError as exc:
            raise ValidationError(str(exc), details={"field": "agent_config"}) from exc
        area.agent_config = cfg
    # Keep the stored column consistent with the derived state.
    area.configured = _is_configured(area)
    # Fix in passing (SETUP-4a): stamp updated_at on the config write — the column was
    # never touched before, so an edited area looked stale forever.
    area.updated_at = datetime.now(UTC)

    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.configure",
        resource_type="practice_area",
        resource_id=area.key,
        practice_area_id=area.id,
        request=request,
        details={"fields": sorted(fields.keys())},
    )
    await db.commit()
    await db.refresh(area)
    return _to_read(area, await _bound_skill_names(db, area.id))


@router.post(
    "",
    response_model=PracticeAreaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a practice area (admin).",
)
async def create_practice_area(
    payload: PracticeAreaCreate,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> PracticeAreaRead:
    """POST /api/v1/practice-areas — create a practice area (admin, ADR-F062).

    ``key`` is an anchored slug (Pydantic). ``agent_config`` is shape-validated by the
    area renderer (a forbidden ``model`` key is a 400, ADR-F010); a new area has no bound
    skills yet, so a skill-bearing subagent is rejected (empty allow-list — the PATCH
    posture). ``tool_groups`` is validated against the code registry (an unknown group is a
    404 — no dead row lands). ``position`` auto-appends ``max(position)+1``; ``configured``
    is server-derived from the profile. A duplicate key is a 409.
    """
    # Validate agent_config the SAME way the PATCH handler does (reuse the renderer's
    # shape/ADR-F010 gate verbatim). A new area has no bound skills, so any subagent
    # `skills` reference is rejected against the empty allow-list.
    if payload.agent_config is not None:
        try:
            build_area_subagents(payload.agent_config, known_skill_names=[])
        except ValueError as exc:
            raise ValidationError(str(exc), details={"field": "agent_config"}) from exc

    # Validate every requested tool group against the code registry (reject, don't store a
    # dead row). 404 mirrors the skill-not-in-registry posture.
    for group_key in payload.tool_groups:
        if group_key not in TOOL_GROUP_REGISTRY:
            raise NotFound(
                f"Tool group {group_key!r} is not in the registry.",
                details={"group_key": group_key},
            )

    # position auto-appends (reorder is SETUP-4b). max(position) over the curated set.
    next_position = (
        await db.execute(select(func.coalesce(func.max(PracticeArea.position), -1)))
    ).scalar_one() + 1
    area = PracticeArea(
        key=payload.key,
        name=payload.name,
        unit_label=payload.unit_label,
        profile_md=payload.profile_md,
        default_tier_floor=payload.default_tier_floor,
        agent_config=payload.agent_config or {},
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
            details={"key": payload.key},
        ) from exc
    # Dedupe the requested groups (preserve order) so a repeated key can't violate the PK.
    seen: set[str] = set()
    for group_key in payload.tool_groups:
        if group_key in seen:
            continue
        seen.add(group_key)
        db.add(PracticeAreaToolGroup(practice_area_id=area.id, group_key=group_key))

    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.create",
        resource_type="practice_area",
        resource_id=area.key,
        practice_area_id=area.id,
        request=request,
        details={"key": area.key, "tool_group_count": len(seen)},
    )
    await db.commit()
    await db.refresh(area)
    return _to_read(area, await _bound_skill_names(db, area.id))


@router.delete(
    "/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a practice area (admin).",
    response_class=Response,
)
async def delete_practice_area(
    key: str,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Response:
    """DELETE /api/v1/practice-areas/{key} — delete a practice area (admin, ADR-F062).

    REFUSES (409, count only) while any NON-ARCHIVED project files under the area: the
    ``projects.practice_area_id`` FK is ON DELETE SET NULL to protect matter/audit data,
    and silently unfiling live matters is the surprise it guards against — the admin
    archives or re-files those matters first. With zero live references the area is deleted
    (its skill/playbook/tool-group rows CASCADE; archived projects and audit rows SET NULL).
    Stale ``matter_capability_toggles`` rows are tolerated at resolve time (recon-verified).
    """
    area = await _load_area_or_404(db, key)
    live_refs = (
        await db.execute(
            select(func.count())
            .select_from(Project)
            .where(Project.practice_area_id == area.id, Project.archived_at.is_(None))
        )
    ).scalar_one()
    if live_refs > 0:
        raise Conflict(
            "Practice area has active matters filed under it; archive or re-file them first.",
            details={"key": key, "active_matter_count": live_refs},
        )
    area_id = area.id
    await db.delete(area)
    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.delete",
        resource_type="practice_area",
        resource_id=key,
        practice_area_id=area_id,
        request=request,
        details={"key": key},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{key}/tool-groups",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Attach a tool group to a practice area (admin).",
    response_class=Response,
)
async def attach_practice_area_tool_group(
    key: str,
    payload: ToolGroupAttachRequest,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Response:
    """POST /api/v1/practice-areas/{key}/tool-groups — ADR-F062 (mirrors the skills pair).

    Body ``{group_key}``; the group must exist in the code registry (unknown → 404). The
    binding makes the group's tools AVAILABLE to matters under the area (the lawyer toggles
    it per matter). Re-attaching returns 409.
    """
    area = await _load_area_or_404(db, key)
    if payload.group_key not in TOOL_GROUP_REGISTRY:
        raise NotFound(
            f"Tool group {payload.group_key!r} is not in the registry.",
            details={"group_key": payload.group_key},
        )
    area_id = area.id
    db.add(PracticeAreaToolGroup(practice_area_id=area_id, group_key=payload.group_key))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(
            "Tool group is already attached to this practice area.",
            details={"key": key, "group_key": payload.group_key},
        ) from exc
    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.tool_group_attach",
        resource_type="practice_area",
        resource_id=key,
        practice_area_id=area_id,
        request=request,
        details={"group_key": payload.group_key},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{key}/tool-groups/{group_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a tool group from a practice area (admin).",
    response_class=Response,
)
async def detach_practice_area_tool_group(
    key: str,
    group_key: str,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Response:
    """DELETE /api/v1/practice-areas/{key}/tool-groups/{group_key} — ADR-F062.

    Idempotent: detaching a not-attached group is a no-op 204 (the desired end state
    holds); an unknown area is a 404.
    """
    area = await _load_area_or_404(db, key)
    await db.execute(
        delete(PracticeAreaToolGroup).where(
            PracticeAreaToolGroup.practice_area_id == area.id,
            PracticeAreaToolGroup.group_key == group_key,
        )
    )
    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.tool_group_detach",
        resource_type="practice_area",
        resource_id=key,
        practice_area_id=area.id,
        request=request,
        details={"group_key": group_key},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{key}/skills",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Attach a skill to a practice area (admin).",
    response_class=Response,
)
async def attach_practice_area_skill(
    key: str,
    payload: SkillAttachRequest,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Response:
    """POST /api/v1/practice-areas/{key}/skills

    Body ``{skill_name}``; the skill must exist in the in-memory registry.
    Re-attaching returns 409. (Config-landed in S3; live attachment to the
    running agent is the S9-gated activation slice — plan §non-goals.)
    """
    area = await _load_area_or_404(db, key)
    registry = _registry(request).current()
    if registry.get(payload.skill_name) is None:
        raise NotFound(
            f"Skill {payload.skill_name!r} is not in the registry.",
            details={"skill_name": payload.skill_name},
        )
    area_id = area.id
    db.add(PracticeAreaSkill(practice_area_id=area_id, skill_name=payload.skill_name))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(
            "Skill is already attached to this practice area.",
            details={"key": key, "skill_name": payload.skill_name},
        ) from exc
    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.skill_attach",
        resource_type="practice_area",
        resource_id=key,
        practice_area_id=area_id,
        request=request,
        details={"skill_name": payload.skill_name},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{key}/skills/{skill_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a skill from a practice area (admin).",
    response_class=Response,
)
async def detach_practice_area_skill(
    key: str,
    skill_name: str,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Response:
    """DELETE /api/v1/practice-areas/{key}/skills/{skill_name}

    Idempotent: detaching a not-attached skill is a 404 on the area only;
    a missing binding is a no-op 204 (the desired end state holds).
    """
    area = await _load_area_or_404(db, key)
    await db.execute(
        delete(PracticeAreaSkill).where(
            PracticeAreaSkill.practice_area_id == area.id,
            PracticeAreaSkill.skill_name == skill_name,
        )
    )
    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.skill_detach",
        resource_type="practice_area",
        resource_id=key,
        practice_area_id=area.id,
        request=request,
        details={"skill_name": skill_name},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{key}/playbooks",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Attach a playbook to a practice area (admin).",
    response_class=Response,
)
async def attach_practice_area_playbook(
    key: str,
    payload: PlaybookAttachRequest,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Response:
    """POST /api/v1/practice-areas/{key}/playbooks — ADR-F054 (capability panel).

    Body ``{playbook_id}``; the playbook must exist and not be soft-deleted. The
    binding makes the playbook AVAILABLE to matters under the area (the lawyer toggles
    it on/off per matter). Re-attaching returns 409.
    """
    area = await _load_area_or_404(db, key)
    playbook = (
        await db.execute(
            select(Playbook).where(
                Playbook.id == payload.playbook_id,
                Playbook.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if playbook is None:
        raise NotFound(
            f"Playbook {payload.playbook_id} is not available.",
            details={"playbook_id": str(payload.playbook_id)},
        )
    area_id = area.id
    db.add(PracticeAreaPlaybook(practice_area_id=area_id, playbook_id=payload.playbook_id))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(
            "Playbook is already attached to this practice area.",
            details={"key": key, "playbook_id": str(payload.playbook_id)},
        ) from exc
    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.playbook_attach",
        resource_type="practice_area",
        resource_id=key,
        practice_area_id=area_id,
        request=request,
        details={"playbook_id": str(payload.playbook_id)},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{key}/playbooks/{playbook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a playbook from a practice area (admin).",
    response_class=Response,
)
async def detach_practice_area_playbook(
    key: str,
    playbook_id: uuid.UUID,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Response:
    """DELETE /api/v1/practice-areas/{key}/playbooks/{playbook_id} — ADR-F054.

    Idempotent: detaching a not-attached playbook is a no-op 204 (the desired end
    state holds); an unknown area is a 404.
    """
    area = await _load_area_or_404(db, key)
    await db.execute(
        delete(PracticeAreaPlaybook).where(
            PracticeAreaPlaybook.practice_area_id == area.id,
            PracticeAreaPlaybook.playbook_id == playbook_id,
        )
    )
    await audit_action(
        db,
        user_id=admin.id,
        action="practice_area.playbook_detach",
        resource_type="practice_area",
        resource_id=key,
        practice_area_id=area.id,
        request=request,
        details={"playbook_id": str(playbook_id)},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
