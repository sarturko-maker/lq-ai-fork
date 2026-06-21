"""PRIV-A2/A3 — live assessment build: "run a DPIA for this and complete it".

The proof deferred since PRIV-A2: that the assessment WRITE loop works end to end
on a REAL model, not a scripted one. A lawyer asks, in plain language, for a DPIA
on a new piece of processing; the Privacy agent composes the assessment tools
(propose_assessment → link_assessment_to_activity → add_risk → complete_assessment),
code-validated at every step (ADR-F018), and lands a coherent, completed assessment
in the deployment-global register (ADR-F019) — satisfying the ADR-F027 completion
invariant (a DPIA cannot complete without a documented mitigation).

Like the PRIV-8b swap test this is NOT third-party-gated — the processing is a
synthetic internal note and the link target is a synthetic seeded register
(``seed_ropa_register``: a "Product analytics" activity). It IS provider-gated:

  * ``@pytest.mark.provider`` + ``LQ_AI_GATEWAY_KEY`` — skips without a live gateway.

Run live against the dev stack (the gateway reaches DeepSeek; the test DB is a
throwaway ``lq_ai_test_*`` the conftest migrates + drops):

    pytest -m provider tests/agents/scenarios/test_assessment_build_scenario.py -s -k skill

Per ADR-F015 this is NOT a model pass/fail gate: the hard asserts are only that
each run reached a terminal state and took a model turn. The real signal — did the
agent build a defensible, completed DPIA with documented mitigations, linked to the
activity? — is scored by :func:`score_assessment` and written, verbatim, to
docs/fork/evidence/priv-a2/.
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
from tests.agents.scenarios.assessment_eval import (
    AssessmentSnapshot,
    cleanup_assessment,
    score_assessment,
    snapshot_assessment,
)
from tests.agents.scenarios.harness import Receipt, run_scenario, seed_matter
from tests.agents.scenarios.ropa_eval import (
    bind_area_skill,
    cleanup_register,
    seed_ropa_register,
    unbind_area_skill,
)
from tests.agents.scenarios.scenarios import FixtureDocument, Scenario, build_document

# Per-run step ceiling = the production cockpit ceiling (ADR-F026: max_steps le=100).
# A coherent DPIA build is orient (list activities) → propose → link → add_risk x2-3
# → complete → report. The first live arms (2026-06-20) at 80 reached `cap_exceeded`
# AFTER completing the assessment but BEFORE reporting back (empty final answer) — the
# real DPIA was built and coherent, only the summary was cut. 100 (the ceiling a real
# cockpit run gets) gives the report-back headroom; the 300s wall clock is the usual
# real limiter and the recursion_limit fix (max(50, max_steps*4)) lets it be spent.
_BUILD_STEPS = 100

_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)
_ASSESSMENT_SKILL = "pia-generation"

_EVIDENCE_DIR = (
    Path(os.environ["LQ_AI_PRIVA2_EVIDENCE_DIR"])
    if os.environ.get("LQ_AI_PRIVA2_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "priv-a2"
)

_MATTER_NAME = "Product analytics — AI profiling DPIA (PRIV-A2)"
_ACTIVITY = "Product analytics"
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]


def _matter_note() -> FixtureDocument:
    """A synthetic internal note describing DPIA-worthy processing (committable).

    The processing is deliberately high-risk on the EDPB criteria (AI + systematic
    profiling of individuals with effects on the service they are offered), so a
    DPIA is the right call and the completion rule (a documented mitigation) bites.
    The prompt is self-contained; the agent may also read this note.
    """
    return build_document(
        "AI-analytics-profiling-note.txt",
        [
            (
                1,
                "Internal note — new AI profiling layer on Product analytics\n\n"
                "We are adding an AI model to our existing Product analytics that profiles "
                "individual users from their in-app behaviour to predict churn and to decide "
                "which retention offers and pricing each user is shown. It runs on the whole "
                "customer base, combines behavioural events with account and demographic data, "
                "and its scores influence what the user is offered — an automated decision with "
                "a real effect on individuals. Please assess this before launch.",
            )
        ],
    )


# Naive plain-language ask, held constant across arms — what a lawyer would type.
# The pia-generation skill (when bound) supplies the method (scope → link → risks
# with design-tied mitigations → complete only when the high-risk rule is met); the
# baseline shows whether the model gets there unaided. Isolating the skill is the
# point (the PRIV-7/8b build-comparison shape).
_BUILD = Scenario(
    id="assessment_build_ai_profiling_dpia",
    title="Build — run a DPIA for the AI profiling layer and complete it",
    note=(
        "Plain-language assessment ask on clearly high-risk processing. A defensible "
        "result is a completed DPIA, linked to the Product analytics activity, with "
        "concrete risks to individuals and at least one documented (design-tied) "
        "mitigation — the ADR-F027 completion rule satisfied."
    ),
    prompt=(
        "We're launching an AI layer on our product analytics that profiles individual "
        "users to predict churn and decide which retention offers and pricing each person "
        "sees. Please run a DPIA for this: link it to the relevant activity in our Record "
        "of Processing Activities, set out the key risks to individuals with concrete "
        "mitigations, and complete it with an overall risk rating. Tell me what you recorded."
    ),
    expect_tools=("propose_assessment",),
    step_bound=_BUILD_STEPS,
)

# (model_alias, bind pia-generation?): flash baseline, flash+skill, pro+skill.
# Both skilled arms pass the registry, so the variables are the skill and the model.
_BUILD_CONFIGS: list[tuple[str, bool]] = [
    ("deepseek", False),
    ("deepseek", True),
    ("deepseek-pro", True),
]


def _build_id(model_alias: str, use_skill: bool) -> str:
    return f"{model_alias}-{'skill' if use_skill else 'noskill'}"


def _write_build_report(
    receipt: Receipt,
    snapshot: AssessmentSnapshot,
    score: dict[str, Any],
    out_dir: Path,
    *,
    model_alias: str,
    use_skill: bool,
) -> tuple[Path, Path]:
    """Write the PRIV-A2 assessment-build behavior report (JSON + Markdown).

    Observations + the agent's own structured output only — never a provider
    key/URL. The prompt and the matter note are synthetic (not third-party).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    payload = {
        "milestone": "PRIV-A2",
        "adr": "F018/F027",
        "mode": f"build · skill={'pia-generation' if use_skill else 'off'}",
        "model_alias": model_alias,
        "model_note": (
            f"alias '{model_alias}' resolves via the gateway to a DeepSeek V4 model "
            "(deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). "
            "DeepSeek is NOT scenario-qualified (ADR-F015) — this run is kept verbatim, "
            "not tuned green."
        ),
        "generated_at": stamp,
        "score": score,
        "assessments": snapshot.to_dict(),
        "run": receipt.to_dict(),
    }
    json_path = out_dir / "behavior-report.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path = out_dir / "behavior-report.md"
    md_path.write_text(_render_md(payload), encoding="utf-8")
    return json_path, md_path


def _render_md(payload: dict[str, Any]) -> str:
    score = payload["score"]
    r = payload["run"]
    counts = score["counts"]
    completed = counts["completed"]
    integrity = score["completion_integrity_ok"]
    headline = (
        f"✅ {completed} completed, integrity OK"
        if completed and integrity
        else ("⚠️ integrity VIOLATED" if not integrity else "✗ none completed")
    )
    lines: list[str] = [
        f"# PRIV-A2 — assessment build ({payload['mode']}) — {payload['model_alias']}",
        "",
        f"- **Model:** {payload['model_note']}",
        f"- **Generated:** {payload['generated_at']}",
        "",
        "> The agent composed the assessment tools (propose → link → add_risk → complete) "
        "from a plain-language ask. Every write is valid by construction (the guarded, "
        "code-validated path, ADR-F018); this report measures whether the agent built a "
        "defensible, completed DPIA. Kept verbatim per ADR-F015 — a thin result is a "
        "finding, not a failure.",
        "",
        f"## Verdict: {headline}",
        "",
        f"- **Assessments:** {counts['assessments']} "
        f"(by type: {counts['by_type'] or '—'}; by status: {counts['by_status'] or '—'})",
        f"- **Completed:** {completed}",
        f"- **Completion-rule integrity** (every completed DPIA/high has a documented "
        f"mitigation, ADR-F027): **{integrity}**",
        f"- **Total risks:** {counts['total_risks']} "
        f"(with documented mitigation: {counts['risks_with_documented_mitigation']})",
        f"- **Assessments linked to an activity:** "
        f"{score['fractions']['assessments_linked_to_activity']}",
        f"- **Risks with documented mitigation:** "
        f"{score['fractions']['risks_with_documented_mitigation']}",
        "",
        "## Per assessment",
        "",
        "| Title | type | status | rating | risks | mitigated | linked | rule ok |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for a in score["per_assessment"]:
        lines.append(
            f"| {a['title']} | {a['type']} | {a['status']} | {a['risk_rating'] or '—'} | "
            f"{a['risk_count']} | {a['risks_with_documented_mitigation']} | "
            f"{a['linked_activity_count']} | {a['completion_rule_satisfied']} |"
        )
    lines += [
        "",
        "## Risks recorded (agent's own text, excerpted)",
        "",
    ]
    for a in payload["assessments"]["assessments"]:
        lines.append(f"**{a['title']}** ({a['type']}, {a['status']}, rating={a['risk_rating']}):")
        if a["risks"]:
            for risk in a["risks"]:
                lines.append(
                    f"- _{risk['likelihood']}x{risk['impact']}, {risk['status']}_ — "
                    f"{risk['description']}  \n  ↳ mitigation: {risk['mitigation'] or '—'}"
                )
        else:
            lines.append("- (no risks recorded)")
        lines.append("")
    lines += [
        "## Run",
        "",
        f"- **Status:** `{r['status']}` · **steps:** {r['step_count']} · "
        f"**model turns:** {r['model_turns']} · **latency:** {r['latency_s']}s",
        f"- **Tools called:** {', '.join(r['tools_called']) or '—'}",
        f"- **Final answer (excerpt):** {r['final_answer_excerpt'] or '—'}",
        "",
    ]
    return "\n".join(lines)


@pytest.mark.parametrize(
    "model_alias,use_skill",
    _BUILD_CONFIGS,
    ids=[_build_id(*cfg) for cfg in _BUILD_CONFIGS],
)
async def test_assessment_build_dpia(
    model_alias: str,
    use_skill: bool,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ask in plain language → assert the agent built+completed a coherent DPIA.

    Control (``use_skill=False``) runs with the area's default skills only; treatment
    binds ``pia-generation`` test-only (no migration). The registry is always passed,
    so the variables are the skill and the model. The Product-analytics activity is
    seeded so the agent has a real ROPA target to link the assessment to.
    """
    registry = load_registry(_SKILLS_DIR)
    seeded = await seed_matter(
        commit_factory, area_key="privacy", doc=_matter_note(), matter_name=_MATTER_NAME
    )
    await seed_ropa_register(commit_factory, source_project_id=seeded.project_id)
    if use_skill:
        await bind_area_skill(commit_factory, seeded.practice_area_id, _ASSESSMENT_SKILL)
    try:
        receipt = await run_scenario(
            _BUILD,
            seeded,
            skill_registry=registry,
            model_alias=model_alias,
            max_steps=_BUILD_STEPS,
        )
        snapshot = await snapshot_assessment(commit_factory, seeded.project_id)
    finally:
        if use_skill:
            # Leave the shared (migration-seeded) practice area as we found it, so a
            # later parametrized control arm isn't contaminated.
            await unbind_area_skill(commit_factory, seeded.practice_area_id, _ASSESSMENT_SKILL)
        await cleanup_assessment(commit_factory, seeded.project_id)
        await cleanup_register(commit_factory, seeded.project_id)
        await seeded.cleanup()

    score = score_assessment(snapshot)
    _write_build_report(
        receipt,
        snapshot,
        score,
        _EVIDENCE_DIR / f"build-{_build_id(model_alias, use_skill)}",
        model_alias=model_alias,
        use_skill=use_skill,
    )

    # Per ADR-F015: assert only that the run is honest (terminal + a model turn);
    # the assessment's quality is a recorded finding, not a pass/fail gate (the model
    # is not yet scenario-qualified and runs are non-deterministic). The ADR-F027
    # completion invariant, however, is code-enforced and MUST hold on any record the
    # write path produced — so it is a hard assert.
    assert receipt.status in _TERMINAL, (receipt.scenario.id, receipt.status)
    assert receipt.model_turns > 0, "no model turn recorded"
    assert score["completion_integrity_ok"], "a completed high-risk assessment lacks a mitigation"
