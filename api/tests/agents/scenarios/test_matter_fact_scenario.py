"""C3b-1 live matter fact-ledger — the agent records dated facts (ADR-F042,
provider-marked, CI-skipped).

Drives the production agent loop against a real model (DeepSeek on the dev stack) to
confirm the typed fact-ledger surface works end to end with a real LLM:

* **Run A — record facts.** The agent is asked to record the key durable facts of a
  deal into the matter's fact ledger (and to supersede a fact if it finds one changed).
  We confirm it reaches for ``record_matter_fact`` and that ``kind='fact'`` rows are
  written with the tool-fixed provenance (``author='agent'``, ``trust='normal'``).

The bi-temporal supersede + the "what did we believe at signing" as-of query are
deterministic store logic, fully covered by the unit tests (no model needed); here we
additionally run the live ``facts_valid_at`` query over whatever the agent recorded and
dump it as evidence. Per ADR-F015 the model's craft is a recorded finding, not a gate;
the hard assertions confirm the SYSTEM worked (loop turned, settled, tool granted, rows
written with the right provenance).

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c3b1 \\
    pytest -m provider tests/agents/scenarios/test_matter_fact_scenario.py -s
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.matter_fact_tools import facts_valid_at
from app.models.project import MatterMemoryEntry
from app.skills import load_registry
from tests.agents.scenarios.harness import run_scenario, seed_commercial_matter
from tests.agents.scenarios.scenarios import Scenario

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_EVIDENCE_DIR = (
    Path(os.environ["UX_B1_EVIDENCE_DIR"])
    if os.environ.get("UX_B1_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c3b1"
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_SKILLS_DIR = os.environ.get("LQ_AI_SKILLS_DIR", "/skills")

_RECORD_PROMPT = (
    "Set up this matter's fact ledger now using the record_matter_fact tool. Record "
    "these durable facts FIRST, each as its own separate record_matter_fact call, "
    "before doing anything else:\n"
    "1. We act for the BUYER, Northwind Trading Ltd (fact_type 'party').\n"
    "2. The counterparty is Acme Corp (fact_type 'party').\n"
    "3. Acme's counsel is Smith Crowell LLP (fact_type 'party').\n"
    "Give each a short source such as 'matter brief'. Then, ONLY if you can find it "
    "quickly in the agreement, also record the headline liability cap as a 'term' "
    "fact with its source. Keep it brief and stop once the key facts are recorded — "
    "do not keep searching the documents."
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def test_agent_records_matter_facts_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = load_registry(Path(_SKILLS_DIR))
    seeded = await seed_commercial_matter(commit_factory)
    evidence: dict[str, object] = {"model": _MODEL}
    try:
        record = Scenario(
            id="matter_fact_record",
            title="Record the matter's dated facts",
            note="Does the agent reach for record_matter_fact and populate kind='fact' rows?",
            prompt=_RECORD_PROMPT,
            expect_tools=("record_matter_fact",),
            step_bound=12,
        )
        receipt = await run_scenario(
            record, seeded, skill_registry=registry, max_steps=50, model_alias=_MODEL
        )

        async with commit_factory() as db:
            facts = (
                (
                    await db.execute(
                        select(MatterMemoryEntry)
                        .where(
                            MatterMemoryEntry.project_id == seeded.project_id,
                            MatterMemoryEntry.kind == "fact",
                        )
                        .order_by(MatterMemoryEntry.created_at, MatterMemoryEntry.id)
                    )
                )
                .scalars()
                .all()
            )
            # The live as-of query over whatever the agent recorded (read-only).
            as_of_now = await facts_valid_at(db, seeded.project_id, datetime.now(UTC))

        def _dump(f: MatterMemoryEntry) -> dict[str, object]:
            return {
                "id": str(f.id),
                "fact_type": f.fact_type,
                "body": f.body_md,
                "source": f.source_citation,
                "author": f.author,
                "trust": f.trust,
                "valid_at": f.valid_at.isoformat() if f.valid_at else None,
                "invalid_at": f.invalid_at.isoformat() if f.invalid_at else None,
                "superseded_by": str(f.superseded_by) if f.superseded_by else None,
            }

        superseded = [f for f in facts if f.invalid_at is not None]
        evidence["run_a"] = {
            "status": receipt.status,
            "tools_called": receipt.tools_called,
            "fact_count": len(facts),
            "facts": [_dump(f) for f in facts],
            "agent_performed_supersede": bool(superseded),
            "live_facts_as_of_now": [f.body_md for f in as_of_now],
        }
        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (_EVIDENCE_DIR / "live-matter-facts.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )

        # --- Hard assertions: the SYSTEM worked + provenance is tool-fixed --------
        assert receipt.status == "completed", receipt.error
        assert "record_matter_fact" in receipt.tools_called, receipt.tools_called
        assert facts, "the agent recorded no facts"
        for f in facts:
            assert f.author == "agent"  # tool-fixed — no agent path mints a human author
            assert f.trust == "normal"  # never human-pinned
            assert f.fact_type in {"party", "term", "date", "decision", "open_point", "fact"}
        # The as-of query returns only currently-valid facts (superseded ones excluded).
        assert len(as_of_now) == len(facts) - len(superseded)
    finally:
        await seeded.cleanup()
