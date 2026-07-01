# Plan — F2 Tabular T4: retrieval-fill + the crossover switch (ADR-F055)

**Status:** ACCEPTED design (maintainer chose **Option B — bounded row-evidence tool**, 2026-07-01). **Branch:**
`fork/f2-tabular-t4-retrieval-fill`. **Depends on:** the 2026-07-01 retrieval fix (embeddings aligned to
`local`, matters re-embedded) — semantic search now works, so this slice is about the *structural* guarantee
and the >quota path, not fire-fighting a live thrash.

## Context (what changed the framing)

T4 was scoped as "the retrieval-fill engine + crossover switch" to handle matters with **more documents than
the subagent fan-out quota**. Investigating the "600-step run that killed the box" reframed it:

- The acute thrash (235 `search_documents`, 0 `record_tabular_row`) was **broken retrieval**, not a missing
  engine — the query embedded via a keyless gateway → silent FTS-only → thin hits → the agent re-worded and
  re-searched the same cell forever. **That root cause is already fixed** (`embedding-provider-mismatch`);
  the very next live run did NOT thrash (1 search, clean 4-way fan-out — it OOM'd instead, now contained by
  the PR #186 mem limits).
- But **nothing structurally prevents** a re-search loop: there is no per-cell / per-query search budget
  anywhere (confirmed). On a matter with genuinely poor retrieval (a scanned PDF, an out-of-domain doc), the
  agent can still loop to the step cap. T4 must make thrash *impossible*, not just *unlikely*.
- And the >quota regime (docs > `fan_out_quota`) is still only **prose advice**; `fill_mode` is hardcoded
  `"fanout"` on finalize (`tabular_tool.py:483` "T4 adds retrieval").

So T4 = (1) a **bounded retrieval primitive** so filling a row can't loop, (2) a real **retrieval-fill path**
for the >quota crossover, routed by `start_tabular_review`, and (3) an **eval gate** that sets the crossover
default on measured cell quality (retrieval-fill vs read-in-full).

## The design fork (needs your call — three options)

The tension: the fork thesis is model-driven tool calls, NOT Python-walks-a-pipeline (CLAUDE.md; we replaced
upstream's linear tabular executor deliberately). So how much of the fill do we hand to code vs the model?

**Option A — Doctrine only (prompt).** Rewrite `TABULAR_FILL_DOCTRINE`: add a per-cell search discipline
("search a cell at most twice; if still thin, record `confidence='low'`/`'failed'` and move on — never
re-search a cell you've already searched") + a retrieval-fill routine above the crossover. *Pros:* zero infra,
purest model-driven, cheapest slice. *Cons:* **soft** — a guarantee that depends on prompt compliance is not
a guarantee; the failure we're fixing is exactly a model ignoring "you already searched this."

**Option B — A bounded row-evidence TOOL (RECOMMENDED).** Add one guarded tool,
`gather_row_evidence(grid_id, document)`: for each column's query it runs **one** `matter_search_reranked`
scoped to that document (hard cap, no loop, **no LLM inside the tool** — retrieval only) and returns the top
grounded passages per column. The agent (or fan-out subagent) then extracts values and calls
`record_tabular_row` — its own model turn, as today. *Why it kills thrash:* the agent gets everything it needs
to fill a row in **one** call, so re-searching is pointless; the cap lives in code, not the prompt. *Why it's
not a pipeline:* the model still CHOOSES to call it and still does the extraction reasoning — like the native
redline engine exposed as a tool (ADR-F045). Works for BOTH regimes: a fan-out subagent calls it for its doc;
the >quota retrieval-fill has one subagent call it across a slice of docs. It's also the natural unit for T5
(live cell fill). *Cons:* one more tool in the grant set; a fixed per-column top-k.

**Option C — Server-side fill engine.** A tool that loops (doc × column) server-side, calls the LLM to extract
each cell, records the row — fully deterministic, bulletproof. *Cons:* this is a mini linear executor with the
model filling JSON slots — the exact pattern the fork removed. Rejected unless you want it; presented for
completeness.

**Recommendation: Option B**, plus a *belt-and-braces* lightweight progress note in the doctrine (not a hard
brake). It gives the structural no-thrash guarantee, fits the model-driven ethos and existing tool precedents,
cleanly enables the crossover, and sets up T5. A hard "searches-between-records" run brake is noted as
**backlog** (it has tool-scoping problems — `search_documents` is general-purpose — and Option B removes the
*reason* to thrash, so the brake is redundant belt).

## Goals
1. **No-thrash guarantee** for grid fill (Option B: a bounded, LLM-free `gather_row_evidence` retrieval tool
   with a hard per-column search cap).
2. **Retrieval-fill crossover**: above `fan_out_quota` docs, `start_tabular_review` recommends the
   retrieval-fill routine (one subagent per row-slice using `gather_row_evidence`), and finalize records
   `fill_mode='retrieval'`; at/below quota, fan-out-read as today (`fill_mode='fanout'`).
3. **Eval gate**: a Track-B/agentic arm comparing retrieval-fill vs read-in-full **cell quality** on CUAD
   fixtures; freeze the finding; set the crossover default on evidence (ADR-F015-style; never tighter than CI).
4. Correct `fill_mode` persisted (no migration — 0082 CHECK already permits `'fanout'|'retrieval'`).

## Non-goals
- **No migration / no schema change** (`fill_mode='retrieval'` already valid; `results` JSONB shape unchanged).
- **No change to `matter_hybrid_search` / the FTS-only fast path** — `gather_row_evidence` calls
  `matter_search_reranked` (the existing query path), so the frozen E0/Slice-A/-D baselines +
  `_REFERENCE_FTS` guard stay byte-identical.
- **No global search brake** (R-series) — backlog; Option B makes it redundant.
- **No F056 work** (per-matter embedding provider — separate slice, sequenced after this).
- **No T5** (live cell-fill animation) — but build `gather_row_evidence` as its natural seam.
- No KB/chat path change; no rerank default change (stays `settings.rerank_enabled`, off on the dev box).

## Implementation (Option B)

### A. `gather_row_evidence` tool — `api/app/agents/tabular_tool.py`
- Add to `TABULAR_TOOL_NAMES` + `build_tabular_tools`. Signature `gather_row_evidence(grid_id: str,
  document: str) -> str`, guarded via `guarded_dispatch` (same `ctx`/grant confinement as the other grid
  tools; matter+owner re-asserted through `binding`).
- Impl `_gather_row_evidence`: load the grid (matter-scoped, NOT for-update — read only), resolve the document
  (reuse `_resolve_one_document`), verify it is one of the grid's docs; then for each column run **one**
  `matter_search_reranked(..., document_id=doc_id, top_k=_EVIDENCE_TOP_K, alpha=..., reranker=...)` (mirror
  `tools._search`'s embed + FTS-fallback + reranker wiring; **one** search per column, no loop). Return a
  compact per-column block: column name → top passages (verbatim text + `chunk_id` for `cited_chunk_ids`).
  No LLM call. Audit `tabular.row_evidence_gathered` (counts/ids only).
- Constants: `_EVIDENCE_TOP_K` (~4), reuse `_HYBRID_ALPHA` from `tools.py`. Cap total returned chars so a
  wide grid can't blow the subagent's context.

### B. Doctrine — `api/app/agents/composition.py` (`TABULAR_FILL_DOCTRINE`)
- Fan-out path (≤ quota): "each subagent calls `gather_row_evidence(grid_id, its_doc)` ONCE, extracts the
  columns from the returned passages, and calls `record_tabular_row` — do not re-search a cell; if a column's
  passages don't answer it, record `confidence='failed'`."
- Retrieval-fill path (> quota): "fan out ≤ quota subagents, each owning a SLICE of the documents; each
  subagent loops its docs calling `gather_row_evidence` + `record_tabular_row` per doc." Keep it prose-routed;
  the tool guarantees the bound.

### C. Crossover + `fill_mode` — `api/app/agents/tabular_tool.py`
- `_start_tabular_review`: keep the `n_docs <= fan_out_quota` decision; reword both strategies around
  `gather_row_evidence`; return the recommendation (already does).
- `_finalize_tabular_review`: set `execution.fill_mode` from how it was filled. Simplest honest signal:
  `'retrieval'` when `n_docs > fan_out_quota` else `'fanout'` (the recommended path). (A precise
  per-row provenance is possible later; the recommendation-based flag matches the plan's intent and needs no
  new state.)

### D. Eval arm — `api/tests/agents/scenarios/cuad_eval.py` (+ a small agentic-quality harness)
- Add a **cell-quality** comparison on CUAD fixtures: for a set of (contract, column=CUAD category) cells,
  score (i) **retrieval-fill** = `gather_row_evidence`'s passages → does the gold span fall in the returned
  passages (a hit\@evidence, reuse `any_hit_at_k` / `precision_at_k` over the returned passage spans); vs (ii)
  **read-in-full** = the whole-doc read path (the fan-out baseline: gold always present, upper bound). Report
  the gap. This measures whether bounded retrieval surfaces the answer as reliably as reading the doc.
- Real embedder + FTS/hybrid on a **throwaway pgvector**, run **alone** (dev-box OOM trap); rerank behind
  `settings.rerank_enabled`. Freeze under `docs/fork/evidence/tabular-review/T4-retrieval-fill/`. Pre-register
  the crossover default rule from the finding.
- CI stays hermetic: a deterministic fake-embedder arm over the synthetic corpus (the Slice-D pattern).

### E. Tests
- `test_tabular_tool.py`: `gather_row_evidence` — matter/owner scope (cross-user/cross-matter → the
  404-conflated absence), doc-not-in-grid rejection, one-search-per-column (assert call count — the no-thrash
  guarantee), returns passages + chunk_ids, unknown/edge inputs. Grant confinement (`TABULAR_TOOL_NAMES`).
- `test_endpoints.py`/`test_openapi.py`: unaffected (no new HTTP route — it's an agent tool, not an endpoint).
- `_finalize_tabular_review`: `fill_mode` reflects the crossover; the no-toggle/≤quota path is byte-identical
  to today (regression guard).

## Critical files
- `api/app/agents/tabular_tool.py` (new tool + `_gather_row_evidence` + `fill_mode` on finalize;
  `TABULAR_TOOL_NAMES`).
- `api/app/agents/composition.py` (`TABULAR_FILL_DOCTRINE`).
- `api/tests/agents/test_tabular_tool.py`; `api/tests/agents/scenarios/cuad_eval.py` (+ evidence dir).
- Docs: ADR-F055 **T4 addendum**; this plan; `MILESTONES.md`; `HANDOFF.md`; memory.
- Reuse (unchanged): `api/app/knowledge/retrieval.py` (`matter_search_reranked`), `api/app/agents/tools.py`
  (`_embed_query`, `_HYBRID_ALPHA`, `MatterBinding`), `api/app/agents/budget.py` (`fan_out_quota`).

## Verification / DoD (ADR-F005 gate)
- Deterministic (dev image, repo root + `skills→/skills:ro`, `--network lq-ai_default`, `DATABASE_URL` by
  NAME): the new tabular-tool tests + full `tests/agents` counts quoted; CI `ruff`/`mypy` clean; frozen
  retrieval baselines byte-identical (the FTS fast path is untouched).
- Live (dev stack, matter `20ce20fb`): a multi-doc grid build — assert the run records rows without a
  search loop (step trace: `gather_row_evidence` + `record_tabular_row` per doc, no 100+ `search_documents`),
  and a forced >quota case takes the retrieval-fill path (`fill_mode='retrieval'`). Screenshot/step-trace in
  evidence.
- Eval finding frozen; crossover default set from it.
- Fresh-context adversarial review incl. the mandatory security + simplification pass: matter/owner scope on
  the new tool (cross-tenant → 404-absence), grant confinement, no cell content in audit, no user input in
  SQL, no stray files, dead-code/dup sweep.
- ADR-F055 T4 addendum; HANDOFF + memory updated; merge under the full ADR-F005 gate (`gh … --repo
  sarturko-maker/lq-ai-fork`; branch+PR; commit trailer).

## Risks / gotchas
- **Ethos**: keep the tool LLM-free (retrieval only) so it's a primitive the model USES, not a pipeline that
  replaces the model. If we ever put extraction inside it, that's Option C — a different ADR call.
- **Per-column top-k**: too small misses the answer (hurts quality), too large bloats subagent context — the
  eval sets it.
- **Byte-identical guard**: `gather_row_evidence` must call the existing `matter_search_reranked` unchanged.
- **Dev-box OOM**: the eval runs the real embedder — run it ALONE at small N; CI uses the fake.
- **fill_mode honesty**: the recommendation-based flag is a coarse signal; note it in the ADR (precise
  per-row fill provenance is a later refinement, not this slice).

## Recommended order
`gather_row_evidence` tool + tests → doctrine rewrite → `fill_mode` on finalize → eval arm + N-small
calibration (freeze, set crossover default) → live verification on `20ce20fb` → ADR-F055 T4 addendum +
HANDOFF/memory → adversarial review → PR + merge.
