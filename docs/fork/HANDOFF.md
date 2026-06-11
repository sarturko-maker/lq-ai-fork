# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-11, end of F0-S6)

- Merged to main through #34; **F0-S6 (the shell shed) is PR #35** — merges on green via the
  ADR-F005 gate, full evidence in the PR. ALL fork ADRs F001..F008 `accepted`;
  **ADR-0009 superseded by ADR-F006** (the OpenWebUI shell is gone).
- **`web/` is now a standalone lean SvelteKit SPA** (ADR-F006): OpenWebUI husk + its Python
  backend + ~150 unused deps + the §4 branding obligation REMOVED (~490k lines); lq-ai code
  verbatim at unchanged paths; **nginx:1.28-alpine serves the static bundle on the same
  :8080 + `/health` contract** (compose/helm/caddy unchanged). Provenance: 123/123 clean
  (`docs/fork/evidence/f0-s6/provenance.md`); lineage in `NOTICES.md` § Web client provenance —
  pre-S6 builds stay bound by the OpenWebUI license in git history.
- Dev stack: 8 services healthy on the S6 web image; DB at migration **0050**; api boot logs
  `agent checkpointer ready (AsyncPostgresSaver)`. Gateway aliases `smart`/`fast`/`budget` →
  `minimax/MiniMax-M3`; key in `.env`.
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Web gates (host, node 20): `cd web && npm run check` (0 errors, whole app — the scoped
  `check:lq-ai` now just aliases it) + `npm run test:frontend -- --run` (752/752).
- API suites run containerized (no host 3.12): throwaway `pgvector/pgvector:pg16` + the api image
  with the repo mounted — **and `skills/` mounted at `/skills`** (migration 0032 seeds from it):
  ```bash
  docker run -d --name s6pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s6pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```

## Done (F0-S6) — the shell shed (ADR-F006)

- In-place extraction: only `web/src/{lib,routes}/lq-ai` survived (254 files, paths unchanged →
  imports/vitest globs/tsconfig/Cypress all intact). New app root WRITTEN FRESH from behavioral
  specs (relicensing condition): rewritten `app.html` FOUC theme script (legacy
  `localStorage.theme` values honored; `html.dark` class convention kept), `app.css` Tailwind v4
  entry (gray-ramp oklch constants carried for pixel parity — recorded in the provenance doc),
  root layout/redirect/error, adapter-static fallback, explicit vitest include globs.
- Container: node:22-alpine build → nginx:1.28-alpine; `no-cache` on mutable entry points,
  immutable caching on hashed assets; `PUBLIC_LQ_AI_API_BASE_URL` still baked at build (lands in
  `/_app/env.js`); the pyodide network fetch at image build is gone.
- Harness: CI web job runs `npm run check`; Cypress OpenWebUI bootstrap + the `fN-` spec-name
  constraint died with the husk; upstream specs deleted, wave/m specs + fixtures kept;
  `cypress/tsconfig.json` self-contained (fresh-clone fix); Makefile `clean` no longer `down -v`.
- Hardening: SkillSourceView sanitizes with the Agents-tab FORBID_TAGS/FORBID_ATTR (capture-as-
  skill bodies derive from model output); footer attribution made truthful ("Apache-2.0").
- Gate: svelte-check 0 errors; vitest 752/752; f0-s3 + f0-s5 green on the new shell (twice —
  before and after review fixes); screenshot parity (intended delta: footer); 36-agent
  adversarial review — 28 confirmed findings fixed or deferred on record, 0 blockers.

## Next slice: F0-S7 — SSE v2: stream like Claude Code (ADR-F006 wire spec)

Per MILESTONES F0-S7:
- Emit the **Vercel AI SDK UI Message Stream v1** from FastAPI — hand-rolled emitter, spec-only
  (no Vercel runtime). `data-*` parts for subagent/interrupt/plan/receipt each carry their
  settled `agent_run_steps` row id (ADR-F004 render-determinism: settled rows decide, streams
  animate). The wire spec was accepted in ADR-F006 — read its option 2 text before starting.
- Reasoning deltas render as a collapsed-by-default thinking ribbon with shimmer status; tool/
  plan frames live; this upgrades the S3/S5 polled rail (polling stays as the fallback).
- Gateway carry-over pairs with S7: the Anthropic adapter still drops `tools`/block content
  (`grep -rn F0-S1 gateway/app`); anonymization decision for block content pending.
- The legacy 4-frame SSE parser (`web/src/lib/lq-ai/sse/parser.ts`) serves the LEGACY chats
  path; the agents surface is polling-only today — S7 adds its stream on the clean shell.
- **Pulled forward into S7 (agentic-UX audit + maintainer re-plan, 2026-06-11 — see MILESTONES):**
  (a) persist subagent identity on `agent_run_steps` — `api/app/agents/runner.py` computes the
  `parent_ids` chain and drops it at persist time; S7 reshapes rows/wire anyway, and flat rows
  leave F1's subagent tree dataless and S9's subagent eval unobservable; (b) extract the
  conversation surface out of the 1215-line `agents/+page.svelte` into a layout-agnostic
  component (props: thread id; renders settled rows) so F1's cockpit re-homes it without
  re-touching stream wiring.
- After S7: **S8 = matter creation on the Agents tab** (maintainer directive — same
  NewMatterModal/POST /projects plumbing, goto-lift prereq, bind+chips+refresh wiring, removes
  the blank-workspace option per ADR-F002); S9 = eval gate. F1 now LEADS with Cockpit v0 on the
  design system (landing = cockpit; practice areas listed from day-one `practice_areas` rows
  with honest not-configured states) preceded by run-lifecycle durability — MILESTONES F1 has
  the full re-scope.

## Pick up exactly here

1. Read CLAUDE.md → this file → MILESTONES F0 → ADR-F006 (wire-spec section) → ADR-F008.
2. Branch `fork/f0-s7-sse-v2` from main (after PR #35 merges).
3. Smoke the stack (multi-turn; NOTE the response nesting — `runs[-1]` is `{run, steps}`):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-local-Pw1!"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
PID=$(curl -s http://localhost:8000/api/v1/projects -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
TID=$(curl -s -X POST http://localhost:8000/api/v1/agents/runs -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"What is the liability cap? Search the matter documents.\",\"project_id\":\"$PID\"}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['thread_id'])")
# poll until completed+continuable:
curl -s http://localhost:8000/api/v1/agents/threads/$TID -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['runs'][-1]['run']['status'], d['continuable'])"
# then follow up:
curl -s -X POST http://localhost:8000/api/v1/agents/runs -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"Without tools: what did I just ask you?\",\"thread_id\":\"$TID\"}"
# the follow-up answer must recall the first question — that's the checkpointer working.
```

## Carry-overs / review deferrals

- `build_deep_agent` must reject model-bearing subagent specs (gateway bypass) — before F1 fan-out.
- Anthropic adapter: `tool_use`/`tool_result` + block-content translation — S7;
  anonymization decision for block content still pending.
- No cancel endpoint (`cancelled` reserved; a checkpointer interrupt is possible — pairs with the
  thread-repair pathway). A stranded `running` run deadlocks its thread (409 `thread_busy`
  forever; UI offers New chat) — the arq migration's startup sweep must settle orphans; ingest
  jobs share the fragility (files strand at `processing`).
- Checkpoint rows invisible to alembic, not cleaned on delete (`adelete_thread` uncalled) — F1.
- Long conversations exceed the dev model's context before deepagents' summarization triggers —
  ADR-F003 compaction lands F2; the summarization-turn `_is_nested` nit rides along.
- No audit rows for run kick-off (tool dispatches ARE audited).
- Rail "lit" wording vs ADR-F002 — F1. Client clock-skew on the 330s staleness cutoff — derive
  from a response header when SSE lands (S7).
- MessageBubble still sanitizes with DEFAULT DOMPurify (SkillSourceView is hardened since S6;
  the Agents tab since S3) — harden when next touched.
- S6 review deferrals (Backlog): eslint-9 flat-config migration (lint harness crashes,
  pre-existing, not a CI gate); path-scoped CSP/frame-ancestors (/word-addin must stay
  Office-frameable); bare-`<select>` restyle (F1 design system).
- Version-poll auto-reload died with the husk: stale SPAs persist until manual refresh after a
  web rebuild (mitigated by `no-cache` on entry points; Backlog).

## Gotchas

- **Cypress on this box — memory-pressure discipline (zero pg crashes with it):**
  ```bash
  docker stop lq-ai-arq-worker-1   # not needed by the specs; frees ~500MB
  ELECTRON_EXTRA_LAUNCH_ARGS='--js-flags=--max-old-space-size=512' \
    CYPRESS_LQ_AI_MATTER_NAME="<pre-seeded matter>" \
    npx cypress run --spec '…' --config video=false,numTestsKeptInMemory=0
  docker start lq-ai-arq-worker-1
  ```
  PRE-SEED matters with the browser closed (spec headers have the steps). If workers wedge
  ("connection is closed" on every job): `docker compose restart ingest-worker arq-worker`.
- **The web image now builds in seconds with the stack UP** — the pre-S6 stop-the-stack OOM
  dance is dead. `docker compose build web && docker compose up -d web` is the whole loop; the
  container serves a pre-built bundle, so rebuild before debugging a UI change.
- The fork Cypress spec-name pattern (`fN-…`) is RETIRED — the OpenWebUI bootstrap it dodged
  died with the husk. Existing names stay for continuity.
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
  `<think>` blocks — the UI collapses them; never strip them in the API.
