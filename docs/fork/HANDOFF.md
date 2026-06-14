# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (AE0 MERGED — next is AE1)

- **AE0 MERGED via PR #59** — AI Elements vendoring foundation (ADR-F011). First slice of the
  **AE-series** (Vercel AI Elements look via the MIT Svelte port `SikandarJODD/ai-elements`,
  vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP gateway/SSE/`guarded_tool_call`/
  audit, KEEP our `marked`+`DOMPurify` sanitizer). Plan: `docs/fork/plans/F1-legacy-design-rollout-decomposition.md`
  §"AI Elements visual adoption". The R-series (legacy `--lq-*` → semantic-token migration of
  non-conversation surfaces) continues independently on the dark-mode bridge.
- **RE-PLAN CHECKPOINT PASSED (AE0 close):** the Svelte port is **high quality** — registry items
  are clean, inspectable JSON (`https://svelte-ai-elements.vercel.app/r/<c>.json`); the token system
  is **identical** to ours (shadcn-svelte + Tailwind v4) so the token-remap is ≈ identity; **zero new
  npm deps**; components compile + render + behave in the real prod bundle. **Decision: proceed
  AE1→AE7 with the VENDOR approach.** The ADR-F011 option-2 hand-build fallback is NOT needed (still
  available per-component if a heavier one disappoints). Heavier components (Response/Reasoning/Tool)
  still get per-slice scrutiny on their markdown sink + any `{@html}`.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE0** (new route in the bundle).
  Login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 803**; **Cypress `ae0-ae-lab.cy.ts` 3/3** headed/live. Infra slice — **screenshot-exempt**
  (the lab is dev scratch, not a user surface). Adversarial review (fresh-context agent): **CLEAN —
  0 blocker / 0 should-fix / 2 cosmetic nits** (security pass CLEAN — no secrets, no `{@html}`, no
  `@ai-sdk/svelte` coupling, 0 `var(--lq-)`, 0 hardcoded hex, no new dep, no live-surface change).

## Done (AE0, this slice)

- **Vendored 2 trivial AI Elements components** into `web/src/lib/lq-ai/components/ai-elements/`
  (source we own, same model as `ui/*`):
  - `loader/` — pure inline-SVG spinner (`currentColor` + `animate-spin`); **zero deps**.
  - `suggestion/` — `Suggestion` chip + `Suggestions` horizontal scroller; reuses the
    already-vendored `ui/button` + `ui/scroll-area` + `cn`; **zero new deps**.
  Each registry-JSON item was **inspected before vendoring** (deps / registryDependencies / source);
  CLI alias placeholders substituted (`$COMPONENTS$`→`$lib/components`, `$UTILS$`→`$lib/utils`);
  house-formatted (prettier). Born **`0 var(--lq-)`** (no R-LAST regression).
- **`ai-elements/README.md`** — provenance + the **token-remap convention** (the AE0 finding: the
  port's tokens are identical to ours → remap ≈ identity; rules: born-0-`--lq-`, no hardcoded hex,
  add-or-map any token the port introduces, keep our hardened markdown sink, any `{@html}` is a
  per-slice security item). The ADR-F011 vendoring seam comment lives in each `index.ts` + this README.
- **Internal lab route** `web/src/routes/lq-ai/_ae-lab/+page.svelte` — renders Loader (3 sizes) +
  Suggestions (chips wired to a pick-counter) + a local non-persisting light/dark toggle. Unadvertised,
  auth-gated, links nowhere → **changes no live surface**. `data-testid`s for the Cypress proof.
- **`NOTICES.md`** — new "Web client provenance" row: MIT `SikandarJODD/ai-elements`, the
  inspect-then-vendor process, "no new runtime dep at AE0", future `shiki` flagged for AE4.
- **`.eslintignore`** — `ai-elements/` exempted from eslint (the shadcn `...rest` + `$props()`
  pattern trips `custom_element_props_identifier`, a false positive for our SPA — same exemption as
  `ui/*`); kept prettier-formatted (owned source). eslint is NOT CI-gated.
- **`cypress/e2e/ae0-ae-lab.cy.ts`** (3 tests, live/headed) — loader renders+animates ×3; suggestion
  `onclick` fires with the correct suggestion text + counter increments; theme flip survives.

## Next slice — pick up exactly here

1. **AE1 — Conversation + Message + Response (full-width)** *(shell; ⚠ touches the LIVE chat surface).*
   Plan §"AI Elements visual adoption" → AE1. `MessageList` → AE **Conversation** (scroll container +
   sticky scroll-to-bottom); `MessageBubble` → AE **Message + Response** (full-width assistant,
   soft right-aligned user bubble — the AI Elements signature; restyles the already-merged R6 bubble
   look). **CRITICAL: the AE "Response" ships its own markdown renderer (Streamdown/marked) — DO NOT
   adopt it. Render OUR sanitized markdown** (`renderModelMarkdown` = `marked`+`DOMPurify` media-forbid).
   Adopt only its *prose styling*. Keep the ProvenancePill / tier / citation row beneath the Response.
   **Vendor pipeline (proven in AE0):** fetch + INSPECT the registry JSON for `conversation`, `message`,
   `response` (`curl https://svelte-ai-elements.vercel.app/r/<c>.json`; parse with python3 — NOT jq,
   not installed; mind `/tmp/types.py` shadowing stdlib — run python from the repo dir), check deps /
   registryDependencies / `{@html}` / tokens BEFORE vendoring; substitute aliases; re-token to identity;
   re-wire to our message store. **Responsive:** narrow = full-bleed. **Adversarial+security:** streaming
   append correctness, citation-decorate action still binds, sanitizer unchanged, dark contrast, ARIA,
   scroll anchoring. Full four-discipline gate + headed before/after screenshots (light+dark, wide+narrow).
   **Backlog (from R6):** converge `ConversationPanel` + `SkillSourceView` onto `renderModelMarkdown`
   (do as part of AE1/AE6).
   Then AE2 Reasoning+Actions → AE3 Sources+InlineCitation → AE4 Code Block (**`shiki` dep**) →
   **AE5 Prompt Input (≡ old R9 slot)** → **AE6 Tool+Task (≡ old R-CONV-2 slot)** → AE7 Suggestions
   (optional — the AE0-vendored `Suggestion`/`Suggestions` are ready; back them with SavedPrompts).
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
- **AE-series (ADR-F011):** plan + ADR accepted ✅ (#58, `c2b505f`) · **AE0 ✅ (#59)** — vendoring
  foundation; re-plan checkpoint passed → vendor approach confirmed for AE1–AE7.

## Carry-overs / review deferrals

- **AE0 nits (accepted on record, no code change — kept byte-faithful to the MIT upstream):**
  (a) `loader-icon.svelte` carries a redundant inline `style="color: currentcolor"` (paths already
  use `stroke="currentColor"`). (b) the upstream clipPath `id="clip0_2393_1490"` is static, so N
  mounted Loaders share the id — invalid HTML in the strict sense, but every instance has identical
  clip geometry so `url(#clip…)` resolves to the first and all render correctly (Cypress 3/3). If a
  future AE component needs per-instance clip geometry, scope the id then (e.g. `$props.id()`).
- **R8 deferred-on-record:** focus-on-open implemented but NOT asserted in Cypress (headed-Electron/
  Xvfb programmatic focus doesn't set `document.activeElement` without OS window focus). Drawers are
  not full focus-traps (cockpit defers this too); ESC + scrim-click + `inert`-on-close cover practice.
- auth/refresh: per-user session cap + web gate timeout SHIPPED (#47). REMAINING: the
  **deterministic-HMAC index** (removes the global bcrypt scan + bad-token-spam DoS; needs a
  migration + security review — Backlog).
- F1-S3 deferrals: subagent-spec skill names bypass registry validation (validate on the activation
  slice); `audit_log.practice_area_id` unindexed; area tier floor operator-set until a model > tier 4.
- ADR-0011 disclosure after F1-S5 attribution. Live SSE token deltas DEAD until a Redis pub/sub
  publisher lands (F1-S4). ADR-0011/F003 conversation memory + compaction → F2.

## Gotchas (carried + new)

- **NEW (AE0): the AE vendor pipeline.** Distribution is **shadcn-svelte registry JSON**, NOT jsrepo
  (the plan said jsrepo; the actual mechanism is `…/r/<component>.json`). INSPECT the JSON before
  vendoring (deps / registryDependencies / `{@html}` / tokens). Items use CLI placeholders
  `$COMPONENTS$`/`$UTILS$` — substitute to `$lib/components`/`$lib/utils`. Watch: `suggestion`'s item
  **under-declares** `scroll-area` as a registry dep (we already had it). The port's "Response" is
  expected to ship an unhardened markdown sink — **replace it with `renderModelMarkdown`**, adopt only
  its prose styling.
- **NEW (AE0): "dev-only route" reality.** The web container ALWAYS serves a prod build (no separate
  dev deploy), so `import.meta.env.DEV` would make a route invisible in our only stack AND untestable
  by Cypress (baseUrl :3000 = the built container). "Dev-only" is realized as an **unadvertised,
  auth-gated, internal** route instead (`_ae-lab`). A **leading-`_` directory DOES route** in this
  SvelteKit version (verified: `/lq-ai/_ae-lab` is a real RouteId via `svelte-kit sync`) — it is NOT
  treated as private. Routes under `/lq-ai/*` are auth-gated by `+layout.svelte` (exempt list is only
  `/login` + `/change-password`).
- **NEW (AE0): vendored AE source is eslint-exempt** (`.eslintignore` `ai-elements/`) for the same
  `custom_element_props_identifier` false positive as `ui/*`; kept prettier-formatted. eslint is NOT
  CI-gated (only `npm run check` + vitest are).
- **R8: chai-jquery subject rebinding** — `.and('have.attr', name[, val])` REBINDS the chained subject
  to the attr value/undefined; put multiple attribute checks in ONE `.should(($el) => {…})` callback.
- **R8: `inert` for off-canvas drawers** — CSS `translate-x-full` only hides visually; descendants stay
  focusable + in the a11y tree. Use `inert={(isNarrow && !open) || undefined}`. A DYNAMIC
  `role={isNarrow ? 'dialog' : undefined}` defeats svelte-check's a11y static analysis → use a static
  `tabindex="-1"` (negative → no `a11y_no_noninteractive_tabindex` warning).
- **R8: active row on a translucent wash needs a backing surface for AA** — bare `text-primary` over
  `bg-muted/40` fails AA in dark (4.12:1). Give active rows `bg-accent text-accent-foreground`
  (9.08:1 dark / 11.32:1 light).
- shadcn `Button onclick` only forwards from a **runes** parent (legacy `on:click` = silent no-op).
  `text-primary` on `bg-accent` fails WCAG AA → use `text-accent-foreground`. `text-destructive` on a
  tinted bg fails AA in dark → add a `dark:` lift (`dark:text-red-300`).
- web CI gates only `npm run check` + vitest (eslint NOT gated). `test:frontend` is vitest WATCH mode —
  run `npx vitest run`. vitest env is `node` (no jsdom) — DOMPurify/sanitisation must be Cypress-tested.
  Long multi-`cy.visit` screenshot loops outlive the token TTL → shoot all frames on ONE page load.
  **headless cypress lies about dark theme — capture headed** (`DISPLAY=:0`), and **rebuild the `web`
  container before screenshotting/Cypress-testing a UI change** (it serves a pre-built bundle).
- `gh pr create` defaults to FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork` AND
  `--head <branch>` (ADR-F001). jq NOT installed — parse `gh --json` with python3 (mind `/tmp/types.py`
  can shadow stdlib `types` — run python from the repo dir, not `/tmp`).
- migrations: NEVER host-side alembic against the live dev DB; api auto-migrates on boot; rebuild
  api+arq-worker+ingest-worker together + web. **NEVER `docker compose down -v`.**
- MiniMax-M3 is tier 4 (weak) — `default_tier_floor` < 4 makes every run 403. Seed areas with NO floor.
  deepagents subagent `model` string = gateway-bypass (ADR-F010 guard at `build_deep_agent`). New API
  endpoints register in tests/test_openapi.py (count assert).
