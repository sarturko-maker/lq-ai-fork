# Plan — ADV-1: agent-offered adversarial review ("hostile reader")

**Status:** drafted 2026-07-11 · revises task #511 (ADV-1) per maintainer decision.
**BUILD IN FLIGHT 2026-07-12** (overnight run): ADR-F084 drafted; module
(`app/agents/adversarial_review.py`), schema (`app/schemas/adversarial_review.py`), mig `0097`
(bind skill + users-gated Library adoption), and an 8-test stub-gateway suite are WRITTEN (parked in
the session scratchpad while the WORKSPACE PR's full suite runs — mounted-repo race discipline).
Design deltas vs the draft below, locked by code reading: the tool rides `COMMERCIAL_TOOL_NAMES`
(the redlining group) via its own narrow builder appended in `_build_redlining` — no new tool group,
no availability migration; the review pass reads the document through
`load_matter_docx_bytes → read_state_of_play` (clean view, 60k-char cap with HONEST truncation);
alias env var is `LQ_AI_ADVERSARIAL_REVIEW_MODEL` (default `smart`). Remaining wiring + gate in
HANDOFF banner ②.
**Linked ADRs:** F034 (fan-out roster + reconciliation), F071 (HITL pause/offer), F032 (no-silent-action),
F041/F015 (craft-by-eval / confirm-capability-first), F010 (gateway sole egress).
New ADR: **F084** (agent-offered adversarial review) — references F034 + F071.

## Why

The agent should be able to red-team its own near-final work product — a hostile read for over-reach,
under-protection, internal inconsistency, and missing material heads — before the lawyer takes the
document. It burns tokens, so it must NOT run every turn. Maintainer decision (2026-07-11):
**the agent OFFERS it and the human confirms.** The agent proposes a review at high-stakes moments;
the lawyer sees a confirm card ("Run a hostile-reader pass over this redline?"); approving spends the
tokens, skipping finishes without it.

## The key structural finding (why this shape)

The shipped **HITL** loop (ADR-F071) is exactly "agent proposes an action → human sees a confirm card
→ approve executes the exact reviewed action". It is reusable for the offer — **but only for a
top-level LEAD tool**. The deepagents `task` builtin and fork-authored subagents are structurally
**un-gateable** (`stamp_subagent_opt_out` sets `interrupt_on={}`; builtins are never in the grant set,
`hitl.py:88`, `capabilities.py:313`). So the original ADV-1 "roster subagent" framing cannot carry the
offer card. **Adversarial review must be a top-level tool the agent proposes.**

The review work itself is a **purpose-specific gateway call**, following the shipped precedent of
`matter_consolidation` (`matter_consolidation.py:143`) and the citation judge: the tool issues its own
`ChatCompletionRequest` through the gateway with a hostile-reader system prompt over the target
document/redline and its own `lq_ai_purpose`, returns structured findings, and records a counts-only
receipt. This sidesteps the subagent-ungateable problem entirely and reuses an existing, gatewayed,
auditable pattern.

## Design

1. **`adversarial_review` — a top-level LEAD tool** in a Commercial tool group, added to that group's
   `*_TOOL_NAMES` frozenset (so it is grant-set-visible → HITL-gateable → admin-toggleable) and to
   `hitl_eligible_tool_names()` coverage (drift-guarded by `test_capabilities.py`). Guarded via
   `guarded_dispatch` (R4/R5/R6) like every tool. Argument = the target work-product file/redline id
   (+ optional focus like "liability/indemnity"). On run: a gateway hostile-reader pass → structured
   findings (over-reach / under-protection / inconsistency / gaps), each anchored to a clause; records
   a receipt (counts/heads/ids only, never clause text).
2. **The offer** = admin sets `hitl_policy = {"adversarial_review": true}` for the area (via the
   shipped `PUT /practice-areas/{key}/hitl-policy`). When the agent proposes the call, the run pauses
   and settles `awaiting_input`; the lawyer sees the confirm card; **Approve** executes the exact
   checkpointed call (bytes pinned, ADR-F071 D4), **Refuse** closes the turn honestly. Default OFF
   (zero-config invariant — unconfigured area's graph stays byte-identical).
3. **A skill `adversarial-review/SKILL.md`** coaching the LEAD **when to propose** it (high-stakes:
   liability caps, indemnity, big exposure, a document about to be handed over) and **when to skip**
   (routine lookup, a small NDA) — so the offer is scarce, not every turn. **Stance-distinct** from
   `deal-review` (which reconciles N drafts) and `negotiation-review` (counterparty rounds): this is a
   red-team of ONE near-final draft. (Maintainer's own bar: stance-distinct or it dies in review.)
4. **Card copy** = bespoke "Run a hostile-reader pass over this redline?" by keying the web
   `HitlConfirmCard` off `step.name == "adversarial_review"` (web-only reskin; fork-authored copy,
   never model/document text — prompt-injection boundary, ADR-F071 D4). Raw args stay collapsible.
5. **Seeded-defect eval** on the C9/CUAD masked-judge substrate: plant defects in a contract, confirm
   the reviewer catches them; compare coached-vs-uncoached (ADR-F015 — a low score is not a model
   trait until the tool is verified wired). **OOM-aware**: the dev box OOMs on parallel ONNX embedder
   spikes; if it can't run, defer the eval on record with the recipe captured (precedent: T4).

## Non-goals
- **No simulated counterparty markup** in this slice (needs an ADV-2 simulation-fence ADR; gated).
- **No guaranteed "always review before emit"** — the model-driven substrate has no deterministic
  pre-emit hook (ADR-F034 honest boundary); that is O-series. ADV-1 makes review *offered + audited*,
  not mandatory. Do not promise otherwise.
- **No scope-on-approve** ("review only the indemnity") — v1 HITL decisions are approve/reject only;
  the WHY-1 rationale seam (#513) is where that would later extend.
- **No new offer-frame type** — reuse the settled `hitl_request` step + confirm card (ADR-F004);
  don't build a bespoke interactive chip.

## Traps
- **Subagent un-gateability** — the offer tool must be top-level LEAD; a `task`-dispatched reviewer
  can never pause. (A non-gated reviewer subagent MAY still exist for free-form fan-out, but it is not
  the offer path.)
- **Zero-config invariant (hard)** — default OFF, admin opt-in; `compile_hitl_policy` must return
  None for an unconfigured area (byte-identical graph); regression-pin it.
- **Card copy is fork-authored, never model text**; retrieved doc/markup renders escaped.
- **Approve pins bytes + still passes `guarded_dispatch`** — an approval never widens a grant or
  bypasses a brake.
- **Drift guards** — adding `adversarial_review` trips `test_endpoints`/`test_openapi`/
  `test_mutation_rbac`/`test_capabilities`; bump deliberately.
- **Token/budget** — a resume is a NEW run row (a turn can spend up to 2× envelope across a pause);
  the review's own gateway pass draws real tokens — factor into R4 / fan-out quota expectations.
- **Gateway sole egress** — the review's model call routes through the gateway only (like
  `matter_consolidation`), never a direct provider call.
- **Eval discipline** — confirm the tool is wired before reading any recall number as a model trait.

## Verification / DoD
- Container suites quoted (API + web); mypy `app`. Live: on a throwaway matter with the area's
  `adversarial_review` HITL toggle on, ask for a redline → agent proposes review → confirm card →
  Approve runs the pass and returns findings; Refuse finishes cleanly. Evidence under
  `docs/fork/evidence/adversarial-review/`. ADR-F084 drafted. HANDOFF + memory updated. Full ADR-F005
  gate (security pass: fence, grant-set, no leaked doc text in receipts/audit).
