"""Capability inventory — the single source of truth for the capability panel (ADR-F054).

ONE pure module computes, for a matter's practice area, which capabilities are
AVAILABLE (the area-curated set) and — overlaid with the lawyer's per-matter
``matter_capability_toggles`` — which are ENABLED. It is consumed by BOTH the read
API (``app.api.matter_capabilities``) and the run composition point
(``app.agents.composition``), so what the panel shows is provably what the agent gets.

Three real capability kinds (+ a disabled MCP placeholder):

* **skill** — the area's bound ``practice_area_skills`` (filtered to the registry's
  current set). Off ⇒ not wired (no source, absent from the prompt skill list).
* **tool** — a per-area CODE group map (here). Tools are code-canonical (the
  ``*_TOOL_NAMES`` frozensets are the truth), so availability is a code map, NOT a
  table — a table would force a seed that must byte-match the grants forever. Off ⇒
  the group's tools are not built, so they never enter ``GuardContext.granted`` (R6
  fail-closes). Toggled by GROUP ("Redlining" / "ROPA" / "Assessments"), not by
  individual tool name — lawyer-legible.
* **playbook** — the area's bound ``practice_area_playbooks`` (the firm's preferred
  positions; reuse the DATA, the legacy executor is frozen). Off ⇒ not injected as
  the read-only "Practice Playbook" memory tier.
* **mcp** — a visible-but-disabled placeholder; real MCP wiring is its own
  approval-gated milestone (ADRs 0014/0015).

Every available capability DEFAULTS ON (the MCP placeholder excepted): a matter the
lawyer never touches has no toggle rows and behaves byte-identically to today.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.agents.commercial_tools import COMMERCIAL_AREA_KEY
from app.agents.ropa_tools import PRIVACY_AREA_KEY
from app.models.playbook import Playbook
from app.skills.registry import SkillRegistry

# Capability kinds (the ``capability_kind`` values; also the DB CHECK set for the
# three real kinds — 'mcp' is a UI-only placeholder, never persisted).
KIND_SKILL = "skill"
KIND_TOOL = "tool"
KIND_PLAYBOOK = "playbook"
KIND_MCP = "mcp"


@dataclass(frozen=True)
class ToolGroupSpec:
    """One toggleable TOOL capability — a named group the lawyer flips on/off.

    ``key`` is the stable group identifier the lawyer toggles and composition gates
    on (``if GROUP.key in enabled_tool_groups`` → build/grant that group's tools).
    The underlying grant set stays in the group's ``build_*_tools`` (the ``*_TOOL_NAMES``
    frozensets); this spec carries only what the panel shows.
    """

    key: str
    label: str
    description: str


# The toggleable tool groups, by area key. Tabular review (next milestone) slots in
# as one more entry under COMMERCIAL_AREA_KEY with no schema change.
REDLINING_GROUP = ToolGroupSpec(
    key="redlining",
    label="Redlining",
    description=(
        "Propose and apply tracked-changes redlines on the matter's contracts, and "
        "run negotiation rounds against the counterparty's markup."
    ),
)
ROPA_GROUP = ToolGroupSpec(
    key="ropa",
    label="ROPA register",
    description=(
        "Maintain the Article 30 record of processing — propose and change processing "
        "activities, systems, vendors and transfers."
    ),
)
ASSESSMENT_GROUP = ToolGroupSpec(
    key="assessment",
    label="Assessments",
    description=(
        "Run privacy assessments (PIA / DPIA / LIA / TIA) and the risk register against "
        "the ROPA register."
    ),
)

AREA_TOOL_GROUPS: dict[str, tuple[ToolGroupSpec, ...]] = {
    PRIVACY_AREA_KEY: (ROPA_GROUP, ASSESSMENT_GROUP),
    COMMERCIAL_AREA_KEY: (REDLINING_GROUP,),
}


class _CapabilityToggle(Protocol):
    """Structural type for a ``matter_capability_toggles`` row (or any override)."""

    capability_kind: str
    capability_key: str
    enabled: bool


@dataclass(frozen=True)
class CapabilityEntry:
    """One capability the panel can show — available/default/toggleable flags."""

    kind: str
    key: str
    label: str
    description: str | None
    available: bool
    default_enabled: bool
    toggleable: bool


@dataclass(frozen=True)
class CapabilitySection:
    """A kind-grouped, ordered slice of the inventory (for the panel)."""

    kind: str
    label: str
    entries: tuple[CapabilityEntry, ...]


# The disabled MCP placeholder — visible so the full shape is legible, but not
# available/toggleable until the MCP milestone wires it (ADRs 0014/0015).
MCP_PLACEHOLDER = CapabilityEntry(
    kind=KIND_MCP,
    key="mcp",
    label="MCP servers",
    description="Connect external tool servers (e.g. case-law research). Coming soon.",
    available=False,
    default_enabled=False,
    toggleable=False,
)

# Section order + labels for the panel (maintainer: "playbooks, skills and tools").
_SECTION_ORDER: tuple[tuple[str, str], ...] = (
    (KIND_PLAYBOOK, "Playbooks"),
    (KIND_SKILL, "Skills"),
    (KIND_TOOL, "Tools"),
    (KIND_MCP, "MCP servers"),
)


@dataclass(frozen=True)
class CapabilityInventory:
    """The area's available capabilities + the resolution of the lawyer's toggles."""

    entries: tuple[CapabilityEntry, ...]

    @staticmethod
    def _override(toggles: Iterable[_CapabilityToggle]) -> dict[tuple[str, str], bool]:
        return {(t.capability_kind, t.capability_key): t.enabled for t in toggles}

    def enabled_keys(self, kind: str, toggles: Iterable[_CapabilityToggle]) -> list[str]:
        """Enabled capability keys of ``kind``, in inventory order.

        A capability is enabled when its (kind, key) override says so, else its
        ``default_enabled``. Non-toggleable / unavailable entries (MCP) are never
        enabled. Order is preserved so e.g. the skill list keeps its area order.
        """
        override = self._override(toggles)
        return [
            e.key
            for e in self.entries
            if e.kind == kind
            and e.toggleable
            and e.available
            and override.get((e.kind, e.key), e.default_enabled)
        ]

    def is_toggleable(self, kind: str, key: str) -> bool:
        """True iff (kind, key) is an available, toggleable capability of this area.

        The PATCH boundary uses this to reject a toggle for an unknown / non-toggleable
        (MCP) / stale key — so a forged or drifted id can never be stored.
        """
        return any(
            e.kind == kind and e.key == key and e.toggleable and e.available for e in self.entries
        )

    def enabled_map(self, toggles: Iterable[_CapabilityToggle]) -> dict[tuple[str, str], bool]:
        """Resolved enabled state for EVERY entry (incl. the MCP placeholder → False).

        For the GET response: each entry's ``enabled`` is its override (if toggleable)
        else its ``default_enabled``; an unavailable/non-toggleable entry is False.
        """
        override = self._override(toggles)
        out: dict[tuple[str, str], bool] = {}
        for e in self.entries:
            if e.toggleable and e.available:
                out[(e.kind, e.key)] = override.get((e.kind, e.key), e.default_enabled)
            else:
                out[(e.kind, e.key)] = e.available and e.default_enabled
        return out

    def sections(self) -> list[CapabilitySection]:
        """All four sections in panel order (a section may be empty; MCP always has
        its placeholder)."""
        return [
            CapabilitySection(
                kind=kind,
                label=label,
                entries=tuple(e for e in self.entries if e.kind == kind),
            )
            for kind, label in _SECTION_ORDER
        ]


def build_area_inventory(
    *,
    area_key: str,
    bound_skill_names: Sequence[str],
    registry: SkillRegistry | None,
    area_playbooks: Sequence[Playbook],
) -> CapabilityInventory:
    """Compute the area's available capabilities (pure — no I/O).

    ``bound_skill_names`` are the area's ``practice_area_skills`` rows; a name the
    registry no longer knows is dropped (registry is source of truth — the same drift
    posture as ``render_area_agent``). ``area_playbooks`` are the playbooks bound via
    ``practice_area_playbooks`` (non-deleted). ``area_key`` selects the tool groups
    from :data:`AREA_TOOL_GROUPS` (an unknown area contributes no tool groups).
    """
    entries: list[CapabilityEntry] = []

    # Playbooks — the firm's preferred positions bound to this area.
    for pb in area_playbooks:
        label = f"{pb.name} ({pb.contract_type})" if pb.contract_type else pb.name
        entries.append(
            CapabilityEntry(
                kind=KIND_PLAYBOOK,
                key=str(pb.id),
                label=label,
                description=(pb.description or None),
                available=True,
                default_enabled=True,
                toggleable=True,
            )
        )

    # Skills — area-bound, filtered to the registry's current set (drift drop).
    for name in bound_skill_names:
        record = registry.get(name) if registry is not None else None
        if record is None:
            continue
        summary = record.summary()
        entries.append(
            CapabilityEntry(
                kind=KIND_SKILL,
                key=name,
                label=summary.title or name,
                description=summary.description,
                available=True,
                default_enabled=True,
                toggleable=True,
            )
        )

    # Tools — the area's code-defined groups.
    for group in AREA_TOOL_GROUPS.get(area_key, ()):
        entries.append(
            CapabilityEntry(
                kind=KIND_TOOL,
                key=group.key,
                label=group.label,
                description=group.description,
                available=True,
                default_enabled=True,
                toggleable=True,
            )
        )

    # MCP — the disabled placeholder (always present so the shape is legible).
    entries.append(MCP_PLACEHOLDER)

    return CapabilityInventory(entries=tuple(entries))


def empty_inventory() -> CapabilityInventory:
    """The inventory for a matter with NO practice area (unfiled/legacy): only the
    MCP placeholder. No skills/tools/playbooks — today's substrate-only behaviour."""
    return CapabilityInventory(entries=(MCP_PLACEHOLDER,))
