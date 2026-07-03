# F058 — Hosted SaaS charter: three delivery modes, stack-per-tenant hosting first

- Status: accepted (maintainer, 2026-07-02)
- Date: 2026-07-02
- Deciders: maintainer (Arturs)
- Informed by: `docs/fork/plans/SAAS-HOSTING.md` (the reviewed recommendation this ADR ratifies);
  NORTH-STAR.md §Keep-possible #4; ADR-F001 (fork charter, rename obligation); ADR-F019
  (deployment-global registers + its pre-committed multi-org supersession clause); ADR-F021
  (authz design-readiness).

## Context

The fork has only ever run on a private dev box, single-tenant by accepted design (ADR-F019: no
`organizations` table, no `org_id`). The maintainer's direction (2026-07-02): make a hosted
version available where companies register an organisation (tenant), create admin accounts, then
user accounts — "a proper SaaS in effect" — **as the market-awareness channel** (nobody knows
LQ.AI Fork exists; hosting is how they find out), while **retaining the ability to take the code
from GitHub and run it as a single tenant**. NORTH-STAR.md invariant #4 ("deployment unit = one
stack per client; do not 'fix' the architecture toward SaaS multi-tenancy") predates this and
must not be silently contradicted. The codebase audit (SAAS-HOSTING.md §2) found: no tenant
entity, no user-creation endpoint at all, an auth core that is strong but not internet-hardened,
a dormant-but-real release pipeline pointed at upstream's registry, and a runtime that fits a
16 GB node. The product is under active development; the hosted fleet must track `main` closely.

## Considered options

1. **Shared-schema multi-tenancy now (org_id + RLS)** — the classic SaaS build; one deployment
   for all tenants, instant self-serve signup, ≈0 marginal tenant cost. Costs the largest
   structural milestone since the fork began (4–6+ weeks touching every ownership chain, the
   registers, the Store, authz, RLS), taxes every future feature with org-scoping, supersedes
   ADR-F019 and north-star #4 — all before a single paying customer exists.
2. **One hosted stack per tenant behind a thin control plane; self-host retained.** Each
   customer gets a dedicated compose stack (own Postgres/object bucket/gateway/Collabora) on
   EU nodes, provisioned by automation, updated by a SHA-pinned fleet deploy. Near-zero app
   refactor (the single-tenant architecture is *correct by construction* per stack); strongest
   isolation story for legal buyers; preserves north-star #4 in every mode. Costs linear infra
   per tenant (~€10–19/mo) and operator-led (not self-serve) onboarding.
3. **Hosted-only (drop the self-host path).** Simplifies support surface and lets hosted
   conveniences become hard dependencies — but the maintainer explicitly rejected it: GitHub
   self-hosting is part of the product's identity and adoption story.
4. **No hosted offering (status quo).** Zero cost, zero awareness: the market cannot discover a
   product it cannot try. Rejected as failing the purpose of the pivot.

## Decision outcome

**Option 2.** One codebase, **three delivery modes**:

- **Mode 1 — self-host from GitHub** (single tenant, docker-compose): remains supported. Every
  hosted convenience must stay *optional and pluggable* — generic SMTP (no hard Scaleway
  dependency), any S3-compatible store (MinIO stays in the default compose), no hosted-only
  assumption baked into `api/`/`web/`/`gateway/`.
- **Mode 2 — operator-hosted dedicated stacks (BUILD NOW)**: the SAAS milestone
  (MILESTONES.md § SAAS; slices SAAS-0…8A per SAAS-HOSTING.md §9). Hetzner EU nodes; sales-led
  provisioning via a private control-plane repo (`tenants.yaml` + provision/deploy scripts);
  per-tenant BYOK falls out free (each stack's gateway holds its own encrypted keys).
- **Mode 3 — shared-schema multi-tenancy (RECORDED, trigger-gated)**: SAAS-HOSTING.md §3B is the
  standing plan of record. **Trigger:** a real self-serve motion (smaller customers wanting
  sign-up + base subscription + BYOK at near-zero marginal cost), OR >20–30 active tenants, OR
  per-tenant ops measurably eating development time. Building Mode 3 will supersede ADR-F019
  (via its own clause) and north-star #4 through a new ADR at that time — not before.

**A→B shape (pre-decided): coexist, not merge.** When Mode 3 is built, it serves *new*
(self-serve) tenants; existing Mode-2 tenants stay on dedicated stacks unless a tenant
individually asks to move. Rationale: the tenant-merge program (email/practice-area-key/vocab
unique-constraint collisions, Store namespace + S3 re-keying, freeze windows) carries real risk
and buys nothing for white-glove tenants who chose isolation. Revisitable at trigger time; the
day-one mitigations below keep the merge option open cheaply.

**Day-one rules that keep every mode healthy** (binding on all SAAS slices):

1. New S3 objects are keyed `tenants/<stack-or-org-id>/<file_id>` (the prefix `file.py` already
   reserves) — makes any future consolidation a re-mapping, not a rewrite.
2. Fleet version skew ≤ N-1 deploy cycles; **no indefinite per-tenant version pinning**.
   Contract-phase migrations gate on "all tenants ≥ expand version" (tracked in `tenants.yaml`).
3. The security gate (SAAS-HOSTING.md §6), the per-tenant **monthly** LLM spend ceiling at the
   gateway, and the commercial pack (`plans/SAAS-COMMERCIAL-PACK.md`) are blockers before the
   first paying tenant — not aspirations.
4. PRC-affiliated model endpoints (MiniMax, DeepSeek) are fenced from tenant traffic; the hosted
   default menu is EU-resident (recommendation: Bedrock-EU Claude + Mistral; maintainer to
   confirm at SAAS-6).
5. The platform-admin vs org-admin split is a security requirement (a customer admin must never
   reach gateway provider-key endpoints), built in the common trunk (SAAS-4).

## Consequences

- **North star intact, amended honestly:** NORTH-STAR.md gains a dated addendum (2026-07-02)
  recording the three delivery modes; invariant #4's deployment unit survives in all of them.
  Forward deployment (bespoke per-client implementations) remains a live business shape; Mode 2
  is operationally its self-serve cousin (we forward-deploy onto our own nodes).
- **Product name DECIDED (maintainer, 2026-07-02 at acceptance): "LQ.AI Oscar Edition".**
  ADR-F001's rename obligation is satisfied without dropping the "LQ.AI" mark: the upstream name
  belongs to a group the maintainer is a member of, so retaining it does not appropriate a
  third party's identity — the "Oscar Edition" suffix still distinguishes the fork from
  upstream's own releases. This unblocks SAAS-3's public DNS.
- **Open decisions carried** (SAAS-HOSTING.md §10): PyMuPDF (Artifex licence vs pypdfium2 swap),
  Collabora posture, EU model menu, pricing/selling entity. Each closes in its named slice.
- **Obligations before the first paying tenant** (tracked in `plans/SAAS-COMMERCIAL-PACK.md`):
  MSA/ToS with liability cap + AI-work-product framing, SLA, AUP, DPA + subprocessor list,
  IR/breach runbook, operator-access policy, E&O/cyber-insurance decision, billing v1 (manual
  invoicing, reverse-charge VAT), and the product's own EU AI Act self-assessment
  (`plans/SAAS-AIACT-SELF-ASSESSMENT.md` — dogfooded through `app/aiact/classify`).
- **What this ADR does NOT do:** it does not build Mode 3, does not supersede ADR-F019 or any
  accepted ADR, and does not alter agent architecture (gateway-only egress, `guarded_dispatch`,
  audit contract all unchanged). The SAAS trunk is infrastructure + lifecycle around the
  existing core.
- **Working model for the milestone** (maintainer, 2026-07-02): the lead model drafts small
  slices and orchestrates; implementation is delegated to smaller models (Sonnet-class; Opus-
  class for complex changes); the lead runs verification/tests/review. Compaction expected per
  slice — HANDOFF.md carries the goal and next slice.

## Addendum (2026-07-02): Rebrand execution — the SAAS-rebrand slice

The name decision above ("LQ.AI Oscar Edition") was executed in the `fork/saas-rebrand-oscar-edition`
slice (task #455). No new ADR: this addendum records *how* the accepted decision was applied and,
more importantly, the boundary the rename must never cross.

- **Surgical, display-strings-only.** The rebrand touches only user-facing PRODUCT-NAME surfaces,
  never identifiers. A four-lens branding audit (recorded in the PR) produced a CHANGE list of 12
  surfaces — the SvelteKit shell `<title>`, the app-wide `CockpitHeader` wordmark, the
  `DualBrandingFooter`, eight per-page `<title>` suffixes, and the README front door — plus a
  fork-identity note under the README H1.
- **The "LQ.AI" mark is retained** (the new name contains it), so a bare `LQ.AI` is not
  automatically wrong. Running-prose mentions, action phrases ("Sign in to LQ.AI"), and `/learn`
  developer-education headings keep the short mark; only naming *surfaces* take the full name.
- **KEEP boundary (a global find/replace would break the app).** These are NOT renamed: the
  `lq-ai/` code namespace + `$lib/lq-ai` imports; `--lq-*`/`.lq-*` CSS tokens; the
  `LQ_AI_*`/`PUBLIC_LQ_AI_*` env-var namespace (pydantic binds by field name); `lq-ai-*`
  package/image/`data-testid` identifiers (~1,300 testids are asserted 1:1 in Cypress);
  cross-service wire-contract headers (`X-LQ-AI-Gateway-Key`, `X-LQ-AI-Routed-*`); infra literals
  (`lq_ai` role/db, `lq-ai-files` bucket); and — extend-never-edit — all upstream/provenance
  references (`LegalQuants/lq-ai`, open-webui, NOTICES.md, LICENSE). `LegalQuants` is the
  provider/org name, not the product, and stays. NOTICES.md is therefore untouched by the rename
  (its entries are provenance; the slice adds no new NOTICES entry).
- **Deferred (documented follow-up):** the Microsoft Word add-in default display name
  (`word_addin.py DEFAULT_DISPLAY_NAME`) + tokenising two hardcoded manifest strings across both
  manifest copies. The add-in is non-live scaffold and admin-overridable; the manifest change is a
  correctness fix that warrants its own M365-validation pass, separate from a display-string rename.
- **DevForkCallout repo URL** (currently upstream `LegalQuants/lq-ai`) is left as-is pending a
  maintainer call: its linked PRD §10 / ADR-0009 are upstream documents, so repointing it to the
  fork would break those specific links.
