# UX-A — navigational convergence: decomposition

Governed by **ADR-F014** (cockpit as the single app shell). Milestone after the F2 visual pass (which ran
through F2-VL2). Each slice = one PR, ≤2–3 days, independently shippable + screenshot-able, full
ADR-F005/F2 gate (build · `npm run check` · vitest shown · headed before/after screenshots light+dark ×
wide+narrow · fresh-context adversarial+security+simplification review · HANDOFF). Order = dependency →
risk. **Every slice preserves all URLs** (route groups are URL-invisible) and **keeps every surface
reachable** — no tool is removed, only re-hosted. A half-migrated state (some tools in the shell, some
still on `TopTabBar`) is an accepted transitional reality between slices.

## Goal / non-goals

- **Goal:** the cockpit becomes the single app shell. Tools live in an expandable **Tools** section of the
  cockpit rail and render in the cockpit **canvas**; the rail + launcher are always present (no dead-end);
  the legacy `(tools)` `TopTabBar` shell + the header Tools dropdown retire.
- **Non-goal (UX-B):** turning tools into agent-chosen, in-context capabilities. Tools stay tools, just
  hosted in the cockpit. UX-B rides the pivot (schema + activation + F1-S4/S5).
- **Non-goal:** redesigning the inside of any tool surface. UX-A re-hosts; per-surface visual calm is F2-M7b/M8.

## Target route structure (end state)

```
/lq-ai/+layout.svelte              auth/boot gate              — UNCHANGED (wraps everything)
/lq-ai/login, change-password      auth-exempt                 — UNCHANGED (no shell)
/lq-ai/_vl-lab, _ae-lab            internal labs               — UNCHANGED (own viewport)
/lq-ai/(app)/+layout.svelte        the cockpit SHELL           — NEW (header + rail[+Tools] + canvas slot)
/lq-ai/(app)/+page.svelte          cockpit landing view-switch — MOVED from /lq-ai/+page.svelte
/lq-ai/(app)/{agents,chats,matters,skills,knowledge,playbooks,tabular,
              saved-prompts,learn,autonomous,admin,settings,trust,
              playbook-executions}/…                            — MOVED from (tools)/ ; URLs unchanged
```
`(tools)/+layout.svelte` (TopTabBar/footer) is deleted in the final slice; `CockpitHeader`'s Tools dropdown
is removed there too.

## Slices

### UX-A-0 — ADR + decomposition (this)
ADR-F014 + this doc. Docs only, no app code. (The F2-M0 precedent.)

### UX-A-1 — Extract the cockpit shell into the `(app)` layout (pure refactor, no behaviour change)
Split `cockpit/Cockpit.svelte` into **shell** (the new `(app)/+layout.svelte`: `CockpitHeader`, the
resizable rail + drawer + toggle, the responsive state, the `#cockpit-main` canvas rendering `children`)
and **landing** (`(app)/+page.svelte`: the `areas/matters/matter/unfiled` view-switch rendered into the
canvas). Delete `/lq-ai/+page.svelte` (now served by `(app)/+page.svelte` — same URL). No tools moved yet;
the rail is unchanged (areas nav only). **Acceptance: the cockpit looks + behaves identically** (the M1
pixel-equal bar — screenshots match VL2). This isolates the one real refactor before any route moves.
- Watch: the rail's `goto`-based selection stays in the shell; URL state still drives the landing page;
  the paneforge `autoSaveId` + drawer/Escape/scrim still work; `#cockpit-main` keeps the only scroll axis.

### UX-A-2 — Rail "Tools" section + migrate the flat list surfaces
Add an **expandable "Tools" group** to `AreaRail` (collapsible; Lucide icons via the VL2 map; active
highlight from `$page.url.pathname`; legacy group muted, M3). Move the **flat list tools** into `(app)`:
`tabular`, `playbooks`, `saved-prompts`, `learn`, `knowledge`, `skills` (incl. their `new`/`[id]`/`[id]/edit`
children). They now render in the canvas with the rail present. `TopTabBar` still serves the
not-yet-migrated surfaces. **Resolve the scroll-parent change** (`#lq-main` → canvas) for these surfaces.
- Watch: each tool's `onMount` fetch + deep-links (`tabular/[id]` etc.) unaffected; `PageShell` widths still
  fit the canvas; the F2-M7a/M7b calm still renders.

### UX-A-3 — Migrate the conversation surfaces
Move `agents`, `chats`, `matters` (+ `matters/[id]`, `playbook-executions/[id]`) into `(app)`. These are
heavier: `matters/[id]` mounts its own `MatterRail` + `ChatPanel` side-by-side, and `chats` reads
`?id=&project_id=` — verify these compose inside the canvas without a nested-rail clash with the cockpit
rail. **Note the overlap with the cockpit's own matter/conversation views** (the cockpit already renders a
matter conversation) — reconcile or keep both deliberately for this slice; record the call.

### UX-A-4 — Migrate the sub-nav surfaces (admin / autonomous / settings / trust)
Move `admin`, `autonomous`, `settings`, `trust` into `(app)`. Each (except trust) has its own sub-nav
`+layout.svelte` (horizontal/vertical) that now renders *inside* the canvas (nested chrome — accepted for
UX-A). The header gear (→ `settings/appearance`) and the rail/Tools entries keep working. Autonomous stays
opt-in gated.

### UX-A-5 — Retire the legacy shell + sweep
Delete `(tools)/+layout.svelte` (`TopTabBar` + `DualBrandingFooter` placement) and remove the
`CockpitHeader` **Tools dropdown** (the rail's Tools section replaces both). Decide the home for the
trust/branding/footer links the old shell carried (likely the rail footer or the header). Cross-surface
sweep: every surface reachable from the rail, no dead `TopTabBar`/`#lq-main` refs, all deep-links resolve,
no orphaned `--lq-*`. Full screenshot matrix; final HANDOFF.

## Risks / watch-list

- **Scroll container.** `(tools)` relied on `html { overflow-y: hidden }` + a full-height `#lq-main`. The
  cockpit canvas (`#cockpit-main`, inside a paneforge pane) must provide the same single scroll axis for
  migrated surfaces. Per-slice check.
- **Nested rails.** `matters/[id]` (MatterRail) and any tool with its own side panel must not fight the
  cockpit rail. UX-A-3 verifies composition.
- **Sub-nav layouts** (admin/autonomous/settings) render inside the canvas → double chrome depth; acceptable
  now, fold into the rail later if it reads heavy.
- **Redundant nav** during migration: `TopTabBar` + the rail Tools section both exist until UX-A-5. Expected.
- **Reversibility:** each slice is a route move + a chrome wiring change with no server `load` to migrate —
  revertable. Keep moves mechanical; do visual calm in F2-M7b/M8, not here.

## Verification (per slice)

`cd web && npm run check` (0 err) + `npx vitest run`; rebuild the `web` container; headed Cypress
(`DISPLAY=:0`, electron) of the touched surfaces with before/after screenshots (light+dark × wide+narrow)
+ **explicit deep-link checks** (visit each migrated tool's URL directly and a `[id]` child) copied to
`docs/fork/evidence/<slice>/`; fresh-context adversarial+security+simplification review; HANDOFF updated.
Merge per ADR-F005 against `sarturko-maker/lq-ai-fork`.
