"""Matter capability-panel endpoints — per-matter capability toggles (ADR-F054).

The cockpit capability panel: the practice AREA curates which capabilities are
AVAILABLE (skills, tools, playbooks; MCP placeholder), the LAWYER toggles a subset
on/off PER MATTER (persisted, survives the matter's conversations). "System proposes,
user owns." The composition point (``app.agents.composition``) reads the same toggles
through the same inventory, so the panel shows exactly what the agent gets — and a
toggled-off capability is genuinely removed from the agent's next run.

**Per-user isolation.** Both endpoints load the matter via the projects
``_load_visible_project`` rule: owner-scoped, archived-excluded, **404** on miss /
cross-user / archived (never 403 — no existence leak).

Audited (``matter.capability_toggle``) with counts/kinds/keys only — capability keys are
identifiers (skill names, tool-group keys, playbook ids), never user content.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.capabilities import (
    CapabilityInventory,
    build_area_inventory,
    empty_inventory,
)
from app.api.dependencies import ActiveUser
from app.api.projects import _load_visible_project
from app.audit import audit_action
from app.db.session import get_db
from app.models.playbook import Playbook
from app.models.practice_area import (
    DeploymentCapabilityToggle,
    PracticeArea,
    PracticeAreaPlaybook,
    PracticeAreaSkill,
    PracticeAreaToolGroup,
)
from app.models.project import MatterCapabilityToggle, Project
from app.schemas.matter_capabilities import (
    CapabilityEntryRead,
    CapabilityInventoryResponse,
    CapabilityOverridesUpdate,
    CapabilitySectionRead,
)
from app.skills.registry import MutableSkillRegistry, SkillRegistry

router = APIRouter(prefix="/matters", tags=["matter-capabilities"])

_DEFAULT_UNIT_LABEL = "Matter"


def _registry_or_none(request: Request) -> SkillRegistry | None:
    """Current skill-registry snapshot from ``app.state`` (or None if uninstalled).

    Graceful — mirrors the composition point's ``skill_registry_provider`` (None ⇒
    the skills section is empty), rather than the admin ``_registry`` which 404s.
    """
    holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    return holder.current() if holder is not None else None


async def _resolve_inventory(
    db: AsyncSession, request: Request, project: Project
) -> tuple[CapabilityInventory, str | None, str]:
    """Build the matter's capability inventory + (practice_area_key, unit_label).

    A matter with no practice area (unfiled/legacy), or whose area row is gone, gets
    the empty inventory (only the MCP placeholder) and the default unit label —
    today's substrate-only behaviour.
    """
    if project.practice_area_id is None:
        return empty_inventory(), None, _DEFAULT_UNIT_LABEL
    area = await db.get(PracticeArea, project.practice_area_id)
    if area is None:
        return empty_inventory(), None, _DEFAULT_UNIT_LABEL

    bound_skill_names = (
        (
            await db.execute(
                select(PracticeAreaSkill.skill_name).where(
                    PracticeAreaSkill.practice_area_id == area.id
                )
            )
        )
        .scalars()
        .all()
    )
    area_playbooks = (
        (
            await db.execute(
                select(Playbook)
                .join(PracticeAreaPlaybook, PracticeAreaPlaybook.playbook_id == Playbook.id)
                .where(
                    PracticeAreaPlaybook.practice_area_id == area.id,
                    Playbook.deleted_at.is_(None),
                )
                .order_by(Playbook.name)
            )
        )
        .scalars()
        .all()
    )
    # SETUP-4a (ADR-F062): tool availability is DATA (practice_area_tool_groups rows) and
    # the deployment-wide (Level 0) toggles narrow the whole panel — feed both to the one
    # inventory chokepoint so the panel shows exactly what the agent gets.
    tool_group_keys = (
        (
            await db.execute(
                select(PracticeAreaToolGroup.group_key).where(
                    PracticeAreaToolGroup.practice_area_id == area.id
                )
            )
        )
        .scalars()
        .all()
    )
    deployment_toggles = (await db.execute(select(DeploymentCapabilityToggle))).scalars().all()
    inventory = build_area_inventory(
        bound_skill_names=bound_skill_names,
        registry=_registry_or_none(request),
        area_playbooks=area_playbooks,
        tool_group_keys=tool_group_keys,
        deployment_toggles=deployment_toggles,
    )
    return inventory, area.key, area.unit_label


async def _load_toggles(db: AsyncSession, project_id: uuid.UUID) -> list[MatterCapabilityToggle]:
    return list(
        (
            await db.execute(
                select(MatterCapabilityToggle).where(
                    MatterCapabilityToggle.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )


def _to_response(
    inventory: CapabilityInventory,
    toggles: list[MatterCapabilityToggle],
    *,
    practice_area_key: str | None,
    unit_label: str,
) -> CapabilityInventoryResponse:
    enabled = inventory.enabled_map(toggles)
    sections = [
        CapabilitySectionRead(
            kind=section.kind,
            label=section.label,
            entries=[
                CapabilityEntryRead(
                    capability_kind=entry.kind,
                    capability_key=entry.key,
                    label=entry.label,
                    description=entry.description,
                    available=entry.available,
                    enabled=enabled[(entry.kind, entry.key)],
                    default_enabled=entry.default_enabled,
                    toggleable=entry.toggleable,
                )
                for entry in section.entries
            ],
        )
        for section in inventory.sections()
    ]
    return CapabilityInventoryResponse(
        practice_area_key=practice_area_key,
        unit_label=unit_label,
        sections=sections,
    )


@router.get("/{project_id}/capabilities", response_model=CapabilityInventoryResponse)
async def get_matter_capabilities(
    project_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> CapabilityInventoryResponse:
    """The matter's capability inventory + the lawyer's resolved on/off state (ADR-F054).

    Owner-scoped (404 on miss / cross-user / archived). An unfiled matter returns only
    the MCP placeholder section.
    """
    project = await _load_visible_project(db, project_id, user.id)
    inventory, area_key, unit_label = await _resolve_inventory(db, request, project)
    toggles = await _load_toggles(db, project.id)
    return _to_response(inventory, toggles, practice_area_key=area_key, unit_label=unit_label)


@router.patch("/{project_id}/capabilities", response_model=CapabilityInventoryResponse)
async def update_matter_capabilities(
    project_id: uuid.UUID,
    payload: CapabilityOverridesUpdate,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> CapabilityInventoryResponse:
    """Set per-matter capability toggles (human-authenticated; ADR-F054).

    Each toggle must name an AVAILABLE, toggleable capability of this matter's area —
    a toggle for an unknown / non-toggleable (MCP) / stale (kind, key) is rejected
    (422) so a forged or drifted id can never be stored. Owner-scoped (404). Audited
    with counts/kinds/keys only.
    """
    project = await _load_visible_project(db, project_id, user.id)
    inventory, area_key, unit_label = await _resolve_inventory(db, request, project)

    # Reject any toggle not in the matter's available, toggleable set (422). Validate
    # ALL before writing any, so a partial set never lands.
    for toggle in payload.toggles:
        if not inventory.is_toggleable(toggle.kind, toggle.key):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Capability {toggle.kind}:{toggle.key} is not an available, "
                    "toggleable capability for this matter."
                ),
            )

    now = datetime.now(UTC)
    for toggle in payload.toggles:
        stmt = (
            pg_insert(MatterCapabilityToggle)
            .values(
                project_id=project.id,
                capability_kind=toggle.kind,
                capability_key=toggle.key,
                enabled=toggle.enabled,
                set_by=user.id,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="pk_matter_capability_toggles",
                set_={"enabled": toggle.enabled, "set_by": user.id, "updated_at": now},
            )
        )
        await db.execute(stmt)

    # Counts/kinds/keys only — capability keys are identifiers, never user content.
    await audit_action(
        db,
        user_id=user.id,
        action="matter.capability_toggle",
        resource_type="project",
        resource_id=str(project.id),
        project=project,
        request=request,
        details={
            "toggle_count": len(payload.toggles),
            "toggles": [
                {"kind": t.kind, "key": t.key, "enabled": t.enabled} for t in payload.toggles
            ],
        },
    )
    await db.commit()

    toggles = await _load_toggles(db, project.id)
    return _to_response(inventory, toggles, practice_area_key=area_key, unit_label=unit_label)
