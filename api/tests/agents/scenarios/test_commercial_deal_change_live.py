"""C5b-3 live deal-change frames — the verdict chips fire end-to-end (ADR-F032,
provider-marked, CI-skipped).

The deterministic chain is covered elsewhere (the ledger drain, the publisher frame,
the cross-process round-trip, the web parser + chip render). This is the INTEGRATION
proof on the live stack: the REAL agent, responding to a counterparty markup through
``respond_to_counterparty``, causes the runner to drain the deal-change ledger and
publish one transient ``data-deal-change`` frame per verdict onto the run stream — the
exact frames the cockpit renders as live chips.

A ``RunStreamBroker`` is subscribed BEFORE the run executes (the frames are transient —
not seeded to a late subscriber), then the captured frames are dumped to the evidence
dir. Rig assertions only (ADR-F015): at least one verdict frame fired, each carries a
ref + a taxonomy verdict (never raw clause text).

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c5b3 \\
    pytest -m provider tests/agents/scenarios/test_commercial_deal_change_live.py -s
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.composition import compose_and_execute_run
from app.agents.stream import RunStreamBroker
from app.models.agent_run import AgentRun, AgentThread
from app.skills import load_registry
from tests.agents.scenarios.commercial_redline_lib import seed_doc_matter
from tests.agents.scenarios.test_commercial_negotiation_scenario import (
    _MODEL,
    _PROMPT,
    NEGOTIATION_DOC,
)

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_VERDICTS = {"accept", "reject", "counter", "leave_open", "escalate", "reply"}

_EVIDENCE_DIR = (
    Path(os.environ["UX_B1_EVIDENCE_DIR"])
    if os.environ.get("UX_B1_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c5b3"
)
_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def test_commercial_deal_change_frames_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await seed_doc_matter(commit_factory, NEGOTIATION_DOC)
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    registry = load_registry(_SKILLS_DIR)
    try:
        async with commit_factory() as db:
            thread = AgentThread(
                user_id=seeded.user_id, project_id=seeded.project_id, title="C5b-3 deal-change"
            )
            db.add(thread)
            await db.flush()
            run = AgentRun(
                user_id=seeded.user_id,
                thread_id=thread.id,
                project_id=seeded.project_id,
                status="running",
                prompt=_PROMPT,
                model_alias=_MODEL,
                max_steps=100,
            )
            db.add(run)
            await db.commit()
            run_id = run.id

        # Subscribe BEFORE the run — deal-change frames are transient (a late
        # subscriber misses them); an in-process broker is the cockpit's stand-in.
        broker = RunStreamBroker()
        queue = broker.subscribe(run_id)

        started = time.monotonic()
        await compose_and_execute_run(
            run_id=run_id,
            session_factory_provider=lambda: commit_factory,
            checkpointer_provider=lambda: None,
            skill_registry_provider=lambda: registry,
            broker=broker,
        )
        latency = time.monotonic() - started

        parts: list[Any] = []
        while not queue.empty():
            parts.append(queue.get_nowait())
        deal_frames = [
            p for p in parts if isinstance(p, dict) and p.get("type") == "data-deal-change"
        ]

        report = {
            "model": _MODEL,
            "latency_seconds": round(latency, 1),
            "deal_change_frames": len(deal_frames),
            "frames": [p["data"] for p in deal_frames],
        }
        (_EVIDENCE_DIR / "deal-change-frames.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

        # Rig (ADR-F015): the integration link fired — the live agent's response drove
        # at least one verdict chip, each a ref + a taxonomy verdict, transient, no
        # clause text on the wire.
        assert deal_frames, "no data-deal-change frame fired on the live run"
        for p in deal_frames:
            assert p.get("transient") is True
            data = p["data"]
            assert isinstance(data.get("ref"), str) and data["ref"]
            assert data.get("verdict") in _VERDICTS, data.get("verdict")
    finally:
        await seeded.cleanup()
