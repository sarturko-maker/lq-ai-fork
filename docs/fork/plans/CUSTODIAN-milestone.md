# CUSTODIAN milestone — the contract custodian-of-record slices

Status: **PLANNED — queued behind ① B-7 milestone acceptance and ② the maintainer's
enterprise-deploy vs product-features direction call.** Drafted 2026-07-11 from the 7-idea strategy
review (8-agent grounded evaluation, session `9148fb31`); maintainer directed "design plans for the
lowest-hanging fruit and put them at the right place in the queue."

## The story (why these five belong together)

The Commercial deep agent becomes the in-house team's **custodian of record** for everything a
contract **obliges** (deadlines), **threatens** (exposure), and **taught us** (whys and outcomes) —
on top of what it already does (redlines). This is one compounding product motion, not five
features:

- All structured writes land in the **same ledger** (`matter_memory_entries`, ADR-F042/F043) under
  its existing supersede-only, bi-temporal, human-corrects guarantees.
- All trust flows through the **same HITL confirm moment** (ADR-F071) — no new approval machinery.
- Extraction quality is gated by the **same eval substrate** (CUAD packs on disk, masked/C9 judges,
  scenario rig) before anyone is told to rely on it.
- Every slice **deepens** the self-host / nothing-leaves-the-building trust story; none opens a new
  ingress or egress.

Strategy kills/parks (federated pooling, a2a protocol, agent gym, contract-DSL compiler, actuarial
layer) are recorded **once, authoritatively, in `docs/fork/MILESTONES.md` § CUSTODIAN** — cite that
section, don't re-litigate here.

## Sequencing rule (the keystone constraint)

OBLIG-1 goes **first** and its `trigger_at` ADR is binding on the rest: three slices (OBLIG-1,
WHY-1, EXPO-1) extend `matter_memory_entries` semantics, and done concurrently or lazily (e.g.
overloading `valid_at` as a deadline) they corrupt the bi-temporal as-of guarantee ADR-F043 exists
to protect. Serialize schema-touching slices behind OBLIG-1; ADV-1 is deliberately disjoint
(roster + skill + eval only) and may interleave anywhere.

---

## OBLIG-1 — obligation dates: "never miss a notice window, clause cited"

The phased kernel of "contract as a runtime". NOT a state-machine compiler; obligation facts with
trigger dates plus a read panel.

- **ADR (small, new):** `trigger_at` (nullable timestamptz, + optional recurrence hint) on
  `matter_memory_entries` for `kind='fact'` — explicitly distinct from bi-temporal `valid_at`
  (when we believed it) vs trigger (when the world demands action). Additive migration only.
- **Extraction:** coach `record_matter_fact` (`fact_type='date'`, `api/app/agents/matter_fact_tools.py`)
  to populate `trigger_at` + `source_citation` for notice windows / renewal deadlines / price-review
  triggers. Skill-level coaching, no new tool surface.
- **Surface:** matter-cockpit "Upcoming obligations" list (ordered by `trigger_at`, shows trust
  level `normal` vs `human-pinned` + the citation; reuse the Memory-tab pattern, C3c-2).
- **Eval gate:** score extraction against CUAD `Notice Period To Terminate Renewal` / `Renewal Term`
  gold labels via `cuad_eval.py`'s `load_cuad` over `CUADv1.json` (`api/tests/fixtures/cuad`,
  overridable via `LQ_AI_CUAD_DIR`; note both CUAD corpora are untracked local artifacts — fetch
  before running). `sample-documents/commercial-dataroom-cuad` is the optional live-demo corpus
  only (`CUAD_DOCS_DIR`), not the gold source.
  **False negatives are the killer metric** — a missed window the lawyer trusted us to catch is
  worse than no feature. Every rendered obligation carries trust level + citation.
- **Explicit non-goals:** no cron sweep, no notifications, no email, no ERP/ticketing anything, no
  agent runs spawned by the system (NORTH-STAR gap #1 — needs its own ADR; phase-1 alerts are
  links into a user-initiated conversation only). No contract DSL, ever.
- Builds on (verified): MatterMemoryEntry `api/app/models/project.py:278` (`_MATTER_FACT_TYPES`
  has `date`/`term`), consolidation `api/app/agents/matter_consolidation.py`, HITL `api/app/agents/hitl.py`.

**OBLIG-2 (follow-on, separate slice):** deterministic **zero-LLM** arq cron sweep over `trigger_at`
+ a matter digest surface (email via `api/app/email.py` or cockpit list). Cron seam precedent:
`api/app/workers/document_pipeline.py:_build_cron_jobs`. Never spawns an agent run. The
portfolio-wide "obligations grid" needs no build — it is a tabular-grid column pack
(`api/app/agents/tabular_tool.py`, ADR-F055) and can demo today.

## ADV-1 — the hostile reader: "the second lawyer the solo GC doesn't have"

One PR on the proven roster pattern (0073 / ADR-F034):

- **Skill** `skills/adversarial-review/SKILL.md`: counterparty-counsel stance; ambiguity lenses
  (undefined terms, one-sided triggers, silent gaps, dangling modifiers, exploitable
  cross-references); each finding = quoted anchor text + the exploit story + a suggested surgical
  counter (defers drafting to `surgical-redline`). Tribunal lens framed **explicitly as
  critique-not-prediction** (zero case-law retrieval exists; the skill must say so). ADR-F028
  untrusted-text framing applies.
- **Roster:** `hostile-reader` subagent appended to the Commercial roster (migration reconciling
  0073; model-free / no-tools per ADR-F010; skills ⊆ bound set per ADR-F017) **and** added to
  `profiles/commercial/profile.yaml` so fresh orgs get it (B-7a parity oracle will enforce the
  manifest↔seed match — update both together).
- **Eval gate:** seeded-defect recall — plant ~8 known ambiguities in a fixture MSA/NDA (fixtures
  exist: `securescan_msa.py`, `aegis_mutual_nda.py`), C9-style gateway judge scores found/missed
  (ADR-F015 finding-not-gate).
- **Distinctness fence (review will check this):** must be a stance-distinct persona — simulate the
  OTHER side's incentives — or it duplicates `deal-review`'s under-protection lens and dies in the
  simplification pass.
- **Explicit non-goals:** NO simulated counterparty-authored markup (would poison the ADR-F048
  author→side roster and ADR-F042 auto-write memory — needs a simulation-fence ADR first); no
  multi-round self-play; no outcome prediction. That's ADV-2, a separate gated design.

## OUTCOME-1 — the clause-outcome ledger (salvaged from "federated intelligence")

Persist what the negotiation loop already knows but throws away. Intra-org only; **nothing leaves
the building — by design and forever in this slice.**

- **ADR:** supersedes ADR-F032's option-3 deferral of a persisted negotiation-round entity.
- **Migration:** matter-scoped clause-outcome rows — (issue/clause label anchored to playbook
  positions or a CUAD-derived taxonomy, decision verb from the existing closed taxonomy
  accept|reject|counter|leave_open|escalate, round, timestamps).
- **Write point:** the existing `apply_decisions` reconciliation in
  `api/app/agents/negotiation_service.py` — one write, no new tool.
- **Why:** this is the structured data the Practice Knowledge prize (ADR-F050) will need; it also
  feeds WHY-1. Banking it costs one slice now vs. an unfillable gap later.
- **Verification:** live negotiation-round scenario test asserts the rows.

## WHY-1 — why on approve (the cheap end of the "why-graph")

- Extend `ResumeDecision` (`api/app/schemas/agent_runs.py`) so an **approve** may carry an optional
  short rationale (today `message` is reject-only by documented semantics).
- On resume, mint ONE human-attributed `fact_type='decision'` row in `matter_memory_entries`
  (body = the stated why + the gated tool/ref; provenance = session `user_id` + `run_id` — columns
  exist, **NO migration**) through the existing human-authenticated write path (ADR-F042 pattern).
- Renders in the existing cockpit Memory panel; survives consolidation bi-temporally.
- **Keep the rationale out of audit rows** (audit stays counts/types/IDs).
- **Friction fence:** optional, one field, approve-only — per-write mandatory capture is the
  documented ADR-F042 anti-pattern. Demo: HITL-3 redline confirm → approve with a reason → the
  agent's next run injects "we applied this redline because …".
- The grand why-graph (cross-matter, template estate, promotion to shared know-how) **is Practice
  Knowledge (ADR-F050)** — gated, not this slice. There is no template-estate entity to annotate;
  do not invent one here.

## EXPO-1 — exposure snapshot (bounds-only; "reject the actuary, keep the calculator")

- **Skill** `exposure-snapshot` fills an existing tabular grid (no new tool surface) with cited
  columns: cap basis, cap amount, uncapped carve-outs, contract value if stated, required insurance
  limits.
- A **deterministic Python helper computes** the "maximum contractual exposure" column (the AIC-2
  pattern: model extracts with citations, code does arithmetic). Output is a number, `UNBOUNDED`,
  or `unresolved — contract value unknown`.
- Resolved bound persists as a dated Matter Fact (schema per OBLIG-1's ADR — this slice follows it).
- **Eval gate before user-visible:** hand-label caps in 5–10 `sample-documents/` contracts; score
  extraction + arithmetic in the scenario harness. Cap arithmetic is legally subtle (per-claim vs
  aggregate, super-caps, precedence) — the helper's rules are part of the review surface.
- **Hard fence (permanent):** bounds only. **Never emit a probability or expected value.** No claims
  data, no solvency feeds, no insurance modelling — the data cannot exist in a self-hosted
  single-company deployment and an invented probability is a liability with no citable source.

---

## Queue position & gates

1. **B-7 milestone acceptance** — in progress as a delegated agentic walk; evidence recorded for
   the maintainer's review and formal sign-off.
2. **B-2c eval** — Workstream-B remainder.
3. **Maintainer direction call** — enterprise-deploy (K8S ladder, F073–F080 ratification) vs
   product. **CUSTODIAN starts only if/when the product branch is chosen.**
4. Then: **OBLIG-1 → ADV-1 → OUTCOME-1 → WHY-1 → EXPO-1** (ADV-1 may interleave; the other four
   serialize behind OBLIG-1's `trigger_at` ADR).

Standing constraints on every slice: ADR-F005 full gate; audience is one company's in-house legal
team; agents never write company/practice-tier memory; gateway remains sole egress; no MCP/external
connectors (double-gated); upstream FROZEN.
