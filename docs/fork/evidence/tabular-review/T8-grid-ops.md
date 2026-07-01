# F2 Tabular T8 — conversational grid-ops (ADR-F055)

The Commercial agent can now **edit a finalized grid in place** on the lawyer's
instruction — the "bash" loop from the maintainer's vision ("tell the agent to update
certain positions"). New tool `update_tabular_cells(grid_id, document, cells)`, granted
alongside the T1 tools, edits a **completed** grid (distinct from `record_tabular_row`,
which only fills a grid still being built). Matter-tier auto-write-then-correct
(ADR-F042): the agent writes, the lawyer owns and can undo.

## Scope + a deferral

**Shipped:** `update_tabular_cells` (re-pull / fix cells of a finalized grid) + the
conversational-edit doctrine. `record_tabular_row` and `update_tabular_cells` share one
`_apply_cells` core (resolve doc → verify in grid → validate columns → upsert → audit);
they differ only in the status gate (running vs completed), the audit action
(`tabular.row_recorded` vs `tabular.cells_updated`), and the confirmation message.

**Deferred (T8b): `combine_documents`.** Merging document B's row into A's has a
**citation-integrity complication**: a grid cell's citations resolve its `cited_chunk_ids`
against the *row's* `document_id`, so cells merged in from B (whose chunk ids belong to B)
would resolve against A — a wrong-document citation. Doing it right needs a per-cell
document_id (a data-model decision), so `combine_documents` gets its own slice rather than
shipping a citation bug.

## Mechanics — deterministic (CI)

`api/tests/agents/test_tabular_tool.py` (+7 tests, 30 total): `update_tabular_cells` edits
a completed grid in place (changes the named cell, leaves the rest of the row untouched,
keeps `status='completed'`, adds no row); rejects a still-running grid (use
`record_tabular_row`), an unknown column, a document not in the matter, an unknown grid,
and a cross-matter binding (404-conflated); audits as `tabular.cells_updated`. The
guarded-closures end-to-end test now drives `start → record → finalize → update` through
`guarded_dispatch` on a live running run.

## Behaviour — live (ADR-F015 finding, masked, DeepSeek)

`api/tests/agents/scenarios/test_tabular_update_eval.py` (provider-marked). A finalized
grid is pre-seeded with nda-alpha's Term **deliberately wrong** ("One (1) year"); the
lawyer asks the agent (holding the grid_id, as it would in-conversation) to fix it. The
`tabular-review` skill is loaded + injected (the T3 attribution lesson).

```json
{
  "status": "completed",
  "called_update": true,
  "alpha_term_after": "Two (2) years",
  "cell_changed": true
}
```

The agent selected `update_tabular_cells` (not `record` / `start`), re-read the document,
and corrected the cell to **"Two (2) years"**. (The edit loop works within a conversation,
where the agent holds the grid_id from building the grid — matching the maintainer's
"then interact with the grid" flow. Cross-conversation editing would need an agent-facing
grid-listing tool — a future item.)

## Gate

- `ruff` + `mypy` (217) clean; 30 tabular-tool + 54 capability/composition tests green.
- No migration; the frozen linear executor and worker are untouched.
