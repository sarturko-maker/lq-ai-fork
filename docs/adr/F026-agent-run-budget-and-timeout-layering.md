# F026 — Agent-run budget defaults + the timeout-layering invariant

- Status: accepted
- Date: 2026-06-19
- Extends: ADR-F002 (the deep-agent "glass cockpit" run + its interim brakes), ADR-F009 (agent runs execute in
  the arq worker under a lease)
- Milestone: post-PRIV-9 cockpit hardening (make real privacy work actually finish)

## Context

A cockpit run is bounded by three independent brakes, all set as conservative placeholders when the agent loop
was first wired (F0-S2) and never re-tuned for the privacy workload:

1. **`max_steps`** — the per-run settled-step cap (`schemas/agent_runs.py`, default `20`). The cockpit's
   `createRun` never sends one, so every UI run falls through to the default.
2. **In-run wall clock** — `runner.DEFAULT_WALL_CLOCK_SECONDS` (`300s`), the run's *own* clean brake: on expiry
   the runner settles the run `failed`/`cap_exceeded` with all steps preserved.
3. **arq job timeout** — `agent_run_worker.AGENT_RUN_JOB_TIMEOUT_SECONDS` (`420s`), a per-function override on
   the shared worker (whose default `job_timeout=900` serves the legacy playbook/tabular jobs). On expiry arq
   hard-cancels the worker coroutine → the run settles as the uglier "run interrupted" (a `CancelledError`).

A single ROPA edit ("change Mixpanel → Hotjar") is ~10–20 *settled* steps (read register → locate activity →
propose/link/retire → re-read, with a model turn between each); a "change X, update Y, add Z" ask stacks
several. So `max_steps=20` capped genuine privacy work mid-run, with no final answer — the symptom the
maintainer hit on the live DeepSeek-flash stack (2026-06-19).

Two things had to be decided together, because the three brakes are **coupled**: raising the step budget without
raising the wall clock would only trade the step cap for a timeout (a reasoning model like DeepSeek flash spends
real wall time per step); and raising the wall clock past the arq job timeout would turn every long run's *clean*
cap into a *hard interruption*. The ordering `in-run wall clock < arq job timeout` is load-bearing.

Maintainer's call (2026-06-19): budget = **100 steps / 900s**.

## Considered Options

1. **Leave it at 20 / 300 / 420.** Rejected — it's the bug; real ROPA tasks don't finish.

2. **Raise only `max_steps`.** Rejected — the 300s wall clock (and behind it the 420s arq timeout) becomes the
   new binding cap on a reasoning model; the run still dies mid-task, now by timeout instead of step cap.

3. **Have the cockpit pass an explicit higher `max_steps`.** Rejected as the *primary* fix: it leaves the
   server default (the contract for every other API caller) wrong, and still doesn't touch the two timeouts.

4. **Make the wall clock a per-run column like `max_steps`.** Rejected for this slice — a schema + migration for
   a knob nobody is varying per-run yet; the run-level default in the runner is the honest single source until a
   real per-run need appears.

5. **Raise all three, preserving the ordering invariant (CHOSEN).** `max_steps` default → 100, wall clock →
   900s, arq timeout → 1020s (= 900 + the existing 120s settle-slack), so the run's own clean cap always fires
   before arq's hard kill.

## Decision Outcome

**Option 5.** Defaults become **`max_steps=100`, wall clock `900s`, arq agent-run timeout `1020s`.**

- `100` is both the default *and* the schema ceiling (`le=100` unchanged) — raising the ceiling above 100 is a
  deliberate later decision, not a side effect of this bump.
- **`max_steps` is not the money guard.** The R4 cost cap (per ADR-F002, enforced at the `guarded_*` chokepoint)
  bounds spend; `max_steps` bounds *loop length* (a runaway-loop and step-budget guard), and the wall clock
  bounds *time*. This separation is why a generous step budget is safe.
- **The invariant** — `DEFAULT_WALL_CLOCK_SECONDS < AGENT_RUN_JOB_TIMEOUT_SECONDS`, with ≥60s slack — is
  documented at both seams and **guarded by a test** (`test_agent_run_timeout_layering`) so a future budget
  change can't silently invert it and convert graceful caps into interruptions.
- The DB column `agent_runs.max_steps` keeps its now-stale `server_default=20`; it is **non-operative** (the
  create route always sets `max_steps` explicitly from the validated body), so aligning it is a cosmetic
  migration deferred to backlog rather than risked here.

## Consequences

- **Real privacy work finishes.** A multi-change ROPA ask runs to a final answer instead of capping at 20 steps;
  900s of wall clock fits ~100 reasoning-model steps with the arq backstop above it.
- **Clean caps stay clean.** When a run *does* exhaust its budget it settles as `cap_exceeded`/timeout with steps
  preserved (ADR-F004 "settled rows decide"), never as a `CancelledError` "run interrupted" — because the
  ordering invariant holds.
- **Higher ceiling on per-run cost/latency.** A pathological run can now consume up to 100 steps / 900s of
  gateway spend before a brake fires; the R4 cost cap remains the hard money limit, so worst-case *spend* is
  still bounded by cost, not steps.
- **No schema change, no new dependency.** Three constants + one guard test; api + arq-worker rebuilt together
  (the worker owns the wall clock and the arq timeout; the api owns the schema default).
- **Reversible.** Pure tuning — revert the three constants to restore the prior budget.
