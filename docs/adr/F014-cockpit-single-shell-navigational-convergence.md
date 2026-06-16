# F014 — UX-A: the cockpit as the single app shell (navigational convergence)

- Status: accepted
- Date: 2026-06-15
- Deciders: maintainer (Arturs) — accepted 2026-06-15 ("yes, retire TopTabBar — commit the plan and
  start UX-A-1"; Approach B + the staged decomposition approved, `TopTabBar` retirement in UX-A-5 confirmed)
- Extends: [[F012]] (which split the UX redesign into F2 / UX-A / UX-B and deferred UX-A to its own
  milestone), [[F002]] (practice-areas-and-agent-home — the F3 "promote tools from the cockpit, demote the
  legacy tab IA" commitment), [[F013]] (design-language layer); builds on **F2-VL2** (the cockpit re-skin +
  resizable rail + the `tab.id → Lucide` icon map).
- Supersedes: none

## Context

F012 split the UX redesign by dependency: **F2** (the reversible *visual* pass — done through VL2),
**UX-A** (navigational convergence — "cockpit is the single shell, tools reachable from it, the legacy
top-tab IA retired"), and **UX-B** (capability convergence — "tools as in-context agent capabilities",
which hard-blocks on the pivot schema + activation + F1-S4/S5). F012 deferred UX-A to its own milestone
after the visual pass and required it to carry its own ADR + decomposition. This is that ADR.

After VL2 the maintainer reviewed the re-skinned cockpit and gave the trigger for UX-A:

> "The cockpit works well, but if you click on any of the tools you are not clear how to get back to the
> cockpit. … Those tools should probably live in an expandable part of the side panel in the cockpit and
> everything is then rendered in the cockpit canvas itself."

**Two parallel chromes coexist today** (confirmed in the route map):

- The **cockpit shell** — `/lq-ai/+page.svelte` mounts `cockpit/Cockpit.svelte`, which *itself* owns the
  whole shell: `CockpitHeader` + a resizable `paneforge` rail (`AreaRail`) + a `#cockpit-main` canvas whose
  content it switches by URL state (`areas → matters → matter → unfiled`). On semantic/F013 tokens.
- The **legacy `(tools)` shell** — `/lq-ai/(tools)/+layout.svelte` renders its OWN header + `TopTabBar` +
  `DualBrandingFooter` + a `#lq-main` scroll container, wrapping ~13 tool routes (agents, chats, matters,
  skills, knowledge, playbooks, tabular, saved-prompts, learn, autonomous, admin, settings, trust). Several
  have their own sub-nav layouts (admin, autonomous, settings) and dynamic children (`tabular/[id]`,
  `knowledge/[id]`, `skills/[id]/edit`, `matters/[id]`, `autonomous/sessions/[id]`, `playbook-executions/[id]`).

Opening a tool swaps the entire chrome (cockpit → TopTabBar shell), so the rail, the launcher, and the way
back to the cockpit all vanish — the dead-end the maintainer hit. Two enabling facts make convergence
low-risk: **there are no `load` functions anywhere** under `/lq-ai` (all data is client-side `onMount`
fetch), and **SvelteKit route groups `()` are URL-invisible**, so routes can be reparented without changing
a single URL or breaking a deep link.

This ADR decides the *navigational* convergence only. It does **not** make tools into agent-chosen
capabilities — that is UX-B, still gated on the pivot. Under UX-A a tool stays exactly the tool it is; it is
simply *hosted inside the cockpit shell* instead of a parallel one.

## Considered Options

### A. Embed each tool as a cockpit *view*

The cockpit renders Tabular/Playbooks/… components in its `#cockpit-main` pane, driven by the cockpit's own
URL state. Tool *routes* go away (or redirect).

- Forces all ~13 surfaces' route-level concerns — sub-routes (`tabular/[id]`, admin/autonomous/settings
  sub-navs), dynamic params, per-tool search-params — to collapse into the cockpit's single `?area=&matter=`
  route. Very large, fragile, touches the inside of every tool, hard to stage, hard to reverse, and breaks
  every existing deep link.

### B. Promote the cockpit shell to a shared layout; reparent the tool routes under it *(chosen)*

Extract the cockpit shell (header + resizable rail + canvas slot) out of `Cockpit.svelte` into a shared
SvelteKit layout for a new **URL-invisible route group** (`(app)`). The cockpit *landing* becomes the page
content rendered into the shell's canvas; each tool route is moved into `(app)` so it renders in the same
canvas, with the shell persistent around it. The rail gains an **expandable "Tools" section** (reusing the
VL2 Lucide map). The `(tools)` `TopTabBar` layout and the header Tools dropdown are retired.

- Each tool keeps its route, its client-side data load, its sub-routing and its deep links (groups don't
  change URLs). The shell is a SvelteKit layout, so it does **not** remount across navigation — the rail and
  the way back are always present and tool↔cockpit feels instant. Stageable surface-by-surface; reversible
  at each step. Reuses everything VL2 built.

### C. Keep two shells, just add a clear "back to cockpit" affordance

A band-aid (e.g. make the legacy brand/logo an obvious cockpit link, or add a "← Cockpit" button to the
`(tools)` shell).

- Cheap, but it does not achieve the single-shell vision the maintainer asked for (tools still live in a
  separate chrome). Acceptable only as a throwaway interim if UX-A slips; not the end state.

## Decision Outcome

**Chosen: B.** Make the cockpit the single app shell via a route-group restructure that preserves every URL:

- New `web/src/routes/lq-ai/(app)/+layout.svelte` = the **extracted cockpit shell** — `CockpitHeader` +
  the resizable rail (`AreaRail` + a new expandable **Tools** section) + a `#cockpit-main` canvas that
  renders the layout's `children`/`<slot>`.
- `web/src/routes/lq-ai/(app)/+page.svelte` = the cockpit **landing** — the `areas/matters/matter/unfiled`
  view-switch, now *page content* rendered into the shell canvas (moved out of the old `/lq-ai/+page.svelte`,
  which is deleted; `(app)/+page.svelte` still serves `/lq-ai`).
- The `(tools)` routes (+ `trust`) move into `(app)` so they render in the canvas; the `(tools)`
  `TopTabBar`/footer layout and the header **Tools dropdown** are retired (the rail's Tools section
  replaces both). The root `/lq-ai/+layout.svelte` auth/boot gate and the auth-exempt routes
  (`login`, `change-password`) and internal labs (`_vl-lab`, `_ae-lab`) are **unchanged** and stay
  outside `(app)` (they must not get the shell).

The work is **staged** into a decomposition (`docs/fork/plans/UX-A-navigational-convergence-decomposition.md`),
each slice an independently shippable PR with the full F2/ADR-F005 gate, reversible, deep-links verified.

## Consequences

- **+** One shell. The rail + launcher are always present → no dead-end; tool↔cockpit navigation is instant
  (shared layout, no remount). The fork's "land in the cockpit, reach tools from there" thesis (F002) is
  realised navigationally.
- **+** Deep links and each tool's client-side `load`/sub-routing are unchanged (route groups are
  URL-invisible; no server `load` to migrate). Reuses the VL2 rail, resizable frame, and Lucide tool-icon map.
- **−** The scroll parent changes (`#lq-main` → the cockpit canvas pane); each migrated surface must be
  checked for content that assumed the full-height `(tools)` `#lq-main`. Handled per slice.
- **−** Sub-nav layouts (admin / autonomous / settings) now render *inside* the canvas (nested chrome) —
  acceptable for UX-A; a later pass may fold them into the rail.
- **−** Retiring `TopTabBar` **is** an IA retirement. F012's "no tab/route/surface retired" rule was scoped
  to the *F2 visual pass*; UX-A is precisely the milestone F012 designated to retire the legacy IA, so this
  is consistent, not a contradiction. No tool is removed — every surface stays reachable from the rail.
- **−** Large surface area (~13 routes, several with sub-layouts) → must be staged; a half-migrated state
  (some tools in the shell, some still on `TopTabBar`) is a transitional reality between slices, like the
  `--lq-*` rollout.
- **~** UX-B is untouched: tools remain tools, merely hosted in the cockpit. The capability convergence
  (agent picks/exposes tools) still rides the pivot track (schema + activation + F1-S4/S5).

## Status update — UX-A COMPLETE (2026-06-16)

Shipped in five slices, all merged: UX-A-1 (shell extraction, #80) · UX-A-2 (rail Tools + flat surfaces,
#82) · UX-A-3 (conversation surfaces, #83) · UX-A-4 (sub-nav surfaces, #84) · UX-A-5 (retire the legacy
`(tools)` shell + the header Tools dropdown + sweep). The cockpit is now the single app shell: every
authenticated surface renders in its canvas with the persistent rail; tools are reached only from the
rail's Tools section; `TopTabBar.svelte`, the `(tools)` route group, and the header Tools dropdown are
gone. `visibleTabsFor` moved to `tabs.ts` (the tab vocabulary outlived the top-tab component). Trust stays
reachable via a dedicated header button. The two predicted nested-chrome consequences held as designed
(sub-nav layouts render in-canvas; `matters/[id]` keeps its own `MatterRail` beside the cockpit rail) —
both flagged for a future reconcile/UX-B pass, neither blocking. No tool surface was removed; all
deep-links resolve unchanged.
