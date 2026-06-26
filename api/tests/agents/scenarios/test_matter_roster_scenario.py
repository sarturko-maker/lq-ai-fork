"""ADR-F048 live authorship roster — the agent records who-is-who (provider-marked, CI-skipped).

Drives the production agent loop against a real model (DeepSeek on the dev stack) to
confirm the roster surface works end to end with a real LLM: the user TELLS the agent
who is who, and the agent reaches for ``record_matter_participant`` to write the roster
(matched per ADR-F048's auto-write — ``trust='inferred'``).

The classification (`classify_author` → ours/counterparty/unknown), the human-wins guard,
and the hand-back bucketing are deterministic and fully covered by the unit + integration
tests (no model needed). Per ADR-F015 the model's craft (does it choose to call the tool)
is a recorded finding; the hard assertions confirm the SYSTEM worked (loop turned, settled,
tool granted, rows written with the tool-fixed ``trust='inferred'``).

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/authorship-slice1 \\
    pytest -m provider tests/agents/scenarios/test_matter_roster_scenario.py -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.matter_roster_tools import live_participants
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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "authorship-slice1"
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_SKILLS_DIR = os.environ.get("LQ_AI_SKILLS_DIR", "/skills")

_ROSTER_PROMPT = (
    "Before anything else, record who is who on this matter using the "
    "record_matter_participant tool — one call per person:\n"
    "1. We act for Northwind Trading Ltd (our client) — side 'ours'.\n"
    "2. The other side's lead counsel is Mark Counsel at Beta LLP, who writes under "
    "the email mcounsel@beta.example — side 'counterparty'.\n"
    "Give each a short source such as 'matter brief'. Then stop — do not search the "
    "documents."
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def test_agent_records_matter_roster_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = load_registry(Path(_SKILLS_DIR))
    seeded = await seed_commercial_matter(commit_factory)
    evidence: dict[str, object] = {"model": _MODEL}
    try:
        record = Scenario(
            id="matter_roster_record",
            title="Record the matter's who-is-who roster",
            note="Does the agent reach for record_matter_participant from a user statement?",
            prompt=_ROSTER_PROMPT,
            expect_tools=("record_matter_participant",),
            step_bound=10,
        )
        receipt = await run_scenario(
            record, seeded, skill_registry=registry, max_steps=40, model_alias=_MODEL
        )

        async with commit_factory() as db:
            roster = await live_participants(db, seeded.project_id)

        def _dump(p: object) -> dict[str, object]:
            return {
                "display_name": getattr(p, "display_name", None),
                "side": getattr(p, "side", None),
                "role_label": getattr(p, "role_label", None),
                "organization": getattr(p, "organization", None),
                "aliases": list(getattr(p, "aliases", []) or []),
                "trust": getattr(p, "trust", None),
            }

        evidence["run"] = {
            "status": receipt.status,
            "tools_called": receipt.tools_called,
            "participant_count": len(roster),
            "roster": [_dump(p) for p in roster],
            "sides": sorted({p.side for p in roster}),
        }
        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        (_EVIDENCE_DIR / "live-matter-roster.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )

        # --- Hard assertions: the SYSTEM worked + provenance is tool-fixed --------
        assert receipt.status == "completed", receipt.error
        assert "record_matter_participant" in receipt.tools_called, receipt.tools_called
        assert roster, "the agent recorded no participants"
        for p in roster:
            assert p.trust == "inferred"  # an agent write is never a confirmed (human) pin
            assert p.side in {"ours", "counterparty", "unknown"}
    finally:
        await seeded.cleanup()
