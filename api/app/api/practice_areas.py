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
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.area_agent import build_area_subagents
from app.api.dependencies import ActiveUser, AdminUser
from app.audit import audit_action
from app.db.session import get_db
from app.errors import Conflict, NotFound, ValidationError
from app.models.practice_area import PracticeArea, PracticeAreaSkill
from app.schemas.practice_areas import (
    PracticeAreaConfigUpdate,
    PracticeAreaListResponse,
    PracticeAreaRead,
    SkillAttachRequest,
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
        # UX-B-3 (ADR-F016): pass the registry's current names so a subagent
        # that references an unknown skill is rejected here, not stored as a
        # dangling reference (close the drift gap at config time). Best-effort:
        # read the holder directly (not _registry, which 404s) so a process
        # without a registry skips the skill check rather than failing the
        # PATCH — production always has one installed (lifespan / worker).
        holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
        known_skill_names = holder.current().names() if holder is not None else None
        try:
            build_area_subagents(cfg, known_skill_names=known_skill_names)
        except ValueError as exc:
            raise ValidationError(str(exc), details={"field": "agent_config"}) from exc
        area.agent_config = cfg
    # Keep the stored column consistent with the derived state.
    area.configured = _is_configured(area)

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
