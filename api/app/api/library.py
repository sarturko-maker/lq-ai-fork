"""Member-readable Org Library — STORE-2 D-B (ADR-F065).

Transparency is load-bearing (CLAUDE.md): "every prompt, skill, agent instruction
and tool grant must be readable in the UI or the source." Mirrors the house
dual-exposure precedent for tier policy (``GET /api/v1/inference/tier-config``,
``app.api.inference.get_tier_config`` — ``ActiveUser``, while the admin write
surface stays fenced at ``PATCH /admin/tier-policy``): the Org Library's WRITE
surface (``POST``/``DELETE /admin/library``) stays ``AdminUser``-gated
(``app.api.admin``); this module's single GET is the member-readable read model
over the same ``org_library_entries`` table, so any active user can see what
their firm's agents are actually running on — not just an admin.

Returns ONLY adopted entries, each joined to its catalog for display metadata
(reusing the exact label/description/provenance derivations
``app.api.admin._deployment_inventory`` uses, so the two surfaces cannot drift).
A dangling entry (adopted, then the underlying skill/playbook left the catalog)
returns ``label=None`` — the web renders the key honestly rather than guessing.

``adopted_by`` is deliberately NOT on the wire: this is a member-visible surface
and carries no cross-user identifiers (who adopted what is admin/audit-log
territory, not something every member needs to see).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.capabilities import KIND_PLAYBOOK, KIND_SKILL, KIND_TOOL, TOOL_GROUP_REGISTRY
from app.api.admin import playbook_display_label
from app.api.dependencies import ActiveUser
from app.db.session import get_db
from app.models.playbook import Playbook as PlaybookORM
from app.models.practice_area import OrgLibraryEntry
from app.skills.registry import MutableSkillRegistry, SkillRegistry

router = APIRouter(prefix="/library", tags=["library"])

# Canonical kind order for the response — mirrors `DeploymentCapabilitiesResponse`'s
# section order (tool, skill, playbook) in `app.api.admin`.
_KIND_ORDER: dict[str, int] = {KIND_TOOL: 0, KIND_SKILL: 1, KIND_PLAYBOOK: 2}


class LibraryEntryRead(BaseModel):
    """One entry the org has adopted into its Library, with display metadata.

    ``label``/``description``/``source``/``author``/``version`` are all ``None``
    when the underlying catalog entry is dangling (adopted, then removed from the
    catalog — a deleted playbook, a renamed/removed skill) — the web renders the
    bare key plus an honest "no longer in the shipped catalog" note rather than
    guessing a label.
    """

    kind: str
    key: str
    label: str | None
    description: str | None
    source: str | None
    author: str | None
    version: str | None
    adopted_at: datetime


class LibraryResponse(BaseModel):
    """``GET /api/v1/library`` response — the org's adopted Library."""

    entries: list[LibraryEntryRead]


def _registry_or_none(request: Request) -> SkillRegistry | None:
    """Current skill-registry snapshot from app state (``None`` if uninstalled).

    Mirrors ``app.api.admin._admin_registry_or_none`` — graceful, so a registry
    outage degrades a skill entry to dangling (``label=None``) rather than 500ing
    the whole Library read.
    """
    holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    return holder.current() if holder is not None else None


async def _live_playbooks_by_id(db: AsyncSession) -> dict[str, PlaybookORM]:
    """Non-deleted playbooks keyed by ``str(id)`` — the Library's playbook key shape."""
    rows = (
        (await db.execute(select(PlaybookORM).where(PlaybookORM.deleted_at.is_(None))))
        .scalars()
        .all()
    )
    return {str(pb.id): pb for pb in rows}


@router.get(
    "",
    response_model=LibraryResponse,
    summary="The org's adopted Library — member-readable (transparency).",
)
async def get_library(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> LibraryResponse:
    """GET /api/v1/library — every capability the org has adopted, for any active user.

    See the module docstring for the transparency rationale and the dangling-entry
    contract. Ordering: kind in canonical order (tool -> skill -> playbook), then
    label (case-insensitive, ``None`` last), then key — stable and legible for a
    card list grouped by kind.
    """
    rows = (await db.execute(select(OrgLibraryEntry))).scalars().all()
    registry = _registry_or_none(request)
    playbooks_by_id = await _live_playbooks_by_id(db)

    entries: list[LibraryEntryRead] = []
    for row in rows:
        kind, key = row.capability_kind, row.capability_key
        label: str | None = None
        description: str | None = None
        source: str | None = None
        author: str | None = None
        version: str | None = None

        if kind == KIND_TOOL:
            tdef = TOOL_GROUP_REGISTRY.get(key)
            if tdef is not None:
                label = tdef.spec.label
                description = tdef.spec.description
                source = "built-in"
        elif kind == KIND_SKILL:
            record = registry.get(key) if registry is not None else None
            if record is not None:
                summary = record.summary()
                label = summary.title or key
                description = summary.description
                source = summary.source
                author = summary.author
                version = summary.version
        else:  # KIND_PLAYBOOK
            pb = playbooks_by_id.get(key)
            if pb is not None:
                label = playbook_display_label(pb)
                description = pb.description or None
                # source stays None: playbooks carry no provenance field today (D-A).

        entries.append(
            LibraryEntryRead(
                kind=kind,
                key=key,
                label=label,
                description=description,
                source=source,
                author=author,
                version=version,
                adopted_at=row.adopted_at,
            )
        )

    entries.sort(
        key=lambda e: (
            _KIND_ORDER.get(e.kind, len(_KIND_ORDER)),
            0 if e.label is not None else 1,
            (e.label or "").lower(),
            e.key,
        )
    )
    return LibraryResponse(entries=entries)


__all__ = ["LibraryEntryRead", "LibraryResponse", "router"]
