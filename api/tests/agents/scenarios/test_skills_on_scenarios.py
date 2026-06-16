"""UX-B-3 — re-qualify the cockpit Deep Agent with SKILLS ON (ADR-F015/F016).

Provider-marked (CI skips — no gateway key). Runs the REAL Commercial agent
through the live gateway with the area's bound skills activated: the
composition point builds the registry-backed backend over Commercial's
default bindings (migration 0056), and the model's tool surface expands with
the deepagents builtin filesystem tools + the SkillsMiddleware skill listing.

Per ADR-F015 this is NOT a pass/fail gate on the model: a scenario that misses
its expected shape is a finding recorded in the committed behavior report
(``docs/fork/evidence/ux-b-3/``), which calibrates whether the expanded surface
derails MiniMax-M3's selection. The assertions only confirm the RIG worked —
every scenario produced a terminal run with receipts and a live model turn.

Run (out-of-CI, live gateway), from repo root:

    docker run --rm --network host \\
      -v "$PWD/api:/app" -v "$PWD/skills:/skills:ro" \\
      -v "$PWD/docs/fork/evidence/ux-b-3:/evidence" \\
      --user "$(id -u):$(id -g)" -e HOME=/tmp \\
      -e DATABASE_URL=postgresql+asyncpg://lq_ai:$POSTGRES_PASSWORD@localhost:5432/lq_ai \\
      -e LQ_AI_GATEWAY_URL=http://localhost:8001 -e LQ_AI_GATEWAY_KEY=$LQ_AI_GATEWAY_KEY \\
      -e UX_B3_EVIDENCE_DIR=/evidence -w /app lq-ai-api-dev \\
      pytest -q -m provider tests/agents/scenarios/test_skills_on_scenarios.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.skills import load_registry
from tests.agents.scenarios.harness import Receipt, run_scenario, seed_matter
from tests.agents.scenarios.report import write_report
from tests.agents.scenarios.scenarios import Scenario, build_fixture_document

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_EVIDENCE_DIR = (
    Path(os.environ["UX_B3_EVIDENCE_DIR"])
    if os.environ.get("UX_B3_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "ux-b-3"
)

_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

# Commercial binds msa-review-saas / msa-review-commercial-purchase / contract-qa
# / nda-review (0056). These scenarios probe whether the model still grounds +
# cites with the larger tool surface, and whether it recognises a matching
# skill. Step bounds are generous: progressive disclosure adds read_file calls
# (reading a SKILL.md) on top of the matter-tool grounding.
_SKILLS_ON_SCENARIOS: list[Scenario] = [
    Scenario(
        id="skill_grounded_review",
        title="Grounded review (skills on)",
        note=(
            "With the area's review skills exposed, does the model still ground "
            "the limitation-of-liability answer in the document and cite it, "
            "rather than answering from the skill prose or wandering the bigger "
            "tool surface?"
        ),
        prompt=(
            "As the customer, review the limitation of liability clause in the "
            "Acme MSA in this matter: what is the cap, and is it acceptable? "
            "Quote the clause and cite the section."
        ),
        expect_tools=("search_documents",),
        step_bound=12,
        must_include=("liability",),
    ),
    Scenario(
        id="skill_recognition",
        title="Skill recognition (skills on)",
        note=(
            "A request squarely matching a bound review skill — does the model "
            "recognise the skill (read its SKILL.md via read_file) and/or apply "
            "a structured review, while still grounding in the document? "
            "Observation only: whether it reaches for the skill is the finding."
        ),
        prompt=(
            "Do a structured risk review of the Acme MSA in this matter from the "
            "customer's perspective, and flag anything a buyer should worry "
            "about, with citations."
        ),
        expect_tools=("search_documents",),
        step_bound=14,
    ),
]


async def test_skills_on_commercial_scenarios(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    # The real, curated library — only Commercial's bound subset is exposed by
    # the backend the composition point builds (ADR-F016).
    registry = load_registry(Path("/skills"))

    seeded = await seed_matter(
        commit_factory,
        area_key="commercial",
        doc=build_fixture_document(),
        matter_name="Acme — Master Services Agreement (skills on)",
    )
    receipts: list[Receipt] = []
    try:
        for scenario in _SKILLS_ON_SCENARIOS:
            receipts.append(await run_scenario(scenario, seeded, skill_registry=registry))
    finally:
        await seeded.cleanup()

    write_report(
        receipts,
        _EVIDENCE_DIR / "commercial",
        model_alias="smart",
        area="commercial",
        milestone="UX-B-3",
    )

    assert len(receipts) == len(_SKILLS_ON_SCENARIOS)
    assert all(r.status in _TERMINAL for r in receipts), [
        (r.scenario.id, r.status) for r in receipts
    ]
    assert any(r.model_turns > 0 for r in receipts), "no model turn recorded in any scenario"
