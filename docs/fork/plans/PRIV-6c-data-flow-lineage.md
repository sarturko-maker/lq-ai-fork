# PRIV-6c — Data-flow / lineage view (plan)

**Status:** proposed (maintainer edits this before implementation — CLAUDE.md § Iteration).
**Milestone:** Oscar Edition / Agentic Modules → Module 1 (Privacy/ROPA).
**ADRs:** implements ADR-F018 (module = typed domain + code-owned truth) + ADR-F019 (deployment-global,
shared-read register). **New ADR-F022 (proposed)** — adopt an interactive graph-rendering dependency
(`@xyflow/svelte`), a conscious divergence from the fork's no-new-dep default (maintainer chose the full
interactive node-link diagram over a hand-rolled SVG view; AskUserQuestion, 2026-06-19).
**Slice size:** read API + web + 1 new web dep, **no migration**. One PR.

## Context

PRIV-6a closed the full Article 30(1) content set; PRIV-6b added the read-only **programme dashboard**
(Overview tab — totals/breakdowns/gaps). PRIV-6 bundled three "SEE the programme" features; 6b shipped the
dashboard, leaving **6c (data-flow / lineage view)** and **6d (Legal-Entity / controller scope — needs a
migration)**. This slice is 6c: render the register's relationships as a **data map** — the
OneTrust/TrustArc "data flow / lineage" concept (IA borrowed, **look ours**: F013 charcoal + scarce
accent, not Oscar/OneTrust chrome — Module-UI requirement, 2026-06-18).

The register is already a graph in the schema:
- `ProcessingActivity.systems` (M:N) — **where** the data lives feeds **what** processes it.
- `ProcessingActivity.vendors` (M:N) — the activity **discloses to** recipients (Art 30(1)(e)).
- `ProcessingActivity.transfers` (1:N; each a `destination` country + `restricted`/`mechanism` + optional
  recipient vendor) — the activity **transfers to** a third country (Art 30(1)(e), Chapter V).

So the lineage flows left→right: **Systems → Activities → Recipients & Destinations**.

## Goal

A read-only **interactive node-link data-flow graph** auto-drawn from the
System→Activity→Vendor/Transfer relationships: draggable nodes, zoom/pan, colour-by-kind, restricted
transfers visually flagged. Surfaced as a **"Data flow" tab** of the ROPA surface (second, after Overview).
The agent maintains the register; the user reads/explores it (system proposes, user owns) — the graph
*informs*, it never edits.

## Non-goals (explicit — keep the slice small)

- **No writes / edits / remediation** — read-only; the agent writes the register, this renders it.
- **No Legal-Entity / controller entity** — that is 6d (needs a migration). No migration here.
- **No new domain fields** — pure projection over what PRIV-1…6a already store.
- **No auto-layout dependency** (dagre/elk) — layout is computed in **pure, deterministic TS** (testable);
  the only new dep is the renderer (`@xyflow/svelte`). One dep, not three.
- **No free-text on the wire** — nodes carry **names** (labels — already exposed by every register tab)
  + **categorical badges** (system_type / lawful_basis / vendor_role / dpa_status / restricted /
  mechanism — also already exposed). No `purpose`/`retention`/`description`/transfer `details`. So the
  shared-read posture (ADR-F019) and the private→shared confused-deputy backlog item are **not heightened**
  (same exposure as the existing register tables).
- **No time-series / history** (`updated_at` has no `onupdate` — carried deferral).

## Approach

Same shape as PRIV-6b (load rows → pure builder → typed DTO → endpoint; web renders), so the projection
is server-owned + unit-tested, and the web stays presentation.

### Backend — pure projector (mirrors `ropa_summary` / `ropa_export`)

1. **`app/ropa_graph.py`** (new, pure) — `build_graph(activities, systems, vendors) -> DataFlowGraph` over
   the `*Read` DTOs (the data the export/summary already assemble). No I/O → unit-tested in isolation.
   - **Nodes** (deterministic order: systems → activities → recipients → destinations, each in the
     register's canonical `created_at,name` order; destinations in first-seen order):
     - `system` — `id="system:{uuid}"`, `label=name`, `system_type`, `ai_usage`.
     - `activity` — `id="activity:{uuid}"`, `label=name`, `lawful_basis`, `controller_role`,
       `special_category`.
     - `recipient` — `id="recipient:{uuid}"`, `label=name`, `vendor_role`, `dpa_status`.
     - `destination` — one per **distinct** transfer `destination` string, `id="destination:{name}"`,
       `label=name`. (Free-text country strings dedupe by exact value — honest: no silent "USA"≡"United
       States" merge.)
   - **Edges** (directed = data-flow direction):
     - `processed_by`: `system → activity`, one per `a.systems` link.
     - `disclosed_to`: `activity → recipient`, one per `a.vendors` link.
     - `transferred_to`: `activity → destination`, one per `a.transfers`, carrying `restricted`,
       `mechanism`, and `recipient` (the transfer's vendor name, or `None`).
   - **Orphans** (a system/vendor with no activity link) appear as nodes with **no edges** — the graph is
     honest about unconnected inventory; the web can cluster them.
2. **`app/schemas/ropa.py`** — new read DTOs (built directly, not `from_attributes`):
   - `DataFlowNode { id, kind, label: str; system_type, lawful_basis, controller_role, vendor_role,
     dpa_status: str|None; ai_usage, special_category: bool|None }` (optional badge fields; only the
     kind-relevant ones populated).
   - `DataFlowEdge { source, target, kind: str; restricted: bool|None; mechanism, recipient: str|None }`.
   - `DataFlowGraph { nodes: list[DataFlowNode]; edges: list[DataFlowEdge] }`.
3. **`app/api/ropa.py`** — `GET /ropa/data-flow` (response_model `DataFlowGraph`). Reuses the existing
   **`_load_register(db)`** helper (discards the two taxonomy lists, like `programme-summary`), then
   `ropa_graph.build_graph(...)` over the 3 `*Read` lists. Rides the router's `dependencies=_active` mount
   → **shared-read** (ADR-F019); 404 only for a genuinely missing id (n/a — this endpoint takes no id).

### Web — interactive graph (ADR-F022)

4. **Dependency:** add **`@xyflow/svelte`** (Svelte-5-native node-link renderer, **MIT**). We supply our own
   node components so the look stays F013 (not vendor chrome). Verify exact version + license + transitive
   set at install; record in **NOTICES.md** (fork-deps) + ADR-F022.
5. **`lib/lq-ai/components/ropa/dataFlow.ts`** (new, **pure**) — `layoutDataFlow(graph): { nodes, edges,
   isEmpty }`: assigns a column by kind (system=0, activity=1, recipient/destination=2), y by within-column
   index, and maps to Svelte Flow `Node`/`Edge` shapes (id, `position{x,y}`, `data`, `type=kind`; edge id
   `"{source}->{target}:{kind}"`, restricted transfers flagged for styling). Deterministic → **vitest**.
6. **`lib/lq-ai/api/ropa.ts`** — `DataFlowNode`/`DataFlowEdge`/`DataFlowGraph` types + `getDataFlow()`.
7. **`components/ropa/DataFlowView.svelte`** (new) — wraps `<SvelteFlow>` (+ `Background`, `Controls` for
   zoom/pan/fit) with **one custom node component** keyed on `data.kind` (charcoal card, kind-coloured
   accent, the categorical badge, special-category/restricted flags) + a **legend**. Calm empty state when
   the graph has no nodes (no canvas). Root `data-testid="lq-ropa-dataflow"`. **SSR guard:** Svelte Flow is
   client-only — render the canvas behind `{#if browser}` (the register already loads on `onMount`, so this
   is consistent), falling back to the empty/loading text under SSR.
8. **`components/ropa/format.ts`** — `RegisterTab` gains `'data-flow'`; `REGISTER_TABS` gains
   `{ id:'data-flow', label:'Data flow' }` at **index 1** (after Overview — both are programme-level views).
   `components/ropa/format.test.ts` updated (tab list).
9. **`components/ropa/RopaRegister.svelte`** — import `getDataFlow`/`DataFlowGraph`/`DataFlowView`; `graph`
   state fetched in the unified `Promise.all`; new `{:else if tab === 'data-flow'}{#if graph}<DataFlowView
   {graph} />{/if}` branch.

## Files

- **api (new):** `app/ropa_graph.py`; tests `tests/test_ropa_graph.py` (pure builder) + data-flow cases in
  `tests/test_ropa_read.py`.
- **api (edit):** `app/schemas/ropa.py` (3 DTOs); `app/api/ropa.py` (`GET /ropa/data-flow`); **global
  contract tests** `tests/test_endpoints.py` (`IMPLEMENTED_ROUTES` += route) + `tests/test_openapi.py`
  (`EXPECTED_PATHS` += path; **route count 139 → 140**) — the PRIV-3 lesson.
- **web (new):** `components/ropa/DataFlowView.svelte`; `components/ropa/dataFlow.ts` + `dataFlow.test.ts`.
- **web (edit):** `package.json` (+`@xyflow/svelte`); `api/ropa.ts`; `components/ropa/RopaRegister.svelte`;
  `components/ropa/format.ts` + `format.test.ts`.
- **docs (new/edit):** `docs/adr/F022-*.md` (proposed); `NOTICES.md` (fork-deps entry); `HANDOFF.md` +
  `MILESTONES.md` (PRIV line) + this plan.

## Verification (DoD — shown, not asserted)

- **api:** `ruff format --check && ruff check` (repo root) + mypy clean; FULL containerized `pytest -q`
  (count quoted, +N over 2283). New tests: pure builder over a known fixture (every node kind + edge kind,
  dedup, orphans, transfer restricted/mechanism/recipient, deterministic order), empty register → empty
  graph, data-flow endpoint (200 active / 401 no-auth, spot-check node/edge), route + OpenAPI contracts.
- **web:** `npm run check` (0 err) + vitest (count quoted; +N for `dataFlow.test.ts` + format tab); rebuild
  the `web` container; **headed Cypress** of the Data flow tab (light+dark × wide+narrow) →
  `docs/fork/evidence/priv-6c/`.
- **live:** dev stack (no migration → rebuild `web` only). The seeded "Programme — GDPR / ROPA" register
  renders as a graph (systems→activities→recipients/destinations, restricted transfer flagged); empty
  state honest; `GET /ropa/data-flow` returns the real projection + 401 unauth. Screenshot.
- **review:** fresh-context adversarial + **security + simplification** pass: no secrets; read-only;
  labels+categorical only (no free-text leak — confirm `purpose`/`retention`/`details`/`description` are
  NOT on the wire); projection matches the register; SSR-safe; no `--lq-*` tokens; F013 only (Oscar/OneTrust
  look NOT copied); the new dep's license is permissive (MIT) + recorded; `_load_register` reuse doesn't
  change export/summary behavior.
- **ADR-F022** drafted (proposed); **HANDOFF.md** updated; **MILESTONES** PRIV line updated (6b ✅ → 6c ✅
  → 6d remaining). Merge per ADR-F005 against `sarturko-maker/lq-ai-fork`.

## Risks / notes

- **New dependency** is the headline risk — recorded in ADR-F022 + NOTICES; chosen lib is MIT + Svelte-5
  native + lets us keep F013 styling (custom nodes). Layout is pure code (no dagre/elk) → one dep only.
- **Bundle size:** Svelte Flow + its CSS adds weight; the canvas renders only on the Data flow tab. If it
  bloats the bundle materially, lazy-`import()` `DataFlowView` (the projector/endpoint are lib-agnostic, so
  the renderer is swappable without touching the contract).
- **SSR:** Svelte Flow is client-only — guard with `{#if browser}` / dynamic import; falls back to text.
- **Contract-test churn** (route count + OpenAPI path) — covered above.
- **Efficiency:** projecting over loaded rows (vs SQL) is fine at register scale (deployment-global, one
  client) and mirrors export/summary; swap internals to SQL later without changing the DTO/endpoint.
- **Destination dedup** is by exact string (honest — no silent country-name normalisation).
