"""C3b-2 live matter-memory consolidation — the agent consolidates the ledger + wiki
(ADR-F043, provider-marked, CI-skipped).

Drives the production agent loop against a real model (DeepSeek on the dev stack) to
confirm the gateway-routed consolidation tool works end to end with a real LLM:

* We seed a matter whose fact ledger has an obvious duplicate and a stale draft fact,
  plus a starting wiki, then ask the agent to consolidate the matter's memory.
* We confirm it reaches for ``consolidate_matter_memory``, the run settles, and the
  ledger/wiki are reconciled (supersede-only — superseded facts keep their history).

Per ADR-F015 the model's craft (exactly which facts it merges) is a recorded finding,
not a gate; the hard assertions confirm the SYSTEM worked (the loop turned, settled, the
tool was granted + routed one gateway call, no crash). The one egress call is the
ADR-F010 obligation this slice discharges.

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_MATTER_CONSOLIDATION_MODEL=deepseek \\
    LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c3b2 \\
    pytest -m provider tests/agents/scenarios/test_matter_consolidation_scenario.py -s
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.matter_fact_tools import live_facts
from app.models.project import MatterMemoryEntry, Project
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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c3b2"
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_SKILLS_DIR = os.environ.get("LQ_AI_SKILLS_DIR", "/skills")

_CONSOLIDATE_PROMPT = (
    "This matter's memory has drifted: the fact ledger has a duplicate party fact and a "
    "stale draft term. Consolidate the matter's memory now by calling the "
    "consolidate_matter_memory tool — it will dedupe and supersede the stale facts and "
    "tidy the wiki. Then briefly tell me what it changed. Do not record new facts by hand."
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_drifted_ledger(
    factory: async_sessionmaker[AsyncSession], project_id: uuid.UUID, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """Plant a starting wiki + 3 facts (a duplicate pair + a stale draft term)."""
    async with factory() as db:
        proj = await db.get(Project, project_id)
        assert proj is not None
        proj.context_md = "Deal: Acme MSA. Buyer = us. (notes are messy)"
        ids: list[uuid.UUID] = []
        for body, ftype in (
            ("We act for the buyer, Northwind Trading Ltd.", "party"),
            ("Acting for the buyer (Northwind).", "party"),  # duplicate of the above
            ("Liability cap is 1 month of fees (draft only).", "term"),  # stale draft
        ):
            f = MatterMemoryEntry(
                project_id=project_id,
                user_id=user_id,
                kind="fact",
                body_md=body,
                trust="normal",
                author="agent",
                fact_type=ftype,
                valid_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            db.add(f)
            await db.flush()
            ids.append(f.id)
        await db.commit()
        return ids


async def test_agent_consolidates_matter_memory_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = load_registry(Path(_SKILLS_DIR))
    seeded = await seed_commercial_matter(commit_factory)
    seeded_ids = await _seed_drifted_ledger(commit_factory, seeded.project_id, seeded.user_id)
    evidence: dict[str, object] = {
        "model": _MODEL,
        "consolidation_model": os.environ.get("LQ_AI_MATTER_CONSOLIDATION_MODEL", "smart"),
        "seeded_fact_ids": [str(i) for i in seeded_ids],
    }
    try:
        scenario = Scenario(
            id="matter_consolidate",
            title="Consolidate the matter's memory",
            note="Does the agent reach for consolidate_matter_memory and reconcile the ledger?",
            prompt=_CONSOLIDATE_PROMPT,
            expect_tools=("consolidate_matter_memory",),
            step_bound=12,
        )
        receipt = await run_scenario(
            scenario, seeded, skill_registry=registry, max_steps=40, model_alias=_MODEL
        )

        async with commit_factory() as db:
            all_facts = (
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
            live = await live_facts(db, seeded.project_id)
            proj = await db.get(Project, seeded.project_id)
            wiki = proj.context_md if proj is not None else None

        superseded = [f for f in all_facts if f.invalid_at is not None]
        evidence["run"] = {
            "status": receipt.status,
            "tools_called": receipt.tools_called,
            "total_fact_rows": len(all_facts),
            "live_fact_count": len(live),
            "superseded_count": len(superseded),
            "live_facts": [f.body_md for f in live],
            "wiki": wiki,
        }
        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (_EVIDENCE_DIR / "live-matter-consolidation.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )

        # --- Hard assertions: the SYSTEM worked (craft is a finding, ADR-F015) --------
        assert receipt.status == "completed", receipt.error
        assert "consolidate_matter_memory" in receipt.tools_called, receipt.tools_called
        # Supersede-only: no fact row is ever deleted (the 3 seeded rows still exist; a
        # merge may add a 4th). History is preserved whatever the model decided.
        assert len(all_facts) >= len(seeded_ids)
        # The matter still has a non-empty wiki after consolidation.
        assert wiki and wiki.strip()
    finally:
        await seeded.cleanup()
