"""Wire shapes for the profile-apply API (ADR-F067 D4, B-7a).

Distinct from :mod:`app.profiles.schema` (the on-disk manifest): these are the
JSON shapes the admin wizard (B-7b) reads/writes over ``/api/v1/profiles``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.profiles.schema import SLUG_PATTERN  # single source (== PracticeAreaCreate.key shape)


class ProfileSummary(BaseModel):
    """One profile in the wizard picker (GET /profiles)."""

    name: str
    kind: Literal["area", "blank"]
    display_name: str
    description: str
    area_key: str | None
    unit_label: str | None
    skill_count: int
    tool_group_count: int
    subagent_count: int


class ProfileListResponse(BaseModel):
    profiles: list[ProfileSummary]


class ProfileDetail(ProfileSummary):
    """A profile's full manifest for the wizard review screen (GET /profiles/{name})."""

    doctrine: str | None
    default_tier_floor: int | None
    default_budget_profile: str | None
    skills: list[str]
    tool_groups: list[str]
    agent_config: dict[str, Any]
    hitl: dict[str, bool]


class ProfileApplyRequest(BaseModel):
    """Body for POST /profiles/{name}/apply.

    For an ``area`` profile the identity (key/name/unit) comes from the manifest
    and these fields must be OMITTED (422 if set). For the ``blank`` profile they
    are REQUIRED — the admin names the new area.
    """

    model_config = ConfigDict(extra="forbid")

    target_key: str | None = Field(default=None, pattern=SLUG_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit_label: str | None = Field(default=None, min_length=1, max_length=200)


class ProfileApplyResult(BaseModel):
    """What apply materialised — counts/keys only (audit-contract shape)."""

    profile_name: str
    target_key: str
    area_created: bool
    #: Newly-inserted Library keys, by kind ({"skill": [...], "tool": [...]}).
    adopted: dict[str, list[str]]
    #: Newly-written area bindings, by kind ({"skill": n, "tool": n}).
    bindings_written: dict[str, int]
    roster_subagents: int
    hitl_tools: int
    #: Manifest-owned area fields the (authoritative) overwrite changed on an
    #: existing area — field NAMES only, never values (ADR-F067 D4 / B-7a Q2).
    changed_fields: list[str]


__all__ = [
    "ProfileApplyRequest",
    "ProfileApplyResult",
    "ProfileDetail",
    "ProfileListResponse",
    "ProfileSummary",
]
