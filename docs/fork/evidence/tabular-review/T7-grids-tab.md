# F2 Tabular T7 — the matter Grids tab (ADR-F055)

The cockpit gains a **"Grids"** tab (sibling to Documents — source files vs derived
grids) that lists a matter's agentic grids, opens the reused full grid, and soft-deletes
one. This actions the maintainer's ask #3 ("grids need to be available in a tab for
clarity") and completes the artifact lifecycle: T1 builds, T2 previews in chat, T7
manages them per matter.

## Backend — one owner-scoped read route, no migration

`GET /api/v1/tabular/matters/{project_id}/grids` (`api/app/api/tabular.py`) returns the
matter's `mode='agentic'`, non-deleted grids, recent-first. Owner-scoped through
`_load_visible_project` (cross-user / unknown / archived → **404**, no existence leak).
The shared `TabularExecutionSummary` gains two default-safe fields — `column_names` (the
grid has no stored title, so the tab derives one from its columns) and `fill_mode`
(fanout|retrieval; null for a linear execution). Soft-delete reuses the existing owner-scoped
`DELETE /tabular/executions/{id}`. No schema change.

Tests (`api/tests/test_tabular_endpoints.py`): the route returns only the owner's live
agentic grids (linear + deleted + other-matter excluded), carries `column_names`/`fill_mode`,
and 404s cross-user / unknown-matter.

## Frontend — `GridsPanel` + a cockpit tab

`web/.../components/matter/GridsPanel.svelte` (modeled on `DocumentsPanel`): loads via
`listMatterGrids`, renders a derived-title row per grid (column names) with a
`docs · columns · fill-mode · age` subtitle, a status badge, an **open** (→ the reused
`/tabular/[id]`) and a **delete**; an empty state when the matter has none; a
`reloadKey` reconcile so a newly-finalized grid appears when a run settles. Pure logic
(`grids-panel-helpers.ts`: title/subtitle/fill-mode/status) is unit-tested.

## Browser render — `T7-cypress/` (deterministic, no LLM)

`web/cypress/e2e/f2-tabular-t7-grids-tab.cy.ts` drives the real panel with the grids
endpoint intercepted, clicks the **Grids** tab, and captures:

- `f2-tabular-t7-grids-light.png` / `-dark.png` — the populated list: **Term, Governing
  law** (3 documents · 2 columns · fan-out) and **Counterparty, Value, Change of control,
  Liability cap** (12 documents · 4 columns · retrieval), each Ready with a delete action.
- `f2-tabular-t7-grids-empty.png` — the empty state ("No grids yet — ask the agent to
  compare a field across several of this matter's documents").

Result: **2 passing, 3 screenshots.**

## Gate

- `npm run check` 0 errors · **1039** frontend tests (7 new helper tests) · eslint clean.
- `ruff check` clean · `mypy` 217 files clean · **8** tabular-endpoint tests (2 new).
- No migration; frozen executor untouched (the route filters `mode='agentic'`).
