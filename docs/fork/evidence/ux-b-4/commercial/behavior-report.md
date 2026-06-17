# UX-B-4 — commercial scenario behavior report

- **Milestone:** UX-B-4 (gate: ADR-F015)
- **Practice area:** commercial
- **Model:** alias 'smart' is expected to resolve to MiniMax-M3 (tier-4) via the gateway's operator-configured routing — the only S9-qualified provider today. The gateway owns the alias→model mapping; this report observes the loop's behaviour, not the resolved model name.
- **Generated:** 2026-06-17T09:43:41+00:00
- **Result:** 0/2 scenarios matched expected shape · 2/2 ran to `completed`

> Per ADR-F015 a scenario that does not match its expected shape is a **finding** that calibrates the area profile / tier floor, not a test failure. The harness asserts only that every scenario produced a terminal run + receipts.

> **Reading the checks:** the `shape_matched` verdict is a coarse heuristic (substring + step-bound matching) — the **final-answer excerpt is the authoritative record** of what the model did. A `refusal_ok=False` or `should_not_ok=False` can be a heuristic false-positive (e.g. a false-confirmation phrase appearing inside a *negated* sentence); read the excerpt before treating a finding as a model defect. Live runs are non-deterministic, so step counts / latencies / tool choices vary run to run — that variance is itself a tier-4 observation.

## Summary

| Scenario | Status | Shape | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- | --- |
| Single fact — direct answer, no delegation | `completed` | ⚠️ finding | search_documents, read_document | 7 | 7.9s |
| Cross-document review — delegate to the researcher | `completed` | ⚠️ finding | search_documents, read_document, read_document, read_document, read_document | 13 | 76.8s |

## Per-scenario detail

### Single fact — direct answer, no delegation (`rfq_single_fact`)

_One fact in one document (the submission deadline). Best path is a direct grounded fetch — a single short question does NOT warrant spawning a subagent. Finding if the model delegates anyway._

- **Prompt:** What is the submission deadline stated in the RFQ instructions for this matter?
- **Status:** `completed`
- **Tools called:** search_documents, read_document  (expected: search_documents; forbidden: task)
- **Steps:** 7 · model turns: 3 · latency: 7.9s
- **Delegation:** 0 `task` call(s) · delegated=False
- **Checks:** expected_tools_present=True, forbidden_tools_absent=True, must_include_ok=True, should_not_ok=True, within_step_bound=False

**Final answer (excerpt):**

```
<think>Found it. The RFQ instructions state that quotations must be submitted by no later than 5:00pm on 30 September 2026. Late submissions will not be considered.</think>

The submission deadline stated in the RFQ instructions is **5:00pm on 30 September 2026**.

Per RFQ-Instructions.txt, §1: "Quotations must be submitted by no later than 5:00pm on 30 September 2026. Late submissions will not be considered."
```

### Cross-document review — delegate to the researcher (`rfq_cross_document_review`)

_A broad review spanning four documents and several independent questions (price, SLA, liability per vendor, vs the draft terms). Best path is to delegate per-vendor / per-question investigation to the document-researcher subagent. Finding if the model does not delegate, or cannot converge within the step cap (the honest tier-4 qualification result, NOT tuned green)._

- **Prompt:** Review this RFQ across all of the documents in the matter. Compare the two vendor proposals on price, service level, and liability, check each against our draft contract terms, and flag the key risks for us. Cite the document name for each point.
- **Status:** `completed`
- **Tools called:** search_documents, read_document, read_document, read_document, read_document  (expected: task; forbidden: —)
- **Steps:** 13 · model turns: 3 · latency: 76.8s
- **Delegation:** 0 `task` call(s) · delegated=False
- **Checks:** expected_tools_present=False, forbidden_tools_absent=True, must_include_ok=True, should_not_ok=True, within_step_bound=True

**Final answer (excerpt):**

```
<think>Now I have all the information I need. Let me analyze and structure this carefully.

**RFQ Instructions (RFQ-Instructions.txt):**
- Buyer: Helix Manufacturing Limited
- Submission deadline: 5:00pm, 30 September 2026
- Evaluation weights: Price 40%, Service levels 35%, Contractual risk/liability 25%
- Not bound to accept lowest

**Brightpath Proposal (Vendor-Proposal-Brightpath.txt):**
- Price: £390,000/year
- Service level: 98.0% on-time, measured quarterly
- Liability cap: 50% of annual fee
- Requires buyer-side indemnity for third-party claims from buyer's instructions

**Northstar Proposal (Vendor-Proposal-Northstar.txt):**
- Price: £420,000/year
- Service level: 99.5% on-time, measured monthly
- Liability cap: 100% of annual fee
- Excludes indirect/consequential loss

**Draft MS…
```
