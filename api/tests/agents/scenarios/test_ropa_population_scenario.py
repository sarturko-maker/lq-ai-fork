"""PRIV-7 — live ROPA population from a real privacy notice (Zendesk).

The maintainer's onboarding test: hand the Privacy Deep Agent a real company
privacy notice and see how much of a coherent Article 30 ROPA it builds through
the PRIV-2..6c guarded, code-validated write tools. The agent writes are validated
before commit, so every persisted row is valid *by construction*; what this test
measures is **how much** of a register a real model populates from a real notice,
and **how** — a naive one-shot ask vs. a staged sequence an onboarding flow would
orchestrate (the 300s per-run wall clock makes staging the realistic shape).

Doubly gated, so CI and a fresh checkout never depend on third-party text:
  * ``@pytest.mark.provider`` + ``LQ_AI_GATEWAY_KEY`` — skips without a live gateway.
  * the local, gitignored Zendesk notice file — skips if absent.

Run live against the dev stack (the gateway reaches DeepSeek; the test DB is a
throwaway ``lq_ai_test_*`` the conftest migrates + drops):

    LQ_AI_ROPA_MODEL=deepseek \\            # deepseek-v4-flash (default); deepseek-pro to escalate
    pytest -m provider tests/agents/scenarios/test_ropa_population_scenario.py -s -k staged

Per ADR-F015 this is NOT a model pass/fail gate; it emits a committed behavior +
coverage report under docs/fork/evidence/priv-7/. DeepSeek is not yet
scenario-qualified — this run is its first qualification data point.
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
    load_notice_document,
    score_coverage,
    snapshot_register,
    unbind_area_skill,
)
from tests.agents.scenarios.scenarios import Scenario

# The real notice lives at a LOCAL, gitignored path (testing-only, not committed).
_NOTICE_PATH = Path(
    os.environ.get(
        "LQ_AI_ROPA_NOTICE_PATH",
        str(Path(__file__).resolve().parent / "_local" / "zendesk-privacy-notice.txt"),
    )
)
_NOTICE_FILENAME = "Zendesk-Privacy-Notice.txt"
_NOTICE_SOURCE = "https://www.zendesk.co.uk/company/agreements-and-terms/privacy-notice/"
_NOTICE_RETRIEVED = "2026-06-19"

# DeepSeek flash by default ('deepseek' → deepseek-v4-flash); 'deepseek-pro' to escalate.
_MODEL = os.environ.get("LQ_AI_ROPA_MODEL", "deepseek")
# Generous per-run step ceiling; the 300s wall clock is the usual real limiter.
_ONESHOT_STEPS = 60
_STAGE_STEPS = 50
_BUILD_STEPS = 60

# The skills library (incl. the new ropa-population skill); the build comparison
# loads this and binds ropa-population to Privacy test-only (no migration).
_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)
_ROPA_SKILL = "ropa-population"

_EVIDENCE_DIR = (
    Path(os.environ["LQ_AI_PRIV7_EVIDENCE_DIR"])
    if os.environ.get("LQ_AI_PRIV7_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "priv-7"
)

_MATTER_NAME = "Zendesk — privacy-notice onboarding (PRIV-7)"
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
    pytest.mark.skipif(
        not _NOTICE_PATH.exists(),
        reason=f"notice file absent ({_NOTICE_PATH}); testing-only, not committed",
    ),
]


_ONESHOT = Scenario(
    id="ropa_oneshot",
    title="One-shot — build the full ROPA from the notice",
    note=(
        "The naive path: one broad ask. Tests whether a single bounded run (300s "
        "wall clock) can read a real notice and build a coherent Article 30 register."
    ),
    prompt=(
        "You maintain this organisation's Article 30 Record of Processing Activities "
        "(ROPA). Our privacy notice has been added to this programme. Read it, then "
        "build the ROPA from it using your ROPA tools: (1) record each distinct "
        "processing activity with its purpose, Article 6 lawful basis, controller/"
        "processor role and a retention period — set the special-category flag and an "
        "Article 9 condition where it processes special-category data; (2) record the "
        "systems/assets and the categories of recipients/vendors involved, with each "
        "vendor's role and DPA status; (3) record any international (third-country) "
        "transfers with their Chapter V safeguards; (4) link each activity to its "
        "systems and recipients and tag it with its categories of data subjects and "
        "personal data. Ground everything in the notice; where the notice is silent on "
        "a required field, choose the most defensible value and note your assumption."
    ),
    expect_tools=("propose_processing_activity",),
    step_bound=_ONESHOT_STEPS,
)

_STAGES: list[Scenario] = [
    Scenario(
        id="ropa_stage1_activities",
        title="Stage 1 — processing activities",
        note="Record the distinct Article 30 activities the notice describes.",
        prompt=(
            "Our organisation's privacy notice is in this programme. Read it and record "
            "the distinct processing activities it describes in our Article 30 register, "
            "calling propose_processing_activity for each. For every activity capture: a "
            "clear name, the purpose, the Article 6 lawful basis, the controller/processor "
            "role and a concise retention period (if the notice gives only a general "
            "retention approach, state a defensible retention). Where an activity processes "
            "special-category (Article 9) data, set special_category and the matching "
            "Article 9 condition. Cover the principal activities a privacy officer would "
            "expect from this notice."
        ),
        expect_tools=("propose_processing_activity",),
        step_bound=_STAGE_STEPS,
    ),
    Scenario(
        id="ropa_stage2_systems_recipients",
        title="Stage 2 — systems & recipients",
        note="Record the systems/assets and the categories of recipients (vendors).",
        prompt=(
            "Continue building our Article 30 register from the privacy notice in this "
            "programme. Record (a) the systems/assets where personal data lives using "
            "propose_system, and (b) the categories of recipients / third parties we "
            "disclose personal data to using propose_vendor — give each a role (processor, "
            "sub_processor, joint_controller, separate_controller or recipient) and a DPA "
            "status. Base these on the recipients and processing described in the notice."
        ),
        expect_tools=("propose_vendor",),
        step_bound=_STAGE_STEPS,
    ),
    Scenario(
        id="ropa_stage3_transfers",
        title="Stage 3 — international transfers",
        note="Record third-country transfers + Chapter V safeguards against activities.",
        prompt=(
            "Continue our Article 30 register. Record our international (third-country) "
            "transfers of personal data and their Chapter V safeguards. First call "
            "list_processing_activities to get the activity ids, then for each relevant "
            "activity call propose_transfer with the destination, whether it is restricted "
            "(recipient outside the UK/EEA) and — when restricted — the safeguard mechanism "
            "(e.g. standard_contractual_clauses, uk_idta, binding_corporate_rules). Ground "
            "the destinations and mechanisms in the notice."
        ),
        expect_tools=("propose_transfer",),
        step_bound=_STAGE_STEPS,
    ),
    Scenario(
        id="ropa_stage4_links_categories",
        title="Stage 4 — links & categories",
        note="Link activities↔systems/recipients and tag data-subject + data categories.",
        prompt=(
            "Finish tying our Article 30 register together. Using the list_* tools to find "
            "ids: link each processing activity to the systems it uses "
            "(link_processing_activity_to_system) and to the recipients it discloses to "
            "(link_vendor_to_activity); and tag each activity with its categories of data "
            "subjects (add_data_subject_categories) and categories of personal data "
            "(add_data_categories), based on the notice."
        ),
        expect_tools=("add_data_categories",),
        step_bound=_STAGE_STEPS,
    ),
]


# The build comparison (PRIV-7 Phase B/C): NAIVE prompts — what an operator would
# actually type — across two passes; the ropa-population SKILL, when bound, carries
# the method (work each activity to completion / link as you go) the naive baseline
# lacked. Holding the prompts constant isolates the skill's (and the model's) effect.
_BUILD_FLOW: list[Scenario] = [
    Scenario(
        id="ropa_build_pass1",
        title="Build pass 1 — populate the ROPA from the notice",
        note="Naive build ask; the skill (if bound) supplies the activity-to-completion method.",
        prompt=(
            "Our organisation's privacy notice is in this programme. Build our Article 30 "
            "Record of Processing Activities from it using your ROPA tools: capture the "
            "processing activities, the categories of data subjects and personal data, the "
            "systems and the recipients involved, and any international transfers. Cover as "
            "much as you can in this pass."
        ),
        expect_tools=("propose_processing_activity",),
        step_bound=_BUILD_STEPS,
    ),
    Scenario(
        id="ropa_build_pass2",
        title="Build pass 2 — fill gaps without duplicating",
        note="Continue the build: complete partial records and add any missing activities.",
        prompt=(
            "Continue building our Article 30 register from the privacy notice. Use the "
            "list_* tools to see what is already recorded, then complete any partially-"
            "recorded activities (missing systems, recipients, data or data-subject "
            "categories, or transfers) and add any activities not yet captured. Do not "
            "duplicate existing entries."
        ),
        expect_tools=("list_processing_activities",),
        step_bound=_BUILD_STEPS,
    ),
]

# (model_alias, bind ropa-population?) — flash control, flash+skill, pro+skill. Both
# arms pass the registry (so the only variable is the ropa-population skill + model).
# (model_alias, bind ropa-population?, max_steps). The first three hold the budget
# constant to isolate skill + model; the last raises max_steps to test whether more
# budget — now that the recursion_limit fix lets a run use it — closes the gap.
# Run SERIALLY (these are manual @pytest.mark.provider tests): bind/unbind mutate the
# shared, migration-seeded practice-area row, so a parallel (xdist) run could let one
# arm's binding contaminate another arm's control. The row-scoped register cleanup is
# parallel-safe; only the shared skill binding is not.
_BUILD_CONFIGS: list[tuple[str, bool, int]] = [
    ("deepseek", False, _BUILD_STEPS),
    ("deepseek", True, _BUILD_STEPS),
    ("deepseek-pro", True, _BUILD_STEPS),
    ("deepseek", True, 150),
]


def _build_id(model_alias: str, use_skill: bool, steps: int) -> str:
    label = "skill" if use_skill else "noskill"
    suffix = "" if steps == _BUILD_STEPS else f"-s{steps}"
    return f"{model_alias}-{label}{suffix}"


def _write_ropa_report(
    receipts: list[Receipt],
    snapshot: RegisterSnapshot,
    coverage: dict[str, Any],
    out_dir: Path,
    *,
    model_alias: str,
    mode: str,
) -> tuple[Path, Path]:
    """Write the PRIV-7 behavior + coverage report (JSON + Markdown).

    Observations + the agent's own structured output only — never the source
    notice verbatim, never a provider key/URL.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    payload = {
        "milestone": "PRIV-7",
        "adr": "F015",
        "mode": mode,
        "model_alias": model_alias,
        "model_note": (
            f"alias '{model_alias}' resolves via the gateway to a DeepSeek V4 model "
            "(deepseek-v4-flash for 'deepseek', deepseek-v4-pro for 'deepseek-pro'). "
            "DeepSeek is NOT yet scenario-qualified (ADR-F015) — this run is a "
            "qualification data point, kept verbatim, not tuned green."
        ),
        "source": {
            "company": "Zendesk",
            "url": _NOTICE_SOURCE,
            "retrieved": _NOTICE_RETRIEVED,
            "note": "Real public notice, testing-only — held transiently, not committed.",
        },
        "generated_at": stamp,
        "coverage": coverage,
        "register": snapshot.to_dict(),
        "runs": [r.to_dict() for r in receipts],
    }
    json_path = out_dir / "behavior-report.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path = out_dir / "behavior-report.md"
    md_path.write_text(_render_md(payload), encoding="utf-8")
    return json_path, md_path


def _render_md(payload: dict[str, Any]) -> str:
    c = payload["coverage"]["counts"]
    src = payload["source"]
    lines: list[str] = [
        f"# PRIV-7 — ROPA population ({payload['mode']}) — {payload['model_alias']}",
        "",
        f"- **Model:** {payload['model_note']}",
        f"- **Source notice:** {src['company']} — {src['url']} (retrieved {src['retrieved']}; "
        f"{src['note']})",
        f"- **Generated:** {payload['generated_at']}",
        "",
        "> Article 30 register the agent built through the guarded, code-validated ROPA "
        "tools. Every persisted row is valid by construction (the write path rejects "
        "invalid proposals); this report measures coverage + coherence, not validity. "
        "Kept verbatim per ADR-F015 — a thin or messy register is a finding, not a failure.",
        "",
        "## Coverage",
        "",
        f"- **Activities:** {c['activities']} · **Systems:** {c['systems']} · "
        f"**Vendors/recipients:** {c['vendors']} · **Transfers:** {c['transfers']} "
        f"({c['restricted_transfers']} restricted)",
        f"- **Distinct data-subject categories:** {c['distinct_data_subject_categories']} · "
        f"**distinct data categories:** {c['distinct_data_categories']}",
        f"- **Activities fully linked** (system + recipient + both category axes): "
        f"{payload['coverage']['activities_fully_linked']}/{c['activities']}",
        f"- **Linkage axis fractions:** {payload['coverage']['linkage_axis_fractions']}",
        f"- **Invariant integrity (special-category ⇔ Art 9):** "
        f"{'OK' if payload['coverage']['integrity_ok'] else 'INCONSISTENT'}",
        "",
        "## Runs",
        "",
        "| Run | Status | Tools called | Steps | Latency |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in payload["runs"]:
        tools = ", ".join(r["tools_called"]) or "—"
        lines.append(
            f"| {r['title']} | `{r['status']}` | {tools} | {r['step_count']} | {r['latency_s']}s |"
        )

    lines += ["", "## Produced register", ""]
    for a in payload["register"]["activities"]:
        sc = " · special-category" + (f" ({a['art9_condition']})" if a["art9_condition"] else "")
        lines += [
            f"### {a['name']}",
            "",
            f"- **Purpose:** {a['purpose_excerpt']}",
            f"- **Lawful basis:** {a['lawful_basis']} · **role:** {a['controller_role']}"
            + (sc if a["special_category"] else ""),
            f"- **Retention:** {a['retention']}",
            f"- **Systems:** {', '.join(a['systems']) or '—'}",
            f"- **Recipients:** {', '.join(a['recipients']) or '—'}",
            f"- **Data subjects:** {', '.join(a['data_subject_categories']) or '—'}",
            f"- **Data categories:** {', '.join(a['data_categories']) or '—'}",
            f"- **Transfers:** {a['transfers'] or '—'}",
            "",
        ]
    if payload["register"]["systems"]:
        lines += ["### Systems (all)", "", f"{payload['register']['systems']}", ""]
    if payload["register"]["vendors"]:
        lines += ["### Vendors/recipients (all)", "", f"{payload['register']['vendors']}", ""]
    return "\n".join(lines)


@pytest.mark.parametrize("model_alias", [_MODEL])
async def test_ropa_population_oneshot(
    model_alias: str,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Naive one-shot: one broad ask, generous step ceiling, 300s wall clock."""
    doc = load_notice_document(_NOTICE_PATH, filename=_NOTICE_FILENAME)
    seeded = await seed_matter(
        commit_factory, area_key="privacy", doc=doc, matter_name=_MATTER_NAME
    )
    receipts: list[Receipt] = []
    try:
        receipts.append(
            await run_scenario(_ONESHOT, seeded, model_alias=model_alias, max_steps=_ONESHOT_STEPS)
        )
        snapshot = await snapshot_register(commit_factory, seeded.project_id)
    finally:
        await cleanup_register(commit_factory, seeded.project_id)
        await seeded.cleanup()

    coverage = score_coverage(snapshot)
    _write_ropa_report(
        receipts,
        snapshot,
        coverage,
        _EVIDENCE_DIR / f"{model_alias}-oneshot",
        model_alias=model_alias,
        mode="one-shot",
    )

    assert all(r.status in _TERMINAL for r in receipts), [
        (r.scenario.id, r.status) for r in receipts
    ]
    assert any(r.model_turns > 0 for r in receipts), "no model turn recorded"


@pytest.mark.parametrize("model_alias", [_MODEL])
async def test_ropa_population_staged(
    model_alias: str,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Staged: four bounded runs accumulate the register (the orchestrated path)."""
    doc = load_notice_document(_NOTICE_PATH, filename=_NOTICE_FILENAME)
    seeded = await seed_matter(
        commit_factory, area_key="privacy", doc=doc, matter_name=_MATTER_NAME
    )
    receipts: list[Receipt] = []
    try:
        for stage in _STAGES:
            receipts.append(
                await run_scenario(stage, seeded, model_alias=model_alias, max_steps=_STAGE_STEPS)
            )
        snapshot = await snapshot_register(commit_factory, seeded.project_id)
    finally:
        await cleanup_register(commit_factory, seeded.project_id)
        await seeded.cleanup()

    coverage = score_coverage(snapshot)
    _write_ropa_report(
        receipts,
        snapshot,
        coverage,
        _EVIDENCE_DIR / f"{model_alias}-staged",
        model_alias=model_alias,
        mode="staged",
    )

    assert len(receipts) == len(_STAGES)
    assert all(r.status in _TERMINAL for r in receipts), [
        (r.scenario.id, r.status) for r in receipts
    ]
    assert any(r.model_turns > 0 for r in receipts), "no model turn recorded"


@pytest.mark.parametrize(
    "model_alias,use_skill,max_steps",
    _BUILD_CONFIGS,
    ids=[_build_id(*cfg) for cfg in _BUILD_CONFIGS],
)
async def test_ropa_population_build(
    model_alias: str,
    use_skill: bool,
    max_steps: int,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Build comparison: naive prompts; the ropa-population skill carries the method.

    Control (``use_skill=False``) runs with the area's default skills only; treatment
    binds ``ropa-population`` test-only (no migration). The registry is always passed,
    so the variables are the skill, the model, and the step budget.
    """
    doc = load_notice_document(_NOTICE_PATH, filename=_NOTICE_FILENAME)
    registry = load_registry(_SKILLS_DIR)
    seeded = await seed_matter(
        commit_factory, area_key="privacy", doc=doc, matter_name=_MATTER_NAME
    )
    if use_skill:
        await bind_area_skill(commit_factory, seeded.practice_area_id, _ROPA_SKILL)
    receipts: list[Receipt] = []
    try:
        for scenario in _BUILD_FLOW:
            receipts.append(
                await run_scenario(
                    scenario,
                    seeded,
                    skill_registry=registry,
                    model_alias=model_alias,
                    max_steps=max_steps,
                )
            )
        snapshot = await snapshot_register(commit_factory, seeded.project_id)
    finally:
        if use_skill:
            # Leave the shared (migration-seeded) practice area as we found it,
            # so a later parametrized run's control arm isn't contaminated.
            await unbind_area_skill(commit_factory, seeded.practice_area_id, _ROPA_SKILL)
        await cleanup_register(commit_factory, seeded.project_id)
        await seeded.cleanup()

    coverage = score_coverage(snapshot)
    _write_ropa_report(
        receipts,
        snapshot,
        coverage,
        _EVIDENCE_DIR / f"build-{_build_id(model_alias, use_skill, max_steps)}",
        model_alias=model_alias,
        mode=f"build · skill={'ropa-population' if use_skill else 'off'} · max_steps={max_steps}",
    )

    assert len(receipts) == len(_BUILD_FLOW)
    assert all(r.status in _TERMINAL for r in receipts), [
        (r.scenario.id, r.status) for r in receipts
    ]
    assert any(r.model_turns > 0 for r in receipts), "no model turn recorded"
