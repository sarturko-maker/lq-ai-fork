"""Pydantic schemas for practice areas — F1-S2 (fork, ADR-F002).

Wire shapes for the cockpit's left rail. The list is curated seed data
in S2 (migration 0053); S3 adds the config vocabulary and admin API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BoundPlaybook(BaseModel):
    """One playbook bound to an area — the join summary the admin UI renders
    (SETUP-4b). Deliberately thin: id to link/detach by, name to label the row;
    the full playbook detail lives at the playbooks endpoints."""

    id: uuid.UUID
    name: str


class PracticeAreaRead(BaseModel):
    """ORM-read view of a :class:`~app.models.practice_area.PracticeArea`.

    ``configured`` drives the F002 inert-card semantics in the cockpit:
    unconfigured areas are not enterable (no composer, no rail, no matter
    creation under them). In F1-S3 it is DERIVED from real config (an area
    is configured ⇔ it has a non-empty profile the agent can build from) —
    the stored column is retained but the API reports the derived value.
    ``unit_label`` is the unit-of-work noun the UI renders — data, not code
    (ADR-F004). ``profile_md`` is readable by everyone for the same
    transparency reason as the Organization Profile (PRD §1.3): an agent
    instruction must be readable in the UI or the source (CLAUDE.md).

    ``bound_tool_groups`` (SETUP-4b) is the area's ``practice_area_tool_groups``
    rows in REGISTRY-CANONICAL order — ``TOOL_GROUP_REGISTRY`` insertion order
    filtered to the area's rows, never DB row order (ADR-F062 D4). ``bound_playbooks``
    is the area's ``practice_area_playbooks`` rows joined to their (non-deleted)
    playbook name.
    """

    id: uuid.UUID
    key: str
    name: str
    unit_label: str
    configured: bool
    position: int
    profile_md: str | None
    default_tier_floor: int | None
    agent_config: dict[str, Any]
    bound_skills: list[str]
    bound_tool_groups: list[str]
    bound_playbooks: list[BoundPlaybook]
    created_at: datetime
    updated_at: datetime


class PracticeAreaListResponse(BaseModel):
    """Full curated list, ``position`` order. Unpaginated: the set is a
    bounded handful of operator-curated rows, not user data."""

    practice_areas: list[PracticeAreaRead]


class PracticeAreaConfigUpdate(BaseModel):
    """Admin config write (PATCH). All fields optional — only those present
    are applied (partial update). Validated at the boundary (reject, don't
    sanitize); ``agent_config`` is shape-checked by the area renderer so an
    invalid subagent spec, an unknown top-level key, or a forbidden ``model``
    key (ADR-F010) is rejected as a 400 (ValidationError), never persisted.

    ``name``/``unit_label`` (SETUP-4b) let the admin UI rename an area or
    relabel its unit-of-work noun post-creation; bounds mirror
    :class:`PracticeAreaCreate`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit_label: str | None = Field(default=None, min_length=1, max_length=200)
    profile_md: str | None = Field(default=None, max_length=20_000)
    default_tier_floor: int | None = Field(default=None, ge=1, le=5)
    agent_config: dict[str, Any] | None = None

    @field_validator("name", "unit_label")
    @classmethod
    def _reject_explicit_null(cls, value: str | None) -> str:
        """SETUP-4b review fix 1: an explicit JSON ``null`` matches the ``None``
        arm of the union, skipping ``min_length`` entirely — and both columns are
        NOT NULL, so letting it through crashes the commit with an unhandled
        IntegrityError (500) instead of the canonical 422. Validators don't run
        for UNSET defaults (``validate_default`` is False), so ``None``-as-
        partial-update-sentinel stays intact; only a *provided* null is rejected
        here, at the boundary (reject, don't sanitize)."""
        if value is None:
            raise ValueError("must be a non-empty string when provided (null is not allowed)")
        return value


class PracticeAreaCreate(BaseModel):
    """Create a practice area (admin, SETUP-4a / ADR-F062).

    ``key`` is an anchored slug (lowercase, no leading/trailing hyphen — the wizard
    precedent); it becomes the stable machine identifier and the URL segment. All fields
    validated at the boundary (reject, don't sanitize); ``agent_config`` is shape-checked
    by the area renderer (a forbidden ``model`` key is rejected, ADR-F010), and
    ``tool_groups`` is validated against the code registry in the handler. ``position`` is
    server-derived (auto-append) and ``configured`` is derived from the profile — neither is
    client-settable.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")
    name: str = Field(min_length=1, max_length=200)
    unit_label: str = Field(min_length=1, max_length=200)
    profile_md: str | None = Field(default=None, max_length=20_000)
    default_tier_floor: int | None = Field(default=None, ge=1, le=5)
    agent_config: dict[str, Any] | None = None
    # Items bounded like ToolGroupAttachRequest.group_key (they are echoed in the 404
    # detail; reject an unbounded string at the boundary).
    tool_groups: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=50
    )


class SkillAttachRequest(BaseModel):
    """Attach a filesystem-canonical skill (by name) to an area."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(min_length=1, max_length=200)


class ToolGroupAttachRequest(BaseModel):
    """Attach a tool group (by registry key) to an area's available set — ADR-F062.

    Mirrors :class:`SkillAttachRequest`; the handler validates ``group_key`` against the
    code registry (``TOOL_GROUP_REGISTRY``) — an unknown key is a 404, so no dead row lands.
    """

    model_config = ConfigDict(extra="forbid")

    group_key: str = Field(min_length=1, max_length=200)


class PracticeAreaReorderRequest(BaseModel):
    """``POST /practice-areas/reorder`` body (SETUP-4b, ADR-F062 addendum).

    ``keys`` must be an EXACT permutation of every existing area key (the
    handler compares as sets AND lengths — a partial list, an unknown key, or
    a duplicate is rejected as 422; reject, don't sanitize — a mismatch means a
    stale client, so the UI just refetches and retries). Item bounds mirror
    :class:`ToolGroupAttachRequest`'s ``group_key``.
    """

    model_config = ConfigDict(extra="forbid")

    keys: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=200
    )


class PlaybookAttachRequest(BaseModel):
    """Attach a playbook (by id) to an area's available set — ADR-F054.

    Mirrors :class:`SkillAttachRequest` but ``playbook_id`` is a real id (playbooks
    are SQL rows). The handler validates the playbook exists and is not soft-deleted.
    """

    model_config = ConfigDict(extra="forbid")

    playbook_id: uuid.UUID
