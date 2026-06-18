# PRIV-6a — personal-data taxonomy (categories of data subjects + personal data)

**Milestone:** Privacy / ROPA module (LQ.AI Oscar Edition). Slice = the first cut of **PRIV-6**, re-planned
at the boundary (the decomposition bundles four features under PRIV-6; this slice takes only the taxonomy).
Governed by **ADR-F018** (typed domain + code-validated agent writes) + **ADR-F019** (relational,
deployment-global inventory graph). **No new ADR** — implementation of accepted decisions.

## Goal

Fill **Article 30(1)(c)** — *"the categories of data subjects and the categories of personal data"* — the
**last** uncaptured Article 30(1) axis. After this slice the export **coverage note is empty**: the RoPA
register captures every Article 30(1) content field. Agent proposes (tags) → code validates → human owns.

## Maintainer decisions (this session)

1. **First PRIV-6 slice = the personal-data taxonomy** (closes Article 30), ahead of the data-flow view /
   Legal-Entity scope / programme dashboard (those ride later slices, re-planned at each boundary).
2. **Model = two M:N controlled-vocabulary entities** — `DataSubjectCategory` + `DataCategory`, each
   many-to-many to `processing_activities` (mirrors `System` / `Vendor`), **both in one slice** (they share
   an identical `{id, name}` shape). Chosen over string-list columns to keep queryable cross-links
   ("which activities process health data?") and stay on the ADR-F019 relational-graph philosophy.

## Design (implementation decisions — recorded for the maintainer)

- **Entities are pure controlled-vocabulary labels:** `{id, name, source_project_id, created_at}`. **No
  `description`** (these are tags, not narrative records — no field would be populated) and **no
  `updated_at`** (a label is immutable; this also sidesteps the carried no-`onupdate` debt). `name` carries
  a **UNIQUE** constraint per taxonomy + a length CHECK — uniqueness is what makes a controlled vocabulary
  a vocabulary (one "Employees", reused), and it makes find-or-create well-defined.
- **Agent ergonomics — list-valued "add" tools, not propose+link:** a lawyer tags an activity with several
  categories at once ("processes contact details, financial data, health data"). So instead of the
  propose+link pair (which would add 6 tools and force the model to dedup via `list`), this slice adds **two
  list-valued tag tools** that **find-or-create each name + link it (idempotent)** in one call:
  - `add_data_subject_categories(processing_activity_id, names: list[str])`
  - `add_data_categories(processing_activity_id, names: list[str])`
  plus `list_data_subject_categories()` / `list_data_categories()`. **4 new tools → 14 total.** Fewer tools
  for a tier-4 model (UX-B found M3 strains on a broad surface), self-deduplicating via the unique name,
  on-thesis for a controlled vocabulary. Each name is validated (`*CategoryInput`: non-blank, ≤200,
  `extra="forbid"`) BEFORE any write; an invalid name is rejected back to the model (never a silent fix).
  The unique constraint is the DB backstop on the rare concurrent-run race (IntegrityError → audited error).
- **No standalone detail page / `/{id}` endpoint for the taxonomies.** A category is a pure label; the
  activity→categories direction (chips on the activity detail) is the meaningful cross-link, and the
  register tab shows each label + how many activities use it. Two **list** endpoints only (route 136→138).

## Non-goals (explicit)

- No `description` / risk / sensitivity rating on a category (assessment track, PRIV-A1 if ever).
- No category **detail page** or `/{id}` endpoint; no **edit/delete/rename** (register stays agent-written,
  user-read — PRIV-6+).
- No data-flow / lineage view, no Legal-Entity scope, no programme dashboard (later PRIV-6 slices).
- No data-**element** tier (OneTrust's third taxonomy level) — categories are the Article 30 unit.

## Files

- `api/app/schemas/ropa.py` — `DataSubjectCategoryInput` / `DataCategoryInput` (name only); `*Summary`
  (id+name) on `ProcessingActivityRead`; `DataSubjectCategoryRead` / `DataCategoryRead` (id/name/created_at
  + linked `processing_activities`) for the list endpoints + the export; new fields on `Article30Export`.
- `api/app/models/ropa.py` — `DataSubjectCategory` + `DataCategory` ORM + 2 M:N tables + relationships +
  unique-name & length CHECKs.
- `api/alembic/versions/0062_personal_data_taxonomy.py` — head 0061→0062; 2 tables + 2 M:N + unique
  indexes; symmetric downgrade. Verify up/down/up on a throwaway pgvector (never the dev DB).
- `api/app/agents/ropa_tools.py` — 4 tools + helpers; `ROPA_TOOL_NAMES` (→14), docstring, returned list.
- `api/app/api/ropa.py` — 2 GET list endpoints; selectinload the new rels on the 3 activity queries +
  export query loads the two taxonomies.
- `api/app/ropa_export.py` — 2 activity columns + 2 sheets (Data Subjects / Data Categories) + row builders;
  `ART30_FIELDS_NOT_YET_RECORDED` → empty; docstring updated (Article 30(1) now fully captured).
- `web/src/lib/lq-ai/api/ropa.ts` — `DataSubjectCategorySummary`/`DataCategorySummary` +
  `*Read` + `data_subject_categories`/`data_categories` on `ProcessingActivityRead` + 2 list fns.
- `web/src/lib/lq-ai/components/ropa/RopaRegister.svelte` — 2 tabs + 2 tables; load the 2 lists.
- `web/src/lib/lq-ai/components/ropa/ProcessingActivityDetail.svelte` — 2 chip sections (data subjects /
  data categories).
- `web/src/lib/lq-ai/components/ropa/format.ts` (+ `.test.ts`) — `REGISTER_TABS` (5 tabs) + empty-state copy.
- Tests: `api/tests/test_ropa.py`, `test_ropa_read.py`, `test_ropa_export.py`,
  `tests/agents/test_ropa_tools.py`; global contract tests `tests/test_endpoints.py` + `tests/test_openapi.py`
  (routes 136→138).
- Docs: `docs/fork/HANDOFF.md`, `docs/fork/MILESTONES.md`.

## Verification (ADR-F005 gate)

Migration up/down/up on a throwaway pgvector; full `pytest -q` (count quoted) + `ruff format && ruff check`
+ `mypy` from repo root; `npm run check` + `npx vitest run`. Rebuild api+arq-worker+ingest-worker (migration)
+ web. Live dev-stack: agent tags an activity with both taxonomies; read API + all 3 exports reflect them;
**coverage note now empty**; screenshots in `docs/fork/evidence/priv-6a/`. Fresh-context
adversarial+security+simplification review. HANDOFF + MILESTONES updated; squash-merge.

## Audit outcome (ultracode multi-agent review, 2026-06-18)

The fresh-context review was run as a **54-agent adversarial workflow** (7 lenses × the whole ROPA module →
per-finding refute-by-default skeptics → synthesis): **23 candidates → 20 survived → 13 confirmed**, initial
verdict **BLOCK** on 2 high-severity defects in the new find-or-create path. Both fixed in-slice plus a
cluster of cheap correctness/transparency/test fixes; the medium confused-deputy finding is flagged to the
maintainer (MILESTONES § Backlog). Full write-up + dispositions:
**`docs/fork/evidence/priv-6a/audit-report.md`**. Headline fixes: the find-or-create is now race-safe
(SAVEPOINT + on-conflict re-select — no raised DB error, no value leak), and the vocabulary is
case/whitespace-insensitive (collapse-whitespace validator + `func.lower` find + functional UNIQUE index on
`lower(name)`).
