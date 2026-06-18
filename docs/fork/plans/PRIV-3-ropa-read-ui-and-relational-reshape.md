# PRIV-3 — ROPA register read UI (lead) + the relational-domain reshape

**Status:** DRAFT for maintainer edit (per CLAUDE.md: explore → written plan → human edits → implement).
**Branch:** `priv-3-ropa-read-ui`. **Milestone:** PRIV (Privacy module, ADR-F018).
**Date:** 2026-06-18. Supersedes the PRIV-3 line in `PRIV-privacy-ropa-module-decomposition.md` (roadmap reshaped below).

---

## 0. Why this plan changed shape

The mandate moved from "render the flat ROPA list" to **"run a OneTrust / TrustArc-comparable privacy
management system inside LQ.AI"** — rendered in our F013 style, with a **real relational DB**, built
**incrementally** (not one shot), **leveraging Oscar's heavy lifting** and **improving** it where thin.

Four reviews fed this (evidence in-session; key findings folded in):

- **OneTrust + TrustArc (the parity bar).** Both are built on a **two-tier inventory**: a **System/Asset**
  record (the IT system where data lives) and a **Processing Activity / Business Process** record (the
  Article 30 record that *composes systems into a data flow*), with **different attributes at each level**
  (TrustArc even makes the element/purpose level configurable: Standard = at system level, Simplified = at
  process level). Around those: **Vendor/Third-Party**, **Legal Entity** (the Article 30 *export scope*),
  and a linked **data taxonomy** (data subjects / categories / elements) — a bidirectional **inventory
  graph** that drives a data-flow map + one-click Article 30 export. Both converge on
  **"agent populates the record, human reviews"** (OneTrust Privacy Agent; TrustArc 80% autofill +
  gap-flagging + discovery) — which IS our ADR-F018 loop, native rather than bolted on.
- **Oscar Privacy (the heavy lifting to lift-and-improve).** Oscar's *structured* layer is deliberately
  THIN (lightweight "Programme" grouping records + a company-level Systems list in config; substance lives
  in markdown skill OUTPUTS). Its real value is the **workflow/knowledge layer**: the **Diana Park
  five-phase methodology** (Data Mapping → Regulatory Assessment → PIA → Consent Architecture →
  Deliverables), the **~13 matter-kind taxonomy** (DSAR access/erasure/rectification/portability, DPIA,
  vendor_dpa, breach_internal/vendor, regulator_inquiry, consent, records_of_processing, training, other),
  and six substantive **skills** with intake questions + templates + decision gates: **dsar-response**,
  **pia-generation** (7-section PIA report template), **dpa-review** (9-term matrix + processor/controller
  positions), **use-case-triage** (PROCEED / PIA-REQUIRED / DPIA-MANDATORY / STOP), **policy-monitor**,
  **reg-gap-analysis**, plus a regulator taxonomy (ICO/CNIL/Garante/BfDI/DPC/EDPB) and sectoral matrix
  (GLBA/HIPAA/FERPA/COPPA/VPPA…). **We go relational where Oscar stayed document-centric; we port-and-improve
  its skills/methodology rather than rebuild them.**
- **Our cockpit + read surfaces (where it plugs in).** New `api/app/api/ropa.py` read router (authz:
  `Project.owner_id == user.id` → **404**, never 403); new web `RopaRegister.svelte` rendered in the matter
  view when `area.key === "privacy"`; reuse `PageShell` + `SectionHeader`; **no table primitive exists** —
  add a small one. Tokens (charcoal `#111`, scarce-blue `--brand`, motion) all in `web/src/app.css`.
  Confirmed: **no ROPA read endpoint or web component exists yet** — greenfield.

---

## 1. The target entity model (the destination — NOT all built in PRIV-3)

The LQ.AI ROPA inventory graph we are building toward (synthesis of OneTrust/TrustArc + Oscar, our names):

| Entity | Role | Today |
|---|---|---|
| **Processing Activity** | Article 30 record (the "business process") | ✅ `processing_activities` (PRIV-1), flat |
| **System / Asset** | IT system where data lives; composed into a PA's data flow | ⛔ not yet |
| **Vendor / Processor** | third party; role (controller/processor/sub-processor); DPA/contract; risk | ⛔ |
| **Legal Entity** | the Article 30 **report scope** (controller vs processor outputs) | ⛔ |
| **Data taxonomy** | data subjects / data categories / data elements — *linked onto* records | ⛔ (today: free-text on the PA) |
| **Transfer** | cross-border flow + **mechanism/safeguard** (SCC/IDTA/adequacy) — invariant: outside UK/EEA ⇒ mechanism required | ⛔ |
| **Assessment** | DPIA/PIA/LIA/TIA — templated, risk-scored, **linked to** PAs, can write back | ⛔ |

**Two unresolved architectural questions (defer to the PRIV-4 ADR, do NOT resolve in PRIV-3):**

1. **Inventory scope — matter vs org.** In OneTrust/TrustArc *and* Oscar, **Systems and the register are
   org/company-level** (one inventory, reused across work), while a specific DPIA/DSAR is matter-level. Our
   `processing_activities` is currently **matter-scoped** (`project_id`). Promoting Systems (and likely the
   register itself) to **org-level** aligns with the 4-level memory model (company level) and the leaders —
   but it's a real change. PRIV-3 stays matter-scoped (no decision forced); the PRIV-4 ADR decides.
2. **Element/purpose level (TrustArc's Standard vs Simplified).** Whether data elements/purposes live on the
   System or on the Processing Activity. Decide when System lands (PRIV-4).

---

## 2. PRIV-3 — the slice (DECISION: two-tier relational spine + read UI)

**Maintainer decision (2026-06-18): establish the two-tier relational spine in PRIV-3.** Add the **System**
entity + a **Processing Activity ↔ System** link as first-class relational tables, draft **ADR-F019**, and
have the read UI render the **real two-tier register** (Systems + Processing Activities), in our F013 style.
The read UI still **leads** as the user-visible deliverable; the minimal schema is built first only because
you can't render a two-tier register without the `systems` table existing. **Accepted: this exceeds the
2–3 day bound** — it may land as two sub-PRs under PRIV-3 (backend spine → read UI) but is one slice on the
roadmap.

### Scope decision (maintainer, 2026-06-18): DEPLOYMENT-GLOBAL company register

**LQ.AI is for in-house teams — the team's one client is its own organization, so the deployment IS the
org.** (This is why the app is single-tenant: `organization_profile` is a singleton, no `organizations`
table, no `org_id`. Oscar Privacy needed multi-client tenancy; LQ.AI does not.) The ROPA register is
therefore **deployment-global**: one company-wide register (Systems + Processing Activities), **not scoped
by matter or user**, shared across the firm. A Privacy matter's agent reads/writes the **one** company
register. **This re-scopes PRIV-1: `processing_activities` drops `project_id`** (it was matter-owned; it is
now part of the global register) and **PRIV-2's write tools drop project-scoping** (they write to the global
register; the area-keyed tool grant + guard chokepoint still gate *who* may write). **Authz:** the register
is intentionally shared across the firm's users (a company record, not a private artifact) — so cross-user
→404 does **not** apply to the register; read endpoints require an active (authenticated firm) user, and
404 still covers a genuinely missing record id. Provenance (which run/matter added an entry) is preserved
via a nullable `source_project_id` reference — for governance/UI filtering — but it does **not** scope or
own the row.

### Concrete schema (PRIV-3, migration 0059)

**`systems` table** — **global** (no ownership FK), mirroring PRIV-1's code-validated pattern (Pydantic
`SystemInput` is the contract; DB CHECKs mirror it):
- `id`
- `source_project_id` (nullable FK → `projects.id`, `ON DELETE SET NULL`) — provenance only, never scoping
- `name` Text (1..200, required)
- `system_type` Text + CHECK enum: `database`, `analytics`, `crm`, `support`, `email_marketing`, `logs`,
  `backup`, `third_party_processor`, `other` (Oscar's systems-walk list ∪ OneTrust asset types)
- `description` Text (≤2000, optional)
- `owner` Text (≤200, optional) — owning team/person
- `hosting_location` Text (≤200, optional) — country/region free-text (the transfer *mechanism* invariant
  arrives with the Transfer entity in PRIV-5, not here)
- `retention` Text (≤1000, optional) — system-level retention (PA retention stays the required one)
- `security_measures` Text (≤2000, optional) — TOMs
- `ai_usage` Boolean (default false) — TrustArc "AI used?" flag
- `created_at`, `updated_at`

**`processing_activity_systems` join table** — M:N (a processing activity composes systems; a system serves
many activities — the OneTrust/TrustArc "Business Process composes Systems" shape): `(processing_activity_id,
system_id)` composite PK, both FK `ON DELETE CASCADE`. *(Element/purpose detail stays on the Processing
Activity — TrustArc "Simplified" style — per ADR-F019.)*

### ADR-F019 (drafted in this slice) — "Relational, deployment-global ROPA inventory graph"
- **Two-tier model:** System ↔ Processing Activity via M:N link (extends ADR-F018's typed-domain +
  code-validated-write pattern to System and the link — the agent proposes a system / a link; code validates
  before commit; reject-and-retry).
- **Scope = deployment-global** (the in-house team's single org IS the deployment; single-tenant by design).
  The register is the company's standing record, shared firm-wide, not matter- or user-scoped. **Supersedes
  the PRIV-1 matter-scoping of `processing_activities`** (drop `project_id` as owner; add nullable
  `source_project_id` for provenance only).
- **Authz:** register is intentionally shared — read requires an active firm user; cross-user→404 applies to
  private matters, **not** to the shared register; 404 still covers a missing record id.
- **Element/purpose level = on the Processing Activity** (TrustArc "Simplified"), not the System.

### Goals
- A user in a **Privacy matter** **SEES the company's two-tier ROPA**: a **Systems** register + a
  **Processing Activities** register (each list + per-record detail), with the **links visible** (a PA's
  detail lists the systems it uses; a system's detail lists the activities using it) — surfaced in the
  cockpit, in **our F013 design language**, **not** Oscar's/OneTrust's look.
- Read API for the **deployment-global** systems + processing activities (+ their links); active-user
  required; 404 only for a missing record id (the register is shared, not per-user).
- The agent can **propose a System** and **link** it to a processing activity — code-validated writes
  (ADR-F018/F019), so the two-tier register is genuinely agent-populated end-to-end.

### Non-goals (this slice)
- No Vendor/Legal-Entity/Transfer/Assessment entities (→ PRIV-5+). No transfer-mechanism invariant yet.
- No create/edit/delete from the **UI** (read-only; the **agent** writes — "system proposes, user owns").
- No Article 30 export (→ PRIV-4a). No data-flow/lineage diagram (→ PRIV-6). No org-level scope move.
- No Oscar skill ports (→ their own slices).

### Files (≈)
**api/ — relational spine (deployment-global)**
- `api/app/models/system.py` (new) — `System` ORM (global; nullable `source_project_id` provenance FK
  `ON DELETE SET NULL`) + CHECK constraints; `api/app/models/ropa.py` gains the M:N relationship via a
  `processing_activity_systems` association table.
- `api/alembic/versions/0059_*.py` (new) — create `systems` + `processing_activity_systems`; **ALTER
  `processing_activities`: drop `project_id` (FK + column), add nullable `source_project_id`** (re-scope per
  ADR-F019). **Verify on a throwaway pgvector container; rebuild api+arq-worker+ingest-worker together**
  (dev-stack hard rule). Dev `processing_activities` is empty (PRIV-1/2 only added the path) — confirm
  before the column drop.
- `api/app/schemas/ropa.py` (extend) — `SystemInput` (write contract, `extra="forbid"`, `system_type` enum),
  `SystemRead`/`SystemList`, `ProcessingActivityRead` (+ linked-systems summary), `ProcessingActivityList`.
- `api/app/agents/ropa_tools.py` (rework + extend) — `propose_processing_activity` drops project scoping
  (writes to the global register; keeps the run/area guard); add `propose_system`, `list_systems`,
  `link_processing_activity_to_system`; all via `guarded_dispatch`; rejection returned to the model (never
  silent write/fix).
- `api/app/api/ropa.py` (new) — read endpoints (global): `GET /ropa/systems` (list), `GET /ropa/systems/{id}`
  (detail + linked PAs), `GET /ropa/processing-activities` (list), `GET /ropa/processing-activities/{id}`
  (detail + linked systems). `ActiveUser` + `get_db`; **404** only on missing id. Read-only.
- `api/app/api/__init__.py` — mount the router under the active-user dependency.
- Tests: `api/tests/test_systems.py` (SystemInput invariants), rework+extend `tests/agents/test_ropa_tools.py`
  (global writes; propose_system / link happy + reject + audit), `api/tests/api/test_ropa_read.py`
  (list/detail/links, active-user required, empty register, unknown id → 404). Update existing PRIV-1/2 tests
  for the dropped `project_id`.

**web/ — the two-tier register read UI (the lead deliverable)**
- `web/src/lib/lq-ai/api/ropa.ts` (new) — `listSystems`, `getSystem`, `listProcessingActivities`,
  `getProcessingActivity` via `apiRequest`.
- `web/src/lib/components/ui/table/` (new, minimal) — small shadcn-svelte Table primitive (reusable).
- `web/src/lib/lq-ai/components/ropa/RopaRegister.svelte` (new) — two-tier shell (Systems | Processing
  Activities), `PageShell` + `SectionHeader`; badges for lawful-basis / controller-role / special-category /
  system_type; honest empty states ("…the Privacy agent adds these as it works.").
- `web/src/lib/lq-ai/components/ropa/ProcessingActivityDetail.svelte` + `SystemDetail.svelte` (new) —
  per-record detail with the cross-links rendered.
- Integration: render `RopaRegister` in the matter view when `area.key === "privacy"` (a "Register" tab
  alongside conversation). Reversible: one render branch.
- `web/src/lib/lq-ai/components/ropa/*.test.ts` — render, empty-state, badge mapping, link rendering.

### Verification (ADR-F005 gate)
- Migration verified on a throwaway pgvector container (never the dev DB); workers rebuilt together.
- api: containerized suite green, counts quoted; new System/tool/read tests incl. the **404 cross-user** case.
- web: `npm run check` + vitest; **headed Cypress** before/after screenshots (light+dark × wide+narrow) of
  both registers + detail, in `docs/fork/evidence/priv-3/`.
- **Live calibration:** scenario harness against a Privacy matter — agent proposes a processing activity +
  a system + a link → all three appear in the two-tier register end-to-end. (Dev model only —
  MiniMax/DeepSeek per the dev-model rule.)
- Fresh-context adversarial + **security + simplification** pass (authz/404, no injection via rendered
  values, no leaked fields, M:N cascade correctness). HANDOFF updated last; compact after.

### ADRs
- Implements ADR-F018 (module = typed domain + code-validated writes + **domain UI** — adds the UI leg).
- **ADR-F019 (new, drafted this slice):** the relational inventory graph + matter-scope + element-level
  decisions (above).

---

## 3. Reshaped PRIV roadmap (incremental; re-planned at each boundary)

- **PRIV-3 (this):** **Two-tier relational spine** (System ↔ Processing Activity) + **read UI** for both
  registers + agent propose/link tools + **ADR-F019**.
- **PRIV-4a:** First **Article 30 export** deliverable (structured export of the matter's register) on the
  run-artifact surface.
- **PRIV-5:** **Vendor/Processor** entity (role, DPA/contract, risk) + links; **Transfer** entity + the
  *outside-UK/EEA ⇒ mechanism-required* invariant (the next code-validated domain invariant).
- **PRIV-6:** **Data-flow / lineage view** (auto-generated from the graph) + **Legal Entity** as the Article
  30 report scope (controller vs processor outputs). Possible **org-level inventory** promotion ADR here.
- **PRIV-7+:** **Assessments** — port-and-improve Oscar's **pia-generation** (7-section template) +
  **use-case-triage** (PROCEED/PIA/DPIA/STOP gates) as code-validated, inventory-linked DPIA/PIA records
  with write-back; then **dsar-response**, **dpa-review**, **policy-monitor**, **reg-gap-analysis** as their
  own slices; regulator + sectoral taxonomies; gap/risk dashboard.

Each is one PR (PRIV-3 possibly two sub-PRs), ≤2–3 days where it can be, full DoD, compact after.

---

## 4. Build order (PRIV-3)

1. **Backend spine** — `System` model + migration 0059 (verify on throwaway container) + `SystemInput`
   schema + invariants tests + ADR-F019 draft.
2. **Agent writes** — `propose_system` / `list_systems` / `link_processing_activity_to_system` in
   `ropa_tools.py` + scripted-model tests.
3. **Read API** — `ropa.py` endpoints + authz/404 tests.
4. **Read UI (the lead)** — Table primitive + `RopaRegister` two-tier shell + detail views + integration +
   vitest.
5. **Live calibration + evidence + HANDOFF + ADR-F005 gate.**

Edit this plan freely before/while I implement — I'm starting at step 1 (backend spine), since the read UI
depends on the `systems` table existing.
