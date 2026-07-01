# Plan — Agentic Tabular Review ("Grids") for Commercial

**Status:** drafted, awaiting maintainer edits. **Proposed ADR:** F055. **Migration:** 0082.
**Milestone:** Capability-panel Phase 2 (see `[[capability-panel-resequence]]`).

**User-facing vocabulary (maintainer-confirmed):** one agentic tabular review = **a "grid"**; the cockpit
gets a dedicated **"Grids"** tab (sibling to Documents — source files vs derived grids). Internally a grid
persists as a `tabular_executions` row with `mode='agentic'`.

## The vision (maintainer, verbatim intent)

Drop ~50 documents into a Commercial Matter. The Deep Agent **fans out — one subagent per document** —
each reads its doc and fills its row of a grid. The result lands in chat as a **compact preview with an
Expand control**; on Expand the cockpit panels gracefully slide back and the **full grid** takes the
stage. From there it is a **"bash" loop**: the lawyer edits the grid directly *or* tells the agent in plain
language ("add a governing-law column", "combine docs 3 and 7", "re-pull the indemnity cap for row 12")
and the agent re-runs just those cells. At scale, one-subagent-per-doc gives way to **chunk + embed +
retrieve** filling the *same* grid. The agent **proactively suggests** building a grid when it fits
(users may not know the capability exists) and **understands natural-language** requests for one. Grids
accumulate over a matter and live in their own tab.

## Context — we are assembling, not building greenfield

The fork already owns every load-bearing piece. The work is wiring, one tool module, one skill, one SSE
frame, one migration, the "Grids" tab, and the cockpit grid takeover.

| Layer | Already there | Source |
|---|---|---|
| Data shapes | `ColumnSpec` / `CellResult` / `Citation` / `TabularResults` (executor-agnostic; `_synthesize_cell_citations`) | `api/app/schemas/tabular.py` |
| Web grid | `TabularGrid` / `TabularCell` / `TabularCitationModal` (props-only) + `/tabular/[id]` page + `tabular.ts` | `web/.../components/`, `web/.../routes/.../tabular/[id]` |
| Persistence | `tabular_executions` (snapshot `columns` + `results` JSONB, `status` CHECK, soft-delete, `parent_execution_id`) | `api/app/models/tabular.py`, mig `0036` |
| Agent-tool seam | `build_matter_tools` factory + `guarded_dispatch` chokepoint (R6/R5/R4 + audit) | `api/app/agents/tools.py`, `guard.py` |
| Capability gating | `AREA_TOOL_GROUPS` + per-matter toggles (ADR-F054); `capabilities.py:63` reserves the tabular slot | `api/app/agents/capabilities.py`, mig `0081` |
| Skills (craft) | area-bound `practice_area_skills`, SKILL.md format, gated by a skill capability toggle (ADR-F041) | `api/app/skills/`, `composition.py` |
| Fan-out | deepagents `task` + model-free subagents + `FanOutQuotaMiddleware` + ADR-F034 reconciliation | `area_agent.py`, `fan_out_middleware.py` |
| Retrieval fill engine | `matter_search_reranked` (hybrid FTS + local embed + cross-encoder) — **the >quota path** | `tools.py:_search` |
| Budget envelope | `resolve_envelope` → economy 8 / **balanced 32** / generous 48 `fan_out_quota`; token brake | `budget.py`, `config.py` |
| Streaming | `RunStreamPublisher` data-* parts; `ConversationPanel.svelte:632` switch; `LiveChange`/`ChangeLedger` | `stream.py`, `ui-message-stream.ts`, `live_changes.py` |
| Doc viewer | embedded Collabora/CODE over WOPI (MPL, not AGPL) — the source-highlight target | ADR-F047, mig `0074/0075` |
| Roster | `matter_participants` (side + trust) — counterparty-profile synergy | ADR-F048 |

**Frozen — do NOT extend** (ADR-F001): `api/app/tabular/{executor,nodes,state}.py` (linear LangGraph,
slot-fill, no model-chosen tool call). We reuse its *data shapes + web grid*, never its orchestration.

## LQ-Grid review (reference-only — patterns, not code; we are Svelte)

LQ-Grid (`github.com/sarturko-maker/LQ-Grid`, the maintainer's React reference) **validates this design**:
its *"the UI never calls an LLM directly — all intelligence goes through Claude Code"* is our
gateway+agent model; its **engine toggle (Claude full-document vs Isaacus fast NLP)** is *our fan-out-read
vs retrieval-fill crossover*, just manual. Its cell = `value` + **`source_quote`** (verbatim, ~125-char
cap) + clause ref + `confidence` + **`notes`** (commentary on ambiguous extractions) — our `CellResult`
plus two fields worth adopting. Patterns harvested (mapped to slices below): source highlighting,
column-preview pills, document grouping with later-doc precedence, filter/smart-sort/resize/reorder/wrap/
row-numbers/semantic-coloring, cell-detail side drawer, counterparty profiles (→ Matter Roster), and
grid→deliverables (Word letters/reports). License: reference-only, no code copied.

## Decisions (maintainer-confirmed)

1. **Fill engine = crossover at `fan_out_quota`.** `doc_count ≤ quota` → one subagent per document, each
   **reads its doc in full** and fills its row. `doc_count > quota` → **retrieval-fill**: ≤quota subagents
   each own a **batch of rows** and fill each cell via `matter_search_reranked` + a grounded extraction.
   The crossover *is* the envelope's `fan_out_quota` (economy 8 / balanced 32 / generous 48). "One subagent
   per 50 docs" is out of bounds (it would weaken the brake); generous (48) is the dial-up.
   - **Extraction is always a counted model turn** (seen by the runner's `usage_metadata` token brake,
     ADR-F051) — never a tool-internal gateway loop. So fan-out↔retrieval = "full-read per doc" vs "batched
     retrieval per cell"; both stay within quota and both are token-counted.
2. **Persistence = reuse `tabular_executions` + a `mode` discriminator** (`linear|agentic`) + `created_by_run_id`
   (provenance, ADR-F046) + `fill_mode` (`fanout|retrieval`). Scope the frozen ARQ worker to
   `mode='linear'`. Reuses the whole read/list/export API + `/tabular/[id]` + grid components.
3. **Cells = reuse `CellResult` + persist `cited_chunk_ids`** (synthesize `Citation` at read time), **plus
   `source_quote` and `notes`** (LQ-Grid). No new citation tables; audit-clean (IDs/counts, never raw
   clause text). *(Citation-storage call delegated to the agent; raise if undesired.)*
4. **Edit model = mutate the same grid in place, audited** (ADR-F042). The bash loop expects the same grid
   to update. `combine_documents` uses **later-doc precedence** (LQ-Grid grouping). **Deliberately diverges**
   from the frozen executor's immutable-child posture (Decision C-9) — called out in ADR-F055.
5. **Coverage = a `finalize` gate.** `finalize_tabular_review` refuses/loops until every (doc × column) cell
   was *attempted*; ungrounded cells render `confidence=failed` (honest receipts), never silent gaps.
   Reuses the single-dispatch no-silent-action gate (ADR-F034/F032). No O-series pipeline.
6. **Discoverability = a SKILL, not routing code** (craft layer, ADR-F041). A Commercial `tabular-review`
   SKILL.md teaches the agent to *proactively offer* a grid (with column pills) when the matter has several
   docs and the ask is tabular, and to *map NL intent* ("compare these", "table of…", "DD grid") to the
   tool. It carries built-in **column templates** (M&A DD / key terms / GDPR). Eval-gated (masked judge).
7. **Home = a dedicated "Grids" cockpit tab** listing the matter's grids (open/rename/delete) — sibling to
   Documents (source vs derived). User-facing noun: "grid".

## Goals
1. Tabular review is a **Commercial matter TOOL** the agent drives, guarded + gated by a `TABULAR_GROUP`
   toggle, producing the existing `TabularResults` shape (+ `source_quote`/`notes`).
2. ≤ quota docs fan-out one subagent per doc; > quota fills the same grid by batched-row retrieval — the
   switch reads the same envelope, so a profile change moves the crossover for free.
3. The grid renders as a **compact preview (column pills) + Expand** in chat; Expand takes the cockpit stage
   (reused `TabularGrid` + cell side-drawer); cells fill **visibly** while the settled grid stays truth.
4. The agent **proactively suggests** grids and **understands NL** requests (the skill).
5. A **conversational bash loop** mutates the grid in place (add/re-pull/combine-with-precedence), audited.
6. Grids are **grounded** (gateway + Citation Engine; `confidence=failed` when ungrounded), **provably
   complete** (finalize gate), and **listable** in their own tab; cells can **highlight their source** in
   the embedded viewer.

## Non-goals
- No new/extended executor; `api/app/tabular/{executor,nodes,state}.py` stay byte-identical (frozen).
- No O-series orchestration (the finalize gate substitutes).
- No raising of `fan_out_quota` to chase "50" (generous=48 is the dial-up).
- No new citation tables; no per-cell tier-picker UI.
- No grid virtualization in v1 (deferred until a real >100-row grid exists; **logged, not silently capped**).
- Counterparty profiles + grid→deliverables are **backlog** (noted, not built here).

## Implementation — vertical slices (each end-to-end, runnable, one PR, ≤2–3 days)

**Core path (build now): T1 → T8. Enrichment: T9–T10. Optional: T11.**

### T1 (core) — Grid artifact + the fan-out tool path (no new UI)
- **Migration 0082**: `tabular_executions.mode TEXT NOT NULL DEFAULT 'linear'` (CHECK `in
  ('linear','agentic')`), `created_by_run_id UUID NULL` (FK `agent_runs`), `fill_mode TEXT NULL` (CHECK
  `in ('fanout','retrieval')`). Scope the ARQ worker to `mode='linear'`. Extend the cell payload with
  `source_quote` (display-capped) + `notes` (schema-level, in `results` JSONB — no column).
- **New `api/app/agents/tabular_tool.py`** — `build_tabular_tools(...)` mirroring `build_matter_tools`;
  own grant frozenset `TABULAR_TOOL_NAMES` (NOT in `MATTER_TOOL_NAMES` — confined); each via
  `guarded_dispatch`:
  - `start_tabular_review(columns, document_ids?) -> {grid_id, recommended_fill, doc_count, quota}` —
    creates the `mode='agentic'` row (snapshot `columns`, `document_ids`, `created_by_run_id`,
    `status='running'`); recommends fanout iff `doc_count ≤ envelope.fan_out_quota` and `estimate_read_cost`
    fits, else retrieval.
  - `record_tabular_row(grid_id, document_id, cells)` — a (sub)agent writes one doc's row; **incremental
    commit** so a token-budget halt leaves a partial-but-persisted grid (F1-S1). Cells: `value` +
    `cited_chunk_ids` + `confidence` + `source_quote` + `notes`.
  - `finalize_tabular_review(grid_id) -> summary` — the **finalize gate** (every cell attempted; set
    `fill_mode`, flip `status='completed'`).
- **`TABULAR_GROUP`** in `capabilities.py` → `AREA_TOOL_GROUPS[COMMERCIAL_AREA_KEY]`; gate at
  `composition.py:752`. **`TABULAR_FILL_DOCTRINE`** prompt block (mirrors `RETRIEVAL_STRATEGY_DOCTRINE`).
- **Verify:** a Commercial run over ≤8 docs persists an agentic grid (JSONB == `TabularResults`);
  renders at `/tabular/[id]`. Draft **ADR-F055**.

### T2 (core) — chat preview (column pills) + Expand → grid ✅ SHIPPED 2026-07-01
- **Refined from a `data-tabular` frame to settled-step derivation** (ADR-F055 T2 addendum,
  maintainer-confirmed): the SSE replay path re-emits only `data-step` rows, so a custom `data-*` frame is
  live-only and would vanish on reload — wrong for a durable artifact. Instead the preview anchors on the
  **settled `finalize_tabular_review` step** (grid id parsed from its short tool-call input); **T2 is
  frontend-only** (no `stream.py`/`ui-message-stream` change).
- NEW `agents/tabular-preview.ts` (`tabularGridIdsForTurn` + `summarizeGridForPreview` +
  `buildDocumentNameById`) → NEW **`TabularPreview.svelte`** (compact M×N + **column pills** + status +
  Expand) rendered after the answer in `ConversationPanel.svelte`. Expand opens the reused `TabularGrid` +
  `TabularCitationModal` in an in-conversation overlay (cockpit stage-takeover motion = T6). `/tabular/[id]`
  refactored to share `buildDocumentNameById`. 16 helper tests + a deterministic Cypress screenshot spec.
  Evidence: `docs/fork/evidence/tabular-review/T2-grid-preview.md`.

### T3 (core) — Discoverability skill: proactive offer + NL intent ✅ SHIPPED 2026-07-01
- NEW `skills/tabular-review/SKILL.md` bound to Commercial (**migration 0083**, 0056/0072 idempotent
  pattern), auto-appears as a toggleable capability (default-on, ADR-F054): *reach for a grid* on a
  multi-doc compare/extract intent (**build it**, don't answer across-many-docs in prose); map NL →
  `start_tabular_review` columns; column templates (key terms / NDA / M&A DD / SaaS / DPA); restraint on a
  single-doc lookup.
- **Eval finding (masked, live DeepSeek, ADR-F015):** **3/3 across 2 reps** with the skill genuinely injected
  (vague ask builds a grid; explicit table maps columns; single-doc stays quiet). The eval was corrected
  after fresh-context review caught the injection-attribution trap (it initially omitted `skill_registry=` →
  measured only the doctrine); it now loads `/skills` + passes the registry + credits a prose offer.
  `test_tabular_discoverability_eval.py`; evidence `docs/fork/evidence/tabular-review/T3-discoverability.md`.

### T4 (core) — Retrieval-fill engine + the crossover switch
- Batched-row subagents: ≤quota subagents, each owns a row slice, fills each cell via
  `matter_search_reranked` + a grounded extraction (own model turn), `record_tabular_row` per doc.
  `start_tabular_review` returns `recommended_fill='retrieval'` above the crossover; the doctrine routes.
- **Eval-gate** cell quality: retrieval-fill vs fan-out-read on CUAD-style fixtures; default the crossover at
  `fan_out_quota`; record the finding. (Dev-box OOM trap: FTS-only fast path for eval; rerank behind
  `settings.rerank_enabled`.)

### T5 (core) — Live cell fill (animation)
- `TabularChangeLedger` (`LiveChange`/`ChangeLedger`); `TabularCellChange.publish` → transient
  `data-tabular-cell` (modeled on `data-deal-change`, `ConversationPanel.svelte:690`). Grid + preview fill
  row-by-row; settled grid stays truth (ADR-F004).
- **Ledger coexistence:** one run-scoped Commercial ledger passed to both `build_commercial_tools` and
  `build_tabular_tools` (drains any `LiveChange` agnostically) — not two ledgers in one slot.

### T6 (core) — Cockpit stage-takeover + cell side-drawer
- Expand → panels slide back, grid takes the stage; responsive collapse (Memory/Documents motion is the
  precedent). **Cell click → side drawer** (CellDetail; LQ-Grid pattern — keeps grid context) showing
  value + confidence + `source_quote` + `notes` + citations. No new ADR.

### T7 (core) — The "Grids" tab (matter-scoped listing) ✅ SHIPPED 2026-07-01
- NEW cockpit tab **"Grids"** (sibling to Documents): lists the matter's `mode='agentic'`, non-deleted
  grids with a **derived title** (column names — grids have no stored title), doc/column counts, `fill_mode`,
  status, age; **open** → the reused `/tabular/[id]`; **soft-delete** (reuses the owner-scoped DELETE).
  Rename deferred (would need a title column) — noted. NEW `GET /tabular/matters/{project_id}/grids`
  (owner-scoped via `_load_visible_project`, cross-matter → 404); `TabularExecutionSummary` +
  `column_names`/`fill_mode` (default-safe). **No migration.** Web `GridsPanel.svelte` +
  `grids-panel-helpers.ts`. Live: `f2-tabular-t7-grids-tab.cy.ts` (list + empty, light/dark). Evidence
  `docs/fork/evidence/tabular-review/T7-grids-tab.md`.

### T8 (core) — Conversational grid-ops (the "bash" loop) ✅ SHIPPED 2026-07-01 (combine → T8b)
- `update_tabular_cells(grid_id, document, cells)` — edits a **completed** grid in place (distinct from
  `record_tabular_row`, running-only); shares one `_apply_cells` core with record; audited
  (`tabular.cells_updated`); matter-tier auto-write-then-correct (ADR-F042). Doctrine teaches the edit loop.
  +7 deterministic tests (30 total) + guarded end-to-end now includes update. **Live (ADR-F015):** the agent
  selects `update_tabular_cells` and corrects a seeded-wrong cell ("One (1) year" → "Two (2) years",
  `cell_changed`). Evidence `docs/fork/evidence/tabular-review/T8-grid-ops.md`.
- **`combine_documents` DEFERRED → T8b:** merging B's row into A's breaks cell-citation integrity (a cell's
  `cited_chunk_ids` resolve against the ROW's `document_id`; merged-in B cells would cite A). Needs a per-cell
  document_id (data-model decision) — its own slice, not a citation bug shipped under time pressure.
- *(No `data-tabular` re-emit — the T2 preview derives from the settled finalize step; an edit surfaces via
  the Grids tab / `/tabular/[id]` re-fetch. Live in-chat re-render on edit is T5's transient frame.)*

### T9 (enrichment) — Source highlighting (cell → original document)
- Cell drawer "View Source" → open the matter document in the embedded **Collabora/WOPI viewer**
  (ADR-F047) with the cited clause highlighted (citations carry chunk offsets / `source_text`). LQ-Grid's
  signature feature; heavier (viewer integration), hence enrichment not core.

### T10 (enrichment) — Rich grid affordances
- Filter (yes/no dropdown · text search) · smart sort (dates chronological · enums by severity) ·
  resizable/reorderable/wrap-toggle columns · row numbers · semantic risk coloring. Enrich `TabularGrid`
  (in-memory first; server-side filter/sort only if a real large grid demands it — benchmark, don't guess).

### T11 (optional) — Agentic cost preview
- Per-cell estimate keyed by a dedicated `purpose` (fanout-read vs retrieval-cell differ), surfaced before a
  wide run; reuses the O-2 blended estimator; labeled an estimate.

**T8b (split from T8):** `combine_documents(grid_id, documents, into)` with later-doc precedence — needs a
per-cell `document_id` first so a merged-in cell's `cited_chunk_ids` resolve against the right document (a
data-model change), then the row-merge + drop the merged docs from `document_ids`.

**Backlog (noted, not built):** an agent-facing grid-listing tool (so the agent can edit a grid across
conversations, not just within the one that built it); counterparty profiles (Matter Roster
`matter_participants` synergy);
grid→deliverables (Word letters/reports/disclosure schedules); grid virtualization (>100 rows).

## Critical files
- NEW `api/app/agents/tabular_tool.py`; NEW migration `0082_tabular_executions_agentic_mode.py`; NEW skill
  `skills/.../tabular-review/SKILL.md` (+ bind via `practice_area_skills`).
- `api/app/agents/capabilities.py` (`TABULAR_GROUP`), `composition.py` (gate + doctrine + run-scoped
  ledger), `stream.py` + `ui-message-stream.ts` + `ConversationPanel.svelte` (frames), `tabular_worker.py`
  (scope `mode='linear'`).
- NEW web `TabularPreview.svelte`, `GridsTab.svelte`; reuse `TabularGrid/Cell/CitationModal`, `tabular.ts`,
  `/tabular/[id]`; reuse the WOPI viewer (T9).
- Docs: ADR-F055; this plan; `MILESTONES.md`; `HANDOFF.md`; evidence `docs/fork/evidence/tabular-review/`.

## Verification / DoD (ADR-F005 gate, per slice)
- Build + lint (`ruff format && ruff check` from **repo root**) + `mypy app` + tests pass, output shown.
- Containerized suites for touched services, counts quoted; throwaway-pgvector migration test for 0082
  (`skills:/skills:ro` + container IP).
- Fresh-context adversarial review incl. the mandatory **security + simplification pass**: tabular tools
  guarded + own grant set (R6 fail-closed when off); 50 uploads treated as **untrusted model input** (cells
  are data, never instructions); no provider key outside the gateway; no stray files; dead-code/dup sweep.
  Frozen `api/app/tabular/{executor,nodes,state}.py` provably untouched.
- Live verification (screenshot / provider test) when behavior changes; rebuild api+arq+ingest together on
  the migration; `docker image prune -f` dangling after.
- Branch + PR (`gh ... --repo sarturko-maker/lq-ai-fork`; direct main pushes blocked); commits end
  `Co-Authored-By: Claude Opus 4.8`; HANDOFF updated at slice end.

## Risks / gotchas
- **Retrieval-fill quality carries the headline 50-doc demo** → eval-gate T4 before defaulting; ship honest.
- **Token-budget blowout mid-fill** → incremental `record_tabular_row` commits leave a partial-but-persisted
  grid (F1-S1), never nothing.
- **Dev-box OOM** (bge + cross-encoder at scale) — hybrid+rerank-at-scale deferred to a ≥16 GB box; FTS-only
  fast path for dev/eval.
- **Worker/table coupling** — the `mode` discriminator + scoped worker query is mandatory.
- **Animation vs truth (ADR-F004)** — `data-tabular-cell` only flashes; `record_tabular_row` persists.
- **Provenance under fan-out (known blocker #6)** — attribute the grid at run level via `created_by_run_id`.
- **Ledger coexistence** (T5) — one run-scoped Commercial ledger.
- **Proactive-offer calibration** (T3) — over-eager offers annoy; eval must check it stays quiet when a grid
  doesn't fit, not only that it offers when it does.
- **Source-highlight offset drift** (T9) — depends on citation offsets staying valid against the rendered
  doc; soft-deleted source files break it (degrade gracefully, never crash the grid).

## Recommended order
T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 (core), then T9 / T10 (enrichment), T11 (optional).
