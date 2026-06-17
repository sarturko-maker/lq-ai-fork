"""Emit the committed behavior report (JSON + Markdown).

The report is the durable evidence artifact ADR-F015 requires: an honest
map of how the injected model (MiniMax-M3) behaves in the cockpit loop.
It carries OBSERVATIONS ONLY — tool names, step counts, statuses,
pass/fail, and a bounded answer excerpt. It never carries a provider
key, the gateway URL, env, or any raw secret-bearing payload.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tests.agents.scenarios.harness import Receipt


def _summary_counts(receipts: list[Receipt]) -> dict[str, int]:
    return {
        "scenarios": len(receipts),
        "shape_matched": sum(1 for r in receipts if r.checks.shape_matched),
        "completed": sum(1 for r in receipts if r.status == "completed"),
    }


def write_report(
    receipts: list[Receipt],
    out_dir: Path,
    *,
    model_alias: str,
    area: str = "commercial",
    milestone: str = "UX-B-1",
    generated_at: str | None = None,
) -> tuple[Path, Path]:
    """Write ``behavior-report.json`` + ``behavior-report.md`` to ``out_dir``.

    Returns the two paths. ``area``/``milestone`` default to the UX-B-1
    Commercial baseline; UX-B-2 passes the per-area values. ``generated_at``
    is injectable for determinism in tests; defaults to the current UTC time.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at or datetime.now(UTC).isoformat(timespec="seconds")
    counts = _summary_counts(receipts)

    payload = {
        "milestone": milestone,
        "adr": "F015",
        "area": area,
        "model_alias": model_alias,
        "model_note": (
            f"alias '{model_alias}' is expected to resolve to MiniMax-M3 (tier-4) "
            "via the gateway's operator-configured routing — the only S9-qualified "
            "provider today. The gateway owns the alias→model mapping; this report "
            "observes the loop's behaviour, not the resolved model name."
        ),
        "generated_at": stamp,
        "summary": counts,
        "results": [r.to_dict() for r in receipts],
    }
    json_path = out_dir / "behavior-report.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md_path = out_dir / "behavior-report.md"
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def _render_markdown(payload: dict) -> str:
    counts = payload["summary"]
    milestone = payload["milestone"]
    lines: list[str] = [
        f"# {milestone} — {payload['area']} scenario behavior report",
        "",
        f"- **Milestone:** {milestone} (gate: ADR-{payload['adr']})",
        f"- **Practice area:** {payload['area']}",
        f"- **Model:** {payload['model_note']}",
        f"- **Generated:** {payload['generated_at']}",
        f"- **Result:** {counts['shape_matched']}/{counts['scenarios']} scenarios "
        f"matched expected shape · {counts['completed']}/{counts['scenarios']} ran to `completed`",
        "",
        "> Per ADR-F015 a scenario that does not match its expected shape is a "
        "**finding** that calibrates the area profile / tier floor, not a test "
        "failure. The harness asserts only that every scenario produced a terminal "
        "run + receipts.",
        "",
        "> **Reading the checks:** the `shape_matched` verdict is a coarse heuristic "
        "(substring + step-bound matching) — the **final-answer excerpt is the "
        "authoritative record** of what the model did. A `refusal_ok=False` or "
        "`should_not_ok=False` can be a heuristic false-positive (e.g. a "
        "false-confirmation phrase appearing inside a *negated* sentence); read the "
        "excerpt before treating a finding as a model defect. Live runs are "
        "non-deterministic, so step counts / latencies / tool choices vary run to "
        "run — that variance is itself a tier-4 observation.",
        "",
        "## Summary",
        "",
        "| Scenario | Status | Shape | Tools called | Steps | Latency |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in payload["results"]:
        tools = ", ".join(r["tools_called"]) or "—"
        shape = "✅" if r["shape_matched"] else "⚠️ finding"
        lines.append(
            f"| {r['title']} | `{r['status']}` | {shape} | {tools} | "
            f"{r['step_count']} | {r['latency_s']}s |"
        )

    lines += ["", "## Per-scenario detail", ""]
    for r in payload["results"]:
        checks = r["checks"]
        lines += [
            f"### {r['title']} (`{r['id']}`)",
            "",
            f"_{r['note']}_",
            "",
            f"- **Prompt:** {r['prompt']}",
            f"- **Status:** `{r['status']}`" + (f" · error: `{r['error']}`" if r["error"] else ""),
            f"- **Tools called:** {', '.join(r['tools_called']) or '—'}  "
            f"(expected: {', '.join(r['expect_tools']) or '—'}; "
            f"forbidden: {', '.join(r['forbid_tools']) or '—'})",
            f"- **Steps:** {r['step_count']} · model turns: {r['model_turns']} · "
            f"latency: {r['latency_s']}s",
            f"- **Delegation:** {r.get('task_calls', 0)} `task` call(s) · "
            f"delegated={r.get('delegated', False)}"
            + (f" · ancestry: {r['ancestry']}" if r.get("ancestry") else ""),
            "- **Checks:** "
            + ", ".join(f"{name}={value}" for name, value in checks.items() if value is not None),
            "",
            "**Final answer (excerpt):**",
            "",
            "```",
            r["final_answer_excerpt"] or "(no final answer)",
            "```",
            "",
        ]
    return "\n".join(lines)
