# PRIV-9a — watch the agent change the register (co-visible + run-lock + live-refresh)

**Date:** 2026-06-19 · **Milestone:** PRIV-9a · **Plan:** `docs/fork/plans/PRIV-9-cockpit-live-register.md`
· **ADRs touched:** none new (sits inside ADR-F019 register-in-a-Privacy-matter + ADR-F004 settled-decides +
ADR-F009 cancel). Frontend-only; no schema, no migration.

## Headline

The group-chat thesis is now *watchable*. In a Privacy matter the conversation and the deployment-global
**ROPA register sit side by side**; while the agent works the composer **locks to a single Stop button**; and
the register **re-reads live** so the agent's writes appear as they land. The hero capture
(`priv-9a-live-row-appeared.png`) shows all three at once: the prompt *"We moved off Mixpanel — use Hotjar
now."*, the composer collapsed to **"The agent is working… [Stop]"**, and **"PRIV-9a live row" appearing in the
register's Processing-activities table** above the pre-existing row — mid-run.

## What shipped

- **Co-visible** (`ConversationHost.svelte`): a resizable `Resizable.PaneGroup` (chat | register) for Privacy
  matters when the panel clears the width budget (`hostWidth − 288 ≥ 880`); below that, the one-at-a-time
  toggle is the fallback — but the conversation **stays mounted (hidden)** there so it still live-updates.
- **Run-lock** (`ConversationPanel.svelte`): while the agent works the input/matter-select/attach are
  **removed from the DOM** (not just disabled) and replaced by a single **Stop** control that calls the *real*
  backend cancel (`POST /agents/runs/{id}/cancel`, ADR-F009) and re-syncs by polling to the settled
  `cancelled` row (ADR-F004 — the polled row decides, never an optimistic local mutation). New
  `agentsApi.cancelRun` + the pure `agentWorking` / `cancellableRunId` helpers.
- **Live-refresh** (`RopaRegister.svelte`): a quiet `reload()` (keeps rows on screen — never the skeleton)
  driven by a self-rescheduling 2 s poll gated on `runActive` (a `pollGeneration` guard keeps it to one
  loop), plus one reconcile fetch on settle (host bumps `reloadKey`). Read-only throughout (ADR-F019) — the
  register UI only ever GETs.

## Evidence (deterministic, in CI-style isolation — no LLM, no live-register writes)

Two headed Electron specs against the live dev stack (auth + the matters rollup are real; the thread poll,
run stream, cancel, and ROPA lists are intercepted so timing is exact and nothing is written to the shared
register):

| Spec | Asserts | Result |
|---|---|---|
| `web/cypress/e2e/priv-9a-covisible.cy.ts` | co-visible (chat + register dashboard both visible, toggle tab gone) when wide; toggle fallback when narrow; light + dark | ✅ pass |
| `web/cypress/e2e/priv-9a-runlock.cy.ts` | run-lock (`#ag-prompt` absent, Stop visible); live row appears mid-run; **no skeleton flicker** (prior row kept, no "Loading…"); Stop → `POST …/cancel` → composer re-enables | ✅ pass |

**Measured UX latency (the maintainer's "no waiting minutes" bar), `time-to-visible.json`:**

```
commit_to_row_visible_ms = 1079   (poll_interval_ms = 2000, bound asserted < 3000)
```

i.e. a committed change surfaced in **~1.1 s** — inside one poll interval, not at run end. Plus the chat
streams steps and Stop is always live, so a long *run* never reads as a frozen *UI*.

Screenshots (this dir): `priv-9a-covisible-{light,dark}.png` (side by side), `priv-9a-toggle-{light,dark}.png`
(fallback), `priv-9a-runlock-covisible.png`, **`priv-9a-live-row-appeared.png`** (the hero), `priv-9a-after-stop.png`.

## Adversarial review (fresh-context, 4 lenses → refute-by-default verify)

14 findings raised, **9 confirmed** (5 should-fix, 4 nits), 5 refuted. Resolution:

- **should-fix — poll double-loop race** (a second concurrent loop could spawn if `runActive` flipped
  false→true during an in-flight tick) → **fixed** with a `pollGeneration` chain-ownership guard (a superseded
  tick refuses to re-arm). Mirrors `ConversationPanel`.
- **should-fix — dead `submitting` terms / unreachable `'Starting…'`** in the composer branch → **fixed**:
  dropped the constant-false guards and the `'Starting…'` label (the run-lock intentionally retires that
  transient — confirmed here).
- **should-fix — Stop disabled during the create-run window** → **fixed**: `submit()` seeds
  `pendingRunId = created.id`, so Stop is targetable the instant the lock engages (window closed to just the
  cancel round-trip).
- **should-fix — no live-refresh in the 720–1168 px toggle band** → **fixed**: the toggle fallback now keeps
  the conversation mounted (hidden) so `runActive` keeps flowing and the toggle register live-updates too
  (also dissolved the "`registerReloadKey` inert in toggle mode" nit, and means switching tabs no longer drops
  a live stream).
- **should-fix — missing run-lock/no-flicker test** → **addressed** by `priv-9a-runlock.cy.ts` (DOM-swap +
  no-skeleton-flicker + the measured latency).
- **nits**: `onDestroy → stopPoll` kept as a belt-and-suspenders alongside the load-bearing `destroyed` guard;
  the latency number is now recorded (above).

## Honest caveats / follow-ups

- **Mid-run resize across the split breakpoint** remounts the conversation panel (it moves between the split
  pane and the toggle div), briefly dropping the live stream; the run is durable (F1-S1) and the poll resumes,
  so no data is lost — a documented nit, not fixed in v1 (would need a structurally-stable panel position).
- **Register pane at minimum co-visible width**: the Overview *dashboard* (PRIV-6b, a 4-column grid) wraps
  tightly at ~420 px (`priv-9a-covisible-light.png`); it's readable and the panes are resizable, and the
  per-entity tables (the "watch a row change" view) are comfortable. Making the dashboard responsive at narrow
  widths is a PRIV-6b refinement, out of this slice.
- **Pre-existing**: the composer label reads "Ask the Commercial agent" even in a Privacy matter
  (`ConversationPanel.svelte`, hardcoded pre-PRIV-9a) — spotted here, not introduced; worth a tidy-up.
- **The changed-row highlight is PRIV-9b** — 9a makes rows appear/disappear live; 9b adds the structured
  change-signal (agent tool results carry the entity id) that highlights *which* row changed, with its own
  ADR-F024.
