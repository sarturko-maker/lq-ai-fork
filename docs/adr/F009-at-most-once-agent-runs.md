# F009 — Agent runs execute at-most-once; orphans settle FAILED, never auto-resume

Status: proposed (drafted in F1-S1, 2026-06-12)

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
  `guarded_tool_call` chokepoint. Every worker write is fenced
  (`WHERE status='running' AND lease_token=:mine`, rowcount-checked) — the
  first terminal writer wins; a zombie's late write is rejected by SQL.
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
- The arq in-progress key (timeout+10s, never renewed) makes arq's own
  recovery the slow backstop; our sweep is the fast path by design.
