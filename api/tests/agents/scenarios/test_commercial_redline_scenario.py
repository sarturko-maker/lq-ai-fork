"""C4 live redline — the canonical single evidence run (ADR-F031, provider-marked,
CI-skipped).

Seeds the **real** SecureScan MSA `.docx` in object storage, drives the production
agent loop, then captures what the model produced: the redlined `.docx`, a readable
reconstruction (`[-del-][+ins+]`), the accept-to-clean text, and a craft-judge
verdict — all to the evidence dir. Per ADR-F015 the model's redline QUALITY is a
recorded finding, not a pass/fail gate; the hard assertions only confirm the SYSTEM
worked (the loop turned and settled). The repeated, **rate-measuring** version is
`test_commercial_redline_eval.py` (C8).

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c4/live \\
    pytest -m provider tests/agents/scenarios/test_commercial_redline_scenario.py -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.redline_render import docx_text, reconstruct_redline_text
from app.agents.redline_service import RedlineService
from tests.agents.scenarios.commercial_redline_lib import (
    RedlineScenarioDoc,
    capture_redline,
    craft_judge,
    seed_doc_matter,
)
from tests.agents.scenarios.harness import run_scenario
from tests.agents.scenarios.scenarios import Scenario
from tests.agents.scenarios.securescan_msa import (
    MSA_FILENAME,
    build_msa_docx,
    msa_normalized_text,
)

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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c4" / "live"
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

_REDLINE_PROMPT = (
    "You are our in-house commercial counsel and we are the CUSTOMER. Review the "
    f'attached vendor SaaS agreement "{MSA_FILENAME}" and redline it to protect us — '
    "apply your changes as tracked changes using apply_redline. Make surgical, "
    "balanced edits (carve-outs, deemed-direct, super-caps where appropriate); do not "
    "rip-and-replace whole clauses. Work through EVERY one-sided clause: the liability "
    "cap, the one-sided indemnity, the IP assignment, the Customer Data licence, the "
    "warranty disclaimer, the unilateral fee increase and the auto-renewal/no-termination "
    "term. Read the whole agreement first, then apply ALL your edits in a SINGLE "
    "apply_redline call (it takes a batch of many edits and re-redlines the original on "
    "each call, so one call must cover everything)."
)

SECURESCAN_DOC = RedlineScenarioDoc(
    id="securescan_saas_msa",
    filename=MSA_FILENAME,
    build_docx=build_msa_docx,
    normalized_text=msa_normalized_text,
    prompt=_REDLINE_PROMPT,
    boilerplate_bare=("shall indemnify, defend and hold harmless", "shall not exceed"),
)

REDLINE_SCENARIO = Scenario(
    id="commercial_redline_msa",
    title="Surgical redline of a vendor-favoured SaaS MSA",
    note="Does the agent read the MSA, then apply_redline with surgical, balanced edits?",
    prompt=_REDLINE_PROMPT,
    expect_tools=("apply_redline",),
    step_bound=100,
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def test_commercial_redline_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await seed_doc_matter(commit_factory, SECURESCAN_DOC)
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (_EVIDENCE_DIR / MSA_FILENAME).write_bytes(build_msa_docx())

    try:
        receipt = await run_scenario(REDLINE_SCENARIO, seeded, model_alias=_MODEL, max_steps=100)

        report: dict[str, object] = {"model": _MODEL, **receipt.to_dict()}
        captured = await capture_redline(commit_factory, seeded.user_id, seeded.project_id)
        if captured is not None:
            redlined_bytes, redlined_name = captured
            (_EVIDENCE_DIR / redlined_name).write_bytes(redlined_bytes)
            redline_view = reconstruct_redline_text(redlined_bytes)
            accepted = docx_text(RedlineService().accept_all(redlined_bytes))
            (_EVIDENCE_DIR / "redline-reconstruction.txt").write_text(
                redline_view, encoding="utf-8"
            )
            (_EVIDENCE_DIR / "accepted-clean.txt").write_text(accepted, encoding="utf-8")
            report["redlined_file"] = redlined_name
            try:
                verdict = await craft_judge(_MODEL, msa_normalized_text(), redline_view, accepted)
                report["judge_rating"] = verdict.verdict
                report["judge_surgical"] = verdict.surgical
                (_EVIDENCE_DIR / "judge-verdict.md").write_text(verdict.text, encoding="utf-8")
            except Exception as exc:
                report["judge_error"] = f"{type(exc).__name__}: {exc}"
        else:
            report["redlined_file"] = None

        (_EVIDENCE_DIR / "redline-report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

        # Rig assertions only (ADR-F015): the loop turned the model and settled.
        assert receipt.status in _TERMINAL, receipt.status
        assert receipt.model_turns > 0, "the model never turned"
        # The system finding the maintainer reviews lives in the evidence dir.
    finally:
        await seeded.cleanup()
