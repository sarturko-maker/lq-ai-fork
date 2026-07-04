"""Pure tests for the capability inventory + playbook renderer (ADR-F054).

No DB / no model — the inventory is a pure function over (area key, bound skill names,
registry, bound playbooks) and the lawyer's toggle overlay. These lock the single
source of truth the API and the run composition both consume.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace

from app.agents import capabilities as cap
from app.agents.capabilities import build_area_inventory, empty_inventory
from app.agents.playbook_context import render_practice_playbook


# --- fakes -------------------------------------------------------------------
@dataclass
class _FakeSummary:
    title: str | None
    description: str | None


@dataclass
class _FakeRecord:
    title: str | None
    description: str | None

    def summary(self) -> _FakeSummary:
        return _FakeSummary(self.title, self.description)


@dataclass
class _FakeRegistry:
    records: dict[str, _FakeRecord]

    def get(self, name: str) -> _FakeRecord | None:
        return self.records.get(name)

    def names(self) -> list[str]:
        return sorted(self.records)


def _toggle(kind: str, key: str, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(capability_kind=kind, capability_key=key, enabled=enabled)


def _playbook(name: str, *, contract_type: str = "NDA", description: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, contract_type=contract_type, description=description
    )


def _registry() -> _FakeRegistry:
    return _FakeRegistry(
        {
            "nda-review": _FakeRecord("NDA review", "Use when reviewing an NDA."),
            "msa-review-saas": _FakeRecord("MSA review (SaaS)", "Use for a SaaS MSA."),
        }
    )


# --- inventory composition ---------------------------------------------------
def test_commercial_inventory_lists_skills_tools_playbooks_and_mcp() -> None:
    pb = _playbook("NDA playbook")
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review", "msa-review-saas"],
        registry=_registry(),
        area_playbooks=[pb],
    )
    sections = {s.kind: s for s in inv.sections()}
    assert [s.kind for s in inv.sections()] == ["playbook", "skill", "tool", "mcp"]
    assert [e.key for e in sections["playbook"].entries] == [str(pb.id)]
    assert {e.key for e in sections["skill"].entries} == {"nda-review", "msa-review-saas"}
    # Commercial offers the redlining + tabular (Grids) tool groups (ADR-F055).
    assert [e.key for e in sections["tool"].entries] == ["redlining", "tabular"]
    # MCP is the disabled placeholder.
    (mcp,) = sections["mcp"].entries
    assert mcp.available is False and mcp.toggleable is False


def test_privacy_inventory_offers_ropa_and_assessment_groups() -> None:
    inv = build_area_inventory(
        tool_group_keys=["ropa", "assessment"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    tools = {s.kind: s for s in inv.sections()}["tool"]
    assert [e.key for e in tools.entries] == ["ropa", "assessment"]


def test_area_with_no_tool_group_rows_has_no_tool_groups() -> None:
    # SETUP-4a: tool availability is DATA — an area with no practice_area_tool_groups rows
    # (e.g. a fresh admin-created area, or an unconfigured seed area) offers no tool groups.
    inv = build_area_inventory(
        tool_group_keys=[],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    assert all(e.kind != "tool" for e in inv.entries)


def test_tool_group_row_not_in_registry_is_dropped_as_drift() -> None:
    # SETUP-4a (D3): a row naming a group absent from the registry is silently dropped from
    # availability (fail-closed) — only the registry-known groups become entries.
    inv = build_area_inventory(
        tool_group_keys=["redlining", "not-a-real-group"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    tools = {s.kind: s for s in inv.sections()}["tool"]
    assert [e.key for e in tools.entries] == ["redlining"]


def test_skill_unknown_to_registry_is_dropped_as_drift() -> None:
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review", "gone-from-registry"],
        registry=_registry(),
        area_playbooks=[],
    )
    skills = {s.kind: s for s in inv.sections()}["skill"]
    assert [e.key for e in skills.entries] == ["nda-review"]


def test_no_registry_yields_no_skills() -> None:
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review"],
        registry=None,
        area_playbooks=[],
    )
    assert all(e.kind != "skill" for e in inv.entries)


def test_skill_label_falls_back_to_name_without_title() -> None:
    reg = _FakeRegistry({"nda-review": _FakeRecord(None, None)})
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review"],
        registry=reg,
        area_playbooks=[],
    )
    (skill,) = [e for e in inv.entries if e.kind == "skill"]
    assert skill.label == "nda-review"


def test_empty_inventory_is_mcp_only() -> None:
    inv = empty_inventory()
    assert [e.kind for e in inv.entries] == ["mcp"]


# --- toggle resolution -------------------------------------------------------
def test_enabled_keys_all_on_by_default() -> None:
    pb = _playbook("NDA playbook")
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review"],
        registry=_registry(),
        area_playbooks=[pb],
    )
    assert inv.enabled_keys("skill", []) == ["nda-review"]
    assert inv.enabled_keys("tool", []) == ["redlining", "tabular"]
    assert inv.enabled_keys("playbook", []) == [str(pb.id)]


def test_enabled_keys_applies_off_override() -> None:
    inv = build_area_inventory(
        tool_group_keys=["ropa", "assessment"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    toggles = [_toggle("tool", "ropa", False)]
    assert inv.enabled_keys("tool", toggles) == ["assessment"]


def test_enabled_keys_explicit_on_is_a_noop_against_default_on() -> None:
    inv = build_area_inventory(
        tool_group_keys=["ropa", "assessment"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    toggles = [_toggle("tool", "ropa", True)]
    assert set(inv.enabled_keys("tool", toggles)) == {"ropa", "assessment"}


def test_enabled_keys_preserves_inventory_order() -> None:
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review", "msa-review-saas"],
        registry=_registry(),
        area_playbooks=[],
    )
    # Inventory order follows bound_skill_names order, not sorted.
    assert inv.enabled_keys("skill", []) == ["nda-review", "msa-review-saas"]


def test_mcp_is_never_enabled() -> None:
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    # Even an (illegitimate) override can't enable the non-toggleable placeholder.
    assert inv.enabled_keys("mcp", [_toggle("mcp", "mcp", True)]) == []


def test_is_toggleable_guards_the_put_boundary() -> None:
    pb = _playbook("NDA playbook")
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review"],
        registry=_registry(),
        area_playbooks=[pb],
    )
    assert inv.is_toggleable("skill", "nda-review") is True
    assert inv.is_toggleable("tool", "redlining") is True
    assert inv.is_toggleable("playbook", str(pb.id)) is True
    # Unknown / wrong-kind / placeholder are all rejected.
    assert inv.is_toggleable("tool", "ropa") is False  # not a commercial group
    assert inv.is_toggleable("skill", "does-not-exist") is False
    assert inv.is_toggleable("mcp", "mcp") is False


def test_enabled_map_covers_every_entry() -> None:
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review"],
        registry=_registry(),
        area_playbooks=[],
    )
    m = inv.enabled_map([_toggle("tool", "redlining", False)])
    assert m[("skill", "nda-review")] is True
    assert m[("tool", "redlining")] is False
    assert m[("mcp", "mcp")] is False


def test_tool_group_registry_order_is_canonical() -> None:
    # SETUP-4a (ADR-F062): the code registry's INSERTION ORDER is the canonical group order
    # (was the AREA_TOOL_GROUPS map). Composition + inventory both iterate this order
    # filtered by an area's rows, so it must stay pinned. The seed (commercial →
    # {redlining, tabular}, privacy → {ropa, assessment}) is pinned by the migration
    # round-trip (tests/test_migrations.py) + the seed-idempotency test
    # (tests/test_practice_areas.py); the parity gate (tests/agents/test_registry_parity.py)
    # pins that this order reproduces the pre-slice per-area grants exactly.
    assert list(cap.TOOL_GROUP_REGISTRY) == ["redlining", "tabular", "ropa", "assessment"]


# --- Level-0 (deployment-wide) narrowing (ADR-F062) --------------------------
def test_deployment_disabled_tool_group_removed_from_availability() -> None:
    inv = build_area_inventory(
        tool_group_keys=["ropa", "assessment"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
        deployment_toggles=[_toggle("tool", "ropa", False)],
    )
    tools = {s.kind: s for s in inv.sections()}["tool"]
    assert [e.key for e in tools.entries] == ["assessment"]  # ropa vanished entirely


def test_deployment_disabled_skill_removed_from_availability() -> None:
    inv = build_area_inventory(
        tool_group_keys=[],
        bound_skill_names=["nda-review", "msa-review-saas"],
        registry=_registry(),
        area_playbooks=[],
        deployment_toggles=[_toggle("skill", "nda-review", False)],
    )
    skills = {s.kind: s for s in inv.sections()}["skill"]
    assert [e.key for e in skills.entries] == ["msa-review-saas"]


def test_deployment_disabled_playbook_removed_from_availability() -> None:
    pb = _playbook("NDA playbook")
    inv = build_area_inventory(
        tool_group_keys=[],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[pb],
        deployment_toggles=[_toggle("playbook", str(pb.id), False)],
    )
    assert all(e.kind != "playbook" for e in inv.entries)


def test_deployment_enabled_toggle_is_inert() -> None:
    # An enabled=true Level-0 row is a no-op (absence already means available).
    inv = build_area_inventory(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review"],
        registry=_registry(),
        area_playbooks=[],
        deployment_toggles=[_toggle("tool", "redlining", True)],
    )
    tools = {s.kind: s for s in inv.sections()}["tool"]
    assert [e.key for e in tools.entries] == ["redlining", "tabular"]


# --- playbook renderer -------------------------------------------------------
def _position(
    issue: str, standard: str, *, fallbacks: list[dict] | None = None, severity: str = "high"
) -> SimpleNamespace:
    return SimpleNamespace(
        issue=issue,
        standard_language=standard,
        fallback_tiers=fallbacks or [],
        severity_if_missing=severity,
    )


def _pb_with_positions(name: str, positions: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(name=name, contract_type="NDA", positions=positions)


def test_render_practice_playbook_empty_is_blank() -> None:
    assert render_practice_playbook([]) == ""


def test_render_practice_playbook_formats_positions() -> None:
    pb = _pb_with_positions(
        "NDA playbook",
        [
            _position(
                "Liability cap",
                "Liability capped at fees paid.",
                fallbacks=[
                    {"rank": 1, "description": "2x fees"},
                    {"rank": 2, "language": "5x fees"},
                ],
                severity="critical",
            )
        ],
    )
    text = render_practice_playbook([pb])
    assert "NDA playbook (NDA)" in text
    assert "Liability cap" in text
    assert "Liability capped at fees paid." in text
    assert "2x fees" in text and "5x fees" in text
    assert "critical" in text


def test_render_practice_playbook_caps_total_length() -> None:
    big = "x" * 1000
    positions = [_position(f"Issue {i}", big) for i in range(50)]
    text = render_practice_playbook([_pb_with_positions("Huge", positions)])
    assert len(text) <= cap_total()


def test_render_practice_playbook_handles_no_positions() -> None:
    text = render_practice_playbook([_pb_with_positions("Empty book", [])])
    assert "Empty book" in text
    assert "no positions recorded" in text


def test_render_practice_playbook_is_defensive_over_malformed_fallbacks() -> None:
    pb = _pb_with_positions(
        "NDA playbook",
        [_position("Issue", "Std", fallbacks=["not-a-dict", {"nope": 1}, {"description": "ok"}])],
    )
    text = render_practice_playbook([pb])
    assert "ok" in text  # only the well-formed tier surfaces; no crash


def cap_total() -> int:
    from app.agents.playbook_context import _MAX_TOTAL_CHARS

    return _MAX_TOTAL_CHARS
