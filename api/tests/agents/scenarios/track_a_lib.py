"""Track-A masked-judge library (F2 slice E1, ADR-F049).

Generalises the redline ``craft_judge`` (``commercial_redline_lib.py``) into a
*masked* retrieval/agentic judge for the Track-A scenarios. The judge — whether
the orchestrator (Claude, the primary judge) or the gateway fallback
(``deepseek-pro``) — sees ONLY a **masked judging packet**:

1. the **sanitised tool timeline** (``evals.runner.fetch_steps`` shape —
   ``seq/kind/name/summary/parent_step_id``; ``run_id`` already dropped, every
   ``summary`` already bounded at persist by ``runner._bounded``),
2. the **user-visible answer** (``evals.scoring.visible_answer`` — ``<think>``
   reasoning stripped), and
3. the eval author's **rubric + expectations**.

It NEVER receives the ground-truth documents, the agent's system prompt /
doctrine, the user's task prompt, or the run id — so it cannot grade by leakage.
It judges the answer's **faithfulness to what the agent actually surfaced**
(every claim traceable to a retrieval in the timeline; honest abstention when
grounding is absent) — exactly what masking makes a fair question.

``build_judging_packet`` + the dataclasses + ``parse_verdict`` are **pure** and
CI-unit-tested (no DB, no LLM). ``masked_judge`` is the provider-only gateway
fallback — used only when no orchestrator session is in the loop. Per ADR-F015
a verdict is a recorded finding, never a runtime gate.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from evals.scoring import visible_answer
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.factory import build_gateway_chat_model, build_gateway_http_client

# The masked timeline shape — the five audited fields of evals.runner.fetch_steps.
# build_judging_packet projects every step to EXACTLY these keys, so a raw row's
# extra payload (raw tool args/results, run_id) can never reach the judge.
_STEP_KEYS = ("seq", "kind", "name", "summary", "parent_step_id")


@dataclass(frozen=True)
class JudgeRubric:
    """How the judge should grade one scenario — the author's instructions.

    ``criteria`` is the prose the judge applies; ``verdict_values`` the allowed
    verdict labels (parsed from a ``VERDICT:`` header, kept UPPERCASE by
    convention); ``flag_names`` the boolean signals to extract (each parsed from
    a ``<NAME>: yes|no`` line).
    """

    criteria: str
    verdict_values: tuple[str, ...] = ("PASS", "PARTIAL", "FAIL")
    flag_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class JudgeVerdict:
    """A parsed judgement — the unit the Track-A baseline aggregates.

    ``evidence_quote`` is kept ONLY if it is a verbatim substring of the visible
    answer the judge graded; a quote not found there is dropped to ``""`` — the
    judge may not introduce text the agent did not write.
    """

    verdict: str  # one of the rubric's verdict_values, or "UNKNOWN"
    flags: dict[str, bool]
    evidence_quote: str
    text: str  # the full judge response, for evidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "flags": self.flags,
            "evidence_quote": self.evidence_quote,
            "text": self.text,
        }


@dataclass(frozen=True)
class JudgingPacket:
    """The masked input handed to ANY judge (Claude orchestrator or gateway).

    Serialisable to JSON for the frozen evidence record + the orchestrator
    judge. Carries ONLY masked material; ``build_judging_packet`` enforces it.
    """

    scenario_id: str
    rubric: JudgeRubric
    expectations: str
    steps: list[dict[str, Any]]  # fetch_steps shape (the five _STEP_KEYS)
    visible_answer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "rubric": {
                "criteria": self.rubric.criteria,
                "verdict_values": list(self.rubric.verdict_values),
                "flag_names": list(self.rubric.flag_names),
            },
            "expectations": self.expectations,
            "steps": self.steps,
            "visible_answer": self.visible_answer,
        }


def _mask_step(step: dict[str, Any]) -> dict[str, Any]:
    """Project a step row to the masked timeline shape — only the five audited
    fields, dropping any raw payload or run identity a caller might pass."""
    return {key: step.get(key) for key in _STEP_KEYS}


def build_judging_packet(
    *,
    scenario_id: str,
    rubric: JudgeRubric,
    expectations: str,
    steps: Sequence[dict[str, Any]],
    final_answer: str | None,
) -> JudgingPacket:
    """Assemble the masked judging packet.

    The masking is enforced HERE, structurally: each step is reduced to the five
    audited fields and the answer to its visible part. The packet never carries
    the agent's prompt/doctrine, raw tool payloads, or the run id.
    """
    return JudgingPacket(
        scenario_id=scenario_id,
        rubric=rubric,
        expectations=expectations,
        steps=[_mask_step(s) for s in steps],
        visible_answer=visible_answer(final_answer),
    )


# --- verdict parsing (pure; never raises) ---------------------------------

_EVIDENCE_RE = re.compile(r'EVIDENCE:\s*"?(.+?)"?\s*(?:\n|$)', re.IGNORECASE)
_TRUE = {"yes", "true"}


def _verdict_re(values: Sequence[str]) -> re.Pattern[str]:
    alt = "|".join(re.escape(v) for v in values)
    return re.compile(rf"VERDICT:\s*({alt})", re.IGNORECASE)


def parse_verdict(text: str, rubric: JudgeRubric, visible: str) -> JudgeVerdict:
    """Parse a judge response into a :class:`JudgeVerdict` (graceful fallback).

    Never raises: a missing/garbled ``VERDICT:`` header → ``"UNKNOWN"``, flags
    default ``False``, evidence ``""`` — craft_judge's discipline. The evidence
    quote is retained only if it is a verbatim substring of the visible answer.
    """
    vm = _verdict_re(rubric.verdict_values).search(text)
    verdict = vm.group(1).upper() if vm else "UNKNOWN"
    flags: dict[str, bool] = {}
    for name in rubric.flag_names:
        fm = re.search(rf"{re.escape(name)}:\s*(yes|no|true|false)", text, re.IGNORECASE)
        flags[name] = bool(fm) and fm.group(1).lower() in _TRUE
    em = _EVIDENCE_RE.search(text)
    quote = em.group(1).strip() if em else ""
    if quote and quote not in visible:
        quote = ""  # the judge may not introduce text the answer does not contain
    return JudgeVerdict(verdict=verdict, flags=flags, evidence_quote=quote, text=text)


# --- the gateway fallback judge (provider-only) ---------------------------


def _judge_system_prompt(rubric: JudgeRubric) -> str:
    flag_lines = "".join(f"{name}: yes|no\n" for name in rubric.flag_names)
    values = "|".join(rubric.verdict_values)
    return (
        "You are an impartial evaluator of an AI legal agent's work. You are given "
        "ONLY (1) a sanitised timeline of the tools the agent invoked plus bounded "
        "digests of what each returned, and (2) the agent's final user-visible answer. "
        "You do NOT see the source documents, the agent's instructions, or the task "
        "wording beyond the criteria below. Judge the answer's FAITHFULNESS to what the "
        "agent actually retrieved (every claim traceable to a retrieval in the timeline; "
        "honest acknowledgement when grounding is absent) — never whether it matches "
        "outside knowledge you happen to hold.\n\n"
        f"CRITERIA:\n{rubric.criteria}\n\n"
        "Respond EXACTLY in this shape:\n"
        f"VERDICT: {values}\n"
        f"{flag_lines}"
        "EVIDENCE: \"<a short verbatim quote from the agent's answer that justifies your "
        'verdict, or leave the quotes empty>"\n'
        "then 2-5 terse bullets of reasoning."
    )


def _render_timeline(steps: Sequence[dict[str, Any]]) -> str:
    lines = []
    for s in steps:
        head = f"#{s.get('seq')} [{s.get('kind')}]"
        if s.get("name"):
            head += f" {s.get('name')}"
        if s.get("summary"):
            head += f": {s.get('summary')}"
        lines.append(head)
    return "\n".join(lines)


def _judge_human_prompt(packet: JudgingPacket) -> str:
    timeline = _render_timeline(packet.steps) or "(no tools used)"
    return (
        f"EXPECTATIONS (what to verify):\n{packet.expectations}\n\n"
        f"AGENT TOOL TIMELINE (sanitised):\n{timeline}\n\n"
        f"AGENT FINAL ANSWER:\n{packet.visible_answer or '(empty answer)'}"
    )


async def masked_judge(*, judge_model_alias: str, packet: JudgingPacket) -> JudgeVerdict:
    """Gateway-routed fallback judge (generalises ``craft_judge``).

    Used when no orchestrator (Claude) session is in the loop — automated and
    reproducible. ``judge_model_alias`` is REQUIRED (no env default) so a run can
    never silently grade a model against itself. The gateway is the only egress;
    ``purpose`` falls back to ``'chat'`` if not allow-listed, as ``craft_judge``
    already does. Per ADR-F015 a finding, never a runtime gate.
    """
    http = build_gateway_http_client()
    try:
        model = build_gateway_chat_model(
            model_alias=judge_model_alias,
            purpose="track_a_masked_judge",
            http_async_client=http,
            project_minimum_inference_tier=None,
            privileged=False,
        )
        resp = await model.ainvoke(
            [
                SystemMessage(content=_judge_system_prompt(packet.rubric)),
                HumanMessage(content=_judge_human_prompt(packet)),
            ]
        )
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
    finally:
        await http.aclose()
    return parse_verdict(text, packet.rubric, packet.visible_answer)
