"""Track-A agentic eval (F2 slice E1, ADR-F049; provider-marked, CI-skipped).

The subjective arm of the eval-first plan: run each Track-A scenario live
(DeepSeek agent), score the deterministic L1 metrics for free, and emit a
**masked judging packet** per run for the L2 faithfulness judgement. The judge
is the orchestrator (Claude) over the frozen packets by default
(``LQ_AI_JUDGE_MODE=claude``) — it never sees the source docs, the agent's
instructions, or the run id, only what the packet carries; the gateway fallback
(``LQ_AI_JUDGE_MODE=gateway``, ``deepseek-pro``) grades inline for automated /
reproducible runs. Per ADR-F015 the rates are findings, not gates — the only
hard assertions are rig hygiene (every run terminal, every packet emitted).

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_TRACK_A_N=10 LQ_AI_JUDGE_MODE=claude \\
    LQ_AI_TRACK_A_EVIDENCE_DIR=/repo/docs/fork/evidence/retrieval-eval/track-a \\
    LQ_AI_SKILLS_DIR=/skills \\
    pytest -m provider tests/agents/scenarios/test_track_a_eval.py -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from evals.runner import fetch_steps
from evals.scoring import score_all
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.skills import SkillRegistry, load_registry
from tests.agents.scenarios.harness import run_scenario, seed_multi_doc_matter
from tests.agents.scenarios.scenarios import Scenario
from tests.agents.scenarios.track_a_fixtures import TRACK_A_SCENARIOS, TrackAScenario
from tests.agents.scenarios.track_a_lib import build_judging_packet, masked_judge

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_N = int(os.environ.get("LQ_AI_TRACK_A_N", "1"))
_JUDGE_MODE = os.environ.get("LQ_AI_JUDGE_MODE", "claude")  # claude | gateway
_JUDGE_MODEL = os.environ.get("LQ_AI_JUDGE_MODEL", "deepseek-pro")
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}
_EVIDENCE_DIR = (
    Path(os.environ["LQ_AI_TRACK_A_EVIDENCE_DIR"])
    if os.environ.get("LQ_AI_TRACK_A_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4]
    / "docs"
    / "fork"
    / "evidence"
    / "retrieval-eval"
    / "track-a"
)
_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


def _followup_scenario(ts: TrackAScenario) -> Scenario:
    assert ts.followup_prompt is not None
    return Scenario(
        id=f"{ts.scenario.id}_followup",
        title=f"{ts.scenario.title} — thread 2",
        note="Thread 2 (fresh thread, same matter): ask for the thread-1 fact.",
        prompt=ts.followup_prompt,
        step_bound=ts.scenario.step_bound,
    )


async def _run_once(
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    ts: TrackAScenario,
    rep: int,
    registry: SkillRegistry,
    packets_dir: Path,
) -> dict[str, object]:
    """One seed → run → (A5: validity check + thread 2) → L1 → packet → (gateway
    judge) cycle. Returns a result row; the seeded rows are torn down."""
    seeded = await seed_multi_doc_matter(
        factory, area_key=ts.area_key, docs=ts.docs, matter_name=ts.matter_name
    )
    row: dict[str, object] = {"scenario": ts.scenario.id, "rep": rep, "expected": ts.expected}
    try:
        receipt = await run_scenario(
            ts.scenario, seeded, skill_registry=registry, model_alias=_MODEL, max_steps=ts.max_steps
        )
        row["status"] = receipt.status
        row["model_turns"] = receipt.model_turns

        if ts.followup_prompt is not None:
            # A5: the planted fact must NOT have been persisted to shared matter
            # memory in thread 1 (else thread 2 sees it via memory, not recall).
            t1_steps = await fetch_steps(engine, receipt.run_id)
            wrote = sorted(
                {
                    str(s["name"])
                    for s in t1_steps
                    if s["kind"] == "tool_call" and s["name"] in ts.fixture_invalid_if_fired
                }
            )
            row["t1_memory_writes"] = wrote
            row["fixture_valid"] = not wrote
            receipt = await run_scenario(
                _followup_scenario(ts),
                seeded,
                skill_registry=registry,
                model_alias=_MODEL,
                max_steps=ts.max_steps,
            )
            row["status_followup"] = receipt.status

        steps = await fetch_steps(engine, receipt.run_id)
        l1 = score_all(ts.metrics, steps, receipt.final_answer)
        row["l1"] = l1
        packet = build_judging_packet(
            scenario_id=ts.scenario.id,
            rubric=ts.rubric,
            expectations=ts.expectations,
            steps=steps,
            final_answer=receipt.final_answer,
        )
        record: dict[str, object] = {
            "scenario": ts.scenario.id,
            "rep": rep,
            "expected": ts.expected,
            "agent_model": _MODEL,
            "l1": l1,
            "packet": packet.to_dict(),
        }
        if _JUDGE_MODE == "gateway":
            try:
                verdict = await masked_judge(judge_model_alias=_JUDGE_MODEL, packet=packet)
                record["verdict"] = verdict.to_dict()
                record["judge_model"] = _JUDGE_MODEL
                row["verdict"] = verdict.verdict
            except Exception as exc:  # ADR-F015: a judge failure is a finding, not a crash
                record["judge_error"] = f"{type(exc).__name__}: {exc}"
                row["judge_error"] = record["judge_error"]

        (packets_dir / f"{ts.scenario.id}-rep{rep}.json").write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        row["packet_written"] = True
        return row
    finally:
        await seeded.cleanup()


async def test_track_a_eval(
    commit_factory: async_sessionmaker[AsyncSession], test_engine: AsyncEngine
) -> None:
    packets_dir = _EVIDENCE_DIR / "packets"
    packets_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(_SKILLS_DIR)  # the real /skills registry → production composition

    results: list[dict[str, object]] = []
    for ts in TRACK_A_SCENARIOS:
        for rep in range(1, _N + 1):
            results.append(
                await _run_once(commit_factory, test_engine, ts, rep, registry, packets_dir)
            )

    report = {
        "agent_model": _MODEL,
        "n": _N,
        "judge_mode": _JUDGE_MODE,
        "judge_model": _JUDGE_MODEL if _JUDGE_MODE == "gateway" else "claude-orchestrator",
        "scenarios": [
            {"id": ts.scenario.id, "expected": ts.expected, "title": ts.scenario.title}
            for ts in TRACK_A_SCENARIOS
        ],
        "results": results,
    }
    (_EVIDENCE_DIR / "track-a-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    # Rig assertions only (ADR-F015): every run reached a terminal state and a
    # masked packet was emitted for every cycle. Verdicts/rates are findings the
    # maintainer (and the orchestrator judge) read from the frozen packets.
    assert results, "no eval runs executed"
    for r in results:
        assert r.get("status") in _TERMINAL, r
        assert r.get("packet_written") is True, r
        if "status_followup" in r:
            assert r["status_followup"] in _TERMINAL, r
