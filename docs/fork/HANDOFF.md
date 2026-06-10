# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-10, end of F0-S3)

- All merged to main: F0-S1 #24, governance #25, F0-S2 #26, **F0-S3 #27 (first visible agent —
  Agents tab live)**, ADR-F006 docs #28, F006 acceptance PR.
- **ADR-F001..F006 accepted** (F006 accepted by the maintainer 2026-06-10 — it governs the S6
  shell shed and the S7 wire spec; read it before building either). Merges follow ADR-F005's
  5-part gate — no exceptions.
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

## Maintainer feedback on live S3 (2026-06-10) — drove the F0 re-sequence

(1) Agents tab auto-lands in Commercial → area picker, F1. (2) No new chat → S5 multi-turn.
(3) No file attach → S4 binds runs to a Matter's documents; composer upload is Backlog.
(4) **No demo tools — tools must be real** (the model itself refused `demo_read_clause` as
self-described canned text; the run honestly answered "no contract attached"). Also: timeline
shows raw JSON args and the closing model turn duplicates the final answer — polish in S4.
(5) "The entire system looks really basic" → UI-stack research → ADR-F006 at F0→F1 boundary.
(6) Stream chats + reasoning, UX like Claude Code → S7 SSE v2 (after the S6 shell shed).
Round 2 (same day): (7) LEFT panel = practice areas → create/pick a Matter (F1 layout).
(8) RIGHT panel = Skills / Playbooks / legal Tools (tabular review, Word redlining), utility tools
collapsed; + a Claude.ai-style **Memory manager** (matter + practice-area memory) — F1/F2.
(9) UI research must benchmark visually against top legal-AI platforms (Harvey, Legora…) and
Claude.ai/Gemini — both research workflows completed same day; findings + decision in
docs/adr/F006-ui-stack-and-design-system.md (proposed). Notable: Harvey's Matter OS pivot and
Legora's aOS independently validate the fork's matter-centric deep-agent thesis; NO vendor has
shipped a user-editable memory manager (Harvey co-building since Jan 2026) — F2's is differentiating.

## Next slice: F0-S4 — real tools on real documents (kill the demo)

Per re-sequenced MILESTONES F0-S4:
- Optional Matter binding on POST `/agents/runs` (`project_id`); the run's agent gets
  `search_documents`/`read_document` over that matter's ingested documents (upstream KB/ingest
  substrate — find the existing retrieval path in `api/app/`); `demo_read_clause` DELETED.
- Matter privilege/tier floors respected; wrap these two tools in the minimal `guarded_tool_call`
  pattern (pulled forward from F1 — security-correct order; seam comment in `runner.py`).
- UI: matter dropdown in the composer (existing matters), natural-language step titles, suppress
  the duplicate closing model turn; rail entries for the two real tools.
- Carry-over due this slice: finish factory key exposure fix (gateway key out of
  `default_headers`; `http_async_client` seam exists).
- Sequence after this slice: S5 multi-turn + checkpointer → S6 shell shed (extract lq-ai to a
  standalone SvelteKit app) → S7 SSE v2 (AI SDK stream spec) → S8 eval gate — per **ADR-F006
  (ACCEPTED 2026-06-10)**, which also fixes the design system (shadcn-svelte, semantic tokens)
  and records the research behind it.

## Pick up exactly here

1. Read CLAUDE.md → this file → MILESTONES F0 → ADR-F006 + F002/F004 (nothing is left unmerged).
2. Branch `fork/f0-s4-real-tools` from main. 3. Smoke the stack:

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
- **Name fork Cypress specs `fN-…`** (or `lq-ai-…`): the support `before()` hook bootstraps an
  OpenWebUI user for any other spec name, and that user BREAKS `/lq-ai/*` (OpenWebUI auth redirect
  under `WEBUI_AUTH=false` once users exist in the web container's `webui.db`). If it happens:
  delete the `admin@example.com` rows from `user` + `auth` in `/app/backend/data/webui.db`.
- After any migration: rebuild `api` + `arq-worker` + `ingest-worker` together. After gateway code
  changes: rebuild `gateway`. In-place pip upgrades clobber langgraph-prebuilt (force-reinstall trio).
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers (`--entrypoint sleep`;
  api image entrypoint runs alembic and dies without `DATABASE_URL`). Tests: throwaway
  `pgvector/pgvector:pg16` only.
- MiniMax-M3 emits `<think>` blocks in final_answer and model-turn summaries — UI collapses them;
  never strip them in the API.
