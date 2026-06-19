# PRIV-6b — Privacy programme dashboard (plan)

**Status:** proposed (maintainer edits this before implementation — CLAUDE.md § Iteration).
**Milestone:** Oscar Edition / Agentic Modules → Module 1 (Privacy/ROPA).
**ADRs:** implements ADR-F018 (module = typed domain + code-owned truth) + ADR-F019 (deployment-global,
shared-read register). **No new ADR** (no architectural call — read-and-aggregate over the existing schema).
**Slice size:** read API + web, **no migration**. One PR.

## Context

PRIV-6a closed the full Article 30(1) content set — the register now captures activities, systems,
vendors/recipients, third-country transfers, and the data-subject/personal-data taxonomy. The content is
complete; what's missing is a way to **SEE the programme** (the module-UI requirement, 2026-06-18: render
the domain like the reference product, in our F013 style). PRIV-6 bundled three features
(data-flow view + Legal-Entity scope + programme dashboard); the maintainer picked the **programme
dashboard** as the first 6b slice. The other two become **6c** (data-flow / lineage view) and **6d**
(Legal-Entity / controller scope — the only one needing a migration).

## Goal

A read-only **programme overview** over the deployment-global ROPA register: headline totals, the
register's shape (lawful-basis / controller-role / DPA-status breakdowns, special-category & restricted-
transfer counts), and honest **gap indicators** ("needs attention"). It is the landing view of the ROPA
surface inside a Privacy matter — you open onto the programme, then drill into the register tabs.

## Non-goals (explicit — keep the slice small)

- **No data-flow / lineage diagram** — that is 6c.
- **No Legal-Entity / controller entity or per-controller scoping** — that is 6d (needs a migration).
- **No writes / edits / remediation actions** — the dashboard reads; the agent writes (system proposes,
  user owns). Gap indicators *inform*; they don't fix.
- **No time-series / trend / history** — `updated_at` has no `onupdate` yet (carried deferral); a "changed
  since" view is out of scope and would be misleading.
- **No new domain fields, no migration.** Pure aggregation over what PRIV-1…6a already store.

## Approach (recommended — maintainer may swap to the lighter client-side variant below)

**Backend owns the aggregation truth** (consistent with ADR-F018 "code owns the domain", reusable by the
future programme report + the assessment track, server-testable), mirroring the PRIV-4a export pattern
(load rows → pure builder → DTO):

1. **`app/ropa_summary.py`** (new, pure) — `build_summary(activities, systems, vendors) -> ProgrammeSummary`
   over the `*Read` DTOs (exactly the data the export already assembles). Pure function, no I/O →
   unit-tested in isolation like `ropa_export.build_export`. All counts derived from the loaded rows
   (`a.vendors == []`, `a.special_category`, `t.restricted`, `v.dpa_status in {pending, none}`, …).
2. **`app/schemas/ropa.py`** — new read DTOs:
   - `CountByValue { value: str; count: int }` (one breakdown bucket).
   - `ProgrammeGaps { activities_without_systems, activities_without_recipients,
     activities_without_data_categories, activities_without_data_subjects, vendors_without_dpa: int }`.
   - `ProgrammeSummary { activities_total, systems_total, vendors_total, transfers_total,
     transfers_restricted, special_category_activities, systems_using_ai: int;
     lawful_basis, controller_role, dpa_status: list[CountByValue]; gaps: ProgrammeGaps }`.
   - Breakdowns returned in **canonical enum order**, including zero buckets (deterministic + honest; the
     web hides zeros if it wants). `vendors_without_dpa` = `dpa_status ∈ {pending, none}`.
3. **`app/api/ropa.py`** — `GET /ropa/programme-summary` (response_model `ProgrammeSummary`). Factor the
   triple load (activities+selectinloads / systems / vendors) currently inlined in `export_article_30`
   into a private `_load_register(db)` helper and reuse it here (DRY; one load path for export + summary).
   Rides the router's existing `dependencies=_active` mount → **shared-read** (ADR-F019), no per-endpoint
   auth. **Even safer than the existing register reads**: the summary is counts only — no free-text — so
   the confused-deputy private→shared concern (Backlog / ADR-F021) doesn't apply to this payload.
4. **Web** — `lib/lq-ai/api/ropa.ts`: wire the `ProgrammeSummary` types + `getProgrammeSummary()`.
   `components/ropa/ProgrammeDashboard.svelte` (new): F013 cards — a totals strip, breakdown bars
   (single-accent, reuse `Badge`/the existing calm style), and a "Needs attention" list from `gaps`
   (zero gaps → a calm "nothing outstanding" state, honestly). Surface it as the **default first tab**
   `'overview'` in `RopaRegister.svelte` (`REGISTER_TABS` gains `{ id:'overview', label:'Overview' }`
   first; `tab` defaults to `'overview'`) — the ROPA surface opens on the programme, then the register
   tabs drill in. Empty register → the dashboard shows all-zeros honestly (it already has `registerEmpty`).
   `format.ts`: labels for any new buckets reuse the existing `lawfulBasisLabel`/`controllerRoleLabel`/
   `dpaStatusLabel` humanizers (no new label families).

### Lighter alternative (if the maintainer prefers web-only, like UX-B-5)

`RopaRegister.svelte` already loads activities/systems/vendors/categories on mount, so the dashboard could
be computed **client-side** by a pure `buildProgrammeSummary(...)` TS helper (vitest-tested) with **no new
endpoint** and **zero contract-test churn**. Smaller, but the aggregation logic then lives only in the
client and isn't reusable server-side (programme report, assessment track). Recommendation: backend, for
durability — but this is a clean fallback if we want the absolute-minimum slice.

## Files

- **api (new):** `app/ropa_summary.py`; tests `tests/test_ropa_summary.py` (pure builder) + summary cases
  in `tests/test_ropa_read.py`.
- **api (edit):** `app/schemas/ropa.py` (3 DTOs); `app/api/ropa.py` (`_load_register` helper +
  `GET /ropa/programme-summary`); **global contract tests** `tests/test_endpoints.py`
  (`IMPLEMENTED_ROUTES` += the new route) + `tests/test_openapi.py` (`EXPECTED_PATHS` += path; **route
  count 138 → 139**) — the PRIV-3 lesson: a new endpoint trips the route-coverage + OpenAPI contracts.
- **web (new):** `components/ropa/ProgrammeDashboard.svelte`.
- **web (edit):** `api/ropa.ts` (types + `getProgrammeSummary`); `components/ropa/RopaRegister.svelte`
  (Overview tab, default); `components/ropa/format.ts` (`REGISTER_TABS` + any bucket labels);
  `components/ropa/format.test.ts` (tab list + labels).

## Verification (DoD — shown, not asserted)

- **api:** `ruff format && ruff check` (from repo root) + mypy clean; full containerized `pytest -q`
  (count quoted, must be +N over 2276) — **run the FULL suite**, not just the slice files (contract tests).
  New tests: pure-builder over a known fixture (every field), empty-register → all zeros,
  gaps fire exactly when a link/DPA is missing, shared-read (200 active / 401 no-auth), route+OpenAPI
  contracts.
- **web:** `npm run check` (0 err) + vitest (count quoted); rebuild the `web` container; **headed Cypress
  screenshot** of the Overview tab (light+dark × wide+narrow) → `docs/fork/evidence/priv-6b/`.
- **live:** dev stack (no migration → no worker rebuild needed; rebuild `web` only). Seed the existing
  demo "Programme — GDPR / ROPA" matter; confirm the totals/breakdowns/gaps match the seeded register and
  the empty state is honest. Screenshot.
- **review:** fresh-context adversarial + **security + simplification** pass (every slice): no secrets;
  read-only; counts-only payload (no free-text leak); aggregation matches the register; no `--lq-*` tokens;
  Oscar/OneTrust look NOT copied (F013 only); `_load_register` dedup doesn't change export behavior.
- **HANDOFF.md** updated; **MILESTONES** PRIV line updated (6a ✅ / 6b ✅ / 6c data-flow + 6d legal-entity
  remaining). Merge per ADR-F005.

## Risks / notes

- **Contract-test churn** is the one easy-to-miss step (route count + OpenAPI paths) — covered above.
- **Efficiency:** aggregating over loaded rows (vs SQL `GROUP BY`) is fine at this register's scale
  (deployment-global, single client) and mirrors the export; if the register ever grows large, swap the
  builder's internals to SQL count/group-by queries — the DTO + endpoint contract stay identical.
- **Breakdown zeros:** returning all canonical buckets (incl. zeros) keeps rendering deterministic; the web
  hides zeros for calm (the preview did). If the maintainer prefers non-zero-only on the wire, trim in the
  builder — one-line change.
