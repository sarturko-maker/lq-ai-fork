# F084 — Agent-offered adversarial review (the hostile reader)

Status: proposed (drafted 2026-07-12, maintainer decision 2026-07-11: "agent offers, human confirms")

## Context

The maintainer wants the agent able to red-team its own near-final work product — a hostile read of a
redline/draft for over-reach, under-protection, internal inconsistency, and missing material heads —
before the lawyer takes the document. It burns tokens, so it must NOT run every turn; the chosen shape
(AskUserQuestion, 2026-07-11) is **the agent proposes the review and the human confirms; approving
spends the tokens**.

Two structural facts (verified in code) shape the design:

1. **Subagents are un-gateable by HITL.** The confirm-card machinery (ADR-F071) only pauses on a
   top-level LEAD tool present in the run's grant set — `compile_hitl_policy` drops non-granted names,
   deepagents builtins (`task`) are never granted, and fork-authored subagents are stamped
   `interrupt_on={}` (`hitl.py:88`). So ADV-1's original "roster subagent" framing cannot carry the
   offer; the review must be a **top-level tool**.
2. **The purpose-specific gateway pass is a shipped pattern.** `consolidate_matter_memory`
   (ADR-F043) and the citation judge each issue ONE bounded, gateway-routed chat completion with
   their own `lq_ai_purpose`, code-validate the untrusted output against a Pydantic schema, and
   reject-not-crash on any failure. The hostile reader is the same shape over a document.

## Considered options

1. **Reviewer subagent only** (the original ADV-1 sketch) — rejected: structurally cannot pause for
   the human's go-ahead (see above), and subagent output is lossy prose the lead must re-encode.
2. **Deterministic post-`apply_redline` offer middleware** — rejected: re-derivation risk; F071
   already rejected this shape (option 3); it would interrupt every emit.
3. **Top-level `adversarial_review` tool riding the redlining group, HITL-gateable, performing a
   purpose-specific gateway pass** — chosen.

## Decision outcome

- **`adversarial_review` is a top-level LEAD tool** in the **redlining group's grant set**
  (`COMMERCIAL_TOOL_NAMES`), built by its own builder (`app/agents/adversarial_review.py`, narrow
  guard grant) invoked from the group's `_build_redlining` adapter. Riding the existing group means:
  no migration for availability (wherever redlining is bound+adopted, review is available), automatic
  membership in `hitl_eligible_tool_names()`, and automatic appearance in the area admin's
  stop-and-ask checklist.
- **The work** = ONE gateway chat completion (`lq_ai_purpose="adversarial_review"`), alias from
  `LQ_AI_ADVERSARIAL_REVIEW_MODEL` (default `smart`), hard `max_tokens` cap, `anonymize=False`
  (judging real clause text, same posture as consolidation/negotiation). Input = the named matter
  document (owner+matter scoped, OOXML-guarded via `load_matter_docx_bytes`), rendered as the current
  text + its tracked changes; bounded input size with an honest truncation notice. Output = strict
  JSON findings (severity / kind / clause anchor / issue / suggestion), code-validated
  (`app/schemas/adversarial_review.py`, bounded counts + field caps), reject-and-retry on any
  malformed output or gateway failure — never a crash, never partial acceptance.
- **The offer** = the shipped HITL loop: an admin sets `hitl_policy={"adversarial_review": true}` →
  the agent's proposed call pauses the run (`awaiting_input`), the lawyer sees the confirm card,
  Approve executes the exact checkpointed call, Refuse closes the turn. **Default OFF** (zero-config
  invariant, F071 D2). Ungated, the tool still works — the skill coaches the agent to propose the
  review conversationally at high-stakes moments and respect the answer, so the behavior is
  "offered, not automatic" in both modes.
- **The craft** lives in `skills/adversarial-review/SKILL.md` — stance-distinct from `deal-review`
  (reconciling N parallel drafts) and `negotiation-review` (counterparty rounds): this is the hostile
  read of ONE near-final work product, plus the WHEN-to-offer / WHEN-to-skip judgment (liability
  caps, indemnities, a document about to be handed over → offer; routine lookups, small NDAs → skip).
  Bound to Commercial by migration + profile manifest + `RECOMMENDED_LIBRARY_SETS` (the T3 pattern,
  post-B7a: seeded state, manifest, and recommendation constant move together or the parity oracle
  fails).
- **Receipts**: the audit row carries counts only (findings by severity/kind, document id) — never
  clause text (ADR-F005 contract). The findings themselves return to the LEAD as the tool result
  (fenced as untrusted-adjacent analysis for the lawyer to weigh).

## Consequences

- Where redlining is enabled, review is available with zero admin work; the pause card appears only
  after an explicit admin opt-in (per-area HITL toggle). Whether the shipped Commercial profile
  should default the toggle ON rides the maintainer's existing profile-HITL decision (same question
  as `apply_redline`) — not pre-empted here.
- The review's own gateway pass draws real tokens (R4 counts it; a resume is a new run row, so a
  paused turn can spend up to 2× envelope — recorded, not tightened).
- No guaranteed "always review before emit" — model-driven substrate, no deterministic pre-emit hook
  (ADR-F034 honest boundary); ADV makes review *offered and audited*, not mandatory. O-series owns
  any hard guarantee.
- No simulated counterparty markup in this slice (needs the ADV-2 simulation-fence ADR; gated).
- The seeded-defect recall eval (C9-style judge) gates the CRAFT claim; if the dev box cannot run it
  (ONNX OOM), it is deferred on record with the recipe captured — ADR-F015 discipline (confirm the
  tool is wired before reading any recall number as a model trait).
