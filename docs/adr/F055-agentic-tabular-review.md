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
