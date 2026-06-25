"""C5b-2 negotiation-review CRAFT eval (ADR-F041, provider-marked, CI-skipped).

Measures whether the bound ``negotiation-review`` skill drives good NEGOTIATION craft on
the round-2 response: the agent reads the counterparty's marked-up NDA and responds, and a
Claude judge grades the produced ``.docx`` for craft — did it restore mutual confidentiality
(ideally by a surgical term-swap counter, not a wholesale rewrite), hold the survival floor by
escalating/reverting the perpetual demand rather than conceding it, and engage the
counterparty's comment (counter-with-reply, not orphan it)?

The no-silent-action coverage is already code-enforced in-run (the run cannot produce a
response unless every change and comment is decided — C5a/C5b-1), so this eval foregrounds
craft (ADR-F015: a finding, not a gate). The agent gets a plain TASK that states our POSITION
but NOT the per-item verdicts, so the eval measures the bound skill's steering (the C8 redline
eval pattern). Agent and judge models are DECOUPLED — ``LQ_AI_SCENARIO_MODEL`` drives the
agent (DeepSeek), ``LQ_AI_JUDGE_MODEL`` is the Claude judge.

Run against the live dev stack:

    DATABASE_URL=... LQ_AI_GATEWAY_URL=... LQ_AI_GATEWAY_KEY=... \\
    LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_JUDGE_MODEL=<claude-alias> \\
    LQ_AI_NEGOTIATION_EVAL_REPS=3 LQ_AI_SKILLS_DIR=/skills \\
    UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c5b2 \\
    pytest -m provider tests/agents/scenarios/test_commercial_negotiation_eval.py -s
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.factory import build_gateway_chat_model, build_gateway_http_client
from app.agents.negotiation_service import read_state_of_play
from app.agents.redline_render import reconstruct_redline_text
from app.skills import SkillRegistry, load_registry
from tests.agents.scenarios.commercial_redline_lib import (
    RedlineScenarioDoc,
    capture_output_file,
    seed_doc_matter,
)
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
    else Path(__file__).resolve().parents[4] / "docs" / "fork" / "evidence" / "c5b2"
)
_SKILLS_DIR = Path(
    os.environ.get("LQ_AI_SKILLS_DIR", str(Path(__file__).resolve().parents[4] / "skills"))
)
_MODEL = os.environ.get("LQ_AI_SCENARIO_MODEL", "deepseek")
_JUDGE = os.environ.get("LQ_AI_JUDGE_MODEL", "claude")
_REPS = int(os.environ.get("LQ_AI_NEGOTIATION_EVAL_REPS", "3"))
_TERMINAL = {"completed", "failed", "cap_exceeded", "cancelled"}

# A plain round-2 TASK: states our POSITION and that we must respond to every item (the
# tool enforces coverage anyway), but NOT which verdict per item — so the eval measures
# whether the bound negotiation-review skill drives counter-vs-escalate, mutualisation,
# and counter-with-reply.
_EVAL_PROMPT = (
    "You are our in-house commercial counsel and we are one party to a MUTUAL NDA. The "
    f'counterparty has returned "{NDA_FILENAME}" with their tracked changes and a comment. '
    "Our position: confidentiality must remain mutual; the confidentiality survival period "
    "floor is three (3) years and the ceiling is five (5) years. Read their markup with "
    "extract_counterparty_position, then respond to every change and every comment with "
    "respond_to_counterparty and deliver your response."
)

NEGOTIATION_DOC = RedlineScenarioDoc(
    id="aegis_counterparty_nda",
    filename=NDA_FILENAME,
    build_docx=build_counterparty_nda_docx,
    normalized_text=nda_clean_text,
    prompt=_EVAL_PROMPT,
)

NEGOTIATION_SCENARIO = Scenario(
    id="commercial_negotiation_craft_eval",
    title="Negotiation craft — respond to a counterparty's marked-up NDA",
    note="Does the bound negotiation-review skill drive counter/escalate/counter-with-reply craft?",
    prompt=_EVAL_PROMPT,
    expect_tools=("extract_counterparty_position", "respond_to_counterparty"),
    step_bound=100,
)


@dataclass(frozen=True)
class NegotiationVerdict:
    """Parsed negotiation-craft judgement — the unit the eval aggregates into a rate."""

    verdict: str  # STRONG | ADEQUATE | WEAK | UNKNOWN
    mutuality_restored: bool  # the one-sided strip is back to mutual
    floor_held: bool  # perpetual survival escalated/reverted, not silently accepted
    comment_engaged: bool  # replied to the comment AND kept it anchored (counter-with-reply)
    text: str  # the full judge response (for evidence)

    @property
    def is_craft_pass(self) -> bool:
        """A run counts toward the craft rate when the judge rates it at least adequate
        AND the two substantive outcomes held — mutual confidentiality restored and the
        survival floor held (escalated, not conceded). Engaging the comment is the IDEAL
        (counter-with-reply) and recorded separately, but reject-then-leave-open is not a
        craft failure (the gate already guarantees no silent loss)."""
        return (
            self.verdict in {"STRONG", "ADEQUATE"} and self.mutuality_restored and self.floor_held
        )


_VERDICT_RE = re.compile(r"VERDICT:\s*(STRONG|ADEQUATE|WEAK)", re.IGNORECASE)
_MUTUAL_RE = re.compile(r"MUTUALITY_RESTORED:\s*(yes|no|true|false)", re.IGNORECASE)
_FLOOR_RE = re.compile(r"FLOOR_HELD:\s*(yes|no|true|false)", re.IGNORECASE)
_COMMENT_RE = re.compile(r"COMMENT_ENGAGED:\s*(yes|no|true|false)", re.IGNORECASE)
_YES = {"yes", "true"}


def _flag(rx: re.Pattern[str], text: str) -> bool:
    m = rx.search(text)
    return bool(m) and m.group(1).lower() in _YES


def _judge_view(docx_bytes: bytes) -> str:
    """A judge-readable view of a tracked-changes ``.docx``: the ``[-del-][+ins+]``
    reconstruction PLUS the comment threads (which the reconstruction omits), so the judge
    can see both the redline moves and any replies. Replies/comments are how counter-with-
    reply shows up; an accepted/rejected change is no longer a tracked change (the judge is
    told this)."""
    redline = reconstruct_redline_text(docx_bytes)
    state = read_state_of_play(docx_bytes)
    lines = [redline, "", "COMMENTS:"]
    if not state.comments:
        lines.append("(none)")
    for c in state.comments:
        who = "us" if c.is_ours else c.author
        kind = "reply" if c.parent_id is not None else "comment"
        lines.append(f"- [{c.ref}] {who} ({kind}): {c.text}")
    return "\n".join(lines)


async def negotiation_judge(
    judge_alias: str, counterparty_view: str, response_view: str
) -> NegotiationVerdict:
    """Claude judge of NEGOTIATION craft on the response ``.docx`` (ADR-F015: a finding).

    Decoupled from the agent model so Claude grades DeepSeek. Asks for machine-readable
    header lines then bullets, so the eval can compute a craft rate while keeping the prose
    for evidence. ``purpose`` is a gateway routing-log tag only (it falls back to "chat"),
    so no gateway change is needed.
    """
    http = build_gateway_http_client()
    try:
        model = build_gateway_chat_model(
            model_alias=judge_alias,
            purpose="commercial_negotiation_craft_judge",
            http_async_client=http,
            project_minimum_inference_tier=None,
            privileged=False,
        )
        sys = SystemMessage(
            content=(
                "You are a senior commercial lawyer grading a junior's RESPONSE to a "
                "counterparty's marked-up mutual NDA, acting for our side. Our position: "
                "confidentiality must stay MUTUAL; the survival floor is three (3) years and the "
                "ceiling five (5) years, so a perpetual/indefinite survival term is BELOW the "
                "floor and must be ESCALATED or reverted, never silently accepted; benign "
                "clarifications may be accepted. Judge NEGOTIATION CRAFT, discounting model "
                "intelligence. You see the counterparty's markup and OUR response, each as a "
                "[-deleted-][+inserted+] reconstruction plus its comment threads. Note how each "
                "decision shows up in our response: an ACCEPTED change is no longer a tracked "
                "change (it is baked into the text); a REJECTED change is reverted to the original "
                "(also no marker); a COUNTER shows as our own [-their wording-][+our wording+]; an "
                "ESCALATED or left-open change stays visible as a tracked change. Assess:\n"
                "- MUTUALITY_RESTORED: is the one-sided 'Recipient/Discloser' obligation back to "
                "mutual ('each party'/'the other party') — ideally by a SURGICAL counter that "
                "swaps only the party terms and leaves the obligation wording bare, not a "
                "wholesale rewrite?\n"
                "- FLOOR_HELD: is the perpetual survival demand escalated or reverted (the "
                "three-year term preserved/visible), NOT silently accepted into the clean text?\n"
                "- COMMENT_ENGAGED: did we reply to the counterparty's comment AND keep it "
                "anchored (counter-with-reply), rather than rejecting the change and orphaning "
                "the comment?\n\n"
                "Respond EXACTLY in this shape:\n"
                "VERDICT: STRONG|ADEQUATE|WEAK\n"
                "MUTUALITY_RESTORED: yes|no\n"
                "FLOOR_HELD: yes|no\n"
                "COMMENT_ENGAGED: yes|no\n"
                "then 3-6 terse bullets citing the specific moves."
            )
        )
        human = HumanMessage(
            content=(
                "COUNTERPARTY MARKUP (their changes + comment):\n"
                + counterparty_view[:10000]
                + "\n\n"
                "OUR RESPONSE (our changes + replies):\n" + response_view[:16000]
            )
        )
        resp = await model.ainvoke([sys, human])
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
    finally:
        await http.aclose()

    vm = _VERDICT_RE.search(text)
    return NegotiationVerdict(
        verdict=vm.group(1).upper() if vm else "UNKNOWN",
        mutuality_restored=_flag(_MUTUAL_RE, text),
        floor_held=_flag(_FLOOR_RE, text),
        comment_engaged=_flag(_COMMENT_RE, text),
        text=text,
    )


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


async def _run_once(
    factory: async_sessionmaker[AsyncSession],
    rep: int,
    registry: SkillRegistry,
    counterparty_view: str,
    out_dir: Path,
) -> dict[str, object]:
    """One seed → run → capture → judge cycle; returns a result row (rows cleaned up)."""
    seeded = await seed_doc_matter(factory, NEGOTIATION_DOC)
    row: dict[str, object] = {"rep": rep}
    try:
        receipt = await run_scenario(
            NEGOTIATION_SCENARIO, seeded, skill_registry=registry, model_alias=_MODEL, max_steps=100
        )
        row["status"] = receipt.status
        row["model_turns"] = receipt.model_turns
        # The number of respond_to_counterparty calls is the gate adapting (a refused
        # reply+reject combination forces another attempt — the C5b-1 signal).
        row["respond_calls"] = receipt.tools_called.count("respond_to_counterparty")

        captured = await capture_output_file(
            factory, seeded.user_id, seeded.project_id, "%(response)%"
        )
        if captured is None:
            row["responded"] = False
            return row
        resp_bytes, _name = captured
        row["responded"] = True  # coverage is structurally guaranteed (the gate let it persist)
        response_view = _judge_view(resp_bytes)
        (out_dir / f"rep{rep}-response.txt").write_text(response_view, encoding="utf-8")
        try:
            verdict = await negotiation_judge(_JUDGE, counterparty_view, response_view)
            (out_dir / f"rep{rep}-verdict.md").write_text(verdict.text, encoding="utf-8")
            row["verdict"] = verdict.verdict
            row["mutuality_restored"] = verdict.mutuality_restored
            row["floor_held"] = verdict.floor_held
            row["comment_engaged"] = verdict.comment_engaged
            row["craft_pass"] = verdict.is_craft_pass
        except Exception as exc:
            row["judge_error"] = f"{type(exc).__name__}: {exc}"
        return row
    finally:
        await seeded.cleanup()


async def test_commercial_negotiation_craft_eval(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    out_dir = _EVIDENCE_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = load_registry(
        _SKILLS_DIR
    )  # the real /skills registry → activates negotiation-review

    # The counterparty markup is deterministic — build the judge's view of it once.
    counterparty_view = _judge_view(build_counterparty_nda_docx())
    (out_dir / "counterparty-view.txt").write_text(counterparty_view, encoding="utf-8")

    results: list[dict[str, object]] = []
    for rep in range(1, _REPS + 1):
        results.append(await _run_once(commit_factory, rep, registry, counterparty_view, out_dir))

    craft_pass = sum(1 for r in results if r.get("craft_pass"))
    engaged = sum(1 for r in results if r.get("comment_engaged"))
    report = {
        "agent": _MODEL,
        "judge": _JUDGE,
        "reps": _REPS,
        "craft_pass": craft_pass,
        "comment_engaged": engaged,
        "total": len(results),
        "results": results,
    }
    (out_dir / "eval-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Rig assertions only (ADR-F015): every run reached a terminal state and turned the
    # model. The craft RATE is the finding the maintainer reads to decide tuning is done —
    # not a flaky hard gate on model quality. Coverage (every item decided) is structurally
    # guaranteed in-run: a response cannot be produced unless the in-tool gate passed.
    assert results, "no eval runs executed"
    for r in results:
        assert r.get("status") in _TERMINAL, r
