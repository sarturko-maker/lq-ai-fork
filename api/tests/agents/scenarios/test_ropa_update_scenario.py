"""PRIV-8b — live ROPA *maintenance*: "we moved off Mixpanel, we use Hotjar now".

The maintainer's literal test of the product thesis (the group-chat ask): a lawyer
says, in plain language, that a tool has been replaced — and the register updates
itself, coherently. PRIV-8a gave the agent the change verbs (soft-retire + unlink,
ADR-F023); this proves the agent can *compose* them into a correct swap on a real
model, and measures whether the ``ropa-maintenance`` skill carries the method a
naive baseline lacks.

Unlike the population test this is NOT notice-gated — the starting register is
synthetic (``seed_ropa_register``: a "Product analytics" activity with a Mixpanel
vendor + system linked), so nothing third-party is involved. It IS provider-gated:

  * ``@pytest.mark.provider`` + ``LQ_AI_GATEWAY_KEY`` — skips without a live gateway.

Run live against the dev stack (the gateway reaches DeepSeek; the test DB is a
throwaway ``lq_ai_test_*`` the conftest migrates + drops):

    pytest -m provider tests/agents/scenarios/test_ropa_update_scenario.py -s -k skill

Per ADR-F015 this is NOT a model pass/fail gate: the hard asserts are only that
each run reached a terminal state and took a model turn. The real signal — did the
live register end up coherent (Hotjar in, Mixpanel gone-from-live but soft-retired
for audit)? — is scored by :func:`evaluate_swap` and written, verbatim, to
docs/fork/evidence/priv-8/.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.skills import load_registry
from tests.agents.scenarios.harness import Receipt, run_scenario, seed_matter
from tests.agents.scenarios.ropa_eval import (
    RegisterSnapshot,
    bind_area_skill,
    cleanup_register,
    evaluate_swap,
    seed_ropa_register,
    snapshot_register,
    unbind_area_skill,
)
from tests.agents.scenarios.scenarios import FixtureDocument, Scenario, build_document

# Per-run step ceiling. A coherent swap is orient (read/list) -> add x2 -> link x2
# -> unlink x2 -> retire x2 -> confirm -> report. First live arms (PRIV-8b, 2026-06-19)
# hit cap_exceeded at 40 with an empty final answer — the model spent early steps
# reading the matter note, then ran out before retiring + reporting. 80 gives a
# single-pass swap clear headroom; the 300s wall clock is the usual real limiter and
# the PRIV-7 recursion_limit fix (max(50, max_steps*4)) lets the budget be spent.
_SWAP_STEPS = 80

_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)
_ROPA_SKILL = "ropa-maintenance"

_EVIDENCE_DIR = (
    Path(os.environ["LQ_AI_PRIV8_EVIDENCE_DIR"])
    if os.environ.get("LQ_AI_PRIV8_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "priv-8"
)

_MATTER_NAME = "Product analytics — vendor change (PRIV-8b)"
_ACTIVITY = "Product analytics"
_OLD = "Mixpanel"
_NEW = "Hotjar"
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]


def _matter_note() -> FixtureDocument:
    """A synthetic internal note that sits in the matter (committable — not third-party).

    Mirrors the maintainer's "forward the email" idea: the change is also written
    down in a document the agent may consult. The prompt is self-contained, so the
    agent does not have to read it — but it can.
    """
    return build_document(
        "Analytics-vendor-change.txt",
        [
            (
                1,
                "Internal note — Product analytics tooling\n\n"
                "Engineering has migrated our product-analytics from Mixpanel to Hotjar, "
                "effective this month. We no longer send any product-usage data to Mixpanel; "
                "Hotjar (EU-hosted) is now the sole product-analytics processor. Please update "
                "the Record of Processing Activities so it reflects Hotjar in place of Mixpanel.",
            )
        ],
    )


# Naive ask, held constant across arms — exactly what a lawyer would type. The
# ropa-maintenance skill (when bound) supplies the method (add → link → unlink →
# retire → confirm; never leave both); the baseline shows whether the model gets
# there unaided. Isolating the skill is the point (PRIV-7 build-comparison shape).
_SWAP = Scenario(
    id="ropa_swap_mixpanel_hotjar",
    title="Swap — replace Mixpanel with Hotjar (the maintainer's literal test)",
    note=(
        "Plain-language maintenance ask. A coherent swap leaves the live register "
        "showing Hotjar where Mixpanel was, with Mixpanel gone-from-live but kept on "
        "record (soft-retired, ADR-F023) — never both."
    ),
    prompt=(
        "We've moved off Mixpanel — we use Hotjar now for our product analytics. "
        "Please update our Record of Processing Activities to reflect that, and tell "
        "me exactly what you changed."
    ),
    expect_tools=("propose_vendor",),
    step_bound=_SWAP_STEPS,
)

# (model_alias, bind ropa-maintenance?): flash baseline, flash+skill, pro+skill.
# Both skilled arms pass the registry, so the variables are the skill and the model.
_SWAP_CONFIGS: list[tuple[str, bool]] = [
    ("deepseek", False),
    ("deepseek", True),
    ("deepseek-pro", True),
]


def _swap_id(model_alias: str, use_skill: bool) -> str:
    return f"{model_alias}-{'skill' if use_skill else 'noskill'}"


def _write_swap_report(
    receipt: Receipt,
    before: RegisterSnapshot,
    after: RegisterSnapshot,
    verdict: dict[str, Any],
    out_dir: Path,
    *,
    model_alias: str,
    use_skill: bool,
) -> tuple[Path, Path]:
    """Write the PRIV-8b swap behavior report (JSON + Markdown).

    Observations + the agent's own structured output only — never a provider
    key/URL. The prompt and the matter note are synthetic (not third-party).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    payload = {
        "milestone": "PRIV-8b",
        "adr": "F023",
        "mode": f"swap · skill={'ropa-maintenance' if use_skill else 'off'}",
        "model_alias": model_alias,
        "model_note": (
            f"alias '{model_alias}' resolves via the gateway to a DeepSeek V4 model "
            "(deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). "
            "DeepSeek is NOT scenario-qualified (ADR-F015) — this run is kept verbatim, "
            "not tuned green."
        ),
        "scenario": {"activity": _ACTIVITY, "replaced": _OLD, "with": _NEW},
        "generated_at": stamp,
        "verdict": verdict,
        "register_before": before.to_dict(),
        "register_after": after.to_dict(),
        "run": receipt.to_dict(),
    }
    json_path = out_dir / "behavior-report.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path = out_dir / "behavior-report.md"
    md_path.write_text(_render_md(payload), encoding="utf-8")
    return json_path, md_path


def _render_md(payload: dict[str, Any]) -> str:
    v = payload["verdict"]
    r = payload["run"]
    s = payload["scenario"]
    headline = (
        "✅ coherent" if v["coherent"] else ("⚠️ lists BOTH" if v["lists_both"] else "✗ incomplete")
    )
    lines: list[str] = [
        f"# PRIV-8b — ROPA swap ({payload['mode']}) — {payload['model_alias']}",
        "",
        f"- **Model:** {payload['model_note']}",
        f'- **Change:** replace **{s["replaced"]}** with **{s["with"]}** on "{s["activity"]}"',
        f"- **Generated:** {payload['generated_at']}",
        "",
        "> The agent composed the PRIV-8a change verbs (soft-retire + unlink) from a "
        "plain-language ask. Every write is valid by construction (the guarded, "
        "code-validated path); this report measures whether the *live* register ended "
        "up coherent. Kept verbatim per ADR-F015 — a messy result is a finding, not a failure.",
        "",
        f"## Verdict: {headline}",
        "",
        f"- **Live register coherent** (new linked + live, old gone-from-live): "
        f"**{v['coherent']}**",
        f"- **Register lists BOTH** (the ADR-F023 failure mode): **{v['lists_both']}**",
        f"- **Old tool soft-retired** (kept on record for audit): **{v['old_soft_retired']}**",
        f"- **Old tool still on record** (never destroyed): **{v['old_still_on_record']}**",
        f"- **Whole activity retired** (would hide it from the live register): "
        f"**{v['activity_retired']}**",
        f"- **Duplicate names** (fidelity flag): {v['duplicate_names'] or '—'}",
        "",
        "| Axis | new linked+live | old linked | old retired | old live-visible |",
        "| --- | --- | --- | --- | --- |",
        f"| recipient (vendor) | {v['recipient']['new_live_visible']} | "
        f"{v['recipient']['old_linked']} | {v['recipient']['old_retired']} | "
        f"{v['recipient']['old_live_visible']} |",
        f"| system | {v['system']['new_live_visible']} | {v['system']['old_linked']} | "
        f"{v['system']['old_retired']} | {v['system']['old_live_visible']} |",
        "",
        "## Run",
        "",
        f"- **Status:** `{r['status']}` · **steps:** {r['step_count']} · "
        f"**model turns:** {r['model_turns']} · **latency:** {r['latency_s']}s",
        f"- **Tools called:** {', '.join(r['tools_called']) or '—'}",
        f"- **Final answer (excerpt):** {r['final_answer_excerpt'] or '—'}",
        "",
        "## Register before → after",
        "",
        f"- **before — recipients:** "
        f"{[a['recipients'] for a in payload['register_before']['activities']]}",
        f"- **before — systems:** "
        f"{[a['systems'] for a in payload['register_before']['activities']]}",
        f"- **after — recipients:** "
        f"{[a['recipients'] for a in payload['register_after']['activities']]}",
        f"- **after — systems:** {[a['systems'] for a in payload['register_after']['activities']]}",
        f"- **after — vendors (all, incl. retired):** {payload['register_after']['vendors']}",
        f"- **after — systems (all, incl. retired):** {payload['register_after']['systems']}",
        "",
    ]
    return "\n".join(lines)


@pytest.mark.parametrize(
    "model_alias,use_skill",
    _SWAP_CONFIGS,
    ids=[_swap_id(*cfg) for cfg in _SWAP_CONFIGS],
)
async def test_ropa_swap_mixpanel_to_hotjar(
    model_alias: str,
    use_skill: bool,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Seed Mixpanel → ask in plain language → assert the swap left the register coherent.

    Control (``use_skill=False``) runs with the area's default skills only; treatment
    binds ``ropa-maintenance`` test-only (no migration). The registry is always passed,
    so the variables are the skill and the model.
    """
    registry = load_registry(_SKILLS_DIR)
    seeded = await seed_matter(
        commit_factory, area_key="privacy", doc=_matter_note(), matter_name=_MATTER_NAME
    )
    await seed_ropa_register(commit_factory, source_project_id=seeded.project_id)
    if use_skill:
        await bind_area_skill(commit_factory, seeded.practice_area_id, _ROPA_SKILL)
    try:
        before = await snapshot_register(commit_factory, seeded.project_id)
        receipt = await run_scenario(
            _SWAP,
            seeded,
            skill_registry=registry,
            model_alias=model_alias,
            max_steps=_SWAP_STEPS,
        )
        after = await snapshot_register(commit_factory, seeded.project_id)
    finally:
        if use_skill:
            # Leave the shared (migration-seeded) practice area as we found it, so a
            # later parametrized control arm isn't contaminated.
            await unbind_area_skill(commit_factory, seeded.practice_area_id, _ROPA_SKILL)
        await cleanup_register(commit_factory, seeded.project_id)
        await seeded.cleanup()

    verdict = evaluate_swap(after, activity_name=_ACTIVITY, old_name=_OLD, new_name=_NEW)
    _write_swap_report(
        receipt,
        before,
        after,
        verdict,
        _EVIDENCE_DIR / f"swap-{_swap_id(model_alias, use_skill)}",
        model_alias=model_alias,
        use_skill=use_skill,
    )

    # Per ADR-F015: assert only that the run is honest (terminal + a model turn);
    # the swap's coherence is a recorded finding, not a pass/fail gate (the model is
    # not yet scenario-qualified and runs are non-deterministic).
    assert receipt.status in _TERMINAL, (receipt.scenario.id, receipt.status)
    assert receipt.model_turns > 0, "no model turn recorded"
