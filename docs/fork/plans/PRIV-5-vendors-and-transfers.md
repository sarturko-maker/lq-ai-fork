# PRIV-5 — Vendors (recipients) + Transfers (+ the outside-UK/EEA ⇒ mechanism invariant)

**Status:** DRAFT for maintainer edit. **Date:** 2026-06-18. **Milestone:** LQ.AI Oscar Edition / Agentic
Modules (Privacy/ROPA). **Branch:** off `main` (PRIV-4a merged, `ec3bc2d`). Governing: ADR-F018 (agentic
modules = typed domain + code-validated agent writes + domain UI), **ADR-F019** (relational, deployment-global
ROPA graph — which already names this slice: *"Establishes the graph the rest of the module hangs off:
Vendors/Processors + Transfers (PRIV-5)"*). Feeds `PRIV-onetrust-to-lqai-functionality-map.md` § B. Memory:
[[oscar-privacy-modules-vision]].

## Goal

PRIV-3 built the relational two-tier register (System ↔ ProcessingActivity); PRIV-4a made it extractable but
HONEST about four Article 30(1) fields the domain does not yet capture. PRIV-5 fills **two of those four** by
extending the ADR-F019 graph:

1. **Vendors / third parties** — *categories of recipients* (Art 30(1)(e), first clause). A `vendor` entity
   (name, role, DPA status, country) linked M:N to the processing activities that disclose data to it.
2. **Transfers** — *third-country transfers + safeguards* (Art 30(1)(e), second clause). A `transfer` entity
   hung off a processing activity, carrying the destination + the Article 46/45/49 mechanism, with the
   **headline validated invariant: a restricted transfer (outside UK/EEA) ⇒ a transfer mechanism is
   required** — mirrored as a DB CHECK exactly like PRIV-1's `special_category ⇔ art9_condition`.

Each lands as the same end-to-end vertical PRIV-3 established: Pydantic write contract + read DTOs → ORM +
CHECK mirror → migration → guarded code-validated agent tools → shared-read API → web client + register UI →
**extend the Article 30 export to render recipients + transfers and shrink the coverage note's two
corresponding lines** → tests (incl. the global route/OpenAPI contracts). Agent proposes → code validates →
human owns (ADR-F018), all unchanged.

## The decomposition decision (split vs combined) — see § Decisions

Doing **both** entities is a full PRIV-3-sized vertical **twice over** (schema + model + migration + tools +
read API + web UI + export + tests, per entity). The maintainer's working rhythm is *short slice → compact →
short slice*, and ≤2–3 days / one PR per slice (CLAUDE.md). **Recommendation: split** into:

- **PRIV-5a — Vendors (recipients).** The `vendor` entity + `processing_activity_vendors` M:N; agent tools;
  read API + a Vendors tab in the register; export gains a **Recipients** column + a Vendors sheet; coverage
  note drops the *"Categories of recipients"* line. Independently valuable and shippable.
- **PRIV-5b — Transfers (+ the invariant).** The `transfer` entity (child of a processing activity, optional
  recipient = a PRIV-5a vendor) + the **restricted ⇒ mechanism** invariant (schema `model_validator` +
  DB CHECK); agent tools; read surface (transfers in the activity detail); export gains a **Transfers** column/
  sheet; coverage note drops the *"Third-country transfers and the safeguards applied"* line. Depends on 5a
  (a transfer's recipient is a vendor).

The two remaining coverage lines (*categories of data subjects*, *categories of personal data*) stay → PRIV-6
(personal-data taxonomy). After 5a+5b the export's coverage note shrinks from four lines to two — honestly.

This plan specifies the **full domain design once**; the file lists below are organised per the split so either
packaging (split or combined) can be lifted from it.

## Non-goals (this slice family)

- **No risk scoring / risk register.** A vendor "risk rating" and assessment-driven risk records belong to the
  **assessment track (PRIV-A1)**; see § Decisions (vendor kept lean). The map places risk under Assessment
  Automation, not inventory.
- **No personal-data taxonomy** (data subjects / data categories / data elements) — PRIV-6; these stay named in
  the coverage note after PRIV-5.
- **No DPA *review*** (term-by-term Art 28 redline) — that's the P2 DPA/Vendor-review track (Oscar `dpa-review`
  playbook + the redline render layer). PRIV-5 records a vendor's DPA *status*, it does not review the DPA.
- **No country-adequacy engine.** Whether a destination is "restricted" is **declared**, not derived from a
  maintained UK-adequacy/EEA list (see § Decisions). A future enhancement may add a helper list.
- **No edit/CRUD UI** (the register stays agent-written, user-read — PRIV-6+); no scheduled recertification.

## Domain design (specified once; same under either packaging)

### Vendor (recipient) — PRIV-5a

A recipient/third party to whom an activity discloses personal data (Art 30(1)(e), first clause). New
`app.schemas.ropa.VendorInput` (write contract) + `VendorRead`/`VendorSummary` (read DTOs); ORM `Vendor` with
the CHECK mirror; M:N `processing_activity_vendors`.

| Field | Type | Notes |
|---|---|---|
| `name` | str, required (1–200) | the vendor / third party |
| `vendor_role` | enum, required | `processor` · `sub_processor` · `joint_controller` · `separate_controller` · `recipient` — the GDPR recipient/relationship category |
| `description` | str?, ≤2000 | what they do for us |
| `country` | str?, ≤200 | where the vendor is established (informs, but does not derive, a transfer) |
| `dpa_status` | enum, required | `in_place` · `pending` · `not_required` · `none` — Art 28 contract status |

- **Link:** `processing_activity_vendors` M:N (an activity discloses to several recipients; a vendor receives
  from several activities) — mirrors `processing_activity_systems` exactly (composite PK, CASCADE both sides,
  index on `vendor_id`).
- **Provenance:** nullable `source_project_id` (`ON DELETE SET NULL`), like System/ProcessingActivity.
- **CHECK mirror:** name length; `vendor_role IN (...)`; `dpa_status IN (...)`; optional-length on description/
  country (the established `_in_set` / `_opt_len` helpers).
- **Agent tools (guarded, code-validated):** `propose_vendor`, `link_vendor_to_activity`, `list_vendors`
  (granted only to a Privacy matter, like the existing five; `source_project_id` closure-injected).
- **Read API:** `GET /ropa/vendors`, `GET /ropa/vendors/{vendor_id}` (shared-read `_active`, ADR-F019);
  vendors appear as a `recipients`/`vendors` summary list on `ProcessingActivityRead`.

### Transfer (third-country transfer + safeguard) — PRIV-5b

A transfer of an activity's personal data to a third country (Art 30(1)(e), second clause). New `TransferInput`
+ `TransferRead`/`TransferSummary`; ORM `Transfer` + the invariant CHECK.

| Field | Type | Notes |
|---|---|---|
| `processing_activity_id` | FK → processing_activities, **required**, CASCADE | a transfer is always *of some activity's data* (Art 30 lists transfers within each activity record) |
| `vendor_id` | FK → vendors, nullable, SET NULL | the recipient of the transfer, when it is a known vendor (intra-group transfers may have none) |
| `destination` | str, required (1–200) | the third country / international organisation |
| `restricted` | bool, default false | is this a **restricted transfer** (recipient outside the UK/EEA)? — declared (see § Decisions) |
| `mechanism` | enum?, nullable | `adequacy_regulations` · `standard_contractual_clauses` · `uk_idta` · `binding_corporate_rules` · `derogation` (Art 49) — the Chapter V basis |
| `details` | str?, ≤2000 | free-text safeguard detail (e.g. "EU SCCs module 2 + UK Addendum, TRA dated …") |

- **The invariant (headline):** `restricted ⇒ mechanism IS NOT NULL`; `NOT restricted ⇒ mechanism IS NULL`
  (a mechanism on a non-restricted, intra-UK/EEA transfer is incoherent — exactly parallel to
  `special_category ⇔ art9_condition`). Enforced **twice**: a Pydantic `model_validator(mode="after")` (the
  authoritative contract the agent write path validates → reject-and-retry) **and** a DB `CheckConstraint`
  (defense-in-depth, the PRIV-1 precedent). The rejection text names the field + rule so the model fixes and
  re-proposes — never a silent write/fix (ADR-F018).
- **Provenance:** nullable `source_project_id` (`ON DELETE SET NULL`).
- **Agent tools:** `propose_transfer` (validates `TransferInput` incl. the invariant; the activity id comes
  from `list_processing_activities`, the optional vendor id from `list_vendors`), `list_transfers`. The
  activity/vendor ids are model-supplied A-class args resolved against the register (membership-checked, like
  `link_processing_activity_to_system`); `source_project_id` stays B-class closure-injected.
- **Read API:** transfers surface on `ProcessingActivityRead` (a `transfers` summary list — destination,
  restricted, mechanism); optionally `GET /ropa/transfers` if a standalone list is wanted (decide in 5b).

### Export changes (PRIV-4a `app/ropa_export.py`)

- **5a:** add a **"Recipients"** column to `ACTIVITY_HEADER` / `_activity_row` (vendors joined `Name (role)`,
  the `_systems_cell` pattern); add a **Vendors** sheet to the XLSX (name, role, country, DPA status, linked
  activities). Drop `"Categories of recipients"` from `ART30_FIELDS_NOT_YET_RECORDED`. Every new cell goes
  through `_csv_safe` (OWASP CSV-injection — the register holds untrusted model-proposed strings).
- **5b:** add a **"Transfers"** column to the activity row (e.g. `destination — mechanism (restricted)`,
  joined); optionally a **Transfers** sheet. Drop `"Third-country transfers and the safeguards applied"` from
  the coverage tuple. `_csv_safe` on every new cell.
- Add `_humanize`-style labels for the new enums (e.g. `uk_idta` → "UK IDTA", `standard_contractual_clauses` →
  "Standard contractual clauses (SCCs)") via the existing `_SYSTEM_TYPE_LABELS`-style maps so the deliverable
  reads like a lawyer wrote it.

### Web (read-only register UI — the module-UI requirement)

`web/src/lib/lq-ai/api/ropa.ts` gains the Vendor/Transfer wire types + `listVendors`/`getVendor` (+ `listTransfers`
if added). `components/ropa/RopaRegister.svelte` gains a **Vendors** tab (5a) alongside Activities | Systems;
`ProcessingActivityDetail.svelte` shows the activity's **recipients** (5a) and **transfers** (5b, with the
restricted/mechanism badge). `format.ts` gains the new enum humanizers. F013 style, honest empty states — NOT
OneTrust's chrome. The export control (PRIV-4a) is unchanged (it already pulls the full register).

## Files (target — grouped per the recommended split)

**PRIV-5a (Vendors):**
- `api/app/schemas/ropa.py` — `VendorRole`, `DpaStatus` StrEnums; `VendorInput`; `VendorRead`/`VendorSummary`;
  add `vendors`/`recipients` to `ProcessingActivityRead`.
- `api/app/models/ropa.py` — `Vendor` ORM + CHECK mirror + `_VENDOR_ROLES`/`_DPA_STATUSES`;
  `processing_activity_vendors` Table; relationships on `ProcessingActivity` and `Vendor`.
- `api/alembic/versions/0060_vendors.py` — `vendors` + `processing_activity_vendors` (+ index on `vendor_id`).
- `api/app/agents/ropa_tools.py` — `propose_vendor`, `link_vendor_to_activity`, `list_vendors`; extend
  `ROPA_TOOL_NAMES`.
- `api/app/api/ropa.py` — `GET /ropa/vendors`, `/ropa/vendors/{vendor_id}`.
- `api/app/ropa_export.py` — Recipients column + Vendors sheet; shrink coverage; new humanizers.
- `web/.../api/ropa.ts`, `components/ropa/RopaRegister.svelte`, `ProcessingActivityDetail.svelte`, `format.ts`.
- Tests: `api/tests/test_ropa.py` (Vendor invariants), `tests/agents/test_ropa_tools.py` (propose/link/list +
  guard/audit), `tests/test_ropa_read.py` (vendors read + activity recipients), `tests/test_ropa_export.py`
  (Recipients column + Vendors sheet + shrunk coverage), **`tests/test_endpoints.py`** (IMPLEMENTED_ROUTES +=
  the new GETs; `_PARAM_VALUES += vendor_id`), **`tests/test_openapi.py`** (EXPECTED_PATHS + bump the route
  count), `web/.../ropa.test.ts` + any new pure helper.

**PRIV-5b (Transfers):** the parallel set — `Transfer`/`TransferInput`/`TransferRead` + the invariant; migration
`0061_transfers.py`; `propose_transfer`/`list_transfers`; transfers on `ProcessingActivityRead` (+ optional
`GET /ropa/transfers`); export Transfers column/sheet + shrink coverage; web activity-detail transfers;
the same test set incl. the **invariant accept/reject (both directions)** in `test_ropa.py` and the DB-CHECK
defense-in-depth test.

## Build order (per slice — the PRIV-3 recipe, lessons banked)

1. **Domain first (TDD the invariant):** schema input + read DTOs + ORM + CHECK mirror; `test_ropa.py` invariant
   accept/reject (for 5b: both directions of restricted⇔mechanism) + the DB-CHECK defense-in-depth test.
2. **Migration** `0060`/`0061`: write it, **verify up/down/up on a throwaway pgvector container — NEVER the dev
   DB** (CLAUDE.md hard rule); confirm CHECK constraints present after upgrade, tables gone after downgrade.
3. **Agent tools** + tool/guard/audit/real-loop tests (`test_ropa_tools.py`); extend `ROPA_TOOL_NAMES`.
4. **Read API** + `test_ropa_read.py`; **register the GLOBAL contracts** (`test_endpoints.py` +
   `test_openapi.py` + route-count bump) and **run the FULL `pytest -q`, not the slice subset** (the banked
   PRIV-3 lesson — new routes trip the route-coverage + OpenAPI-sketch contracts; CI catches them, the subset
   run does not).
5. **Export** changes + `test_ropa_export.py` (new columns/sheets + shrunk coverage + injection guard on new
   cells).
6. **Web** client + register UI; `npm run check` + `npx vitest run` (NOT `npm run test:frontend` — that's bare
   `vitest` watch-mode and never exits).
7. **Migration apply to dev stack:** rebuild `api` + `arq-worker` + `ingest-worker` **together** (the non-migration
   api code change ALSO needs `docker compose build api && up -d --no-deps api` — the api container bakes code).
   Rebuild `web` before UI debugging.
8. **Live-verify** on localhost (seed a vendor + a restricted transfer with a mechanism, and a rejected one;
   download all three export formats; confirm the Recipients/Transfers columns + the shrunk coverage note;
   screenshot the Vendors tab + activity detail). Evidence → `docs/fork/evidence/priv-5a/` (+ `priv-5b/`).
9. **Security + simplification pass** (folded into the adversarial review).

## Verification (ADR-F005 gate — per slice)

`docker run … pytest -q` (FULL suite, counts quoted) + **ruff & mypy from the REPO ROOT** (root `ruff.toml`,
line-length 100 — running from `api/` falls back to 88 and over-wraps; mypy gates in CI separately from pytest);
`web && npm run check` (0 err) + `npx vitest run`; migration throwaway-verified; live download + screenshot
evidence; fresh-context adversarial+security+simplification review (CSV-injection on the new export cells is a
named check; the restricted⇒mechanism invariant verified in both layers); HANDOFF updated. Squash-merge against
`sarturko-maker/lq-ai-fork` once CI is green. **Compact after each slice.**

## Security notes (folded in, not an afterthought)

- **Shared-read, authenticated** (ADR-F019): the new read endpoints mount under `_active`; no per-user scoping;
  404 = a genuinely missing id, never an existence leak. The register carries no `source_project_id` outward.
- **CSV/XLSX injection** extends to every NEW export cell (vendor names, transfer destinations, free-text
  details are all model-proposed → untrusted on the way out) — `_csv_safe` guards them, with a test.
- **Code-validated writes:** the invariant lives in `TransferInput` (rejected back to the model) AND the DB
  CHECK; `source_project_id` stays B-class closure-injected (the model cannot name another matter); every write
  flows through `guarded_dispatch` (R5/R6 + one audit row of counts/types/IDs, never the proposed values).
- **No new dependencies** (no new SBOM surface): reuses pydantic / SQLAlchemy / openpyxl (already present).
- **Parameterized SQL only;** the CHECK fragments interpolate only hardcoded GDPR-canonical constants (no user
  input → no injection surface), like the PRIV-1 `_in_set` precedent.

## ADR?

Likely **no new ADR** — ADR-F019 already states the graph "hangs off Vendors/Processors + Transfers (PRIV-5)",
and the restricted⇒mechanism invariant follows the established ADR-F018 code-validated-invariant pattern
(PRIV-1's art9 invariant carried no per-invariant ADR). Record the two structural calls (transfer = child of an
activity; restricted is *declared* not *derived*) as a one-line comment at the code seam + here. **Write a light
ADR-F021 only if** the maintainer picks a non-obvious option in § Decisions (e.g. derive restricted from a
maintained adequacy list, or make transfer standalone-global rather than activity-child) — those would surprise
a future reader and cross the "diverges from the established pattern" bar.

## Decisions — DECIDED (maintainer, 2026-06-18)

1. **Slice boundary → SPLIT.** PRIV-5a (Vendors / recipients) ships first; PRIV-5b (Transfers + the invariant)
   follows and depends on it. Two small independently-shippable verticals, two migrations, matching the
   short-slice → compact rhythm.
2. **Vendor risk → DEFER to assessments (PRIV-A1).** Vendor stays lean — `name`, `vendor_role`, `description`,
   `country`, `dpa_status`. No `risk_level` field in PRIV-5a; risk is an assessment-track concept.
3. **Restricted transfer → DECLARED bool.** A `restricted` bool the agent/code sets; the invariant
   `restricted ⇒ mechanism` mirrors `special_category ⇔ art9_condition` exactly. No adequacy/EEA country list
   to maintain (that drifts as adequacy regs change). A derived helper list stays a possible later enhancement.

**Transfer** is modelled as a **child of one processing activity** (required FK, CASCADE) with an optional
recipient vendor — the Article 30 structure (maintainer not asked to override; standalone-global was the
alternative). No new ADR needed under these (obvious) choices — recorded under ADR-F018/F019; a one-line seam
comment will note the transfer-coupling + declared-restricted calls.

**→ Implementing PRIV-5a now.**
