# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-10, end of F0-S3)

- F0-S1 merged (#24), governance (#25), F0-S2 merged (#26). F0-S3 on branch
  `fork/f0-s3-agents-tab` → PR #27 (merge it first if still open, gate per ADR-F005).
- ADR-F001..F005 accepted. Merges follow ADR-F005's 5-part gate — no exceptions.
- Dev stack: 8 services healthy; `web` rebuilt from F0-S3 code; DB at migration 0048. Gateway
  aliases `smart`/`fast`/`budget` → `minimax/MiniMax-M3` (tier 4); key in `.env`.
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Host `web/node_modules` installed (`npm ci --force`, node 20) — web gates run on the host:
  `npm run check:lq-ai` (CI gate, 0 errors) + `npm run test:frontend -- --run`.

## Done (F0-S3) — FIRST VISIBLE AGENT

- **Agents tab** (`/lq-ai/agents`, registered in `tabs.ts`, visible to all roles): hardcoded
  "Commercial — preview" card, message box → POST `/agents/runs`, step timeline, previous-runs list.
- **Capability rail v0**: the full model-visible tool universe (demo_read_clause + 9 deepagents
  builtins incl. the disabled `execute`) dim → active (pulsing, call in flight) → lit (used);
  unknown observed tools appended, never hidden. State machine + all page logic in
  `web/src/routes/lq-ai/agents/page-helpers.ts` (pure, Vitest-covered).
- **Polling**: self-rescheduling setTimeout (no overlap, no out-of-order) + generation guard;
  tolerates 3 transient failures then offers Retry; 330s staleness cutoff for orphaned 'running'
  rows (BackgroundTasks die with the api process — sweep still deferred to arq migration).
- **`<think>` collapse in UI only** (API record keeps full text); answer markdown sanitized with
  media tags FORBIDden (image-beacon exfil channel closed — model output is untrusted input).
- Typed client `web/src/lib/lq-ai/api/agents.ts` (+ barrel); Cypress live spec
  `cypress/e2e/f0-s3-agents-tab.cy.ts` doubles as ADR-F005 evidence (needs the dev stack).
- Adversarial review (32-agent workflow): 23 confirmed findings fixed in-branch (1 blocker — this
  file; the rest should-fix/nit), 5 refuted; record on PR #27.

## Next slice: F0-S4 — multi-turn chat + checkpointer

Per MILESTONES F0-S4:
- Agent runs become conversations: send prior turns (today `api/app/api/chats.py:1370` is
  single-turn and `execute_agent_run` takes one prompt); wire `langgraph-checkpoint-postgres`
  (pinned, unused — first consumer) so a deep agent resumes a thread across requests.
- Decide: extend `agent_runs` with a thread/conversation id vs bind to existing `chats` — read
  ADR-F002/F003 first; the Agents tab UI then gains a follow-up composer on a settled run.
- Carry-over due this slice: finish factory key exposure fix (move gateway key fully out of
  `default_headers` — repr/LangSmith leak surface; `http_async_client` seam already exists).

## Pick up exactly here

1. Read CLAUDE.md → this file → MILESTONES F0 → ADR-F003. 2. Merge PR #27 if still open.
3. Branch `fork/f0-s4-multi-turn` from main. 4. Smoke the stack:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-local-Pw1!"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s -X POST http://localhost:8000/api/v1/agents/runs -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"prompt":"What is the liability cap? Use your tools."}'
# poll GET /api/v1/agents/runs/{id} → {run:{status,final_answer,...}, steps:[{seq,kind,name,summary}]}
# or watch it live at http://localhost:3000/lq-ai/agents
```

## Carry-overs / review deferrals

- Factory key exposure → due in S4 (above). `build_deep_agent` must reject model-bearing subagent
  specs (gateway bypass) — before F1 fan-out.
- Anthropic adapter: `tool_use`/`tool_result` + block-content translation — S4/S5
  (`grep -rn F0-S1 gateway/app`); anonymization decision for block content still pending.
- No cancel endpoint (`cancelled` reserved); `cost_usd` NULL until F1 R4; runs in-process via
  BackgroundTasks (arq migration + startup sweep for orphans later); no audit rows for run kick-off.
- Rail "lit" wording diverges from ADR-F002 ("lit = loaded" vs S3's "lit = used") — reconcile when
  F1 implements per-area config; the in-UI caption is self-consistent.
- MessageBubble shares the image-exfil DOMPurify gap fixed on the Agents tab (Backlog).
- Client clock skew can mistrigger the 330s staleness cutoff — derive now from a response header
  when SSE lands (TODO in page-helpers.ts).

## Gotchas

- **Web image build OOMs unless the stack is stopped first**: `docker compose stop && DOCKER_BUILDKIT=1
  docker compose build web && docker compose up -d` (needs ~5.5GB free; vite dies in minify
  otherwise). First boot of a fresh web image downloads HF models — takes minutes to healthy.
- `gh pr create` defaults to the FROZEN upstream repo — always pass
  `--repo sarturko-maker/lq-ai-fork` (ADR-F001: no upstream interaction).
- After any migration: rebuild `api` + `arq-worker` + `ingest-worker` together. After gateway code
  changes: rebuild `gateway`. In-place pip upgrades clobber langgraph-prebuilt (force-reinstall trio).
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers (`--entrypoint sleep`;
  api image entrypoint runs alembic and dies without `DATABASE_URL`). Tests: throwaway
  `pgvector/pgvector:pg16` only.
- MiniMax-M3 emits `<think>` blocks in final_answer and model-turn summaries — UI collapses them;
  never strip them in the API.
