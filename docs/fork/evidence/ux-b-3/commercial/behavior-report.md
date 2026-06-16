# UX-B-3 — commercial scenario behavior report

- **Milestone:** UX-B-3 (gate: ADR-F015)
- **Practice area:** commercial
- **Model:** alias 'smart' is expected to resolve to MiniMax-M3 (tier-4) via the gateway's operator-configured routing — the only S9-qualified provider today. The gateway owns the alias→model mapping; this report observes the loop's behaviour, not the resolved model name.
- **Generated:** 2026-06-16T20:50:51+00:00
- **Result:** 1/2 scenarios matched expected shape · 1/2 ran to `completed`

> Per ADR-F015 a scenario that does not match its expected shape is a **finding** that calibrates the area profile / tier floor, not a test failure. The harness asserts only that every scenario produced a terminal run + receipts.

> **Reading the checks:** the `shape_matched` verdict is a coarse heuristic (substring + step-bound matching) — the **final-answer excerpt is the authoritative record** of what the model did. A `refusal_ok=False` or `should_not_ok=False` can be a heuristic false-positive (e.g. a false-confirmation phrase appearing inside a *negated* sentence); read the excerpt before treating a finding as a model defect. Live runs are non-deterministic, so step counts / latencies / tool choices vary run to run — that variance is itself a tier-4 observation.

## Summary

| Scenario | Status | Shape | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- | --- |
| Grounded review (skills on) | `completed` | ✅ | search_documents, read_document | 7 | 34.3s |
| Skill recognition (skills on) | `cap_exceeded` | ⚠️ finding | search_documents, read_file, read_document, read_file, read_file, read_file, read_file | 16 | 7.3s |

## Per-scenario detail

### Grounded review (skills on) (`skill_grounded_review`)

_With the area's review skills exposed, does the model still ground the limitation-of-liability answer in the document and cite it, rather than answering from the skill prose or wandering the bigger tool surface?_

- **Prompt:** As the customer, review the limitation of liability clause in the Acme MSA in this matter: what is the cap, and is it acceptable? Quote the clause and cite the section.
- **Status:** `completed`
- **Tools called:** search_documents, read_document  (expected: search_documents; forbidden: —)
- **Steps:** 7 · model turns: 3 · latency: 34.3s
- **Checks:** expected_tools_present=True, forbidden_tools_absent=True, must_include_ok=True, should_not_ok=True, within_step_bound=True

**Final answer (excerpt):**

```
<think>
Now I have a complete picture. Let me analyze the limitation of liability clause from a customer's perspective:

**The Clause (Section 7):**
"Except for liability arising from a breach of confidentiality or either party's indemnification obligations, each party's aggregate liability under this Agreement shall not exceed the total fees paid by Customer in the twelve (12) months immediately preceding the event giving rise to the claim. Neither party shall be liable for any indirect, incidental, or consequential damages."

**Analysis from Customer's Perspective:**

1. **The Cap:** 12 months of fees paid by Customer (a "12-month lookback" cap).

2. **Acceptability from a customer standpoint:**
   - **Concerning aspects:**
     - The cap is tied to fees *paid* in the prior 12 months, wh…
```

### Skill recognition (skills on) (`skill_recognition`)

_A request squarely matching a bound review skill — does the model recognise the skill (read its SKILL.md via read_file) and/or apply a structured review, while still grounding in the document? Observation only: whether it reaches for the skill is the finding._

- **Prompt:** Do a structured risk review of the Acme MSA in this matter from the customer's perspective, and flag anything a buyer should worry about, with citations.
- **Status:** `cap_exceeded`
- **Tools called:** search_documents, read_file, read_document, read_file, read_file, read_file, read_file  (expected: search_documents; forbidden: —)
- **Steps:** 16 · model turns: 2 · latency: 7.3s
- **Checks:** expected_tools_present=True, forbidden_tools_absent=True, must_include_ok=True, should_not_ok=True, within_step_bound=False

**Final answer (excerpt):**

```
(no final answer)
```
