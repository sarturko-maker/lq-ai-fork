# F1 re-plan — slice list (draft for maintainer edit, 2026-06-12)

Status: DRAFT — written at the F0/F1 milestone boundary (CLAUDE.md: re-plan at
milestone boundaries). F0 closes with S9 (model qualification gate merged; see
`docs/fork/model-compatibility.md`). Inputs: MILESTONES.md § F1, the #36
re-plan directive (run-lifecycle durability first), and
`docs/fork/research/deepagents-ecosystem.md` §1.4/§5 (durability facts,
landmines #1/#6/#7/#8, stream-events adapter, agent.json shape).

The maintainer edits this list before any F1 work starts. Slices are vertical
(end-to-end, runnable, testable, ≤2–3 days, one PR each).

## F1-S1 — Run-lifecycle durability (arq + sweep + cancel)

The cockpit must not land on zombie "running" matters; today a stranded run
deadlocks its thread forever (409 thread_busy, no sweep, no cancel).

- Agent runs move from FastAPI BackgroundTasks to **arq** with `max_tries=1`
  (arq is at-least-once; redelivery after a hard worker death would re-run
  the graph — the self-inflicted version of langgraph platform's sweeper
  bug #7417).
- **`durability="sync"`** on graph invocation (default "async" can lose the
  checkpoint for a step whose side effects ran; ecosystem appendix flags the
  sync-vs-exit tension — start correctness-first, revisit only if checkpoint
  bloat measures badly).
- **Startup + periodic orphan sweep** keyed off `agent_runs` heartbeats
  (heartbeat from inside the stream loop, per event — deepagents subagents
  run minutes inside one tool call; a per-job heartbeat would false-orphan
  live runs, the exact #7417 failure). Orphans settle as FAILED; **resume is
  a user action, never automatic** — safe auto-resume needs the
  `(run_id, tool_call_id)` idempotency ledger (S3 below).
- **Lease/fencing** (`claimed_by`/`claimed_at`/fencing token checked at
  `guarded_tool_call`): OSS langgraph has no coordination preventing two
  executors resuming one thread; the sweep must never re-dispatch a live run.
- **Cancel endpoint**: arq `Job.abort()` (`allow_abort_jobs=True`), runner
  finalizer catches `BaseException` (CancelledError is not Exception),
  settles `status=cancelled`; cooperative stop-flag check in
  `guarded_tool_call` gives between-tool-calls cancel for free.
- **Regression test: cancel mid-tool-call** — `PatchToolCallsMiddleware`
  permanently wedges threads on cancel-mid-tool-call, OPEN at deepagents
  0.6.8 (#3789). If it wedges on our pin: exclude the middleware via the
  HarnessProfile seam (landed in S9) and re-test; settled rows stay the
  source of truth so a wedged langgraph thread is recoverable.
- **Thread repair**: a failed/capped/cancelled latest run no longer makes the
  thread permanently non-continuable (today one bad turn kills the matter
  conversation).
- **Checkpoint retention rides along** (Backlog item, pulled in because the
  sweep job is being written anyway): `adelete_thread()` wired into thread
  delete; time-based DELETE for expired checkpoint rows ("90%+ of DB is
  expired checkpoints" in production reports). Migration obligations per
  CLAUDE.md dev rules (rebuild api + both workers together).
- Ingest-job orphan sweep rides along (same fragility family).

DB: `agent_runs` gains heartbeat_at / claimed_by / fencing columns +
`cancelled` status. Verification: kill -9 the worker mid-run → sweep settles
the run FAILED and the thread accepts a new turn; cancel mid-fan-out → thread
continuable; checkpoint rows for a deleted thread are gone.

## F1-S2 — Design-system foundation + Cockpit v0 shell

- shadcn-svelte + bits-ui + paneforge + Tailwind v4; semantic intent tokens,
  light+dark; bespoke agent components (reasoning ribbon, plan/task/tool
  cards) — panels land on the new system, never the S6 ad-hoc CSS (ADR-F006).
- Login lands in the cockpit; LEFT panel lists `practice_areas` rows (S3's
  auto-landing stays retired; unconfigured areas are INERT cards).
- Matters/programmes under an area with activity rollups (`AgentThread`
  carries project_id + last_run_status — a group-by away), pick-or-create in
  place (S8 plumbing), resume into conversation; "unfiled conversations"
  bucket for legacy unbound threads.
- Needs F1-S3's `practice_areas` rows to exist first IF the schema slice is
  cheap — otherwise ship the shell against a seeded standard-areas table in
  the same PR (maintainer call).

## F1-S3 — `practice_areas` schema + per-area Deep Agent

- Schema: name, unit-of-work label, area profile, bound skills/playbooks/
  MCPs, default tier floor; `projects.practice_area_id` (nullable); audit
  rows gain `practice_area_id`. Config vocabulary mirrors deepagents-cli's
  agent.json/skills/subagents folder shape (ecosystem §1.4) — declarative
  shape data consumed by one renderer, no per-area code branches (ADR-F004).
- Per-area `create_deep_agent`: area system prompt, area-scoped skills,
  subagent fan-out. **Subagent specs are security surfaces**: `permissions`
  REPLACE the parent's, tools OVERRIDE, middleware does not inherit — area
  config generation emits complete per-subagent declarations, and
  `build_deep_agent` rejects model-bearing subagent specs (gateway bypass —
  S4 review carry-over, now load-bearing).
- The unit-of-work noun renders from area config (today hardcoded in 4
  places in the composer).
- Qualification hook: any new model/profile pair an area config names must
  have a row in `docs/fork/model-compatibility.md` (S9 gate).

## F1-S4 — Subagent tree + SSE v3-projection adapter

- Consume deepagents v3 `stream_events` typed projections (`.subagents`,
  `lc_agent_name`) through an explicit adapter module to our SSE v2 frames —
  beta API, internals churn within 0.6.x; the adapter is mandatory.
- **Capture subagent identity at stream time into `agent_run_steps`** —
  transcripts are unrecoverable from checkpoints (#1355); reload can never
  reconstruct the tree. (Settled-rows design hardened into a constraint.)
- Fixes the shared thinking-ribbon buffer under parallel fan-out (S7
  carry-over).
- Validate frame taxonomy against deep-agents-ui and CopilotKit AG-UI before
  freezing types.

## F1-S5 — `(run_id, tool_call_id)` idempotency ledger + attribution fan-out

- Ledger inside `guarded_tool_call`: langgraph resume is replay-based (the
  tools node re-executes; replayed calls carry the SAME tool_call_ids since
  the AIMessage is checkpointed first) — recording results at the chokepoint
  and returning them on replay makes resume/HITL-approve safe. Share the
  unique constraint with audit rows so dedup and audit stay consistent.
- Extend `work_product_attributions` to multi-inference agent runs (blocker
  #6) — prerequisite for trust chrome.
- This is what later makes a "resume" button safe (S1 settles orphans as
  FAILED until this exists).

## F1-S6 — Decision inbox v1 (HITL)

- Maps 1:1 onto shipped API: `interrupt_on={'tool': InterruptOnConfig(...)}`
  → `result.interrupts[0].value.action_requests` → `Command(resume=...)`;
  checkpointer already in place. Persist interrupt payloads as settled
  `agent_run_steps` rows.
- Denial messages carry "what to do instead" (rejected-grant loop class,
  landmine #14 — MiniMax-class models loop on bare denials; regression-test).
- Avoid mixing interrupting and non-interrupting tools in one parallel batch
  (#6626) until the S5 ledger lands.

## F1-S7 — Trust chrome + run artifacts

- Citation/receipt/attribution records for agent runs (ordered AFTER S5's
  attribution extension — receipts against the one-inference-per-message
  schema would write wrong rows).
- Run artifact surface: the NDA-review real task lands its work product as
  files on the Matter (ADR-F002 "deliverables are artifacts, not chat text").
- Tier badge + receipts drawer carried to the agent surface.

## F1-S8 — RIGHT panel + auto-titling/auto-filing resolver

- Three-section capability rail (Skills / Playbooks / Tools; utility tools
  collapsed); dim → lit semantics per section.
- Auto-titling + auto-filing as a service-side, channel-agnostic resolver
  (one-tap confirm when uncertain) — the embryo of inbound channel routing
  (north-star invariant 2; never web-UI-only logic).

## Sequencing notes

- S1 before everything (cockpit must not land on zombie state).
- S2/S3 order is the one real maintainer decision (shell-first with seeded
  rows vs schema-first).
- S5 unlocks S6's parallel-batch caveat and S7's receipts; S4 is independent
  after S1.
- Langfuse self-hosted observability (one CallbackHandler at the runner
  invoke site) can ride any slice as a small addition — flagged, not sliced.

## Explicitly NOT in F1

- Auto-resume of orphaned runs (needs S5 ledger + maintainer sign-off).
- Async subagents preview (graph_id-oriented, "not plug-and-play"; F3 at
  the earliest).
- LangGraph Platform / langgraph-api self-host (license-keyed, phone-home —
  no-SaaS).
- Anthropic adapter tool_use translation (S9 avoided it; pulls in only if a
  Claude-family model is added to the matrix).

---

## Appendix — F1-S1 exploration notes (read-only, 2026-06-12 overnight run)

### arq patterns already in the codebase

- **Playbook worker**: `api/app/workers/arq_setup.py:226-247` — queue
  `arq:m3a6` (shared with Tabular/Autonomous), `job_timeout: 900`, NO
  explicit `max_tries` (arq default 5 — F1-S1 must set `max_tries=1`
  explicitly), no `allow_abort_jobs` anywhere yet. Cron precedent exists:
  `autonomous_idle_watchdog` + `autonomous_schedule_dispatcher`
  (`arq_setup.py:216-223`, minute=0) — the run-orphan sweep can be a
  third cron job in this shape.
- **Ingest worker**: `api/app/workers/document_pipeline.py:240-273` —
  default queue, `max_jobs` from `LQ_AI_INGEST_WORKER_CONCURRENCY`.
- **Enqueue side**: `api/app/workers/queue.py` — module-global cached
  pools (default + m3a6), `RedisSettings.from_dsn(settings.redis_url)`.
- **Worker bootstrap**: both workers' `on_startup` install the skill
  registry; the ingest worker ALSO runs a startup orphan sweep
  (`find_orphaned_files()`, `api/app/pipeline/ingest.py:376-390` —
  re-enqueues rows stuck at pending/processing). Precedent for the
  agent-run sweep; difference: agent runs settle FAILED, never re-enqueue
  (resume needs the S5 ledger).

### Runner seams (what crosses the process boundary)

- Kick-off today: `background.add_task(_run_in_background, run_id, broker)`
  (`api/app/api/agent_runs.py:358`); composition point at
  `agent_runs.py:808-919`.
- **Clean seams** (already callables, work identically in a worker):
  `session_factory_provider` (process-global factory,
  `db/session.py:55-64`), `checkpointer_provider`
  (`get_agent_checkpointer`, None degrades), gateway http client (built
  + closed inside the composition point — no shared state).
- **The one process-local piece**: `RunStreamBroker`
  (`app.state.agent_stream_broker`, `main.py:108` — in-memory pub/sub
  keyed by run_id). The S7 stream endpoint ALREADY serves subscribers
  with no live publisher via the DB-tail fallback (poll every 2s,
  `agent_runs.py:434-461,539-546`) and closes orphaned-at-running
  streams at the 330s cutoff (`agent_runs.py:167-172`). So F1-S1 v1 can
  run worker-side with `broker=None` and lose only live-delta animation
  (settled rows still stream) — Redis pub/sub for live deltas is an
  optional follow-up, exactly as ADR-F004 anticipated ("lossiness only
  costs animation").

### Ingest orphan story (rides along)

- Parse failures set `files.ingestion_status='failed'` directly; storage
  errors raise → arq visibility-timeout requeue (row stays 'processing');
  recovery is STARTUP-ONLY sweep, no cron. F1-S1's cron sweep shape can
  cover both families.
