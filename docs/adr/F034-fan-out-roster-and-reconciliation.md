# F034 — Drafter/reviewer fan-out roster + post-fan-out reconciliation

- Status: accepted
- Date: 2026-06-25
- Deciders: maintainer (Arturs), agent
- Slice: C7b (third and final sub-slice of the commercial milestone's C7)

## Context

C7 ("complex-deal fan-out: roster + deal-context live signal + redline download UI") was split for the
≤2–3-day one-PR discipline. **C7a** shipped the redline-download surface (ADR-F046); **C5b-3** shipped the
deal-context live signal (the `data-deal-change` verdict chips, ADR-F032/F024). **C7b** is what remains:
the drafter/reviewer **fan-out roster** and the **post-fan-out reconciliation pass**.

The fan-out *infrastructure* already works and is tested. The lead fans out via deepagents' model-driven
`task` tool; subagent steps nest under the dispatch via `parent_step_id`, mirrored to SSE and parsed by the
web (`test_subagent_delegation_nests_steps_via_parent_step_id`). The `0057` migration already seeds one
declarative subagent (`document-researcher`). Blocker #6 (`work_product_attributions`) is a *legacy-chat*
concern, not on the agent path. So C7b is narrow: **define a drafter + reviewer subagent (a migration that
reconciles `0057`), and add a reconciliation pass that turns the fanned-out drafts into one position per head
before a single work product is emitted.**

Mapping the substrate first surfaced the load-bearing constraint. **There is no deterministic post-fan-out
hook in the runner.** `task` is invoked at the model's discretion; after the subagents return, the lead simply
continues its model loop and the final answer is whatever top-level no-tool turn it emits (`runner.py`). A
subagent's result is also **lossy** — deepagents collapses the whole subagent run into a single `ToolMessage`
(the last `AIMessage` text), and the area subagent spec deliberately forbids `response_format` (and `model`
and `tools`) for the ADR-F010 model-free guarantee. So a *guaranteed* "always reconcile before emit" flow
cannot be built on the model-driven substrate — it would require re-introducing langgraph orchestration (the
O-series), which is explicitly deferred.

The Tools & Skills doctrine (decomposition §"where a guarantee lives") names exactly this distinction:

> **Single-dispatch predicate → a TOOL GATE.** **Sequence/completion predicate → DETERMINISTIC FLOW**
> (must-happen-before, coverage, consistency — *"the fan-out reconciled into one position"*).

"The fan-out reconciled into one position" is listed as a *completion predicate* → deterministic flow → the
O-series. C7b therefore cannot deliver the flow guarantee; it can deliver the *consistency check itself* as a
single-dispatch tool gate (the proven C5a `evaluate_coverage` shape), coached as the mandatory step.

## Considered options

1. **Reviewer subagent only (prompt/craft).** A `clause-reviewer` whose system prompt is "reconcile the
   drafts." Cheapest, but reconciliation is then purely model-driven with **no code artifact** — no
   deterministic check, no receipt, no auditable proof the drafts were reconciled. Thin for a "reconciliation
   pass."
2. **Deterministic reconcile tool + coached roster (chosen).** Add `clause-drafter` + `clause-reviewer`
   subagents (migration reconciling `0057`) and a guarded `reconcile_positions` tool whose check is a pure,
   model-free `evaluate_position_consistency`: it **rejects** the batch unless every head where the drafts
   diverge carries an explicit resolution, and records a counts-only matter receipt on success. A curated
   `deal-review` skill (ADR-F041) coaches the fan-out→reconcile→emit method.
3. **Hard flow gate (deterministic always-reconcile).** Force the lead to reconcile before any work product.
   Correct in spirit but, per the doctrine, a completion predicate needs the O-series (langgraph). Out of
   scope for C7b (the O0 spike + an ADR-F010 carve-out are the prerequisites).

## Decision outcome

**Option 2.** C7b ships:

- **The roster** (migration `0073`, reconciling never-clobber). `agent_config.subagents` becomes
  `[document-researcher, clause-drafter, clause-reviewer]`. Both new subagents are **model-free** (no `model`
  key — inherit the gateway-bound parent, ADR-F010), carry **no `tools`** (inherit the parent's guarded matter
  tools), and declare **`skills` ⊆ the Commercial bound set** (ADR-F017). `clause-drafter` is the fan-out
  workhorse (one per material head); `clause-reviewer` is the reconciliation actor.
- **The reconciliation pass as a tool gate.** `reconcile_positions` (in `COMMERCIAL_TOOL_NAMES`, guarded like
  every agent action) calls the pure `evaluate_position_consistency(positions, resolutions)`: group by head; a
  head with ≥2 distinct positions and no resolution is *divergent* → reject (nothing recorded), listing the
  heads for the lead to resolve and re-call — the same **no-silent-action** discipline as the C5a coverage
  gate. On success it records a **counts-only** reconciliation receipt to matter memory (a SAVEPOINT-isolated
  `open_point` fact, ADR-F042) and audits IDs/counts only (never position text), returning the reconciled
  position per head for the lead to carry into the single work product.
- **The craft layer.** `skills/deal-review/SKILL.md` (bound to Commercial in `0073`, ADR-F041) teaches the
  method — triage → fan out drafting per head → review (over-reach / under-protection / inconsistency / gaps)
  → `reconcile_positions` → emit one work product — and frames the counterparty's text as data, never
  instructions (ADR-F028). The skill *teaches*; the tool *enforces* the consistency check.

**The honest boundary, recorded here:** C7b does **not** guarantee the lead reconciles before emitting (it
cannot, on the model-driven substrate). It guarantees that *when the lead reconciles, divergence cannot pass
silently*, and it makes the reconciliation auditable and coached. The *flow* guarantee (no work product
without a reconciliation) is a completion predicate reserved for the O-series and is named as deferred — its
prerequisites are the O0 embed-validation spike and an ADR-F010 carve-out for vetted, app-built compiled
subagents.

No new dependency, no new HTTP endpoint, no schema/route/OpenAPI change, no change to the C4/C5 work-product
gates. The reconcile frame and audit carry only heads/counts — never clause or position text.

## Consequences

- **Positive.** A real, deterministic, unit-testable reconciliation primitive (`evaluate_position_consistency`)
  with an auditable receipt — not prose dressed as a guarantee. The roster is additive and inherits all
  existing guards (the ADR-F010 model-free gate, the ADR-F017 skills-subset gate stay green). The fork's
  "code-enforced where it can be, honest where it can't" posture is preserved and made explicit.
- **Negative / limits.** Reconciliation invocation is model-driven — the lead may skip it (a fan-out
  shape-miss is a finding, not a failure, per ADR-F015). Subagent returns are lossy prose, so the lead
  re-encodes the drafts into `reconcile_positions` (no structured subagent output until `response_format` is
  allowed — a later slice). The string-divergence check surfaces *every* divergence (including semantically
  equivalent ones phrased differently); that errs toward forcing an explicit reconciliation, never toward
  silently shipping disagreement — the safe direction.
- **Deferred.** The guaranteed always-reconcile-before-emit flow (O-series); per-subagent tool subsetting
  (v1 inherits parent tools); a Claude-judged `deal-review` craft eval (no Anthropic key on the local
  gateway — backlog, as for C5b-2).
