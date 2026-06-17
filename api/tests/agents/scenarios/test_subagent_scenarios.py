"""UX-B-4 — exercise a LIVE subagent through the cockpit loop (ADR-F015/F017).

Provider-marked (CI skips — no gateway key). Commercial carries a live
``document-researcher`` subagent (migration 0057); the composition point wires
it with its own isolated skill source (ADR-F017). This drives the REAL
Commercial agent through the live gateway against a multi-document RFQ matter
and records whether the lead model DELEGATES on-demand: it should answer a
single focused fact directly (no ``task``) and fan out to the researcher for a
broad cross-document review.

Per ADR-F015 this is NOT a pass/fail gate on the model: whether it delegates,
and whether it converges, are findings recorded in the committed behavior
report (``docs/fork/evidence/ux-b-4/``). The deterministic ancestry test
(``tests/agents/test_agent_composition.py``) proves the mechanism in CI; this
live run characterises a tier-4 model's delegation behaviour. The assertions
here only confirm the RIG worked — every scenario produced a terminal run with
receipts and a live model turn.

Run (out-of-CI, live gateway), from repo root:

    docker run --rm --network host \\
      -v "$PWD/api:/app" -v "$PWD/skills:/skills:ro" \\
      -v "$PWD/docs/fork/evidence/ux-b-4:/evidence" \\
      --user "$(id -u):$(id -g)" -e HOME=/tmp \\
      -e DATABASE_URL=postgresql+asyncpg://lq_ai:$POSTGRES_PASSWORD@localhost:5432/lq_ai \\
      -e LQ_AI_GATEWAY_URL=http://localhost:8001 -e LQ_AI_GATEWAY_KEY=$LQ_AI_GATEWAY_KEY \\
      -e UX_B4_EVIDENCE_DIR=/evidence -w /app lq-ai-api-dev \\
      pytest -q -m provider tests/agents/scenarios/test_subagent_scenarios.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.skills import load_registry
from tests.agents.scenarios.harness import Receipt, run_scenario, seed_multi_doc_matter
from tests.agents.scenarios.report import write_report
from tests.agents.scenarios.subagent_fixtures import (
    RFQ_DOCS,
    RFQ_MATTER_NAME,
    RFQ_REVIEW_MAX_STEPS,
    SUBAGENT_SCENARIOS,
)

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_EVIDENCE_DIR = (
    Path(os.environ["UX_B4_EVIDENCE_DIR"])
    if os.environ.get("UX_B4_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "ux-b-4"
)

_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

# The cross-document review gets extra step headroom for delegation; the single
# fact uses the default cap.
_MAX_STEPS_BY_SCENARIO = {"rfq_cross_document_review": RFQ_REVIEW_MAX_STEPS}


async def test_subagent_commercial_scenarios(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    # The real curated library; the composition point exposes only Commercial's
    # bound subset to the lead agent and only the subagent's (⊆ area) subset to
    # the researcher, each via its own source (ADR-F017).
    registry = load_registry(Path("/skills"))

    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=RFQ_DOCS,
        matter_name=RFQ_MATTER_NAME,
    )
    receipts: list[Receipt] = []
    try:
        for scenario in SUBAGENT_SCENARIOS:
            receipts.append(
                await run_scenario(
                    scenario,
                    seeded,
                    skill_registry=registry,
                    max_steps=_MAX_STEPS_BY_SCENARIO.get(scenario.id, 16),
                )
            )
    finally:
        await seeded.cleanup()

    write_report(
        receipts,
        _EVIDENCE_DIR / "commercial",
        model_alias="smart",
        area="commercial",
        milestone="UX-B-4",
    )

    assert len(receipts) == len(SUBAGENT_SCENARIOS)
    assert all(r.status in _TERMINAL for r in receipts), [
        (r.scenario.id, r.status) for r in receipts
    ]
    assert any(r.model_turns > 0 for r in receipts), "no model turn recorded in any scenario"
