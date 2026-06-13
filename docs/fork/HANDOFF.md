# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (end of F1-S2.1 — design iteration v2 on the cockpit)

- **F1-S2.1 merged via PR #45**: responsive collapse + elevation/shade scale + motion,
  per the maintainer's review of the live F1-S2 cockpit (his four points, verbatim, in
  `docs/fork/plans/F1-S2.1-design-iteration-v2.md` — plan includes the benchmark review
  of Harvey/Legora/Linear/Attio PRODUCT SCREENSHOTS, the 3-wave legacy rollout order,
  and the deviations incl. the post-review fix round). Web-only diff; api/gateway
  untouched (F1-S2 counts stand: api 2097/3 skipped, gateway S9 counts).
- Dev stack: 8 services healthy; DB at 0053; `web` rebuilt on slice code. Login:
  http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1! — lands in the
  cockpit (now responsive; theme toggle in header).
- Gateway aliases smart/fast/budget → minimax/MiniMax-M3; ONLY the MiniMax key is real
  (CALL-based token plan, not PAYG).
- Suites at gate: web check **0 errors** (warnings 20→5), vitest **779/779**, live
  cypress **22/22** (f1-s2-cockpit 5/5, NEW f1-s21-responsive 4/4, f0-s3 1/1, wave-a
  3/3, m4 9/9); CI green ×3. Adversarial review: 34 agents, 25 confirmed (6 should-fix
  ALL FIXED, 0 blockers), 3 refuted. Evidence: `docs/fork/evidence/f1-s21/`.

## Done (F1-S2.1, this slice)

- **Responsive**: rail = collapsible paneforge pane ≥880px (header PanelLeft toggle,
  collapsed state persists via autoSaveId) / off-canvas drawer <880px (dialog
  semantics, Escape/scrim/select closes, initial focus); ONE pane group across both
  layouts (live conversation survives the breakpoint); matter workspace stacks <720px
  HOST width (list ⇄ full-width conversation with back row; `$effect` syncs the stacked
  pane to URL threadId so composer-created/history threads show the panel and width
  crossings never unmount a live stream); legacy panel horizontal overflow fixed
  (`html { overflow-x: clip }` + centered `max-w-3xl` column).
- **Shade/contrast/motion** (ADR-F006 extended, values only): light canvas →
  oklch(0.965 0.004 90) warm gray under white floating cards; tokenized elevation
  (`--elevation-xs/sm/md/lg` → `shadow-*`; dark variants deeper); 3-step text hierarchy
  (0.21 / 0.45 / ≥85%-alpha metadata — 85% is the 4.5:1 floor, review-verified);
  conversation workspace = ONE rounded-xl card with recessed `bg-muted/40` thread
  aside; rail merges with canvas, selected row = floating card chip; `color-scheme`
  flips native scrollbars/controls; reduced-motion-aware `in:fade|global` view intros,
  smooth scrolling + overscroll containment, hover lift/arrow affordances, animated
  rail collapse (gated on reduced-motion), resizer hover/drag affordance.
- **ConversationPanel** (1,412-LOC legacy, renders INSIDE the cockpit): entire scoped
  `<style>` palette migrated to semantic tokens (indigo primary Run, status intent
  badges, muted insets); empty area-card bar no longer renders ($$slots guard). Markup/
  typography migration stays rollout wave 1.
- **Legacy dark stopgap**: `:root.dark { --lq-* }` in practice.css — legacy dark was
  hard-white; now charcoal-scale STOPGAP quality (accent 0.65 L = computed dual-use
  optimum; hardcoded white-on-accent fills sit ~3:1 until each wave migrates).
  `:root.dark` NOT `.dark`: 16 scoped re-imports of practice.css out-cascade an
  equal-specificity `.dark` block.

## Next slice — pick up exactly here

1. **F1-S3 — `practice_areas` config vocabulary + per-area Deep Agent**
   (`docs/fork/plans/F1-replan.md` § F1-S3): EXTEND the 0053 table (area profile md,
   bound skills/playbooks/MCPs, default tier floor), `projects.practice_area_id`
   (nullable), audit rows gain `practice_area_id`, config/admin API, per-area
   `create_deep_agent` (area system prompt, area-scoped skills, subagent fan-out).
   **Security load-bearing**: `build_deep_agent` must reject model-bearing subagent
   specs (gateway bypass); subagent permissions REPLACE, tools OVERRIDE, middleware
   does not inherit — emit complete per-subagent declarations.
2. The cockpit consumes S3 directly: `configured` becomes derived from real config;
   matters file via `projects.practice_area_id` (today ALL matters render under
   Commercial, presentation-only); the unit-of-work noun already renders from
   `unit_label`. Cockpit URL area keys stay presentation-only until S3's FK.
3. **Legacy-surface rollout** (maintainer point c — "the entire interface will need to
   change, not just the agents tab"), sliced separately, order ratified in the S2.1
   plan § Goals-3: **wave 1** conversation core (ConversationPanel markup/typography +
   ChatPanel tree → chats, matters workspace, agents tab, cockpit pane in one wave);
   **wave 2** knowledge/skills/playbooks/tabular; **wave 3** settings/admin/trust/
   saved-prompts/learn (+ `autonomous/` only if it survives F2/F3) + `(tools)` chrome
   last. Sequence the waves against S3/S4 priorities with the maintainer.
4. Qualification hook: any model/profile pair an area config names needs a row in
   `docs/fork/model-compatibility.md` (S9 gate).
5. Every slice is multi-file: explore → written plan (docs/fork/plans/…) → implement →
   full ADR-F005 gate.

## Carry-overs / review deferrals

- **NEW (S2.1 review, deferred on record)**: drawer focus TRAP (dialog semantics +
  initial focus shipped; trap pending); legacy white-on-accent fills ~3:1 in dark until
  per-surface migration; dark Run-button 3.54:1 (the dark `--primary`/foreground pair —
  resolve in the design system during wave 1); drawer scrim lightens in dark
  (`bg-foreground/20` — pick a dimming token when the rollout systematizes overlays);
  crossing 720px with the LIST showing still unmounts a non-live panel's transient
  state; composer up-shadow not tokenized; pre-existing hairline borders 1.15–1.35:1 vs
  the 3:1 UI contract comment (decorative separators on filled surfaces — revisit in
  wave 1).
- auth/refresh hardening (pre-existing, recorded by the F1-S2 security pass): bcrypt
  scan now off-thread but still holds a pooled connection; ~15 concurrent garbage-token
  requests can pin the default pool. Real fix: deterministic HMAC index column +
  injected semaphore; dev session-prune needs maintainer approval (186 rows).
- ADR-0011 disclosure on the agent surface (tier badge/receipts on ConversationPanel) —
  sequenced AFTER F1-S5's attribution extension.
- Sandbox-bound agent threads: creatable via API, invisible in the cockpit — consider
  rejecting sandbox `project_id` at `POST /agents/runs` in S3.
- Live SSE animation (token deltas) DEAD in production until a Redis pub/sub publisher
  lands — F1-S1 deferral; consider riding F1-S4.
- Flood brake counts queued-unclaimed runs (ADR-F009, on record). Two-writers window
  (zombie checkpoint writes ≤1 heartbeat) — F1-S5. Step/audit appends unfenced
  (deliberate, ADR-F009). web STALE_RUNNING_AFTER_MS approximation — S4.
- Ingest orphan recovery is STARTUP-ONLY — cron sweep stays Backlog.
- Mismatch read-noise watch metric (19/20), L2 judge seam unrun — S9.
- Anthropic adapter tool_use translation — only if a Claude family joins.
- Conversation compaction (ADR-F003) — F2. MessageBubble legacy DOMPurify. Cypress
  pre-existing reds: wave-b Enhance-Prompt + skill-detail, wave-c chat-in-matter
  (control-proven, `docs/fork/evidence/f1-s2/live-verification.md`).

## Gotchas (carried + new)

- **NEW: headless captures lie about theme** — headless Electron AND headless Chromium
  composite stale light tiles into screenshots after a theme flip (even after reload /
  dark first paint) while computed styles are correct. Capture theme evidence HEADED
  (`--browser chromium --headed`, Cypress spawns Xvfb); assert computed styles, not
  pixels. Probe + analysis: `docs/fork/evidence/f1-s21/live-verification.md`.
- **NEW: practice.css cascade** — 16 legacy components re-`@import` practice.css in
  scoped `<style>` blocks; theme overrides for `--lq-*` must be `:root.dark` (0,2,0)
  or later duplicates win. Never add a plain `.dark` block there.
- **NEW: prettier sweeps legacy files** — practice.css is 2-space indented; running
  `prettier --write` on it rewrites the whole file to tabs. Format ONLY new-code files;
  match legacy file style by hand (same lesson as the api ruff-parity trap).
- **NEW: paneforge 1.0.2 facts** — sizes are percentages; `collapsible` +
  `collapsedSize={0}`; instance `collapse()/expand()/isCollapsed()`; set explicit
  `id`+`order` on panes under `autoSaveId`; collapsed state persists; `data-collapsed`/
  `data-pane-state` attrs for styling; flex-grow transitions enable
  collapsing/expanding states (suppress the class while dragging AND under
  reduced-motion); Enter on the focused resizer toggles collapse.
- **NEW: svelte transition locality** — `in:fade` on a component root does NOT play
  when an ancestor `{#if}`/`{#key}` branch swaps it in; use `|global` for view-level
  intros.
- **NEW: route groups** — legacy tool routes live under `web/src/routes/lq-ai/(tools)/`
  (URLs unchanged); cockpit owns its viewport at `/lq-ai`. Tests importing route
  modules by RELATIVE path must include `(tools)`.
- **cypress login waits** — after submitting login, WAIT for the redirect
  (`cy.url({timeout}).should('not.include','/login')`) before `cy.visit()`.
- **headless Electron windows are 1280 wide** — 1440 viewports get CROPPED in
  `capture: 'viewport'` screenshots; use `cy.viewport(1280,800)` for evidence.
- **vendored `src/lib/components/ui/**` + `src/lib/utils.ts`** are eslint/prettier-
  EXEMPT; never run the shadcn-svelte CLI in CI; don't let `add` runs downgrade
  `@lucide/svelte`.
- **tokens** — new UI uses semantic tokens; `darkMode` comes from
  `@config tailwind.config.js` — do NOT add a `@custom-variant dark`. Faded text floors
  at 85% alpha (4.5:1). Elevation: `shadow-xs/sm/md/lg` are tokenized via
  `--elevation-*`.
- **panel re-homing** — ConversationPanel mounts per thread via `{#key}`; the cockpit
  keeps the key STABLE for the panel-created thread (`panelOwnedThread`); stacked mode
  syncs to threadId via `$effect` — don't add competing writers to `stackedShowPanel`.
- agent runs execute on the arq-worker; after ANY migration rebuild api + arq-worker +
  ingest-worker together (and `web` serves a pre-built bundle — rebuild before
  debugging UI).
- arq `Job.abort` flag-then-wait; redelivered `max_tries=1` jobs settle without
  re-running (0.26.3). langgraph `durability=` kwarg CRASHES without a checkpointer.
  `aupdate_state` needs `as_node="tools"`; repair reads the PINNED view.
- FastAPI 204 routes need `response_class=Response` (M3-C2). New API endpoints must
  register in tests/test_openapi.py (count assert!) + tests/test_endpoints.py.
- `cy.intercept` BUFFERS streamed responses — never intercept the SSE route under
  liveness test.
- `gh pr create` defaults to the FROZEN upstream — always
  `--repo sarturko-maker/lq-ai-fork` AND `--head <branch>` (ADR-F001). jq is NOT
  installed — parse `gh --json` with python3.
- Host Python is 3.11; api/gateway need 3.12 — all py tooling in containers.
  Containerized pytest needs `skills/` at `/skills`; ruff needs repo-root ruff.toml;
  pin ruff to CI's resolved version before formatting api code. Throwaway-pg recipe:
  ```bash
  docker run -d --name s9pg -e POSTGRES_USER=lq -e POSTGRES_PASSWORD=lq -e POSTGRES_DB=lqtest pgvector/pgvector:pg16
  docker run --rm --network container:s9pg -v $PWD/api:/work -v $PWD/skills:/skills:ro -w /work \
    -e PYTHONPATH=/work -e DATABASE_URL=postgresql+asyncpg://lq:lq@localhost:5432/lqtest \
    --entrypoint bash lq-ai-api:latest -c "pip install -q pytest pytest-asyncio respx; pytest tests/ -q"
  ```
- NEVER `docker compose down -v`; NEVER host-side alembic against the dev DB. `.env`
  S3 keys stay commented out (backup `.env.bak-f0-s4`).
- MiniMax-M3 emits `<think>` inline AND a `reasoning` delta field; both round-trip the
  gateway verbatim. GET /agents/runs/{id} returns `{run, steps}`; ORM models don't
  declare FK edges — flush per dependency level. Eval cycles run SEQUENTIALLY, never
  with Cypress.
