"""Pure tests for the capability inventory + playbook renderer (ADR-F054 + ADR-F065).

No DB / no model — the inventory is a pure function over (bound skill names, registry, bound
playbooks, bound tool-group keys) narrowed by the org's adopt-in Library. These lock the
single source of truth the API and the run composition both consume.

STORE-1 (ADR-F065) flipped the narrowing predicate from disable-out (Level-0 toggles) to
adopt-in (``org_library_entries``): a binding resolves ONLY if its (kind, key) is adopted.
Most tests here adopt every fixture capability (the common "all available" case) via the
``_inv`` wrapper's default; the drift-guard matrix + the Library block pin the polarity.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

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


def _lib(kind: str, key: str) -> SimpleNamespace:
    """One adopted org_library_entries row (structural)."""
    return SimpleNamespace(capability_kind=kind, capability_key=key)


def _snap(
    slug: str, *, title: str | None = None, description: str | None = None
) -> SimpleNamespace:
    """One approved org_skill_versions snapshot (structural — slug/title/description)."""
    return SimpleNamespace(slug=slug, title=title, description=description)


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


def _adopt_all(
    *,
    tool_group_keys: Sequence[str],
    bound_skill_names: Sequence[str],
    area_playbooks: Sequence[Any],
) -> list[SimpleNamespace]:
    """Library entries adopting every fixture capability — the common 'all adopted' case."""
    return (
        [_lib("tool", k) for k in tool_group_keys]
        + [_lib("skill", n) for n in bound_skill_names]
        + [_lib("playbook", str(pb.id)) for pb in area_playbooks]
    )


def _inv(
    *,
    tool_group_keys: Sequence[str] = (),
    bound_skill_names: Sequence[str] = (),
    registry: Any = None,
    area_playbooks: Sequence[Any] = (),
    library_entries: Sequence[Any] | None = None,
    org_skill_snapshots: Any = None,
) -> cap.CapabilityInventory:
    """``build_area_inventory`` with adopt-in defaults: unless ``library_entries`` is given
    explicitly, every fixture capability is adopted (so it is available). ``org_skill_snapshots``
    (ADR-F067) threads straight through — default None ≡ the pre-slice registry-only path."""
    if library_entries is None:
        library_entries = _adopt_all(
            tool_group_keys=tool_group_keys,
            bound_skill_names=bound_skill_names,
            area_playbooks=area_playbooks,
        )
    return build_area_inventory(
        tool_group_keys=list(tool_group_keys),
        bound_skill_names=list(bound_skill_names),
        registry=registry,
        area_playbooks=list(area_playbooks),
        library_entries=list(library_entries),
        org_skill_snapshots=org_skill_snapshots,
    )


# --- inventory composition ---------------------------------------------------
def test_commercial_inventory_lists_skills_tools_playbooks_and_mcp() -> None:
    pb = _playbook("NDA playbook")
    inv = _inv(
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
    inv = _inv(
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
    inv = _inv(
        tool_group_keys=[],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    assert all(e.kind != "tool" for e in inv.entries)


def test_tool_group_row_not_in_registry_is_dropped_with_warning(caplog: Any) -> None:
    # SETUP-4a (D3(c), review F3): a row naming a group absent from the registry is dropped
    # AT THE AVAILABILITY CHOKEPOINT — the structured drift warning (counts/keys only) fires
    # HERE regardless of adoption, and only the registry-known groups become entries.
    with caplog.at_level(logging.WARNING):
        inv = _inv(
            tool_group_keys=["redlining", "not-a-real-group"],
            bound_skill_names=[],
            registry=_registry(),
            area_playbooks=[],
            # Adopt BOTH (even the drifted one) to prove the registry drop is independent.
            library_entries=[_lib("tool", "redlining"), _lib("tool", "not-a-real-group")],
        )
    tools = {s.kind: s for s in inv.sections()}["tool"]
    assert [e.key for e in tools.entries] == ["redlining"]  # drifted row never an entry
    drift = [r for r in caplog.records if getattr(r, "event", None) == "tool_group_unknown_skipped"]
    assert drift, "the D3(c) drift warning did not fire at the availability chokepoint"
    assert drift[0].count == 1 and drift[0].keys == ["not-a-real-group"]


def test_skill_unknown_to_registry_is_dropped_as_drift() -> None:
    inv = _inv(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review", "gone-from-registry"],
        registry=_registry(),
        area_playbooks=[],
    )
    skills = {s.kind: s for s in inv.sections()}["skill"]
    assert [e.key for e in skills.entries] == ["nda-review"]


def test_no_registry_yields_no_skills() -> None:
    # registry None ⇒ skills off entirely; org skills are skills, so an approved snapshot must
    # NOT resolve either (ADR-F067 — the feature being off fails closed). Passing a matching
    # org snapshot proves the org branch does not sneak a skill in when the registry is absent.
    inv = _inv(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review", "house-nda-clause"],
        registry=None,
        area_playbooks=[],
        org_skill_snapshots={"house-nda-clause": _snap("house-nda-clause", title="House NDA")},
    )
    assert all(e.kind != "skill" for e in inv.entries)


def test_skill_label_falls_back_to_name_without_title() -> None:
    reg = _FakeRegistry({"nda-review": _FakeRecord(None, None)})
    inv = _inv(
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


# --- org-authored skill snapshots (ADR-F067 D2/D3) ---------------------------
def test_org_skill_snapshot_adopted_and_bound_resolves_with_title_label() -> None:
    """An approved org snapshot the registry does NOT know, adopted + bound, becomes an
    available skill entry labelled from its snapshot title."""
    inv = _inv(
        tool_group_keys=[],
        bound_skill_names=["house-nda-clause"],
        registry=_registry(),  # does not know the org slug
        area_playbooks=[],
        org_skill_snapshots={
            "house-nda-clause": _snap(
                "house-nda-clause",
                title="House NDA clause",
                description="Our standard NDA clause.",
            )
        },
    )
    (skill,) = [e for e in inv.entries if e.kind == "skill"]
    assert skill.key == "house-nda-clause"
    assert skill.label == "House NDA clause"
    assert skill.description == "Our standard NDA clause."
    assert skill.available and skill.toggleable and skill.default_enabled


def test_org_skill_snapshot_label_falls_back_to_slug_without_title() -> None:
    inv = _inv(
        bound_skill_names=["house-nda-clause"],
        registry=_registry(),
        org_skill_snapshots={"house-nda-clause": _snap("house-nda-clause")},
    )
    (skill,) = [e for e in inv.entries if e.kind == "skill"]
    assert skill.label == "house-nda-clause"


def test_org_skill_snapshot_not_adopted_is_absent() -> None:
    """Approval is not adoption (ADR-F067): a snapshot bound but NOT in the Library never
    becomes an entry — and does NOT fire the unresolved warning (adoption is checked first)."""
    inv = _inv(
        bound_skill_names=["house-nda-clause"],
        registry=_registry(),
        area_playbooks=[],
        org_skill_snapshots={"house-nda-clause": _snap("house-nda-clause", title="House NDA")},
        library_entries=[],  # nothing adopted
    )
    assert all(e.kind != "skill" for e in inv.entries)


def test_org_skill_revoked_or_absent_snapshot_drops_with_unresolved_warning(caplog: Any) -> None:
    """A still-adopted+bound skill whose approved snapshot is gone (revoked/superseded ⇒
    absent from the map) and that the registry does not know is dropped fail-closed with the
    F067 D3.8 ``skill_unresolved_skipped`` warning (counts/keys only)."""
    with caplog.at_level(logging.WARNING):
        inv = _inv(
            bound_skill_names=["revoked-skill"],
            registry=_registry(),  # does not know it
            org_skill_snapshots={},  # revoked ⇒ absent from the map
        )
    assert all(e.kind != "skill" for e in inv.entries)
    dropped = [r for r in caplog.records if getattr(r, "event", None) == "skill_unresolved_skipped"]
    assert dropped, "the F067 D3.8 fail-close warning did not fire"
    assert dropped[0].count == 1 and dropped[0].keys == ["revoked-skill"]


def test_org_skill_default_none_drops_org_only_binding_fail_closed(caplog: Any) -> None:
    """The kwarg is OPTIONAL and fails CLOSED: omitting it drops an org-only skill (one the
    registry does not know), never opens anything — the same posture as a revoked snapshot."""
    with caplog.at_level(logging.WARNING):
        inv = _inv(
            bound_skill_names=["house-nda-clause"],
            registry=_registry(),
            # org_skill_snapshots omitted (default None)
        )
    assert all(e.kind != "skill" for e in inv.entries)
    assert any(getattr(r, "event", None) == "skill_unresolved_skipped" for r in caplog.records)


def test_org_skill_shadowed_by_shipped_registry_wins(caplog: Any) -> None:
    """No shadowing (D2): when BOTH the registry and an org snapshot claim a slug the shipped
    entry wins (its label) and the org version is ignored with the
    ``org_skill_shadowed_by_shipped`` warning."""
    with caplog.at_level(logging.WARNING):
        inv = _inv(
            bound_skill_names=["nda-review"],
            registry=_registry(),  # knows nda-review as "NDA review"
            org_skill_snapshots={"nda-review": _snap("nda-review", title="ORG NDA override")},
        )
    (skill,) = [e for e in inv.entries if e.kind == "skill"]
    assert skill.label == "NDA review"  # shipped wins, not the org title
    shadowed = [
        r for r in caplog.records if getattr(r, "event", None) == "org_skill_shadowed_by_shipped"
    ]
    assert shadowed, "the no-shadowing warning did not fire"
    assert shadowed[0].count == 1 and shadowed[0].keys == ["nda-review"]


def test_org_and_shipped_skills_coexist_in_inventory_order() -> None:
    """A mixed area: one shipped skill + one org snapshot both resolve; entry order follows
    ``bound_skill_names`` (not sorted, not source-grouped)."""
    inv = _inv(
        bound_skill_names=["nda-review", "house-nda-clause"],
        registry=_registry(),
        org_skill_snapshots={"house-nda-clause": _snap("house-nda-clause", title="House NDA")},
    )
    skills = {s.kind: s for s in inv.sections()}["skill"]
    assert [e.key for e in skills.entries] == ["nda-review", "house-nda-clause"]


# --- STORE-1 drift guard: catalog vs Library vs binding (ADR-F065) -----------
def test_adopted_and_bound_resolves_for_every_kind() -> None:
    """adopted + bound ⇒ the capability resolves (is an available entry)."""
    pb = _playbook("NDA playbook")
    inv = _inv(
        tool_group_keys=["redlining"],
        bound_skill_names=["nda-review"],
        registry=_registry(),
        area_playbooks=[pb],
        library_entries=[
            _lib("tool", "redlining"),
            _lib("skill", "nda-review"),
            _lib("playbook", str(pb.id)),
        ],
    )
    assert ("tool", "redlining") in {(e.kind, e.key) for e in inv.entries}
    assert ("skill", "nda-review") in {(e.kind, e.key) for e in inv.entries}
    assert ("playbook", str(pb.id)) in {(e.kind, e.key) for e in inv.entries}


def test_not_adopted_but_bound_is_narrowed_for_every_kind() -> None:
    """not-adopted + bound ⇒ narrowed (absent from the inventory) — the single off-state."""
    pb = _playbook("NDA playbook")
    inv = _inv(
        tool_group_keys=["redlining"],
        bound_skill_names=["nda-review"],
        registry=_registry(),
        area_playbooks=[pb],
        library_entries=[],  # nothing adopted
    )
    kinds = {e.kind for e in inv.entries}
    assert kinds == {"mcp"}  # only the placeholder survives
    assert all(e.kind not in {"tool", "skill", "playbook"} for e in inv.entries)


def test_not_adopted_and_not_bound_is_absent_for_every_kind() -> None:
    """not-adopted + not-bound ⇒ absent (nothing bound, nothing adopted)."""
    inv = _inv(
        tool_group_keys=[],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
        library_entries=[],
    )
    assert [e.kind for e in inv.entries] == ["mcp"]


def test_partial_adoption_narrows_only_the_unadopted() -> None:
    """A mixed Library adopts some bindings and not others — each resolves independently."""
    inv = _inv(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review", "msa-review-saas"],
        registry=_registry(),
        area_playbooks=[],
        library_entries=[_lib("tool", "redlining"), _lib("skill", "msa-review-saas")],
    )
    tools = {s.kind: s for s in inv.sections()}["tool"]
    skills = {s.kind: s for s in inv.sections()}["skill"]
    assert [e.key for e in tools.entries] == ["redlining"]  # tabular not adopted → narrowed
    assert [e.key for e in skills.entries] == ["msa-review-saas"]  # nda-review not adopted


# --- toggle resolution -------------------------------------------------------
def test_enabled_keys_all_on_by_default() -> None:
    pb = _playbook("NDA playbook")
    inv = _inv(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review"],
        registry=_registry(),
        area_playbooks=[pb],
    )
    assert inv.enabled_keys("skill", []) == ["nda-review"]
    assert inv.enabled_keys("tool", []) == ["redlining", "tabular"]
    assert inv.enabled_keys("playbook", []) == [str(pb.id)]


def test_enabled_keys_applies_off_override() -> None:
    inv = _inv(
        tool_group_keys=["ropa", "assessment"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    toggles = [SimpleNamespace(capability_kind="tool", capability_key="ropa", enabled=False)]
    assert inv.enabled_keys("tool", toggles) == ["assessment"]


def test_enabled_keys_explicit_on_is_a_noop_against_default_on() -> None:
    inv = _inv(
        tool_group_keys=["ropa", "assessment"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    toggles = [SimpleNamespace(capability_kind="tool", capability_key="ropa", enabled=True)]
    assert set(inv.enabled_keys("tool", toggles)) == {"ropa", "assessment"}


def test_enabled_keys_preserves_inventory_order() -> None:
    inv = _inv(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review", "msa-review-saas"],
        registry=_registry(),
        area_playbooks=[],
    )
    # Inventory order follows bound_skill_names order, not sorted.
    assert inv.enabled_keys("skill", []) == ["nda-review", "msa-review-saas"]


def test_mcp_is_never_enabled() -> None:
    inv = _inv(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=[],
        registry=_registry(),
        area_playbooks=[],
    )
    # Even an (illegitimate) override can't enable the non-toggleable placeholder.
    toggles = [SimpleNamespace(capability_kind="mcp", capability_key="mcp", enabled=True)]
    assert inv.enabled_keys("mcp", toggles) == []


def test_is_toggleable_guards_the_put_boundary() -> None:
    pb = _playbook("NDA playbook")
    inv = _inv(
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
    inv = _inv(
        tool_group_keys=["redlining", "tabular"],
        bound_skill_names=["nda-review"],
        registry=_registry(),
        area_playbooks=[],
    )
    toggles = [SimpleNamespace(capability_kind="tool", capability_key="redlining", enabled=False)]
    m = inv.enabled_map(toggles)
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


# --- RECOMMENDED_LIBRARY_SETS drift guard (STORE-2 D-C) ----------------------


def test_recommended_library_sets_area_keys_are_standard() -> None:
    """Every area key in the recommended-sets constant is a real standard area."""
    assert set(cap.RECOMMENDED_LIBRARY_SETS) == {
        "commercial",
        "privacy",
        "m-and-a",
        "disputes",
        "employment",
    }


def test_recommended_library_sets_tool_keys_resolve_against_registry() -> None:
    """Every recommended tool key must be a real, currently-registered tool group.

    A renamed/removed tool group must break CI, not silently drop the Store page's
    'Recommended for {area}' rail entry.
    """
    for area, kinds in cap.RECOMMENDED_LIBRARY_SETS.items():
        for key in kinds.get(cap.KIND_TOOL, ()):
            assert key in cap.TOOL_GROUP_REGISTRY, (
                f"recommended tool '{key}' for area '{area}' is not in TOOL_GROUP_REGISTRY"
            )


def test_recommended_library_sets_skill_names_load_from_real_corpus() -> None:
    """Every recommended skill name must load from the real `skills/` corpus.

    Mirrors the corpus-health guard in ``test_skill_loader.py`` — a renamed or
    deleted skill directory must fail CI rather than silently vanish from the
    Store page's recommendation rail.
    """
    from pathlib import Path

    from app.skills.loader import load_registry

    real_skills_dir = Path(__file__).resolve().parents[3] / "skills"
    if not real_skills_dir.is_dir():
        import pytest

        pytest.skip(f"real skills directory not present: {real_skills_dir}")

    loaded = set(load_registry(real_skills_dir).names())
    for area, kinds in cap.RECOMMENDED_LIBRARY_SETS.items():
        for name in kinds.get(cap.KIND_SKILL, ()):
            assert name in loaded, (
                f"recommended skill '{name}' for area '{area}' does not load "
                "from the real skills/ corpus"
            )


def test_recommended_library_sets_no_playbooks() -> None:
    """No seed migration binds a playbook to any area — verified empty by design."""
    for kinds in cap.RECOMMENDED_LIBRARY_SETS.values():
        assert cap.KIND_PLAYBOOK not in kinds


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
