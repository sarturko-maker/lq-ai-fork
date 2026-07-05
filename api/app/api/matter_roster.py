"""Matter authorship-roster endpoints — the human-authenticated who-is-who (ADR-F048).

The roster is **auto-write-then-correct** (ADR-F042): the agent records who is who as it
learns (``record_matter_participant`` — ``trust='inferred'``), and the supervising lawyer
**owns it after** — directly adding, editing or removing a participant here. A human
write is structurally authoritative: it sets ``trust='confirmed'`` with ``user_id`` from
the authenticated session (never agent/model input), and the agent's auto-curation may
never override a confirmed side/role (B2 — an agent-asserted identity is forgeable by
document/prompt injection).

**Per-user isolation.** Every endpoint loads the matter via the projects
``_load_visible_project`` rule: owner-scoped, archived-excluded, **404** on miss /
cross-user / archived (never 403 — no existence leak). The ``id + project`` lookup also
404s a cross-matter entry id.

Audited (``matter_roster.*``) with counts/IDs only — never the participant's name, email
or role text (audit contract; identity is sensitive). The read is folded into the
composite ``GET /matters/{id}/memory`` (an active ``roster`` array) so the cockpit panel
loads everything in one fetch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.matter_roster_tools import live_participants
from app.api.dependencies import MutatingUser
from app.api.projects import _load_visible_project
from app.audit import audit_action
from app.db.session import get_db
from app.errors import NotFound
from app.models.project import MatterParticipant
from app.schemas.matter_memory import (
    MATTER_PARTICIPANT_NAME_MAX_CHARS,
    MATTER_PARTICIPANT_ORG_MAX_CHARS,
    MATTER_PARTICIPANT_ROLE_MAX_CHARS,
    MATTER_PARTICIPANT_SOURCE_MAX_CHARS,
    MatterParticipantSide,
    ParticipantRead,
    clean_alias_list,
)

router = APIRouter(prefix="/matters", tags=["matter-memory"])


class ParticipantCreateRequest(BaseModel):
    """``POST /matters/{project_id}/roster`` body — the lawyer adds a participant.

    ``str_strip_whitespace`` trims first, so a whitespace-only name collapses to "" and
    422s at the boundary (never the DB CHECK as a 500). Reject, don't sanitize.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    display_name: str = Field(min_length=1, max_length=MATTER_PARTICIPANT_NAME_MAX_CHARS)
    side: MatterParticipantSide
    role_label: str | None = Field(default=None, max_length=MATTER_PARTICIPANT_ROLE_MAX_CHARS)
    organization: str | None = Field(default=None, max_length=MATTER_PARTICIPANT_ORG_MAX_CHARS)
    aliases: list[str] | None = None
    source_citation: str | None = Field(
        default=None, max_length=MATTER_PARTICIPANT_SOURCE_MAX_CHARS
    )

    @field_validator("role_label", "organization", "source_citation")
    @classmethod
    def _blank_is_absent(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, value: list[str] | None) -> list[str]:
        return clean_alias_list(value)


class ParticipantUpdateRequest(BaseModel):
    """``PATCH /matters/{project_id}/roster/{entry_id}`` body — a partial edit.

    Every field is optional; only those PRESENT are applied (``model_fields_set``). A
    human edit always (re)confirms the entry (``trust='confirmed'``). ``aliases``, when
    given, REPLACES the alias list (the panel sends the full set).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    display_name: str | None = Field(
        default=None, min_length=1, max_length=MATTER_PARTICIPANT_NAME_MAX_CHARS
    )
    side: MatterParticipantSide | None = None
    role_label: str | None = Field(default=None, max_length=MATTER_PARTICIPANT_ROLE_MAX_CHARS)
    organization: str | None = Field(default=None, max_length=MATTER_PARTICIPANT_ORG_MAX_CHARS)
    aliases: list[str] | None = None
    source_citation: str | None = Field(
        default=None, max_length=MATTER_PARTICIPANT_SOURCE_MAX_CHARS
    )

    @field_validator("role_label", "organization", "source_citation")
    @classmethod
    def _blank_is_absent(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("aliases")
    @classmethod
    def _clean_aliases(cls, value: list[str] | None) -> list[str]:
        return clean_alias_list(value)


class ParticipantRetireResponse(BaseModel):
    """The outcome of a human remove: the entry id + when it left the active roster.

    A removed participant drops off the active roster, so a second remove of the same id
    is a 404 (it reads as absent) — unlike the memory-tier correction/fact retires, which
    are idempotent on a still-present row.
    """

    id: uuid.UUID
    retired_at: datetime


def _to_read(p: MatterParticipant) -> ParticipantRead:
    return ParticipantRead(
        id=p.id,
        display_name=p.display_name,
        aliases=list(p.aliases or []),
        organization=p.organization,
        role_label=p.role_label,
        side=p.side,
        trust=p.trust,
        source_citation=p.source_citation,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _aliases_excluding_name(display_name: str, aliases: list[str]) -> list[str]:
    """Store aliases as the extra match strings minus the display name (it always matches).

    ``clamp=True``: a rename folds the old name into the (already-validated) alias set,
    which can tip a near-cap entry over — clamp rather than 500 (the request validator
    already rejected an over-count *proposal*; this is internal upkeep).
    """
    dn = display_name.strip().casefold()
    return [a for a in clean_alias_list(aliases, clamp=True) if a.strip().casefold() != dn]


async def _load_active_participant(
    db: AsyncSession, project_id: uuid.UUID, entry_id: uuid.UUID
) -> MatterParticipant:
    """Load an ACTIVE participant of THIS matter by id, or 404 (no existence leak).

    The id + project scope blocks a cross-matter id; the caller has already owner-scoped
    the project. A soft-retired row is treated as absent (404) so a remove is final.
    """
    entry = (
        await db.execute(
            select(MatterParticipant).where(
                MatterParticipant.id == entry_id,
                MatterParticipant.project_id == project_id,
                MatterParticipant.superseded_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise NotFound(
            f"Participant {entry_id} not found for this matter.",
            details={"entry_id": str(entry_id)},
        )
    return entry


@router.post(
    "/{project_id}/roster",
    status_code=status.HTTP_201_CREATED,
    response_model=ParticipantRead,
)
async def create_matter_participant(
    project_id: uuid.UUID,
    payload: ParticipantCreateRequest,
    user: MutatingUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> ParticipantRead:
    """Add a participant to a matter's roster (human-authenticated; ADR-F048).

    The matter must be the caller's own active project (404 otherwise). The entry is
    written ``trust='confirmed'`` with ``user_id`` from the session; the agent cannot
    override a confirmed side/role. Audited with counts/IDs only (never the name/role).
    """
    project = await _load_visible_project(db, project_id, user.id)

    entry = MatterParticipant(
        project_id=project.id,
        user_id=user.id,
        display_name=payload.display_name,
        aliases=_aliases_excluding_name(payload.display_name, payload.aliases or []),
        organization=payload.organization,
        role_label=payload.role_label,
        side=payload.side.value,
        trust="confirmed",
        source_citation=payload.source_citation,
        run_id=None,
    )
    db.add(entry)
    await db.flush()
    response = _to_read(entry)

    # Counts/IDs only — never the name/email/role text (audit contract).
    await audit_action(
        db,
        user_id=user.id,
        action="matter_roster.create",
        resource_type="project",
        resource_id=str(project.id),
        project=project,
        request=request,
        details={"entry_id": str(response.id), "side": payload.side.value},
    )
    await db.commit()
    return response


@router.patch("/{project_id}/roster/{entry_id}", response_model=ParticipantRead)
async def update_matter_participant(
    project_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: ParticipantUpdateRequest,
    user: MutatingUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> ParticipantRead:
    """Edit a roster participant (human-authenticated; ADR-F048).

    A partial edit — only the fields PRESENT in the body are applied. Any edit
    (re)confirms the entry (``trust='confirmed'``), so a corrected entry becomes
    lawyer-owned and the agent can no longer override its side/role. Owner-scoped (404);
    the id+project lookup 404s a cross-matter id. Audited with counts/IDs only.
    """
    project = await _load_visible_project(db, project_id, user.id)
    entry = await _load_active_participant(db, project.id, entry_id)

    fields = payload.model_fields_set
    # Apply the aliases REPLACE first (the panel sends the full list), so a simultaneous
    # rename below can still fold the OLD name into the set — if display_name ran first,
    # the replace would clobber that preservation (the panel always sends both fields).
    if "aliases" in fields:
        entry.aliases = _aliases_excluding_name(entry.display_name, payload.aliases or [])
    if "display_name" in fields and payload.display_name is not None:
        # Preserve the old name as an alias so prior edits under it still match.
        entry.aliases = _aliases_excluding_name(
            payload.display_name, [*(entry.aliases or []), entry.display_name]
        )
        entry.display_name = payload.display_name
    if "side" in fields and payload.side is not None:
        entry.side = payload.side.value
    if "role_label" in fields:
        entry.role_label = payload.role_label
    if "organization" in fields:
        entry.organization = payload.organization
    if "source_citation" in fields:
        entry.source_citation = payload.source_citation

    # A human edit (re)confirms the entry — it becomes lawyer-owned (B2).
    entry.trust = "confirmed"
    entry.user_id = user.id
    entry.updated_at = datetime.now(UTC)
    response = _to_read(entry)

    await audit_action(
        db,
        user_id=user.id,
        action="matter_roster.update",
        resource_type="project",
        resource_id=str(project.id),
        project=project,
        request=request,
        details={"entry_id": str(response.id), "side": entry.side},
    )
    await db.commit()
    return response


@router.post("/{project_id}/roster/{entry_id}/retire", response_model=ParticipantRetireResponse)
async def retire_matter_participant(
    project_id: uuid.UUID,
    entry_id: uuid.UUID,
    user: MutatingUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> ParticipantRetireResponse:
    """Remove a participant from the active roster (human-authenticated; ADR-F048).

    Soft-retire: sets ``superseded_at`` so the participant drops off the active roster
    without deleting the row. Owner-scoped (404); the id+project lookup 404s a
    cross-matter id (and an already-retired entry, which reads as absent). Audited with
    IDs only.
    """
    project = await _load_visible_project(db, project_id, user.id)
    entry = await _load_active_participant(db, project.id, entry_id)

    now = datetime.now(UTC)
    entry.superseded_at = now
    entry_id_out = entry.id

    await audit_action(
        db,
        user_id=user.id,
        action="matter_roster.retire",
        resource_type="project",
        resource_id=str(project.id),
        project=project,
        request=request,
        details={"entry_id": str(entry_id_out)},
    )
    await db.commit()
    return ParticipantRetireResponse(id=entry_id_out, retired_at=now)


async def roster_read(db: AsyncSession, project_id: uuid.UUID) -> list[ParticipantRead]:
    """The active roster as read projections — for the composite GET /memory.

    A thin api-layer helper over the agent-layer ``live_participants`` substrate so the
    composite memory read and the write endpoints return the identical shape.
    """
    return [_to_read(p) for p in await live_participants(db, project_id)]
