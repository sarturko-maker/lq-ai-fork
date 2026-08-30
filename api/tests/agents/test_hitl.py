"""Pure tests for the HITL policy compiler — HITL-1 (ADR-F071).

No DB / no model: ``compile_hitl_policy`` is a pure function over
(stored policy, run grant set), and ``stamp_subagent_opt_out`` a pure
mutation of the rendered subagent specs. These pin the maintainer's
zero-config invariant at its source: an empty (or fully-dropped) policy
compiles to ``None`` — the caller then never sets ``interrupt_on`` and
never touches a spec, so the unconfigured graph is byte-identical to
today's. The end-to-end pause rides ``test_agent_runner.py`` /
``test_agent_composition.py``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.hitl import (
    ALWAYS_INTERRUPT_TOOL_NAMES,
    EDITABLE_TOOL_NAMES,
    allowed_decisions_for,
    compile_hitl_policy,
    decisions_allowed_for_step,
    stamp_subagent_opt_out,
)

_GRANTED = frozenset({"apply_redline", "search_documents", "read_document"})


# --- T1(a): zero-config invariant at the compiler -----------------------------


def test_empty_policy_compiles_to_none() -> None:
    assert compile_hitl_policy({}, _GRANTED) is None


def test_policy_naming_only_ungranted_tools_compiles_to_none() -> None:
    """A stale policy (tool no longer granted) must compile to NOTHING — no
    middleware, no error, never a bricked run (ADR-F071)."""
    assert compile_hitl_policy({"retired_tool": True}, _GRANTED) is None


def test_empty_grant_set_compiles_to_none() -> None:
    assert compile_hitl_policy({"apply_redline": True}, frozenset()) is None


# --- T6: compiler units (R2/R3/R4) --------------------------------------------


def test_true_compiles_to_approve_reject_config_with_fork_description() -> None:
    compiled = compile_hitl_policy({"apply_redline": True}, _GRANTED)
    assert compiled is not None
    assert set(compiled) == {"apply_redline"}
    config = compiled["apply_redline"]
    # An ORDINARY gated tool's decisions are EXACTLY approve/reject — `edit` is
    # scoped to the one editable tool (ADR-F087) and `respond` exists nowhere.
    assert config["allowed_decisions"] == ["approve", "reject"]
    # The ask is fork-authored (static string; args ride as data, never prose).
    assert config["description"] == (
        "The agent wants to run apply_redline and is waiting for your go-ahead."
    )


def test_unknown_names_drop_with_warning_and_granted_names_survive(
    caplog: Any,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.agents.hitl"):
        compiled = compile_hitl_policy({"apply_redline": True, "not_a_tool": True}, _GRANTED)
    assert compiled is not None and set(compiled) == {"apply_redline"}
    dropped = [r for r in caplog.records if r.__dict__.get("event") == "hitl_policy_name_dropped"]
    assert [r.__dict__.get("tool") for r in dropped] == ["not_a_tool"]


def test_malformed_values_skip_without_raising(caplog: Any) -> None:
    """Anything but exactly `true` is malformed in v1 — skipped (name only in the
    log, never the value), and a malformed policy never bricks the run."""
    policy: dict[Any, Any] = {
        "apply_redline": True,  # the one valid entry
        "search_documents": False,  # falsy must NOT arm middleware — skipped
        "read_document": {"allowed_decisions": ["approve"]},  # dict shape is v2+
    }
    with caplog.at_level(logging.WARNING, logger="app.agents.hitl"):
        compiled = compile_hitl_policy(policy, _GRANTED)
    assert compiled is not None and set(compiled) == {"apply_redline"}
    skipped = [r for r in caplog.records if r.__dict__.get("event") == "hitl_policy_entry_skipped"]
    assert {r.__dict__.get("tool") for r in skipped} == {"search_documents", "read_document"}


def test_non_string_keys_skip_without_raising(caplog: Any) -> None:
    with caplog.at_level(logging.WARNING, logger="app.agents.hitl"):
        compiled = compile_hitl_policy({1: True, "apply_redline": True}, _GRANTED)
    assert compiled is not None and set(compiled) == {"apply_redline"}
    skipped = [r for r in caplog.records if r.__dict__.get("event") == "hitl_policy_entry_skipped"]
    assert len(skipped) == 1
    # The bad key's TYPE is logged, never its value.
    assert skipped[0].__dict__.get("key_type") == "int"
    assert "tool" not in skipped[0].__dict__


def test_all_entries_malformed_compiles_to_none() -> None:
    assert compile_hitl_policy({"apply_redline": False, 2: True}, _GRANTED) is None


# --- T7: subagent opt-out stamp (R7) ------------------------------------------


def test_stamp_with_compiled_policy_opts_every_spec_out() -> None:
    specs = [
        {"name": "drafter", "description": "d", "system_prompt": "p"},
        {"name": "reviewer", "description": "d", "system_prompt": "p", "skills": ["/s"]},
    ]
    stamp_subagent_opt_out(specs, {"apply_redline": {"allowed_decisions": ["approve", "reject"]}})
    assert all(spec["interrupt_on"] == {} for spec in specs)


def test_stamp_without_compiled_policy_touches_nothing() -> None:
    """Zero-config invariant: no compiled policy ⇒ the specs stay byte-identical
    (no interrupt_on key ever appears)."""
    specs = [{"name": "drafter", "description": "d", "system_prompt": "p"}]
    before = [dict(spec) for spec in specs]
    stamp_subagent_opt_out(specs, None)
    assert specs == before
    assert "interrupt_on" not in specs[0]


# --- INTAKE-3 (ADR-F086): the code-enforced structural floor ------------------
#
# ``draft_email_reply`` is gated because it is OUTBOUND, not because an area
# configured it. These pin that the floor cannot be configured away AND that a run
# which was never granted the tool is byte-identical to the pre-slice behaviour.

_INTAKE_GRANTED = frozenset({"record_intake_outcome", "draft_email_reply", "read_document"})


def test_structural_floor_gates_outbound_tool_with_an_empty_policy() -> None:
    compiled = compile_hitl_policy({}, _INTAKE_GRANTED)
    assert compiled is not None
    assert set(compiled) == {"draft_email_reply"}
    # ADR-F087: the floor tool is the ONE editable one.
    assert compiled["draft_email_reply"]["allowed_decisions"] == ["approve", "edit", "reject"]


def test_policy_cannot_remove_the_structural_floor() -> None:
    """Neither a `false` entry (skipped as malformed) nor a policy that simply
    omits the tool can leave an outbound call ungated."""
    for policy in ({"draft_email_reply": False}, {"read_document": True}, {"nope": True}):
        compiled = compile_hitl_policy(dict(policy), _INTAKE_GRANTED)
        assert compiled is not None, policy
        assert "draft_email_reply" in compiled, policy


def test_structural_floor_survives_a_malformed_non_object_policy() -> None:
    compiled = compile_hitl_policy("not-a-dict", _INTAKE_GRANTED)  # type: ignore[arg-type]
    assert compiled is not None
    assert set(compiled) == {"draft_email_reply"}


def test_floor_does_not_gate_the_outcome_tool() -> None:
    """record_intake_outcome is NOT outbound — it stays ungated unless an area's
    policy asks for it (the ADR gates what LEAVES the system, not what files it)."""
    compiled = compile_hitl_policy({}, _INTAKE_GRANTED)
    assert compiled is not None
    assert "record_intake_outcome" not in compiled


def test_non_intake_runs_keep_the_zero_config_invariant() -> None:
    """A run that was never granted an outbound tool compiles to None exactly as
    before — the floor is grant-set-intersected, so nothing changes for it."""
    assert compile_hitl_policy({}, _GRANTED) is None
    assert compile_hitl_policy({"retired_tool": True}, _GRANTED) is None


def test_subagents_keep_the_structural_floor_but_lose_the_area_policy() -> None:
    """B2: clearing a subagent's interrupt_on outright handed a DELEGATED agent an
    ungated draft_email_reply — the one tool the injection backstop rests on. The
    AREA's entries still drop; the floor does not."""
    compiled = compile_hitl_policy({"read_document": True}, _INTAKE_GRANTED)
    assert compiled is not None
    assert set(compiled) == {"read_document", "draft_email_reply"}
    specs: list[dict[str, Any]] = [{"name": "clause-drafter"}, {"name": "clause-reviewer"}]
    stamp_subagent_opt_out(specs, compiled)
    for spec in specs:
        assert set(spec["interrupt_on"]) == {"draft_email_reply"}
        assert spec["interrupt_on"]["draft_email_reply"]["allowed_decisions"] == [
            "approve",
            "edit",
            "reject",
        ]
    # Each spec owns its dict — mutating one must not leak into the others.
    specs[0]["interrupt_on"].clear()
    assert set(specs[1]["interrupt_on"]) == {"draft_email_reply"}


def test_non_intake_subagents_are_still_fully_opted_out() -> None:
    """The pre-slice behaviour survives wherever no floor tool is granted."""
    compiled = compile_hitl_policy({"apply_redline": True}, _GRANTED)
    assert compiled is not None
    assert not (ALWAYS_INTERRUPT_TOOL_NAMES & _GRANTED)
    specs: list[dict[str, Any]] = [{"name": "document-researcher"}]
    stamp_subagent_opt_out(specs, compiled)
    assert specs[0]["interrupt_on"] == {}


# --- INTAKE-4b (ADR-F087): per-tool verbs + the resume endpoint's gate --------


def test_only_the_editable_tool_gets_the_edit_verb() -> None:
    assert {"draft_email_reply"} == EDITABLE_TOOL_NAMES
    # Editable ⊆ the structural floor: nothing is editable that is not gated.
    assert EDITABLE_TOOL_NAMES <= ALWAYS_INTERRUPT_TOOL_NAMES
    assert allowed_decisions_for("draft_email_reply") == ["approve", "edit", "reject"]
    assert allowed_decisions_for("apply_redline") == ["approve", "reject"]
    # `respond` is never offered — the UI's Respond is reject+message (ADR-F087).
    assert "respond" not in allowed_decisions_for("draft_email_reply")


def test_allowed_decisions_lists_are_fresh_per_call() -> None:
    """A compiled entry is handed to middleware and to the step digest; a shared
    list would let either mutate the module constant for the whole process."""
    first = allowed_decisions_for("draft_email_reply")
    first.append("respond")
    assert allowed_decisions_for("draft_email_reply") == ["approve", "edit", "reject"]


def _digest(*entries: dict[str, Any]) -> str:
    return json.dumps(list(entries), sort_keys=True)


def test_step_gate_reads_the_verbs_out_of_the_digest() -> None:
    summary = _digest(
        {
            "tool": "draft_email_reply",
            "args": {"body": "hi"},
            "allowed_decisions": ["approve", "edit", "reject"],
        }
    )
    assert decisions_allowed_for_step("draft_email_reply", summary) == {
        "approve",
        "edit",
        "reject",
    }


def test_step_gate_narrows_to_approve_reject_on_anything_it_cannot_read() -> None:
    """A missing, truncated, non-JSON, empty or odd-shaped digest may only ever
    NARROW the verbs — never widen them (the fail-closed direction)."""
    conservative = {"approve", "reject"}
    for summary in (
        None,
        "",
        '[{"tool": "draft_email_reply", "args": {"body": "Th',  # truncated
        "{}",
        "[]",
        '[{"args": {}}]',  # no tool name
        '[{"tool": "draft_email_reply", "args": {}}]',  # pre-F087: no verbs
        '[{"tool": "draft_email_reply", "allowed_decisions": []}]',
        '[{"tool": "draft_email_reply", "allowed_decisions": "edit"}]',
    ):
        assert decisions_allowed_for_step("draft_email_reply", summary) == conservative, summary


def test_step_gate_never_honours_edit_for_a_non_editable_tool() -> None:
    """A hand-edited (or drifted) digest claiming `edit` for another tool buys
    nothing: the tool NAME is authoritative over the stored list."""
    summary = _digest(
        {"tool": "apply_redline", "args": {}, "allowed_decisions": ["approve", "edit", "reject"]}
    )
    assert decisions_allowed_for_step("apply_redline", summary) == {"approve", "reject"}


def test_step_gate_intersects_across_a_multi_call_pause() -> None:
    """ONE decision is fanned across every gated call in the turn, so a verb has
    to be admissible for ALL of them."""
    summary = _digest(
        {
            "tool": "draft_email_reply",
            "args": {},
            "allowed_decisions": ["approve", "edit", "reject"],
        },
        {"tool": "apply_redline", "args": {}, "allowed_decisions": ["approve", "reject"]},
    )
    assert decisions_allowed_for_step("draft_email_reply", summary) == {"approve", "reject"}


def test_step_gate_distrusts_a_digest_that_disagrees_with_the_step_name() -> None:
    summary = _digest(
        {
            "tool": "draft_email_reply",
            "args": {},
            "allowed_decisions": ["approve", "edit", "reject"],
        }
    )
    assert decisions_allowed_for_step("apply_redline", summary) == {"approve", "reject"}
