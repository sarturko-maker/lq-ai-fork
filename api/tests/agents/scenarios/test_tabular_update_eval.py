"""F2 Tabular T8 — conversational grid-edit eval (ADR-F055, provider-marked, CI-skipped).

Run against the live dev stack:

    DATABASE_URL=… LQ_AI_GATEWAY_KEY=… LQ_AI_GATEWAY_URL=http://gateway:8001 \\
    LQ_AI_SKILLS_DIR=/skills \\
    pytest -m provider -s tests/agents/scenarios/test_tabular_update_eval.py

The mechanics of ``update_tabular_cells`` are covered deterministically
(``test_tabular_tool.py`` drives it end-to-end through a real run). This eval checks
the LIVE tool-SELECTION behaviour the T8 doctrine steers: given a FINALIZED grid and a
lawyer asking to fix a cell, does the agent reach for ``update_tabular_cells`` (not
``record_tabular_row`` / ``start_tabular_review``) and change the right cell?

A completed grid is pre-seeded (in a real session the agent holds the grid_id from
building it — here the prompt carries it, as the conversation would). The
``tabular-review`` skill is loaded + injected (the T3 attribution lesson). Per ADR-F015
the assertions only confirm the rig turned the live model; the outcome is a finding.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.document import Document
from app.models.file import File
from app.models.tabular import TabularExecution
from app.skills import load_registry
from tests.agents.scenarios.harness import run_scenario, seed_multi_doc_matter
from tests.agents.scenarios.scenarios import Scenario, build_document

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)

_NDAS = [
    build_document(
        "nda-alpha.txt",
        [
            (1, "Mutual Non-Disclosure Agreement — Project Alpha."),
            (1, "Term: This Agreement remains in force for two (2) years from the Effective Date."),
            (1, "Governing law: the laws of England and Wales."),
        ],
    ),
    build_document(
        "nda-beta.txt",
        [
            (1, "Mutual Non-Disclosure Agreement — Project Beta."),
            (1, "Term: This Agreement continues for three (3) years."),
            (1, "Governing law: the laws of the State of New York."),
        ],
    ),
]


async def _doc_ids_by_name(
    factory: async_sessionmaker[AsyncSession], project_id: object
) -> dict[str, str]:
    async with factory() as db:
        rows = (
            await db.execute(
                select(File.filename, Document.id)
                .join(Document, Document.file_id == File.id)
                .where(File.project_id == project_id)
            )
        ).all()
    return {name: str(doc_id) for name, doc_id in rows}


async def test_tabular_update_eval(commit_factory: async_sessionmaker[AsyncSession]) -> None:
    registry = load_registry(_SKILLS_DIR)
    assert registry.get("tabular-review") is not None

    seeded = await seed_multi_doc_matter(
        commit_factory, area_key="commercial", docs=_NDAS, matter_name="T8 grid edit"
    )
    try:
        ids = await _doc_ids_by_name(commit_factory, seeded.project_id)
        # Pre-seed a FINALIZED grid whose nda-alpha Term is DELIBERATELY WRONG.
        async with commit_factory() as db:
            grid = TabularExecution(
                user_id=seeded.user_id,
                skill_name=None,
                status="completed",
                mode="agentic",
                project_id=seeded.project_id,
                fill_mode="fanout",
                document_ids=[ids["nda-alpha.txt"], ids["nda-beta.txt"]],
                columns=[
                    {"name": "Term", "query": "What is the term?"},
                    {"name": "Governing law", "query": "What is the governing law?"},
                ],
                results={
                    "rows": [
                        {
                            "document_id": ids["nda-alpha.txt"],
                            "document_name": "nda-alpha.txt",
                            "cells": {
                                "Term": {"value": "One (1) year", "confidence": "high"},
                                "Governing law": {
                                    "value": "Laws of England and Wales",
                                    "confidence": "high",
                                },
                            },
                        },
                        {
                            "document_id": ids["nda-beta.txt"],
                            "document_name": "nda-beta.txt",
                            "cells": {
                                "Term": {"value": "Three (3) years", "confidence": "high"},
                                "Governing law": {
                                    "value": "Laws of the State of New York",
                                    "confidence": "high",
                                },
                            },
                        },
                    ]
                },
            )
            db.add(grid)
            await db.commit()
            grid_id = str(grid.id)

        scenario = Scenario(
            id="edit-cell",
            title="Fix a wrong cell in a finalized grid → update_tabular_cells",
            note="ADR-F055 T8: conversational grid edit.",
            prompt=(
                f"You already built a comparison grid for me (grid {grid_id}). The Term for "
                "nda-alpha.txt is wrong — it says one year, but the NDA actually runs for two "
                "years. Re-read nda-alpha.txt and correct that cell in the grid."
            ),
            expect_tools=(),
            step_bound=20,
            must_include=(),
        )
        receipt = await run_scenario(scenario, seeded, skill_registry=registry, max_steps=20)

        async with commit_factory() as db:
            fresh = await db.get(TabularExecution, grid.id)
            term_cell = next(
                r["cells"]["Term"]["value"]
                for r in (fresh.results or {}).get("rows", [])
                if r["document_name"] == "nda-alpha.txt"
            )

        finding = {
            "status": receipt.status,
            "model_turns": receipt.model_turns,
            "tools_called": receipt.tools_called,
            "called_update": "update_tabular_cells" in receipt.tools_called,
            "alpha_term_after": term_cell,
            "cell_changed": term_cell != "One (1) year",
        }
        print("\n=== ADR-F055 T8 grid-edit finding ===")
        print(json.dumps(finding, indent=2, default=str))
    finally:
        await seeded.cleanup()

    # ADR-F015: assert only that the rig turned the live model; the edit is a finding.
    assert receipt.status in {"completed", "failed", "cap_exceeded", "cancelled"}
    assert receipt.model_turns > 0
