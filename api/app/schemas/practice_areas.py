"""Pydantic schemas for practice areas — F1-S2 (fork, ADR-F002).

Wire shapes for the cockpit's left rail. The list is curated seed data
in S2 (migration 0053); S3 adds the config vocabulary and admin API.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    invalid subagent spec (or a forbidden ``model`` key, ADR-F010) is a 422.
    """

    model_config = ConfigDict(extra="forbid")

    profile_md: str | None = Field(default=None, max_length=20_000)
    default_tier_floor: int | None = Field(default=None, ge=1, le=5)
    agent_config: dict[str, Any] | None = None


class SkillAttachRequest(BaseModel):
    """Attach a filesystem-canonical skill (by name) to an area."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(min_length=1, max_length=200)
