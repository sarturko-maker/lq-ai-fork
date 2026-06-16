"""UX-B-1 — drive the Commercial starter scenarios through the live agent.

Provider-marked (CI skips — no gateway key). Run against the live dev
stack, which also supplies the test DB's Postgres:

    DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lq_ai \\
    LQ_AI_GATEWAY_KEY=<dev key> \\
    pytest -m provider tests/agents/scenarios/test_commercial_scenarios.py -s

Per ADR-F015 this is NOT a pass/fail gate on the model: a scenario that
misses its expected shape is a finding recorded in the committed
behavior report (which calibrates UX-B-2). The assertions below only
confirm the RIG worked — every scenario produced a terminal run with
receipts, and the live loop actually turned the model.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.agents.scenarios.harness import Receipt, run_scenario, seed_commercial_matter
from tests.agents.scenarios.report import write_report
from tests.agents.scenarios.scenarios import COMMERCIAL_SCENARIOS

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

# api/tests/agents/scenarios/ → repo root is four parents up. Overridable
# via UX_B1_EVIDENCE_DIR so a containerized / nightly run can point the
# report at a mounted host path (the repo root differs inside a container).
_EVIDENCE_DIR = (
    Path(os.environ["UX_B1_EVIDENCE_DIR"])
    if os.environ.get("UX_B1_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "ux-b-1"
)

_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}


async def test_commercial_scenario_baseline(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await seed_commercial_matter(commit_factory)
    receipts: list[Receipt] = []
    try:
        for scenario in COMMERCIAL_SCENARIOS:
            receipts.append(await run_scenario(scenario, seeded))
    finally:
        await seeded.cleanup()

    # Write the durable evidence artifact BEFORE asserting, so the report
    # lands even when the rig surfaces something worth inspecting.
    write_report(receipts, _EVIDENCE_DIR, model_alias="smart")

    assert len(receipts) == len(COMMERCIAL_SCENARIOS)
    # No run stranded at 'running' (the flood-brake regression).
    assert all(r.status in _TERMINAL for r in receipts), [
        (r.scenario.id, r.status) for r in receipts
    ]
    # The live loop actually turned the model (not an instant wiring error).
    assert any(r.model_turns > 0 for r in receipts), "no model turn recorded in any scenario"
