# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (2026-06-11, end of F0-S8)

- Merged to main through #37; **F0-S8 (matter create-in-place + conversation readability) is the
  current PR** off `fork/f0-s8-matter-create` — merges on green via the ADR-F005 gate, evidence in
  the PR + `docs/fork/evidence/f0-s8/`. All fork ADRs F001..F008 `accepted`.
- **The agents surface now reads like claude.ai/Claude Code** (maintainer feedback folded in):
  composer DOCKED at the bottom (sticky card), conversation top-down above it, Conversations list
  in the side column; thinking renders MARKDOWN (live ribbon + settled reasoning, same
  marked+DOMPurify `SANITIZE_OPTS` path as the answer); tool calls/results collapse to one-line
  `stepDigest` rows; the live ribbon is auto-expanded, tail-anchored, clamped — collapses into the
  settled "Reasoning" row when the turn lands.
- **Matters create in place** (ADR-F002 closed out): "+ New matter" beside the matter select opens
  the page-hosted `NewMatterModal` (full form, privileged ⇒ tier-floor invariant); on create the
  page appends to `matters`, writes the bound `selectedMatterId` (the panel's reactive watcher
  clears stale upload chips), and refreshes the list. The modal's old hardcoded post-create goto
  moved to the Matters page's `onCreated`. **"No matter — blank workspace" is GONE** — Run stays
  disabled until a matter is selected/created; POST /agents/runs still accepts null project_id
  (server unchanged).
- Auto-scroll pins to the conversation tail inside the **nearest scrollable ancestor** — the shell
  scrolls `<main id="lq-main">` (`html` is overflow-hidden), so document scrolling silently no-ops,
  and document-bottom would over-scroll past the conversation (side column is taller). See
  `scrollContainer()`/`tailScrollTop()` in ConversationPanel.
- Dev stack: 8 services healthy; DB at migration **0051**. Gateway aliases `smart`/`fast`/`budget`
  → `minimax/MiniMax-M3`; key in `.env`.
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
- Web gates (host, node 20): `cd web && npm run check` (0 errors) +
  `npm run test:frontend -- --run` (778/778). S8 touched ZERO api/gateway files.
- API suites run containerized (no host 3.12) — see the F0-S7 snippet below (unchanged):
  ```bash
  docker run -d --name s8pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s8pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```

## Done (F0-S8)

- Web-only slice; 4 commits. Components: `ConversationPanel.svelte` (layout reorder, `mdSafe`,
  step folding, live ribbon, auto-scroll, ADR-F002 submit guard, `newmatter` event),
  `agents/+page.svelte` (modal host, `onMatterCreated`, side column), `NewMatterModal.svelte`
  (goto lifted), `matters/+page.svelte` (owns navigation), `helpers.ts` (`stepDigest` +
  `STEP_DIGEST_LIMIT`, 5 new vitest cases).
- Specs: **f0-s3 REWRITTEN** — creates its matter through the new modal (self-sufficient again,
  doubles as S8 live evidence; asserts Run disabled pre-matter, rail 9→11 flip on bind);
  f0-s7's ribbon assertion now proves VISIBLE streamed text (auto-expanded ribbon); all
  screenshots are `capture: 'viewport'` (full-page stitching renders the sticky composer over
  the conversation).
- Gate: web 778/778 + svelte-check 0 errors; f0-s3 + f0-s4 + f0-s5 + f0-s7 green on the rebuilt
  stack; evidence screenshots in `docs/fork/evidence/f0-s8/`; 27-agent adversarial review —
  22 findings raised, 0 confirmed (all refuted on the actual code).

## Next slice: F0-S9 — eval gate (ADR-F004)

Per MILESTONES S9 (last F0 slice):
- Tool-call and subagent uptake at **N≥20 runs** on MiniMax-M3 **plus one second model family**
  (masked judge, pre-flight variance gate); subagent dispatch as task-scoped procedures, not
  open-ended delegation.
- Read ADR-F004 first — it defines what the eval gates and why (render-determinism was the
  workaround; the eval is the proof the model-driven loop is real).
- Needs: a second model family wired through the gateway (check `gateway/app/config*` for alias
  plumbing; the Anthropic adapter still lacks tool_use translation — an OpenAI-compatible second
  family avoids that blocker), an eval harness (likely `api/tests/agents/eval/` or a script —
  decide and ADR if it crosses module boundaries), and seeded matters with documents for
  grounded prompts.
- Branch `fork/f0-s9-eval-gate` from main after the S8 PR merges.

## Pick up exactly here

1. Read CLAUDE.md → this file → MILESTONES S9 → ADR-F004.
2. Smoke the stack: login at the URL above, Agents tab → "+ New matter" → run a prompt — you
   should see the bottom composer, live markdown thinking, collapsed tool rows.
3. `cd web && npm run check && npm run test:frontend -- --run` to confirm the baseline.

## Carry-overs / review deferrals

- `build_deep_agent` must reject model-bearing subagent specs (gateway bypass) — before F1 fan-out.
- Anthropic adapter: `tool_use`/`tool_result` + block-content translation still pending
  (`grep -rn F0-S1 gateway/app`); anonymization decision for block content pending. Matters for
  S9 if the second model family is Anthropic — prefer OpenAI-compatible to avoid the blocker.
- No cancel endpoint (`cancelled` reserved). A stranded `running` run deadlocks its thread
  (409 thread_busy; UI offers New chat); the arq startup sweep is F1 run-lifecycle durability.
- Checkpoint rows invisible to alembic, not cleaned on delete (`adelete_thread` uncalled) — F1.
- Long conversations exceed the dev model's context before deepagents' summarization triggers —
  ADR-F003 compaction lands F2.
- No audit rows for run kick-off (tool dispatches ARE audited).
- MessageBubble still sanitizes with DEFAULT DOMPurify (legacy surface) — harden when next touched.
- Thinking ribbon under PARALLEL subagent fan-out shares one buffer (S7 deferral — per-block
  ribbons land with F1's subagent tree).
- wave-c-matters test 3 hangs PRE-EXISTING on this box (fails identically on main's build; the
  AUT's POST /projects never leaves the browser under Cypress on that surface) — Backlog.
- S6 deferrals unchanged (Backlog): eslint-9 flat-config migration; path-scoped CSP;
  bare-`<select>` restyle; version-poll auto-reload.

## Gotchas

- **`cy.intercept` BUFFERS streamed responses** — never intercept the SSE route you assert
  liveness on; the thinking ribbon is the streaming evidence (polling can never feed it).
- **The shell scrolls `#lq-main`, NOT the document** (`html{overflow-y:hidden}` in app.css).
  Anything that programmatically scrolls the agents surface must resolve the scroll container
  (see `scrollContainer()` in ConversationPanel) — `document.scrollingElement` no-ops silently.
- **Cypress screenshots on the agents surface: use `capture: 'viewport'`** — full-page stitching
  interacts with the sticky composer and hides the conversation.
- **Cypress on this box — memory-pressure discipline (zero pg crashes with it):**
  ```bash
  docker stop lq-ai-arq-worker-1   # not needed by the specs; frees ~500MB
  ELECTRON_EXTRA_LAUNCH_ARGS='--js-flags=--max-old-space-size=512' \
    CYPRESS_LQ_AI_MATTER_NAME="S5 PreSeed 1781169832" \
    npx cypress run --spec '…' --config video=false,numTestsKeptInMemory=0
  docker start lq-ai-arq-worker-1
  ```
  f0-s3 no longer needs a pre-seed (it creates its own matter); f0-s4/s5/s7 still do.
  If workers wedge ("connection is closed" on every job): `docker compose restart ingest-worker arq-worker`.
- The web image builds in seconds with the stack UP; the container serves a pre-built bundle, so
  `docker compose build web && docker compose up -d web` before debugging a UI change.
- `gh pr create` defaults to the FROZEN upstream repo — always pass
  `--repo sarturko-maker/lq-ai-fork` AND `--head <branch>` (ADR-F001).
- `gh pr checks | awk '{print $2}'` breaks on check names containing spaces — parse with
  `--json` or verify checks manually before declaring red.
- Background merge-watchers end with `git checkout main` — verify the current branch before
  committing slice work. ALSO: switching branches with uncommitted spec edits then
  `git checkout -- <file>` on the other branch DESTROYS the edit (bit us in S8 — recommitted).
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
