# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (F2 milestone OPEN — F2-M3 shipped; AE-series CLOSED)

- **NEW MILESTONE — F2 (scira-style minimalist pass), governed by ADR-F012.** The maintainer wants the
  whole interface taken toward the calm, minimal aesthetic of [`scira`](https://github.com/zaidmukaddam/scira)
  (**AGPL → REFERENCE ONLY**: study look/IA, never fetch/copy code), AND a UX redesign (land in the
  cockpit → reach tools from there → deep-agents-per-area as the centre). **ADR-F012 splits the work by
  dependency:** **F2** = the *visual* pass (now, reversible, no irreversible IA move — all 11 tabs stay);
  **UX-A** = navigational convergence (own milestone after F2; cockpit becomes the single shell, legacy
  top-tab IA retired — unblocked frontend IA); **UX-B** = capability convergence ("tools as in-context
  agent capabilities", *rides the pivot track* — hard-blocked by the practice_area/unit_of_work SCHEMA +
  area activation + F1-S4/S5; building it before those = schema debt or a dishonest hollow shell). Plan:
  `docs/fork/plans/F2-minimalist-pass-decomposition.md` (slices **F2-M0…M9**). This extends F006/F011 and
  sequences F002's F3 commitment.
- **F2-M0 (PR #67, main `749a5a1`)** — docs + baseline only (no app code): **ADR-F012** written;
  F2 decomposition doc written; **before** baseline screenshots captured (cockpit landing + a legacy
  `(tools)` chrome surface, light+dark × wide+narrow) in `docs/fork/evidence/f2-m0/` via the reusable
  `cypress/e2e/f2-baseline.cy.ts` (PHASE=before|after). The cockpit already lands on "Your practice"
  (areas + per-area agents + unfiled matters) — the architecture already leans toward the destination;
  F2-M4 adds a calm centered intent entry above it.
- **F2-M3 (this slice)** — tab-bar visual condense (restyle/group ONLY — **no tab retired/hidden/
  reordered**). Added a **presentational** `group?: 'core'|'legacy'|'gated'` field + `tabGroupOf()` to
  `lib/lq-ai/tabs.ts` (playbooks/tabular → `legacy`; autonomous/admin → `gated`; absent ⇒ `core`) — purely
  visual, does NOT touch `isTabVisible`/`isTabAvailable`/`activeTabFor`/`visibleTabsFor`. **`TopTabBar`**
  condensed (`gap-4`→`gap-0.5`, `px-1`→`px-2.5`) with **in-place section separators** (inert
  `role="presentation" aria-hidden` `<li>` rules at each group boundary) + the **legacy group rests one
  step quieter** (`text-muted-foreground/70`), all via a new exported pure **`tabStateClass()`** (unit-
  tested). One `<ul role="tablist">` preserved → arrow-key nav intact (separators carry no button, so the
  `button[role="tab"]` nodelist still maps to `tabIndex`). **`CockpitHeader`** Tools dropdown mirrors the
  muted-legacy treatment. **Resolves the M2 active-tab nit** (active wins in `tabStateClass`). Also
  strengthened the reusable `f2-baseline.cy.ts` tools-skills wait (on `nav[aria-label="Primary"]`, not
  `body`) after a blank light-wide capture. Suites: web check **0 err**; **vitest 829** (+6: `tabGroupOf`
  + `tabStateClass`); f2-baseline cypress **2/2** (PHASE=after). Evidence: `docs/fork/evidence/f2-m3/`
  (legacy `(tools)` skills surface, light+dark × wide+narrow — grouping + muted legacy visible both
  themes). Fresh-context review: **SHIP**, no blockers/should-fixes/nits. web-only.
- **F2-M2 (PR #69, main `feacb02`)** — chrome calm + `--lq-*` → semantic token unification (the dark-mode fix).
  Migrated four chrome files off the legacy `--lq-*` system to semantic Tailwind utilities + applied scira
  calm: **`TopTabBar.svelte`** (scoped `<style>` dropped; muted resting tabs, **single primary accent** on
  the active tab + lighter underline, `text-muted-foreground/60` for unavailable), **`AmbientTrustChrome`**
  (wrapper + ⌘K hint), **`DualBrandingFooter`** (raw `gray-*` → `text-muted-foreground`/`border-border`),
  **`(tools)/+layout.svelte`** shell (`.lq-shell`/`.lq-topbar`/`.lq-brand` + inline `var(--lq-*)` styles →
  `bg-background`/`text-foreground`/`text-primary` — the **robust fix** for the AE5 `--lq-canvas`
  light-in-dark cascade quirk). The legacy chrome accent now **unifies to the cockpit's blue `--primary`**
  (was teal/sage). Zero live `var(--lq-*)` refs remain in the four files (only `data-testid`/`id="lq-main"`/
  import paths/comments). **`TrustPill.svelte` NOT touched — deferred on record** (see carry-overs).
  Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 823** (unchanged —
  TopTabBar's pure `visibleTabsFor` test still green; styling is screenshot-verified); f2-baseline cypress
  **2/2** (PHASE=after). Evidence: `docs/fork/evidence/f2-m2/` (cockpit + legacy `(tools)` skills, light+
  dark × wide+narrow); dark mode renders correctly (no light-in-dark). Fresh-context review: **SHIP**, no
  blockers (1 unreachable-state nit on record). web-only — no api/gateway change.
- **F2-M1 (PR #68, main `a8db5c7`)** — calm layout primitives. New `components/primitives/PageShell.svelte`
  (centered `mx-auto w-full max-w-* px-* py-*` container) + `SectionHeader.svelte` (title + optional
  subtitle, `page`=h1 / `section`=h2 type scale), each with an exported pure helper (`pageShellClass`,
  `sectionHeaderScale`) **unit-tested** (vitest +7 → 823). Adopted in **one** real consumer,
  `cockpit/AreaGrid.svelte` (the "Your practice" page title + the "Unfiled matters" section header +
  the page container). Faithful extraction: after-shots **pixel-identical** to the M0 before-baselines
  (`docs/fork/evidence/f2-m1/`). No new token scale; semantic tokens only; no `{@html}`; no IA change.
  Fresh-context review: **SHIP**, no blockers (2 nits on record — see carry-overs). Suites: web check
  **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 823**; f2-baseline cypress **2/2**
  (PHASE=after). web-only — no api/gateway change.

- **AE-series (ADR-F011) — CLOSED. AE0 (#59) + AE1 (#60) + AE2 (#61) + AE3 (#62) + AE4 (#63) + AE5 (#64) +
  AE6 (#65) + AE7 (#66) ALL MERGED.** The series brought the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **AE7 = honest Suggestions, NO new dep:** reused the AE0-vendored `suggestion/` as-is. The chips are
  empty-conversation **starters** backed by the user's own **SavedPrompts** (an honest, user-owned source)
  — NOT model-invented follow-ups (no honest source for those exists, so none are shown). **`shiki` (AE4)
  remains the ONLY new runtime dep across the whole AE series**; AE5/AE6/AE7 added none.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE7** (the bundle carries the ChatPanel
  chips + the SavedPromptsPanel `onPromptsLoaded` hook). Login: http://localhost:3000/lq-ai/login ·
  admin@lq.ai / LQ-AI-local-Pw1!  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only
  S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 816** (unchanged — AE7 behavior is covered by Cypress, no unit-level pure helper added);
  **Cypress `ae7-suggestions.cy.ts` 5/5** headed/live-stubbed (4 functional + 1 capture; the first test
  eats the documented first-`cy.visit` session-establishment latency → it ran ~30s and passed; the rest
  are fast). **api/gateway UNAFFECTED — AE7 touches only `web`** (no backend change). AE7 **after**
  screenshots (empty-chat starter chips, light+dark, wide+narrow) in `docs/fork/evidence/ae7/`.
  Adversarial review (fresh-context agent): **SHIP**, no blockers/should-fixes; nit #1 (a benign chip
  flash while a populated chat's messages load) was FIXED in-slice by adding the `message_count` gate.
  Security pass: NO `{@html}` introduced — the chip label (`prompt.name`) + inserted body
  (`prompt.prompt_text`) are escaped text/attribute bindings via the vendored `Suggestion`→`Button`;
  SavedPrompts are user-owned + server-scoped (404-not-403); no secrets/stray files; web-only.

## Done (AE7, this slice)

- **`ChatPanel.svelte`** — AE **Suggestion** starter chips above the composer. A row of
  `Suggestions`/`Suggestion` (the AE0-vendored chips, reused as-is) renders the user's saved prompts as
  one-click starters, gated `{#if messages.length === 0 && (activeChat?.message_count ?? 0) === 0 &&
  savedPromptChips.length > 0}` — i.e. only on an EMPTY conversation that genuinely has no messages, and
  only when the user actually has saved prompts. Chip label = `prompt.name`; `onclick` fills the composer
  with `prompt.prompt_text` via the new shared **`insertIntoComposer`** helper (which also replaced the
  inline arrow the SavedPromptsPanel quick-insert used — same append-if-nonempty-else-set behavior, now
  deduped). The chips are **NOT** model-invented follow-ups — there is no honest source for those, so none
  are shown.
- **`SavedPromptsPanel.svelte`** — new optional **`onPromptsLoaded(prompts)`** callback, fired at the end
  of its existing `refresh()`. This lets ChatPanel render the same honest, user-owned list as chips WITHOUT
  a second `GET /saved-prompts` — the panel stays the single fetch site. (The panel only mounts inside
  `{#if activeChat}`, which persists across chat switches, so no re-fetch / no race; `message_count`
  gates the empty-state flash during a populated chat's message load.)
- **`cypress/e2e/ae7-suggestions.cy.ts`** (5) — live-stubbed chat surface on `/lq-ai/chats` (SHORT
  fixtures): chips count == saved-prompt count + label is the prompt name; click inserts the prompt BODY
  (exact-value assert, proving label≠inserted); chips hidden once the conversation has messages (composer
  still present → proves it's an empty-state-only affordance, not a load failure); **NO chips when the
  saved-prompts list is empty (the anti-invention guarantee)**; + 1 before/after capture (light+dark,
  wide+narrow). **NOTICES** (AE row bumped AE0–AE7 + AE7 sentence) + `ai-elements/README.md` (AE7
  honest-source paragraph) + plan (AE7 DONE) updated. **No new ADR** — F011 already sanctions reusing a
  vendored component; the honest-source/no-invention call is recorded here + in NOTICES/README/memory.

## Next slice — pick up exactly here

**Active milestone: F2 (minimalist pass).** F2-M0…M3 shipped. The legacy `(tools)` shell + tab bar +
footer + AmbientTrustChrome are on semantic tokens with the cockpit's blue accent; the tab bar is now
condensed + grouped (core / muted-legacy / gated) with all 11 tabs intact.

1. **F2-M4 — Cockpit centered intent entry** (`docs/fork/plans/F2-minimalist-pass-decomposition.md`).
   New `cockpit/CenteredEntry.svelte` rendered in the `view==='areas'` branch of `cockpit/Cockpit.svelte`,
   ABOVE a de-emphasised `AreaGrid`. A calm centered **launcher — NOT a composer (ADR-F002 forbids an
   unbound free-floating chat)**: greeting + a single prompt-styled field that routes via
   `cockpit/helpers.ts` `cockpitUrl(...)` into the area→matter binding flow (carry the typed text forward
   as the `ConversationHost` draft); exactly-one-configured-area → enter it, multiple → anchor/filter the
   grid. Optional honest starter chips (AE `suggestion/` backed by the user's SavedPrompts — the AE7
   precedent; empty ⇒ none). Optional pure `launchIntent(areas, text) → {url, draft}` helper in
   `helpers.ts` (unit-testable). Reuse `AreaGrid`/`helpers.ts`/`components/ai-elements/suggestion/`/shadcn
   `ui/{input,button}`. **Do NOT** reuse the AE5 `ChatPanel` composer or `ConversationPanel` (they
   manufacture an unbound thread → F002). Reversible (delete the component + one render line). Then M5
   (CockpitHeader restyle) → M6/M7/M8 (per-surface calm) → M9 (sweep). Use `cypress/e2e/f2-baseline.cy.ts`
   (PHASE=after) for the cockpit after-shots. **Hard rule (ADR-F012): no tab/route/surface retired or
   hidden in F2; never re-introduce `--lq-*`; the cockpit entry is a launcher, not an unbound composer.**
2. **UX-A (navigational convergence)** — own milestone after F2 (cockpit = single shell, legacy top-tab IA
   retired). **UX-B (capability convergence)** — folds into the pivot track (F1-S4/S5 + area activation +
   schema). Both per ADR-F012.
3. R-series rollout slices (any order — the dark-mode bridge holds un-migrated surfaces; **coordinate with
   F2 — don't double-touch chrome, never re-introduce `--lq-*`**): Foundation/rail R2–R5, Wave 1 R-CONV-1
   (logic; R-CONV-2 → AE6), Wave 2 R12/R13/R14a-b/R15/R15b-tab-pb/R16, Wave 3
   R17a-b/R18/R19a-b/R20/R-CHROME, cleanup R-TYPO → R-BRIDGE → R-LAST. autonomous R21 = SKIP.
4. **F1-S4** (subagent tree + SSE v3-projection adapter) / **F1-S5** (idempotency ledger +
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
  `shiki`) · **AE5 ✅ (#64)** Prompt Input (≡ R9 — option-2; dark-mode column gap FIXED) · **AE6 ✅ (#65)**
  Tool+Task (≡ R-CONV-2 — option-2 hand-build, no new dep; `groupTurnSteps`; renderModelMarkdown
  convergence) · **AE7 ✅ (PR #66)** Suggestions (honest starter chips backed by SavedPrompts; AE0
  `suggestion/` reused, no new dep). **AE-series CLOSED (AE0–AE7 done) — no AE8.**

## Carry-overs / review deferrals

- **F2-M2 — `TrustPill.svelte` migration DEFERRED (own slice).** Its sage/slate/amber/red tone palette
  (`--lq-accent/tier/warn/error` + `-soft`/`-border`) has **no equivalent in the base semantic palette**
  (which only carries primary/destructive/muted/accent) — migrating it would mean **adding a tone-color
  scale to `app.css`, which F2 forbids ("no new token scale")**. It is dark-bridged in `practice.css`
  (`:root.dark`, renders acceptably) and feeds **~15 consumers** (MatterCard, MatterRail*, EnhancePrompt
  Expansion, Trust*Card, skills page, TierBadge, AmbientFooter…). Treat as its own future slice — likely
  alongside R-series tone work or when M7/M8 calm those surfaces; it needs the tone scale defined first.
  **Transitional state after M2:** the legacy chrome accent is blue (`--primary`) while un-migrated page
  content (skills "+ New skill" button, all TrustPills) stays teal/sage — expected during staged rollout.
- **F2-M2 — active-tab nit RESOLVED in M3.** The active-AND-unavailable/legacy precedence is now explicit
  in the pure `tabStateClass()` (active branch first), unit-tested.
- **F2-M1 — 2 nits on record (non-blocking).** (1) `PageShell` hardcodes the calm padding default
  `px-6 py-10 sm:px-8` (AreaGrid's rhythm). The sibling surfaces it will eventually serve differ —
  `MattersPanel` uses `py-8`, `ConversationHost` uses `px-4 py-4 sm:px-6` — so **F2-M6 must add a `pad`
  variant before those adopt PageShell** (don't force AreaGrid's rhythm onto them; don't try to override
  via the `class` passthrough — Tailwind utility order makes a px/py override unreliable). (2) The refactor
  adds two structurally-empty wrapper `<div>`s (the `in:fade` div + SectionHeader's root, which renders
  `class=""` when no class is passed) — no box-model effect, render is pixel-equal (screenshots confirm),
  fully reversible. Visually identical, not literally byte-identical DOM — acceptable under the pixel-equal
  contract.
- **AE7 — no new carry-overs.** Review SHIP, no blockers/should-fixes; nit #1 (chip flash while a
  populated chat's messages load) FIXED in-slice via the `message_count` gate. Honest-source design is
  load-bearing: chips are the user's own SavedPrompts shown as empty-state starters, never model-invented
  follow-ups — if a future slice wants contextual follow-ups, it needs a real backend source first (don't
  fabricate). The remaining composer-adjacent panels (ModelPicker/SkillPicker/SavedPromptsPanel internals)
  stay on the `--lq-*` dark stopgap (their own future R slices).
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
