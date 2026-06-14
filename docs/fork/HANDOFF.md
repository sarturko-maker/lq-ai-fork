# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (AE4 MERGED — next is AE5)

- **AE0 (#59) + AE1 (#60) + AE2 (#61) + AE3 (#62) + AE4 (PR #63) MERGED** — AI Elements adoption on the
  chat surface (ADR-F011). The **AE-series** brings the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **VENDOR APPROACH (AE0–AE4):** token system is **identical** to ours (shadcn-svelte + Tailwind v4) so
  remap ≈ identity. **ADR-F011 option-2 (hand-build, don't vendor) used again in AE4:** the AE `code`
  registry item pulls `svelte-toolbelt` + a separate `copy-button` registry item + line-number/overflow
  machinery + a controlled-`code`-prop API that doesn't fit our `{@html}` sink — so the AE code-block
  identity was hand-built in `lib/lq-ai/code/` as a Svelte action over the sanitized output (NOT vendored).
  **AE4 adds the ONE new runtime dep ADR-F011 pre-approved: `shiki` (`^4.2.0`).** It is the only new dep
  through the AE series.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE4**.
  Login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 816** (811 + 5 new `code/__tests__/shiki.test.ts`); **Cypress `ae4-code-block.cy.ts` 8/8**
  headed/live (lab functional ×5 + live integration + 2 capture; one cold-boot first-attempt flake,
  clean 8/8 on a warm re-run). **api/gateway UNAFFECTED — AE4 touches only `web`** (no backend change).
  AE4 after-screenshots (lab code cards + chat surface, light+dark, wide+narrow) in
  `docs/fork/evidence/ae4/`. Adversarial review (fresh-context agent): see PR #63. Security pass: highlight
  runs only on already-sanitized `.textContent`; Shiki output **re-sanitized with DOMPurify** before it
  re-enters the DOM (no new injection sink); injected `<script>` renders as inert text (Cypress-asserted);
  DOMPurify preserves `--shiki-dark` so dark mode works (Cypress + screenshot); shiki is the only new dep;
  no secrets/stray files.

## Done (AE4, this slice)

- **`lib/lq-ai/code/shiki.ts`** — fine-grained Shiki highlighter singleton: bundled `createHighlighter`
  + the **pure-JS regex engine** (`shiki/engine/javascript`, no WASM) + GitHub light/dark **dual-theme** +
  an explicit modest language list. `normalizeLang(raw)` maps aliases (`sh`→bash, `ts`→typescript,
  `py`→python, `postgres`→sql, …) + case/whitespace-insensitive + **falls back to `text`** for unknown
  langs (codeToHtml throws on an unknown lang). Vitest `code/__tests__/shiki.test.ts` (5).
- **`lib/lq-ai/code/enhance.ts`** — `enhanceCodeBlocks` **Svelte action** (mirrors
  `citations/decorate-inline.ts`): finds `pre > code` in the **already-sanitized** `{@html}` output,
  reads `.textContent` (a plain string), Shiki-highlights it, **re-sanitizes Shiki's output with
  DOMPurify**, then swaps in the AE card (language header + copy button top-right). No-op while
  `enabled === false` (streaming); a **generation counter + `pre.isConnected` guard** discard stale/
  detached async results; highlight failure leaves the raw `<pre>` (never drops the code). Copy button
  has an accessible label + transient "Copied" confirmation.
- **`app.css`** — a `.lq-code` block for the Shiki-generated `<pre class="shiki">` internals (padding,
  mono font, `overflow-x`) + the **class-based dark swap** (`.dark .lq-code .shiki span { color:
  var(--shiki-dark) }`); Shiki's own bg forced transparent so the card supplies one bg per theme.
- **`MessageBubble.svelte`** — `use:enhanceCodeBlocks={{ enabled: !isStreaming }}` on the same prose
  `<div>` as `decorateCitationsInline` (orthogonal: one acts on `pre>code`, the other on text markers).
- **`_ae-lab`** — code-block demo through the REAL chat path (markdown → `renderModelMarkdown` → `{@html}`
  → action): python, sql, an unsupported `cobol` (→ text), and a no-language fence with a literal
  `<script>` (injection-safety proof). **NOTICES** (new `code/**` row + shiki SBOM) + `ai-elements/README.md`
  (option-2 note) updated. **`cypress/e2e/ae4-code-block.cy.ts`** (8). **No new ADR** — F011 already
  sanctioned both `shiki` and the option-2 pattern; the action approach mirrors the accepted
  `decorate-inline` seam.

## Next slice — pick up exactly here

1. **AE5 — Prompt Input** (plan §"AI Elements visual adoption" → AE5; **≡ the old R9 slot**). Composer →
   AE **Prompt Input**: unified rounded shell + toolbar (model selector, attach 📎, enhance ✨, receipts
   📜, submit/stop). KEEP `SlashPopover` + `EnhancePromptExpansion`. **Also migrates ChatPanel's remaining
   `--lq-*` shell** — this fixes the standing **dark-mode shell gap** (see Carry-overs: the central chat
   *column* renders LIGHT in dark mode because ChatPanel's shell still uses legacy `--lq-*`). **Responsive
   collapse REQUIRED in the narrow shot.** Inspect the AE `prompt-input` registry item first
   (`curl …/r/prompt-input.json`, parse with python3 — NOT jq; mind `/tmp/types.py`) and apply option-2
   if it pulls avoided deps. Full four-discipline gate + before/after screenshots (light+dark, wide+narrow).
   Then **AE6 Tool+Task (≡ old R-CONV-2 slot; responsive)** → AE7 Suggestions (the AE0 `Suggestion` chips
   are ready). **Backlog (from R6):** converge `ConversationPanel` + `SkillSourceView` onto
   `renderModelMarkdown` (do as part of AE6).
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
  Inline-Citation · **AE4 ✅ (PR #63)** Code Block (Shiki highlight, option-2 action; the one new dep
  `shiki`). **Next AE5 (Prompt Input ≡ R9 — migrates ChatPanel shell + fixes the dark-mode column gap).**

## Carry-overs / review deferrals

- **AE2 — ChatPanel dark-mode shell gap (deferred to AE5 ≡ old R9):** in the wide layout the central
  chat *column* renders LIGHT in dark mode while the chrome is dark — ChatPanel shell still uses legacy
  `--lq-*` tokens. Pre-existing (AE1+AE2), NOT an AE3 regression (AE3 touched only the message footer +
  the new Sources card, both semantic-token). **AE5 migrates ChatPanel's `--lq-*` block.**
- **AE4 — no new carry-overs.** The ChatPanel dark-mode shell gap above is unchanged by AE4 (AE4 only
  added a `use:` action on the existing prose `<div>` + a `.lq-code` CSS block + `lib/lq-ai/code/`).
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
