"""C7b — live drafter/reviewer fan-out + reconciliation (provider-marked, ADR-F034/F015).

Drive the REAL commercial agent (a gateway model) on a multi-head deal and observe
whether it fans out the ``clause-drafter`` / ``clause-reviewer`` roster (migration 0073)
and calls ``reconcile_positions`` before summarising. Per ADR-F015 a shape-miss (it
didn't fan out, or didn't reconcile) is a recorded FINDING, not a failure — the
deterministic mechanics are pinned in ``test_agent_composition.py`` (roster nesting) and
``test_commercial_tools.py`` (the reconcile gate + receipt); this proves the live loop
turns the real model through the new roster + tool end-to-end.

    DATABASE_URL=... LQ_AI_GATEWAY_KEY=... LQ_AI_SCENARIO_MODEL=deepseek \\
      pytest -m provider tests/agents/scenarios/test_commercial_fan_out_scenario.py -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.composition import compose_and_execute_run
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.project import MatterMemoryEntry
from app.schemas.agent_runs import AgentRunStepKind
from app.skills import load_registry
from tests.agents.scenarios.harness import seed_commercial_matter

pytestmark = [
    pytest.mark.provider,
    pytest.mark.skipif(
        "LQ_AI_GATEWAY_KEY" not in os.environ,
        reason="needs a live gateway (LQ_AI_GATEWAY_KEY unset)",
    ),
]

# Overridable so a containerized run can point the evidence at a mounted host path.
_EVIDENCE = (
    Path(os.environ["UX_B1_EVIDENCE_DIR"])
    if os.environ.get("UX_B1_EVIDENCE_DIR")
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c7b"
)

_PROMPT = (
    "Read the Acme MSA ONCE, then review it across its material heads. Draft our "
    "client-protective position on EACH of liability, indemnity, and term by delegating one "
    "clause-drafter per head — pass each drafter the relevant clause text directly so it does "
    "NOT re-search the matter; one focused proposal each. Then you MUST call the "
    "reconcile_positions tool with one position per head (liability, indemnity, term), "
    "supplying a resolution for any head where drafts diverge, BEFORE you write the summary. "
    "We are the Customer; keep liability capped and carve out confidentiality, data and IP."
)
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}


async def test_commercial_fan_out_and_reconcile_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    alias = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
    registry = load_registry(Path("/skills"))
    seeded = await seed_commercial_matter(commit_factory)
    try:
        async with seeded.factory() as db:
            thread = AgentThread(
                user_id=seeded.user_id, project_id=seeded.project_id, title="C7b fan-out"
            )
            db.add(thread)
            await db.flush()
            run = AgentRun(
                user_id=seeded.user_id,
                thread_id=thread.id,
                project_id=seeded.project_id,
                status="running",
                prompt=_PROMPT,
                model_alias=alias,
                max_steps=80,  # fan-out headroom: parent → N drafters → reconcile → summary
            )
            db.add(run)
            await db.commit()
            run_id = run.id

        await compose_and_execute_run(
            run_id=run_id,
            session_factory_provider=lambda: seeded.factory,
            checkpointer_provider=lambda: None,
            skill_registry_provider=lambda: registry,
        )

        async with seeded.factory() as db:
            run_row = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
            steps = (
                (
                    await db.execute(
                        select(AgentRunStep)
                        .where(AgentRunStep.run_id == run_id)
                        .order_by(AgentRunStep.seq)
                    )
                )
                .scalars()
                .all()
            )
            facts = (
                (
                    await db.execute(
                        select(MatterMemoryEntry).where(
                            MatterMemoryEntry.project_id == seeded.project_id,
                            MatterMemoryEntry.kind == "fact",
                        )
                    )
                )
                .scalars()
                .all()
            )

        tool_calls = [
            s.name for s in steps if s.kind == AgentRunStepKind.tool_call.value and s.name
        ]
        task_steps = [
            s for s in steps if s.kind == AgentRunStepKind.tool_call.value and s.name == "task"
        ]
        task_ids = {s.id for s in task_steps}
        nested = [s for s in steps if s.parent_step_id in task_ids]
        reconcile_calls = [s for s in steps if s.name == "reconcile_positions"]
        receipts = [f.body_md for f in facts if "Reconciled" in f.body_md]

        evidence = {
            "model_alias": alias,
            "status": run_row.status,
            "step_count": len(steps),
            "tool_calls": tool_calls,
            "task_delegations": len(task_steps),
            "nested_under_task": len(nested),
            "reconcile_positions_calls": len(reconcile_calls),
            "reconciliation_receipts": receipts,
            "final_answer_excerpt": (run_row.final_answer or "")[:1500],
        }
        _EVIDENCE.mkdir(parents=True, exist_ok=True)
        (_EVIDENCE / "fan-out-reconcile.json").write_text(json.dumps(evidence, indent=2))

        # RIG assertions only (ADR-F015): the loop turned the real model to a terminal
        # state. The fan-out / reconcile SHAPE is a recorded finding in the evidence file.
        assert run_row.status in _TERMINAL, run_row.error
        assert any(s.kind == AgentRunStepKind.model_turn.value for s in steps), "no model turn"
    finally:
        await seeded.cleanup()
