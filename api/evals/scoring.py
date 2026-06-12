"""Deterministic L0/L1 scorers over settled ``agent_run_steps`` rows.

Plain Python, zero LLM calls (oscar's masked-judge insight: "did tool X
fire with arg Y" needs no judge — a programmatic extractor is
doctrine-masked by construction). Metric kinds are declared in the
scenario JSONs (``api/evals/scenarios/``); this module interprets them.

Tool identification is STRUCTURAL — the runner persisted a
``tool_call`` row when the loop dispatched a tool — never regex over
model text (oscar's ``[TOOL_CALL]`` pseudo-call lesson).
"""

from __future__ import annotations

from typing import Any


def _tool_calls(steps: list[dict[str, Any]], tool: str) -> list[dict[str, Any]]:
    return [s for s in steps if s.get("kind") == "tool_call" and s.get("name") == tool]


def _contains(haystack: str | None, fragment: str) -> bool:
    return fragment.casefold() in (haystack or "").casefold()


def score_metric(spec: dict[str, Any], steps: list[dict[str, Any]], answer: str | None) -> Any:
    """One metric value: bool for gates, str for enums, None for n/a."""
    kind = spec["kind"]

    if kind == "tool_fired":
        fired = len(_tool_calls(steps, spec["tool"]))
        return fired >= int(spec.get("min_count", 1))

    if kind == "tool_fired_any":
        fired = sum(len(_tool_calls(steps, tool)) for tool in spec["tools"])
        return fired >= int(spec.get("min_count", 1))

    if kind == "tool_not_fired":
        return len(_tool_calls(steps, spec["tool"])) == 0

    if kind == "tool_arg_contains":
        calls = _tool_calls(steps, spec["tool"])
        if not calls and spec.get("only_if_fired"):
            return None  # n/a — the paired *_fired metric carries the miss
        return any(_contains(c.get("summary"), spec["fragment"]) for c in calls)

    if kind == "answer_contains_any":
        return any(_contains(answer, f) for f in spec["fragments"])

    if kind == "answer_contains_all_groups":
        return all(any(_contains(answer, v) for v in group) for group in spec["groups"])

    if kind == "answer_not_contains_any":
        return not any(_contains(answer, f) for f in spec["fragments"])

    if kind == "task_strategy":
        # oscar's fan-out strategy enum: one_per_item | partition | none.
        # one_per_item = at least one task per item AND every item named
        # in some task's args digest; partition = ≥2 tasks but not fully
        # itemized; none = 0-1 tasks (no real fan-out).
        items: list[str] = spec["item_fragments"]
        calls = _tool_calls(steps, "task")
        matched = {item for item in items if any(_contains(c.get("summary"), item) for c in calls)}
        if len(calls) >= len(items) and len(matched) == len(items):
            return "one_per_item"
        if len(calls) >= 2:
            return "partition"
        return "none"

    raise ValueError(f"unknown metric kind {kind!r}")


def score_all(
    metrics_spec: dict[str, dict[str, Any]],
    steps: list[dict[str, Any]],
    answer: str | None,
) -> dict[str, Any]:
    return {name: score_metric(spec, steps, answer) for name, spec in metrics_spec.items()}
