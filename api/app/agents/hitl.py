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
* INTAKE-4b (ADR-F087, amending F071) makes ``allowed_decisions`` PER TOOL: the one
  editable tool (:data:`EDITABLE_TOOL_NAMES`) admits ``edit`` as well, because its
  arguments are the artefact the lawyer is reviewing. The compiled list rides the
  interrupt payload, the ``hitl_request`` digest and the SSE frame, so the cockpit
  offers exactly the verbs the resume endpoint will accept
  (:func:`decisions_allowed_for_step` is that endpoint's gate).
* INTAKE-3 (ADR-F086) adds a code-enforced FLOOR on top of the policy:
  :data:`ALWAYS_INTERRUPT_TOOL_NAMES` — outbound tools — are gated whenever the run
  was granted them, whatever the policy says (or does not say). Structural, not
  policy: the prompt-injection backstop cannot be configured away.

The pause description is FORK-authored (a plain static string per tool) — never
model, skill, or document text; the pending call's args ride the interrupt payload
and the ``hitl_request`` step row as data, not as prose (ADR-F071).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from typing import Any

logger = logging.getLogger(__name__)

# Decisions allowed for an ORDINARY gated tool (ADR-F071): approve / reject only.
# `edit` on an arbitrary tool is a licence to rewrite structured arguments the human
# never sees rendered, and langchain's native `respond` fabricates a success-shaped
# tool result — both break "what you saw is what runs".
_ALLOWED_DECISIONS = ["approve", "reject"]

# INTAKE-4b (ADR-F087, amends F071): the ONE exception. ``draft_email_reply``'s
# arguments ARE the artefact under review — prose a lawyer is qualified to rewrite —
# and its execution is the send, so "approve or refuse" makes review a rubber stamp.
# Nothing else is editable; adding a name here is a deliberate decision, never a
# default, and the resume endpoint refuses an ``edit`` for anything outside this set.
EDITABLE_TOOL_NAMES = frozenset({"draft_email_reply"})
_EDITABLE_DECISIONS = ["approve", "edit", "reject"]


#: The order the cockpit offers the verbs in. A ``frozenset`` from
#: :func:`decisions_allowed_for_step` has no order, and a read API that hands the UI
#: a differently-shuffled list on every request would make the card's buttons move.
DECISION_ORDER = ("approve", "edit", "reject")


def order_decisions(decisions: Iterable[str]) -> list[str]:
    """Sort decision verbs into :data:`DECISION_ORDER`; unknown verbs sort last, by name."""
    return sorted(
        decisions,
        key=lambda d: (
            DECISION_ORDER.index(d) if d in DECISION_ORDER else len(DECISION_ORDER),
            d,
        ),
    )


def allowed_decisions_for(tool_name: str) -> list[str]:
    """The decision verbs this tool's pause accepts (ADR-F087).

    A FRESH list per call: a compiled policy entry is handed to middleware and to
    the step digest, and a shared list would let either alias (and mutate) the
    module constants. ``respond`` is deliberately absent everywhere — the UI's
    "Respond" is ``reject`` + ``message`` (ADR-F087).
    """
    if tool_name in EDITABLE_TOOL_NAMES:
        return list(_EDITABLE_DECISIONS)
    return list(_ALLOWED_DECISIONS)


# INTAKE-3 (ADR-F086): the STRUCTURAL HITL floor — not policy. Every outbound tool
# is interrupt-gated whenever it is granted, regardless of (and unremovable by) the
# area's stored ``hitl_policy``, including an empty or absent one. This is the
# prompt-injection backstop the ADR names: "the safety line is structural, not
# policy … no category mechanism exists that could unlock auto-send", so nothing an
# email says and no admin misconfiguration can let a reply leave without a human.
# Names here are unioned into the compiled policy iff they are in the run's grant
# set — an ungranted name still compiles to nothing (the zero-config invariant holds
# byte-identically for every non-intake run).
ALWAYS_INTERRUPT_TOOL_NAMES = frozenset({"draft_email_reply"})


def _describe(tool_name: str) -> str:
    """The fork-authored ask shown to the human (R3) — static, never model text."""
    return f"The agent wants to run {tool_name} and is waiting for your go-ahead."


def compile_hitl_policy(policy: dict[Any, Any], granted: frozenset[str]) -> dict[str, Any] | None:
    """Compile a stored ``hitl_policy`` into deepagents' ``interrupt_on`` shape.

    Returns ``None`` when nothing compiles (empty policy, or every entry dropped/
    skipped) — the caller must then leave the ``interrupt_on`` kwarg unset entirely
    (zero-config invariant, ADR-F071). Each surviving entry maps to an
    ``InterruptOnConfig``-shaped dict: :func:`allowed_decisions_for` (approve/reject —
    plus ``edit`` for the one editable tool, ADR-F087) and the fork-authored
    description.
    """
    compiled: dict[str, Any] = {}
    if not isinstance(policy, dict):
        # The column has no DB CHECK and is dict-typed only at the ORM boundary;
        # a non-object value (plantable today only by out-of-band SQL) must degrade,
        # not raise (R2: a malformed policy never bricks a run — ADR-F071). It must
        # NOT, however, drop the structural floor below (ADR-F086).
        logger.warning(
            "hitl_policy ignored: stored value is not an object",
            extra={"event": "hitl_policy_not_object", "value_type": type(policy).__name__},
        )
        return _with_structural_floor(compiled, granted)
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
            "allowed_decisions": allowed_decisions_for(name),
            "description": _describe(name),
        }
    return _with_structural_floor(compiled, granted)


def _with_structural_floor(
    compiled: dict[str, Any], granted: frozenset[str]
) -> dict[str, Any] | None:
    """Union the code-enforced floor into a compiled policy (ADR-F086, INTAKE-3).

    Structural, not policy: an outbound tool the run was GRANTED is gated whether or
    not the area's JSONB names it, and the policy cannot remove it (a stored
    ``{"draft_email_reply": false}`` is already skipped as malformed, and even a
    hostile value cannot delete the key added here — the floor is applied last).
    A run that was granted none of these names is untouched, so the zero-config
    invariant (``None`` when nothing compiles) is byte-identical for every
    non-intake run.
    """
    for name in sorted(ALWAYS_INTERRUPT_TOOL_NAMES & granted):
        compiled[name] = {
            "allowed_decisions": allowed_decisions_for(name),
            "description": _describe(name),
        }
    return compiled or None


def decisions_allowed_for_step(step_name: str | None, summary: str | None) -> frozenset[str]:
    """Which decision verbs the persisted ``hitl_request`` step admits (ADR-F087).

    The resume endpoint's gate. The runner writes the digest as
    ``json.dumps([{"tool", "args", "allowed_decisions"}, …])``; ONE human decision is
    fanned across every gated call in the paused turn, so the answer is the
    INTERSECTION over the entries.

    DEFENSIVE, and deliberately asymmetric: anything that does not parse into a
    non-empty list of well-formed entries — a truncated digest, a pre-F087 row, a
    hand-edited one — falls back to the conservative :data:`_ALLOWED_DECISIONS` pair.
    A malformed digest can therefore only ever NARROW the verbs, never widen them;
    the runner's own name check (``_build_resume_command``) is the second gate.
    """
    conservative = frozenset(_ALLOWED_DECISIONS)
    if not summary:
        return conservative
    try:
        parsed = json.loads(summary)
    except (TypeError, ValueError):
        return conservative
    if not isinstance(parsed, list) or not parsed:
        return conservative
    allowed: set[str] | None = None
    for entry in parsed:
        if not isinstance(entry, dict) or not isinstance(entry.get("tool"), str):
            return conservative
        decisions = entry.get("allowed_decisions")
        if not isinstance(decisions, list) or not decisions:
            return conservative
        names = {d for d in decisions if isinstance(d, str)}
        # The tool name is authoritative over the digest's own list: a row whose
        # entry claims `edit` for a non-editable tool is not honoured.
        names &= set(allowed_decisions_for(entry["tool"]))
        allowed = names if allowed is None else (allowed & names)
    if not allowed:
        return conservative
    if step_name is not None and step_name not in {e.get("tool") for e in parsed}:
        # The step's own `name` column disagrees with its digest — trust neither.
        return conservative
    return frozenset(allowed)


def tool_names_for_step(step_name: str | None, summary: str | None) -> list[str]:
    """Which tools the persisted ``hitl_request`` step is asking about (INTAKE-5a).

    Read-only companion to :func:`decisions_allowed_for_step`, over the same digest
    (``json.dumps([{"tool", "args", "allowed_decisions"}, …])`` — the runner writes it):
    the Inbox says "needs your decision on draft_email_reply" without loading the
    checkpoint. Same defensive posture — a truncated, malformed or pre-F087 digest
    degrades to the step's own ``name`` column (or an empty list), never raises, and
    never widens anything: this list is display copy, and the resume endpoint's gate
    is :func:`decisions_allowed_for_step`, not this.

    Order is the digest's own (the order the model asked), de-duplicated.
    """
    names: list[str] = []
    if summary:
        try:
            parsed = json.loads(summary)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            for entry in parsed:
                if isinstance(entry, dict) and isinstance(entry.get("tool"), str):
                    tool = entry["tool"]
                    if tool not in names:
                        names.append(tool)
    if not names and step_name is not None:
        names = [step_name]
    return names


def stamp_subagent_opt_out(
    subagents: Sequence[dict[str, Any]], compiled: dict[str, Any] | None
) -> None:
    """Opt every fork-authored subagent spec out of a compiled policy — EXCEPT the
    structural floor (ADR-F071 + ADR-F086).

    LEAD-only scope in v1: spec-level ``interrupt_on`` suppresses deepagents'
    inheritance of the top-level policy. Clearing it OUTRIGHT would have handed a
    delegated subagent an ungated ``draft_email_reply`` — the outbound tool the whole
    injection backstop rests on (adversarial review B2). So the AREA's policy entries
    are still dropped, but every name in :data:`ALWAYS_INTERRUPT_TOOL_NAMES` that
    actually compiled is carried into each spec: the floor is structural, and
    delegation is not a way around it.

    No-op when nothing compiled — the zero-config invariant requires the specs
    untouched (byte-identical graph), and a non-intake run compiles no floor, so its
    specs still receive exactly ``{}``. The deepagents auto-added "general-purpose"
    subagent has no spec here and still INHERITS the full policy — accepted (it closes
    the ``task``-delegation bypass for lead-granted tools; ADR-F071).
    """
    if compiled is None:
        return
    floor = {
        name: config for name, config in compiled.items() if name in ALWAYS_INTERRUPT_TOOL_NAMES
    }
    for spec in subagents:
        spec["interrupt_on"] = dict(floor)
