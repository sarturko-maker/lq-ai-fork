# PRIV-9b — live changed-row highlight + cross-process streaming (evidence)

**Date:** 2026-06-19 · **ADRs:** F024 (agent→register change-signal), F025 (cross-process run-stream transport)

## What shipped

1. **The change-signal (ADR-F024).** The Privacy agent's guarded ROPA tools record their affected
   `(kind, id, verb)` into a run-scoped, B-class `RopaChangeLedger` after a successful flush — only on a REAL
   change (no-ops/rejections record nothing). The runner drains it onto a transient `data-ropa-change` stream
   frame. The cockpit lifts the id into a host-hoisted recently-changed set; `RopaRegister` washes the matching
   activity/system/vendor row (`--status-completed-wash`, fading; reduced-motion → instant). Model-facing prose
   unchanged; ids only (audit-safe).

2. **Cross-process streaming (ADR-F025).** Agent runs execute in the arq worker; a publish-only
   `RedisStreamBroker` fans the run's live parts onto Redis pub/sub, and an api-side reference-counted
   `RedisStreamBridge` republishes them into the existing process-local broker — so the SSE endpoint (and the
   runner, and `RunStreamPublisher`) are **unchanged** and the whole live cockpit (reasoning ribbon, tool
   frames, AND the highlight) now reaches the browser. Before this, F1-S1's worker execution left the SSE
   stream serving DB-tail only ("live parts simply stop arriving"); this closes that gap.

## Proof 1 — LIVE on DeepSeek (real agent, real register, real stream)

Three runs on the seeded Privacy matter via the `deepseek` alias (`deepseek-v4-flash`), each **completed**, each
captured off the real SSE endpoint (`GET /agents/runs/{id}/stream`). Summary in
`live-deepseek-stream-frames.txt`. The decisive lines:

| use-case | tool path | `data-ropa-change` frame | run |
|---|---|---|---|
| add a system | propose_system (Hotjar) | `{kind: system, id: 95a5441b…, verb: create}` | completed |
| retire a system | retire_system (Mixpanel) | `{kind: system, id: c9ec4a65…, verb: retire}` | completed |
| add a vendor | propose_vendor (Stripe) | `{kind: vendor, id: f7dfe0bc…, verb: create}` | completed |

Each capture also shows the FULL live experience now crossing worker→Redis→api→browser: ~114–171
`reasoning-delta` (the thinking ribbon), `tool-input-available`/`tool-output-available` (tool frames),
`start-step`/`finish-step` (turn boundaries), the terminal text block, and the `data-ropa-change` frame. This
is the cross-process transport (ADR-F025) working end-to-end — `start-step`/`reasoning-delta` are live-only
parts (never DB-tail), so their arrival proves the bridge.

> Note: the cockpit UI's default alias is `smart` → MiniMax-M3, whose token plan is currently exhausted, so
> UI-initiated runs fail until it's topped up (or `smart` is repointed). The `deepseek` alias has quota — the
> runs above used it directly via the API. Repointing the global `smart` alias to make the UI route to DeepSeek
> needs maintainer authorization (shared infra); it was not done.

## Proof 2 — the highlight in the browser (deterministic, CI-safe)

`web/cypress/e2e/priv-9b-highlight.cy.ts` (headed electron, 1280) drives the REAL highlight code path: the
seeded Privacy matter, co-visible (rail collapsed), register on the Systems tab; the run stream is intercepted
to deliver a **real** `data-ropa-change` frame for a rendered system row. The ConversationPanel consumes it →
dispatches `ropachange` → the host washes the matching row. **Passed**; screenshots:

- `priv-9b-highlight-light.png` — the **Hotjar** row washed green beside the run-locked chat ("The agent is
  working… [Stop]").
- `priv-9b-highlight-dark.png` — the same in dark mode (the dark `--status-completed-wash`).

The SAME frame shape is proven to fire live on DeepSeek (Proof 1), so the deterministic frame is faithful.

## Gate

- **API:** `2346 passed, 19 skipped` (full suite, throwaway pgvector) — re-run green after the review fixes.
  New: `test_ropa_changes.py`, `test_agent_stream_redis.py` (fake-redis round-trip + attach-leak + pump-death
  drop), the change-signal recording tests in `test_ropa_tools.py`, the `ropa_changed` publisher tests, and the
  runner drain→`ropa_changed` glue test. ruff + mypy clean.
- **Web:** `npm run check` 0 errors; `893 vitest passed` (incl. `parseRopaChangePayload`).
- **Cypress:** `priv-9b-highlight.cy.ts` passed (light + dark).
- **Adversarial review (fresh-context, 4 lenses → per-finding refute-by-default verify): 13 raised → 7
  confirmed → 6 dropped; ALL fixed.** Two should-fixes hardened the new Redis bridge —
  (1) `attach()` now closes the pubsub if `subscribe()` blips (no connection leak); (2) `_pump()` now catches a
  mid-stream Redis drop, drops the dead subscription + releases it (a future viewer rebuilds; the open stream
  falls to the DB-tail). Plus: the `compose_and_execute_run` `broker` type now covers `RedisStreamBroker`; a
  `_closed` flag stops a post-shutdown publish re-spawning the drain; and the runner glue gained a direct test.
- **Post-fix live regression:** the rebuilt dev stack re-ran a 4th live DeepSeek scenario (add **PostHog**
  system) → `data-ropa-change {system, …, create}`, 130 reasoning-deltas + tool frames cross-process, completed.

## Known follow-ups (not 9b regressions)

- **Co-visible register pane is narrow at 1280 with the rail collapsed** — the "ROPA register" heading +
  subtitle wrap and the table needs horizontal scroll. This is the PRIV-9a carryover (Overview/register cramped
  at narrow co-visible width); the wash is clearly visible regardless. Worth a width/layout pass.
- **Dev-only skill bindings:** `ropa-maintenance` + `ropa-population` were bound to the Privacy area **in the
  dev DB** so the live agent is coherent. The production default-binding migration remains the standing Backlog
  item.
- **Live test register mutations:** the three live runs left real changes in the dev register (Hotjar added,
  Mixpanel soft-retired, Stripe added) — all reversible; the agent's normal job. Noted, not cleaned.
- **Category-row wash + retire "outro" animation** remain deferred (ADR-F024 § Known limits).
