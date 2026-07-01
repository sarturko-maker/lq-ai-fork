# ADR-F057 — AI Compliance module: a deterministic EU-AI-Act verdict engine the model cannot override

- Status: proposed
- Date: 2026-07-01
- Deciders: Arturs (maintainer)
- Supersedes / relates: **extends ADR-F018** (agentic modules = typed domain + code-validated writes) with a
  sharper invariant for legal *determinations*; rides **ADR-F019** (deployment-global relational inventory),
  **ADR-F020** (conversational-link intake — build-deferred), **ADR-F021** (authz design-readiness contract);
  **reuses ADR-F027** (assessment/risk + completion invariant) for the FRIA track; skills follow **ADR-F041**
  (craft-via-eval); merged under **ADR-F005**. Plan: `docs/fork/plans/AI-COMPLIANCE-module.md`. Reference
  project: the maintainer's private `sarturko-maker/EU_AI_Act` — reference-only, clean-room.

## Context

The Privacy/ROPA module (ADR-F018) proved the agentic-module shape end-to-end: a typed domain the agent
persists through code-validated tool writes, rendered as a cockpit domain UI. The next module is **AI
Compliance** — a company-wide register of an enterprise's **AI systems**, classified under **Regulation (EU)
2024/1689 (the EU AI Act), as amended by the Digital Omnibus adopted 2026-06-30**. It is the AI-native twin of
the ROPA: AI-system register ≈ processing-activity register; conversational-link intake ≈ ADR-F020;
DEPT_SME↔department RBAC ≈ ADR-F021.

Structurally this is mostly *mirroring* Privacy (new practice area, `build_compliance_tools` +
`guarded_dispatch`, `models/`+`schemas/` with reject-and-retry, a `/compliance` read API + register UI, FRIA
reusing the F027 assessment tables; memory tiers + document retrieval inherited free). That part needs no new
decision — F018 covers it.

The **new** decision is narrower and load-bearing: **how the AI Act risk classification (role, tier,
obligations, article refs, deadlines) is produced.** A risk tier is a *legal determination*, not a data field.
F018's "code validates the model's write" is necessary but not sufficient here — if the model *proposes the
tier* and code merely checks it, the model still anchors a legal conclusion, the conclusion is not
reproducible, and an intake conversation could talk a system into a lower tier. That is the exact failure mode
of a OneTrust-style questionnaire with a chatbot bolted on, and it is unacceptable for a compliance product of
record. The classification must be **owned by deterministic code**, reproducible, and auditable — especially
because the underlying law is still moving (the Omnibus was adopted yesterday; Commission Art 6(3) guidance was
still draft at our knowledge cutoff).

## Considered Options

1. **Model classifies (LLM decides the tier).** The agent reads the intake + docs and states the risk tier.
   Cheapest; but the legal determination is non-reproducible, model-quality-dependent, un-auditable, and
   *steerable* — a system can be argued down a tier. Rejected: this is a chat wrapper, not a compliance engine.
2. **Model proposes the tier; code validates the proposal against rules.** The F018 pattern applied verbatim:
   the model asserts `tier=high`, code checks it is consistent. Better, but the model still anchors the answer,
   two runs can disagree, and "validate a guess" is not the same as "compute the verdict." The presence of the
   model's assertion in the record undermines the auditability.
3. **Deterministic engine owns the verdict; the model supplies only facts (chosen).** The agent proposes
   *structured facts* (intended purpose, Annex-III match booleans, org role, Art-5 triggers, …) through
   guarded, code-validated tools; a deterministic engine `classify_system(facts)` computes the verdict (tier,
   route, article refs, applicable-obligation set, deadlines) and returns `predicate_trace` + `ruleset_version`
   + a `verdict_hash`. A **server-side presence gate** means the model **cannot mint or assert a tier** — there
   is no tool that writes a tier directly; the only path to a classification is through the engine over facts.
   The verdict is a durable, re-derivable artifact: any edit to a classification-relevant fact invalidates the
   hash and re-runs the engine. The model's role (proposed facts + confidence) is logged separately from the
   engine's role (the verdict).

## Decision Outcome

**Chosen: option 3.** The AI Compliance module is an agentic module (F018) whose **legal classification is
owned by a deterministic in-process engine** (`app/aiact/classify.py`), gated so the model provides facts and
never the verdict, with signed, re-derivable verdict provenance. Scope calls for v1 (maintainer-decided
2026-07-01):

- **Deployment-global register** (ADR-F019): one company-wide inventory of the org's own AI systems;
  `source_project_id` provenance only; shared-read; cross-user→404. No `org_id`/multi-tenant.
- **GPAI / Chapter V deferred** to a later slice (AIC-4b): ship the risk-pyramid + provider/deployer
  obligations first; carry `is_gpai`/`gpai_systemic` **flags** on `ai_systems` from AIC-1 so the distinct
  `ai_models` entity + systemic-risk axis slot in later without rework.
- **External conversational-link intake deferred** (ADR-F020 posture): this deployment is never exposed to
  external traffic, so v1 intake is a firm user driving the agent internally; the tokenized SME-link surface is
  design-of-record, built only on an explicit exposure decision (AIC-9).
- **Law content is versioned data, not code.** The `regulatory_calendar` (Art 113 phased dates) and the rule
  set are data tables carrying a `ruleset_version`, grounded on the **adopted Digital Omnibus (2026-06-30)** and
  current primary sources, **counsel-reviewed**. Draft-basis predicates (e.g. Art 6(3) derogations) either
  carry a "draft basis" disclaimer on the verdict or gate high-risk conservatively until final guidance. A
  deadline shift is a data edit + a new `ruleset_version`, never a code change.
- **Verdict hash is an unsigned content digest** in v1 (tamper-evidence + re-derivability); cryptographic
  signing (key in the gateway per the sole-key-holder rule) is a later option, not v1.
- **Authz-ready by construction** (ADR-F021): every register row carries a durable NON-NULL `practice_area_id`;
  reads go through the injected policy seam (`can()`/`visible_filter()`, read-deny→404); writes flow
  `guarded_dispatch` carrying `user_id` + `practice_area_id`. No hand-rolled authz.

The engine extends, never bypasses, the chokepoint: it is a deterministic gate over `guarded_dispatch`
(R4/R5/R6 + one audit row of counts/types/IDs); all model calls route through the gateway (ADR-F010); the loop
stays deepagents/langgraph (ADR-F001). Built thin-vertical-first (one entity end-to-end, AIC-1) and eval-gated
where classification correctness matters (ADR-F041).

## Consequences

- **Good:** the legal determination is **reproducible and auditable independent of model quality** (the same
  reason a tier-4-weak model is tolerable for the ROPA) — and cannot be steered by an intake conversation; the
  signed `verdict_hash` + `ruleset_version` make a fact-edit visibly invalidate a prior verdict, which matters
  precisely because the law is moving; the "engine owns the verdict, model supplies facts" pattern generalizes
  to any future rules-based compliance module (ISO 42001, DORA, sectoral regimes); honest by construction (no
  faked classification, rejected facts are visible).
- **Cost:** the rule set is **legally load-bearing** and must be authored, counsel-reviewed, and
  version-tracked against a *moving* law (the just-adopted Omnibus must be researched and encoded — our
  knowledge predates it); the deterministic engine + presence gate + provenance is **real new code beyond the
  ROPA mirror** (the module's genuine IP); the deferred GPAI + external-intake halves mean v1 is deliberately
  incomplete against full OneTrust parity.
- **Follow-ups:** GPAI/Chapter V slice (AIC-4b); external conversational-link intake on an exposure decision
  (AIC-9, full F020 security envelope); web-research + counsel review of the adopted Digital Omnibus as AIC-2
  input; if verdict signing is later required, route the digest through the gateway; the "LQ.AI Oscar Edition"
  rebrand keeps its own ADR.

## Implementation notes — AIC-1 (2026-07-01): the `ai_systems` register

The first entity landed (the PRIV-3 analogue; plan `docs/fork/plans/AIC-1-ai-systems-register.md`). Concrete
calls made under this ADR, recorded here so the reasoning survives:

- **Presence gate is structural, not just prompted.** `ai_systems` has NO risk-tier/role column and there is
  NO tool that writes one. The write schema `AiSystemInput` is `extra="forbid"`, so a `risk_tier` the model
  tries to smuggle in is a hard validation error (tested). The register stores only facts —
  `intended_purpose`, `lifecycle_status`, `development_origin` (build-vs-buy raw fact that *informs* the role),
  and the GPAI carry-flags. The tier/role verdict is AIC-2's separate artifact.
- **Born flip-ready, but the policy seam is deferred.** Every row carries a durable **NON-NULL
  `practice_area_id`** (FK `RESTRICT`) — the one deliberate divergence from the ROPA exemplar (which predates
  ADR-F021 and has no such column). But AIC-1 does **not** build the `visible_filter()`/`can()` seam: the
  `/compliance` router ships **shared-read, behaviour-identical to `/ropa`** (ADR-F019). The column's only job
  today is to make the future flip to area-membership enforcement a pure read-path change **with no
  migration**. This honours the "authz-ready by construction" commitment without over-building the seam in the
  first entity slice.
- **`self_declared_role` and the authoritative role deferred to AIC-3.** AIC-1 stores only `development_origin`
  so the presence gate stays unambiguous (no role-ish column that reads like a verdict); the authoritative
  role + Art 25 flip triggers are AIC-3.
- **GPAI stays pure carry-flags.** `is_gpai` / `gpai_systemic` with a coherence invariant
  (`gpai_systemic ⇒ is_gpai`) enforced in both the Pydantic model and a DB CHECK; zero obligation logic wired
  (that is AIC-4b).
- **Area key.** `COMPLIANCE_AREA_KEY = "ai-compliance"` — must byte-match the AIC-0 seed
  (`practice_areas.key`, migration 0084) or the composition branch never fires.
- **Live-wash included** (not deferred): a run-scoped `AiSystemChangeLedger` + a transient
  `data-compliance-change` SSE frame drive the cockpit's changed-row highlight; `runner.py` and
  `live_changes.py` stay area-agnostic (the LiveChange/ChangeLedger Protocols already generalise).

## Implementation notes — AIC-2 (2026-07-01): the deterministic verdict engine

The module's genuine IP landed (plan `docs/fork/plans/AIC-2-verdict-engine.md`). Concrete calls made under
this ADR:

- **The engine is a pure total function.** `app/aiact/classify.py:classify(facts)` has no LLM call, no I/O,
  no key, no clock, no randomness — a deterministic function of `(facts, RULESET_VERSION)`. This is *why* the
  legal determination is reproducible and auditable independent of model quality, and why the seal
  (`verdict_hash`) is stable. Legal content is isolated in `app/aiact/ruleset.py` as versioned data
  (`RULESET_VERSION` + a "not legal advice" `DISCLAIMER` + article-ref maps) so a legal update is a data +
  version bump, never an engine rewrite (the "law is versioned data, not code" commitment).
- **The presence gate is enforced at the facts schema, structurally.** The only path to a tier is
  `classify_ai_system(ai_system_id, <facts>)`; its `ClassificationFactsInput` is `extra="forbid"` with **no
  tier/route/risk field**, so a smuggled verdict is a hard validation error (tested by parametrised
  `tier`/`risk_tier`/`route`/`verdict` rejections and a signature test asserting the tool has no such
  parameter). The model authors facts; the engine authors the tier — provably.
- **Route ⇔ tier is 1:1; a derogation is a modifier, not a route.** The five `ClassificationRoute` values each
  map to exactly one terminal tier. An Art 6(3) derogation does not get its own route: it is recorded in
  `predicate_trace` + the Art 6(3) `article_refs` + the `draft_basis` flag, and the residual (limited/minimal)
  tier keeps its own terminal route. This is a deliberate refinement of the plan's six-route sketch — it keeps
  every route an honest explanation of its tier.
- **Conservative derogation posture (maintainer-decided).** A claimed Art 6(3) ground is honoured but the
  verdict is flagged `draft_basis=true` (Art 6(3) is the least-settled predicate); profiling of natural
  persons **never** derogates (Art 6(3) final subparagraph), tested explicitly.
- **Facts snapshot on the verdict, not the register (maintainer-decided).** The richer classification facts
  live as a JSONB snapshot on the `risk_classifications` row, keeping `ai_systems` thin and the presence gate
  crisp (the register can never hold a tier). `verdict_hash` = unsigned SHA-256 over normalised facts +
  `RULESET_VERSION` + tier + route + sorted refs (ADR-F057 unsigned-digest-v1).
- **Recompute-on-fact-change via supersede.** A verdict is never mutated in place. Re-classifying with an
  identical `verdict_hash` is an idempotent no-op; a changed verdict sets the prior row's `superseded_at` and
  inserts a fresh one. A **partial unique index** (`WHERE superseded_at IS NULL`) enforces at most one current
  verdict per system; superseded rows are the audit history.
- **Legal grounding + counsel-review gate.** The rule set was web-researched (2026-07-01) against the adopted
  Digital Omnibus (Council green light 29 June 2026): the classification *test* is unchanged from Reg
  2024/1689; the Omnibus deferred *dates* (AIC-6's calendar, not this engine) and added one Art 5 prohibition
  (NCII/CSAM), which the engine encodes. Every verdict carries `RULESET_VERSION` + the disclaimer; a verdict is
  authoritative only after counsel validates the rule set (open item #8 — still open).
- **Dates are out of scope here.** AIC-2 cites *articles*, not deadlines; the phased Art 113/Omnibus dates
  (Annex III 2 Dec 2027, Annex I 2 Aug 2028, Art 50 marking 2 Dec 2026, FRIA 2 Dec 2027) belong to AIC-6.
- **Role stays out of the engine.** Provider/deployer does not change the tier (it changes *obligations*,
  AIC-3), so it is deliberately absent from the engine's inputs.
- **UI depth = tier badge only** (maintainer-decided): the register gains a coloured risk badge
  (prohibited/high/limited/minimal/unclassified + a `draft` marker), washed live via the existing
  `data-compliance-change` path (verb `classify`). The full `GET …/classification` verdict (route + refs +
  trace) is served for a future detail drawer (deferred).
