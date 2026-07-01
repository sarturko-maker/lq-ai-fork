# Plan — AI Compliance module (EU AI Act deep agent)

**Status: DRAFT for maintainer edit** (CLAUDE.md: explore → written plan → human edits → implement).
Created 2026-07-01 on the AI-Compliance pivot. Companion backlog snapshot: `docs/fork/PLANNED-WORK.md`.

## One-paragraph thesis

A second regulatory-register **module** on the same agentic-modules substrate as Privacy — the AI-native
twin of the ROPA. A Deep Agent maintains a company-wide **register of AI systems**; a **deterministic rules
engine (not the model) issues the verdict of record** — the EU AI Act role, risk tier, applicable
obligations, article references and deadlines — sealed by a signed verdict hash. The agent *proposes* facts,
code *classifies and validates*, the human *owns*. Structurally it clones Privacy (register + code-validated
writes + cockpit domain UI + conversational intake); its domain is AI systems and its verdict axis is
Regulation (EU) 2024/1689 rather than GDPR Articles 6/9/28/30/35.

## Why this is a near-twin of Privacy (and what that buys us)

The Privacy/ROPA module already proves every substrate seam this module needs — so most of the build is
*mirroring*, not inventing. Verified in the codebase:

| Seam | Privacy exemplar | AI Compliance mirror | Cost |
|---|---|---|---|
| Practice area | `practice_areas` row (mig 0053/0055), `PRIVACY_AREA_KEY` (ropa_tools.py:88), composition branch (composition.py:806) | new `ai-compliance` row + `COMPLIANCE_AREA_KEY` + one composition branch | thin |
| Domain tools | `build_ropa_tools` + `ROPA_TOOL_NAMES`, all via `guarded_dispatch` (R4/R5/R6 + 1 audit row) | `build_compliance_tools` + `COMPLIANCE_TOOL_NAMES`, **reuse guard verbatim** | new nouns only |
| Typed domain | `models/ropa.py` + `schemas/ropa.py` (Pydantic `extra=forbid`, enums, reject-and-retry) | `models/compliance.py` + `schemas/compliance.py` | new nouns only |
| Migrations | ROPA graph 0058–0065 (one entity per migration) | new tables from **0084+** (chain off latest on main at build time) | new tables |
| Code-validated writes | `try/ValidationError → _rejection_text` (ADR-F018) | identical loop, compliance invariants | pattern reuse |
| Assessment track | `build_assessment_tools`, `Assessment`+`Risk` (mig 0064, ADR-F027) | FRIA reuses the same tables (widened `type`) | near-clone |
| Domain UI | read-only `/ropa` router + `RopaRegister.svelte` in cockpit split view + `ropachange` row-wash | `/compliance` router + `ComplianceRegister.svelte` + `compliancechange` wash | mirror |
| Memory tiers | TierMemoryMiddleware + matter wiki/facts/roster/conversation recall | **inherited for free** — zero code | free |
| Doc ingest + retrieval | local embedder + `matter_hybrid_search` + `search_documents` | **inherited for free** — upload model cards/DPIAs, search works | free |

**The genuinely NEW part** (the module's IP, ADR-worthy as ~F057): the **deterministic classification engine +
server-side presence gate + signed verdict provenance**. ROPA validates writes field-by-field; here a whole
decision tree *owns the output* and the model **cannot self-certify a tier** — it supplies facts, the engine
decides. That is the honest differentiator over a OneTrust-style questionnaire.

## Governing ADRs (this module RIDES them, never precedes them)

- **ADR-F018** (proposed) — module = typed domain + code-validated writes + domain UI; *"deterministic rules
  engine issues the verdict of record."* The module's core structural rule.
- **ADR-F019** (accepted) — deployment-global relational inventory. The AI-systems register is **company-wide,
  single-tenant**, shared-read, `source_project_id` for provenance only (never scoping), cross-user→404.
- **ADR-F020** (accepted, **build-DEFERRED**) — conversational-link external intake (tokenized, scoped agent,
  full security envelope). The SME-talks-to-the-agent surface. Inherits the "no external exposure until an
  explicit decision" posture — this box is never exposed, so the intake half stays deferred.
- **ADR-F021** (proposed) — authz design-readiness contract. The module must be **born flip-ready**: every
  domain row carries a durable NON-NULL `practice_area_id`; all reads go through the injected policy seam
  (`can()`/`visible_filter()`, read-deny→404); every write flows `guarded_dispatch` carrying
  `user_id + practice_area_id`. The DEPT_SME↔department RBAC maps onto user↔practice-area.
- **NEW ADR-F057** (to draft in slice AIC-0) — *the AI Compliance module*: the AI-systems register, the
  deterministic verdict engine + presence gate + signed verdict hash, and the scope decisions below. Riding
  F018/F019/F020/F021.

**Clean-room hard rule.** Prior art = the maintainer's PRIVATE repo `sarturko-maker/EU_AI_Act` (Next.js/Prisma).
**Reference-only, clean-room** (same posture as Oscar Privacy / scira): take the *design + domain patterns*,
re-author on our stack (FastAPI/SQLAlchemy/SvelteKit); copy **no** code, seed data, brand tokens, prompt copy,
subsidiary list, or docs; **never fetch/crawl it**. The employer's name/branding must appear **nowhere** in the
fork. **Domain caveats to RE-VALIDATE (not lift):** the prior art encodes a **DRAFT** Art 6(3) guideline, does
**NOT** model GPAI Chapter V, and predates the **Digital Omnibus, which was ADOPTED 2026-06-30** (our own
knowledge cutoff also predates it — the deadlines/obligations must be web-researched + counsel-reviewed against
the *adopted* text). The rule content is legally load-bearing and is a counsel-review concern — not an
engineering copy.
(Naming collision to avoid: `docs/compliance/` is an unrelated SOC2/ISO certification pack, NOT this module.)

## The EU AI Act domain model (Reg 2024/1689) — grounded

**Risk pyramid (most-restrictive-wins), a closed enum:** `prohibited` (Art 5) · `high` (Art 6 — Annex I
product-safety route + Annex III use-case route, filtered by the Art 6(3) derogation predicates) ·
`limited`/transparency (Art 50, **stacks** on any tier) · `minimal` (residual). Orthogonal axis: **GPAI models**
(Chapter V) with a **systemic-risk** sub-tier.

**Classification = the deterministic verdict of record.** A waterfall of named boolean predicates over intake
facts: (1) is it an Art 3(1) AI system / GPAI model? (2) any Art 5 practice → **prohibited, terminal**.
(3) Annex I safety component OR Annex III use-case → candidate high-risk; apply the Art 6(3) filter unless it
profiles natural persons. (4) GPAI → Chapter V (+ systemic if >10²⁵ FLOP or designated). (5) Art 50 triggers
attach transparency. (6) else minimal. `classify_system(facts) -> Verdict{tier, route, article_refs[],
predicate_trace, ruleset_version, verdict_hash}`. **Server-side presence gate:** the model supplies facts; the
engine decides — a system cannot be "talked into" a lower tier.

**Org role per system (not per org):** `provider` (Chapter III Sec 2–3) · `deployer` (Art 26 + Art 27 FRIA) ·
`importer` (Art 23) · `distributor` (Art 24) · `authorised_representative` (Art 22). **Role-flip (Art 25):** a
deployer becomes a provider on rebrand / substantial modification / repurposing. Obligations = **tier × role**.
Most enterprise tenants are **deployers** of vendor systems and **providers** of in-house ones — so the
deployer branch (Art 26) is the module's primary path (mirrors ROPA where the operator is usually controller).

**Core entities (the ROPA twins):**
- `ai_systems` ≈ `processing_activities` — name, **intended_purpose** (Art 3(12), the single most
  classification-relevant field — Annex III is a list of use-cases), lifecycle_stage, deployment_status,
  org_role, role_flip triggers, is_gpai/gpai_systemic flags. Deployment-global (F019).
- `risk_classifications` — the verdict row: tier, route, article_refs, `predicate_trace` (JSONB),
  `ruleset_version`, `verdict_hash`, `computed_at`, `computed_from_facts_fingerprint`. **Recompute-on-fact-change.**
- `obligation_items` ≈ ROPA link-tables — one row per applicable article, **deterministically seeded from
  verdict×role** (provider Chapter III / deployer Art 26 / Art 50 stack): {system_id, article_ref, title,
  status ∈ not_started/in_progress/satisfied/na, evidence_file_id, owner, due_date}.
- `ai_providers` ≈ `vendors` + `conformity_assessments` (CE marking, EU declaration of conformity ref, Annex
  VIII EU-database registration id, internal-Annex-VI vs notified-body-Annex-VII route).
- `incidents` (Art 73) — with a **statutory clock** (15 days / ≤2 days critical / ≤10 days death) the engine
  computes from `occurred_at` + severity → a deadline/timeline surface (closer to a GDPR Art 33 72h timer than
  to a static ROPA risk row).
- `regulatory_calendar` — **versioned data table** of Art 113 phased dates (baseline: 2 Feb 2025 prohibited;
  2 Aug 2025 GPAI; 2 Aug 2026 Annex III + Art 50; 2 Aug 2027 Annex I) — **but these must be reconciled against
  the Digital Omnibus adopted 2026-06-30**, which may have moved several high-risk dates. Because the law is
  moving, this is data, not code — a deadline change is a data edit + a new `ruleset_version`.
- **FRIA (Art 27)** — the conversational DPIA-analogue; **reuse the `assessment`+`risk` tables** (ADR-F027)
  with a widened `type ∈ {classification, fria, conformity}` and a ported completion invariant (a FRIA cannot
  complete without documented human-oversight measures + ≥1 mitigated fundamental-rights risk).

## Goals
1. A configured **AI Compliance practice area** whose Deep Agent maintains a company-wide, deployment-global
   **AI-systems register** through **code-validated** tool writes (never free-prose, never model-direct).
2. A **deterministic classification engine** that owns the EU AI Act verdict (role, tier, obligations, article
   refs, deadlines) with a **server-side presence gate** and **signed, re-derivable verdict provenance**.
3. A **cockpit domain UI** (F013 look, our chrome — *what to show* from OneTrust/the reference, never *how it
   looks*) rendering the register, per-system obligations checklist, and a governance dashboard + inventory
   export as the deliverable of record.
4. Built **eval-first** where craft matters (ADR-F041) and **authz-flip-ready by construction** (ADR-F021).

## Non-goals (v1)
- **No external/unauthenticated intake surface.** The conversational-link SME intake (ADR-F020) stays DESIGN
  -of-record + DEFERRED until an explicit exposure decision (this box is never externally exposed). v1 intake
  is a firm user driving the agent internally.
- **No multi-tenant / org_id.** Single-tenant, deployment-global like the ROPA (F019). Subsidiaries are data
  within the one tenant.
- **No copied law text or rule code from the reference repo** — re-authored against current primary sources;
  counsel-reviewed. Draft-guideline predicates carry a "draft basis" disclaimer or gate conservatively.
- No legacy-executor reuse; no gateway-bypass; no new module-level singletons (CLAUDE.md rules hold).

## Milestone AIC — vertical slices (each ≤2–3 days, one PR, end-to-end + tested)

- **AIC-0 — Module ADR + area shell.** Draft **ADR-F057** (module shape, verdict-engine doctrine, presence
  gate, signed provenance, scope decisions recorded). Seed the `ai-compliance` practice area (migration:
  `practice_areas` row + `profile_md` doctrine + skill bindings scaffold), `COMPLIANCE_AREA_KEY` constant, a
  `build_compliance_tools` factory (list-only to start), the composition branch, the `AREA_TOOL_GROUPS` entry.
  **DoD:** a compliance matter is creatable, the agent answers with the inherited memory tiers + document
  search, no domain writes yet. *(Proves the area lights up.)*
- **AIC-1 — AI System register (first entity end-to-end; the PRIV-3 analogue).** `ai_systems` table
  (deployment-global, F019), `models/compliance.py` + `schemas/compliance.py` (`AISystemInput`, role/lifecycle
  enums), code-validated `propose_ai_system` + `list_ai_systems` in `build_compliance_tools`, read-only
  `GET /compliance/ai-systems`, minimal `ComplianceRegister.svelte` in the cockpit split view (isComplianceMatter)
  + `compliancechange` row-wash. **DoD:** the agent proposes an AI system from a conversation, code validates,
  it appears live in the register. *(Thin relational spine + read UI + propose tool, live-verified.)*
- **AIC-2 — The deterministic verdict engine (the module's IP).** `app/aiact/classify.py`:
  prohibited screen (Art 5) → high-risk waterfall (Annex I/III + Art 6(3)) → Art 50 stack → minimal; returns
  `Verdict{tier, route, article_refs, predicate_trace, ruleset_version, verdict_hash}`. A `classify_ai_system`
  tool that takes **facts** and returns the **engine** verdict (presence gate — model cannot mint a tier);
  persist a `risk_classifications` row + recompute-on-fact-change. Scenario eval on known systems.
  **DoD:** given facts, the engine emits a reproducible, hash-sealed verdict; the agent provably cannot
  self-certify. *(ADR-F057 core; the honest differentiator.)*
- **AIC-3 — Org role + obligations checklist (tier × role → ObligationItem).** role enum + role-flip triggers
  on `ai_systems`; `obligation_items` deterministically seeded from verdict×role (provider Chapter III /
  deployer Art 26 / Art 50 stack); status + evidence-link tools; per-system checklist in the register UI.
  **DoD:** classifying a high-risk deployer system auto-seeds the Art 26 obligation set; the agent fills
  status; the human owns.
- **AIC-4 — Providers/vendors + conformity-assessment chain.** `ai_providers` (≈ vendors) + link;
  `conformity_assessments` (CE / DoC / EU-DB registration / Annex VI vs VII route); `propose_ai_provider` /
  `link` / `record_conformity_assessment`; cross-entity rule (importer/distributor → verify CE+DoC).
  **DoD:** a vendor system records its provider + CE status; the engine adds the verify-CE obligation.
- **AIC-5 — FRIA/assessment track (reuse ADR-F027).** Widen the assessment `type` enum; `fria-generation`
  skill (near-clone of `pia-generation`); `link_assessment_to_system`; ported completion invariant.
  **DoD:** the agent runs a conversational FRIA that files into the register; can offer to build one from an
  existing DPIA.
- **AIC-6 — Incidents + deadlines engine.** `incidents` (Art 73 clock) + `regulatory_calendar` (versioned Art
  113 dates); engine computes `report_deadline` + per-obligation `due_date`; per-system timeline surface.
  **DoD:** a serious incident sets the statutory clock; the timeline shows upcoming deadlines.
- **AIC-7 — Skills + eval harness (fix the Privacy skill-binding gap).** `aiact-register-population` (work one
  system to completion), classification/obligations/evidence-quality skills; **bind via a REAL migration**
  (0067/0072/0083 precedent — not test-only, the observed Privacy gap); masked-judge scenario eval on register
  completeness + classification correctness. **DoD:** the agent proactively populates the register on an intake
  conversation; eval green.
- **AIC-8 — Governance dashboard + inventory export (deliverable of record).** `ProgrammeDashboard` analogue
  (per-tier counts, gap view, deadline calendar) + export (AI-system inventory / conformity register,
  JSON/CSV/XLSX) ≈ the Article 30 export. **DoD:** the module renders a OneTrust-comparable AI-governance
  cockpit; export produces the inventory of record.
- **AIC-9 (DEFERRED) — conversational-link SME intake.** The F020 tokenized external surface for system owners
  (token table, Redis limiter, strict CSP, scoped grant floor, per-link cost cap). Design-of-record now; built
  only when an exposure decision is made.
- **GPAI/Chapter V (scope toggle) — AIC-4b if included.** A distinct `ai_models` entity + systemic-risk axis +
  Art 53/55 obligation set. Net-new (no ROPA analogue; prior art didn't model it). **Recommend deferring** to a
  dedicated slice after the deployer path lands; carry `is_gpai`/`gpai_systemic` flags on `ai_systems` from
  AIC-1 so the later entity slots in.

## Verification / DoD (ADR-F005 gate, every slice)
- Deterministic tests in the dev image (repo-root ruff config, line-length 100; mypy; pytest) with counts
  quoted; migrations verified on a **throwaway pgvector container** then applied by rebuilding
  api+arq-worker+ingest-worker together (never host-side `alembic upgrade` on the live DB).
- Live verification when behavior changes (agent proposes → engine classifies → register UI updates), evidence
  in the PR; masked-judge eval where craft/classification correctness matters (ADR-F041).
- Fresh-context adversarial review incl. the mandatory **security + simplification pass** (no leaked secrets,
  authz through the seam not inline, injection, verdict cannot be model-minted, no stray files).
- ADR-F057 drafted in AIC-0 and kept current; HANDOFF + memory updated each slice; agent-merged under the full
  gate (ADR-F005).

## Decisions (maintainer, 2026-07-01) + remaining open items
**DECIDED:**
1. **GPAI/Chapter V — DEFERRED to AIC-4b** (carry `is_gpai`/`gpai_systemic` flags from AIC-1). Non-blocking,
   reversible.
2. **Register tenancy — DEPLOYMENT-GLOBAL** (one company-wide inventory, ADR-F019; `source_project_id`
   provenance only; shared-read; no `org_id`).
3. **Kick-off — START AIC-0 NOW** (the 3 open tabular/embedding PRs merge alongside on the maintainer's nod).
4. **⚠️ Digital Omnibus ADOPTED 2026-06-30** (per maintainer). Our knowledge predates it — the `regulatory_calendar`
   + rule content must be **web-researched + counsel-reviewed against the ADOPTED text** at AIC-2/AIC-6, not the
   baseline/proposal set. AIC-0 hardcodes no law, so this does not block the shell.

**STILL OPEN (recommendations baked in; edit here):**
5. **ADR gating** — draft F057 and proceed on Privacy's shipped proof of F018, or first flip F018/F021 to
   `accepted`? *(Recommend: draft F057, proceed; honor the F021 contract by construction.)*
6. **unit_label noun** for the area — 'Programme' (mirrors Privacy) vs 'Register' vs 'AI Governance'.
   *(Recommend: 'Programme' for consistency with Privacy.)*
7. **Verdict-hash signing** — plain content digest (tamper-evidence) vs cryptographic signature (key lives only
   in the gateway per the sole-key-holder rule). *(Recommend: unsigned digest v1; revisit.)*
8. **Rule provenance / counsel review** — who validates the current rule set (adopted Omnibus, Art 6(3), GPAI
   deadlines); ship the adopted Reg 2024/1689-as-amended dates as a versioned table with a "re-validate" disclaimer.

## Risks / gotchas
- **Legal content is the load-bearing risk, not the code.** The verdict engine's rules must track current
  primary sources; the verdict-hash + `ruleset_version` design makes rule versions auditable precisely because
  the law is still moving — **the Digital Omnibus was adopted 2026-06-30 (after our knowledge cutoff)**, and Art
  6(3) guidance was draft. Web-research + counsel-review the adopted text before any date/verdict is presented
  as authoritative.
- **Presence gate is the honesty guarantee** — if the model can ever assert a tier directly, the module is just
  a chat wrapper. Enforce engine-owns-verdict at the tool boundary, test it adversarially.
- **Don't clone the Privacy skill-binding gap** — bind domain skills in a real migration (AIC-7), not
  test-only.
- **Tier floor** — do not set `default_tier_floor` above the only qualified model (tier 4) or every run fails
  (the Commercial/M3 lesson).
- **Clean-room discipline** — zero code/asset/branding carryover from `EU_AI_Act`; employer identity nowhere.
