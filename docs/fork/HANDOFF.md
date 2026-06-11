# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-11, end of F0-S7)

- Merged to main through #36; **F0-S7 (SSE v2 + subagent identity + conversation extraction) is
  PR #37** — merges on green via the ADR-F005 gate, full evidence in the PR. All fork ADRs
  F001..F008 `accepted`.
- **The agents surface streams like Claude Code** (ADR-F006 wire spec):
  `GET /api/v1/agents/runs/{run_id}/stream` emits the AI SDK UI Message Stream v1 — settled rows
  as `data-step` parts (part id = row id, same-id reconciliation), live reasoning deltas, tool
  frames keyed by settled `tool_call` row ids, `data-plan` for `write_todos`, terminal text block
  = settled `final_answer`. `RunStreamBroker` (in-process, lifespan-owned) bridges runner →
  endpoint; the DB-tail fallback alone is a complete stream (arq-migration-proof). Polling stays
  the contract and the fallback.
- **Subagent identity persists**: migration **0051** added `agent_run_steps.parent_step_id`
  (innermost enclosing tool dispatch; NULL = root loop; pre-S7 rows honestly NULL). The UI indents
  nested steps; F1's subagent tree and S9's eval read this column.
- **The conversation surface is a component**:
  `web/src/lib/lq-ai/components/agents/ConversationPanel.svelte` (composer, turns/steps, thinking
  ribbon, uploads, polling + stream). The agents route is chrome (header, conversations list,
  capability rail via bound props, head/copy slots). Thread switching = `{#key}` remount;
  draft prompt + matter selection survive as two-way-bound props. Helpers moved to
  `web/src/lib/lq-ai/agents/helpers.ts` (lib components must not import from routes).
- Dev stack: 8 services healthy; DB at migration **0051**; api boot logs
  `agent checkpointer ready (AsyncPostgresSaver)`. Gateway aliases `smart`/`fast`/`budget` →
  `minimax/MiniMax-M3`; key in `.env`.
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Web gates (host, node 20): `cd web && npm run check` (0 errors) +
  `npm run test:frontend -- --run` (773/773).
- API suites run containerized (no host 3.12): throwaway `pgvector/pgvector:pg16` + the api image
  with the repo mounted — **and `skills/` mounted at `/skills`** (migration 0032 seeds from it):
  ```bash
  docker run -d --name s7pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s7pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```

## Done (F0-S7) — SSE v2 + the two pulled-forward MUSTs

- Emitter (`api/app/agents/stream.py` + endpoint in `api/app/api/agent_runs.py`): broker pub/sub
  with subscriber cap + mid-run-attach seeding (openers of in-flight reasoning/tool blocks, spec
  conformance), channel released when the last subscriber leaves (no leak), orphaned-at-'running'
  runs end the stream at the poller's 330s cutoff, every exit ends the message before `[DONE]`.
  The request session closes BEFORE streaming (a 300s stream must not pin a pool connection);
  the generator reads through `get_stream_session_factory` (a Depends seam — tests bind it to
  the migrated test DB).
- Runner: forwards `on_chat_model_stream` deltas as reasoning blocks; persists
  `parent_step_id` via the `tool_step_ids` map (langchain run id → settled row id); wire
  `toolCallId` IS the settled `tool_call` row id.
- Web: `sse/ui-message-stream.ts` (v1 consumer), `agents/run-stream.ts` (pure reducers — stream
  parts upsert the SAME detail shape polling fills), `agents/server-clock.ts` (Date-header skew;
  closes the F0-S3 staleness carry-over; api CORS now exposes `Date`). Stream failure falls back
  to polling; stream end triggers ONE reconcile fetch.
- Gate: api agents suite 102 passed / 1 skipped; full api suite green (the two OpenAPI contract
  tests now register the stream path, count 123); gateway 572 passed + mypy --strict clean; web
  773/773 + svelte-check 0 errors; live timestamped wire capture + idempotent replay capture in
  `docs/fork/evidence/f0-s7/`; Cypress f0-s7-stream + f0-s3 + f0-s5 green on the rebuilt stack;
  30-agent adversarial review — 24 confirmed / 0 blockers, fixed or deferred on record.

## Next slice: F0-S8 — matters without leaving the agent (maintainer directive)

Per MILESTONES F0-S8:
- "+ New matter" on the Agents tab reusing the SAME plumbing as the Matters tab:
  `NewMatterModal` + `POST /projects`, full form — the privileged ⇒ tier-floor invariant
  (`ProjectCreateRequest`, api/app/schemas/projects.py ~163-175, `extra='forbid'`) must ride
  along; never a name-only quick-create.
- Prereq refactor FIRST: the modal's hardcoded post-create `goto('/lq-ai/matters/{id}')` moves to
  the Matters page's `onCreated` callback (the caller owns navigation) — find it in
  `web/src/lib/lq-ai/components/NewMatterModal.svelte` (~line 98).
- On create from the Agents tab: bind the new matter (the panel's `selectedMatterId` is now a
  two-way-bound prop on ConversationPanel — set it from the page), clear pending upload chips
  (F0-S5 honesty invariant), refresh the matter list.
- With create-in-place shipped, REMOVE the "No matter — blank workspace" option (ADR-F002:
  free-floating chat is not offered). Mind f0-s3's spec: it currently runs UNBOUND (9 builtin
  rail items) — removing blank workspace changes that spec's setup; update it in the same PR.
- Branch `fork/f0-s8-matter-create` from main (after PR #37 merges).

## Pick up exactly here

1. Read CLAUDE.md → this file → MILESTONES F0-S8 → ADR-F002.
2. Smoke the stack (the F0-S5 snippet still works; note `runs[-1]` is `{run, steps}`):
   POST /agents/runs → poll `GET /agents/threads/{tid}` until `completed True` → follow-up.
3. To see the stream itself:
   `curl -sN http://localhost:8000/api/v1/agents/runs/$RID/stream -H "Authorization: Bearer $TOKEN"`
   — expect `data-step` parts then `text-*`/`data-run`/`finish`/`[DONE]`.

## Carry-overs / review deferrals

- `build_deep_agent` must reject model-bearing subagent specs (gateway bypass) — before F1 fan-out.
- Anthropic adapter: `tool_use`/`tool_result` + block-content translation still pending
  (`grep -rn F0-S1 gateway/app`); anonymization decision for block content pending. Dev model is
  MiniMax (OpenAI-compatible), so nothing blocks F0 on it.
- No cancel endpoint (`cancelled` reserved). A stranded `running` run deadlocks its thread
  (409 thread_busy; UI offers New chat); S7 bounded the STREAM for orphans (330s cutoff both
  sides) but the row itself still needs the arq startup sweep (F1 run-lifecycle durability).
- Checkpoint rows invisible to alembic, not cleaned on delete (`adelete_thread` uncalled) — F1.
- Long conversations exceed the dev model's context before deepagents' summarization triggers —
  ADR-F003 compaction lands F2.
- No audit rows for run kick-off (tool dispatches ARE audited).
- MessageBubble still sanitizes with DEFAULT DOMPurify (legacy surface) — harden when next touched.
- Thinking ribbon under PARALLEL subagent fan-out shares one buffer (S7 review deferral —
  per-block ribbons land with F1's subagent tree).
- S6 deferrals unchanged (Backlog): eslint-9 flat-config migration; path-scoped CSP;
  bare-`<select>` restyle; version-poll auto-reload.

## Gotchas

- **`cy.intercept` BUFFERS streamed responses** — intercepting the SSE route delivers the whole
  stream in one burst and erases the liveness under test (cost a debugging round in S7). Assert
  streaming via its UI effects (the thinking ribbon) instead.
- **Cypress on this box — memory-pressure discipline (zero pg crashes with it):**
  ```bash
  docker stop lq-ai-arq-worker-1   # not needed by the specs; frees ~500MB
  ELECTRON_EXTRA_LAUNCH_ARGS='--js-flags=--max-old-space-size=512' \
    CYPRESS_LQ_AI_MATTER_NAME="S5 PreSeed 1781169832" \
    npx cypress run --spec '…' --config video=false,numTestsKeptInMemory=0
  docker start lq-ai-arq-worker-1
  ```
  PRE-SEED matters with the browser closed (spec headers have the steps). If workers wedge
  ("connection is closed" on every job): `docker compose restart ingest-worker arq-worker`.
- The web image builds in seconds with the stack UP; the container serves a pre-built bundle, so
  `docker compose build web && docker compose up -d web` before debugging a UI change.
- `gh pr create` defaults to the FROZEN upstream repo — always pass
  `--repo sarturko-maker/lq-ai-fork` AND `--head <branch>` (ADR-F001).
- Background merge-watchers end with `git checkout main` — verify the current branch before
  committing slice work (bit us in S5).
- **.env S3 keys**: explicit `S3_ACCESS_KEY`/`S3_SECRET_KEY` never existed in MinIO — they stay
  commented out so compose falls back to MinIO root creds (backup: `.env.bak-f0-s4`).
- After any migration: rebuild `api` + `arq-worker` + `ingest-worker` together. Containerized
  pytest needs `skills/` at `/skills`; ruff needs the repo-root `ruff.toml` visible (mount the
  REPO, workdir `/repo/api`) or it mass-reformats.
- Upstream has TWO file↔project relations (`project_files` join vs `files.project_id` column);
  matter tools honor the union (ADR-F007).
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers. MiniMax-M3 emits
  `<think>` blocks — the UI collapses them (and the ribbon streams them); never strip them in
  the API.
