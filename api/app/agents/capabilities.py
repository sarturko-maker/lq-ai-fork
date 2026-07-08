"""Capability inventory — the single source of truth for the capability panel (ADR-F054).

ONE pure module computes, for a matter's practice area, which capabilities are
AVAILABLE (the area-curated set) and — overlaid with the lawyer's per-matter
``matter_capability_toggles`` — which are ENABLED. It is consumed by BOTH the read
API (``app.api.matter_capabilities``) and the run composition point
(``app.agents.composition``), so what the panel shows is provably what the agent gets.

Three real capability kinds (+ a disabled MCP placeholder):

* **skill** — the area's bound ``practice_area_skills`` (filtered to the registry's
  current set). Off ⇒ not wired (no source, absent from the prompt skill list).
* **tool** — a named tool GROUP. Availability is DATA (the ``practice_area_tool_groups``
  rows, resolved against :data:`TOOL_GROUP_REGISTRY`, SETUP-4a / ADR-F062 — so an
  admin-created area can be granted domain tools); what a group NAME resolves to (its
  grant set, builder, ledger, doctrine) stays CODE — the ``*_TOOL_NAMES`` frozensets are
  the truth, never a table (a grant table would force a seed that must byte-match the
  grants forever; F054-D1 rejected-option-2 is superseded only for *availability*). Off ⇒
  the group's tools are not built, so they never enter ``GuardContext.granted`` (R6
  fail-closes). Toggled by GROUP ("Redlining" / "ROPA" / "Assessments"), not by
  individual tool name — lawyer-legible.
* **playbook** — the area's bound ``practice_area_playbooks`` (the company's preferred
  positions; reuse the DATA, the legacy executor is frozen). Off ⇒ not injected as
  the read-only "Practice Playbook" memory tier.
* **mcp** — a visible-but-disabled placeholder; real MCP wiring is its own
  approval-gated milestone (ADRs 0014/0015).

Every available capability DEFAULTS ON (the MCP placeholder excepted): a matter the
lawyer never touches has no toggle rows and behaves byte-identically to today.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.assessment_tools import build_assessment_tools
from app.agents.budget import BudgetEnvelope
from app.agents.commercial_tools import build_commercial_tools
from app.agents.deal_changes import DealChangeLedger
from app.agents.live_changes import ChangeLedger
from app.agents.redline_service import RedlineService
from app.agents.ropa_changes import RopaChangeLedger
from app.agents.ropa_tools import build_ropa_tools
from app.agents.tabular_tool import build_tabular_tools
from app.agents.tools import MatterBinding
from app.models.playbook import Playbook
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

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


# The toggleable tool groups, by area key. New groups slot in as one more entry under
# their area key with no schema change (tool availability is a code map, not a table).
REDLINING_GROUP = ToolGroupSpec(
    key="redlining",
    label="Redlining",
    description=(
        "Propose and apply tracked-changes redlines on the matter's contracts, and "
        "run negotiation rounds against the counterparty's markup."
    ),
)
# ADR-F055 (F2 Tabular T1): the agentic "grids" tool group — cross-document tabular review.
TABULAR_GROUP = ToolGroupSpec(
    key="tabular",
    label="Grids",
    description=(
        "Build and maintain cross-document review grids (a column per question, a row per "
        "document) over the matter's contracts, and update them conversationally."
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

# --- tool-group registry (ADR-F062, SETUP-4a) --------------------------------
#
# The registry maps a tool-group NAME to its CODE: the panel spec, the builder adapter
# (uniform ctx → the group's real builder kwargs), and an optional ledger factory. It is
# the single source of truth for WHAT a group name resolves to; the DATA
# (``practice_area_tool_groups`` rows) says only WHICH groups an area offers. Two
# invariants ride the registry:
#   * A row naming a group ABSENT here is dropped (fail-closed to absence — never a
#     grant), so no stale/forged row can mint tools it never had (D3).
#   * The dict INSERTION ORDER is the canonical group order (redlining → tabular → ropa →
#     assessment). Both ``build_area_inventory`` and the composition loop iterate the
#     registry filtered by an area's rows — so ordering is code-canonical and can never
#     drift from a seed's row order (D4). This order within each area reproduces today's
#     build sequence exactly (the parity gate depends on it).


@dataclass(frozen=True)
class GroupBuildContext:
    """Run-invariant inputs every tool-group builder adapter needs.

    Frozen; carries the uniform surface each adapter maps onto its concrete builder's
    real kwargs (tabular takes ``envelope.fan_out_quota``; redlining calls
    ``redline_service_provider()``). ``binding`` is non-optional — the composition loop
    only builds domain groups for a matter-bound run.
    """

    session_factory: async_sessionmaker[AsyncSession]
    run_id: uuid.UUID
    binding: MatterBinding
    envelope: BudgetEnvelope
    redline_service_provider: Callable[[], RedlineService]


@dataclass(frozen=True)
class ToolGroupDef:
    """One tool group's CODE: its panel spec, its builder adapter, its optional ledger.

    ``build`` maps the uniform :class:`GroupBuildContext` (plus the run-scoped ledger the
    loop created from ``ledger_factory``, or ``None``) onto the group's concrete
    ``build_*_tools`` call and returns its tools. ``ledger_factory`` is the run-scoped
    live-change ledger constructor for the groups that stream signals (redlining →
    ``DealChangeLedger``, ropa → ``RopaChangeLedger``); ``None`` for groups that don't.
    """

    spec: ToolGroupSpec
    build: Callable[[GroupBuildContext, ChangeLedger | None], list[Callable[..., Any]]]
    ledger_factory: Callable[[], ChangeLedger] | None = None


def _build_redlining(
    ctx: GroupBuildContext, ledger: ChangeLedger | None
) -> list[Callable[..., Any]]:
    # C4/C5b-3 (ADR-F031/F032/F035): the surgical-redline + negotiation tools. The Adeu
    # engine is built per-run from the injected provider (no startup singleton). The
    # deal-change ledger (created by the loop from ``ledger_factory``) drives the inline
    # verdict chips. The cast is safe: the loop always passes a ``DealChangeLedger`` here.
    return build_commercial_tools(
        ctx.session_factory,
        run_id=ctx.run_id,
        binding=ctx.binding,
        redline_service=ctx.redline_service_provider(),
        change_ledger=cast("DealChangeLedger | None", ledger),
    )


def _build_tabular(ctx: GroupBuildContext, ledger: ChangeLedger | None) -> list[Callable[..., Any]]:
    # ADR-F055 (F2 Tabular T1): the agentic "grids" tools. ``fan_out_quota`` sizes the
    # fan-out↔retrieval crossover off the run's budget envelope. No ledger (live cell-fill
    # is T5).
    return build_tabular_tools(
        ctx.session_factory,
        run_id=ctx.run_id,
        binding=ctx.binding,
        fan_out_quota=ctx.envelope.fan_out_quota,
    )


def _build_ropa(ctx: GroupBuildContext, ledger: ChangeLedger | None) -> list[Callable[..., Any]]:
    # PRIV-2/9b (ADR-F018/F024): the ROPA domain tools. The ropa-change ledger (created by
    # the loop) drives the register-row wash. The cast is safe: the loop always passes a
    # ``RopaChangeLedger`` here.
    return build_ropa_tools(
        ctx.session_factory,
        run_id=ctx.run_id,
        binding=ctx.binding,
        change_ledger=cast("RopaChangeLedger | None", ledger),
    )


def _build_assessment(
    ctx: GroupBuildContext, ledger: ChangeLedger | None
) -> list[Callable[..., Any]]:
    # PRIV-A2 (ADR-F018/F027): the privacy-assessment tools. No ledger (the read UI is A3).
    return build_assessment_tools(ctx.session_factory, run_id=ctx.run_id, binding=ctx.binding)


# Insertion order IS the canonical group order (see the note above). ``DealChangeLedger`` /
# ``RopaChangeLedger`` are their own no-arg constructors (satisfy
# ``Callable[[], ChangeLedger]`` structurally).
TOOL_GROUP_REGISTRY: dict[str, ToolGroupDef] = {
    REDLINING_GROUP.key: ToolGroupDef(
        spec=REDLINING_GROUP, build=_build_redlining, ledger_factory=DealChangeLedger
    ),
    TABULAR_GROUP.key: ToolGroupDef(spec=TABULAR_GROUP, build=_build_tabular),
    ROPA_GROUP.key: ToolGroupDef(
        spec=ROPA_GROUP, build=_build_ropa, ledger_factory=RopaChangeLedger
    ),
    ASSESSMENT_GROUP.key: ToolGroupDef(spec=ASSESSMENT_GROUP, build=_build_assessment),
}


# --- recommended Library sets (STORE-2 D-C) ----------------------------------
#
# The Store page's "Recommended for {area}" rail needs a runtime source for "what does
# LQ ship bound to each area by default" — no such constant existed before STORE-2 (the
# shipped defaults live only as migration literals, spread across six files because each
# later craft slice added one more skill by hand-rolled SQL rather than editing a shared
# map). This constant is the drift-guarded transcription of that union — content MUST
# match the seed migrations exactly (a guard test in ``tests/agents/test_capabilities.py``
# pins every referenced tool key against ``TOOL_GROUP_REGISTRY`` and every skill name
# against the real ``skills/`` corpus, so a renamed skill breaks CI instead of silently
# dropping a recommendation). It is read-only display data for the Store page — it does
# NOT feed ``build_area_inventory`` or any resolution chokepoint.
#
# Provenance (area key -> kind -> tuple of keys, insertion order canonical):
#   * skills: ``0056_default_area_skill_bindings.py`` (``_DEFAULT_BINDINGS``, the initial
#     per-area seed) plus the later one-off craft-skill bindings:
#     ``0067_commercial_surgical_redline_skill.py`` (surgical-redline, commercial),
#     ``0069_matter_memory_skill_binding.py`` (matter-memory, every standard area),
#     ``0072_commercial_negotiation_review_skill.py`` (negotiation-review, commercial),
#     ``0073_commercial_roster_and_reconciliation.py`` (deal-review, commercial),
#     ``0083_bind_tabular_review_skill.py`` (tabular-review, commercial).
#   * tools: ``0086_tool_group_registry_deployment_toggles.py`` (``_SEED_TOOL_GROUPS``).
#   * playbooks: no seed migration binds any playbook to any area by default (verified —
#     no ``practice_area_playbooks`` INSERT exists in any migration), so no area has a
#     recommended playbook set today.
RECOMMENDED_LIBRARY_SETS: dict[str, dict[str, tuple[str, ...]]] = {
    "commercial": {
        KIND_TOOL: ("redlining", "tabular"),
        KIND_SKILL: (
            "msa-review-commercial-purchase",
            "msa-review-saas",
            "contract-qa",
            "nda-review",
            "surgical-redline",
            "matter-memory",
            "negotiation-review",
            "deal-review",
            "tabular-review",
        ),
    },
    "privacy": {
        KIND_TOOL: ("ropa", "assessment"),
        KIND_SKILL: (
            "dpa-checklist-review",
            "vendor-privacy-policy-first-pass",
            "contract-qa",
            "matter-memory",
        ),
    },
    "m-and-a": {
        KIND_SKILL: (
            "nda-review",
            "contract-qa",
            "contract-snapshot",
            "matter-memory",
        ),
    },
    "disputes": {
        KIND_SKILL: (
            "contract-qa",
            "action-items-from-client-alert",
            "matter-memory",
        ),
    },
    "employment": {
        KIND_SKILL: (
            "contract-qa",
            "nda-review",
            "action-items-from-client-alert",
            "matter-memory",
        ),
    },
}


def build_area_tool_groups(
    ctx: GroupBuildContext,
    group_keys: Iterable[str],
) -> tuple[list[Callable[..., Any]], ChangeLedger | None]:
    """Build the ENABLED tool groups for one run, in canonical REGISTRY order (ADR-F062).

    ``group_keys`` is the run's enabled tool-group set — the area's
    ``practice_area_tool_groups`` rows ∩ registry ∩ per-matter/Level-0 toggles, already
    resolved by :func:`build_area_inventory`. Iterating the REGISTRY (not the input) makes
    the order code-canonical and deterministic (D4). This is the R6 grant seam for tool
    groups; it is fail-closed by construction:

    * A key not in the registry cannot build anything (there is nothing to build from) — it
      is skipped with a structured warning (counts/keys only, never values). In production
      the input is ALREADY registry-filtered by :func:`build_area_inventory` (which emits
      the D3(c) drift warning at the point a real DB row is dropped), so this check is
      defense-in-depth for any direct caller. Absence at the row, registry, or toggle
      level ⇒ the group's tools never enter ``tools`` and never enter any
      ``GuardContext.granted`` (D3).
    * The run keeps the FIRST non-None ledger as its live-change ledger (D5). If DATA ever
      attaches two ledger-bearing groups to one area, BOTH groups' tools are still built,
      but a structured warning records that only the first streams live changes (honest,
      non-breaking; real multi-ledger is future work).
    """
    wanted = set(group_keys)
    unknown = sorted(k for k in wanted if k not in TOOL_GROUP_REGISTRY)
    if unknown:
        logger.warning(
            "tool-group keys not in registry; skipped (no grant)",
            extra={
                "event": "tool_group_unknown_skipped",
                "count": len(unknown),
                "keys": unknown,
            },
        )
    tools: list[Callable[..., Any]] = []
    change_ledger: ChangeLedger | None = None
    ledger_source: str | None = None
    for group_key, tdef in TOOL_GROUP_REGISTRY.items():
        if group_key not in wanted:
            continue
        ledger = tdef.ledger_factory() if tdef.ledger_factory is not None else None
        tools.extend(tdef.build(ctx, ledger))
        if ledger is not None:
            if change_ledger is None:
                change_ledger, ledger_source = ledger, group_key
            else:
                logger.warning(
                    "multiple ledger-bearing tool groups on one area; only the first "
                    "streams live changes",
                    extra={
                        "event": "tool_group_multi_ledger",
                        "kept": ledger_source,
                        "ignored": group_key,
                    },
                )
    return tools, change_ledger


class _CapabilityToggle(Protocol):
    """Structural type for a ``matter_capability_toggles`` row (or any override)."""

    capability_kind: str
    capability_key: str
    enabled: bool


class _LibraryEntry(Protocol):
    """Structural type for an ``org_library_entries`` row (ADR-F065).

    A capability the org adopted. Deliberately has no ``enabled`` field — membership IS
    the state (adopt-in), unlike the disable-only toggle it replaced."""

    capability_kind: str
    capability_key: str


class _OrgSkillSnapshot(Protocol):
    """Structural type for an approved ``org_skill_versions`` snapshot (ADR-F067 D2/D3).

    Only the fields the availability chokepoint needs to build a panel entry — the slug
    (the capability key) plus the display ``title`` / ``description`` helper properties
    the ORM row exposes over its stored frontmatter. The served bytes (the SKILL.md
    body + provenance banner) are resolved separately, at the ``build_area_skill_wiring``
    seam; this protocol carries nothing model-facing."""

    slug: str

    @property
    def title(self) -> str | None: ...

    @property
    def description(self) -> str | None: ...


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
    bound_skill_names: Sequence[str],
    registry: SkillRegistry | None,
    area_playbooks: Sequence[Playbook],
    tool_group_keys: Sequence[str],
    library_entries: Iterable[_LibraryEntry],
    org_skill_snapshots: Mapping[str, _OrgSkillSnapshot] | None = None,
) -> CapabilityInventory:
    """Compute the area's available capabilities (pure — no I/O). ADR-F054 + ADR-F065 + ADR-F067.

    ``bound_skill_names`` are the area's ``practice_area_skills`` rows; a name the
    registry no longer knows is dropped (registry is source of truth — the same drift
    posture as ``render_area_agent``). ``area_playbooks`` are the playbooks bound via
    ``practice_area_playbooks`` (non-deleted). ``tool_group_keys`` are the area's
    ``practice_area_tool_groups`` rows (SETUP-4a): tool availability is DATA, resolved
    against :data:`TOOL_GROUP_REGISTRY` in canonical registry order. A row naming a group
    absent from the registry is dropped HERE, at the availability chokepoint, with a
    structured warning (counts/keys only) — fail-closed to absence, so no dead row mints a
    grant (D3(c); the grant-seam loop keeps a defense-in-depth check of its own). This
    registry-drift drop is independent of adoption and fires regardless.

    ``library_entries`` are the org's ``org_library_entries`` rows — the adopt-in Org
    Library (ADR-F065 D3), REQUIRED, no default. A binding (skill / tool group / playbook)
    becomes AVAILABLE only if its ``(kind, key)`` is ADOPTED into the Library — absence is
    the single off-state ("not in your Library"): the capability never becomes an entry, so
    the panel never shows it, composition never builds it, skills never wire, and the
    playbook tier never renders (one chokepoint for all four). Under this adopt-in polarity
    a call site that forgot the kwarg would fail CLOSED (nothing adopted ⇒ nothing
    available), but the kwarg is kept REQUIRED anyway so every call site is explicit —
    there is no production site that legitimately passes ``()``.

    ``org_skill_snapshots`` are the org's APPROVED org-authored skill snapshots
    (``org_skill_versions`` rows with ``state='approved'``), keyed by slug — the D2/D3
    harness output (ADR-F067). Unlike ``library_entries`` this kwarg is OPTIONAL and
    defaults to ``{}``: it can only ADD a skill an org authored + adopted + bound, never
    open anything, so forgetting it fails CLOSED (org skills simply drop; nothing shipped
    is affected). A bound+adopted skill resolves as an org snapshot ONLY when the
    filesystem registry does NOT know its slug — the no-shadowing posture (D2): if BOTH
    know the name the registry (shipped) wins and the org version is ignored with a
    structured ``org_skill_shadowed_by_shipped`` warning (counts/keys only). A
    bound+adopted skill the registry AND the snapshots both fail to resolve is dropped
    fail-closed with a structured ``skill_unresolved_skipped`` warning — the F067 D3.8
    revoke signal (an approved snapshot that was revoked / superseded is simply absent
    from the map, so a still-bound revoked skill lands here). That warning also fires for
    plain registry drift, which was silently dropped before this slice.
    """
    # ADR-F065: the set of (kind, key) the org ADOPTED into its Library. A binding resolves
    # only if it is a member — adopt-in, the inverse of the old disable-out toggle.
    adopted = {(e.capability_kind, e.capability_key) for e in library_entries}
    # ADR-F067: the approved org-authored snapshots, keyed by slug. None ≡ {} — fail-closed
    # (forgetting it only drops org skills; see the docstring).
    snapshots = org_skill_snapshots or {}

    entries: list[CapabilityEntry] = []

    # Playbooks — the company's preferred positions bound to this area (adopted ones only).
    for pb in area_playbooks:
        if (KIND_PLAYBOOK, str(pb.id)) not in adopted:
            continue
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

    # Skills — area-bound, adopted-into-Library, resolved against the filesystem registry
    # FIRST (shipped is source of truth), then the approved org snapshots (ADR-F067).
    # Adoption narrows first; a resolved name still drops if it matches neither source.
    shadowed_skills: list[str] = []
    unresolved_skills: list[str] = []
    for name in bound_skill_names:
        if (KIND_SKILL, name) not in adopted:
            continue
        # Skills resolve ONLY when the registry is live. registry is None ⇒ skills are off
        # entirely (the UX-B-1/2 baseline); org skills ARE skills, so they fail closed with it
        # (ADR-F067 — the feature being off never opens an org snapshot). Resolve the display
        # label/description from whichever source wins, THEN append once (shipped or org share
        # one entry shape).
        record = registry.get(name) if registry is not None else None
        snapshot = snapshots.get(name) if registry is not None else None
        if record is not None:
            # No shadowing (D2): shipped wins on collision. If an org snapshot ALSO claims this
            # slug the shipped entry is served and the org version is ignored — logged as a
            # structured warning (never a silent swap).
            if snapshot is not None:
                shadowed_skills.append(name)
            summary = record.summary()
            label = summary.title or name
            description = summary.description
        elif snapshot is not None:
            label = snapshot.title or name
            description = snapshot.description
        else:
            # Adopted + bound but resolves NOWHERE — registry drift, a revoked/superseded org
            # snapshot (absent from the map), or the whole skills subsystem being off (registry
            # None). Fail-closed drop with a structured warning (F067 D3.8 revoke signal); the
            # pre-slice code dropped registry drift silently.
            unresolved_skills.append(name)
            continue
        entries.append(
            CapabilityEntry(
                kind=KIND_SKILL,
                key=name,
                label=label,
                description=description,
                available=True,
                default_enabled=True,
                toggleable=True,
            )
        )

    if shadowed_skills:
        logger.warning(
            "org skill slug collides with a shipped skill; shipped wins (org version ignored)",
            extra={
                "event": "org_skill_shadowed_by_shipped",
                "count": len(shadowed_skills),
                "keys": sorted(shadowed_skills),
            },
        )
    if unresolved_skills:
        logger.warning(
            "adopted+bound skill resolves in neither the registry nor an approved org "
            "snapshot; dropped from availability (fail-closed)",
            extra={
                "event": "skill_unresolved_skipped",
                "count": len(unresolved_skills),
                "keys": sorted(unresolved_skills),
            },
        )

    # Tools — the area's rows ∩ registry, iterated in canonical REGISTRY order (D4), so the
    # sequence is code-canonical and reproduces today's build order exactly. A drifted row
    # (group absent from the registry) is dropped HERE — this is the one place a real DB
    # row meets the registry, so the D3(c) structured warning fires here (counts/keys
    # only); downstream consumers only ever see the pre-filtered set.
    group_key_set = set(tool_group_keys)
    unknown_groups = sorted(group_key_set - TOOL_GROUP_REGISTRY.keys())
    if unknown_groups:
        logger.warning(
            "tool-group rows not in registry; dropped from availability (no grant)",
            extra={
                "event": "tool_group_unknown_skipped",
                "count": len(unknown_groups),
                "keys": unknown_groups,
            },
        )
    for group_key, tdef in TOOL_GROUP_REGISTRY.items():
        if group_key not in group_key_set:
            continue
        if (KIND_TOOL, group_key) not in adopted:
            continue
        entries.append(
            CapabilityEntry(
                kind=KIND_TOOL,
                key=group_key,
                label=tdef.spec.label,
                description=tdef.spec.description,
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
