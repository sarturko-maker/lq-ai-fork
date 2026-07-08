"""HITL policy compiler — HITL-1 (ADR-F071).

Compiles a practice area's stored ``hitl_policy`` (JSONB, ``{"<tool name>": true}``)
into the ``interrupt_on`` mapping deepagents feeds langchain's
``HumanInTheLoopMiddleware``. One pure function, called from the composition point
AFTER the run's final tool list exists, so the compiled policy is always
policy ∩ the run's ACTUAL grant set:

* Names outside the grant set drop with a structured warning (a stale policy can
  never brick a run; deepagents builtins like ``task``/``read_file`` are never in
  the grant set, so they are structurally ungateable — ADR-F071).
* Malformed entries (key not a str, value not exactly ``true``) skip with a
  structured warning carrying the tool NAME only — never values.
* An empty result compiles to ``None``: the caller then never sets the
  ``interrupt_on`` kwarg, no HITL middleware attaches, and the agent graph is
  byte-identical to an unconfigured area's (the zero-config invariant, ADR-F071).

The pause description is FORK-authored (a plain static string per tool) — never
model, skill, or document text; the pending call's args ride the interrupt payload
and the ``hitl_request`` step row as data, not as prose (ADR-F071).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

# Decisions allowed in v1 (ADR-F071): approve / reject only. `edit` and `respond`
# would break "what you saw is what runs" until arg-diff review UX exists.
_ALLOWED_DECISIONS = ["approve", "reject"]


def _describe(tool_name: str) -> str:
    """The fork-authored ask shown to the human (R3) — static, never model text."""
    return f"The agent wants to run {tool_name} and is waiting for your go-ahead."


def compile_hitl_policy(policy: dict[Any, Any], granted: frozenset[str]) -> dict[str, Any] | None:
    """Compile a stored ``hitl_policy`` into deepagents' ``interrupt_on`` shape.

    Returns ``None`` when nothing compiles (empty policy, or every entry dropped/
    skipped) — the caller must then leave the ``interrupt_on`` kwarg unset entirely
    (zero-config invariant, ADR-F071). Each surviving entry maps to an
    ``InterruptOnConfig``-shaped dict: ``allowed_decisions=["approve", "reject"]``
    plus the fork-authored description.
    """
    if not isinstance(policy, dict):
        # The column has no DB CHECK and is dict-typed only at the ORM boundary;
        # a non-object value (plantable today only by out-of-band SQL) must degrade,
        # not raise (R2: a malformed policy never bricks a run — ADR-F071).
        logger.warning(
            "hitl_policy ignored: stored value is not an object",
            extra={"event": "hitl_policy_not_object", "value_type": type(policy).__name__},
        )
        return None
    compiled: dict[str, Any] = {}
    for name, value in policy.items():
        if not isinstance(name, str):
            logger.warning(
                "hitl_policy entry skipped: key is not a string",
                extra={"event": "hitl_policy_entry_skipped", "key_type": type(name).__name__},
            )
            continue
        if value is not True:
            # v1 stores exactly `true` per tool (R2); anything else is malformed —
            # skip (name only, never the value) rather than brick the run.
            logger.warning(
                "hitl_policy entry skipped: value is not `true`",
                extra={"event": "hitl_policy_entry_skipped", "tool": name},
            )
            continue
        if name not in granted:
            logger.warning(
                "hitl_policy name dropped: not in the run's grant set",
                extra={"event": "hitl_policy_name_dropped", "tool": name},
            )
            continue
        compiled[name] = {
            "allowed_decisions": list(_ALLOWED_DECISIONS),
            "description": _describe(name),
        }
    return compiled or None


def stamp_subagent_opt_out(
    subagents: Sequence[dict[str, Any]], compiled: dict[str, Any] | None
) -> None:
    """Opt every fork-authored subagent spec out of a compiled policy (ADR-F071).

    LEAD-only scope in v1: spec-level ``interrupt_on={}`` suppresses deepagents'
    inheritance of the top-level policy. No-op when nothing compiled — the
    zero-config invariant requires the specs untouched (byte-identical graph).
    The deepagents auto-added "general-purpose" subagent has no spec here and
    still INHERITS the policy — accepted (it closes the ``task``-delegation
    bypass for lead-granted tools; ADR-F071).
    """
    if compiled is None:
        return
    for spec in subagents:
        spec["interrupt_on"] = {}
