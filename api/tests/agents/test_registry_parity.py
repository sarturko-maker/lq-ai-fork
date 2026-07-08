"""The hard parity gate — the tool-group registry reproduces the pre-slice grants (ADR-F062).

SETUP-4a replaces the hardcoded per-area ``if area_key == …`` domain-tool branch in
``compose_and_execute_run`` with a data-driven loop over :data:`TOOL_GROUP_REGISTRY`
(``build_area_tool_groups``). The FROZEN literals below were captured from the PRE-refactor
elif output (the exact ordered tool names each builder returns, per seeded area). This test
pins that the registry loop reproduces them EXACTLY — same tools, same ORDER, same ledger
class, same ``tabular_enabled`` flag — so the default (seeded) path is provably unchanged.

Also proves the new fail-closed + isolation invariants (D3/D4):
* an unknown area (no rows) yields zero domain groups,
* a row naming an unregistered group is SKIPPED (no grant), with a structured warning,
* cross-area attachment grants exactly the named group's tools for THAT run (D3 feature),
* a privacy run never builds commercial tools unless a row attaches them (isolation).

Pure — no DB, no model. The builders stash their inputs in closures (no I/O at build
time), so a dummy session factory + a dummy redline service exercise the real loop.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from app.agents.budget import BudgetEnvelope
from app.agents.capabilities import (
    ASSESSMENT_GROUP,
    REDLINING_GROUP,
    ROPA_GROUP,
    TABULAR_GROUP,
    TOOL_GROUP_REGISTRY,
    GroupBuildContext,
    build_area_tool_groups,
)
from app.agents.deal_changes import DealChangeLedger
from app.agents.redline_service import RedlineService
from app.agents.ropa_changes import RopaChangeLedger
from app.agents.tools import MatterBinding

# --- FROZEN parity literals (captured from the pre-refactor elif output) -----------------
# The exact ordered tool names each builder returns, per group. Captured 2026-07-04 by
# running the untouched builders (build_commercial_tools / build_tabular_tools /
# build_ropa_tools / build_assessment_tools) before the composition refactor. The builders
# are NOT changed by SETUP-4a, so these are the ground truth for the grant sets; the
# registry loop must reproduce them in this order.
REDLINING_NAMES = [
    "apply_redline",
    "preview_redline",
    "extract_counterparty_position",
    "respond_to_counterparty",
    "reconcile_positions",
]
TABULAR_NAMES = [
    "start_tabular_review",
    "record_tabular_row",
    "finalize_tabular_review",
    "update_tabular_cells",
]
ROPA_NAMES = [
    "propose_processing_activity",
    "propose_system",
    "propose_vendor",
    "propose_transfer",
    "link_processing_activity_to_system",
    "link_vendor_to_activity",
    "add_data_subject_categories",
    "add_data_categories",
    "retire_processing_activity",
    "retire_system",
    "retire_vendor",
    "retire_transfer",
    "unlink_system_from_activity",
    "unlink_vendor_from_activity",
    "list_processing_activities",
    "list_systems",
    "list_vendors",
    "list_transfers",
    "list_data_subject_categories",
    "list_data_categories",
]
ASSESSMENT_NAMES = [
    "propose_assessment",
    "add_risk",
    "complete_assessment",
    "link_assessment_to_activity",
    "list_assessments",
]

# The seeded areas' tool-group sets (migration 0086 seed) and the ordered grant they must
# reproduce (registry-order ∩ the set).
COMMERCIAL_GROUPS = {"redlining", "tabular"}
COMMERCIAL_ORDERED_NAMES = REDLINING_NAMES + TABULAR_NAMES
PRIVACY_GROUPS = {"ropa", "assessment"}
PRIVACY_ORDERED_NAMES = ROPA_NAMES + ASSESSMENT_NAMES


def _names(tools: list[Any]) -> list[str]:
    return [getattr(t, "name", getattr(t, "__name__", repr(t))) for t in tools]


# The tabular adapter reads only ``envelope.fan_out_quota``; a fixed envelope suffices.
_TEST_ENVELOPE = BudgetEnvelope(
    token_budget=8_000_000, fan_out_quota=8, max_steps=400, wall_clock_seconds=3600.0
)


def _ctx(envelope: BudgetEnvelope = _TEST_ENVELOPE) -> GroupBuildContext:
    binding = MatterBinding(
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Parity Matter",
        privileged=False,
        minimum_inference_tier=None,
        practice_area_id=uuid.uuid4(),
    )
    return GroupBuildContext(
        session_factory=cast(Any, None),  # builders only stash it (no I/O at build time)
        run_id=uuid.uuid4(),
        binding=binding,
        envelope=envelope,
        redline_service_provider=lambda: cast(RedlineService, object()),
    )


# --- registry shape ----------------------------------------------------------------------
def test_registry_order_is_canonical() -> None:
    # Insertion order IS the canonical group order — the parity gate depends on it (D4).
    # B-3 (ADR-F067 D1): the composition-only knowledge group sits LAST, so it perturbs
    # no seeded area's grant order (mirrors the pin in tests/agents/test_capabilities.py).
    assert list(TOOL_GROUP_REGISTRY) == ["redlining", "tabular", "ropa", "assessment", "knowledge"]
    assert TOOL_GROUP_REGISTRY["redlining"].spec is REDLINING_GROUP
    assert TOOL_GROUP_REGISTRY["tabular"].spec is TABULAR_GROUP
    assert TOOL_GROUP_REGISTRY["ropa"].spec is ROPA_GROUP
    assert TOOL_GROUP_REGISTRY["assessment"].spec is ASSESSMENT_GROUP


# --- the hard parity gate ----------------------------------------------------------------
# The tabular_enabled prompt flag (the third parity dimension) is pinned at the REAL seam —
# the composition-driven doctrine tests in tests/agents/test_agent_composition.py
# (test_tabular_doctrine_*): commercial → doctrine present, privacy → absent, and a NEW
# area with a tabular row → present (the area-agnostic derivation). Asserting it against
# this file's own literals would be a tautology (review F2).
def test_commercial_parity_tools_order_and_ledger() -> None:
    tools, ledger = build_area_tool_groups(_ctx(), COMMERCIAL_GROUPS)
    assert _names(tools) == COMMERCIAL_ORDERED_NAMES  # exact tools, exact ORDER
    assert isinstance(ledger, DealChangeLedger)  # first ledger-bearing group's ledger


def test_privacy_parity_tools_order_and_ledger() -> None:
    tools, ledger = build_area_tool_groups(_ctx(), PRIVACY_GROUPS)
    assert _names(tools) == PRIVACY_ORDERED_NAMES
    assert isinstance(ledger, RopaChangeLedger)


def test_group_input_order_does_not_change_output_order() -> None:
    # The loop iterates the REGISTRY, not the input — so a reversed input set is identical.
    tools_a, _ = build_area_tool_groups(_ctx(), {"tabular", "redlining"})
    assert _names(tools_a) == COMMERCIAL_ORDERED_NAMES


# --- fail-closed + isolation (D3/D4) -----------------------------------------------------
def test_unknown_area_yields_zero_domain_groups() -> None:
    tools, ledger = build_area_tool_groups(_ctx(), set())
    assert tools == []
    assert ledger is None


def test_unknown_group_row_is_skipped_never_granted(caplog: Any) -> None:
    with caplog.at_level(logging.WARNING):
        tools, ledger = build_area_tool_groups(_ctx(), {"redlining", "bogus-group"})
    # The bogus row grants nothing; only redlining is built (fail-closed to absence).
    assert _names(tools) == REDLINING_NAMES
    assert isinstance(ledger, DealChangeLedger)
    # A structured warning records the skip (counts/keys only — no values).
    assert any(
        getattr(r, "event", None) == "tool_group_unknown_skipped"
        or "not in registry" in r.getMessage()
        for r in caplog.records
    )


def test_cross_area_attachment_grants_only_the_named_group() -> None:
    # D3: attaching one group (e.g. redlining) to ANY area grants exactly its tools for that
    # run — the loop is area-agnostic (data-driven). No commercial tools leak into a set
    # that doesn't name them, and vice versa (isolation both sides).
    red_tools, _ = build_area_tool_groups(_ctx(), {"redlining"})
    assert _names(red_tools) == REDLINING_NAMES
    assert "start_tabular_review" not in _names(red_tools)  # tabular not attached → absent

    ropa_tools, ledger = build_area_tool_groups(_ctx(), {"ropa"})
    assert _names(ropa_tools) == ROPA_NAMES
    assert isinstance(ledger, RopaChangeLedger)
    # A privacy-only set never builds a commercial tool (isolation).
    assert not (set(_names(ropa_tools)) & set(COMMERCIAL_ORDERED_NAMES))


def test_only_first_ledger_streams_when_two_are_attached(caplog: Any) -> None:
    # D5: if DATA ever attaches two ledger-bearing groups, both build but only the first
    # (registry order → redlining) streams; a warning records the second.
    with caplog.at_level(logging.WARNING):
        tools, ledger = build_area_tool_groups(_ctx(), {"redlining", "ropa"})
    assert isinstance(ledger, DealChangeLedger)  # redlining is first in registry order
    # Both groups' tools are still built (honest, non-breaking).
    assert set(REDLINING_NAMES) <= set(_names(tools))
    assert set(ROPA_NAMES) <= set(_names(tools))
    assert any(
        getattr(r, "event", None) == "tool_group_multi_ledger" or "only the first" in r.getMessage()
        for r in caplog.records
    )
