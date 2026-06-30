"""Pydantic schemas for the capability panel — per-matter capability toggles (ADR-F054).

Wire shapes for ``GET``/``PUT /matters/{project_id}/capabilities``: the read groups the
area's available capabilities (Playbooks / Skills / Tools / MCP placeholder) with each
one's resolved ``enabled`` state; the write is the lawyer's sparse set of on/off toggles.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CapabilityEntryRead(BaseModel):
    """One capability the panel shows — availability + the resolved enabled state."""

    capability_kind: str
    capability_key: str
    label: str
    description: str | None
    available: bool
    enabled: bool
    default_enabled: bool
    toggleable: bool


class CapabilitySectionRead(BaseModel):
    """A kind-grouped section (Playbooks / Skills / Tools / MCP), in panel order."""

    kind: str
    label: str
    entries: list[CapabilityEntryRead]


class CapabilityInventoryResponse(BaseModel):
    """The matter's full capability inventory (GET response / PUT echo)."""

    practice_area_key: str | None
    unit_label: str
    sections: list[CapabilitySectionRead]


class CapabilityToggleInput(BaseModel):
    """One on/off toggle the lawyer sets. ``extra='forbid'`` rejects stray fields."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["skill", "tool", "playbook"]
    key: str = Field(min_length=1, max_length=200)
    enabled: bool


class CapabilityOverridesUpdate(BaseModel):
    """The PUT body — a bounded set of toggles. Validated at the boundary; the handler
    additionally rejects any (kind, key) not in the matter's AVAILABLE set (422)."""

    model_config = ConfigDict(extra="forbid")

    toggles: list[CapabilityToggleInput] = Field(default_factory=list, max_length=200)
