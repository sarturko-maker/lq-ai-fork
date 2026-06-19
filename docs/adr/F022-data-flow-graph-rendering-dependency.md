# F022 — Interactive data-flow graph rendering (adopt `@xyflow/svelte`)

- Status: accepted
- Date: 2026-06-19 (accepted 2026-06-19 by the maintainer)
- Extends: ADR-F018 (agentic modules = typed domain + domain UI), ADR-F019 (relational, deployment-global
  ROPA inventory graph), ADR-F013 (F013 design language)
- Milestone: PRIV-6c (Privacy / ROPA module — data-flow / lineage view)

## Context

The Privacy module must render its domain UI like the reference product (Module-UI requirement, 2026-06-18):
a privacy officer should **see** the register, not just download it. PRIV-3…6b shipped the tabular register
+ the programme dashboard. PRIV-6c adds the remaining "SEE the programme" view: the **data-flow / lineage
map** — the OneTrust/TrustArc "data map" — over the relational graph ADR-F019 already stores
(System → Processing Activity → Vendor/Transfer).

The fork carries a standing rule (CLAUDE.md § Code rules): *"New dependencies are SBOM entries and
supply-chain surface — justify each one or don't add it."* Every web feature to date has been built on the
existing shadcn-svelte primitives + Tailwind, with **no charting/graph library**. A node-link graph with
**drag, zoom/pan, fit-to-view and colour-by-kind** is materially harder to hand-roll than a static SVG:
laying out nodes, drawing non-overlapping edges, and handling pan/zoom is a renderer in its own right.

The maintainer was offered three shapes (AskUserQuestion, 2026-06-19): (a) a hand-rolled activity-centric
flow built from CSS/SVG, no dep; (b) hand-rolled layered columns + SVG connectors, no dep; (c) a true
interactive node-link graph via a library, accepting a new dependency. **The maintainer chose (c)** — the
full interactive diagram — consciously authorizing a new dependency for this flagship module surface. This
ADR records that divergence from the no-dep default and pins the specific library + how we contain its
footprint.

## Considered Options

1. **Hand-rolled SVG/CSS, no dependency.** Zero supply-chain surface; fully in our control and F013 style.
   But re-implements a graph renderer: connector geometry is fragile across responsive breakpoints, and
   drag/zoom/pan/fit are non-trivial to build and maintain. Rejected by the maintainer's choice of the
   interactive diagram — and a half-built renderer is worse value than a maintained one.
2. **`@xyflow/svelte` (Svelte Flow), MIT — CHOSEN.** The Svelte-5-native node-link library by the xyflow
   team (makers of React Flow). Gives drag/zoom/pan/fit, custom node + edge components, and a controlled
   layout API out of the box. We render **our own** node components, so the look stays F013 (charcoal +
   scarce accent), never the library's or a vendor's chrome — only the *mechanics* (canvas, transforms,
   handles) are borrowed. Layout positions are computed in **pure, deterministic TS** in our own code, so we
   do **not** also pull a layout engine (dagre/elk) — one dependency, not three.
3. **d3 / `d3-sankey`.** Powerful and well-known, but our shape is a directed node-link graph, not a Sankey;
   building interactive drag/zoom on raw d3 selections is more plumbing than (2) for less fit, and pulls
   several d3-* packages anyway.
4. **`cytoscape`.** A heavy, canvas-first graph engine. Powerful for large graphs, but harder to style to
   F013 (canvas, not DOM nodes), not Svelte-native, and far more surface than a single-client register
   needs.

## Decision Outcome

Adopt **`@xyflow/svelte`** (option 2) as the web's first graph-rendering dependency, scoped to the ROPA
data-flow view, under these containment rules:

- **License gate:** MIT (Apache-2.0-compatible). Verified at install; recorded in `NOTICES.md` (fork-deps)
  with its transitive set. If the resolved version or a transitive dep is not permissively licensed, the
  adoption is blocked and we fall back to option 1.
- **Styling stays ours:** custom Svelte node components keyed on node `kind`; the library supplies the
  canvas/transform/edges only. No vendor/library chrome leaks into the UI (Module-UI requirement; F013).
- **No second dependency for layout:** node positions are computed by a pure `layoutDataFlow(graph)` helper
  in our own code (unit-tested, deterministic) — not dagre/elk.
- **Renderer is swappable:** the data-flow projection is a backend-owned, library-agnostic DTO
  (`DataFlowGraph` — nodes + edges) served by `GET /ropa/data-flow`. Replacing the renderer later touches
  only `DataFlowView.svelte` + `layoutDataFlow`, never the contract.
- **Client-only:** Svelte Flow needs the DOM; the canvas renders behind a browser guard with a text
  fallback under SSR.

## Consequences

- **+1 runtime dependency** (plus its transitive packages) in the `web` bundle — a real supply-chain +
  bundle-size cost, accepted by the maintainer for the flagship interactive data map. Bundle impact is
  contained to the Data flow tab; if it proves heavy, `DataFlowView` is lazy-`import()`-able without
  contract change.
- **Gain:** a maintained, accessible-ish, interactive graph renderer, reusable by future module data maps,
  with our own F013 node styling and our own deterministic layout.
- **Precedent:** this is the fork's first deliberate exception to the no-new-dep default. It is **not** a
  general loosening — the rule still holds; this ADR is the justification record for *this* dependency. A
  future viz dep needs its own justification (its own ADR or an explicit note).
- **Reversible-ish:** the projection DTO + endpoint are lib-agnostic, so a later swap (or a return to a
  hand-rolled view) is a localised web change, not a domain/API change.
