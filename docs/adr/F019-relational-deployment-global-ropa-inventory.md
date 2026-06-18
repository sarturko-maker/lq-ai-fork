# F019 — Relational, deployment-global ROPA inventory graph

- Status: accepted
- Date: 2026-06-18
- Supersedes: the matter-scoping of `processing_activities` introduced in PRIV-1 (ADR-F018 / migration 0058)
- Extends: ADR-F018 (agentic modules = typed domain + code-validated agent writes + domain UI)
- Milestone: PRIV-3 (Privacy / ROPA module)

## Context

PRIV-1/2 shipped the Privacy module's first typed domain as a single, **matter-scoped** entity:
`processing_activities.project_id` ties each Article 30 record to one Privacy matter, and the PRIV-2 write
tools scope every write/read by that `project_id`. The module's mandate has since been raised: LQ.AI's
Privacy module is to be a **OneTrust / TrustArc-comparable** privacy-management system, rendered in our F013
style.

Both market leaders — and the maintainer's own Oscar Privacy reference — are built on a **two-tier inventory
graph**: a **System/Asset** record (the IT system where personal data lives) and a **Processing Activity /
Business Process** record (the Article 30 record that *composes* systems into a data flow), with
vendors/transfers/assessments hung off the same graph. Crucially, in all three the inventory is **org/
company-level** — one standing register reused across all privacy work — not a per-matter artifact.

Two questions had to be answered before extending the schema:

1. **Shape:** stay single-entity, or make the inventory genuinely relational (System ↔ Processing Activity
   as linked tables)?
2. **Scope:** matter-scoped (today), or org/company-scoped (the leaders)?

A constraint shaped (2): **LQ.AI is single-tenant by design.** It targets **in-house teams**, whose single
"client" is their own organization — so the deployment *is* the organization. There is a singleton
`organization_profile`, **no `organizations` table, and no `org_id` on users or projects**. (Oscar Privacy
needed multi-client tenancy because it served many client companies; LQ.AI does not.)

## Considered Options

1. **Keep matter-scoped, single-entity.** Smallest, no rework. But it diverges permanently from the leaders'
   company-wide register and can't represent the System↔Activity graph — fails the parity mandate.
2. **Relational, but matter-scoped.** Add System + link, keep `project_id` on both. Each matter gets its own
   private register — wrong real-world model (a company has one ROPA, not one per matter) and forces awkward
   cross-matter reconciliation later.
3. **Relational + introduce real multi-tenancy** (an `organizations` table + `org_id` everywhere). True
   multi-org SaaS, but a large cross-cutting platform change touching auth on every endpoint — out of scope
   for a Privacy slice, and unjustified for a single-tenant in-house product.
4. **Relational + deployment-global** (chosen). Make the register a genuine two-tier graph (System ↔
   Processing Activity, M:N) and scope it to the **deployment** (= the one in-house org), with no ownership
   FK. Delivers the company-wide register and the graph; needs no tenancy machinery.

## Decision Outcome

**Chosen: option 4 — relational, deployment-global.**

- **Relational two-tier graph.** Add a first-class `systems` table and a `processing_activity_systems` M:N
  association (a processing activity composes systems; a system serves many activities — the
  OneTrust/TrustArc "Business Process composes Systems" shape). Data-element/purpose detail stays on the
  Processing Activity (TrustArc "Simplified" placement); revisit if a system-level placement is needed.
- **Deployment-global scope.** The register is the company's standing record, shared firm-wide. **Drop
  `processing_activities.project_id` as an ownership key** and add a **nullable `source_project_id`**
  (`ON DELETE SET NULL`) for *provenance only* (which matter/run first recorded an entry) — never scoping.
  `systems` carries the same nullable `source_project_id`.
- **Code-validated writes (ADR-F018) extend to the new surface.** The agent proposes a System / a
  Processing-Activity↔System link; deterministic code (Pydantic `SystemInput`, membership checks) validates
  before commit; a failure is returned to the model to fix and re-propose — never a silent write/fix.
- **Authz.** The register is intentionally shared across the firm's users (a company record, not a private
  per-user/per-matter artifact). Read endpoints require an **active (authenticated) firm user**; the
  cross-user→404 rule continues to protect *private matters* but does **not** apply to the shared register.
  404 still covers a genuinely missing record id. The agent write path is still gated by the area-keyed tool
  grant (only Privacy matters receive ROPA tools) and the `guarded_dispatch` chokepoint (R5/R6 + audit).

## Consequences

- **Re-scopes a shipped slice.** PRIV-1's `processing_activities.project_id` is dropped (migration 0059) and
  PRIV-2's write tools/tests are reworked to the global register. Safe now: no environment holds
  `processing_activities` data yet (0058 unshipped to any DB with data).
- Single-tenant assumption is now load-bearing for the register. If LQ.AI ever needs multi-org tenancy, that
  is a separate platform milestone that would supersede the "deployment-global" scope here (an `org_id`
  retro-fit), not a local change.
- The shared-register authz posture is a deliberate, documented divergence from the per-user ownership model
  used elsewhere — called out so it is not read as an accidental authz hole in review.
- Establishes the graph the rest of the module hangs off: Vendors/Processors + Transfers (PRIV-5), data-flow
  view + Legal-Entity report scope (PRIV-6), assessments (PRIV-7+).
