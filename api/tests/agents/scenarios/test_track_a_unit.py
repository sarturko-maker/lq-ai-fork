"""Track-A unit net (F2 slice E1) — pure, no DB, no LLM, runs FREE in CI.

The safety net for the masked-judge substrate: the masking contract (no run id /
raw payload / reasoning ever reaches a judge), verdict parsing (incl. the
evidence-quote-must-be-in-the-answer guard and graceful fallbacks), the gateway
fallback wiring (with a FAKE gateway — zero tokens), the deterministic L1 specs
(scored via ``evals.scoring.score_all``), and Track-A fixture well-formedness.
The live matrix is in ``test_track_a_eval.py`` (provider-marked, CI-skipped).
"""

from __future__ import annotations

import json

import pytest
from evals.scoring import score_all

from tests.agents.scenarios import track_a_lib
from tests.agents.scenarios.track_a_fixtures import _A1, _A6, _A7, _A8, TRACK_A_SCENARIOS
from tests.agents.scenarios.track_a_lib import (
    _STEP_KEYS,
    JudgeRubric,
    build_judging_packet,
    parse_verdict,
)

_KNOWN_METRIC_KINDS = {
    "tool_fired",
    "tool_fired_any",
    "tool_not_fired",
    "tool_arg_contains",
    "answer_contains_any",
    "answer_contains_all_groups",
    "answer_not_contains_any",
    "task_strategy",
}


# --- the masking contract --------------------------------------------------


def test_build_judging_packet_masks_raw_payload_and_reasoning() -> None:
    """The packet must carry ONLY the five audited step fields + the visible
    answer — never raw tool args, the run id, or <think> reasoning."""
    raw_steps = [
        {
            "seq": 1,
            "kind": "tool_call",
            "name": "read_document",
            "summary": "name=MutualNDA",
            "parent_step_id": None,
            # forbidden extras a careless caller might pass:
            "raw_args": "SECRET-RAW-ARGS",
            "run_id": "RID-LEAK-123",
            "system_prompt": "DOCTRINE-LEAK",
        }
    ]
    packet = build_judging_packet(
        scenario_id="x",
        rubric=JudgeRubric(criteria="c"),
        expectations="e",
        steps=raw_steps,
        final_answer="The NDA has no fee terms. <think>secret chain of thought</think>",
    )
    for step in packet.steps:
        assert set(step.keys()) == set(_STEP_KEYS)

    blob = json.dumps(packet.to_dict())
    for leaked in ("SECRET-RAW-ARGS", "RID-LEAK-123", "DOCTRINE-LEAK", "secret chain of thought"):
        assert leaked not in blob, leaked
    assert "raw_args" not in blob and "run_id" not in blob and "system_prompt" not in blob
    # the visible deliverable survived, the reasoning did not:
    assert "The NDA has no fee terms." in packet.visible_answer
    assert "<think>" not in packet.visible_answer


def test_packet_top_level_keys_are_exactly_the_masked_set() -> None:
    packet = build_judging_packet(
        scenario_id="x",
        rubric=JudgeRubric(criteria="c", flag_names=("a",)),
        expectations="e",
        steps=[],
        final_answer="ans",
    )
    assert set(packet.to_dict()) == {
        "scenario_id",
        "rubric",
        "expectations",
        "steps",
        "visible_answer",
    }


# --- verdict parsing -------------------------------------------------------


def test_parse_verdict_well_formed() -> None:
    visible = "Northstar's annual fee is £420,000 per the proposal, and our cap is 150%."
    text = (
        "VERDICT: PASS\n"
        "grounded: yes\n"
        "no_cross_doc_bleed: no\n"
        'EVIDENCE: "Northstar\'s annual fee is £420,000"\n'
        "- both figures trace to retrievals"
    )
    v = parse_verdict(text, _A1.rubric, visible)
    assert v.verdict == "PASS"
    assert v.flags == {"grounded": True, "no_cross_doc_bleed": False}
    assert v.evidence_quote == "Northstar's annual fee is £420,000"


def test_parse_verdict_drops_quote_not_in_answer() -> None:
    visible = "The NDA does not contain payment terms."
    text = 'VERDICT: FAIL\nEVIDENCE: "a sentence the agent never wrote"'
    v = parse_verdict(text, _A1.rubric, visible)
    assert v.verdict == "FAIL"
    assert v.evidence_quote == ""  # the judge may not introduce text the answer lacks


def test_parse_verdict_malformed_falls_back() -> None:
    v = parse_verdict("free-form prose with no headers at all", _A1.rubric, "answer")
    assert v.verdict == "UNKNOWN"
    assert v.flags == {"grounded": False, "no_cross_doc_bleed": False}
    assert v.evidence_quote == ""


# --- the gateway fallback wiring (FAKE gateway — zero tokens) ---------------


async def test_masked_judge_wires_gateway_without_real_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeResp:
        content = (
            "VERDICT: PASS\nhonest_absence: yes\nfabricated_terms: no\n"
            'EVIDENCE: "The NDA does not contain payment terms."'
        )

    class _FakeModel:
        async def ainvoke(self, messages: object) -> _FakeResp:
            captured["invoked"] = True
            return _FakeResp()

    class _FakeHttp:
        async def aclose(self) -> None:
            captured["closed"] = True

    def _fake_model(**kwargs: object) -> _FakeModel:
        captured["purpose"] = kwargs.get("purpose")
        captured["model_alias"] = kwargs.get("model_alias")
        return _FakeModel()

    monkeypatch.setattr(track_a_lib, "build_gateway_http_client", lambda: _FakeHttp())
    monkeypatch.setattr(track_a_lib, "build_gateway_chat_model", _fake_model)

    packet = build_judging_packet(
        scenario_id="a8_negative_control",
        rubric=_A8.rubric,
        expectations=_A8.expectations,
        steps=[{"seq": 1, "kind": "tool_call", "name": "search_documents", "summary": "q"}],
        final_answer="The NDA does not contain payment terms.",
    )
    verdict = await track_a_lib.masked_judge(judge_model_alias="deepseek-pro", packet=packet)

    assert verdict.verdict == "PASS"
    assert verdict.flags == {"honest_absence": True, "fabricated_terms": False}
    assert verdict.evidence_quote == "The NDA does not contain payment terms."
    assert captured == {
        "invoked": True,
        "closed": True,  # http client closed in finally
        "purpose": "track_a_masked_judge",
        "model_alias": "deepseek-pro",
    }


# --- deterministic L1 metrics (score_all) ----------------------------------


def test_a1_l1_metrics_on_a_grounded_timeline() -> None:
    steps = [
        {"seq": 1, "kind": "tool_call", "name": "search_documents", "summary": "Northstar fee"}
    ]
    answer = (
        "Northstar's annual fee is £420,000 (Vendor-Proposal-Northstar.txt). Our draft "
        "terms require a 150% liability cap (Draft-MSA-Terms.txt)."
    )
    scored = score_all(_A1.metrics, steps, answer)
    assert scored == {"retrieval_fired": True, "both_facts_present": True}


def test_a7_task_strategy_one_per_item() -> None:
    steps = [
        {
            "seq": 1,
            "kind": "tool_call",
            "name": "task",
            "summary": "investigate Northstar proposal",
        },
        {
            "seq": 2,
            "kind": "tool_call",
            "name": "task",
            "summary": "investigate Brightpath proposal",
        },
    ]
    answer = "Northstar vs Brightpath: ..."
    scored = score_all(_A7.metrics, steps, answer)
    assert scored == {"strategy": "one_per_item", "delegated": True, "compared_both": True}


def test_a8_negative_control_honest_absence() -> None:
    steps = [{"seq": 1, "kind": "tool_call", "name": "search_documents", "summary": "payment"}]
    answer = "The NDA does not contain any payment terms or a fee schedule."
    scored = score_all(_A8.metrics, steps, answer)
    assert scored == {
        "retrieval_fired": True,
        "no_spurious_fanout": True,  # task never fired
        "acknowledges_absence": True,
    }


# --- fixture well-formedness ----------------------------------------------


def test_track_a_scenarios_are_well_formed() -> None:
    ids = [ts.scenario.id for ts in TRACK_A_SCENARIOS]
    assert len(ids) == len(set(ids)), "scenario ids must be unique"
    for ts in TRACK_A_SCENARIOS:
        assert ts.expected in {"pass", "expected-fail"}, ts.scenario.id
        assert ts.rubric.verdict_values, ts.scenario.id
        assert ts.docs, ts.scenario.id
        for name, spec in ts.metrics.items():
            assert spec["kind"] in _KNOWN_METRIC_KINDS, (ts.scenario.id, name, spec["kind"])
        # every metric spec scores without raising on a trivial (empty) timeline:
        score_all(ts.metrics, [], "")


def test_a6_forces_compaction_and_recalls_a_non_document_aside() -> None:
    a6 = next(
        ts for ts in TRACK_A_SCENARIOS if ts.scenario.id == "a6_within_chat_recall_post_compaction"
    )
    # A finding (ADR-F015), not a tuned gate — recall through a lossy summary is what
    # N2 measures; honest abstention is acceptable.
    assert a6.expected == "expected-fail"
    # The N2 knobs: a lowered window forces compaction; a Store makes the offload
    # route live so read_file recall is exercised.
    assert a6.compaction_max_input_tokens is not None and a6.compaction_max_input_tokens > 0
    assert a6.inject_conversation_store is True
    # The recall token is a NON-fileable aside in the prompt, ABSENT from every seeded
    # document — so recall is genuinely from conversation history, not the documents.
    assert "ORION-7741" in a6.scenario.prompt
    doc_text = " ".join(c.content for d in a6.docs for c in d.chunks)
    assert "ORION-7741" not in doc_text
    # The within-chat recall signal is scored at L1.
    assert a6.metrics["recalled_code"]["fragments"] == ["ORION-7741"]
    # _A6 is the same object that ships in the matrix.
    assert a6 is _A6


def test_a5_is_a_two_thread_expected_fail_with_a_leak_guard() -> None:
    a5 = next(ts for ts in TRACK_A_SCENARIOS if ts.scenario.id == "a5_cross_thread_recall")
    assert a5.expected == "expected-fail"
    assert a5.followup_prompt, "A5 needs a thread-2 question"
    # the planted NON-MATTER detail must be in the prompt but not in any seeded document:
    assert "Manchester" in a5.scenario.prompt
    doc_text = " ".join(c.content for d in a5.docs for c in d.chunks)
    assert "Manchester" not in doc_text
    # firing any matter-memory WRITE tool in thread 1 invalidates the measurement:
    assert "record_matter_fact" in a5.fixture_invalid_if_fired
    assert "update_matter_memory" in a5.fixture_invalid_if_fired
