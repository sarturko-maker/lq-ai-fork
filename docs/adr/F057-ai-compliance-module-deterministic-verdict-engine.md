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
