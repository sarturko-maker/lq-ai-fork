"""C5a live negotiation round — the provable second round (ADR-F032, provider-marked,
CI-skipped).

Seeds a counterparty-marked-up NDA (their tracked changes + a comment), drives the
production agent loop, and checks the SYSTEM worked: the agent called
``extract_counterparty_position`` then ``respond_to_counterparty``, the coverage gate
held (every change/comment addressed exactly once — the run could not settle otherwise),
and a response ``.docx`` with our tracked changes + threaded comments was produced. The
craft of the response (which verdict per clause) is a recorded finding, not a gate
(ADR-F015). Evidence → the evidence dir.

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c5a \\
    pytest -m provider tests/agents/scenarios/test_commercial_negotiation_scenario.py -s
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app import storage
from app.agents.negotiation_service import read_state_of_play
from app.agents.redline_render import reconstruct_redline_text
from app.models.file import File
from app.skills import load_registry
from tests.agents.scenarios.commercial_redline_lib import RedlineScenarioDoc, seed_doc_matter
from tests.agents.scenarios.harness import run_scenario
from tests.agents.scenarios.negotiation_nda import (
    NDA_FILENAME,
    build_counterparty_nda_docx,
    nda_clean_text,
)
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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c5a"
)
_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

_PROMPT = (
    "You are our in-house commercial counsel. The counterparty has returned our mutual "
    f'NDA "{NDA_FILENAME}" with their tracked changes and a comment. Our position: '
    "confidentiality must stay MUTUAL (not one-directional); the survival period floor is "
    "three (3) years and our ceiling is five (5) years — anything perpetual/indefinite is "
    "BELOW our floor and must be ESCALATED to the supervisor, never silently conceded; "
    "minor clarifications that don't shift risk are fine to accept.\n\n"
    "First call extract_counterparty_position on the document to read their markup. Then "
    "call respond_to_counterparty with exactly ONE decision for EVERY change and EVERY "
    "comment it lists — accept the benign clarification, reject or counter the one-sided "
    "edits (you draft the replacement language for a counter), escalate the below-floor "
    "demand, and reply to their comment. You must address every item; the tool will reject "
    "your response if anything is left unaddressed."
)

NEGOTIATION_DOC = RedlineScenarioDoc(
    id="aegis_counterparty_nda",
    filename=NDA_FILENAME,
    build_docx=build_counterparty_nda_docx,
    normalized_text=nda_clean_text,
    prompt=_PROMPT,
)

NEGOTIATION_SCENARIO = Scenario(
    id="commercial_negotiation_round2",
    title="Respond to a counterparty's marked-up NDA — full coverage, escalate below floor",
    note="Does the agent extract the counterparty's position, then respond to every change/comment?",
    prompt=_PROMPT,
    expect_tools=("extract_counterparty_position", "respond_to_counterparty"),
    step_bound=80,
)


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _capture_response(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, project_id: uuid.UUID
) -> tuple[bytes, str] | None:
    """Download the agent's response ``.docx`` (most recent), matter-scoped (ADR-F035)."""
    async with factory() as db:
        row = (
            await db.execute(
                select(File.storage_path, File.filename)
                .where(
                    File.owner_id == user_id,
                    File.project_id == project_id,
                    File.filename.like("%(response)%"),
                )
                .order_by(File.created_at.desc())
            )
        ).first()
    if row is None:
        return None
    chunks: list[bytes] = []
    async with storage.stream_download(storage_path=row.storage_path) as stream:
        async for chunk in stream:
            chunks.append(chunk)
    return b"".join(chunks), row.filename


async def test_commercial_negotiation_round_live(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await seed_doc_matter(commit_factory, NEGOTIATION_DOC)
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    cp_bytes = build_counterparty_nda_docx()
    (_EVIDENCE_DIR / NDA_FILENAME).write_bytes(cp_bytes)
    # The counterparty markup as the agent will read it (the StateOfPlay checklist).
    state = read_state_of_play(cp_bytes)
    (_EVIDENCE_DIR / "counterparty-state-of-play.txt").write_text(
        reconstruct_redline_text(cp_bytes), encoding="utf-8"
    )

    registry = load_registry(_SKILLS_DIR)
    try:
        receipt = await run_scenario(
            NEGOTIATION_SCENARIO, seeded, skill_registry=registry, model_alias=_MODEL, max_steps=100
        )

        report: dict[str, object] = {
            "model": _MODEL,
            "counterparty_changes": len(state.changes),
            "counterparty_open_comments": len(state.open_comment_refs),
            **receipt.to_dict(),
        }
        captured = await _capture_response(commit_factory, seeded.user_id, seeded.project_id)
        if captured is not None:
            resp_bytes, resp_name = captured
            (_EVIDENCE_DIR / resp_name).write_bytes(resp_bytes)
            (_EVIDENCE_DIR / "response-reconstruction.txt").write_text(
                reconstruct_redline_text(resp_bytes), encoding="utf-8"
            )
            report["response_file"] = resp_name
        else:
            report["response_file"] = None

        (_EVIDENCE_DIR / "negotiation-report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

        # Rig assertions (ADR-F015): the loop turned, settled, and ran the negotiation
        # loop — extract then respond. Full coverage is enforced in-tool: the run could
        # not have produced a response file without addressing every change/comment.
        assert receipt.status in _TERMINAL, receipt.status
        assert receipt.model_turns > 0, "the model never turned"
        assert "extract_counterparty_position" in receipt.tools_called, receipt.tools_called
        assert "respond_to_counterparty" in receipt.tools_called, receipt.tools_called
    finally:
        await seeded.cleanup()
