# F1-S1 plan — run-lifecycle durability (arq + heartbeat/lease + sweep + cancel)

Status: executed under the maintainer's 2026-06-12 directive ("Run F1-S1 and
make runs unkillable"), per the RATIFIED F1 re-plan (PR #42). Inputs:
`docs/fork/plans/F1-replan.md` § F1-S1 + appendix,
`docs/fork/research/run-durability-landscape.md` (this slice's research),
`docs/fork/research/deepagents-ecosystem.md` §1.4. ADRs in force: F002
(guarded_tool_call chokepoint), F004 (settled rows are the truth), F008
(threads/checkpointer). New ADR drafted in this slice: F009 (at-most-once run
execution + settle-FAILED-never-auto-resume) — the delivery-semantics call is
hard to reverse and diverges from langgraph platform's at-least-once design.

## Goal

A crashed, killed, or cancelled agent run can no longer deadlock anything:
the run row always settles, the thread always accepts the next message, and a
user can cancel a live run. Kill -9 the worker mid-run → the sweep settles the
run FAILED within ~2 minutes and the conversation continues.

## Non-goals (explicitly out)

- Auto-resume of orphaned runs (needs the F1-S5 `(run_id, tool_call_id)`
  ledger; ADR-F009 records why).
- Live token deltas across the process boundary (Redis pub/sub broker) — the
  S7 DB-tail fallback serves the stream; "lossiness only costs animation"
  (ADR-F004). Optional follow-up, noted in MILESTONES backlog.
- A `queued` run status (web knows the current five; runs stay `running` from
  POST; the claim-grace sweep rule covers lost enqueues).
- Age-based intra-thread checkpoint pruning + ShallowPostgresSaver evaluation
  (needs measured bloat + a legal-retention policy decision) — backlog.
- UI cancel button (lands with the S2 cockpit; S1 ships the endpoint).

## Design (research-backed; see run-durability-landscape.md)

### Execution moves to arq, at-most-once

- `POST /agents/runs` enqueues `agent_run_job(run_id)` on the existing
  `arq:m3a6` worker (precedent: autonomous/tabular; no new container) with
  `_job_id = f"agent-run:{run_id}"`. Enqueue failure or `None` (arq's silent
  job-id-collision return, verified) → run settled `failed` immediately —
  never a silent zombie.
- Registered via `arq.worker.func(..., max_tries=1, timeout=420)`:
  verified at arq 0.26.3 that `job_try > max_tries` is checked BEFORE the body
  runs, so post-SIGKILL redelivery settles arq-side without re-running the
  graph (at-most-once; our row is settled by the sweep). Worker-wide defaults
  for legacy jobs unchanged; `allow_abort_jobs = True` added (only jobs we
  explicitly abort are affected). arq floor raised to 0.26.3 (abort/retry-race
  fixes; already installed).
- `_run_in_background` moves to `app/agents/composition.py` (pure move +
  rename `compose_and_execute_run`); the api keeps no execution path —
  BackgroundTasks is gone.

### Lease + heartbeat + write-side fencing

- `agent_runs` gains `claimed_by` (text, informational worker tag),
  `claimed_at`, `lease_token` (uuid, the fencing value), `heartbeat_at`.
  All comparisons use DB-side `now()` (single clock authority).
- The job CLAIMS atomically: `UPDATE ... SET claimed_by, claimed_at=now(),
  heartbeat_at=now(), lease_token=:new WHERE id=:run AND status='running' AND
  claimed_by IS NULL` — rowcount 0 → already settled/claimed → honest no-op.
- The runner heartbeats from inside the stream loop, throttled to one write
  per 15s, AND `guarded_dispatch` touches the heartbeat per tool dispatch
  (the two-source pattern; tool-boundary-only and per-job-only granularities
  both false-orphan in the field — Hermes/#7417).
- EVERY worker write is fenced: heartbeat and terminal UPDATEs carry
  `WHERE status='running' AND lease_token=:mine`, rowcount-checked. Rowcount
  0 on heartbeat → the run was settled elsewhere (sweep/cancel) → the runner
  hard-stops (`RunSettledElsewhere`), skips finalize. First terminal writer
  wins; a zombie's late write is rejected by SQL (terminal-status
  monotonicity).

### Orphan sweep (startup + every-minute cron on the arq worker)

Settles as FAILED, never re-enqueues (ADR-F009). One conditional UPDATE
(atomic; multi-replica safe without SKIP LOCKED), predicate re-checked in the
WHERE clause:

- claimed + `heartbeat_at < now() - 120s` → `failed`,
  error `orphaned: worker heartbeat stale`.
- unclaimed + `started_at < now() - 300s` (claim grace ≫ heartbeat threshold;
  covers lost enqueues, dead workers before claim, and pre-migration legacy
  rows) → `failed`, error `orphaned: never claimed by a worker`.

The `orphaned:` error prefix keeps infra deaths separable from agent failures
(OpenClaw's `lost` lesson) without a new status value. One audit row per
settled run (`agent_run.orphan_settled`, counts/types/IDs). A false-orphan
(event drought > 120s on a live run) is SAFE — fencing halts the zombie — just
rude; the threshold is settings-overridable. 300s wall clock still bounds all
runs. Thresholds: heartbeat 15s / orphan 120s (8 missed beats) / grace 300s.

### Cancel endpoint (settle-first, idempotent)

`POST /agents/runs/{run_id}/cancel` — owner-scoped, 404 cross-user:

1. Terminal already → 200 with the row (idempotent no-op; Letta pattern).
2. `UPDATE ... SET status='cancelled', finished_at=now() WHERE id AND
   status='running'`; rowcount 0 → re-read, return (it settled in the race).
3. Audit row (`agent_run.cancel`), then best-effort `Job.abort()` — the
   impatient path; the worker also notices via its next fenced write failing
   (≤ ~15s) and R5 already denies tool dispatches on non-running status.
4. Worker `BaseException` handler (abort/shutdown `CancelledError`): fenced
   settle attempt (no-op when the endpoint won), re-raise so arq's abort
   bookkeeping sees it. SIGTERM deploys settle runs the same way (the
   silent-orphan-factory failure mode).

### Thread repair + admission

- Follow-up admission (`POST /runs` with `thread_id`) and `continuable` accept
  any TERMINAL latest status (`completed | failed | cancelled | cap_exceeded`)
  — not just `completed` — still requiring checkpoint state + active matter.
  (A first-run-failed thread with no checkpoint stays non-continuable:
  nothing to honestly continue; documented edge.)
- Pre-invoke transcript repair in the composition path: if the thread's
  checkpoint state ends in an AIMessage with dangling `tool_calls`, append
  synthetic `ToolMessage`s ("interrupted; the action may or may not have
  executed" / "cancelled by the user before this tool returned") via
  `aupdate_state` before streaming. With no dangling calls left,
  `PatchToolCallsMiddleware` has nothing to Overwrite — the #3789 wedge path
  is never entered. Regression test: cancel mid-tool-call → follow-up turn
  completes (the ratified plan's #3789 test).

### Durability + retention

- `astream_events(..., durability="sync")` (kwarg forwarding verified) — the
  checkpoint for a step whose side effects ran is never lost to a crash.
- `DELETE /agents/threads/{thread_id}` (new): owner-scoped 404; 409
  `thread_busy` while a run is live; deletes the row (runs/steps cascade) +
  `adelete_thread()` + audit row.
- User deletion needs no new hook: hard delete cascades `agent_threads`, and
  the daily GC cron then removes the orphaned checkpoint lineages.
- Daily GC cron: checkpoint lineages whose `thread_id` has no `agent_threads`
  row → `adelete_thread()` (covers user-cascade deletes, historical orphans,
  and failed best-effort endpoint deletes).
- Ingest-orphan cron: CUT at implementation time. `files` carries only
  `created_at` (no `updated_at`), so a cron cannot distinguish stuck from
  legitimately-processing without a new migration on a LEGACY pipeline
  (bugfix-only per CLAUDE.md), and a cron re-enqueue can race a live job
  in ways the boot-time startup sweep cannot. Startup sweep stays the
  recovery path; backlogged.

## Files

- `api/alembic/versions/0052_agent_run_lease.py` — 4 columns + partial index
  `(status='running')`; rebuild api + arq-worker + ingest-worker together.
- `api/app/models/agent_run.py`, `api/app/config.py` (3 settings),
  `api/pyproject.toml` (arq floor).
- `api/app/agents/composition.py` (moved composition point + repair),
  `runner.py` (heartbeat hook, fenced finalize, durability, hard-stop),
  `guard.py` (heartbeat touch).
- `api/app/workers/agent_run_worker.py` (job + claim + sweep + GC),
  `arq_setup.py` (func registration, allow_abort_jobs, crons),
  `queue.py` (enqueue helper).
- `api/app/api/agent_runs.py` (enqueue kick-off, cancel + thread-delete
  endpoints, admission/continuable).
- `docs/adr/F009-at-most-once-agent-runs.md`, MILESTONES backlog notes,
  HANDOFF rewrite. Tests across `api/tests/agents/` + workers.

## Verification (ADR-F005 gate)

1. Containerized api + gateway suites, counts quoted. New tests: claim/fence
   (zombie write rejected), sweep rules (stale heartbeat, unclaimed grace,
   fresh runs untouched), cancel (idempotent, race, audit), admission/repair
   (dangling tool_calls → follow-up works), enqueue-None handling,
   thread-delete + checkpoint cleanup, #3789 regression.
2. Live on the dev stack (MiniMax): kill -9 the arq worker mid-run → sweep
   settles FAILED → same thread accepts and completes a follow-up; cancel a
   live fan-out run → thread continuable; delete a thread → checkpoint rows
   gone (SQL count). Evidence in `docs/fork/evidence/f1-s1/`.
3. Fresh-context adversarial review (security pass included: new endpoints,
   audit rows, no key/score leakage in errors); blockers fixed in-slice.
