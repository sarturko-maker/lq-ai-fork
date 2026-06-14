# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (AE6 shipped — next is AE7)

- **AE0 (#59) + AE1 (#60) + AE2 (#61) + AE3 (#62) + AE4 (#63) + AE5 (#64) MERGED; AE6 (PR #65) on `ae6-tool-task`** — AI Elements adoption on the
  chat surface (ADR-F011). The **AE-series** brings the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **VENDOR APPROACH (AE0–AE6):** token system is **identical** to ours (shadcn-svelte + Tailwind v4) so
  remap ≈ identity. **ADR-F011 option-2 (hand-build, don't vendor) used again in AE6:** the AE `tool`/`task`
  registry items pull `collapsible` + `badge` + `runed` + `./code.json` / `bits-ui` — so the AE Tool card +
  Task step-list identity were hand-built on native `<details>` directly in `ConversationPanel.svelte` (NOT
  vendored). **`shiki` (AE4) remains the ONLY new runtime dep** through the AE series; AE5+AE6 added none.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE6** (the spec is bundle-independent,
  but the bundle carries the AE6 ConversationPanel changes).
  Login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 816** (net baseline — +5 `groupTurnSteps`, −5 dead `stepDigest`); **Cypress
  `ae6-tool-task.cy.ts` 7/7** headed/live-stubbed (6 functional + 1 capture; first run had 1 first-visit
  flake on the first test, deterministic 7/7 on the re-run). **api/gateway UNAFFECTED — AE6 touches only
  `web`** (no backend change). AE6 **after** screenshots (agent timeline, light+dark, wide+narrow) in
  `docs/fork/evidence/ae6/`. Adversarial review (fresh-context agent): SHIP, no blockers/should-fixes;
  the one simplification nit (dead `stepDigest`) was FIXED in-slice. Security pass: the 5 `{@html}` sinks
  all route through the shared `renderModelMarkdown` (media-forbid); tool Parameters/Result bodies are
  escaped TEXT bindings (`{t.inputBody}`/`{t.outputBody}`, never `{@html}`); no secrets/stray files; web-only.

## Done (AE6, this slice)

- **`ConversationPanel.svelte`** — the per-turn step timeline is now ONE collapsible AE **Task** list
  (`<details class="ag-task" open>` → search-glyph trigger "N steps" + rotating chevron) holding AE
  **Tool** cards: `<details class="ag-tool">` with a wrench header + natural-language tool name + a status
  **badge** (Completed = `circle-check` on `--color-status-completed-wash`; Running = spinning
  `loader-circle` on `--color-status-running-wash`) + collapsible **Parameters / Result** mono sections.
  The call+result pair into one card via the pure `groupTurnSteps(steps)` helper in `agents/helpers.ts`
  (adjacency-only: same name + parent; the subagent `task` dispatch/result stay separate cards). **The
  `.ag-steps` `<ol>` + `<li>` rows + `details.ag-thinking` are KEPT** so the live specs (f0-s3/s4/s7) still
  match. Reasoning idiom unchanged. Deleted the old `.ag-step__fold/__mono/__digest` + `.ag-step--tool_*`
  CSS. **Polling / stream / staleness / run-level `statusBadge` UNTOUCHED** — grouping is view-only over
  the already-`visibleSteps` list; the step record is never mutated.
- **Convergence (R6 backlog):** `ConversationPanel` **and** `SkillSourceView` dropped their local
  `marked`+`DOMPurify`+`SANITIZE_OPTS` copies and now call the shared `renderModelMarkdown`
  (`sanitize-markdown.ts`), which gained an optional `{ breaks }` param so SKILL.md keeps its hard line
  breaks. One media-forbid sink for the whole model-output surface.
- **Simplification:** deleted the now-dead `stepDigest` + `STEP_DIGEST_LIMIT` (+ their test block) — the
  old collapsed-fold one-liner has no caller after the Tool card.
- **`cypress/e2e/ae6-tool-task.cy.ts`** (7) — live-stubbed agent timeline on `/lq-ai/agents` (one SETTLED
  conversation = model_turn + one tool pair, so polling/streaming never engage): Task grouping ("2 steps",
  `.ag-steps li` ×2), one paired Tool card (`svg.lucide-wrench` + title + Completed badge w/
  `svg.lucide-circle-check`), collapsed-by-default body → expand reveals Parameters+Result (assert on the
  `open` attr, NOT visibility — see gotcha), Reasoning `<details>` kept, Task collapse toggles `open`,
  answer renders; + 1 capture (single visit, theme toggled in place). **NOTICES** + `ai-elements/README.md`
  (`tool`/`task` not-vendored paragraph) + plan updated. **No new ADR** — F011 already sanctions option-2.

## Next slice — pick up exactly here

1. **AE7 — Suggestions** (plan §"AI Elements visual adoption" → AE7; **optional, lowest priority**). The
   AE0 `Suggestion`/`Suggestions` chips are already vendored (`components/ai-elements/suggestion/`). Add
   follow-up suggestion chips above/below a composer **ONLY if a clean, honest data source exists** — else
   back them with SavedPrompts, or **DEFER** (don't invent suggestions). Full four-discipline gate +
   before/after screenshots if it ships. **With AE7 the AE-series closes** (AE0–AE6 done).
2. Other rollout slices (any order — the dark-mode bridge holds un-migrated surfaces):
   Foundation/rail R2–R5, Wave 1 R-CONV-1 (logic; R-CONV-2 → AE6), Wave 2
   R12/R13/R14a-b/R15/R15b-tab-pb/R16, Wave 3 R17a-b/R18/R19a-b/R20/R-CHROME, cleanup R-TYPO →
   R-BRIDGE → R-LAST. autonomous R21 = SKIP (deferred to F2/F3, stays on bridge).
3. **F1-S4** (subagent tree + SSE v3-projection adapter) / **F1-S5** (idempotency ledger +
   attribution fan-out) — `docs/fork/plans/F1-replan.md`. **Area skills/subagents ACTIVATION**
   (S9-gated) — wires `composition.py` to pass area skills/subagents + re-runs the S9 matrix.
   **Backlog:** scira-style minimalist interface pass AFTER the AE-series (MILESTONES § Backlog;
   **AGPL → reference-only**, study look/IA, never copy code — unlike the MIT AE port we vendor).

## Rollout progress

- **R-series:** Step 0 ✅ (#50) · R0 ✅ · R1a ✅ (#51) · R6 ✅ (#52) · R7 ✅ (#55) · responsive parity ✅
  (#53) · **R8 ✅ (#57)**. CI unblocked (repo public).
- **AE-series (ADR-F011):** plan+ADR ✅ (#58) · **AE0 ✅ (#59)** vendoring foundation · **AE1 ✅ (#60)**
  Conversation+Message+Response · **AE2 ✅ (#61)** Reasoning+Actions · **AE3 ✅ (#62)** Sources +
  Inline-Citation · **AE4 ✅ (#63)** Code Block (Shiki highlight, option-2 action; the one new dep
  `shiki`) · **AE5 ✅ (#64)** Prompt Input (≡ R9 — option-2; dark-mode column gap FIXED) · **AE6 ✅ (PR #65)**
  Tool+Task (≡ R-CONV-2 — option-2 hand-build, no new dep; `groupTurnSteps`; renderModelMarkdown
  convergence). **Next AE7 Suggestions (optional, lowest priority) → AE-series closes.**

## Carry-overs / review deferrals

- **AE6 — no new carry-overs.** Review SHIP, the one nit (dead `stepDigest`) fixed in-slice. Per-tool
  status has no error state (the record carries no per-tool error signal) — a failed/stale run surfaces
  via the run-level badge + stale banner + the rail's `failed` state, which is honest and documented in
  `toolView`. The cockpit `ConversationHost` stacked collapse (<720px) was verify-only (unchanged); the
  legacy `.ag-layout` 1-col collapse (<900px) is the AE6 narrow shot. ModelPicker/SkillPicker etc. remain
  on the `--lq-*` dark stopgap (their own future slices).
- **AE5 — ChatPanel dark-mode column gap RESOLVED.** The standing AE2 carry-over (central chat *column*
  rendered LIGHT in dark mode while the chrome was dark) is FIXED in AE5: the `<section>` got
  `bg-background text-foreground` and the header/composer migrated off `--lq-*` to semantic tokens.
  Confirmed by `docs/fork/evidence/ae5/ae5-{before,after}-chat-dark-{wide,narrow}.png`. **Note:** the
  remaining composer-adjacent panels still on `--lq-*` (ModelPicker pill, SkillPicker, SavedPromptsPanel)
  render acceptably on the `--lq-*` dark stopgap and are each their own future R/AE slice — NOT migrated here.
- **AE5 — no other new carry-overs.** UX change recorded above (tools stay visible while streaming).
- **AE3 — no new carry-overs.** The fresh-context review's one should-fix (soft-deleted filenames
  surfacing + misleading CASCADE comment) and both nits (unused `isFallbackLabel`; over-vendored
  `inline-citation`/`-text`) were FIXED in-slice, not deferred.
- **AE1 nit (on record):** unused `debugInfo` getter in `stick-to-bottom-context.svelte.ts` — kept
  diffable vs MIT upstream.
- **AE0 nits (on record, byte-faithful to MIT upstream):** `loader-icon.svelte` redundant inline
  `style="color: currentcolor"`; shared static clipPath id across mounted Loaders (renders fine; scope
  with `$props.id()` if a future AE component needs per-instance clip geometry).
- **R8 deferred-on-record:** focus-on-open not asserted in Cypress (Xvfb programmatic focus); drawers not
  full focus-traps (ESC + scrim + `inert` cover practice).
- auth/refresh: per-user session cap + web gate timeout SHIPPED (#47). REMAINING: the
  **deterministic-HMAC index** (removes the global bcrypt scan + bad-token DoS; needs a migration +
  security review — Backlog). **AE3 re-confirmed:** under a LONG spec (7 min, many `cy.visit`) AND
  concurrent Docker load (the api suite running), page loads start timing out (elements "never found") —
  the documented degradation, NOT a code defect. Re-running the spec ALONE on a fresh/uncontended backend
  → **5/5**. More evidence for the HMAC index.
- F1-S3 deferrals: subagent-spec skill names bypass registry validation (validate on activation slice);
  `audit_log.practice_area_id` unindexed; area tier floor operator-set until a model > tier 4.
- ADR-0011 disclosure after F1-S5 attribution. Live SSE token deltas DEAD until a Redis pub/sub
  publisher lands (F1-S4). ADR-0011/F003 conversation memory + compaction → F2.

## Gotchas (carried + new)

- **NEW (AE6): Cypress reports a CLOSED `<details>`'s content as "visible".** Chromium collapses a
  `<details>` by giving non-`<summary>` children a zero box WITHOUT `display:none`, so Cypress'
  `.should('not.be.visible')` FAILS on collapsed content. Assert on the `open` ATTRIBUTE instead
  (`.should('not.have.attr','open')` → click `> summary` → `.should('have.attr','open')`); check inner
  content with `.should('exist')`/`contains`, not visibility. (Cost AE6 two red tests on the first run.)
- **NEW (AE6): a second `cy.visit` to `/lq-ai/agents` mid-test intermittently bounces to `/login`.** The
  capture test originally re-visited per theme; the dark iteration's visit re-triggered auth and
  redirected (the documented first-visit session flake, here fatal because it's not the run's first test).
  Fix: visit + open the thread ONCE, then toggle the theme IN PLACE (`localStorage.theme` + the `.dark`
  class on `<html>`) and screenshot per theme/viewport — no second auth-triggering visit.
- **NEW (AE6): the AE `tool`/`task` registry items are option-2 territory.** `tool` pulls `collapsible` +
  `badge` + `runed` + `./code.json` (the AE4 code block we hand-built, NOT vendored); `task` pulls
  `collapsible` + `bits-ui`. `collapsible` is the same shadcn component dodged for reasoning/sources. Hand-
  build the AE Tool card + Task list on native `<details>` (the ConversationPanel already used that idiom).
- **NEW (AE5): the dark-mode "light chat column" root cause.** The center `<section>` was transparent and
  showed the `(tools)` layout's `.lq-shell { background: var(--lq-canvas) }`, and `--lq-canvas` resolved to
  its LIGHT value on the chat route (a cascade/bundle-order quirk of the legacy `@import practice.css`
  chain — practice.css banks on `:root.dark` winning, but it wasn't on this surface). Fix = stop depending
  on `--lq-*` for the column: give the `<section>` `bg-background text-foreground` (semantic, `.dark`-driven,
  proven on the already-dark sidebar). General rule for the R/AE rollout: when a surface is light-in-dark,
  the migration to semantic tokens IS the fix — don't chase the `--lq-*` cascade.
- **NEW (AE5): the AE `prompt-input` registry item is option-2 territory.** It pulls `ai@^6` (the Vercel AI
  SDK transport we reject — bypasses gateway/SSE/`guarded_tool_call`), `runed`, 6 registry deps, and 23
  SDK-bound `Controller`/context files. Hand-build the identity (`rounded-xl border shadow-sm` shell →
  textarea → `flex justify-between p-1` toolbar; submit = status-driven lucide icon) directly on our composer.
- **NEW (AE5): a dropdown in a bottom toolbar must open UPWARD.** `ModelPicker` got an opt-in `dropUp`
  (`bottom-full mb-1` vs `mt-1`) so its menu doesn't clip off the viewport bottom; opt-in keeps other
  consumers (admin/models) on the default downward menu.
- **NEW (AE5): the composer is inherently the LIVE chat surface** (needs an active chat) — so AE5 has NO
  `_ae-lab` section (a static duplicate would drift). Functional + capture run on `/lq-ai/chats?id=…` with
  the SHORT stubbed fixture (add a `**/api/v1/models` intercept so the toolbar ModelPicker populates). The
  first test of the run still eats the first-`cy.visit` session-establishment latency (fails attempt 1,
  passes on retry) — `retries: { runMode: 2 }` covers it; 7/7 final.
- **NEW (AE4): DOMPurify (3.4.0) DOES preserve CSS custom properties in `style`.** Shiki dual-theme output
  carries the dark palette in a `--shiki-dark` CSS var on each token's inline `style`; class-based dark mode
  breaks silently if the sanitiser strips it. It does NOT — verified in a real browser (Cypress asserts
  `span[style*="--shiki-dark"]` exists post-sanitize + the dark screenshot shows the dark palette). vitest
  env is `node` (no DOM) so DOMPurify behavior is **Cypress-only** to test — don't try to unit-test it.
- **NEW (AE4): Shiki fine-grained setup = no WASM, only listed grammars.** Use `createHighlighter` from
  `shiki` + `createJavaScriptRegexEngine` from `shiki/engine/javascript` (NOT the default oniguruma WASM)
  + an explicit `langs` list. `codeToHtml` THROWS on an unknown lang → `normalizeLang` must map to a loaded
  grammar or `'text'`. `shiki` is the only declared dep; `@shikijs/langs|themes` arrive as its pinned
  transitives.
- **NEW (AE4): a literal `</script>` inside a Svelte `<script>` string closes the block** (parse error).
  Escape the slash — `'<\/script>'` — when a demo string must contain it (the lab injection-safety sample).
- **NEW (AE3): run ruff from the REPO ROOT with the root `ruff.toml`, exactly as CI does.** CI runs
  `ruff check api scripts` + `ruff format --check api scripts` from the repo root. Running ruff from
  inside `api/` uses ruff's DEFAULT settings (the root `ruff.toml` excludes web/ and tunes line-length/
  rules) → spurious "would reformat" noise AND it MISSES rules like `UP017` (`datetime.UTC` over
  `timezone.utc`) — AE3's first CI run failed on exactly that. Correct repro:
  `docker run --rm -v $PWD:/repo -w /repo python:3.12-slim bash -c "pip install -q ruff; ruff check api
  scripts; ruff format --check api scripts"`. Under the root config everything (incl. your edits) is
  format-clean. `mypy app` (run from `api/`) still must pass separately.
- **NEW (AE3): running api pytest off the live dev DB.** The runtime image has NO test deps and the live
  postgres is off-limits. Recipe: throwaway `docker run -d --name <pg> --network lq-ai_default
  pgvector/pgvector:pg16` (+ `CREATE EXTENSION vector`); then
  `docker run --rm --network lq-ai_default -v $PWD/api:/app -v $PWD/skills:/skills:ro -e
  DATABASE_URL=postgresql+asyncpg://lq_ai:lq_ai@<pg>:5432/lq_ai -e LQ_AI_SKILLS_DIR=/skills --entrypoint
  bash lq-ai-api:latest -c "pip install -q -e .[dev]; python -m pytest -q …"`. **Mount `./skills`** or
  migration 0032 (seeds NDA playbook YAML) fails. conftest creates its own `lq_ai_test_*` DB per run.
- **NEW (AE3): the citations intercept glob.** The endpoint is `/chats/{id}/messages/{mid}/citations` —
  AE2's `**/api/v1/messages/*/citations` glob MISSED it (no `/chats/` segment). Use
  `**/api/v1/chats/*/messages/*/citations`.
- **NEW (AE3): option-2 again — Sources + inline-citation.** `sources` pulls `collapsible`;
  `inline-citation` pulls `carousel`+`hover-card`+16 files. Hand-build `Sources` on `<details>`; vendor
  only the dependency-free `inline-citation` primitives you actually use (AE0 "take only what you need").
  Inspect each registry item's `dependencies`/`registryDependencies` BEFORE deciding vendor vs hand-build.
- **(AE2): forward shadcn `Button onclick` through a RUNES wrapper, not the legacy parent** (legacy
  `on:click` on a runes component = silent no-op). `MessageActionsBar`/`MessageSources` are runes wrappers
  the legacy `MessageBubble` feeds plain props.
- **(AE2): lab-based functional Cypress dodges the auth-login flakiness.** `_ae-lab` is auth-gated but
  makes no API calls → deterministic interaction tests run there; use the live chat surface only for the
  integration check + before/after capture. Distinguish icons via lucide `svg.lucide-<name>`.
- **(AE1): the AE dark-capture recipe.** SHORT fixture · `localStorage.theme` BEFORE `cy.visit` · post-boot
  class pin · `cy.get('html').should('have.class', theme)` · 1px viewport nudge before `cy.screenshot`.
- **(AE1): wrapping a Svelte-4 component's content in runes children works** (legacy slots → `children`
  snippet). Alias the AE `Message` *component* vs our `Message` *type* (`Message as AeMessage`).
- **(AE0): the AE vendor pipeline** = shadcn-svelte registry JSON (`…/r/<c>.json`), NOT jsrepo. INSPECT
  before vendoring. Items can under-declare deps. Never adopt the `streamdown-svelte` `response` sink —
  keep `renderModelMarkdown`. **"dev-only route"** = unadvertised, auth-gated, leading-`_` (`_ae-lab`);
  the web container always serves a PROD build. Vendored AE source is eslint-exempt; kept prettier-formatted.
- web CI gates only `npm run check` + vitest (eslint/prettier NOT gated). `npx vitest run` (NOT
  `test:frontend` = watch). vitest env is `node` (no jsdom) — DOMPurify/sanitisation must be Cypress-tested.
  **headless cypress lies about dark theme — capture headed** (`DISPLAY=:0`); **rebuild the `web`
  container before screenshotting/Cypress-testing a UI change.** Cypress trashes `cypress/screenshots`
  at run START — copy before/after frames to `docs/fork/evidence/` immediately after each run.
- `gh pr create` defaults to FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork` AND
  `--head <branch>` (ADR-F001). jq NOT installed — parse `gh --json` with python3 (run from repo dir,
  `/tmp/types.py` shadows stdlib `types`).
- migrations: NEVER host-side alembic against the live dev DB; api auto-migrates on boot; rebuild
  api+arq-worker+ingest-worker together + web. **NEVER `docker compose down -v`.**
- MiniMax-M3 is tier 4 (weak) — `default_tier_floor` < 4 makes every run 403. deepagents subagent `model`
  string = gateway-bypass (ADR-F010 guard at `build_deep_agent`). New API endpoints register in
  tests/test_openapi.py (count assert) — AE3 added NO endpoint (a field on an existing one).
