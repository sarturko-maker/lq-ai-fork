"""Pydantic schema for a shipped agent-profile manifest (ADR-F067 D4, B-7a).

A **profile manifest** is a versioned, in-repo, declarative bundle describing
what a practice area IS by default — its doctrine, unit vocabulary, tier/budget
defaults, module bindings, sub-agent roster, and HITL defaults. Manifests live
under the repo-root ``profiles/`` directory (``profiles/<name>/profile.yaml`` +
a sibling ``doctrine.md``) and are loaded read-only at API boot, like the skills
catalog. An admin materialises one onto a real area via
``POST /api/v1/profiles/{name}/apply`` (copy-not-link).

This module is the *structural* schema only. Cross-registry validation (skill
keys resolve, tool-group keys are real and bindable, the roster passes
``build_area_subagents``, HITL names are eligible) happens in
:mod:`app.profiles.loader`, where the live registries are available — and, like
the gateway config loader, it is **fail-loud**: a malformed manifest refuses the
boot rather than silently degrading (ADR-F067 D4 — "refuse unknown kind/key at
LOAD, never at apply-time surprise").
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Profile shape. ``area`` ships a fully-configured practice area (Commercial,
# Privacy); ``blank`` creates a bare area the admin configures themselves — its
# identity (key/name/unit) comes from the apply request, not the manifest.
ProfileKind = Literal["area", "blank"]

# The closed unit-of-work vocabulary for SHIPPED manifests (B-7a; the
# maintainer's TYPES refinement). Deliberately manifest-layer only: the DB
# ``practice_areas.unit_label`` column and ``PracticeAreaCreate`` stay free Text,
# so admins can still label bespoke areas any noun and the live ``m-and-a``
# "Deal" is untouched (ADR-F067 D4, B-7a addendum). Enforcing it in the DB is a
# separate, migration-bearing follow-up.
UnitLabel = Literal["Matter", "Project", "Programme", "Investigation"]

# Same slug shape as ``PracticeAreaCreate.key`` (schemas/practice_areas.py) — a
# profile ``name`` is also its folder name, and ``area_key`` names a real area.
SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$"


class ProfileBindings(BaseModel):
    """The module keys a profile binds to its area (by kind + key).

    B-7a scope is skills + tool groups — the two shipped kinds that bind by a
    static, registry-resolvable key. Playbooks and knowledge are deliberately
    out of scope: no shipped profile binds either, and both reference DB **ids**
    (not static keys), so they cannot live in an in-repo manifest without a
    lookup. The schema can grow those fields when a shipped profile needs them.
    """

    model_config = ConfigDict(extra="forbid")

    skills: list[str] = Field(default_factory=list)
    tool_groups: list[str] = Field(default_factory=list)


class ProfileManifest(BaseModel):
    """One ``profile.yaml`` (doctrine is injected separately from ``doctrine.md``)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=SLUG_PATTERN)
    kind: ProfileKind
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)

    # --- area-only fields (required iff kind == "area", forbidden iff "blank") ---
    area_key: str | None = Field(default=None, pattern=SLUG_PATTERN)
    unit_label: UnitLabel | None = None
    default_tier_floor: int | None = Field(default=None, ge=1, le=5)
    default_budget_profile: Literal["economy", "balanced", "generous"] | None = None
    bindings: ProfileBindings | None = None
    #: The sub-agent roster (``{"subagents": [...]}``) — validated structurally
    #: here and cross-checked against the bound skill set by the loader via
    #: ``build_area_subagents`` (ADR-F010 model-key ban, ADR-F017 skills-subset).
    agent_config: dict[str, Any] = Field(default_factory=dict)
    #: HITL defaults (``{tool_name: True}``) written into ``practice_areas.hitl_policy``.
    hitl: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _kind_field_coupling(self) -> ProfileManifest:
        """An ``area`` profile needs its area block; a ``blank`` one forbids it."""
        if self.kind == "area":
            missing = [
                f for f in ("area_key", "unit_label", "bindings") if getattr(self, f) is None
            ]
            if missing:
                raise ValueError(
                    f"kind='area' profile is missing required field(s): {sorted(missing)}"
                )
        else:  # blank — identity + config come from the apply request, not the manifest
            forbidden = [
                f
                for f in (
                    "area_key",
                    "unit_label",
                    "default_tier_floor",
                    "default_budget_profile",
                    "bindings",
                )
                if getattr(self, f) is not None
            ]
            if self.agent_config:
                forbidden.append("agent_config")
            if self.hitl:
                forbidden.append("hitl")
            if forbidden:
                raise ValueError(
                    f"kind='blank' profile must not set area field(s): {sorted(forbidden)}"
                )
        return self


__all__ = ["SLUG_PATTERN", "ProfileBindings", "ProfileKind", "ProfileManifest", "UnitLabel"]
