# Run-durability landscape — how OSS agent stacks keep runs un-killable

Research input to **F1-S1** (run-lifecycle durability), surveyed 2026-06-12 by a
6-agent parallel sweep + completeness critic. Projects: OpenClaw, Hermes Agent
(Nous Research), OpenHands, LangGraph/deepagents production practice, arq
internals, and a server-side-agents survey (Letta, AutoGPT Platform, Dify,
OpenAI Agents SDK + Temporal).

## Provenance — read this first

Two confidence tiers. Design decisions in the F1-S1 plan rest ONLY on tier 1.

**Tier 1 — verified** (read in our containers at our pinned versions, or
issue/doc pages confirmed during the sweep):

- arq 0.26.3 (installed): `max_tries` is checked against `job_try` BEFORE the
  job body runs — after a SIGKILL, redelivery with `job_try=2 > 1` settles the
  arq job as failed WITHOUT re-running the body. True at-most-once with
  `max_tries=1`.
- arq 0.26.3: the abort branch in `run_job`'s exception handling precedes the
  retry branch — an aborted job is never re-queued, even with `retry_jobs=True`.
  Abort works on queued-not-started jobs; delivery is `task.cancel()` →
  `asyncio.CancelledError`, polled every 0.5s, requires `allow_abort_jobs=True`
  and a live worker.
- arq 0.26.3: the per-job `in_progress` key TTL is `max function timeout + 10s`,
  set once (`psetex`), never renewed — arq cannot distinguish a live run from a
  dead one until that TTL lapses. arq's own recovery is the slow backstop; an
  application-level heartbeat + sweep is the fast path.
- arq 0.26.3: `enqueue_job` silently returns `None` when a job or result key
  with the same `job_id` still exists (`keep_result` default 3600s). Callers
  must treat `None` as "not enqueued".
- arq 0.26.3: `arq.worker.func(coro, *, timeout=, max_tries=, ...)` gives
  per-function overrides — `max_tries=1` for agent runs without changing the
  shared worker's defaults for legacy jobs.
- langchain-core (installed): `astream_events(**kwargs)` forwards kwargs to
  `astream`; `Pregel.astream` accepts `durability` — so
  `agent.astream_events(..., durability="sync")` reaches the checkpointer.
- deepagents 0.6.8 (installed): `PatchToolCallsMiddleware` is present
  (`deepagents.middleware.patch_tool_calls`).
- langgraph #7417 (LangGraph Platform): the platform's own sweeper false-orphans
  live runs — `BG_JOB_HEARTBEAT` hardcoded 120s, sweep at 240s, no way to signal
  liveness during a long await — and then AUTO-RESUMES them, re-executing the
  in-flight tools node and duplicating side effects (replay re-runs the node an
  interrupt/crash happened in). The platform is at-least-once
  (`BG_JOB_MAX_RETRIES=3`).
- deepagents #3789: `PatchToolCallsMiddleware`'s own dangling-tool-call repair
  can permanently wedge a thread at our exact pin (0.6.x / langgraph 1.2.4) —
  its `Overwrite`-based update suffers type erasure crossing a JSON boundary.
- langgraph #6726 / #5672: a `CancelledError` mid-run leaves dangling
  `tool_calls` in checkpoint state → `INVALID_CHAT_HISTORY` on the next invoke;
  cancel also loses un-checkpointed streamed state.
- OSS `AsyncPostgresSaver` has no TTL/retention API; `adelete_thread()` deletes
  the checkpoint/blob/write rows for one `thread_id` (all namespaces) by index.
  LangGraph Platform ships a delete-strategy TTL sweeper as a managed feature —
  the thing we're rebuilding OSS-side.

**Tier 2 — reported by researchers, NOT independently verified** (the critic
flagged star counts, issue numbers and some file paths in the OpenClaw and
Hermes findings as plausible-but-unverified; treat as corroborating color, not
citable fact). The *patterns* below recur across ≥3 independent projects, which
is the actual evidence.

## The convergent architecture

Every surveyed project that runs agents server-side either has — or has the
scar tissue for lacking — the same four mechanisms:

1. **Positive liveness signal (heartbeat), not exception-handler settlement.**
   Hangs don't throw: Letta #3212 (MCP SDK swallowed an error; run sat
   'running' 4+ hours), Dify #12798/#26169/#27415 (request-thread-owned status
   writes die with the client; official workaround is manual DB surgery).
   Heartbeat granularity must cover long awaits: tool-boundary-only heartbeats
   (Hermes' original design; reported) and coarse per-job heartbeats (langgraph
   #7417; verified) both false-orphan live runs. The convergent fix:
   **heartbeat from inside the stream loop per event, rate-limited**, plus a
   touch at the tool-dispatch chokepoint.

2. **Lease + write-side fencing.** AutoGPT's `ClusterLock` (Redis SET NX +
   rate-limited refresh + Lua compare-and-swap release), Hermes'
   `AND current_run_id = :expected` on every completion/heartbeat UPDATE,
   OpenClaw's pid+starttime tuples against PID recycling: the lease must
   identify the *execution attempt* (a per-claim token, not a hostname), and
   **every status/heartbeat write is a conditional UPDATE checked by rowcount**
   — the first terminal writer wins, a zombie's late write is rejected by SQL.
   Terminal-status monotonicity (a late "success" never downgrades a settled
   FAILED) falls out of the same WHERE clause.

3. **Sweep settles FAILED; resume is never automatic.** At-least-once
   redelivery of agent graphs re-runs side effects: AutoGPT shipped RabbitMQ
   redelivery and documented full re-runs + dangling execution trees as the
   consequence; langgraph #7417 is the same bug in managed form. Temporal's
   doctrine is the theoretical backing: exactly-once side effects are
   impossible without callee-enforced idempotency keys, so at-most-once is the
   honest default (`maximum_attempts=1`). OpenClaw auto-resumes ONLY when the
   durable transcript proves no side effect was in flight — our "always settle
   FAILED" is their conservative branch applied unconditionally, correct until
   the F1-S5 `(run_id, tool_call_id)` ledger exists.

4. **Cooperative cancel + out-of-band abort, idempotent, force-settled.**
   Letta polls a stop flag at step boundaries and treats cancelling a finished
   run as an explicit no-op; Dify's stop flag is honored only at node
   boundaries so cancel latency = the longest single tool/LLM call (#18481);
   AutoGPT runs cancellation on a separate queue so it never sits behind work.
   Hermes force-clears the lock server-side rather than waiting for the worker
   to observe the flag. Synthesis: **the cancel endpoint settles the run row
   itself** (first-writer-wins UPDATE), then signals the worker (arq
   `Job.abort` + the worker noticing its fenced writes start failing).

## Transcript repair is the other half

Settling the row un-blocks the *list*; the *conversation* stays bricked unless
the checkpoint transcript is repaired. OpenHands writes a synthetic
`ErrorObservation` bound to the orphaned `tool_call` ("Stop button pressed.
The action has not been executed.") so the transcript stays tool-call-
consistent; langgraph #6726 + deepagents #3789 (both verified) show our pinned
stack both *needs* this and that the built-in middleware repair can itself
wedge. F1-S1 therefore repairs explicitly (synthetic `ToolMessage` per dangling
tool call, distinct wording for user-cancel vs worker-death) before the next
invoke, and regression-tests cancel-mid-tool-call → follow-up.

## Retention

Weakest area everywhere. No application-level project ships checkpoint TTL;
production langgraph users report "90%+ of the DB is historical exhaust" and
cron-delete whole threads. Reusable ideas: TTL-everything for signal keys
(Dify/Letta), an explicit terminal `expired` status (Letta), platform-side
retention windows (Temporal). `ShallowPostgresSaver` (keep-only-latest) is
worth evaluating later as retention-by-design — deepagents #1355 (transcripts
are unrecoverable from checkpoints anyway) removes the main reason to keep
history. F1-S1 ships: `adelete_thread` on thread delete + a GC pass for
checkpoint lineages whose thread row is gone; age-based intra-thread pruning is
deferred (needs a measured bloat problem + a legal-retention policy call).

## Failure modes to test for (each one shipped somewhere)

- Run sat 'running' forever because settlement lived in an exception handler
  and the failure was a hang (Letta #3212).
- Graceful deploy (SIGTERM) silently orphaned runs because the shutdown path
  didn't settle them (OpenClaw report; arq verified: shutdown cancels tasks →
  our `BaseException` handler must settle before re-raising).
- Sweep ate a freshly-created run that no worker had claimed yet (needs a
  claim grace window distinct from the heartbeat threshold).
- Cancel returned success but the run kept executing (Dify #18481 — bounded
  here by fenced writes + heartbeat-failure hard-stop).
- Settled thread refused the next user message (OpenHands #5480 — the
  admission rule + repair regression test).
- Job-id collision made `enqueue_job` return `None` and nobody noticed (arq,
  verified).
