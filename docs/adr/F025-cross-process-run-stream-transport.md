# F025 — Cross-process run-stream transport (Redis pub/sub bridge)

- Status: accepted
- Date: 2026-06-19
- Extends: ADR-F004 (render-deterministic UI — settled rows decide, streams animate), ADR-F006 (the AI SDK UI
  Message Stream wire spec + the in-process broker), ADR-F009 (agent runs execute in the arq worker),
  ADR-F024 (the change-signal that rides this stream)
- Milestone: PRIV-9b/9c (the live cockpit — reasoning ribbon, tool-call frames, and the changed-row highlight
  actually stream as the agent works)

## Context

F0-S7 (ADR-F006) built the live SSE stream — reasoning deltas, tool-call frames, step mirrors, and now the
PRIV-9b `data-ropa-change` highlight signal — over a **process-local** `RunStreamBroker` (in-memory asyncio
queues): the runner publishes parts, the SSE endpoint subscribes, both in the api process.

F1-S1 (ADR-F009) then moved **agent execution into the arq worker** — a *different* process. The worker calls
`compose_and_execute_run(...)` with **no broker**, so `publisher=None`: the worker emits **zero** live parts.
The api's SSE endpoint, subscribing to its own (empty) local broker, falls back to the DB-tail (settled rows).
`stream.py` documents this exactly: *"when execution moves out of process … live parts simply stop arriving
and the endpoint's DB-tail fallback carries the stream unchanged."*

The accepted consequence at the time was "lossiness only costs animation" (ADR-F004). But the product thesis —
a cockpit that feels *like Claude Code*, with the agent's work visible as it happens (streamed tool calls,
subagent fan-out, and the PRIV-9b changed-row highlight) — needs the live stream to actually reach the browser.
Today, in the live stack, it does not: the chat updates only by ~2s polling and the highlight can't fire at
all (its transient frame is never emitted cross-process). Maintainer's call (2026-06-19): wire it.

## Considered Options

1. **Leave it (DB-tail only).** Status quo: no live animation in the live stack; the highlight is dormant.
   Rejected — it's the gap we're closing.

2. **Run the agent in-process in the api again.** Undo F1-S1's worker execution so the broker is shared.
   Rejected: F1-S1/ADR-F009 (lease, fenced settle, orphan sweep, durable resume) is load-bearing; the api must
   keep no execution path (a 300s run must not live in a request worker).

3. **Persist the live parts and poll them.** Write reasoning/tool/change parts to a table the client polls.
   Rejected: it turns animation into durable state (contra ADR-F004), inflates writes on the hot path, and
   duplicates what settled rows already carry.

4. **Redis pub/sub bridge into the existing local broker (CHOSEN).** The worker publishes each stream part to
   a Redis channel keyed by run id; an api-side subscriber **republishes** those parts into the *existing*
   process-local `RunStreamBroker`, which fans them to SSE subscribers exactly as before. Redis is already in
   the stack (arq's queue). The runner, the `RunStreamPublisher` semantic surface, and the entire SSE endpoint
   are **unchanged** — the broker becomes the api-side fan-out for Redis-delivered parts.

## Decision Outcome

**Option 4.** A thin Redis transport that reuses everything already built:

- **Publish side (worker) — `RedisStreamBroker`** (`stream.py`): a publish-only, broker-shaped facade
  (`publisher()`/`publish()`/`close()`), so the **same `RunStreamPublisher` is reused unchanged**. `publish()`
  is sync + fire-and-forget (never raises into the runner); it enqueues onto a single asyncio queue drained by
  one background task that `PUBLISH`es JSON-encoded parts to `agent_run_stream:{run_id}` **in FIFO order**
  (so `start` precedes `delta`, `tool-input` precedes `tool-output`). `close()` enqueues a
  `{"__stream_closed__": true}` marker after the terminal parts. Created once per worker process in the arq
  `on_startup` from `ctx["redis"]`, stored in `ctx`, passed by `agent_run_job` → `execute_run_job` → `compose`.

- **Subscribe side (api) — `RedisStreamBridge`** (`stream.py`): subscribes to a run's channel and republishes
  each part into the process-local `RunStreamBroker` (`broker.publish(run_id, part)`; the close marker →
  `broker.close(run_id)`). **Reference-counted per run id** — one Redis subscription per run regardless of how
  many browsers watch it (the local broker fans out), torn down when the last viewer detaches. Created in the
  api lifespan from the shared `app.cache.get_redis()` client; the SSE endpoint `attach`es after its ownership
  check and `detach`es in `finally`. If Redis is unavailable the attach fails soft → the endpoint serves the
  DB-tail (today's behaviour) — degradation, never a crash.

- **The SSE endpoint and the runner do not change.** The bridge makes worker-published parts appear in the
  local broker as if they were local; `_stream_run_events` reads them through the same subscriber queue.

## Consequences

- **The live cockpit works in the real stack.** Reasoning ribbon, tool-call frames, subagent steps, AND the
  PRIV-9b changed-row highlight stream as the agent works — not just on a 2s poll. The "like Claude Code" UX
  is real, not in-process-only.
- **Determinism preserved (ADR-F004).** Pub/sub is fire-and-forget with no replay: a part published before a
  late subscriber's `SUBSCRIBE` round-trip completes, or during a transport blip, is simply missed — the
  DB-tail + the client's poll re-derive the truth from settled rows. The transport carries *animation*; it can
  never corrupt or invent state. The highlight signal (ADR-F024) keeps its "lose a flash, never data" contract.
- **Ordering held.** The single FIFO drain task on the publish side preserves per-run part order; different
  runs use different channels (no cross-run interleave matters).
- **No new authz surface.** The SSE endpoint authorizes run ownership (404 cross-user) *before* the bridge
  attaches, so a user can never bridge a run they don't own. The channel is an internal-only Redis key holding
  exactly what the polled rows already hold (bounded, secret-free step digests + ids) — the same trust
  boundary as the arq job payloads already on this Redis. No raw values, no new secret surface.
- **No new dependency, no schema change.** Redis is already the arq queue; the transport is in-flight only.
- **Backpressure is bounded.** The publish queue and each subscriber queue are capped; a wedged drain/consumer
  drops parts (logged) rather than blocking the run — animation degrades, the run never becomes the stream's
  hostage (the F0-S7 posture, extended across the process boundary).
- **Known limits.** (a) A mid-run join misses parts emitted before subscription (pub/sub has no backlog); the
  local broker's open-block seeding only covers parts seen *after* the bridge attached. Our client tolerates
  unknown-id parts (it reconciles from settled rows), so this costs animation smoothness on a late join, not
  correctness. (b) A mid-stream Redis drop ends the live relay for that *already-open* SSE stream — its viewer
  falls to the DB-tail poll for the rest of the stream (the `_pump` task catches the error, drops the now-dead
  subscription, and releases its connection so a *future* viewer of the same run rebuilds a fresh relay rather
  than bumping refcount on a corpse). Full in-stream auto-reconnect is deliberately out of scope — the DB-tail
  is the recovery backstop (ADR-F004). Both are animation loss, never data loss.
