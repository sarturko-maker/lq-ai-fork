"""UX-B-4 subagent fixtures — a multi-document Commercial RFQ + two scenarios.

Delegation is on-demand, not a pipeline (ADR-F017): a Commercial agent should
answer a single focused question **directly** (no subagent), but fan out to its
``document-researcher`` subagent when a matter spans **many documents and
several independent questions** — the Claude-Code-for-legal posture. A
single-document matter gives the agent no reason to delegate, so this fixture
plants a small **RFQ** matter: the buyer's instructions, two competing vendor
proposals, and the draft contract terms. The two scenarios probe both arms:

* ``rfq_single_fact`` — one fact in one document; best path is a direct grounded
  fetch (**expect NO ``task``**).
* ``rfq_cross_document_review`` — compare both proposals on several dimensions and
  check them against the draft terms; best path is to **delegate** per-vendor /
  per-question investigation to the researcher (**expect ≥1 ``task``**).

Per ADR-F015 a shape-miss (it delegated when it needn't, or didn't when it
should) is a recorded **finding**, not a failure — UX-B-3 already showed M3
over-explores, so a no-delegate or no-converge run is the honest qualification
result, kept verbatim.
"""

from __future__ import annotations

from tests.agents.scenarios.scenarios import FixtureDocument, Scenario, build_document

# The hard run cap for the cross-document review — delegation needs headroom
# (parent search → task → subagent search/read → report → parent answer) beyond
# the single-turn default. Still bounded so a runaway loop ends as cap_exceeded.
RFQ_REVIEW_MAX_STEPS = 28

_RFQ_INSTRUCTIONS = build_document(
    "RFQ-Instructions.txt",
    [
        (
            1,
            "1. Request for Quotation. Helix Manufacturing Limited (the "
            '"Buyer") invites quotations for the supply of managed logistics '
            "services. Quotations must be submitted by no later than 5:00pm on "
            "30 September 2026. Late submissions will not be considered.",
        ),
        (
            1,
            "2. Evaluation Criteria. Quotations will be evaluated on price (40%), "
            "service levels (35%), and contractual risk including liability terms "
            "(25%). The Buyer is not bound to accept the lowest or any quotation.",
        ),
    ],
)

_VENDOR_NORTHSTAR = build_document(
    "Vendor-Proposal-Northstar.txt",
    [
        (
            1,
            "Northstar Logistics — Proposal. Annual fee: four hundred and twenty "
            "thousand pounds (£420,000). Service level: 99.5% on-time delivery, "
            "measured monthly.",
        ),
        (
            1,
            "Liability. Northstar's aggregate liability is capped at one hundred "
            "percent (100%) of the annual fee. Northstar excludes all liability "
            "for indirect and consequential loss.",
        ),
    ],
)

_VENDOR_BRIGHTPATH = build_document(
    "Vendor-Proposal-Brightpath.txt",
    [
        (
            1,
            "Brightpath Freight — Proposal. Annual fee: three hundred and ninety "
            "thousand pounds (£390,000). Service level: 98.0% on-time delivery, "
            "measured quarterly.",
        ),
        (
            1,
            "Liability. Brightpath's aggregate liability is capped at fifty "
            "percent (50%) of the annual fee. Brightpath requires the Buyer to "
            "indemnify it against third-party claims arising from the Buyer's "
            "instructions.",
        ),
    ],
)

_DRAFT_TERMS = build_document(
    "Draft-MSA-Terms.txt",
    [
        (
            1,
            "Draft Contract Terms. The Buyer's standard terms require a liability "
            "cap of at least one hundred and fifty percent (150%) of the annual "
            "fee and prohibit any Buyer-side indemnity of the supplier.",
        ),
        (
            1,
            "Governing Law. The Buyer's standard terms are governed by the laws of "
            "England and Wales. Any service level below 99.0% on-time delivery "
            "requires director-level approval.",
        ),
    ],
)

RFQ_MATTER_NAME = "Helix Logistics RFQ — vendor evaluation"

RFQ_DOCS: list[FixtureDocument] = [
    _RFQ_INSTRUCTIONS,
    _VENDOR_NORTHSTAR,
    _VENDOR_BRIGHTPATH,
    _DRAFT_TERMS,
]

SUBAGENT_SCENARIOS: list[Scenario] = [
    Scenario(
        id="rfq_single_fact",
        title="Single fact — direct answer, no delegation",
        note=(
            "One fact in one document (the submission deadline). Best path is a "
            "direct grounded fetch — a single short question does NOT warrant "
            "spawning a subagent. Finding if the model delegates anyway."
        ),
        prompt="What is the submission deadline stated in the RFQ instructions for this matter?",
        expect_tools=("search_documents",),
        forbid_tools=("task",),
        step_bound=6,
        must_include=("30 September 2026",),
    ),
    Scenario(
        id="rfq_cross_document_review",
        title="Cross-document review — delegate to the researcher",
        note=(
            "A broad review spanning four documents and several independent "
            "questions (price, SLA, liability per vendor, vs the draft terms). "
            "Best path is to delegate per-vendor / per-question investigation to "
            "the document-researcher subagent. Finding if the model does not "
            "delegate, or cannot converge within the step cap (the honest "
            "tier-4 qualification result, NOT tuned green)."
        ),
        prompt=(
            "Review this RFQ across all of the documents in the matter. Compare "
            "the two vendor proposals on price, service level, and liability, "
            "check each against our draft contract terms, and flag the key risks "
            "for us. Cite the document name for each point."
        ),
        expect_tools=("task",),
        step_bound=20,
        must_include=("Northstar", "Brightpath"),
    ),
]
