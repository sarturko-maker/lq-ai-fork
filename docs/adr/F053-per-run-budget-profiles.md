# F053 — Per-run budget profiles (cost/effort envelope) + ≥4× default ceilings

- Status: accepted (with F2 Slice O, 2026-06-30)
- Date: 2026-06-30
- Deciders: maintainer (Arturs), agent
- Milestone: **F2 — Memory / retrieval** (the "Strategy + safety" line). Builds on **ADR-F051**
  (per-run token budget — R4 realised) and **ADR-F049 Slice E** (fan-out quota); a companion to the
  PageIndex slice (`docs/fork/plans/PAGEINDEX-SLICE-P.md`), which needs both more headroom and a
  user-facing dial.

## Context

The four per-run brakes — the token budget (ADR-F051), the fan-out quota (ADR-F049 Slice E), the
settled-step ceiling (`max_steps`), and the wall-clock timeout — shipped with conservative, uncalibrated
defaults (2M tokens / 8 subagents / 100 steps / 900s). The maintainer's directive: **the default ceilings
should be at least 4× higher so the agent can fan out and read liberally, with an easy way to dial them
*down* in the UI.** The philosophy is "system proposes, user owns" applied to cost: a generous ceiling is a
*runaway backstop*, not a budget; the human picks a cheaper/faster/tighter envelope when they want one. Cost
should stop being the day-to-day throttle (speed and context-window are the real arbiters — see the plan's
strategy doctrine); the brake only exists to bound a pathological run.

An awareness-only review of upstream (`github.com/LegalQuants/lq-ai`) confirmed there is **no reusable
budget-profile / per-user-quota / cost-dashboard system** to adopt — upstream's only cost cap is the
autonomous-session USD brake, welded to the `AutonomousSession` ORM + a fixed `ToolIntent` enum + the
phase-machine, which the deepagents runner does not use. So this is new work; the one upstream wheel worth
reusing (a rolling-average USD estimator to populate `agent_runs.cost_usd`) is **deferred to Slice O-2**
(see Consequences) to keep this slice reviewable.

Constraint discovered while mapping the flow: the arq worker is enqueued with **only the run id** and reads
`agent_runs` columns directly — so the chosen envelope must be **persisted on the run row**, not threaded
through job args.

## Considered options

1. **Raise the four config defaults 4× and stop there (no UI, no profiles).** One-line-each change.
   *Rejected:* delivers "4× higher" but not "easy to reduce in the UI" — a high ceiling with no dial-down is
   half the ask and arguably less safe (no cheap mode).

2. **Per-run raw integer fields in the composer (token budget, fan-out, steps, wall clock).** Four number
   inputs. *Rejected:* not "easy" — four knobs the user must understand and keep consistent; invites
   nonsensical combinations.

3. **A `budget_profile` enum (economy / balanced / generous) resolving to a four-brake envelope server-side,
   persisted on the run row, surfaced as ONE dropdown (CHOSEN).** balanced (default) is the ≥4× tier (read
   from `Settings`, so env-tunable); economy is the conservative pre-Slice-O tier (the dial-down); generous
   raises it for deep work. One dropdown, three named tiers, no inconsistent states.

## Decision outcome

Chosen: **option 3.**

- **Profiles → envelope.** `BudgetProfile` (StrEnum: economy/balanced/generous) in
  `app.schemas.agent_runs`; `resolve_envelope(profile, settings) -> BudgetEnvelope` in
  `app.agents.budget` is the single source of truth. economy = `(2M, 8, 100, 900s)`; **balanced (default)**
  = `Settings.(run_token_budget=8M, fan_out_quota=32, run_max_steps=400, run_wall_clock_seconds=3600s)`;
  generous = `(16M, 48, 600, 5400s)`. A NULL/unknown profile (legacy rows) resolves to balanced.
- **≥4× defaults.** The raised `Settings` defaults are the balanced tier — exactly 4× the economy tier on
  every brake (8M/32/400/3600 vs 2M/8/100/900). Encoded as a test (`test_budget.py`).
- **Persisted on the row.** Migration **0080** adds `agent_runs.budget_profile` (nullable `TEXT`, additive,
  non-destructive). The endpoint resolves the envelope, materializes `max_steps` on the row (the runner
  reads it directly; an explicit request `max_steps` overrides the profile — ceiling raised to 600), and
  stores the profile string. Composition re-resolves the other three brakes from the stored profile and
  passes them into the runner (was a direct `get_settings()` read).
- **One UI dropdown.** The composer (`ConversationPanel.svelte`) gains a Budget select (Economy/Balanced/
  Generous, default balanced) sent as `budget_profile` on every run; the run-read response echoes it.
- **Timeout layering.** The arq job timeout is raised `1020s → 5520s` to stay above the largest profile's
  wall clock (`MAX_PROFILE_WALL_CLOCK_SECONDS = 5400s`) so the runner's clean cap still fires before arq
  hard-cancels; the invariant is guarded by `test_agent_run_timeout_layering`.

## Consequences

- **The agent can work freely; the human can dial down.** balanced lets it fan out (32) and spend (8M)
  without clipping legitimate multi-turn / bounded-fan-out work; economy gives a cheap, fast, tight run in
  one click; generous unblocks deep work (and is what a token-hungry PageIndex deep-dive will want).
- **Ceilings are still backstops, not budgets.** Raising them widens blast radius; the mitigations are (a)
  the dial-down, (b) the brakes still fire at the selected tier, (c) — once O-2 lands — a visible cost
  estimate. 8M tokens is large on a premium model, but the local gateway runs cheaper models and the number
  is a runaway guard, not the expected spend.
- **One source of truth, env-tunable default.** balanced reads from `Settings`, so an operator can shift the
  default tier without a code change; economy/generous are fixed. The 4× relationship is asserted in tests.
- **`cost_usd` still NULL — deferred to Slice O-2 (the actioned upstream-reuse finding).** Showing
  *estimated spend* in the budget UI needs a per-token rate; upstream's `estimate_judge_call_cost_usd`
  (`api/app/citation/cost.py`) is **not** directly reusable (it is per-call and `purpose='judge_paraphrase'`,
  while deepagents calls are `agent_loop`). O-2 will mirror its rolling-average-from-`inference_routing_log`
  pattern with a new `agent_loop` per-token estimator, populate `agent_runs.cost_usd` at `settle_run` from
  the persisted `total_tokens`, and surface it in the UI. Exact per-run attribution still needs the deferred
  routing-log `run_id` (a separate cross-service slice).
- **Gate.** Deterministic: `test_budget.py` (the profile→envelope map + the ≥4× requirement + legacy/NULL →
  balanced); `test_agent_runs_api.py` (profile persisted + resolves `max_steps`, explicit override, invalid
  profile rejected, ceiling raised to 600); `test_agent_run_timeout_layering` (arq timeout > largest profile
  wall clock). Migration 0080 up→down→up verified on a throwaway pgvector; full api + web suites green.
- **No new dependency.** Additive migration only; the gateway is untouched.

## Slice O-2 addendum — `cost_usd` populated (accepted 2026-06-30)

Slice O deferred showing *estimated spend*; O-2 lands it. Mapping the cost surfaces changed two
assumptions the parent slice made, both in our favour:

- **No migration, no new column.** `agent_runs.cost_usd` (`NUMERIC(10,4)`, nullable) already
  exists and is already exposed on `AgentRunRead` + the TS `AgentRun`. O-2 only writes and
  renders it.
- **Real calibration data already flows.** Every deep-agent gateway call is tagged
  `purpose='agent_loop'` (`app.agents.factory`) and the gateway records a real per-call
  `cost_estimate` (from its `cost_tracking.rates` map) on the routing-log row — so a rolling
  average over `agent_loop` traffic has live data, not just a cold-start default.

Decisions (within F053's accepted umbrella; recorded here, no new ADR):

1. **Blended per-token rate, not a per-call average.** `app.citation.cost` averages *per-call*
   cost (a judge call is fixed-shape). A run is many calls of varying size and the only
   run-level quantity persisted is `total_tokens` (Slice G), so the estimator
   (`app.agents.cost`) computes `SUM(cost_estimate) / SUM(tokens_in+tokens_out)` over the last
   100 priced `agent_loop` rows (<=30 days) and multiplies by `total_tokens`. Summing-then-
   dividing weights the rate by call size.
2. **An estimate, not exact per-run cost.** The routing log has no run/agent-run id, so a run's
   own rows can't be summed — exact attribution stays a deferred cross-service slice
   (routing-log `run_id`). The UI labels it "Est. cost ~ ..." with a "not an exact bill" tooltip.
3. **Fallback rate when uncalibrated.** Fewer than 5 priced `agent_loop` rows ->
   `DEFAULT_AGENT_PER_TOKEN_USD` (~$3/Mtok), a documented placeholder that self-calibrates. (On
   the dev box, whose gateway prices no local model, the fallback is what shows — honest, and
   labelled approximate.)
4. **No cache.** Unlike the judge estimator (fires several times per chat message), this runs
   once per run at settlement — a process-global cache would buy nothing, so it is omitted (no
   module singleton).
5. **Own session, best-effort.** The runner computes the cost in a SEPARATE short-lived session
   before `_finalize` (a failed rate query can never poison the settlement transaction) and only
   when `total_tokens` is truthy; any failure degrades to `cost_usd` NULL. Timeout/error paths
   settle unpriced (no token total). `settle_run` gained a `cost_usd` param it persists in the
   one terminal UPDATE.
6. **UI = post-run actual only.** The estimate renders on the settled run card, not as a pre-run
   per-profile number: multiplying a per-token rate by a profile's *ceiling* (8M/16M tokens)
   would show a scary backstop figure, not expected spend — misleading. A "typical run ~ $X"
   hint near the dropdown (rate x the average run's tokens) is a possible honest follow-up.

Gate: `test_agent_cost.py` (blended math, size-weighting, fallback <5, purpose/null/stale
filters, total_tokens None/0, db=None, defensive DB-error fallback); `test_agent_lease.py`
(cost_usd persisted + NULL by default); `test_agent_runner.py` (normal path priced, timeout
path unpriced); `ConversationPanel-helpers.test.ts` (`formatRunCostUSD`). No migration; gateway
untouched; no new dependency. `cost_usd` exact per-run attribution (routing-log `run_id`)
remains the deferred follow-up.
