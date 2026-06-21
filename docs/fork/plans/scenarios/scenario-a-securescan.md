# Scenario A — SecureScan buy-side first-pass triage (clean paper → prose redline)

**Status:** design (fixtures not yet built). **First** live-verification vehicle for the COMMERCIAL agent —
buildable at the current pickup (C1 + C-CLIENT + C0; **no C4/C5**). Synthetic/illustrative — NOT Zendesk's
real legal positions. Designed 2026-06-21 (adversarial-reviewed: re-scoped from an over-reaching first draft
to what actually ships now).

## One-liner

Zendesk (the **customer**) sends clean SecureScan vendor paper for a first-pass procurement review. The agent
ingests the multi-format set (**C1**), recognises the **buy-side flip** from the injected house context
(**C-CLIENT**), holds the surgical posture (**C0**), triages signal from noise, and returns a **prose first-pass
redline + escalation memo** — *no* tool-emitted tracked-changes (that's the deferred C4 acceptance scenario)
and *no* counterparty-position extraction (the paper is clean → that's Scenario B).

## Why it runs first

Lowest dependency in the ladder: needs only slices shipped/shipping now. It extends the already-live
`CUSTOMER_PROCUREMENT` fixture (`api/tests/agents/scenarios/zendesk_client.py`) rather than forking a
near-duplicate. `apply_redline` / `propose_deal_context_update` / Adeu / any download endpoint do **not** exist
yet — so A's deliverable is the most that's buildable: a prose redline the agent produces with
`search_documents` alone.

## Deal setup

**Vendor:** SecureScan, Inc. (one locked name). **Product:** real-time threat-scanning SaaS that ingests
Zendesk support-ticket content to flag malicious attachments / phishing / PII leaks. **Shape (locked, matches
the existing fixture):** $50,000/year, 12-month term, auto-renew, New York law. **Data flow:** SecureScan reads
ticket content (guest PII + sometimes internal staff data) → it is a **sub-processor of Zendesk's customer
data**. **Why legal cares:** PII processing by a vendor whose clean paper has (a) no data-processing terms
("Data Protection. Not applicable."), (b) a 3-month liability cap (below the 12-month house floor), (c) New
York law (non-standard for a California house).

## Inbound email

- **From:** jason.martinez@zendesk.com → **To:** commercial-legal@zendesk.com
- **Subject:** First-pass review — SecureScan buy (clean paper, DPA required) — what's our redline?
- **Body (brief):** "Moving on SecureScan, a threat-detection tool for our support-ticket infra. First-pass
  buy-side review on their **clean** standard terms — us forming OUR first position, not reacting to theirs.
  They'll touch our customers' PII. $50K/yr, 12-mo, auto-renew. Per house policy we'll require a DPA. Give me a
  surgical redline + a one-line rationale per edit, flag anything needing GC, tell me what SecureScan should
  send next + our fallback. Triage signal from noise — focus on the order form."

## Attachments (the triage test)

| Bucket | File | Format | Purpose |
|---|---|---|---|
| **Primary** | `SecureScan-OrderForm.docx` (5 clauses: parties+scope; fees+term; 3-mo cap; "Data Protection. Not applicable."; NY law) | DOCX | the instrument to redline |
| **Directly relevant** | `DPA-Requirement-Brief.txt` (internal: SecureScan processes PII → DPA mandatory) | TXT | corroborates the DPA blocker (cite a source, not just the profile) |
| **Context** | `Zendesk-Ticket-Data-Classification-Policy.pdf` | PDF | DPA scope background; not a redline target |
| **Noise** | `SecureScan-Product-Brochure.pdf` | PDF | distractor — don't redline marketing |
| **Noise** | `2024-Legacy-Analytics-Vendor-NDA.docx` | DOCX | off-matter — must be recognised as not governing this deal |

## The three surgical redline moves (confined to what's in the fixture)

1. **Liability cap (3 months' fees, no carve-outs).** Below the 12-month house floor; buy-side flip forbids the
   vendor self-capping its own data-breach liability so low. → **COUNTER** (amend the figure + add a
   data-breach/IP carve-out; fallback = 2× annual super-cap) **+ ESCALATE to GC** before sending. Phrase-level,
   not a clause rewrite.
2. **Data Protection ("Not applicable.").** PII processing with no terms. → **BLOCKER**: require a DPA addendum
   as a deliverable (do **not** draft the DPA body inline — that's whole-instrument drafting). **ESCALATE to GC.**
3. **Governing law (New York).** Non-standard for a California house. → **FLAG** (counter to California /
   arbitration-in-CA acceptable), **not** a GC escalation (profile: non-standard law is "a flag, not an
   auto-accept").

## House posture applied (from the injected ZENDESK_PROFILE_MD)

Side-detection flip to buyer · DPA mandatory · liability floor (12-mo, super-cap 2× annual, never uncapped) ·
surgical house style (smallest change; controlling last word because C-CLIENT injects the profile BEFORE the
area doctrine) · give the deal owner a rationale + fallback, not just "no" · escalation list (PII-without-DPA
and below-floor cap → GC; governing law → flag).

## Expected agent behaviour → slice coverage

INGEST multi-format (**C1**) → TRIAGE signal/context/noise; ignore the legacy NDA + brochure (**C0**) → LOAD
client context (injected, no tool call — **C-CLIENT**) → SIDE-FLIP to buyer → SEARCH + ground every assertion
in clause text (**C0**) → APPLY house triggers → DRAFT prose surgical first-pass redline w/ rationale + fallback
(**C0**) → ESCALATE (DPA + cap to GC) / FLAG (law) / hand off to the deal owner (human owns the commercial call).

**Not exercised:** C3 (no `propose_deal_context_update`) · C4 (prose, no tracked-changes tool) · C2 (standalone
files, no chain; no `.eml`) · C5 (clean paper, no inbound redline) · C6/C7 (single-turn, small set).

## Pass signals (findings per ADR-F015 — recorded, not hard-asserted)

Side-flip to customer/buyer · DPA blocker raised + addendum required · surgical posture (narrow edits, no
whole-clause rewrite, no inline DPA draft) · 3-mo cap identified below floor → GC · governing law handled as a
flag (CA counter), not escalated · triage focuses on the order form (+ DPA brief), ignores legacy NDA + brochure
· **honest scope** (does NOT claim a tracked-changes `.docx` or a deal-context write) · Receipt `completed`,
`search_documents` used, `model_turns ≥ 2`, no `cap_exceeded` (raise `max_steps` above the harness default 16).

## Fixtures to build (when wiring the live run)

Extend `zendesk_client.py` (don't fork): keep `ZENDESK_PROFILE_MD`; add `build_securescan_order_form()` →
`FixtureDocument` (5 short sections, ONE cap = 3 months', ONE vendor name); add the noise/context fixtures;
add a `Scenario` (existing dataclass fields only — `expect_tools=('search_documents',)`,
`must_include=('DPA','liability','data')`, no `docs` field — docs seed via the harness). Wire via
`seed_multi_doc_matter(factory, area_key='commercial', docs=[...], matter_name='SecureScan — procurement
(first pass)')` in a provider-marked test, profile ON, `skill_registry=` set, `max_steps` raised. All fixtures
keep the ILLUSTRATIVE/SYNTHETIC header.

## Distinct from Scenario B

A = **clean paper**, first position, no C5, prose deliverable. B (Project Meridian) = **inbound redlines** →
owns the `.eml`/`.msg` chain (C2) + counterparty-position extraction (C5) + heavier Adeu work (C4). See
`scenario-b-meridian.md`.
