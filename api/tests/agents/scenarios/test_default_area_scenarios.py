"""UX-B-2 — drive the default-area scenarios through the live agent.

Provider-marked (CI skips — no gateway key). Run against the live dev
stack, which also supplies the test DB's Postgres:

    DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lq_ai \\
    LQ_AI_GATEWAY_KEY=<dev key> \\
    pytest -m provider tests/agents/scenarios/test_default_area_scenarios.py -s

Per ADR-F015 this is NOT a pass/fail gate on the model: a scenario that
misses its expected shape is a finding recorded in the committed per-area
behavior report (which calibrates the area profile). The assertions below
only confirm the RIG worked for each area — every scenario produced a
terminal run with receipts, and the live loop actually turned the model.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.agents.scenarios.area_fixtures import AREA_FIXTURES, AreaFixture
from tests.agents.scenarios.harness import Receipt, run_scenario, seed_matter
from tests.agents.scenarios.report import write_report

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

# Overridable via UX_B2_EVIDENCE_DIR so a containerized / nightly run can
# point the reports at a mounted host path (the repo root differs inside a
# container). Each area writes to <dir>/<area_key>/behavior-report.{json,md}.
_EVIDENCE_DIR = (
    Path(os.environ["UX_B2_EVIDENCE_DIR"])
    if os.environ.get("UX_B2_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "ux-b-2"
)

_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}


@pytest.mark.parametrize("fixture", AREA_FIXTURES, ids=[f.area_key for f in AREA_FIXTURES])
async def test_default_area_scenarios(
    fixture: AreaFixture,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await seed_matter(
        commit_factory,
        area_key=fixture.area_key,
        doc=fixture.doc,
        matter_name=fixture.matter_name,
    )
    receipts: list[Receipt] = []
    try:
        for scenario in fixture.scenarios:
            receipts.append(await run_scenario(scenario, seeded))
    finally:
        await seeded.cleanup()

    # Write the durable evidence artifact BEFORE asserting, so the report
    # lands even when the rig surfaces something worth inspecting.
    write_report(
        receipts,
        _EVIDENCE_DIR / fixture.area_key,
        model_alias="smart",
        area=fixture.area_key,
        milestone="UX-B-2",
    )

    assert len(receipts) == len(fixture.scenarios)
    # No run stranded at 'running' (the flood-brake regression).
    assert all(r.status in _TERMINAL for r in receipts), [
        (r.scenario.id, r.status) for r in receipts
    ]
    # The live loop actually turned the model (not an instant wiring error).
    assert any(r.model_turns > 0 for r in receipts), "no model turn recorded in any scenario"
