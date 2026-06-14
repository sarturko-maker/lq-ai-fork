# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (AE2 MERGED — next is AE3)

- **AE0 (PR #59, `77855f9`) + AE1 (PR #60) + AE2 (PR #61) MERGED** — AI Elements adoption on the chat
  surface (ADR-F011). The **AE-series** brings the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **VENDOR APPROACH CONFIRMED (AE0–AE2):** the port is high quality; the token system is **identical**
  to ours (shadcn-svelte + Tailwind v4) so remap ≈ identity. Still **zero new runtime deps** through AE2.
  **AE2 was the first to use the ADR-F011 option-2 hand-build fallback** (the AE `reasoning` registry
  block pulls 4 deps we avoid — streamdown/shiki/mode-watcher/collapsible — so the AE Reasoning identity
  was hand-built on our accessible `<details>` instead of vendored). The actions subtree WAS cleanly
  vendored (reuses `ui/button`+`ui/tooltip`).
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE2**.
  Login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 803**; **Cypress `ae2-reasoning-actions.cy.ts` 7/7** + regression **`ae1` 5/5 · `r6` 3/3**,
  headed/live. AE2 after-screenshots (chat surface, light+dark wide) in `docs/fork/evidence/ae2/`; the
  **AE2 "before" baseline = `docs/fork/evidence/ae1/ae1-after-conversation-*-wide.png`** (same main
  bundle/fixture pre-AE2 — shows old ribbon + no actions; saves a rebuild). Adversarial review
  (fresh-context agent): **SHIP — 0 blocker / 0 should-fix / 3 nits (all left on record)**. Security
  pass CLEAN (no new `{@html}`; model `<think>` sanitized via `renderModelMarkdown` before the
  ribbon; clipboard writes are inert plaintext; no new deps; no secrets/stray files).
  - **NOTE (real-backend specs, NOT AE2 regressions):** `f0-s5-multi-turn` timed out at **file
    ingestion** and `f0-s7-stream` **skips** without `LQ_AI_MATTER_NAME` (live SSE deltas DEAD until
    F1-S4). AE2 is web-only. The first run of `r6`+`ae1` showed `r6` "1 failing 2 skipped" = a
    `beforeEach` LOGIN timeout (r6 has no `cy.session`/retries) under the degraded auth backend — r6
    re-run ALONE = **3/3**. Same documented login flakiness, NOT a ribbon defect.

## Done (AE2, this slice)

- **Vendored `ai-elements/message/actions/`** — `message-action.svelte` (ghost icon-button + tooltip +
  sr-only label; reuses `ui/button` + `ui/tooltip`), `message-actions.svelte` (inline row),
  `message-toolbar.svelte` (footer row). Exported from `message/index.ts`. Re-tokened (identity).
- **NEW `MessageActionsBar.svelte` (runes)** — the per-assistant-message toolbar: **Copy** (answer text),
  **Retry** (callback), **Copy-sources** (formatted citations, hidden when none). Self-contained
  clipboard + transient "copied" tick. It's a **runes** wrapper on purpose: the legacy `MessageBubble`
  feeds it plain props/callbacks, and the shadcn `Button` `onclick` forwards reliably from a runes parent
  (a legacy `on:click` on a runes component is a silent no-op — see Gotchas).
- **`ReasoningRibbon` → AE Reasoning identity (option-2 hand-build)** — brain icon, rotating chevron,
  "Thinking…" shimmer while streaming, measured "Thought for Ns", auto-open-while-streaming +
  one-shot auto-collapse. Kept on the accessible native `<details>` + the sanitized slot. New optional
  `streaming`/`durationSeconds` props are DORMANT on the live chat surface (no separate reasoning
  stream until F1-S4) → renders a static "Reasoning" there; the streaming path is exercised in `_ae-lab`.
- **`MessageBubble`** — renders `<MessageActionsBar>` in the assistant footer (answer = `split.visible`,
  `sources` formatted from `fetchedCitations`, `onRetry`); added `onRetry` prop. **All other plumbing
  unchanged.** **`MessageList`/`ChatPanel`** — thread `onRetry`; `handleAssistantRetry` reuses the
  extracted `rerunPrecedingPrompt` (shared with `handleRefusalRerun`).
- **`_ae-lab`** — added Reasoning (with a streaming toggle) + actions-bar demo sections. **NOTICES +
  `ai-elements/README.md`** updated (actions vendored; reasoning option-2 recorded).
- **`cypress/e2e/ae2-reasoning-actions.cy.ts`** (7 tests) — lab: ribbon idle/streaming/duration/
  auto-collapse + copy/copy-sources/retry; live chat: assistant-only actions; before/after capture.

## Next slice — pick up exactly here

1. **AE3 — Sources + Inline Citation** (plan §"AI Elements visual adoption" → AE3). Wrap the M2 Citation
   Engine in AE **Sources** (collapsible "Used N sources") + **Inline Citation** styling; **preserve the
   5-state verification UI + the lazy `GET /messages/{id}/citations` single-fetch** (`fetchedCitations`
   in `MessageBubble`; `M2Citations.svelte`; `decorate-inline.ts`). **Inspect first** (proven pipeline):
   `curl https://svelte-ai-elements.vercel.app/r/sources.json` + `r/inline-citation.json` — parse with
   python3 from the repo dir (NOT jq; mind `/tmp/types.py`). Watch for `streamdown`/`shiki`/`mode-watcher`
   deps (defer/avoid; Shiki is AE4) — if the item pulls them, use the **option-2 hand-build** (as AE2 did
   for reasoning). **Untrusted:** source titles/quotes are model+document output — escape, never `{@html}`
   without `renderModelMarkdown`. **Adversarial:** verification-state contrast (the 5 states read AA in
   dark), single-fetch race, source-title escaping. Full four-discipline gate + before/after screenshots.
   **AE-capture recipe (see Gotchas):** SHORT fixture + localStorage-theme-before-visit + post-boot
   `setTheme` class pin + `html.should('have.class')` + viewport nudge; lab-based functional tests dodge
   the auth-login flakiness.
   Then AE4 Code Block (**`shiki` dep**) → **AE5 Prompt Input (≡ old R9 slot; also migrates ChatPanel's
   remaining `--lq-*` shell — see Carry-overs)** → **AE6 Tool+Task (≡ old R-CONV-2 slot)** → AE7
   Suggestions (the AE0 `Suggestion` chips are ready). **Backlog (from R6):** converge `ConversationPanel`
   + `SkillSourceView` onto `renderModelMarkdown` (do as part of AE6).
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
  vendoring foundation · **AE1 ✅ (#60)** — Conversation + Message + full-width Response · **AE2 ✅
  (#61)** — Reasoning identity (option-2) + per-message Actions (Copy/Retry/Copy-sources). Next AE3.

## Carry-overs / review deferrals

- **AE2 — ChatPanel dark-mode shell gap (deferred to AE5 ≡ old R9):** in the wide layout the central
  chat *column* renders LIGHT in dark mode while the chrome (header/sidebar/footer) is dark — the
  ChatPanel shell still uses legacy `--lq-*` tokens (the dark-mode bridge doesn't fully cover it). This
  is **pre-existing** (identical in the AE1 dark capture) and NOT an AE2 regression; AE2 only touched the
  bubble internals (ribbon + actions, both semantic-token). **AE5 migrates ChatPanel's `--lq-*` block.**
- **AE2 nits (accepted on record, from the fresh-context review):** (a) `handleAssistantRetry` is a
  one-line passthrough to `rerunPrecedingPrompt` — kept for symmetry with `handleRefusalRerun` + a
  documented future divergence. (b) `MessageActionsBar.copyTimer` has no `onDestroy` clear — a pending
  1.5s timeout could set `copied=false` after unmount; Svelte 5 tolerates it (cosmetic). (c) `untrack()`
  in the `ReasoningRibbon` `$state` initializer — KEPT (it silences the `state_referenced_locally`
  svelte-check warning; the reviewer's "no-op" call was on the runtime, not the linter).
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

- **NEW (AE2): some AE registry blocks aren't cleanly vendorable — use option-2.** The `reasoning`
  block's registry JSON pulls `streamdown-svelte` + `@shikijs/themes` + `mode-watcher` + a `collapsible`
  we don't ship + a Streamdown `Response` sink. When an item drags in the avoided deps, **hand-build the
  AE *identity* on our existing primitive** (ADR-F011 option-2) instead of vendoring — that's what AE2
  did for `ReasoningRibbon` (kept the accessible `<details>`, added brain/chevron/shimmer/duration). The
  clean `actions/` subtree (only `ui/button`+`ui/tooltip`) WAS vendored normally. Inspect each item's
  `dependencies` BEFORE deciding vendor vs hand-build.
- **NEW (AE2): forward shadcn `Button onclick` through a RUNES wrapper, not the legacy parent.** The
  legacy `MessageBubble` can't reliably forward `onclick` to a runes shadcn `Button`. Fix: a small runes
  component (`MessageActionsBar.svelte`) renders the AE actions; the legacy parent passes plain
  props/callbacks to it (legacy→runes prop passing is fine). Inside the runes wrapper, `onclick` →
  `restProps` → `Button` forwards correctly.
- **NEW (AE2): `npx prettier --write` reformats pre-existing non-conformant files → unrelated churn.**
  Web CI gates only `npm run check` + vitest (NOT prettier/eslint), so committed files aren't all
  prettier-clean. Running prettier on a touched-but-mostly-unchanged file (e.g. ChatPanel) rewrites
  dozens of unrelated lines. **Format only genuinely-new files; for an edited legacy file, match the
  surrounding style by hand and `git checkout main --` it if prettier churned it** (AE2 reverted
  ChatPanel and re-applied just the logical change).
- **NEW (AE2): lab-based functional Cypress dodges the auth-login flakiness.** The `_ae-lab` route is
  auth-gated but makes no API calls, so deterministic interaction tests (reasoning toggle, copy/retry)
  run there without the live chat fixtures. Use the live chat surface only for the integration check +
  before/after capture. Distinguish Copy/Check icons etc. via lucide's `svg.lucide-<name>` class.
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
