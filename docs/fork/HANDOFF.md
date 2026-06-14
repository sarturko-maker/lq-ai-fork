# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (AE1 MERGED — next is AE2)

- **AE0 (PR #59, `77855f9`) + AE1 (PR #60) MERGED** — AI Elements adoption on the chat surface
  (ADR-F011). The **AE-series** brings the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **VENDOR APPROACH CONFIRMED (AE0 + AE1):** the port is high quality; the token system is **identical**
  to ours (shadcn-svelte + Tailwind v4) so remap ≈ identity. AE1 proved the pipeline on a REAL live
  surface with **zero new runtime deps** (one transitive, `runed`, promoted to a declared devDep).
  The ADR-F011 option-2 hand-build fallback remains available per-component but is not needed.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE1**.
  Login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 803**; **Cypress `ae1-conversation.cy.ts` 5/5** + regression **`r6` 3/3 · `m2-c2` 1/1 ·
  `wave-m1` 3/3**, headed/live. Before/after screenshots (light+dark × wide+narrow, 8 PNGs) in
  `docs/fork/evidence/ae1/`. Adversarial review (fresh-context agent): **ship-ready — 0 blocker /
  1 should-fix (actioned: `runed` phantom dep → declared) / 2 nits (1 actioned: sentinel
  `aria-hidden`; 1 left diffable)**. Security pass CLEAN (no secrets; the only `{@html}` are the
  pre-existing DOMPurify-sanitized `rendered`/`reasoningHtml`; no `@ai-sdk/svelte`/`streamdown`/`shiki`
  imports; 0 `var(--lq-)`; package.json/lockfile delta = the 1 `runed` line only).
  - **NOTE (real-backend specs, NOT AE1 regressions):** `f0-s5-multi-turn` timed out at **file
    ingestion** (worker round-trip) and `f0-s7-stream` **skips** without `LQ_AI_MATTER_NAME` (live SSE
    deltas DEAD until F1-S4). AE1 is web-only — no ingestion/streaming/transport code touched.

## Done (AE1, this slice)

- **Vendored `ai-elements/conversation/`** (full block) — `Conversation` (scroll container,
  `role="log"`) + `ConversationContent` (the scroller) + `ConversationScrollButton` (sticky
  scroll-to-bottom) + `EmptyState`, backed by a runes `StickToBottomContext` (Resize/Mutation/
  Intersection observers auto-scroll on append UNLESS the user scrolled up). **Fixed an upstream
  double `bind:this`** (Svelte 5 compile error) + added `aria-hidden` to the sentinel.
- **Vendored `ai-elements/message/` CORE ONLY** — `Message` + `MessageContent` (the identity: user
  `bg-secondary` soft right bubble; assistant plain full-width `text-foreground`). **NOT vendored:**
  the upstream Streamdown `response` (would bypass our sink), `branching`/`attachments`/`actions`
  (AE2/AE4). Context trimmed to the `MessageRole` type.
- **`MessageList` → runes** — renders Conversation/Content/ScrollButton/EmptyState; dropped the
  `afterUpdate` hard-scroll; kept the `lq-ai-message-list` testid on the scroller; added a
  `lq-ai-scroll-bottom` testid on the scroll button.
- **`MessageBubble` → Message + full-width Response** — wraps each turn in `Message`/`MessageContent`
  (AE `Message` aliased `AeMessage` to avoid the `Message` *type* clash). Assistant renders OUR
  `renderModelMarkdown` prose as the "Response" (port's markdown sink NOT adopted). **All plumbing
  unchanged** (ReasoningRibbon, `use:decorateCitationsInline`, M2Citations, TierBadge,
  AppliedSkillsChip, capture, overflow, refusal, error, enhanced pill). Dropped dead `bubbleClasses`;
  annotated the sanitized `{@html}` (net −1 lint error).
- **`runed` promoted** transitive→declared devDep (`^0.35.1`; surgical 1-line lockfile add, `npm ci`
  verified). **NOTICES + `ai-elements/README.md`** updated.
- **`cypress/e2e/ae1-conversation.cy.ts`** (structure + before/after capture; SHORT fixture for
  capture so auto-scroll doesn't fight the shot). **`r6` tweak:** `scrollIntoView()` the ribbon
  summary before the visibility check (AE1's `gap-8` + auto-scroll can push a middle turn's collapsed
  ribbon above the fold — rendered + functional, just not in view; same idiom the spec already uses).

## Next slice — pick up exactly here

1. **AE2 — Reasoning + Actions** (plan §"AI Elements visual adoption" → AE2). `primitives/ReasoningRibbon`
   → AE **Reasoning** (shimmer while streaming, auto-collapse on complete + a duration); add per-message
   **Actions** (copy / retry / copy-citation) wired to the existing rerun + stream handlers. **Inspect
   first** (proven pipeline): `curl https://svelte-ai-elements.vercel.app/r/reasoning.json` (+ `actions`
   if a separate item) — parse with python3 from the repo dir (NOT jq; mind `/tmp/types.py` shadowing).
   The `message` block's `actions/` subtree was deliberately left unvendored in AE1 — pull it here.
   Watch for `mode-watcher`/`shiki`/`streamdown` deps in those items (defer/avoid; Shiki is AE4). Keep
   reasoning sanitization unchanged (`renderModelMarkdown`). **Adversarial:** reasoning sanitization,
   action focus/keyboard, retry idempotency, dark contrast. Full four-discipline gate + before/after
   screenshots. **AE-capture recipe (AE1 finding, see Gotchas):** SHORT fixture + localStorage-theme-
   before-visit + post-boot `setTheme` class pin + `html.should('have.class')` + a viewport nudge.
   Then AE3 Sources+InlineCitation → AE4 Code Block (**`shiki` dep**) → **AE5 Prompt Input (≡ old R9
   slot)** → **AE6 Tool+Task (≡ old R-CONV-2 slot)** → AE7 Suggestions (the AE0 `Suggestion` chips are
   ready). **Backlog (from R6):** converge `ConversationPanel` + `SkillSourceView` onto
   `renderModelMarkdown` (do as part of AE6).
2. Other rollout slices (any order — the dark-mode bridge holds un-migrated surfaces):
   Foundation/rail R2–R5, Wave 1 R-CONV-1 (logic; R-CONV-2 → AE6), Wave 2
   R12/R13/R14a-b/R15/R15b-tab-pb/R16, Wave 3 R17a-b/R18/R19a-b/R20/R-CHROME, cleanup R-TYPO →
   R-BRIDGE → R-LAST. autonomous R21 = SKIP (deferred to F2/F3, stays on bridge).
3. **F1-S4** (subagent tree + SSE v3-projection adapter) / **F1-S5** (idempotency ledger +
   attribution fan-out) — `docs/fork/plans/F1-replan.md`. **Area skills/subagents ACTIVATION**
   (S9-gated) — wires `composition.py` to pass area skills/subagents + re-runs the S9 matrix.

## Rollout progress

- **R-series:** Step 0 coverage table ✅ (PR #50) · R0 ✅ (#50) · R1a ✅ (#51) · R6 ✅ (#52) ·
  R7 ✅ (#55) · responsive parity ✅ (#53) · **R8 ✅ (#57, `183abd9`)**. CI unblocked (repo public).
- **AE-series (ADR-F011):** plan + ADR accepted ✅ (#58, `c2b505f`) · **AE0 ✅ (#59, `77855f9`)** —
  vendoring foundation · **AE1 ✅ (#60)** — Conversation + Message + full-width Response (live chat
  surface). Vendor approach confirmed; next AE2.

## Carry-overs / review deferrals

- **AE1 nit (accepted on record):** the upstream `debugInfo` getter in `stick-to-bottom-context.svelte.ts`
  is unused; left in to stay diffable against the MIT upstream (the "owned but diffable" convention).
- **AE0 nits (accepted on record, kept byte-faithful to the MIT upstream):** (a) `loader-icon.svelte`
  carries a redundant inline `style="color: currentcolor"`. (b) the upstream clipPath
  `id="clip0_2393_1490"` is static, so N mounted Loaders share the id — invalid HTML strictly, but
  every instance has identical clip geometry so `url(#clip…)` resolves to the first and all render
  correctly. Scope the id (`$props.id()`) if a future AE component needs per-instance clip geometry.
- **R8 deferred-on-record:** focus-on-open implemented but NOT asserted in Cypress (headed-Electron/
  Xvfb programmatic focus doesn't set `document.activeElement` without OS window focus). Drawers are
  not full focus-traps (cockpit defers this too); ESC + scrim-click + `inert`-on-close cover practice.
- auth/refresh: per-user session cap + web gate timeout SHIPPED (#47). REMAINING: the
  **deterministic-HMAC index** (removes the global bcrypt scan + bad-token-spam DoS; needs a
  migration + security review — Backlog). **AE1 observation:** under sustained rapid Cypress logins
  (dozens/session) the auth backend degrades and `cy.login` intermittently times out (pre-AE1-render,
  i.e. NOT an AE1 defect — every AE1 failure this session was login/load-timeout, never an assertion).
  Mitigated in `ae1-conversation.cy.ts` with **`cy.session` (login once) + `retries:{runMode:2}`**;
  the spec is 5/5 when the stack isn't hammered. This is more evidence for prioritizing the HMAC index.
- F1-S3 deferrals: subagent-spec skill names bypass registry validation (validate on the activation
  slice); `audit_log.practice_area_id` unindexed; area tier floor operator-set until a model > tier 4.
- ADR-0011 disclosure after F1-S5 attribution. Live SSE token deltas DEAD until a Redis pub/sub
  publisher lands (F1-S4). ADR-0011/F003 conversation memory + compaction → F2.

## Gotchas (carried + new)

- **NEW (AE1): the AE dark-capture recipe.** A SHORT fixture is mandatory for screenshots — the AE
  Conversation auto-scrolls to the latest turn, so a long thread scrolls the interesting content out
  of frame AND the in-flight smooth-scroll fights the shot (renders mid-thread / wrong theme). Recipe
  that works (see `ae1-conversation.cy.ts` capture describe): 2-message fixture · `localStorage.theme`
  set BEFORE `cy.visit` · post-boot `setTheme()` class pin · `cy.get('html').should('have.class', theme)`
  · a 1px viewport nudge before `cy.screenshot`. Long fixtures are fine for STRUCTURE tests (scroll
  button etc.), just not for captures.
- **NEW (AE1): wrapping a Svelte-4 component's content in runes children components works** — a legacy
  `MessageBubble` renders the runes `Message`/`MessageContent` via default slots (Svelte 5 bridges
  legacy slots → the `children` snippet). The `Message` *type* (../types) vs AE `Message` *component*
  collide — alias the import (`Message as AeMessage`).
- **NEW (AE1): a first-party import of a transitive dep is fragile** — declare it. `conversation/`
  imports `runed` directly, so it was promoted from shadcn transitive to a declared `devDependency`
  (`^0.35.1`). Surgical 1-line lockfile edit (add to root `devDependencies`; the `node_modules/runed`
  node already existed) keeps `npm ci` green without the wasm-wasi optional-dep churn that a full
  `npm install` introduces.
- **AE0: the AE vendor pipeline.** Distribution is **shadcn-svelte registry JSON**, NOT jsrepo (the
  plan said jsrepo; the actual mechanism is `…/r/<component>.json`). INSPECT the JSON before vendoring
  (deps / registryDependencies / `{@html}` / tokens). Items use CLI placeholders `$COMPONENTS$`/`$UTILS$`
  — substitute to `$lib/components`/`$lib/utils`. Items can **under-declare** registry deps (e.g.
  `suggestion` omits `scroll-area`; `conversation`'s scroll-button needs `button`). The port's
  `response`/heavier blocks ship a `streamdown-svelte` markdown sink — **never adopt it; keep
  `renderModelMarkdown`**, take only the prose styling. Take only the files you need (AE1 took
  `message` CORE, not the whole block).
- **AE0: "dev-only route" reality.** The web container ALWAYS serves a prod build (no separate dev
  deploy), so `import.meta.env.DEV` would make a route invisible in our only stack AND untestable by
  Cypress (baseUrl :3000 = the built container). "Dev-only" = an **unadvertised, auth-gated, internal**
  route (`_ae-lab`). A **leading-`_` directory DOES route** in this SvelteKit version (verified RouteId).
- **AE0: vendored AE source is eslint-exempt** (`.eslintignore` `ai-elements/`) for the same
  `custom_element_props_identifier` false positive as `ui/*`; kept prettier-formatted. eslint is NOT
  CI-gated (only `npm run check` + vitest are).
- **R8: chai-jquery subject rebinding** — `.and('have.attr', name[, val])` REBINDS the chained subject
  to the attr value/undefined; put multiple attribute checks in ONE `.should(($el) => {…})` callback.
- **R8: `inert` for off-canvas drawers** — CSS `translate-x-full` only hides visually; descendants stay
  focusable + in the a11y tree. Use `inert={(isNarrow && !open) || undefined}`. A DYNAMIC
  `role={isNarrow ? 'dialog' : undefined}` defeats svelte-check's a11y static analysis → use a static
  `tabindex="-1"`.
- **R8: active row on a translucent wash needs a backing surface for AA** — bare `text-primary` over
  `bg-muted/40` fails AA in dark (4.12:1). Give active rows `bg-accent text-accent-foreground`.
- shadcn `Button onclick` only forwards from a **runes** parent (legacy `on:click` = silent no-op).
  `text-primary` on `bg-accent` fails WCAG AA → use `text-accent-foreground`. `text-destructive` on a
  tinted bg fails AA in dark → add a `dark:` lift (`dark:text-red-300`).
- web CI gates only `npm run check` + vitest (eslint NOT gated). `test:frontend` is vitest WATCH mode —
  run `npx vitest run`. vitest env is `node` (no jsdom) — DOMPurify/sanitisation must be Cypress-tested.
  **headless cypress lies about dark theme — capture headed** (`DISPLAY=:0`), and **rebuild the `web`
  container before screenshotting/Cypress-testing a UI change** (it serves a pre-built bundle). Cypress
  trashes `cypress/screenshots` at the START of each run (`trashAssetsBeforeRuns`) — copy before/after
  frames to `docs/fork/evidence/` IMMEDIATELY after each phase run.
- `gh pr create` defaults to FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork` AND
  `--head <branch>` (ADR-F001). jq NOT installed — parse `gh --json` with python3 (mind `/tmp/types.py`
  can shadow stdlib `types` — run python from the repo dir, not `/tmp`).
- migrations: NEVER host-side alembic against the live dev DB; api auto-migrates on boot; rebuild
  api+arq-worker+ingest-worker together + web. **NEVER `docker compose down -v`.**
- MiniMax-M3 is tier 4 (weak) — `default_tier_floor` < 4 makes every run 403. Seed areas with NO floor.
  deepagents subagent `model` string = gateway-bypass (ADR-F010 guard at `build_deep_agent`). New API
  endpoints register in tests/test_openapi.py (count assert).
