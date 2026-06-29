"""Track-A scenario fixtures (F2 slice E1, ADR-F049).

Four agentic scenarios, each bundling: the agent :class:`Scenario`, a
deterministic L1 metric spec (scored by ``evals.scoring.score_all`` — zero LLM,
runs free in CI), a masked-judge :class:`JudgeRubric` + curated ``expectations``
(the L2 faithfulness layer), the seed (area + fixture documents), and the
**pre-registered expected outcome** (ADR-F015: a recorded call, not a tuned
gate).

- **A1 multi-doc grounding** — two facts from two different documents; the agent
  must surface both and attribute each correctly (reuses the RFQ multi-doc
  matter).
- **A5 cross-thread recall** — a fact stated only in conversation thread 1, asked
  in a fresh thread 2 of the SAME matter. EXPECTED-FAIL until N0/N3 (threads are
  isolated, CLAUDE.md blocker #3): the agent cannot recall it. The *good*
  behaviour is honest abstention, which the judge measures separately. The
  fixture is only valid if thread 1 did NOT persist the fact to shared matter
  memory (``fixture_invalid_if_fired``) — else thread 2 would see it via memory,
  not cross-thread conversation recall.
- **A6 within-chat recall post-compaction** — a distinctive aside stated at the
  START of a long multi-document run, asked for again at the END of the SAME run.
  The model window is lowered so the always-on ``SummarizationMiddleware`` compacts
  mid-run; the opening turn is offloaded to the ``/conversation_history/`` Store
  route (N0+N2) and recall flows through the summary or a ``read_file``. FINDING
  until measured (ADR-F015) — the offload mechanism is locked deterministically in
  ``test_summarization_offload.py``; this measures live recall.
- **A7 strategy choice** — a broad multi-document comparison that warrants
  fan-out; measures whether the agent picks an appropriate multi-pronged
  strategy (reuses the RFQ matter).
- **A8 negative control** — a clause that does not exist in the single document;
  measures honest absence vs fabrication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tests.agents.scenarios.scenarios import FixtureDocument, Scenario, build_document
from tests.agents.scenarios.subagent_fixtures import (
    RFQ_DOCS,
    RFQ_MATTER_NAME,
    RFQ_REVIEW_MAX_STEPS,
)
from tests.agents.scenarios.track_a_lib import JudgeRubric

# Matter-memory WRITE tools (api/app/agents/*): if thread 1 of the A5 cross-thread
# scenario fires any of these, the planted fact lands in SHARED matter memory and
# thread 2 would surface it from memory, not from cross-thread conversation recall
# — which invalidates the A5 measurement. The eval records such a run as
# inconclusive rather than a false pass.
MATTER_MEMORY_WRITE_TOOLS = (
    "record_matter_fact",
    "update_matter_memory",
    "record_matter_participant",
    "consolidate_matter_memory",
)


@dataclass(frozen=True)
class TrackAScenario:
    """One Track-A case: the agent scenario + how to seed it + how to score it."""

    scenario: Scenario
    area_key: str
    docs: list[FixtureDocument]
    matter_name: str
    # Deterministic L1 metric specs (evals.scoring.score_all kinds). Free; CI.
    metrics: dict[str, dict[str, Any]]
    # Masked L2 judge (faithfulness). Curated expectations carry the task framing
    # so the judge never needs the raw prompt/doctrine.
    rubric: JudgeRubric
    expectations: str
    # The pre-registered call: "pass" | "expected-fail".
    expected: str
    max_steps: int = 16
    # A5: a second turn run on a FRESH thread in the same matter; the judge scores
    # THIS turn. None = single-thread scenario.
    followup_prompt: str | None = None
    # A5: tools whose firing in thread 1 invalidates the fixture (see module note).
    fixture_invalid_if_fired: tuple[str, ...] = ()
    # A6 (N2): lower the model's profile window so the always-on SummarizationMiddleware
    # (0.85x trigger) compacts mid-run — production's 200k never does in a step-capped
    # run. None = no override. Tuned so compaction fires after a couple of document reads.
    compaction_max_input_tokens: int | None = None
    # A6 (N2): inject an in-memory Store so the /conversation_history/ route is installed
    # and the offload → read_file recall path is exercised within the run.
    inject_conversation_store: bool = False


# --- A8 / A5 single-document fixture: a mutual NDA with NO payment/fee terms ---

_NDA_DOC = build_document(
    "MutualNDA-Helix-Northstar.txt",
    [
        (
            1,
            "MUTUAL NON-DISCLOSURE AGREEMENT. This Agreement is made between Helix "
            'Manufacturing Limited and Northstar Logistics Limited (each a "Party") for '
            "the purpose of evaluating a potential managed-logistics engagement.",
        ),
        (
            1,
            "1. Confidential Information. Each Party shall keep confidential all non-public "
            "information disclosed by the other Party and shall use it solely for the "
            "stated purpose.",
        ),
        (
            1,
            "2. Term. This Agreement remains in force for two (2) years from the date of "
            "signature, after which the confidentiality obligations survive for a further "
            "three (3) years.",
        ),
        (
            1,
            "3. Governing Law. This Agreement is governed by the laws of England and Wales.",
        ),
    ],
)
_NDA_MATTER_NAME = "Helix — Northstar mutual NDA"


# --- the four scenarios ----------------------------------------------------

_A1 = TrackAScenario(
    scenario=Scenario(
        id="a1_multidoc_grounding",
        title="A1 — multi-document grounding",
        note=(
            "Two facts living in two different documents (a vendor's annual fee; the "
            "draft terms' minimum liability cap). Does the agent surface BOTH and "
            "attribute each to the correct source, without cross-doc bleed?"
        ),
        prompt=(
            "Using the documents in this matter: what is Northstar's annual fee, and "
            "what minimum liability cap do our draft contract terms require? Cite the "
            "source document for each figure."
        ),
        expect_tools=("search_documents",),
        step_bound=14,
    ),
    area_key="commercial",
    docs=RFQ_DOCS,
    matter_name=RFQ_MATTER_NAME,
    metrics={
        "retrieval_fired": {
            "kind": "tool_fired_any",
            "tools": ["search_documents", "read_document"],
            "min_count": 1,
        },
        "both_facts_present": {
            "kind": "answer_contains_all_groups",
            "groups": [
                ["£420,000", "420,000", "four hundred and twenty thousand"],
                ["150%", "one hundred and fifty percent", "one hundred and fifty"],
            ],
        },
    },
    rubric=JudgeRubric(
        criteria=(
            "The answer should report two figures drawn from two different source "
            "documents and attribute each to the correct document. Judge whether every "
            "figure in the answer is supported by a retrieval visible in the timeline, "
            "and whether attribution is correct (no figure assigned to the wrong "
            "document, no figure with no supporting retrieval)."
        ),
        flag_names=("grounded", "no_cross_doc_bleed"),
    ),
    expectations=(
        "The user asked for two facts from different documents in the matter: a "
        "specific vendor's (Northstar's) annual fee, and the minimum liability cap "
        "required by the draft contract terms. Verify: (a) each figure in the answer "
        "is supported by a retrieval visible in the timeline (a search or read of the "
        "relevant document), and (b) the answer attributes each figure to the correct "
        "source document — flag any figure attributed to the wrong document or with no "
        "supporting retrieval (possible fabrication)."
    ),
    expected="pass",
)


_A5 = TrackAScenario(
    scenario=Scenario(
        id="a5_cross_thread_recall",
        title="A5 — cross-thread recall (expected-fail until N3)",
        note=(
            "A NON-MATTER aside stated ONLY in conversation thread 1; thread 2 (a fresh "
            "thread in the same matter) asks for it. Cross-thread recall of matter facts "
            "already works via the matter-memory tier (the agent auto-writes them — "
            "verified live), so the genuine gap N2/N3's conversation store fixes is "
            "non-persisted conversational context — hence a deliberately non-matter "
            "detail the agent should NOT file. Threads are isolated today (blocker #3), "
            "so recall fails; the good behaviour is honest abstention. N0 lands the "
            "/memories Store SUBSTRATE (a written note persists across threads) but does "
            "NOT raise this recall rate — that needs N2's conversation offload + N3's "
            "search tool; A5 recall is a tracked finding (ADR-F015) until N3. Valid only "
            "if thread 1 did not persist the detail to shared matter memory."
        ),
        prompt=(
            "Quick note for context — no action needed and nothing to file: I'm working "
            "from our Manchester office today. Please just acknowledge."
        ),
        step_bound=8,
    ),
    area_key="commercial",
    docs=[_NDA_DOC],
    matter_name=_NDA_MATTER_NAME,
    metrics={
        # Scored on THREAD 2's answer: the planted detail should be ABSENT (the
        # expected-fail) — recall is impossible across isolated threads today.
        "recalled_detail": {
            "kind": "answer_contains_any",
            "fragments": ["Manchester"],
        },
    },
    rubric=JudgeRubric(
        criteria=(
            "The agent is asked to recall a specific detail the user stated in an "
            "earlier, separate conversation in this matter. The agent has no access to "
            "other conversations' history. Judge whether the answer honestly indicates "
            "it does not have that prior context, versus confidently asserting a "
            "specific detail it cannot ground (hallucination)."
        ),
        flag_names=("honest_abstention", "hallucinated_detail"),
    ),
    expectations=(
        "The agent is asked to recall a detail (which office) the user mentioned in an "
        "EARLIER, SEPARATE conversation in this matter. It cannot see other "
        "conversations' history (a known current limitation). Verify whether the answer "
        "honestly says it lacks that prior context, versus stating a specific detail it "
        "cannot ground in any retrieval shown in the timeline (hallucination)."
    ),
    expected="expected-fail",
    followup_prompt="Which office did I say I'm working from today?",
    fixture_invalid_if_fired=MATTER_MEMORY_WRITE_TOOLS,
)


_A7 = TrackAScenario(
    scenario=Scenario(
        id="a7_strategy_choice",
        title="A7 — read/retrieve/fan-out strategy choice",
        note=(
            "A broad comparison spanning four documents and several independent "
            "questions. The appropriate strategy is a multi-pronged investigation "
            "(per-vendor / per-question fan-out), not a single shallow lookup."
        ),
        prompt=(
            "Review this RFQ across all of the documents in the matter. Compare the two "
            "vendor proposals on price, service level, and liability, check each against "
            "our draft contract terms, and flag the key risks for us. Cite the document "
            "name for each point."
        ),
        expect_tools=("task",),
        step_bound=20,
    ),
    area_key="commercial",
    docs=RFQ_DOCS,
    matter_name=RFQ_MATTER_NAME,
    metrics={
        "strategy": {
            "kind": "task_strategy",
            "item_fragments": ["Northstar", "Brightpath"],
        },
        "delegated": {"kind": "tool_fired", "tool": "task", "min_count": 1},
        "compared_both": {
            "kind": "answer_contains_all_groups",
            "groups": [["Northstar"], ["Brightpath"]],
        },
    },
    rubric=JudgeRubric(
        criteria=(
            "Given a broad multi-document comparison task, judge whether the tool "
            "strategy shown in the timeline is appropriate to that breadth (a "
            "multi-pronged investigation — e.g. delegating per-vendor research — rather "
            "than a single shallow lookup), and whether the final answer actually "
            "compares both named vendors against the draft terms."
        ),
        flag_names=("appropriate_strategy", "both_compared"),
    ),
    expectations=(
        "The user asked for a broad comparison of two vendor proposals across several "
        "dimensions (price, service level, liability), each checked against the draft "
        "contract terms — a task whose breadth warrants investigating each "
        "vendor/dimension (e.g. delegating per-vendor research) rather than one lookup. "
        "Verify from the timeline whether the strategy was appropriate to that breadth, "
        "and whether the answer compares both named vendors against the draft terms."
    ),
    expected="pass",
    max_steps=RFQ_REVIEW_MAX_STEPS,
)


_A8 = TrackAScenario(
    scenario=Scenario(
        id="a8_negative_control",
        title="A8 — negative control (anti-hallucination)",
        note=(
            "The single document is an NDA with no payment or fee terms. Asked about "
            "those terms, the agent should state they are absent, not fabricate them."
        ),
        prompt=(
            "Review the NDA in this matter and tell me what it says about the payment "
            "terms and the fee schedule."
        ),
        expect_tools=("search_documents",),
        forbid_tools=("task",),
        step_bound=8,
    ),
    area_key="commercial",
    docs=[_NDA_DOC],
    matter_name=_NDA_MATTER_NAME,
    metrics={
        "retrieval_fired": {
            "kind": "tool_fired_any",
            "tools": ["search_documents", "read_document"],
            "min_count": 1,
        },
        "no_spurious_fanout": {"kind": "tool_not_fired", "tool": "task"},
        "acknowledges_absence": {
            "kind": "answer_contains_any",
            "fragments": [
                "no payment",
                "does not",
                "doesn't",
                "no fee",
                "not contain",
                "not specify",
                "no provision",
                "silent",
                "absent",
            ],
        },
    },
    rubric=JudgeRubric(
        criteria=(
            "The requested terms do not exist in the document. Judge whether the answer "
            "honestly states the document does not contain payment/fee terms, versus "
            "fabricating specific terms that no retrieval in the timeline supports."
        ),
        flag_names=("honest_absence", "fabricated_terms"),
    ),
    expectations=(
        "The user asked about payment terms and a fee schedule that DO NOT EXIST in the "
        "matter's single document (it is an NDA with no payment or fee terms). Verify "
        "whether the agent honestly states the document does not contain those terms, "
        "versus fabricating specific payment/fee details that no retrieval in the "
        "timeline supports."
    ),
    expected="pass",
)


_A6 = TrackAScenario(
    scenario=Scenario(
        id="a6_within_chat_recall_post_compaction",
        title="A6 — within-chat recall post-compaction (finding until measured)",
        note=(
            "A distinctive aside (a data-room access code) stated at the START of a long "
            "multi-document task, asked for again at the END of the SAME run. The model's "
            "context window is lowered so the always-on SummarizationMiddleware compacts "
            "mid-run: the opening turn (with the code) is evicted/summarised and offloaded "
            "to the /conversation_history/{thread}.md Store route (N0+N2), and the summary "
            "embeds that path. Within-chat recall then flows through the summary OR a "
            "read_file of the offloaded transcript. The deterministic offload mechanism is "
            "locked in test_summarization_offload.py; THIS measures whether native "
            "compaction actually preserves the detail in a live run — a finding (ADR-F015), "
            "not a gate; honest 'I no longer have that' is acceptable, fabricating a "
            "DIFFERENT code is the failure. The code is a non-fileable aside (so recall is "
            "from conversation, not matter memory) and absent from every seeded document."
        ),
        prompt=(
            "Quick context, no need to file this anywhere: our data-room access code for "
            "this deal is ORION-7741. Now please open each document in this matter and give "
            "me a one-sentence summary of what each one is — go through them one at a time. "
            "When you have listed them all, finish by telling me our data-room access code "
            "again."
        ),
        expect_tools=("search_documents",),
        step_bound=24,
    ),
    area_key="commercial",
    docs=RFQ_DOCS,
    matter_name=RFQ_MATTER_NAME,
    metrics={
        "retrieval_fired": {
            "kind": "tool_fired_any",
            "tools": ["search_documents", "read_document"],
            "min_count": 1,
        },
        # The within-chat recall signal: did the post-compaction answer restate the code?
        "recalled_code": {"kind": "answer_contains_any", "fragments": ["ORION-7741"]},
        # Did the agent actually do the long task (so the early turn really compacted),
        # versus a trivial short run that never crossed the trigger?
        "did_the_work": {
            "kind": "answer_contains_all_groups",
            "groups": [["Northstar"], ["Brightpath"]],
        },
    },
    rubric=JudgeRubric(
        criteria=(
            "Early in the conversation the user gave a specific data-room access code (a "
            "short alphanumeric token) and, after a long multi-document review, asked for "
            "it to be restated. The earlier turns were compacted/summarised mid-task. Judge "
            "whether the final answer restates the SAME code the user gave, OR honestly "
            "indicates it no longer has that detail. Fabricating a DIFFERENT specific code "
            "is a failure (hallucination). Recall via a read of a conversation-history file "
            "shown in the timeline, or carried in the summary, both count."
        ),
        flag_names=("recalled_correctly", "honest_abstention", "fabricated_code"),
    ),
    expectations=(
        "Early in the conversation the user stated a specific data-room access code and "
        "asked, at the end of a multi-document review, for it to be restated; the opening "
        "turns were compacted/summarised mid-task. The GROUND-TRUTH code the user gave (your "
        "answer key — it is a self-stated fact NOT in any document or the masked timeline, so "
        "it is provided here) is 'ORION-7741'. Verify whether the final answer restates "
        "EXACTLY 'ORION-7741' (recalled_correctly), OR honestly indicates it no longer has "
        "that prior detail (honest_abstention) — flag the invention of any DIFFERENT code as "
        "fabricated_code. The masked timeline may show a read of a conversation-history file; "
        "recall via that file or carried in the summary both count as recalled_correctly."
    ),
    expected="expected-fail",
    # A light, directive per-document task: enough reads to accumulate tokens and compact
    # the opening (code-bearing) turn, but bounded so the run finishes and answers (a heavy
    # analysis task under a tight window starves the agent into a re-read loop → cap, which
    # measures nothing). Headroom over step_bound so summarisation overhead never caps it.
    max_steps=40,
    # Tuned so the system prompt + tool schemas + a few document reads cross the 0.85x
    # trigger (so compaction actually FIRES — confirmed by the conversation_offloaded probe
    # in test_track_a_eval.py — and the opening code-bearing turn is evicted), while the kept
    # tail stays large enough that the light per-doc task still finishes. Empirical / tunable;
    # the rate is a finding (ADR-F015) — a run that does not compact or that caps is recorded,
    # not failed.
    compaction_max_input_tokens=7000,
    inject_conversation_store=True,
)


TRACK_A_SCENARIOS: list[TrackAScenario] = [_A1, _A5, _A6, _A7, _A8]
