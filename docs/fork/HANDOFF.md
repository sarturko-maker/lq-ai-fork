# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (AE5 MERGED — next is AE6)

- **AE0 (#59) + AE1 (#60) + AE2 (#61) + AE3 (#62) + AE4 (#63) + AE5 (PR #64) MERGED** — AI Elements adoption on the
  chat surface (ADR-F011). The **AE-series** brings the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **VENDOR APPROACH (AE0–AE5):** token system is **identical** to ours (shadcn-svelte + Tailwind v4) so
  remap ≈ identity. **ADR-F011 option-2 (hand-build, don't vendor) used again in AE5:** the AE
  `prompt-input` registry item pulls `ai@^6` (the AI SDK transport we reject) + `runed` + 6 registry deps +
  23 SDK-bound context files — so the AE Prompt Input identity was hand-built directly on the existing
  composer in `ChatPanel.svelte` (NOT vendored). **`shiki` (AE4) remains the ONLY new runtime dep** through
  the AE series; AE5 added none.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE5**.
  Login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 816** (unchanged — AE5 is a UI restructure, no unit tests added); **Cypress
  `ae5-prompt-input.cy.ts` 7/7** headed/live (6 functional + 1 capture; the first test's attempt-1 eats the
  first-`cy.visit` session-establishment latency → fails then passes on retry — the documented first-visit
  flake, NOT a code defect; 7/7 final on TWO runs). **api/gateway UNAFFECTED — AE5 touches only `web`** (no
  backend change). AE5 **before+after** screenshots (chat surface, light+dark, wide+narrow) in
  `docs/fork/evidence/ae5/` — the before-dark clearly shows the LIGHT chat column; the after-dark shows it
  fixed. Adversarial review (fresh-context agent): SHIP, no blockers/should-fixes, 2 cosmetic nits left
  (consistent `text-white` Stop; icon-btn class dedup). Security pass: no new `{@html}`/sink (textarea is
  `bind:value`); no secrets/stray files; web-only.

## Done (AE5, this slice)

- **`ChatPanel.svelte`** — the composer is now ONE unified AE **Prompt Input** shell:
  `<div data-testid="lq-ai-prompt-input">` → `rounded-xl border border-input bg-card shadow-sm
  focus-within:ring-1` holding the textarea (transparent/borderless) on top + a bottom toolbar
  (`data-testid="lq-ai-prompt-toolbar"`, `flex items-center justify-between`): LEFT = `ModelPicker dropUp`
  + attach/enhance/receipts **lucide** icon-buttons (Paperclip/Sparkles/ScrollText — emoji retired);
  RIGHT = Send (lucide Send) / Stop (lucide Square). KEPT every wire + `data-testid`
  (`lq-ai-send-btn`/`-abort-btn`/`-attach-kb-btn`/`-enhance-btn` + `data-enhance-mode`/`-receipts-toggle`/
  `-composer-input`/`-composer`), `SlashPopover` (now anchored to the shell via the kept
  `.lq-composer-popover` rule), `EnhancePromptExpansion`, `SkillPicker`, `SavedPromptsPanel`. **UX change
  on record:** tools stay VISIBLE during streaming (only Send↔Stop swaps); Enhance still `disabled` while
  streaming. Header + composer + `<section>` migrated off `--lq-*`/`text-gray-*`/hardcoded-white to semantic
  tokens (`bg-background`/`border-border`/`bg-card`/`text-foreground`/`text-muted-foreground`/`bg-primary`/
  `bg-destructive`); the `<section>` got `bg-background text-foreground` — **the dark-mode column-gap fix**.
  Deleted the scoped `.lq-composer/.lq-btn-*/.lq-composer-wrap` styles + the now-unused `@import
  practice.css` (children still import it, so global `--lq-*` :root rules remain for them).
- **`ModelPicker.svelte`** — opt-in `dropUp` prop (default false): toolbar usage opens the menu UPWARD
  (`bottom-full mb-1`) so it doesn't clip at the viewport bottom; admin/models page keeps the default
  downward menu. No token change to ModelPicker (still `--lq-*`, its own future slice).
- **`cypress/e2e/ae5-prompt-input.cy.ts`** (7) — live stubbed chat surface (the composer is inherently the
  live surface; no lab section to avoid a drifting static duplicate): unified shell, toolbar contents +
  lucide SVGs, send disabled→enabled, Enhance opens its panel, slash popover anchors, model menu opens
  upward; + before/after capture. **NOTICES** (AE row note: option-2, no vendoring, no new dep) +
  `ai-elements/README.md` (`prompt-input` not-vendored paragraph) + plan updated. **No new ADR** — F011
  already sanctions option-2; the token migration is the established rollout pattern.

## Next slice — pick up exactly here

1. **AE6 — Tool + Task** (plan §"AI Elements visual adoption" → AE6; **≡ the old R-CONV-2 slot**).
   `ConversationPanel` agent steps (`ag-step--tool_call/tool_result`) → AE **Tool** (collapsible
   name/input/output/status) + **Task** (step list); keep the Reasoning idiom; **keep ALL polling /
   stale-detection / statusBadge logic untouched** (R-CONV-1 already extracted it). **Responsive collapse
   REQUIRED in the narrow shot.** Inspect the AE `tool`/`task` registry items first (`curl …/r/<c>.json`,
   parse with python3 — NOT jq; mind `/tmp/types.py`) and apply option-2 if they pull avoided deps.
   **Backlog (from R6, do as part of AE6):** converge `ConversationPanel` + `SkillSourceView` onto
   `renderModelMarkdown`. Full four-discipline gate + before/after screenshots (light+dark, wide+narrow).
   Then **AE7 Suggestions** (the AE0 `Suggestion` chips are ready; optional/lowest priority).
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
  `shiki`) · **AE5 ✅ (PR #64)** Prompt Input (≡ R9 — option-2 hand-build, no new dep; migrated ChatPanel
  shell off `--lq-*` → **dark-mode column gap FIXED**). **Next AE6 (Tool+Task ≡ R-CONV-2 slot) → AE7.**

## Carry-overs / review deferrals

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
