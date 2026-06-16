# UX-B-2 — privacy scenario behavior report

- **Milestone:** UX-B-2 (gate: ADR-F015)
- **Practice area:** privacy
- **Model:** alias 'smart' is expected to resolve to MiniMax-M3 (tier-4) via the gateway's operator-configured routing — the only S9-qualified provider today. The gateway owns the alias→model mapping; this report observes the loop's behaviour, not the resolved model name.
- **Generated:** 2026-06-16T17:22:46+00:00
- **Result:** 3/3 scenarios matched expected shape · 3/3 ran to `completed`

> Per ADR-F015 a scenario that does not match its expected shape is a **finding** that calibrates the area profile / tier floor, not a test failure. The harness asserts only that every scenario produced a terminal run + receipts.

> **Reading the checks:** the `shape_matched` verdict is a coarse heuristic (substring + step-bound matching) — the **final-answer excerpt is the authoritative record** of what the model did. A `refusal_ok=False` or `should_not_ok=False` can be a heuristic false-positive (e.g. a false-confirmation phrase appearing inside a *negated* sentence); read the excerpt before treating a finding as a model defect. Live runs are non-deterministic, so step counts / latencies / tool choices vary run to run — that variance is itself a tier-4 observation.

## Summary

| Scenario | Status | Shape | Tools called | Steps | Latency |
| --- | --- | --- | --- | --- | --- |
| Grounded fetch — lawful basis | `completed` | ✅ | search_documents, search_documents | 6 | 7.8s |
| No tool needed (general knowledge) | `completed` | ✅ | — | 1 | 18.0s |
| Ambiguous → clarify | `completed` | ✅ | search_documents | 4 | 14.9s |

## Per-scenario detail

### Grounded fetch — lawful basis (`privacy_single_tool_fetch`)

_A direct fact in the ROPA — does the model search and ground the lawful basis rather than invent one?_

- **Prompt:** What is the lawful basis recorded for this processing activity in the programme?
- **Status:** `completed`
- **Tools called:** search_documents, search_documents  (expected: search_documents; forbidden: —)
- **Steps:** 6 · model turns: 2 · latency: 7.8s
- **Checks:** expected_tools_present=True, forbidden_tools_absent=True, must_include_ok=True, should_not_ok=True, within_step_bound=True

**Final answer (excerpt):**

```
<think>
I found the answer directly. The lawful basis is legitimate interests under Article 6(1)(f) of the UK GDPR, recorded in the Customer-Analytics-ROPA.txt on page 1. Let me provide a concise answer with the citation.
</think>
The lawful basis recorded for the Customer Analytics processing activity is **legitimate interests under Article 6(1)(f) of the UK GDPR**.

Source: *Customer-Analytics-ROPA.txt*, page 1 (section 1, "Processing Activity and Lawful Basis"). The purpose recorded alongside it is "product improvement and usage analysis."
```

### No tool needed (general knowledge) (`privacy_no_tool_needed`)

_A general-knowledge question with an explicit no-documents framing — does the model answer directly, or burn a tool call it was told to skip?_

- **Prompt:** Without consulting any documents in this programme, briefly explain in general terms what a Data Protection Impact Assessment (DPIA) is.
- **Status:** `completed`
- **Tools called:** —  (expected: —; forbidden: search_documents, read_document)
- **Steps:** 1 · model turns: 1 · latency: 18.0s
- **Checks:** expected_tools_present=True, forbidden_tools_absent=True, must_include_ok=True, should_not_ok=True, within_step_bound=True

**Final answer (excerpt):**

```
<think>
The user is asking a general question about what a DPIA is, and explicitly says "Without consulting any documents in this programme." So I should not use search_documents or read_document tools. I should just answer from general knowledge as a privacy practice agent.

A DPIA under the UK GDPR/GDPR is:
- Article 35 GDPR / UK GDPR Article 35
- Required where processing is "likely to result in a high risk to the rights and freedoms of natural persons"
- It's a process to help identify and minimise data protection risks
- Describes the processing, assesses necessity and proportionality, assesses risks, and identifies mitigations
- Must be conducted before processing begins
- Consultation with DPO is required
- ICO provides guidance; list of processing requiring DPIA exists (Article 35(…
```

### Ambiguous → clarify (`privacy_ambiguous_clarify`)

_An unresolved referent ('it') — does the model ask, or guess a subject?_

- **Prompt:** Is it compliant?
- **Status:** `completed`
- **Tools called:** search_documents  (expected: —; forbidden: —)
- **Steps:** 4 · model turns: 2 · latency: 14.9s
- **Checks:** expected_tools_present=True, forbidden_tools_absent=True, must_include_ok=True, should_not_ok=True, within_step_bound=True, clarify_ok=True

**Final answer (excerpt):**

```
<think>
The matter has a single document — a Customer Analytics ROPA. The user's question "Is it compliant?" is genuinely ambiguous: compliant with what? Against which standard? The ROPA itself, a specific processing activity in it, a proposed change, etc.

I should ask a brief clarifying question rather than guess. The user has given me essentially nothing to anchor on.
</think>
The matter contains a single document: **Customer-Analytics-ROPA.txt** (2 pages) — the records-of-processing register for a customer analytics programme.

"Is it compliant?" is too open-ended for me to act on without guessing. To give you a grounded answer I need to know what specifically you want assessed. A few likely candidates — let me know which (or describe your own):

1. **The ROPA itself** — is the registe…
```
