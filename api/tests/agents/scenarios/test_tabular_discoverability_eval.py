"""F2 Tabular T3 — discoverability eval for the ``tabular-review`` craft skill (ADR-F055/F041).

Provider-marked (CI skips — no gateway key). Run against the live dev stack:

    DATABASE_URL=postgresql+asyncpg://lq_ai:...@postgres:5432/lq_ai \\
    LQ_AI_GATEWAY_KEY=<dev key> LQ_AI_GATEWAY_URL=http://gateway:8001 \\
    LQ_AI_SKILLS_DIR=/skills LQ_AI_SCENARIO_MODEL=deepseek \\
    pytest -m provider tests/agents/scenarios/test_tabular_discoverability_eval.py -s

Measures whether the bound ``tabular-review`` skill steers DISCOVERABILITY, NOT grid
mechanics (T1 proved mechanics). The prompts deliberately do NOT name a grid or the
tools — they state a lawyer's intent. The eval records, per scenario, whether the agent
reached for ``start_tabular_review`` and which columns it chose:

* APT asks (several documents, a compare/extract-across intent) SHOULD offer/build a grid.
* A QUIET ask (a single-document lookup) should NOT — restraint is half the craft.

Per ADR-F015 this is a recorded FINDING, not a pass/fail gate on the model; the assertions
only confirm the rig turned the live model. The finding is frozen under
``docs/fork/evidence/tabular-review/``.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.tabular import TabularExecution
from tests.agents.scenarios.harness import run_scenario, seed_multi_doc_matter
from tests.agents.scenarios.scenarios import Scenario, build_document

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]


def _nda(name: str, project: str, term: str, law: str) -> object:
    return build_document(
        name,
        [
            (1, f"Mutual Non-Disclosure Agreement — {project}."),
            (1, f"Term: {term}"),
            (1, f"Governing law: {law}"),
        ],
    )


_THREE_NDAS = [
    _nda(
        "nda-alpha.txt",
        "Project Alpha",
        "in force for two (2) years.",
        "the laws of England and Wales.",
    ),
    _nda(
        "nda-beta.txt",
        "Project Beta",
        "continues for three (3) years.",
        "the laws of the State of New York.",
    ),
    _nda(
        "nda-gamma.txt", "Project Gamma", "survives for five (5) years.", "the laws of Singapore."
    ),
]
_ONE_NDA = [_THREE_NDAS[0]]


# Prompts NEVER name a grid or a tool — they state intent. The skill must recognise the shape.
_APT_VAGUE = Scenario(
    id="apt-vague",
    title="Several docs + get-on-top intent → should offer a grid",
    note="ADR-F055 T3: proactive offer over multiple documents.",
    prompt=(
        "I've got three NDAs in this matter — nda-alpha.txt, nda-beta.txt and nda-gamma.txt. "
        "I need to get on top of their key terms across the set, especially how long each one "
        "runs for and which law governs it. What's the best way to see this?"
    ),
    expect_tools=(),
    step_bound=24,
    must_include=(),
)
_APT_TABLE = Scenario(
    id="apt-table",
    title="Explicit 'table … for each' → should map NL to columns",
    note="ADR-F055 T3: natural-language → start_tabular_review columns.",
    prompt=(
        "Give me a table of the term and the governing law for each of these three NDAs "
        "(nda-alpha.txt, nda-beta.txt, nda-gamma.txt)."
    ),
    expect_tools=(),
    step_bound=24,
    must_include=(),
)
_QUIET_SINGLE = Scenario(
    id="quiet-single-doc",
    title="Single-document lookup → should NOT build a grid",
    note="ADR-F055 T3: restraint — one document is a lookup, not a grid.",
    prompt="What's the term in nda-alpha.txt?",
    expect_tools=(),
    step_bound=16,
    must_include=(),
)

_CASES = [
    (_APT_VAGUE, _THREE_NDAS, True),
    (_APT_TABLE, _THREE_NDAS, True),
    (_QUIET_SINGLE, _ONE_NDA, False),
]


async def test_tabular_discoverability_eval(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    findings: list[dict[str, object]] = []
    for scenario, docs, should_offer in _CASES:
        seeded = await seed_multi_doc_matter(
            commit_factory,
            area_key="commercial",
            docs=docs,
            matter_name=f"T3 discoverability — {scenario.id}",
        )
        try:
            receipt = await run_scenario(scenario, seeded, max_steps=scenario.step_bound)
            async with commit_factory() as db:
                grid = (
                    await db.execute(
                        select(TabularExecution).where(
                            TabularExecution.project_id == seeded.project_id,
                            TabularExecution.mode == "agentic",
                        )
                    )
                ).scalar_one_or_none()
            offered = "start_tabular_review" in receipt.tools_called
            findings.append(
                {
                    "scenario": scenario.id,
                    "should_offer_grid": should_offer,
                    "offered_grid": offered,
                    "correct": offered == should_offer,
                    "status": receipt.status,
                    "model_turns": receipt.model_turns,
                    "tools_called": receipt.tools_called,
                    "grid_columns": (
                        [c.get("name") for c in (grid.columns or [])] if grid else None
                    ),
                }
            )
        finally:
            await seeded.cleanup()

    print("\n=== ADR-F055 T3 discoverability finding ===")
    print(json.dumps(findings, indent=2, default=str))
    correct = sum(1 for f in findings if f["correct"])
    print(f"discoverability: {correct}/{len(findings)} scenarios matched the intended behaviour")

    # ADR-F015: assert only that the rig turned the live model on every scenario — the
    # discoverability outcome above is a recorded finding, not a pass/fail gate.
    assert len(findings) == len(_CASES)
    for f in findings:
        assert f["status"] in {"completed", "failed", "cap_exceeded", "cancelled"}
        assert f["model_turns"] > 0
