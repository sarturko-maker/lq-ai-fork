# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-10, end of F0-S2)

- F0-S1 merged (#24, `816f5ac`); governance merged (#25, `39ba43f` — ADR-F005 agent-merge policy,
  F0 re-sequenced). F0-S2 on branch `fork/f0-s2-agent-runs` → PR (merge it first if still open).
- ADR-F001..F005 accepted. Merges follow ADR-F005's 5-part gate — no exceptions.
- Dev stack: 8 services healthy; api/gateway/workers rebuilt from F0-S2 code; DB at migration 0048.
  Gateway aliases `smart`/`fast`/`budget` → `minimax/MiniMax-M3` (tier 4); key in `.env`. Gateway
  live config sits in a named volume (copy seed + `docker compose restart gateway` to change).
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!

## Done (F0-S2)

- **Agent-run records**: `agent_runs` + `agent_run_steps` (migration 0048) — every loop step
  persisted as it completes (`model_turn`/`tool_call`/`tool_result`, astream_events v2; one COMMIT
  per step so pollers see live progress). Interim caps: `max_steps` (default 20), wall-clock 300s;
  statuses running/completed/failed/cancelled/cap_exceeded. `guarded_tool_call`/R4 is F1 (seam
  marked in `runner.py`, ADR-F002).
- **Endpoints**: POST `/api/v1/agents/runs` (202, BackgroundTasks), GET `/agents/runs/{id}` →
  `{run: {...}, steps: [...]}` ordered — **this is the S3 polling contract** — GET `/agents/runs`
  paginated. Cross-user = 404.
- **Gateway**: `tools`/`tool_choice` typed on the request schema (ollama adapter switched off
  `model_extra` — regression caught by suite); `agent_loop` in `_KNOWN_PURPOSES`; streaming test
  pins tool_call delta passthrough.
- **LIVE PROOF**: run `de73320c…` completed via the real endpoint — 4 ordered steps, final answer
  quotes Clause 7.2, routing-log rows tagged `purpose='agent_loop'` (after gateway rebuild — the
  fallback-to-'chat' on unknown purpose worked as designed before it).
- Evidence: api 1949 passed (+19) / mypy clean; gateway 571 passed / mypy --strict clean.

## Next slice: F0-S3 — FIRST VISIBLE AGENT (Agents tab v0)

Per MILESTONES F0-S3: a new tab under `web/src/lib/lq-ai/` + route `/lq-ai/agents`:
- One hardcoded preview area card ("Commercial — preview"). One message box → POST `/agents/runs`.
- **Capability rail v0**: list the run's tools (for now: `demo_read_clause` + deepagents builtins),
  dim → lit as steps complete; poll GET `/agents/runs/{id}` every ~2s while status=running
  (render-deterministic: UI reads settled steps, never a stream). Tool calls + final answer
  rendered; previous runs listed (GET `/agents/runs`).
- MiniMax-M3 emits `<think>…</think>` in `final_answer` and step summaries — strip or collapse it
  in the UI (do NOT strip in the API; the record keeps the honest full text).
- Follow web house style: `web/src/lib/lq-ai/` isolation, typed API client (`api/client.ts`
  patterns), tabs.ts entry + TopTabBar gate, Vitest for stores/parsing. Cypress optional this slice.
- Defer: SSE (S5 upgrades polling to live), practice_areas schema (F1), auth-scoped area config (F1).

## Pick up exactly here

1. Read CLAUDE.md → this file → MILESTONES F0. 2. Merge the F0-S2 PR if still open (gate per
   ADR-F005). 3. Branch `fork/f0-s3-agents-tab` from main. 4. Smoke the contract:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-local-Pw1!"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s -X POST http://localhost:8000/api/v1/agents/runs -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"prompt":"What is the liability cap? Use your tools."}'
# then poll GET /api/v1/agents/runs/{id} — UI shape: {run:{status,final_answer,...}, steps:[{seq,kind,name,summary}]}
```

5. Remember: rebuild `web` container to see UI changes (pre-built bundle, no HMR).

## Carry-overs / review deferrals (S2 → later)

- Factory key exposure: `http_async_client` seam added; FINISH by moving the gateway key fully out
  of `default_headers` (repr/LangSmith leak surface) — S3 or S4.
- `build_deep_agent` must reject model-bearing subagent specs (gateway bypass guard) — before F1
  subagent fan-out.
- Anthropic adapter: `tool_use`/`tool_result` + block-content translation — S4/S5 (`grep -rn F0-S1
  gateway/app`); anonymization for block content — decision pending (skip is observable; fully
  skipped requests report `anonymization_applied=False`).
- No cancel endpoint yet (`cancelled` status reserved); `cost_usd` NULL until F1 R4; runs execute
  in-process via BackgroundTasks (arq migration later); audit rows for run kick-off not yet written.

## Gotchas

- **In-place pip upgrade clobbers langgraph-prebuilt**: `pip install --force-reinstall --no-deps
  langgraph langgraph-prebuilt langgraph-checkpoint` (fresh image builds unaffected).
- After any migration: rebuild `api` + `arq-worker` + `ingest-worker` together. After gateway code
  changes: rebuild `gateway` (a stale gateway silently downgraded `agent_loop` → 'chat').
- Host Python is 3.11; api/gateway need 3.12 — all tooling in containers (`--entrypoint sleep`;
  the api image entrypoint runs alembic and dies without `DATABASE_URL`).
- Tests: throwaway `pgvector/pgvector:pg16` only, never the live compose postgres.
- langgraph 1.x: no `__version__`; `add_node` needs named-`state` callback protocols.
