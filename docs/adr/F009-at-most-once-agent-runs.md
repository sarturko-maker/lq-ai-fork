# F009 — Agent runs execute at-most-once; orphans settle FAILED, never auto-resume

Status: accepted (maintainer, 2026-06-12; drafted in F1-S1)

## Context

F1-S1 moves agent-run execution from FastAPI BackgroundTasks (dies with the
api process; no recovery; stranded `running` rows deadlock their threads) to
the arq worker. A queue forces a delivery-semantics decision: what happens
when a worker dies mid-run, and may the system re-run the graph?

A deepagents run's side effects are not idempotent: tool calls hit the
gateway (spend), write audit rows, and (from F1 onward) act on documents.
LangGraph resume is replay-based — the tools node that was in flight
re-executes on resume. LangGraph Platform runs the at-least-once version of
this design (`BG_JOB_MAX_RETRIES=3`, heartbeat + sweeper) and its flagship
production failure (langgraph #7417) is the consequence: a sweeper with a
too-coarse liveness signal false-orphaned live runs and auto-resumed them,
duplicating side effects. AutoGPT Platform shipped the same bug class via
RabbitMQ redelivery (full re-runs, dangling execution trees — PR #9759's
documented limitation). Temporal's doctrine states the underlying law:
exactly-once side effects are impossible without callee-enforced idempotency
keys. We have no idempotency ledger until F1-S5.

## Considered options

1. **At-least-once (arq default `max_tries=5`) + auto-resume from
   checkpoint** — what langgraph platform does. Maximal recovery; duplicates
   side effects on every false-positive and every mid-tool-call death.
2. **At-most-once (`max_tries=1`); orphans settle FAILED; resume is a user
   action** — verified at arq 0.26.3: `job_try > max_tries` is checked before
   the body runs, so redelivery after a hard death settles without
   re-executing. The user re-sends; the conversation continues on the
   checkpoint (durability="sync" keeps state current).
3. **Durable-execution framework (Temporal-style activities + replay)** —
   correct resume, but requires per-tool-call recorded results + idempotency
   keys + a deterministic orchestrator; a platform migration, not a slice.

## Decision outcome

Option 2. A lost run costs the user one re-sent message; a duplicated run
costs double spend, double audit rows, and (post-F1) doubled actions on legal
documents — an unacceptable trade for an in-house legal tool. Concretely:

- arq `max_tries=1`, `_job_id = "agent-run:{run_id}"`; enqueue failure or
  collision (`enqueue_job` → `None`) settles the run `failed` immediately.
- Liveness is a positive signal: per-claim lease (`lease_token`) +
  `heartbeat_at` written from inside the stream loop (throttled) and at the
  `guarded_tool_call` chokepoint. The fencing invariant, precisely: every
  `agent_runs` status/heartbeat write is conditional on `status='running'`
  (terminal-status monotonicity — the first terminal writer wins); worker
  terminal writes and the runner's throttled heartbeat are ADDITIONALLY
  lease-fenced (`AND lease_token=:mine`, rowcount-checked). The guard's
  tool-boundary touch is status-conditional only — safe because claims are
  once-only (`claimed_by IS NULL`), so no successor lease can exist. Step
  and audit APPENDS are unfenced: a zombie can accrue them (and gateway
  spend) for up to one heartbeat interval before it hard-stops; the sweep
  also fires `Job.abort` at every stale-heartbeat settle to kill zombies
  actively.
- A startup + every-minute sweep settles stale runs as `failed` with an
  `orphaned:` error prefix (infra deaths stay separable from agent errors).
  The sweep NEVER re-enqueues.
- Cancel settles the row first (idempotent, first-writer-wins), then signals
  the worker (arq `Job.abort` + fenced-write detection).
- Threads stay continuable after any terminal status: dangling tool calls in
  checkpoint state are repaired with synthetic ToolMessages before the next
  invoke (deepagents #3789's middleware repair can wedge a thread; ours
  preempts it).

## Consequences

- No automatic recovery: a worker death mid-run always costs the user a
  re-send. Honest, visible, bounded.
- Safe auto-resume becomes possible only with the F1-S5
  `(run_id, tool_call_id)` idempotency ledger; any future ADR enabling it
  must supersede this one.
- False-orphans (heartbeat drought on a live run) are safe but rude — the
  fenced zombie halts; the run reports failed while having partially run.
  Threshold (120s) is settings-tunable; the 300s wall clock bounds all runs.
  A single tool body longer than the threshold is the drought case: neither
  liveness source fires inside one tool await.
- Two-writers window: a settled run's zombie may write checkpoint/step
  rows for up to one heartbeat interval (≤15s; sweep-abort shortens it)
  while a follow-up is already admitted — the lineage can briefly fork.
  Accepted: bounded, rare, and a per-thread write lock is F1-S5 territory
  (the idempotency-ledger slice owns multi-writer semantics).
- Queue wait counts as `running`: the row is created at POST, claimed at
  pickup. The claim grace (1200s) exceeds the shared queue's worst-case
  pickup delay (legacy jobs run 900s), so queued runs are never falsely
  failed — at the cost of slow detection for the rare lost-enqueue zombie
  (enqueue FAILURES settle immediately at POST). A worker outage holds the
  user's flood-brake slots until the sweep clears them; cancel is the
  escape hatch.
- The arq in-progress key (timeout+10s, never renewed) makes arq's own
  recovery the slow backstop; our sweep is the fast path by design.
