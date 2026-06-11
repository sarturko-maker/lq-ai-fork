# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-11, end of F0-S5)

- Merged to main through #31 (F0-S4 #30, S5 scope promotion #31); **F0-S5 = PR #32**.
  ADR-F001..F006 accepted; **ADR-F007 (matter document scope) and ADR-F008 (conversation
  identity: `agent_threads` + Postgres checkpointer) are `proposed` — maintainer accepts**.
  Merges follow ADR-F005's 5-part gate — no exceptions.
- Dev stack: 8 services healthy on the S5 images; DB at migration **0050**; the api log shows
  `agent checkpointer ready (AsyncPostgresSaver)` on boot (its tables are library-managed via
  `setup()`, NOT alembic — deliberate, ADR-F008). Gateway aliases `smart`/`fast`/`budget` →
  `minimax/MiniMax-M3` (tier 4); key in `.env`.
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Host `web/node_modules` installed (node 20) — web gates run on the host:
  `npm run check:lq-ai` (0 errors) + `npm run test:frontend -- --run` (749/749).
- API suites run containerized (no host 3.12): throwaway `pgvector/pgvector:pg16` + the api image
  with the repo mounted — **and `skills/` mounted at `/skills`** (migration 0032 seeds from it):
  ```bash
  docker run -d --name s5pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s5pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```

## Done (F0-S5) — multi-turn conversations + composer upload (ADR-F008)

- **Conversation identity**: `agent_threads` (migration 0050) — id doubles as the langgraph
  checkpointer thread key; the THREAD owns the Matter binding, each run snapshots it; pre-S5 runs
  backfilled as one-run threads (`thread_id = run id`); `agent_runs.thread_id` NOT NULL; partial
  unique index = at most one running run per thread (API maps the IntegrityError to 409).
- **Durable state**: `AsyncPostgresSaver` over its own psycopg pool
  (`api/app/agents/checkpointer.py`), opened in the lifespan, idempotent `setup()`, degraded-not-
  crashed on init failure (new runs single-shot; follow-ups refused — honest, never silent context
  loss). `psycopg[binary]` added to pyproject (slim image has no libpq).
- **Follow-up rules** (POST /agents/runs with `thread_id`): 404 unowned (no existence leak);
  409 `thread_busy` / `thread_not_continuable` (latest run must be `completed` AND checkpoint
  state must exist — interrupted loops strand dangling tool calls; repair pathway is a later
  slice); 422 when `project_id` is sent on a follow-up (the binding is the thread's). New threads
  get a bounded-prompt title (auto-titling F1/F2).
- **Thread endpoints**: GET `/agents/threads` (paginated, newest activity, newest-run badge);
  GET `/agents/threads/{id}` (runs oldest-first with steps + advisory `continuable`) — the UI's
  polling target.
- **Web**: conversation view (turns = prompt + steps + answer), follow-up composer on a settled
  thread, "New chat", conversations list; matter select only for new chats (binding fixed at
  creation). **Composer upload**: attach + drop zone → `POST /files` with the bound matter's
  `project_id` (ADR-F007 upload-time membership — S4 tools see it with zero wiring), ingestion
  chips pending → processing → ready/failed polled at 2s, attach disabled with an honest hint
  when unbound (ADR-F002).
- **Verification**: agents suite green incl. NEW multi-turn memory tests (scripted model proves
  the follow-up sees turn 1 through the REAL composition; cross-thread isolation; real
  AsyncPostgresSaver round trip against the test DB); migration 0050 up/down/up + seeded backfill
  verified on a throwaway pg; LIVE multi-turn proven on MiniMax-M3 (follow-up recalled the prior
  question + its own answer with no tools); Cypress f0-s5 (3 acts: grounded turn → memory
  follow-up → composer upload grounds turn 3) + f0-s3 + f0-s4; full counts in PR #32.

## Next slice: F0-S6 — the shell shed (ADR-F006)

Per MILESTONES F0-S6:
- Extract the lq-ai code (~50k LOC under `web/src/{lib,routes}/lq-ai/`, zero husk imports —
  audited in the ADR-F006 research) into a standalone lean SvelteKit app; kill the OpenWebUI husk,
  its Python backend container, and the §4 branding obligation.
- Includes the per-file provenance pass over the lq-ai `.svelte` components (~123 files) and the
  `app.html` theme-script rewrite (REWRITE, not copy — Apache-2.0 relicensing condition).
- Verification bar: screenshot diff + the f0-s3 AND f0-s5 Cypress specs green on the new shell
  (f0-s5 exercises conversation + upload — the deepest UI path we have).
- Watch: the `webui.db` login-breaking bootstrap dies with the husk; Cypress support file's
  spec-name pattern (`/^f\d+-/`) and `cy.registerAdmin()` shim become removable.
- S7 (SSE v2, AI SDK stream spec) lands on the clean shell — the wire-spec is accepted (ADR-F006);
  S5's thread/run/step rows are the settled records its `data-*` parts will reference.

## Pick up exactly here

1. Read CLAUDE.md → this file → MILESTONES F0 → ADR-F006 (the S6 contract) → ADR-F008 (what the
   agents surface now is).
2. Branch `fork/f0-s6-shell-shed` from main (after PR #32 merges).
3. Smoke the stack (multi-turn, end to end):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-local-Pw1!"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
PID=$(curl -s http://localhost:8000/api/v1/projects -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
TID=$(curl -s -X POST http://localhost:8000/api/v1/agents/runs -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"What is the liability cap? Search the matter documents.\",\"project_id\":\"$PID\"}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['thread_id'])")
# poll GET /api/v1/agents/threads/$TID until completed+continuable, then:
curl -s -X POST http://localhost:8000/api/v1/agents/runs -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Without tools: what did I just ask you?\",\"thread_id\":\"$TID\"}"
# the answer must recall the first question — that's the checkpointer working.
```

## Carry-overs / review deferrals

- `build_deep_agent` must reject model-bearing subagent specs (gateway bypass) — before F1 fan-out.
- Anthropic adapter: `tool_use`/`tool_result` + block-content translation — S7
  (`grep -rn F0-S1 gateway/app`); anonymization decision for block content still pending.
- No cancel endpoint (`cancelled` reserved; R5 honors it at the tool boundary; a checkpointer
  interrupt is now possible — pairs with the thread-repair pathway for failed/capped threads).
- Checkpoint rows are invisible to alembic and NOT cleaned up on thread/user delete
  (`adelete_thread` exists, no delete surface yet) — fold into F1's retention/cleanup work
  (Backlog line exists).
- Runs in-process via BackgroundTasks (arq migration + startup sweep). **Ingest jobs share the
  fragility**: a worker/db hiccup mid-ingest strands files at `processing` forever — fold into
  the arq/orphan-sweep work. NEW since S5: a stranded `running` run now also **deadlocks its
  thread** (409 `thread_busy` forever; the UI offers New chat) — the startup sweep must settle
  orphans. The per-user flood brake is also check-then-insert racy (pre-S2; bounded overshoot).
- Long conversations will exceed the dev model's context BEFORE deepagents' default summarization
  triggers (~170k tokens) — ADR-F003's budget-alias compaction lands in F2; until then a very long
  thread eventually fails its runs honestly. Related latent nit: a summarization middleware model
  turn would be top-level (not tool-nested) and could be mis-read as a final-answer candidate —
  revisit `_is_nested` when compaction lands.
- No audit rows for run kick-off (tool dispatches ARE audited since S4).
- Rail "lit" wording diverges from ADR-F002 ("lit = loaded" vs "lit = used") — reconcile in F1.
- MessageBubble (upstream surface) shares the image-exfil DOMPurify gap fixed on the Agents tab.
- Client clock skew can mistrigger the 330s staleness cutoff — derive now from a response header
  when SSE lands (TODO in page-helpers.ts).
- deepagents' summarization middleware will eventually compact long threads in-context; ADR-F003's
  budget-alias compaction + digests land in F2 — watch token growth on long conversations.

## Gotchas

- **Cypress on this box: always `--config video=false`** — and even videoless Electron can trigger
  postgres SIGPIPE crash-recovery windows that kill in-flight ingest jobs (files stick at
  `processing`). For f0-s4/f0-s5, PRE-SEED with the browser closed and pass
  `CYPRESS_LQ_AI_MATTER_NAME=…` (spec headers have the steps; f0-s5's composer upload can't be
  pre-seeded — it IS the test). After postgres crash cycles the WORKERS' DB pools can wedge
  ("connection is closed" on every job) — `docker compose restart ingest-worker arq-worker` heals.
- **.env S3 keys**: explicit `S3_ACCESS_KEY`/`S3_SECRET_KEY` never existed in MinIO — they're
  commented out so compose falls back to the MinIO root creds. Keep it that way
  (backup: `.env.bak-f0-s4`).
- **Web image build OOMs unless the stack is stopped first**: `docker compose stop &&
  DOCKER_BUILDKIT=1 docker compose build web && docker compose up -d` (~5.5GB free needed).
- `gh pr create` defaults to the FROZEN upstream repo — always pass
  `--repo sarturko-maker/lq-ai-fork` (ADR-F001: no upstream interaction).
- **Name fork Cypress specs `fN-…`** (pattern in cypress/support/e2e.ts): any other name
  bootstraps an OpenWebUI user that BREAKS `/lq-ai/*` (delete the rows from `user` + `auth` in
  the web container's `webui.db` if it happens). Dies with the husk in S6.
- After any migration: rebuild `api` + `arq-worker` + `ingest-worker` together. Containerized
  pytest needs `skills/` mounted at `/skills` (migration 0032 seeds playbooks from it). Ruff must
  run with the repo-root `ruff.toml` visible (mount the REPO, workdir `/repo/api`) or it
  mass-reformats at defaults.
- Upstream has TWO file↔project relations: `project_files` (attach endpoint) and
  `files.project_id` (upload form field, what the composer upload uses). Matter tools honor the
  union (ADR-F007).
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers. MiniMax-M3 emits
  `<think>` blocks — the UI collapses them; never strip them in the API.
