# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (end of F1-S2 — the cockpit is the landing surface)

- **F1-S2 merged via PR (see merge commit on main)**: design-system
  foundation + Cockpit v0 shell per the ratified re-plan
  (`docs/fork/plans/F1-replan.md` § F1-S2) and the slice plan + deviations
  (`docs/fork/plans/F1-S2-design-system-cockpit.md`).
- Dev stack: 8 services healthy; **DB at migration 0053**
  (`practice_areas` minimal table + standard-rows seed: commercial
  configured, disputes/m-and-a/privacy/employment inert); api +
  arq-worker + ingest-worker + web rebuilt together on slice code.
- Gateway aliases smart/fast/budget → minimax/MiniMax-M3; ONLY the MiniMax
  key is real (CALL-based token plan, not PAYG — budget rules relaxed).
- App login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  — **login now lands in the COCKPIT** (area grid; tab chrome lives only on
  the legacy `(tools)` routes, reachable via the header's Tools menu).
- Suites at gate time: **api 2097 passed / 3 skipped** (containerized,
  throwaway pgvector, alembic head incl. 0053); gateway untouched (S9
  counts stand); web **check 0 errors** + **778/778** vitest. Live:
  f1-s2-cockpit 5/5, f0-s5 real-model multi-turn 1/1, wave-a 3/3, m4 9/9;
  wave-b 4/6 + wave-c 4/5 — those 3 fails **reproduce on the pre-slice
  bundle** (control run; pre-existing). Evidence:
  `docs/fork/evidence/f1-s2/`.
- Adversarial review (5 dimensions + per-finding refutation, 37 agents):
  32 verified findings — 26 confirmed in-slice ALL FIXED, 3 pre-existing
  recorded below, 3 refuted.

## Done (F1-S2, this slice)

- **Design system** (ADR-F006): shadcn-svelte 1.3.0 vendored
  (`web/src/lib/components/ui/**`, 11 components, lint/format-exempt;
  NOTICES rows added), bits-ui 2.18.1 + paneforge 1.0.2 + lucide; semantic
  intent tokens in `web/src/app.css` — warm light-first canvas
  (maintainer rule, verbatim: "don't use black background, needs to be
  clean and professional, cutting edge design"), charcoal dark floored at
  L=0.23 (≈#1B1E24), status intent tokens (running/completed/failed/
  cancelled/attention + washes). Legacy `--lq-*` surfaces untouched.
- **Cockpit v0** (`web/src/lib/lq-ai/cockpit/`): lands on the AREA LIST;
  left rail = seeded practice areas (unconfigured = INERT cards, honest
  state) + unfiled-conversations bucket; matters under Commercial with
  settled-row rollups; pick-or-create in place; resume into the re-homed
  ConversationPanel; URL state `?area=&matter=&thread=` deep-links (the
  panel now dispatches `threadcreated` so first-send syncs the URL without
  remounting); header: trust chrome, Tools menu (+ Trust & transparency),
  theme toggle, settings, sign-out. Legacy chrome moved to the
  `(tools)` route group — URLs unchanged, agents tab kept for regression
  value.
- **API**: minimal `practice_areas` (0053, idempotent seed — S3 owns the
  config vocabulary), `GET /practice-areas`, `GET /agents/matters`
  (one-call rollup: per-matter thread_count/last_run_at/newest-run status
  + unfiled summary; archived/sandbox threads in neither bucket —
  documented + tested), `project_id`/`unfiled` filters on
  `GET /agents/threads` (mutually exclusive; foreign ids match nothing).
  OpenAPI count 124 → 126.
- **Legacy bugfix (security-sensitive, extra review pass done)**:
  `POST /auth/refresh` bcrypt scan moved off-thread (it FROZE the api
  event loop — found live with 186 accumulated dev sessions; logins
  stalled deterministically) + post-scan liveness re-check under
  `FOR UPDATE` (the longer scan window made refresh-token double-spend
  trivially reliable; the loser now 401s with a `concurrent_rotation`
  audit row).
- Docs: plan + deviations, NOTICES (vendored source + 19-package SBOM
  delta), db-schema (practice_areas + 0052 lease columns), evidence.

## Next slice — pick up exactly here

1. Next: **F1-S3 — `practice_areas` config vocabulary + per-area Deep
   Agent** (`docs/fork/plans/F1-replan.md` § F1-S3): EXTEND the 0053 table
   (area profile md, bound skills/playbooks/MCPs, default tier floor),
   `projects.practice_area_id` (nullable), audit rows gain
   `practice_area_id`, config/admin API, per-area `create_deep_agent`
   (area system prompt, area-scoped skills, subagent fan-out).
   **Security load-bearing**: `build_deep_agent` must reject model-bearing
   subagent specs (gateway bypass); subagent permissions REPLACE, tools
   OVERRIDE, middleware does not inherit — emit complete per-subagent
   declarations.
2. The cockpit consumes S3 directly: `configured` becomes derived from
   real config; matters file via `projects.practice_area_id` (today ALL
   matters render under Commercial, presentation-only); the unit-of-work
   noun already renders from `unit_label`. Cockpit URL state uses area
   KEYS — never written to stored rows yet (MILESTONES pre-F1 guard
   honored; S3's FK makes filing real).
3. Qualification hook: any model/profile pair an area config names needs a
   row in `docs/fork/model-compatibility.md` (S9 gate).
4. Multi-file slice: explore → written plan (docs/fork/plans/F1-S3-…) →
   implement → full ADR-F005 gate.

## Carry-overs / review deferrals

- **NEW — auth/refresh hardening (pre-existing, recorded by the F1-S2
  security pass)**: the unauthenticated all-users bcrypt scan is now
  off-thread but still holds a pooled connection for its duration and
  ~15 concurrent garbage-token requests can pin the default pool (32
  to_thread workers can saturate cores). Real fix: deterministic HMAC
  index column (tracked in-code at `auth.py` scan comment) + a small
  injected semaphore; also consider a dev session-prune (maintainer
  approval needed — 186 rows accumulated). Legacy-bugfix candidate.
- **NEW — ADR-0011 disclosure on the agent surface**: ConversationPanel
  (now the landing conversation surface) has never carried the tier
  badge/receipts; deliberately sequenced AFTER F1-S5's attribution
  extension (MILESTONES "Trust chrome reaches the agent surface").
  Deferred on record.
- **NEW — sandbox-bound agent threads**: creatable via API (no UI path),
  invisible in the cockpit (documented + tested); consider rejecting
  sandbox `project_id` at `POST /agents/runs` in S3 (closes the state at
  the source).
- Live SSE animation (token deltas) DEAD in production until a Redis
  pub/sub publisher lands — F1-S1 deferral; consider riding F1-S4.
- Flood brake counts queued-unclaimed runs (ADR-F009, on record).
- Two-writers window (zombie checkpoint writes ≤1 heartbeat) — F1-S5.
- Step/audit appends unfenced (deliberate, ADR-F009 invariant).
- web STALE_RUNNING_AFTER_MS approximation — revisit when the cockpit
  redefines run presentation further (S4).
- Ingest orphan recovery is STARTUP-ONLY (hit live this slice: transient
  asyncpg drop left a file at `processing`; worker restart's sweep fixed
  it) — cron sweep stays Backlog.
- Mismatch read-noise watch metric (19/20), L2 judge seam unrun — S9.
- `build_deep_agent` model-bearing subagent rejection — NOW DUE in S3.
- Anthropic adapter tool_use translation — only if a Claude family joins.
- Conversation compaction (ADR-F003) — F2. MessageBubble legacy DOMPurify.
  wave-c-matters test 3 pre-existing hang — Backlog. Cypress pre-existing
  reds: wave-b Enhance-Prompt + skill-detail, wave-c chat-in-matter
  (control-proven, `docs/fork/evidence/f1-s2/live-verification.md`).

## Gotchas (carried + new)

- **NEW: route groups** — legacy tool routes live under
  `web/src/routes/lq-ai/(tools)/` (URLs unchanged); the gate layout
  (`routes/lq-ai/+layout.svelte`) is auth/idle only; cockpit owns its
  viewport at `/lq-ai`. Tests importing route modules by RELATIVE path
  must include `(tools)` in the path.
- **NEW: cypress login waits** — after submitting login, WAIT for the
  redirect (`cy.url({timeout}).should('not.include','/login')`) before
  `cy.visit()`: visiting mid-login CANCELS the in-flight POST.
- **NEW: headless Electron windows are 1280 wide** — a 1440 viewport gets
  CROPPED in `capture: 'viewport'` screenshots; use `cy.viewport(1280,800)`
  for evidence shots.
- **NEW: vendored `src/lib/components/ui/**` + `src/lib/utils.ts`** are
  eslint/prettier-EXEMPT (stay diffable vs upstream); never run the
  shadcn-svelte CLI in CI; `@lucide/svelte` must not be downgraded by
  `add` runs (registry items pin an older major).
- **NEW: tokens** — new UI uses the semantic tokens (`bg-background`,
  status intents...); the legacy `--lq-*` layer is untouched and legacy
  dark mode remains broken (pre-existing). `darkMode` comes from
  `@config tailwind.config.js` (class strategy) — do NOT add a
  `@custom-variant dark`.
- **NEW: panel re-homing** — ConversationPanel mounts per thread via
  `{#key}`; the cockpit keeps the key STABLE for the thread the panel
  itself just created (`panelOwnedThread`) — remounting there kills the
  live stream. `initialThreadId` is read at mount only.
- agent runs execute on the arq-worker; after ANY migration rebuild api +
  arq-worker + ingest-worker together (and `web` serves a pre-built
  bundle — rebuild it before debugging UI).
- arq `Job.abort` flag-then-wait; redelivered `max_tries=1` jobs settle
  without re-running (0.26.3). langgraph `durability=` kwarg CRASHES
  without a checkpointer. `aupdate_state` needs `as_node="tools"`;
  repair reads the PINNED view (state.config).
- FastAPI 204 routes need `response_class=Response` (M3-C2). New API
  endpoints must register in tests/test_openapi.py (count assert!) +
  tests/test_endpoints.py exclusion list.
- `cy.intercept` BUFFERS streamed responses — never intercept the SSE
  route under liveness test. Cypress on agents surface:
  `capture: 'viewport'`.
- `gh pr create` defaults to the FROZEN upstream — always
  `--repo sarturko-maker/lq-ai-fork` AND `--head <branch>` (ADR-F001).
  jq is NOT installed — parse `gh --json` with python3.
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in
  containers. Containerized pytest needs `skills/` at `/skills`; ruff
  needs repo-root ruff.toml. Throwaway-pg test recipe:
  ```bash
  docker run -d --name s9pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s9pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```
- NEVER `docker compose down -v`; NEVER host-side alembic against the dev
  DB. `.env` S3 keys stay commented out (backup `.env.bak-f0-s4`).
- MiniMax-M3 emits `<think>` inline AND a `reasoning` delta field; both
  round-trip the gateway verbatim. GET /agents/runs/{id} returns
  `{run, steps}`; ORM models don't declare FK edges — flush per
  dependency level. Eval cycles run SEQUENTIALLY, never with Cypress.
