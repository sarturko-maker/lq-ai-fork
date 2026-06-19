# PRIV-6e — Geographic cross-border transfer map

**Status:** PLAN for maintainer edit. **Date:** 2026-06-19. Governing: ADR-F018/F019 (agentic modules,
relational deployment-global ROPA), ADR-F022 (data-flow rendering-dependency precedent). Sibling of the
node-link **data-flow** view shipped in PRIV-6c. Competitive grounding: the 2026-06-19 research runs (see
`PRIV-onetrust-to-lqai-functionality-map.md` § Update 2026-06-19).

## Why

Both OneTrust and TrustArc ship **two** register visualizations — a node-link graph/lineage view **and** a
**geographic map**. We shipped the node-link one (PRIV-6c, `@xyflow/svelte`); we do **not** have the
geographic one. So the geographic transfer map is a real, specific gap.

**The opening:** the research could not confirm that either incumbent's geographic map shows the **legal
transfer mechanism** inline — both appear to be "by hosting location" plots with per-country counters/pins.
We can beat that on legal substance, not just visuals: a map where clicking a cross-border arc surfaces the
Chapter V safeguard (SCCs / adequacy / UK IDTA / BCR / derogation) and **visually flags any `restricted`
transfer that is missing a mechanism** — an invariant we already enforce in the data (PRIV-5b).

## What we already have (so this is a rendering slice, not a data-model change)

- The `transfer` entity (PRIV-5b) carries everything an arc needs: `destination` (country string),
  `restricted`, `mechanism`, optional recipient `vendor`, parent activity.
- The graph projector (`api/app/ropa_graph.py`, PRIV-6c) already emits `transferred_to` edges with
  `restricted` / `mechanism` / `recipient` — the geographic view can reuse the same loaded register.
- `GET /ropa/data-flow` already exists; the new view can either reuse it or add a sibling
  `GET /ropa/transfer-map` projection (decision below).

## The one real prerequisite — destination is free-text

`transfer.destination` is a **free-text country string** today ("US", "United States", "USA" all possible).
Reliable geo-plotting needs a stable mapping to ISO-3166 country codes / coordinates. Options (pick in the
slice):

- **(A) Controlled country vocabulary at the write boundary** — validate `destination` against an ISO-3166
  country list in `TransferInput` (reject-don't-sanitize, the ADR-F018 pattern). Cleanest long-term; a small
  migration is NOT needed (validation only), but it tightens an existing field so **existing dev rows may
  need normalising**. Best correctness.
- **(B) Server-side geocode lookup at projection time** — keep the free-text column, map name→ISO+centroid
  in a static lookup table inside the new projector; unmapped strings render in an honest "unmapped" list,
  never silently dropped. No write-path change; least invasive. **Recommended first step** (additive, no
  data migration), with (A) as a follow-up hardening once the vocabulary is settled.

Either way: **never silently drop an unmappable destination** — surface it (an "unmapped destinations" note
beside the map), mirroring PRIV-6c's honest orphan-node treatment.

## New dependency — needs the ADR-F022 treatment

A geographic arc map needs a viz library. **Recommendation: Apache ECharts** (Apache-2.0; native animated
geo arcs via `geo` + `lines`/`effectScatter`; **no WebGL**; tree-shakeable; maintained Svelte-5 wrapper
`bherbruck/svelte-echarts`, MIT; and it also does Sankey natively if we ever want a volume-flow view).
Runner-up: **d3-geo** (ISC, ~20 KB, ultra-light, fully on-brand, hand-rolled arcs — we already have d3
transitively via xyflow). **Disqualified: amCharts** (proprietary "linkware" — forces a visible logo unless
licensed; fails OSI even though it's on GitHub). Full shortlist + licenses in the functionality-map update.

This is a deliberate **new-dep exception** exactly like `@xyflow/svelte` in PRIV-6c → **draft ADR-F0xx**
(new-dep justification + NOTICES.md entry + license confirmation) in the same PR, per CLAUDE.md
"new dependencies are SBOM entries… justify each one." If we pick d3-geo we lean on existing transitive d3
and the ADR is lighter (still record it).

## Decisions to ratify in the plan/ADR

1. **Library:** ECharts (dual-purpose, no WebGL, sleek defaults) vs d3-geo (lean, on-brand, more dev time).
   Lead recommendation: **ECharts** unless we want zero new top-level deps.
2. **Destination resolution:** (B) projection-time geocode lookup first (additive), (A) controlled
   vocabulary as a follow-up. Lead recommendation: **(B) then (A)**.
3. **Endpoint:** reuse `GET /ropa/data-flow` (already carries transfer edges) vs add a dedicated
   `GET /ropa/transfer-map` that emits `{from_iso, to_iso, restricted, mechanism, recipient, count}` arc
   records. Lead recommendation: **dedicated projection** — the geo view wants arcs aggregated by
   country-pair with a `restricted`/mechanism rollup, which differs from the node-link shape; keep
   `ropa_graph.py` clean and add `ropa_transfer_map.py` (pure projector, same `_load_register` load path,
   unit-tested in isolation, mirroring the established pattern).
4. **Wire posture (ADR-F019):** labels + categorical badges only — country names, ISO codes, `restricted`,
   `mechanism`, recipient **name**; **no free-text** `details`/`purpose`/`retention` crosses the wire (a
   pure test asserts it, as PRIV-6c did). Shared-read; no confused-deputy heightening.

## Slice shape (one PR, ≤2–3 days, full DoD)

- **Backend:** `app/ropa_transfer_map.py` pure projector → `TransferMapArc`/`TransferMapResponse` DTOs;
  destination→ISO geocode lookup (static table, honest "unmapped" list); `GET /ropa/transfer-map`
  (shared-read `_active`, rides `_load_register`); route-count contract tests
  (`test_endpoints.py` + `test_openapi.py`) updated; wire-level free-text-leak guard test; pure projector
  unit tests (arc aggregation, restricted-without-mechanism flag, unmapped surfacing, orphan/empty states).
- **Web:** new dep + ADR + NOTICES; `TransferMapView.svelte` (browser-guarded canvas; charcoal/scarce-blue
  per F013; animated arcs styled by `restricted`; click arc → mechanism + recipient popover; restricted-
  without-mechanism rendered as an alert; honest empty + "unmapped destinations" states); a **"Transfer
  map"** register tab beside "Data flow"; fetched in the unified `Promise.all`; vitest for any pure helper
  (e.g. `destinationToIso`, arc-aggregation if done client-side).
- **Verify:** ruff+mypy; full api suite with counts; web `npm run check` 0 err + vitest; **LIVE on dev
  stack** (seed a couple of cross-border transfers — one restricted+SCCs, one adequacy, one restricted-
  *without*-mechanism to prove the alert) → headed Cypress screenshots light/dark × wide/narrow into
  `docs/fork/evidence/priv-6e/`; fresh-context adversarial+security+simplification review; HANDOFF updated.

## Non-goals (this slice)

Volume-weighted Sankey (possible later with the same ECharts dep); a 3D globe (globe.gl is a marketing-hero
look, not an in-product compliance panel); editing transfers from the map (the agent remains the sole
audited writer — ADR-F019; the map is read-only like the rest of the register UI).
