# F2 Tabular T6 — grid review WORKSPACE + human cell-override (ADR-F055 T6 / ADR-F042)

Branch `fork/f2-tabular-t6-workspace-drawer`. **No migration** (the override rides the `results` JSONB).

## What shipped

The grid stopped being an artifact you pop open in a stacked modal and became a review **workspace**.

- **Stage-takeover, not a modal.** The `ag-grid-overlay` (z-60) + `TabularCitationModal` (z-100) are gone
  (the modal is deleted). Expand on the in-chat preview, and a Grids-tab row click, now open the grid as a
  **cockpit stage-takeover** — the `DocumentEditorPanel` fly-in reused verbatim, so the conversation card stays
  the first flex child and is never remounted (**live SSE survives**), and the shell rail collapses.
- **One docked drawer.** `TabularWorkspace` hosts the full `TabularGrid` beside one `TabularCellDrawer` that
  **pushes** the grid (no backdrop, no z-stack). The drawer shows value · confidence · tier · cost · verbatim
  `source_quote` · notes · citations · **Open source document** (a new tab via `GET /files/{source_file_id}/content`)
  · the **override + note** form.
- **Human cell-override — the load-bearing add (ADR-F042 human-write, never an agent tool).**
  `POST` + `DELETE /api/v1/tabular/executions/{id}/cells/override`: owner-scoped (`user_id` from the session),
  `mode=='agentic'`-gated (404 on a linear / cross-user row — the frozen executor is untouchable),
  `.with_for_update()` before the JSONB read-modify-write, audit carries **IDs/counts only**. The override
  rides the cell dict in `results` (4 new `CellResult` fields, all default `None`). **"Human wins" is
  structural:** `tabular_tool._upsert_row` preserves the `override_*` keys, so a re-pull /
  `update_tabular_cells` refreshes the agent value underneath but can never clobber the lawyer's correction.
  The effective display value everywhere is `override_value ?? value`.
- **Also fixed:** cell-squish (fixed 16rem column widths + horizontal scroll + a **Wrap** line-clamp toggle,
  not `width:100%`); the composer-overlap cosmetic (the drawer docks in-stage). `‹ Grids / <title>`
  breadcrumb; no standing "Grid" tab.

## The 4 locked maintainer decisions (AskUserQuestion, 2026-07-02)

1. Cell sign-off = editable **override + note** in T6 (human-write endpoint, not an agent tool); verified/
   flagged sign-off is Phase 2.
2. Deliverables = grid triages → hands flagged rows to the skill/editor flow (Phase 5); the grid does not own
   document generation.
3. Lens = document-per-row; counterparty as a column + filter (Phase 4).
4. Source view (v1) = verbatim quote + **opens the source document**; true in-editor highlight is T9.

## Gate (ADR-F005)

Deterministic, in the `lq-ai-api-dev` container against real Postgres (throwaway `lq_ai_test_*` DB):

- **api — 48 pass**: `test_tabular_endpoints.py` + `test_tabular_tool.py`. New: override **set** (agent value
  kept underneath), **clear** (revert), **404** (cross-user / linear-mode / missing cell), **422** (blank value
  / unknown key), **human-wins-across-a-subsequent-agent-write** (`_upsert_row` preserves the override), and
  **audit-carries-no-value/note**.
- **api guards — 4 pass**: `test_endpoints.py` `IMPLEMENTED_ROUTES` (+POST/DELETE tuples) + `test_openapi.py`
  `EXPECTED_PATHS` (+1 path) and `len(actual) == 158 → 159`.
- **mypy** clean (217 source files). **ruff** format + check clean (CI-parity, fresh `ruff` in `python:3.12-slim`).
- **web — 1051 vitest pass** (99 files; +12 new `tabular-workspace-helpers` tests) + **svelte-check 0 errors**
  (file count 1485 → 1484 — `TabularCitationModal` deleted).
- **Cypress** `f2-tabular-t2-grid-preview.cy.ts` (Expand → `lq-tabular-workspace`) and `m3-c-tabular-review.cy.ts`
  (cell → `lq-tabular-cell-drawer`) updated to the new test-ids. Cypress is not CI-gated (web CI = `check` +
  `test:frontend`); the specs are mock-based and deterministic.

## Screenshots (live, against the rebuilt web bundle)

Captured by `web/cypress/e2e/f2-tabular-t6-workspace-drawer.cy.ts` (mocked login + shell + a completed grid +
the override POST; deterministic, no DB state). The spec passes; 3 viewport screenshots in `T6-cypress/`:

- **`f2-tabular-t6-grid.png`** — the grid renders (Document / Term / Governing law / Liability cap; a failed
  cell; no overlay, no modal).
- **`f2-tabular-t6-drawer.png`** — a cell click opens the **docked** drawer beside the grid (it pushes the
  grid): value · confidence · verbatim **source quote** (amber) · **citations** (HIGH · Page 3) · **Open source
  document** · the **override + note** form pre-filled with the agent value.
- **`f2-tabular-t6-overridden.png`** — after Save, the human value **wins**: the grid cell shows
  "Three (3) years" + an **EDITED** badge, and the drawer shows the value with an **"Overridden by lawyer"**
  badge and the struck-through agent value underneath ("Agent value: Two (2) years"). This is the ADR-F042
  "human wins" contract, live end-to-end (POST → refetch → re-render).

(The standalone `/tabular/[id]` page centres its content at `max-width: 80rem`, so the docked drawer's right
edge is clipped in the viewport capture; all content is present. The cockpit stage-takeover — `TabularWorkspace`
in the `DocumentEditorPanel` fly-in — gives the grid + drawer the full rail-collapsed width.)

## Adversarial review (fresh-context, then verified)

A fresh-context adversarial review (2 reviewers over the diff → verify each finding) surfaced **one confirmed
should-fix**, since fixed: `TabularCellDrawer`'s draft-reset guard keyed on the display `documentName` rather
than the unique `documentId`. In a grid holding two documents with the **same filename**, switching between
their same-column cells produced an identical key, so a stale override draft was **not** reset — and Save could
write the override onto the wrong document (an ADR-F042 human-write corrupted). Fix: thread `documentId` into
the drawer and key the reset on `documentId + columnName` (both `TabularWorkspace` and `/tabular/[id]` pass it).
Everything else (the override endpoint authz / `overridden_by`-from-session / audit-no-leak / `_upsert_row`
human-wins, and the SSE-safe stage-takeover) verified clean.

## Notes / follow-ups

- `/tabular/[id]` keeps its export/cancel/banner chrome and inlines the same `TabularGrid` + `TabularCellDrawer`
  (component-level DRY; the small override-handler wiring is duplicated with `TabularWorkspace` — accepted).
- Source **highlighting** in the opened document stays T9 (v1 opens the file unhighlighted).
- Later phases: P2 verified/flagged + completion meter (migration) · P3 output-types + semantic colour · P4
  party column/filter · P5 deliverables.
