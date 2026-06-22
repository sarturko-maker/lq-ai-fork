"""C8 surgical-redline CRAFT eval (ADR-F041, provider-marked, CI-skipped).

The maintainer's mechanism for getting to *reliable* surgical redlines: run many
vendor scenarios x repetitions and measure the **surgical-craft rate** (so we can
tune the skill/doctrine until redlines are reliably surgical), rather than bolt a
slow runtime critic onto every production run. Craft = structure-preserving,
multi-narrow-edits-per-clause, recognisable boilerplate left bare — judged on the
PRODUCED `.docx`, discounting model intelligence (ADR-F015: a finding, not a gate).

The agent is given a plain redline TASK (not surgical-technique instructions) so the
eval measures whether the bound `surgical-redline` skill + doctrine actually drive
the craft. Per scenario x rep it captures the reconstruction + a structured
craft-judge verdict, then writes an aggregate rate report to the evidence dir.

Run against the live dev stack (DeepSeek):

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_REDLINE_EVAL_REPS=3 \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c8 \\
    pytest -m provider tests/agents/scenarios/test_commercial_redline_eval.py -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.redline_render import bare_text, docx_text, reconstruct_redline_text
from app.agents.redline_service import RedlineService
from app.skills import SkillRegistry, load_registry
from tests.agents.scenarios.commercial_redline_lib import (
    RedlineScenarioDoc,
    capture_redline,
    craft_judge,
    seed_doc_matter,
)
from tests.agents.scenarios.databridge_license import (
    LICENSE_FILENAME,
    build_license_docx,
    license_normalized_text,
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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c8"
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_REPS = int(os.environ.get("LQ_AI_REDLINE_EVAL_REPS", "3"))
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}
_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)


def _redline_prompt(filename: str) -> str:
    """A plain redline TASK — deliberately NOT spelling out surgical technique, so
    the eval measures whether the bound skill/doctrine drive the craft."""
    return (
        "You are our in-house commercial counsel and we are the CUSTOMER. Review the "
        f'attached vendor agreement "{filename}" and redline it to protect us, applying '
        "your changes as tracked changes with apply_redline. Work through every one-sided "
        "clause — licence/scope, fees, IP, the data licence, warranties, indemnity, the "
        "liability cap and termination. Read the whole agreement first, then apply ALL your "
        "edits in a SINGLE apply_redline call."
    )


CORPUS: list[RedlineScenarioDoc] = [
    RedlineScenarioDoc(
        id="securescan_saas_msa",
        filename=MSA_FILENAME,
        build_docx=build_msa_docx,
        normalized_text=msa_normalized_text,
        prompt=_redline_prompt(MSA_FILENAME),
        boilerplate_bare=("shall indemnify, defend and hold harmless", "shall not exceed"),
    ),
    RedlineScenarioDoc(
        id="databridge_licence",
        filename=LICENSE_FILENAME,
        build_docx=build_license_docx,
        normalized_text=license_normalized_text,
        prompt=_redline_prompt(LICENSE_FILENAME),
        boilerplate_bare=("shall indemnify, defend and hold harmless", "shall not exceed"),
    ),
]


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _run_once(
    factory: async_sessionmaker[AsyncSession],
    doc: RedlineScenarioDoc,
    rep: int,
    registry: SkillRegistry,
    out_dir: Path,
) -> dict[str, object]:
    """One seed → run → capture → judge cycle; returns a result row (rows cleaned up)."""
    seeded = await seed_doc_matter(factory, doc)
    row: dict[str, object] = {"doc": doc.id, "rep": rep}
    try:
        scenario = Scenario(
            id=f"redline_eval_{doc.id}_{rep}",
            title=f"Surgical redline craft — {doc.id} (rep {rep})",
            note="Does the bound surgical-redline skill drive structure-preserving edits?",
            prompt=doc.prompt,
            expect_tools=("apply_redline",),
            step_bound=100,
        )
        receipt = await run_scenario(
            scenario, seeded, skill_registry=registry, model_alias=_MODEL, max_steps=100
        )
        row["status"] = receipt.status
        row["model_turns"] = receipt.model_turns

        captured = await capture_redline(factory, seeded.user_id, seeded.project_id)
        if captured is None:
            row["redlined"] = False
            return row
        redlined_bytes, _name = captured
        redline_view = reconstruct_redline_text(redlined_bytes)
        accepted = docx_text(RedlineService().accept_all(redlined_bytes))
        (out_dir / f"{doc.id}-rep{rep}-reconstruction.txt").write_text(
            redline_view, encoding="utf-8"
        )
        row["redlined"] = True
        # Deterministic structure check: did the recognisable boilerplate survive bare?
        row["boilerplate_bare"] = all(
            phrase in bare_text(redline_view) for phrase in doc.boilerplate_bare
        )
        try:
            verdict = await craft_judge(_MODEL, doc.normalized_text(), redline_view, accepted)
            (out_dir / f"{doc.id}-rep{rep}-verdict.md").write_text(verdict.text, encoding="utf-8")
            row["verdict"] = verdict.verdict
            row["surgical"] = verdict.surgical
            row["surgical_pass"] = verdict.is_surgical_pass
        except Exception as exc:
            row["judge_error"] = f"{type(exc).__name__}: {exc}"
        return row
    finally:
        await seeded.cleanup()


async def test_commercial_redline_craft_eval(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    out_dir = _EVIDENCE_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(_SKILLS_DIR)  # the real /skills registry → activates the bound skills

    results: list[dict[str, object]] = []
    for doc in CORPUS:
        for rep in range(1, _REPS + 1):
            results.append(await _run_once(commit_factory, doc, rep, registry, out_dir))

    # Aggregate the surgical-craft rate per doc + overall.
    rates: dict[str, dict[str, float]] = {}
    for doc in CORPUS:
        rows = [r for r in results if r["doc"] == doc.id]
        passes = sum(1 for r in rows if r.get("surgical_pass"))
        rates[doc.id] = {"surgical_pass": passes, "total": len(rows)}
    overall_pass = sum(1 for r in results if r.get("surgical_pass"))
    rates["overall"] = {"surgical_pass": overall_pass, "total": len(results)}

    report = {"model": _MODEL, "reps": _REPS, "rates": rates, "results": results}
    (out_dir / "eval-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Rig assertions only (ADR-F015): every run reached a terminal state and turned
    # the model. The surgical-craft RATE is the finding the maintainer reads from the
    # evidence to decide tuning is done — not a flaky hard gate on model quality.
    assert results, "no eval runs executed"
    for r in results:
        assert r.get("status") in _TERMINAL, r
