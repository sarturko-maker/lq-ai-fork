"""Aggregate cycle JSONs into the qualification matrix (markdown).

    python -m evals.report <results_dir> [> matrix.md]

Per (scenario x model) cell: each metric as fired/valid fractions,
strategy distribution for enums, plus cost/latency telemetry. Small-N
caveats are printed next to every cell (oscar's rule: never quote a
rate without its N; CI half-widths ±43pp at N=5, ±29pp at N=10).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_records(results_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text())
        for path in sorted(results_dir.glob("*.json"))
        if path.name != "manifest.json"
    ]


def _fraction(metric_values: list[Any]) -> str:
    judged = [v for v in metric_values if isinstance(v, bool)]
    not_applicable = sum(1 for v in metric_values if v is None)
    if not judged:
        return "n/a"
    suffix = f" (n/a: {not_applicable})" if not_applicable else ""
    return f"{sum(judged)}/{len(judged)}{suffix}"


def _enum_distribution(metric_values: list[Any]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for v in metric_values:
        if isinstance(v, str):
            counts[v] += 1
    return ", ".join(f"{k}:{n}" for k, n in sorted(counts.items())) or "n/a"


def render(results_dir: Path) -> str:
    records = load_records(results_dir)
    manifest_path = results_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        cells[(r["scenario_id"], r["model_alias"])].append(r)

    lines = [
        "# F0-S9 qualification results",
        "",
        f"- git: `{manifest.get('git_sha', 'unknown')}` · instruction sha: "
        f"`{manifest.get('instruction_sha', 'unknown')[:16]}…`",
        f"- cycles on disk: {len(records)}",
        "",
    ]
    total_cost = 0.0
    total_in = total_out = 0
    for (scenario_id, model_alias), cycle_records in sorted(cells.items()):
        valid = [r for r in cycle_records if r.get("valid")]
        completed = [r for r in valid if r.get("status") == "completed"]
        n = len(cycle_records)
        lines.append(f"## {scenario_id} x {model_alias} (N={n})")
        lines.append("")
        lines.append(
            f"- valid cycles: {len(valid)}/{n} · completed: {len(completed)}/{n}"
            + (" · statuses: " + ", ".join(sorted({r.get("status", "?") for r in cycle_records})))
        )
        metric_names: list[str] = []
        for r in valid:
            for name in r.get("metrics", {}):
                if name not in metric_names:
                    metric_names.append(name)
        lines.append("")
        lines.append("| metric | result |")
        lines.append("|---|---|")
        for name in metric_names:
            values = [r["metrics"].get(name) for r in valid]
            if any(isinstance(v, str) for v in values):
                lines.append(f"| {name} | {_enum_distribution(values)} |")
            else:
                lines.append(f"| {name} | {_fraction(values)} |")
        durations = [r["duration_s"] for r in cycle_records if r.get("duration_s")]
        cost = sum(r.get("cost_usd_estimate") or 0 for r in cycle_records)
        tokens_in = sum(r.get("tokens_in") or 0 for r in cycle_records)
        tokens_out = sum(r.get("tokens_out") or 0 for r in cycle_records)
        total_cost += cost
        total_in += tokens_in
        total_out += tokens_out
        lines.append("")
        lines.append(
            f"- telemetry: {tokens_in:,} in / {tokens_out:,} out tokens · "
            f"~${cost:.4f} · duration {min(durations or [0]):.0f}-{max(durations or [0]):.0f}s"
        )
        errored = [r for r in cycle_records if r.get("status") in ("failed", "cap_exceeded")]
        for r in errored:
            lines.append(
                f"- {r['status']} cycle c{r['cycle']:02d}: `{(r.get('error') or '')[:160]}`"
            )
        lines.append("")
    lines.append(
        f"**Session totals: {total_in:,} in / {total_out:,} out tokens · ~${total_cost:.4f}** "
        "(MiniMax standard rates $0.60/$2.40 per MTok — upper bound; launch promo is half)"
    )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("evals/out")
    print(render(target))
