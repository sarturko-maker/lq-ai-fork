# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-10, end of F0-S4)

- Merged to main through #29 (F0-S1 #24, governance #25, F0-S2 #26, F0-S3 #27, ADR-F006 #28/#29);
  **F0-S4 = PR #30**. ADR-F001..F006 accepted; **ADR-F007 (matter document scope = attach join ∪
  upload-time column) drafted in #30, status proposed — maintainer accepts**. Merges follow
  ADR-F005's 5-part gate — no exceptions.
- Dev stack: 8 services healthy on the S4 images; DB at migration **0049**. Gateway aliases
  `smart`/`fast`/`budget` → `minimax/MiniMax-M3` (tier 4); key in `.env`.
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Host `web/node_modules` installed (node 20) — web gates run on the host:
  `npm run check:lq-ai` (0 errors) + `npm run test:frontend -- --run` (739/739).
- API suites run containerized (no host 3.12): throwaway `pgvector/pgvector:pg16` + the api image
  with the repo mounted — **and `skills/` mounted at `/skills`** (migration 0032 seeds from it):
  ```bash
  docker run -d --name s4pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s4pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/agents/ -q"
  ```

## Done (F0-S4) — real tools on real documents; demo DELETED

- **Matter binding**: optional `project_id` on `POST /agents/runs` (owned + active or 404 — no
  existence leak; migration 0049, FK `SET NULL`); returned in `AgentRunRead`; matter dropdown in
  the composer; matter chip on the run header.
- **Real tools** (`api/app/agents/tools.py`): `search_documents` (websearch_to_tsquery FTS over the
  matter's chunks — works with NO embedding provider; empty query → inventory; no hits → honest
  message) and `read_document` (full `normalized_content` by filename, 40k-char bound with an
  honest truncation notice). Injected ONLY when the run is matter-bound. **Matter membership is
  the UNION of `project_files` (attach endpoint) and upload-time `files.project_id` (`POST /files`
  sets only the column — verified live, no join row).** Owner re-asserted on every query.
- **Minimal guarded chokepoint** (`api/app/agents/guard.py`, ADR-F002 pulled forward): every
  matter-tool dispatch passes `guarded_dispatch` — R6 grant set, R5 run-status re-read (advisory:
  deepagents converts tool exceptions to model-visible errors; hard stop needs cancel+checkpointer,
  S5+), R4 honest no-op (local reads; budgets F1), ONE `agent_run.tool_call` audit row per dispatch
  (counts/types/IDs; `privilege_marked` resolves from the project; error rows carry the exception
  TYPE only).
- **Tier floor / privilege**: matter-bound runs send `lq_ai_project_minimum_inference_tier` +
  `lq_ai_privileged` on the model client's `extra_body` — the chat path's D1/M2-B3 envelope; the
  gateway enforces. Tool-role messages bypass anonymization by design (M2-D2: intact source text).
- **Carry-over closed — factory key exposure**: gateway key now rides an owned
  `httpx.AsyncClient`'s headers (`build_gateway_http_client`), never `ChatOpenAI.default_headers`
  (serializable → dump/trace leak). `execute_agent_run` takes the model INJECTED (pure executor);
  `_run_in_background` is the composition point and owns the client lifecycle. Pinned by test:
  the key never appears in `model_dump_json()`.
- **Web**: rail = 9 builtins, +2 matter tools (first) only when bound — the honest model-visible
  universe; natural-language step titles (UI-only; rows keep raw name + args verbatim); closing
  model turn deduplicated against `final_answer` by exact server-bound comparison
  (`visibleSteps`, pure + tested).
- **Adversarial review (48-agent workflow)** confirmed 20 findings (2 should-fix clusters + nits);
  all fixed in-branch — most load-bearing: composition failures now FINALIZE the run as 'failed'
  (`mark_run_failed`, never strands 'running'/flood-brake); guard's audit-failure path now rolls
  back (a failed audit flush no longer masks the tool result); binding re-validated (owner +
  archived) at execution time; `_run_in_background` got injection seams + real composition tests.
- **Verification**: FULL api suite + mypy containerized (counts in PR #30); web **0 svelte-check
  errors, 740/740 Vitest**; live Cypress **f0-s4 1/1** (seeded matter + generated MSA PDF → model
  dispatched `search_documents` → answer cites f0-s4-msa.pdf p.1 Clause 7.2) and **f0-s3 1/1**;
  screenshots in `docs/fork/evidence/f0-s4/`. Live API run transcript in the PR.

## Next slice: F0-S5 — multi-turn + new chat + composer upload

Per MILESTONES F0-S5:
- Conversations on the **Postgres checkpointer** (langgraph; first consumer in the codebase) so a
  follow-up message continues the SAME agent state — tool results, todos, workspace files survive.
- Follow-up composer on a settled run; "New chat" within the area; chat/run list grouped by
  conversation on the agents page. The legacy single-turn chat path (`chats.py:1370`) stays LEGACY.
- **Composer file upload** (promoted from Backlog by the maintainer, 2026-06-11): attach button +
  drop zone in the agent composer → `POST /files` with the bound matter's `project_id` — that's
  ADR-F007's upload-time membership path, so S4's `search_documents`/`read_document` see the
  document with zero extra wiring. Show ingestion status in the composer (pending → ready; poll
  the file row). Requires a Matter selected — an unbound upload has no home (ADR-F002). Reuse
  `ChatPanel.svelte`'s upload pattern (`filesApi.uploadFile(file, {project_id})`); note the
  ingest-job fragility gotchas below when testing this live.
- Watch blockers: the gateway Anthropic adapter still drops `tools` (irrelevant for MiniMax dev,
  prerequisite for any Anthropic model — pair with the S5/S7 block-content translation carry-over);
  `cancelled` status is still reserved — a cancel endpoint becomes meaningful now that R5 denies
  dispatch on non-running runs.
- Design call to draft in the PR (ADR if it crosses module boundaries): conversation identity —
  reuse `agent_runs` with a `thread_id`, or a new `agent_threads` table the runs FK into.

## Pick up exactly here

1. Read CLAUDE.md → this file → MILESTONES F0 → ADR-F002/F004 (+F006 for what S6/S7 will demand
   of S5's shapes).
2. Branch `fork/f0-s5-multi-turn` from main (after the S4 PR merges).
3. Smoke the stack (matter-bound run end to end):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-local-Pw1!"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
PID=$(curl -s http://localhost:8000/api/v1/projects -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
curl -s -X POST http://localhost:8000/api/v1/agents/runs -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"What is the liability cap? Search the matter documents.\",\"project_id\":\"$PID\"}"
# poll GET /api/v1/agents/runs/{id} — or watch http://localhost:3000/lq-ai/agents
```

## Carry-overs / review deferrals

- `build_deep_agent` must reject model-bearing subagent specs (gateway bypass) — before F1 fan-out.
- Anthropic adapter: `tool_use`/`tool_result` + block-content translation — S5/S7
  (`grep -rn F0-S1 gateway/app`); anonymization decision for block content still pending.
- No cancel endpoint (`cancelled` reserved; R5 in `agents/guard.py` already honors it at the tool
  boundary); `cost_usd` NULL until F1 R4; runs in-process via BackgroundTasks (arq migration +
  startup sweep). **Ingest jobs share the fragility**: a worker/db hiccup mid-ingest strands files
  at `processing` forever (seen live) — fold into the arq/orphan-sweep work.
- No audit rows for run kick-off (tool dispatches ARE audited since S4).
- Rail "lit" wording diverges from ADR-F002 ("lit = loaded" vs "lit = used") — reconcile in F1.
- MessageBubble (upstream surface) shares the image-exfil DOMPurify gap fixed on the Agents tab.
- Client clock skew can mistrigger the 330s staleness cutoff — derive now from a response header
  when SSE lands (TODO in page-helpers.ts).

## Gotchas

- **Cypress on this box: always `--config video=false`** — and even videoless Electron can trigger
  postgres SIGPIPE crash-recovery windows that kill in-flight ingest jobs (files stick at
  `processing`). For the f0-s4 spec, PRE-SEED with the browser closed and pass
  `CYPRESS_LQ_AI_MATTER_NAME=…` (spec header has the steps). After postgres crash cycles the
  WORKERS' DB pools can wedge ("connection is closed" on every job) —
  `docker compose restart ingest-worker arq-worker` heals them.
- **.env S3 keys**: the original `.env` set explicit `S3_ACCESS_KEY`/`S3_SECRET_KEY` that never
  existed in MinIO — every upload 500'd since first boot. They're now commented out so compose
  falls back to the MinIO root creds. If `.env` is ever regenerated, keep it that way (backup:
  `.env.bak-f0-s4`).
- **Web image build OOMs unless the stack is stopped first**: `docker compose stop &&
  DOCKER_BUILDKIT=1 docker compose build web && docker compose up -d` (~5.5GB free needed). First
  boot of a fresh web image downloads HF models — minutes to healthy.
- `gh pr create` defaults to the FROZEN upstream repo — always pass
  `--repo sarturko-maker/lq-ai-fork` (ADR-F001: no upstream interaction).
- **Name fork Cypress specs `fN-…`** (or `lq-ai-…`): any other name bootstraps an OpenWebUI user
  that BREAKS `/lq-ai/*` (delete the `admin@example.com` rows from `user` + `auth` in the web
  container's `webui.db` if it happens).
- After any migration: rebuild `api` + `arq-worker` + `ingest-worker` together. Containerized
  pytest needs `skills/` mounted at `/skills` (migration 0032 seeds playbooks from it).
- Upstream has TWO file↔project relations: `project_files` (attach endpoint, what the Projects UI
  lists) and `files.project_id` (set by upload's form field, NO join row). Matter tools honor the
  union — keep that in mind for any F1 file UX.
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers. MiniMax-M3 emits
  `<think>` blocks — the UI collapses them; never strip them in the API.
