# F051 — Per-run token-budget brake (R4 realised)

- Status: accepted (with F2 Phase-3 Slice F, 2026-06-30)
- Date: 2026-06-30
- Deciders: maintainer (Arturs), agent
- Milestone: **F2 — Memory / retrieval** (the "Strategy + safety" line of
  `docs/fork/plans/RETRIEVAL-MEMORY-eval-first.md`). Follows ADR-F049 **Slice E**
  (cost-aware fan-out + a fan-out quota), which shipped the *soft* guards and explicitly
  deferred the *hard* token stop to its own slice + ADR — this is that ADR.

## Context

The fork's guarded-tool chokepoint advertises three brakes — R6 (grant), R5 (halt), and
**R4 (cost)** — but **R4 has always been a documented no-op** (`api/app/agents/guard.py`).
Nothing enforces a per-run **token** or **dollar** budget anywhere. The brakes that actually
fire are `max_steps`, the langgraph `recursion_limit`, and a wall-clock timeout — all **step/
time** caps, not **cost** caps. A model that loops or fans out can burn a large number of
tokens *within* the step budget (one wide fan-out turn spawns several subagent runs, each
filling its own window) long before it trips `max_steps` — the ADR-F015 over-exploration
finding. Slice E added a pre-flight read-cost estimate, a strategy doctrine, and a fan-out
**quota** (a per-dispatch ceiling on the `task` tool); those make runaway fan-out *unlikely
and bounded* but **not impossible**, and the slice was explicit that cost-safety could not be
claimed until a real token budget existed.

Two facts settled the design (verified in-container):

1. **Token usage can be read api-side, per turn.** The gateway already forces
   `stream_options.include_usage=true` upstream and forwards the final usage chunk in its SSE
   (`gateway/app/providers/openai.py`, `gateway/app/api/inference.py`). The api-side
   `ChatOpenAI` simply did not *ask* for it (`stream_usage` unset), so langchain never parsed
   it. Setting `stream_usage=True` makes langchain populate `usage_metadata` on the merged
   `on_chat_model_end` message — including nested subagent model turns. The runner already
   consumes those events.
2. **Routing-log rows cannot be attributed to a run.** `inference_routing_log` carries
   `tokens_in/out` + `purpose` + `timestamp` but **no `run_id`** (the gateway does not know
   the agent run). So aggregating "this run's tokens" from the routing log would need a
   gateway change + a new correlation column — fragile and cross-service.

## Considered options

1. **Aggregate the gateway routing log per run, halt at the guard (R4 literally in
   `guarded_dispatch`).** Sum `inference_routing_log` rows for the run and deny the next tool
   dispatch over budget. **Rejected:** the routing log has no `run_id` (a `user_id + purpose +
   timestamp` window join is fragile under concurrent runs); the cost is in the *model* calls,
   not the tool dispatches the guard wraps (a local DB read has zero marginal cost — R4 at the
   tool is *correctly* a no-op); and it needs gateway + schema changes.

2. **Persist a per-run token total (migration) and enforce on it.** Add
   `agent_runs.total_tokens`, accumulate, halt, and expose it. **Rejected for this slice** (kept
   as a follow-up): the *brake* needs only the live running total, not persistence; a migration
   triggers the api+arq+ingest rebuild discipline and more surface for no enforcement benefit.
   Observability (and the calibration it would enable) is a deliberate, recorded deferral.

3. **Accumulate per-turn `usage_metadata` in the runner and halt in the loop, beside
   `max_steps` (CHOSEN).** Enable `stream_usage=True`; sum each model turn's
   `usage_metadata.total_tokens` (lead + subagents) in `_drive_agent`; halt the run when the
   cumulative total crosses a configurable `run_token_budget`, settling `cap_exceeded` with a
   distinct `error="token_budget_exceeded"`. In-memory, no migration, api-side only.

## Decision outcome

Chosen: **option 3.** The real cost is the gateway model calls, so the token brake lives where
that cost is incurred — the runner loop — as a sibling to `max_steps`, not at the tool-dispatch
guard (R4-at-the-tool stays an honest no-op; its docstring now points here).

- **Enabler:** `factory.build_gateway_chat_model` sets `stream_usage=True` (one line; the
  gateway already forwards the usage chunk).
- **Accumulate + brake:** `runner._drive_agent` sums `usage_metadata.total_tokens` on every
  `on_chat_model_end` event (a helper `_usage_total`, 0 when usage is absent so the brake never
  fires on missing data) and, mirroring the `max_steps` check, halts when
  `cumulative_tokens >= token_budget and not is_final`. The not-mid-final-answer guard means a
  turn that produces the deliverable is never cut off.
- **Settle:** `cap_exceeded` (the existing capped-run terminal state — partial steps preserved,
  no deliverable) with `error="token_budget_exceeded"` so it is told apart from the step cap
  (which leaves `error` NULL). Lease-fenced via the same `_finalize`/`settle_run` path.
- **Config:** `Settings.run_token_budget` (default **2,000,000** — a conservative, uncalibrated
  runaway backstop ≈ 10× the 200k window; ≤ 0 disables), threaded from `composition` into
  `execute_agent_run` like the wall-clock timeout.
- **No migration, no new dependency, no behavioural gateway change** (`stream_usage=True` only
  makes the api-side parse what the gateway already sends).

## Consequences

- **R4 is now real where it matters.** A run cannot spend unbounded tokens; a pathological loop
  or over-eager fan-out is halted at a hard ceiling, completing the "Strategy + safety" story
  (Slice E's estimate + doctrine + quota + this budget). The honest caveat from Slice E is
  discharged: cost-safety no longer rests only on the model honouring an estimate.
- **The default ceiling is uncalibrated.** 2M is a backstop, not a tuned cap: generous enough
  not to clip a legitimate multi-turn / bounded-fan-out run (8 subagents each near a 200k window
  can legitimately approach ~1.5M), low enough to bound a true runaway. Precise calibration
  needs per-run token telemetry — which is exactly the persistence deferred in option 2; until
  then the value is tunable via config and the *mechanism* (not the number) is what shipped.
- **Token totals are not persisted/observable yet.** The brake is in-memory; a settled run shows
  `cap_exceeded` + `token_budget_exceeded` but not its token count. `agent_runs.cost_usd` stays
  NULL. Persisting `total_tokens` (and deriving `cost_usd`) is a recorded follow-up that also
  unlocks calibration and a cockpit cost surface.
- **`stream_usage=True` is global** (every gateway chat model, not only agent runs). It is
  additive — a usage-only final chunk with empty content, which the runner's
  `on_chat_model_stream` delta path already skips — so it is benign for the chat path and useful
  everywhere.
- **Nested-fan-out attribution is correct but coarse.** Subagent model turns report their usage
  on `on_chat_model_end` events the lead's runner consumes, so they count toward the run budget
  (the point — fan-out is the runaway vector). The budget is a whole-run total, not per-subagent.
- **Degraded usage is fail-open.** If a provider returns no usage (`usage_metadata` absent),
  `_usage_total` returns 0 and the brake never fires spuriously — the run is still bounded by
  `max_steps`/wall-clock. A provider that under-reports usage weakens the brake; that is the
  honest limit of trusting provider-reported tokens (a tokenizer-side estimate is a possible
  future hardening).
- **Gate (ADR-F015 — the runaway-token-budget halt is the deterministic CI gate).**
  `tests/agents/test_agent_runner.py`: a looping model reporting fixed tokens/turn halts as
  `cap_exceeded` + `token_budget_exceeded` before `max_steps`; `budget <= 0` disables; a normal
  run under budget completes unaffected; a final-answer turn is never cut off mid-deliverable.
  The fake `ScriptedToolCallingModel` emits a trailing usage chunk (mirroring ChatOpenAI's
  final include-usage chunk), verified in-container to surface on the merged event.
