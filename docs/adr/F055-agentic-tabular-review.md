# F055 — Agentic tabular review as a matter tool: fill-engine crossover + grid artifact

- Status: proposed
- Date: 2026-06-30
- Deciders: maintainer (Arturs), agent
- Supersedes: —  ·  Related: F001 (fork charter / frozen executor), F042 (matter auto-write-then-correct),
  F034 (fan-out roster + reconciliation), F032 (no-silent-action gate), F049 (native memory + eval-gated
  retrieval; fan-out quota), F051 (per-run token budget), F053 (budget profiles), F054 (capability toggles),
  F046 (run provenance), F004 (render determinism)

## Context

Upstream tabular review is a **frozen linear executor** (`api/app/tabular/{executor,nodes,state}.py`): a
LangGraph walks `load_documents → extract_cells → aggregate`; each cell is one FTS query + one
slot-filling gateway call + a Citation-Engine check. There is no model-chosen tool call. Per ADR-F001 it
is bugfix-only; the fork does not extend it.

The Commercial practice area needs **grid-over-many-documents** analysis as part of the lawyer's unit of
work: drop *N* contracts into a Matter, get a columns-as-questions × documents grid, then iterate on it
conversationally ("add a governing-law column", "re-pull the cap for row 12", "combine docs 3 and 7").
The maintainer's mental model is a "bash-like" loop where the agent fans out one subagent per document.

The fork already owns the substrate this needs: the executor-agnostic **data shapes** (`ColumnSpec`,
`CellResult`, `Citation`, `TabularResults`) and **web grid** (`TabularGrid`/`TabularCell`/
`TabularCitationModal` + `/tabular/[id]`); the `tabular_executions` **persistence row**; the
**`guarded_dispatch`** tool chokepoint; **deepagents fan-out** (`task` + model-free subagents +
`FanOutQuotaMiddleware`); the **retrieval engine** (`matter_search_reranked`); the **budget envelope**
(`resolve_envelope`: economy 8 / balanced 32 / generous 48 `fan_out_quota`, token brake); the **streaming
data-\* frames** + `LiveChange`/`ChangeLedger`; and **capability toggles** (F054), whose code already
reserves the tabular slot under Commercial. The decision is how to assemble these without touching the
frozen executor, and how to honor the "50 agents" vision against the fan-out safety brake.

## Considered options

1. **Extend / subclass the frozen executor** for an agentic mode. Rejected — violates ADR-F001 (the
   linear graph is frozen); its three-node state shape is tightly coupled to slot-filling and cannot
   express model-chosen per-doc reads or a conversational mutation loop.
2. **A full O-series deterministic LangGraph orchestration** (Python walks a per-cell graph, guarantees
   completeness). Rejected for this milestone — large new surface, re-introduces the "Python walks the
   graph" pattern the fork is moving away from; a finalize gate buys provable completeness far cheaper.
3. **A new deepagents matter TOOL set + a fill-engine crossover, reusing the data/grid/persistence
   substrate** (this ADR). The lead agent drives `start → fan-out|retrieval → finalize`; the grid is a
   matter-tier artifact it maintains and the lawyer corrects.

## Decision outcome

Chosen: **option 3.** Five coupled, hard-to-reverse, upstream-diverging calls:

1. **Tabular review is a deepagents matter TOOL, not an executor.** A new `tabular_tool.py` exposes
   `start_tabular_review` / `record_tabular_row` / `finalize_tabular_review` (and, later,
   `update_tabular_cells` / `combine_documents`), each routed through `guarded_dispatch` with its **own**
   grant set `TABULAR_TOOL_NAMES` (confined, not folded into `MATTER_TOOL_NAMES`) and gated by a new
   `TABULAR_GROUP` capability toggle under `COMMERCIAL_AREA_KEY` (F054 — no toggle migration). The frozen
   `api/app/tabular/{executor,nodes,state}.py` stay untouched; only their **data shapes + web grid** are
   reused.

2. **The fill-engine crossover IS the budget envelope's `fan_out_quota`.** `doc_count ≤ quota` →
   one subagent per document, each **reads its doc in full** and writes its row. `doc_count > quota` →
   **retrieval-fill**: ≤quota subagents each own a **batch of rows** and fill each cell via
   `matter_search_reranked` + a grounded extraction. The `FanOutQuotaMiddleware` ceiling (economy 8 /
   balanced 32 / generous 48) doubles as the deliberate strategy switch. **"One subagent per 50 docs" is
   explicitly out of bounds** — it would weaken the safety brake; generous (48) is the supported dial-up.
   **Extraction is always a counted model turn** (seen by the runner's `usage_metadata` token brake,
   ADR-F051) — never a tool-internal gateway loop, which would bypass the budget. So the distinction is
   "full-read per doc" vs "batched retrieval per cell"; both stay within quota and both are token-counted.

3. **Persistence reuses `tabular_executions` + a `mode` discriminator** (`linear|agentic`), plus
   `created_by_run_id` (provenance, F046) and `fill_mode` (`fanout|retrieval`) — migration 0082. The
   frozen ARQ tabular worker's pending-scan is scoped to `mode='linear'` so it never grabs agentic rows.
   The ADR-F001 freeze covers executor *code*, not the storage row — reusing it inherits the entire
   read/list/export API + `/tabular/[id]` page + grid components. **Cell citations persist as
   `cited_chunk_ids`**, synthesized at read time (`_synthesize_cell_citations`) — no new citation tables;
   audit contract intact (IDs/counts, never raw clause text). Cells also carry `source_quote` (verbatim,
   display-capped) and `notes` (commentary on ambiguous extractions), schema-level in `results` JSONB (no
   new columns) — adopted from the LQ-Grid reference cell shape.

4. **The grid is matter-tier auto-write-then-correct (ADR-F042).** The conversational loop **mutates the
   same grid in place**, audited; the lawyer corrects/undoes/pins. `combine_documents` uses **later-document
   precedence** (the LQ-Grid grouping rule). This **deliberately diverges** from the frozen executor's
   immutable-child posture (its Decision C-9, where every bulk op spawns a `parent_execution_id` child).
   The "bash" UX requires the same grid to update.

5. **Completeness via a `finalize` gate, not an orchestration pipeline.** `finalize_tabular_review`
   refuses/loops until every (doc × column) cell was *attempted*; ungrounded cells render as
   `confidence=failed` (honest receipts), never silent gaps — reusing the single-dispatch no-silent-action
   gate (ADR-F034/F032).

6. **Discoverability is a SKILL, not routing code** (craft layer, ADR-F041). A Commercial `tabular-review`
   SKILL.md teaches the agent to *proactively offer* a grid (with column pills) when a matter holds several
   documents and the ask is tabular, and to *map natural language* ("compare these", "table of…", "DD
   grid") onto `start_tabular_review` with inferred columns; it carries built-in column templates. Intent
   recognition is model-driven (deepagents tool selection), tuned by eval — there is no special routing
   path. The behaviour is bounded by eval (it must stay quiet when a grid does not fit, not only offer when
   it does).

7. **A grid is a first-class matter artifact with a dedicated home.** User-facing noun: **"grid"**; the
   cockpit gets a dedicated **"Grids"** tab (sibling to Documents — source files vs derived grids) listing
   the matter's grids (open / rename / soft-delete), matter-owner scoped (cross-matter → 404).

The grid surfaces via a new `data-tabular` stream frame (compact preview with column pills + Expand → the
reused grid) and a transient `data-tabular-cell` frame (live fill, via a `TabularChangeLedger` implementing
`LiveChange`/`ChangeLedger`); these extend the existing data-\* spec and ride this ADR. A cell's source can
be highlighted in the embedded Collabora/WOPI viewer (ADR-F047) via its citation offsets. The cockpit
stage-takeover, the cell side-drawer, and the richer grid affordances (filter/sort/resize/coloring,
LQ-Grid-derived) are design-system slices needing no separate ADR.

## Consequences

**Positive.** No frozen-executor change; one migration buys the whole read/export/render stack. The
crossover needs no magic number — it tracks the budget profile, so dialing economy/balanced/generous moves
it for free. Token and fan-out brakes stay honest (extraction is always a counted model turn within the
quota). Incremental `record_tabular_row` commits mean a token-budget halt leaves a partial-but-persisted
grid (F1-S1 durability). Grounding + finalize gate give honest, provably-complete grids. The capability
toggle confines the tool (R6 fail-closed when off).

**Negative / risks.** Retrieval-fill carries the headline 50-doc use case, so its cell quality **must be
eval-gated** vs fan-out-read before defaulting (ship honest if it trails). Reusing `tabular_executions`
couples the agentic path to the frozen worker — the `mode` scope is mandatory, not optional. In-place
mutation diverges from upstream's immutable history (a forward-only export gives audit). Dev-box OOM keeps
hybrid+rerank-at-scale deferred (FTS-only fast path for dev/eval). Provenance under fan-out relies on
`created_by_run_id` at run level (known blocker #6: `work_product_attributions` assumes one inference per
message). A Commercial matter with both Redlining and Tabular on needs one run-scoped change ledger, not
two.

**Neutral.** Grid virtualization, counterparty sidebar, per-cell tier UI, and source-document highlighting
are LQ-Grid-inspired backlog, out of scope here.

## T2 addendum (2026-07-01) — the preview derives from the settled step, not a new frame

The Decision-outcome paragraph anticipated the grid surfacing "via a new `data-tabular` stream frame".
Implementing T2 surfaced a constraint that makes that frame the wrong primary mechanism: the SSE replay
path (`api/app/api/agent_runs.py:_stream_run_events`) re-emits only settled `data-step` rows — every custom
`data-*` frame (`data-plan`, `data-deal-change`) is **live-only and never survives a reload**. A grid is a
**durable artifact**, so its in-chat preview must re-derive on reload; a live-only frame could not be its
source, and adding one purely for live latency would be a redundant second path (the finalize `data-step`
already arrives live).

**Decision (refines decision 7's surfacing clause; maintainer-confirmed 2026-07-01):** the preview anchors
on the **settled `finalize_tabular_review` step** already in the run timeline — the parent derives the grid
id from that tool call's short `{"grid_id": "<uuid>"}` input (well under the ~2000-char step-summary cap;
unparseable → skipped, never fatal) and renders one `TabularPreview` card per finalized grid, fetching the
body from the existing owner-scoped `GET /tabular/executions/{id}`. **No new stream frame; T2 is
frontend-only** (`web/.../agents/tabular-preview.ts` + `TabularPreview.svelte` + a `ConversationPanel`
render block; the `/tabular/[id]` page is refactored to share `buildDocumentNameById`). The card renders
identically live and on reload (ADR-F004). **Expand** opens the FULL reused `TabularGrid` +
`TabularCitationModal` in an in-conversation overlay (the cockpit "panels slide back" stage-takeover motion
stays T6). The **transient `data-tabular-cell`** frame for live cell fill (T5) is unaffected — it is genuine
animation (ADR-F004), the right use of a live-only frame.

Cosmetic deferred to T6: the cockpit composer floats over the bottom of the conversation, so a tall trailing
grid card sits partly behind it until scrolled (header/status/pills stay clear; Expand unaffected) — a
pre-existing trait of any tall trailing content, addressed by the T6 stage rework.

## T6 addendum (2026-07-02) — grid review WORKSPACE + a human-write cell-override endpoint

Decision 7 called the grid "a first-class matter artifact" and the closing paragraph noted "the cockpit
stage-takeover, the cell side-drawer, and the richer grid affordances … are design-system slices needing no
separate ADR." A maintainer-driven design phase (LQ-Grid reference review + an approved mockup + four locked
`AskUserQuestion` decisions) **reframed** the target: the grid is a review **WORKSPACE**, not an artifact you
pop open in a modal. The UI parts stay design-system slices (no ADR). But T6 adds **one thing this ADR did
not anticipate** and that touches the audit/authz contract, so it is recorded here rather than left implicit.

**What decision 4 said, and where T6 lands it.** Decision 4 made the grid matter-tier
**auto-write-then-correct (ADR-F042)** — "the conversational loop mutates the same grid in place … the
lawyer corrects/undoes/pins." Until now the only cell writer was the **agent** (`record_tabular_row` /
`update_tabular_cells`, T8), each under `guarded_dispatch`. ADR-F042 §B2 is explicit that the *human*
correction is an **authenticated HTTP action, never an agent tool** (pinning mirrors
`matter_memory` corrections). T6 realises that human half.

**Decision (refines decision 4; maintainer-confirmed 2026-07-02):**

1. **A new human-write endpoint** `POST /api/v1/tabular/executions/{execution_id}/cells/override` (set) and
   `DELETE …/cells/override?document_id=&column_name=` (clear/undo — the ADR-F044 human-authenticated-revert
   posture). It is a **human action, not a `guarded_dispatch` tool.** Owner-scoped from the **session**
   `user.id` (cross-user → 404, no existence leak), gated to **`mode=='agentic'`** (404 on a linear row — it
   can never touch the frozen executor, ADR-F001), row-locked (`.with_for_update()`) before the `results`
   read-modify-write, audited **`tabular.cell_overridden` with IDs/counts only** (never the value/note,
   ADR-F005 / 0013 D6). It mirrors `create_matter_correction` field-for-field (`str_strip_whitespace`,
   `extra='forbid'`, response built before `db.commit()`).

2. **The override rides the `results` JSONB — no migration, no new columns.** Four keys are added to a cell
   dict (`override_value`, `override_note`, `overridden_by`, `overridden_at`) and surfaced by adding the same
   four fields to `CellResult` (defaults `None`; existing + agent-written cells validate unchanged). This
   inherits decision 3's "schema-level in `results` JSONB (no new columns)" posture. The **effective display
   value is `override_value ?? value`**; the agent's `value` and citations stay visible underneath.

3. **"The human value wins" is STRUCTURAL, not conventional.** Two guarantees: (a) `overridden_by` comes
   from the authenticated session, never from agent/model input (which is forgeable via prompt/document
   injection); (b) the agent write path (`_upsert_row`/`_apply_cells`) **preserves any `override_*` keys**
   when it rewrites a cell — the agent may refresh the underlying value/citations, but it can neither drop
   nor overwrite the lawyer's override. This is the tabular analogue of `trust='human-pinned'` winning in
   `matter_memory`, and it is covered by an explicit test (override survives a subsequent
   `update_tabular_cells`).

4. **The stage-takeover + docked drawer are design-system slices (no ADR):** the workspace reuses the
   `DocumentEditorPanel` fly-in (the conversation stays a mounted flex child → live SSE survives), and one
   docked `TabularCellDrawer` replaces the stacked `TabularCitationModal` + `ag-grid-overlay`.

**Consequences.** Positive: the lawyer can correct a cell and the correction is durable, attributable, and
un-clobberable by the agent — closing decision 4's human half without a migration and without weakening the
`guarded_dispatch`-only rule for agent writes. Negative/risk: the override lives in JSONB alongside the
agent's value, so any future consumer of `results` must read the effective value via `override_value ??
value` (centralised in one read-side helper + the web `CellResult`); a consumer that ignores it would show
the stale agent value. Neutral: verified/flagged sign-off, a completion meter, semantic colour, the party
column/filter, and deliverables remain later phases (P2–P5); source **highlighting** in the opened document
stays T9 (T6 v1 opens the source file, unhighlighted).

## T4 addendum (2026-07-01) — the bounded row-evidence primitive + the fill-mode crossover

The decision outcome's fan-out engine (T1) filled a grid by having each subagent **read a whole document**
and record its row, and `start_tabular_review` degraded a >quota set to prose advice ("read the most
relevant, retrieve the rest") because "the retrieval-fill path above the quota is T4". A live incident
(2026-07-01) exposed a sharper problem than the >quota case: with retrieval degraded (a keyless gateway
embedder → silent FTS-only on long contracts), the agent **re-searched the same cell forever** — 235
`search_documents`, 0 `record_tabular_row`, to the step cap. The root retrieval fault is fixed elsewhere
(embeddings aligned to local; ADR-F056), but the tabular tool had **no structural defence**: nothing bounded
searches-per-cell.

**Decision (maintainer-chosen, Option B of the T4 plan).** Add ONE guarded tool, `gather_row_evidence(grid_id,
document)`, that runs **exactly one** `matter_search_reranked` per column (scoped to that document) and returns
the grounded passages + chunk ids — **no LLM inside the tool** (retrieval only). The agent still extracts and
`record_tabular_row`s (its own model turn). This keeps the model-driven ethos (a tool the agent *chooses*,
like the native redline engine of ADR-F045 — NOT a Python pipeline that fills JSON slots, which is exactly
what the fork removed) while making thrash **structurally impossible**: the agent gets everything to fill a row
in one call, so re-searching is pointless and the cap lives in code, not the prompt. Considered + rejected:
doctrine-only (soft — the bug is a model ignoring "you already searched this"); a server-side fill engine that
also extracts (a mini linear executor — against the fork thesis).

**Details.** `gather_row_evidence` reuses the SAME embed+hybrid+rerank wiring as `search_documents` via a new
shared `tools.matter_reranked_hits` (`search_documents` refactored onto it, no behaviour change);
`matter_search_reranked` and the frozen E0/Slice-A/-D FTS baselines are untouched. The doctrine routes
gather→record and forbids cell re-search (record `confidence='failed'` when the passages don't answer;
escalate to `read_document` only when clearly thin). Finalize records `fill_mode='retrieval'` above the
fan-out quota else `'fanout'` — a recommendation-based signal (per-row fill provenance is a later refinement);
**no migration** (mig 0082's CHECK already permits `'retrieval'`). Grid load for evidence is read-only (no
`FOR UPDATE` — it never writes `results`), a scope-sharing helper single-sources the matter+owner+agentic
boundary so the two loaders can't drift.

**Consequences.** Positive: a grid can no longer thrash regardless of retrieval quality; the >quota crossover
is a real path, not prose; `gather_row_evidence` is also T5's natural cell-fill seam. Audit carries
counts/ids only (`tabular.row_evidence_gathered`), matter+owner scope is re-asserted (cross-tenant →
404-absence), the grant set stays confined. Neutral/deferred: the **eval gate** (retrieval-fill vs
read-in-full **cell quality** on CUAD, to tune the crossover default) is OOM-sensitive (real embedder) and
runs alone on a throwaway pgvector — until it lands the crossover stays at its current sensible default
(fan-out ≤ quota, retrieval > quota), so nothing regresses. Per-column top-k is fixed (`_EVIDENCE_TOP_K`);
the eval will size it.
