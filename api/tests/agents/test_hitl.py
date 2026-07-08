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

import logging
from typing import Any

from app.agents.hitl import compile_hitl_policy, stamp_subagent_opt_out

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
    # v1 decisions are EXACTLY approve/reject — edit/respond are named non-goals.
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
