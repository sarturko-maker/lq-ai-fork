# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (end of F1-S1 — runs are unkillable)

- **F1-S1 merged via PR (see merge commit on main)**: run-lifecycle durability
  per the ratified re-plan (`docs/fork/plans/F1-replan.md`) + ADR-F009
  (at-most-once, settle-FAILED-never-auto-resume — read it before touching
  the lease/sweep/cancel machinery).
- Dev stack: 8 services healthy; **DB at migration 0052** (agent_runs lease
  columns); api + arq-worker + ingest-worker rebuilt together on slice code;
  eval fixture matters still seeded ("S9 Eval — Single Doc 9001" / "S9 Eval —
  Batch Fanout 9002").
- Gateway aliases smart/fast/budget → minimax/MiniMax-M3; ONLY the MiniMax
  key is real (CALL-based token plan, not PAYG — budget rules relaxed).
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Suites at gate time: **api 2084 passed / 3 skipped** (containerized,
  throwaway pgvector, alembic head incl. 0052); gateway untouched (S9 counts
  stand); web check 0 errors + 778/778 frontend tests (comment-only change).
- Adversarial review (44 agents, 5 dimensions + security pass): 39 raised,
  35 confirmed (1 blocker — evals conftest import — + 17 should-fix + 17
  nits), ALL fixed in-slice, 4 refuted, 0 pre-existing. Live verification
  (docs/fork/evidence/f1-s1/live-verification.md): kill -9 mid-run → sweep
  settled FAILED at +2m12s → same thread completed a follow-up with context;
  cancel 200 in 0.53s + arq abort delivered; thread delete → checkpoint rows
  0/0/0; post-deploy spot check on final images.

## Done (F1-S1, this slice)

- **Execution moved to the arq worker** (`agent_run_job`, `max_tries=1`,
  timeout 420s, deterministic job id `agent-run:{run_id}`,
  `allow_abort_jobs=True`): BackgroundTasks is gone; enqueue failure settles
  the run `failed` before the 202 returns.
- **Lease + heartbeat + fencing** (`app/agents/lease.py`, migration 0052):
  claim-once (`claimed_by IS NULL`), throttled per-event heartbeat (15s) +
  guard-touch at tool dispatch (commits BEFORE the tool body), fenced
  terminal writes (first writer wins; zombie writes rejected by rowcount;
  runner hard-stops via `RunSettledElsewhere`).
- **Orphan sweep** (startup + every-minute cron): stale heartbeat (120s) →
  FAILED `orphaned: worker heartbeat stale` + active `Job.abort`; unclaimed
  past grace (1200s — ABOVE the shared queue's 900s legacy ceiling) →
  FAILED `orphaned: never claimed`. Settles commit before the audit pass.
- **Cancel endpoint** (`POST /agents/runs/{id}/cancel`): settle-first,
  idempotent, audited, then best-effort abort.
- **Thread repair + admission**: any TERMINAL status admits a follow-up;
  dangling tool_calls repaired pre-invoke from the PINNED checkpoint view
  (deepagents #3789 + the pending-writes window); degraded worker
  checkpointer refuses follow-ups honestly.
- **Retention**: `DELETE /agents/threads/{id}` (+ `adelete_thread`), daily
  checkpoint-GC cron for orphaned lineages; `durability="sync"` on
  checkpointed runs.
- Docs: ADR-F009, plan, research (`run-durability-landscape.md`), evidence.

## Next slice — pick up exactly here

1. **ADR-F009 ACCEPTED by the maintainer (2026-06-12).** F1-S1 is fully closed.
2. Next: **F1-S2 — design-system foundation + Cockpit v0 shell** (the redesign
   the maintainer is keen on: practice areas lined up). Read
   `docs/fork/plans/F1-replan.md` § F1-S2 + § Sequencing FIRST.
3. **MAINTAINER DESIGN RULE (2026-06-12, verbatim, governs ALL UI work):**
   "don't use black background, needs to be clean and professional, cutting
   edge design." Read: light-first professional canvas (Harvey/Legora bar per
   the re-plan), no black/near-black app background; cutting-edge polish.
   This is his ONLY stated constraint — everything else is delegated.
4. S2/S3 ordering: delegated by the maintainer ("my only rule is…") →
   take the re-plan's noted option: SHELL-FIRST, with seeded standard
   practice-area rows shipping in the same PR (real `practice_areas` schema
   lands in S3).
5. shadcn-svelte + bits-ui + paneforge + Tailwind v4 are NEW dependencies —
   SBOM justification per CLAUDE.md; ADR-F006 governs the design system.
   Web container serves a pre-built bundle — rebuild to see anything.
6. The cockpit's status rollups can now trust `last_run_status` — F1-S1's
   whole point. Multi-file slice: explore → written plan
   (docs/fork/plans/F1-S2-…) → implement → full ADR-F005 gate.

## Carry-overs / review deferrals

- Live SSE animation (token deltas) is DEAD in production until a Redis
  pub/sub publisher lands (worker has no broker; DB-tail serves settled
  rows every 2s) — explicit F1-S1 non-goal, backlogged; consider riding F1-S4.
- Flood brake counts queued-but-unclaimed runs: a worker outage can 429 a
  user until the sweep clears (cancel is the escape hatch) — on record in
  ADR-F009; revisit with R4 budgets.
- Two-writers window (zombie checkpoint writes ≤1 heartbeat interval vs an
  immediately-admitted follow-up) — bounded + abort-shortened; proper fix is
  F1-S5's ledger/locking territory.
- Step/audit appends are unfenced (deliberate; ADR-F009 states the exact
  invariant). Guard touch is status-conditional only.
- web STALE_RUNNING_AFTER_MS (330s from started_at) can falsely render a
  queue-delayed run stale (comment updated; run read model doesn't expose
  lease columns) — fix when the cockpit redefines run presentation (S2).
- Mismatch read-noise watch metric (19/20), L2 judge seam unrun, no
  action-tool canary / compaction-survival eval scenarios — unchanged from S9.
- `build_deep_agent` must reject model-bearing subagent specs — F1-S3/S4.
- Anthropic adapter tool_use translation — only if a Claude family joins.
- Conversation compaction (ADR-F003) — F2. MessageBubble legacy DOMPurify.
  wave-c-matters test 3 pre-existing hang — Backlog.

## Gotchas (carried + new)

- **NEW: agent runs execute on the arq-worker** — restarting it mid-run is
  safe (sweep settles, thread repairs) but kills live runs; eval cycles need
  it healthy. After ANY migration: rebuild api + arq-worker + ingest-worker
  together (0052 hit all three).
- **NEW: the arq worker now inits the langgraph checkpointer at startup**
  (degrades to None → follow-ups refused honestly worker-side).
- **NEW: `Job.abort` semantics**: flag is set before the confirmation wait;
  `abort(timeout=2)` + catch TimeoutError = fire-and-forget. arq settles a
  redelivered `max_tries=1` job WITHOUT re-running the body (verified 0.26.3).
- **NEW: langgraph kwarg trap**: `durability=` on `astream_events` CRASHES
  without a checkpointer (`_put_checkpoint_fut` AttributeError) — only pass
  it when thread_id+checkpointer exist (runner does this).
- **NEW: aupdate_state on the deepagents graph needs `as_node="tools"`**
  (plain update → InvalidUpdateError: ambiguous). Un-pinned aget_state
  applies PENDING WRITES; the next invoke discards them — read the pinned
  view (state.config) for repair decisions.
- **NEW: FastAPI 204 routes need `response_class=Response`** (M3-C2 pattern)
  or the suite dies at collection.
- New API endpoints must be registered in tests/test_openapi.py (count
  assert!) + tests/test_endpoints.py exclusion list.
- `cy.intercept` BUFFERS streamed responses — never intercept the SSE route
  under liveness test. The shell scrolls `#lq-main`, not the document.
  Cypress on agents surface: `capture: 'viewport'`; memory-pressure recipe in
  git history (S7 HANDOFF) if needed.
- Web container serves a pre-built bundle — rebuild before debugging UI.
- `gh pr create` defaults to the FROZEN upstream — always
  `--repo sarturko-maker/lq-ai-fork` AND `--head <branch>` (ADR-F001).
  jq is NOT installed — parse `gh --json` with python3.
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers.
  Containerized pytest needs `skills/` at `/skills`; ruff needs repo-root
  ruff.toml; container-written mounted files are root-owned (chown in-
  container). Throwaway-pg test recipe: see git history or below.
  ```bash
  docker run -d --name s9pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s9pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```
- NEVER `docker compose down -v`; NEVER host-side alembic against the dev DB.
- `.env` S3 keys stay commented out (backup `.env.bak-f0-s4`).
- MiniMax-M3 emits `<think>` inline AND a `reasoning` delta field; both
  round-trip the gateway verbatim. `final_answer` retains `<think>`.
- GET /agents/runs/{id} returns `{run, steps}`; `files.ingestion_status`
  CHECK allows pending/processing/ready/failed; ORM models don't declare FK
  edges — flush per dependency level. Eval cycles run SEQUENTIALLY, never
  with Cypress.
