"""Live agent-driven verification of the agentic "grids" tool — ADR-F055 (F2 Tabular T1).

Provider-marked (CI skips — no gateway key). Run against the live dev stack:

    DATABASE_URL=postgresql+asyncpg://lq_ai:...@postgres:5432/lq_ai \\
    LQ_AI_GATEWAY_KEY=<dev key> LQ_AI_GATEWAY_URL=http://gateway:8001 \\
    pytest -m provider tests/agents/scenarios/test_tabular_grid_live.py -s

Drives the PRODUCTION composition point over a Commercial matter holding three small
NDAs with distinct Term / Governing-law clauses, asks for a comparison grid, and reads
back the persisted ``mode='agentic'`` ``tabular_executions`` row. Per ADR-F015 the
assertions only confirm the RIG turned the live model and produced a terminal run; the
grid outcome (which tools fired, whether it finalized, the cell values) is PRINTED as the
recorded finding (it also seeds the T3 discoverability eval).
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

_NDAS = [
    build_document(
        "nda-alpha.txt",
        [
            (1, "Mutual Non-Disclosure Agreement — Project Alpha."),
            (1, "Term: This Agreement remains in force for two (2) years from the Effective Date."),
            (1, "Governing law: This Agreement is governed by the laws of England and Wales."),
        ],
    ),
    build_document(
        "nda-beta.txt",
        [
            (1, "Mutual Non-Disclosure Agreement — Project Beta."),
            (1, "Term: This Agreement continues for a period of three (3) years."),
            (1, "Governing law: This Agreement is governed by the laws of the State of New York."),
        ],
    ),
    build_document(
        "nda-gamma.txt",
        [
            (1, "Mutual Non-Disclosure Agreement — Project Gamma."),
            (1, "Term: The confidentiality obligations survive for five (5) years."),
            (1, "Governing law: This Agreement is governed by the laws of Singapore."),
        ],
    ),
]

_GRID_SCENARIO = Scenario(
    id="commercial-grid",
    title="Build a key-terms grid across three NDAs",
    note="ADR-F055 T1: the agent should build a grid (start/record/finalize) over the NDAs.",
    prompt=(
        "I have three NDAs in this matter: nda-alpha.txt, nda-beta.txt and nda-gamma.txt. "
        "Build me a comparison grid with two columns — Term and Governing law — one row per "
        "NDA. Read each document, fill in every cell, and finalize the grid."
    ),
    expect_tools=("start_tabular_review", "finalize_tabular_review"),
    step_bound=24,
    must_include=(),
)


async def test_commercial_grid_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=_NDAS,
        matter_name="NDA portfolio — grid",
    )
    try:
        receipt = await run_scenario(_GRID_SCENARIO, seeded, max_steps=24)

        async with commit_factory() as db:
            grid = (
                await db.execute(
                    select(TabularExecution).where(
                        TabularExecution.project_id == seeded.project_id,
                        TabularExecution.mode == "agentic",
                    )
                )
            ).scalar_one_or_none()

        evidence = {
            "status": receipt.status,
            "model_turns": receipt.model_turns,
            "tools_called": receipt.tools_called,
            "task_calls": receipt.task_calls,
            "delegated": receipt.delegated,
            "grid_created": grid is not None,
            "grid_status": grid.status if grid else None,
            "grid_fill_mode": grid.fill_mode if grid else None,
            "grid_columns": [c.get("name") for c in (grid.columns or [])] if grid else None,
            "grid_rows": (grid.results or {}).get("rows", []) if grid else None,
            "final_answer": receipt.final_answer,
        }
        print("\n=== ADR-F055 T1 live grid evidence ===")
        print(json.dumps(evidence, indent=2, default=str))
    finally:
        await seeded.cleanup()

    # ADR-F015: assert only that the rig turned the live model — the grid outcome is a
    # recorded finding (printed above), not a pass/fail gate on the model.
    assert receipt.status in {"completed", "failed", "cap_exceeded", "cancelled"}
    assert receipt.model_turns > 0
