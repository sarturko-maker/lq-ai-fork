"""C3a live matter-memory — the matter remembers itself (ADR-F042, provider-marked,
CI-skipped).

Drives the production agent loop against a real model (DeepSeek on the dev stack) to
confirm the auto-write-then-correct loop works end to end with a real LLM:

1. **Run A — auto-write.** The agent is asked to note the key facts of a deal. We
   confirm it reaches for ``update_matter_memory`` and that the matter wiki
   (``projects.context_md``) is populated as a result.
2. **The human correction.** A ``human-pinned`` correction is recorded on the matter.
3. **Run B — recall + no-overwrite.** A fresh run on the same matter; we confirm it
   settles, and — the load-bearing guarantee — that the pinned correction **survives**
   the agent's own re-curation (a real run cannot drop/alter it).

Per ADR-F015 the model's craft is a recorded finding, not a pass/fail gate; the hard
assertions confirm the SYSTEM worked (loop turned, settled, tool granted) and the B2
no-overwrite invariant held. Evidence (the wiki the model wrote, tools called) lands
in the evidence dir.

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c3a \\
    pytest -m provider tests/agents/scenarios/test_matter_memory_scenario.py -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c3a"
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_SKILLS_DIR = os.environ.get("LQ_AI_SKILLS_DIR", "/skills")

_RECORD_PROMPT = (
    "We are acting for the BUYER, Northwind Trading Ltd, on the Acme MSA in this "
    "matter. The counterparty is Acme Corp and their counsel is Smith Crowell LLP. "
    "Note the key facts of this deal into the matter's working memory so you (and "
    "future runs) remember them — who we act for, the counterparty and their counsel, "
    "and the headline commercial terms you can see in the agreement (read it first)."
)

_RECALL_PROMPT = "What do we know about this matter so far? Summarise it briefly."

_PINNED_CORRECTION = (
    "Correction: we are NOT taking the auto-renewal as-is — the lawyer requires a "
    "right to terminate for convenience on 60 days' notice. Treat this as settled."
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def test_matter_remembers_itself_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = load_registry(Path(_SKILLS_DIR))
    seeded = await seed_commercial_matter(commit_factory)
    evidence: dict[str, object] = {"model": _MODEL}
    try:
        # --- Run A: the agent auto-writes the matter wiki ---------------------
        record = Scenario(
            id="matter_memory_record",
            title="Auto-write the matter wiki",
            note="Does the agent reach for update_matter_memory and populate context_md?",
            prompt=_RECORD_PROMPT,
            expect_tools=("update_matter_memory",),
            step_bound=14,
        )
        receipt_a = await run_scenario(
            record, seeded, skill_registry=registry, max_steps=40, model_alias=_MODEL
        )
        async with commit_factory() as db:
            proj = await db.get(Project, seeded.project_id)
            wiki_after_a = (proj.context_md or "") if proj else ""
        evidence["run_a"] = {
            "status": receipt_a.status,
            "tools_called": receipt_a.tools_called,
            "wiki_after_a": wiki_after_a,
        }

        # --- The human correction (the only pin writer is the human) ---------
        async with commit_factory() as db:
            db.add(
                MatterMemoryEntry(
                    project_id=seeded.project_id,
                    user_id=seeded.user_id,
                    kind="correction",
                    body_md=_PINNED_CORRECTION,
                    trust="human-pinned",
                )
            )
            await db.commit()

        # --- Run B: recall + the no-overwrite guarantee under a real run -----
        recall = Scenario(
            id="matter_memory_recall",
            title="Recall the matter + survive re-curation",
            note="A fresh run sees the wiki + pinned correction; the pin must survive.",
            prompt=_RECALL_PROMPT,
            step_bound=14,
        )
        receipt_b = await run_scenario(
            recall, seeded, skill_registry=registry, max_steps=40, model_alias=_MODEL
        )
        async with commit_factory() as db:
            pins = (
                (
                    await db.execute(
                        select(MatterMemoryEntry).where(
                            MatterMemoryEntry.project_id == seeded.project_id,
                            MatterMemoryEntry.trust == "human-pinned",
                        )
                    )
                )
                .scalars()
                .all()
            )
            proj = await db.get(Project, seeded.project_id)
            wiki_after_b = (proj.context_md or "") if proj else ""
        evidence["run_b"] = {
            "status": receipt_b.status,
            "tools_called": receipt_b.tools_called,
            "answer_excerpt": (receipt_b.final_answer or "")[:600],
            "wiki_after_b": wiki_after_b,
            "pinned_correction_count": len(pins),
            "pinned_bodies": [p.body_md for p in pins],
        }

        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (_EVIDENCE_DIR / "live-matter-memory.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )

        # --- Hard assertions: the SYSTEM worked + B2 held --------------------
        assert receipt_a.status == "completed", receipt_a.error
        assert "update_matter_memory" in receipt_a.tools_called, receipt_a.tools_called
        assert wiki_after_a.strip(), "the agent left the matter wiki empty"
        assert receipt_b.status == "completed", receipt_b.error
        # B2 no-overwrite: the human-pinned correction survives a real re-curation run.
        assert len(pins) == 1
        assert pins[0].body_md == _PINNED_CORRECTION
    finally:
        await seeded.cleanup()
