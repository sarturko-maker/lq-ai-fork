# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (F2 milestone OPEN — F2-VL0 shipped, F013 token layer live; AE-series CLOSED)

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
- **F2-VL0 (this slice, PR #76)** — the **F013 design-language token layer** lands (ADR-F013; milestone
  **F2-VL**, sequenced between M7a and M7b). **`app.css` recoloured to the Vercel palette** (spec §1): the two
  structural remaps that define the look — **`--primary` is now INK** (`#111` light / `#ededed` dark, inverts)
  not the old indigo, and a **new `--brand`** holds the one scarce Vercel blue (`#0070f3` / `#47a3ff`), used
  only for focus / links / running. Everything else monochrome; **charcoal `#111` dark floor** (never black),
  white canvas, hairline borders. Hex values match the approved `direction-vercel` mockup. Also: **type scale**
  `--text-display`…`--text-label` registered in `@theme` (consumed later as `text-*` utility classes — JIT, so
  the vars are pruned until VL1/R-TYPO use them; not a defect); **motion** tokens `--motion-fast/base/slow` +
  2 eases; `--radius` → **10px** base, `--radius-lg` pinned **12px** (cards); elevation **de-tinted** (neutral,
  was indigo); status `running` = `--brand`. `motionMs()` callers (5 files) wired onto a new **`MOTION` JS
  mirror** in `cockpit/helpers.ts` of the CSS `--motion-*` tokens — a **unit test parses `app.css` and locks
  the two in sync** (durations normalised 120→base 150, 160→base, 100→fast). Theme-color meta → `#111`/`#fff`.
  **Tokens only — no new layout** (VL1 builds the AppShell/primitives; VL2 the cockpit proof). The one app-wide
  visible shift: indigo-blue → ink primaries + scarce blue, on charcoal dark. Suites: web check **0 err** (5
  pre-existing a11y warnings, untouched files); **vitest 837** (+1: the MOTION↔CSS sync lock); f2-baseline
  cypress **4/4** (PHASE=after — reused as-is). Built bundle verified to carry `--brand`/`--primary:#111`/
  `--motion-*`/`--background:#111`. Evidence: `docs/fork/evidence/f2-vl0/` (cockpit, matters, conversation,
  playbooks, tabular, skills — light+dark × wide+narrow; ink inverting primaries, charcoal dark with no
  light-in-dark, green dot-status, blue scarce). web-only — no api/gateway change.
- **F2-M7a (PR #74)** — calm **table-list surfaces**: `playbooks`, `tabular`, `skills` list pages.
  **Split of F2-M7** by visual family (M7b = `knowledge`/`learn`/`saved-prompts` card/wrapper surfaces, next).
  Each page: (1) **adopt `<PageShell size="wide" pad="compact">`** for the centered container (the three
  list pages used `max-width: 64rem`/`max-w-5xl` = PageShell `wide` exactly; bespoke header kept — the
  header row carries an h1 + a trailing CTA + subtitle, which `SectionHeader` doesn't model, the same call
  M6 made for MattersPanel); (2) **migrate the COLOR `--lq-*` tokens → semantic** (`--lq-border`→`--border`,
  `--lq-surface`→`--card`, `--lq-inset`→`--muted`, `--lq-canvas`→`--background`, `--lq-accent`→`--primary`
  (teal→**blue** — unifies the page accent with the chrome, the M2 precedent), `--lq-on-accent`→
  `--primary-foreground`, `--lq-text`→`--foreground`, `--lq-text-secondary`/`-tertiary`→`--muted-foreground`,
  `--lq-error`→`--destructive`, `--lq-error-soft`→`--status-failed-wash`); (3) **tabular status pills → the
  existing `--status-*` tone family** (running/completed/failed/cancelled + `-wash`, defined for BOTH themes
  in `app.css` — an existing scale, NOT a new token scale → sidesteps the TrustPill problem). **Left for
  R-TYPO (documented, not a defect):** `--lq-radius*`/`--lq-space-*`/`lq-text-*` (no semantic equivalent, no
  light/dark variance, R-TYPO's domain — never re-introduced, just not double-touched). **`TrustPill`
  badges on skills stay teal/sage** (M2 deferral — needs the tone scale defined first). Suites: web check
  **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 836** (unchanged — presentation-only,
  no new pure helper, like M2/M5); f2-baseline cypress **4/4** (PHASE=after — added a playbooks + tabular
  capture test; skills captured by the existing `(tools)`-chrome test). Evidence:
  `docs/fork/evidence/f2-m7a/` (playbooks + tabular + skills, light+dark × wide+narrow — dark renders
  honest, no light-in-dark; CTAs blue). Fresh-context review: **SHIP**, no blockers/should-fixes/nits
  (every target token verified to exist in both themes; markup balanced; `lq-ai-user-skills` testid
  forwarded via PageShell `{...rest}`). web-only — no api/gateway change.
- **F2-M6 (PR #73, main `bf3f034`)** — matters + conversation surfaces **consolidated onto `PageShell`** (the M1
  carry-over). Added a **`pad` variant** to `components/primitives/PageShell.svelte`
  (`PageShellPad = 'default'|'compact'|'tight'`; `default`=`px-6 py-10 sm:px-8`, `compact`=`px-6 py-8
  sm:px-8`, `tight`=`px-4 py-4 sm:px-6`); `pageShellClass(size, pad='default', extra='')` (signature
  changed — only callers are PageShell itself + its test). **`MattersPanel`** container →
  `<PageShell pad="compact" data-testid="lq-cockpit-matters">` (bespoke header kept — SectionHeader models
  no back link / trailing action / truncating title); **`ConversationHost`** keyed conversation column →
  `<PageShell size="narrow" pad="tight">`. Both keep the `in:fade` on an inner div (the AreaGrid M1 idiom —
  PageShell is a component; transitions need an element). **Visually equivalent** — the pads were copied
  verbatim (the win is consolidation/consistency, not a visible redesign). **`AreaRail` intentionally
  untouched** (sidebar — already minimal, doesn't fit PageShell/SectionHeader). Suites: web check **0 err**;
  **vitest 836** (+1 pad-variant assertion); f2-baseline cypress **3/3** (PHASE=after — added a matters +
  conversation capture test). Evidence: `docs/fork/evidence/f2-m6/` (matters + conversation, light+dark ×
  wide+narrow). Fresh-context review: **SHIP**, no blockers/should-fixes/nits (visual equivalence verified
  exactly; the responsive geometry test still matches the testid). web-only.
- **F2-M5 (PR #72, main `2f363e4`)** — CockpitHeader **minimal-chrome restyle** (already semantic → **restyle-only,
  reversible**; one file, no logic/props/routes changed). `cockpit/CockpitHeader.svelte`: muted icon
  buttons now also **`hover:text-foreground`** (one calm resting state → brighten on hover, matching the
  M2/M3 tab-bar idiom; applied to the rail toggle, Tools trigger, theme, settings, sign-out); the right
  cluster gap tightened `gap-1.5`→`gap-1`; the **three trailing utility icons (theme/settings/sign-out)
  grouped into one tight `gap-0.5` cluster behind a hairline `bg-border` separator** so account/prefs read
  apart from tools/trust; single primary accent stays on the brand. **No AI furniture (ADR-F002)** — the
  header still picks no models/skills/context; `AmbientTrustChrome` (ADR-0011 disclosure) + the Tools menu
  (with the M3 muted-legacy treatment) + the trust link all intact. No new token scale, no `--lq-*`, no
  `{@html}`, nothing retired. Suites: web check **0 err**; **vitest 835** (unchanged — presentation-only,
  no pure helper, like M2); f2-baseline cypress **2/2** (PHASE=after). Evidence:
  `docs/fork/evidence/f2-m5/` (cockpit, light+dark × wide+narrow — separator + tight cluster visible both
  themes; the legacy `(tools)` surface uses `TopTabBar`/`(tools)` chrome, NOT this header, so its shots are
  unchanged). Fresh-context review: **SHIP**, no blockers/should-fixes (1 benign cosmetic nit). web-only.
- **F2-M4 (PR #71, main `df65826`)** — cockpit centered intent **launcher** (ADR-F002: a launcher, **NOT a
  composer** — it never starts an unbound thread). New **`cockpit/CenteredEntry.svelte`** rendered ABOVE
  a **de-emphasised** `AreaGrid` (its "Your practice" header dropped from `page`→`section`, so the page
  keeps a **single h1** — the launcher's "What are you working on?"), wired through a new
  **`landingView`** snippet in `cockpit/Cockpit.svelte` (replaces the two duplicated `AreaGrid` render
  blocks — areas-view + fallback — a real simplification). On submit a new **pure `launchIntent(areas,
  text) → {url, draft}`** helper (`cockpit/helpers.ts`, unit-tested) decides: **exactly one CONFIGURED
  area → enter it** (`cockpitUrl({area})`) carrying the text; **0 or several → no nav**, draft held +
  hint points the user at the grid below. The text carries via a parent-held **`pendingDraft`** in
  `Cockpit.svelte` → passed to `ConversationHost` as **`initialDraft`**, which seeds the composer
  `prompt` **once on mount** (`!prompt` guard) and clears it via **`onDraftConsumed`** — so only the
  FIRST matter after a launch is seeded, never a second, never overwriting in-progress text; unfiled
  (resume-only) gets no draft. Optional starter chips = the user's own **SavedPrompts** (AE7 precedent,
  fetched fail-soft → none). Suites: web check **0 err**; **vitest 835** (+6 `launchIntent`); f2-baseline
  cypress **2/2** (PHASE=after) + a throwaway interaction spec confirmed end-to-end carry-forward
  (submit → `area=commercial` → open matter → composer pre-seeded), then removed. Evidence:
  `docs/fork/evidence/f2-m4/` (cockpit, light+dark × wide+narrow — launcher hero + chip + de-emphasised
  grid). Fresh-context review: **SHIP**, no blockers; 1 should-fix (stale-draft carry window) documented
  in-code as accepted intended behavior; hint-after-typing nit FIXED in-slice (`oninput` clears it).
  web-only — no api/gateway change.
- **F2-M3 (PR #70, main `7c03cef`)** — tab-bar visual condense (restyle/group ONLY — **no tab retired/hidden/
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

## Done (F2-VL0, this slice)

- **`web/src/app.css`** — recoloured both `:root` (light) and `.dark` to the Vercel palette (hex, matching
  `direction-vercel`): ink `--primary` `#111`/`#ededed` (was indigo), new `--brand` `#0070f3`/`#47a3ff`,
  neutral gray ramp, charcoal `#111` dark floor, white canvas/cards, `#fafafa`/`#0c0c0c` sidebar. `--ring` =
  brand. Status `running` = brand blue (the rest green/red/neutral); washes re-derived per theme. Elevation
  de-tinted to neutral oklch (was hue-262 indigo). In `@theme`: added `--color-brand`/`--color-brand-foreground`
  mappings, the `--text-display`…`--text-label` scale (size + line-height + weight + tracking companions),
  `--radius-lg` pinned `0.75rem`; `--radius` `0.5rem`→`0.625rem`. In `:root`: `--motion-fast/base/slow` +
  `--motion-ease-standard/-emphasized`.
- **`cockpit/helpers.ts`** — new exported `MOTION = { fast:100, base:150, slow:240 }` (the JS mirror of the CSS
  `--motion-*` tokens; Svelte JS transitions take a number, not a CSS var). `motionMs()` unchanged (still the
  reduced-motion gate). Theme-color meta literals → `#111111`/`#ffffff`.
- **5 motion consumers** (`MattersPanel`, `ConversationHost` ×2, `Cockpit` ×2, `AreaGrid`, `ChatPanel`) — import
  `MOTION` and pass `motionMs(MOTION.base|fast)` instead of magic 120/160/100 (normalised; ≤30ms shift).
- **`cockpit/__tests__/helpers.test.ts`** — new `MOTION scale (F013 VL0)` suite: reads `app.css`, regex-parses
  `--motion-fast/base/slow`, asserts `MOTION` matches (the anti-drift sync lock). vitest 836→837.
- **No new ADR** (ADR-F013 already accepted in PR #75; this is its first code slice). **No new `--lq-*`, no
  `{@html}`, no token scale removed, no surface retired.** Evidence: `docs/fork/evidence/f2-vl0/`.

## Done (F2-M7a, PR #74)

- **`(tools)/playbooks/+page.svelte`** — `<section class="lq-playbooks-page">` → `<PageShell size="wide"
  pad="compact">` + inner `.lq-playbooks-page` (now flex/gap only; width/margin/padding from PageShell).
  CTA + apply button → `--primary`/`--primary-foreground`; subtitle/states → `--muted-foreground`/`--muted`;
  error block → `--destructive`/`--status-failed-wash`; table → `--card`/`--border`.
- **`(tools)/tabular/+page.svelte`** — same PageShell adoption + token migration; **status pills** (`completed`/
  `failed`/`cancelled`/`running`+`pending`) remapped from `--lq-success`/`--lq-error`/`--lq-warning`/`--lq-inset`
  onto `--status-completed`/`--status-failed`/`--status-cancelled`/`--status-running` + their `-wash` bgs.
- **`(tools)/skills/+page.svelte`** — outer `<div class="p-4 max-w-5xl mx-auto" data-testid="lq-ai-user-skills">`
  → `<PageShell size="wide" pad="compact" data-testid="lq-ai-user-skills">` (testid forwarded via `{...rest}`).
  Inline `style="color: var(--lq-text*)"` + `<style>` `.lq-btn-*`/`.lq-link`/`.lq-table-skill-card`/`.lq-thead`/
  `.lq-tbody`/`.lq-scope-personal`/`.lq-empty-state` color tokens migrated; `--lq-radius*`/`--lq-space-6` left
  (R-TYPO); `TrustPill` "Table"/scope badges untouched (deferred). Partial-semantic markup (rose error blocks,
  Tailwind utilities) left as-is.
- **`cypress/e2e/f2-baseline.cy.ts`** — new capture test deep-links `/lq-ai/playbooks` (waits
  `lq-playbooks-generate-cta`) + `/lq-ai/tabular` (waits `lq-tabular-new-cta`), captures both light+dark ×
  wide+narrow. Skills captured by the existing `(tools)`-chrome test. **No new ADR** (visual consolidation
  within ADR-F012). Evidence: `docs/fork/evidence/f2-m7a/`.

## Done (F2-M6, PR #73)

- **`components/primitives/PageShell.svelte`** — new `pad` variant (the M1 carry-over). `PageShellPad =
  'default'|'compact'|'tight'` + a `PAD` map; `pageShellClass(size, pad='default', extra='')` (signature
  changed — grep-confirmed the only callers are PageShell's own template + the test). New `pad` prop
  (default `'default'`, so AreaGrid is unaffected). The `default`/`compact`/`tight` pads ARE the matters/
  conversation rhythms verbatim — do NOT override pad via `class` (Tailwind utility order is unreliable).
- **`cockpit/MattersPanel.svelte`** — container div → `<PageShell pad="compact" data-testid=
  "lq-cockpit-matters">` with the `in:fade|global` on an inner div (the AreaGrid M1 idiom). Bespoke header
  kept (back link + truncating `<h1>` + trailing "New {noun}" button — SectionHeader models none of these).
  Body reindented +1 level (large but purely mechanical; prettier-clean).
- **`cockpit/ConversationHost.svelte`** — the `{#key panelKey}` conversation column div →
  `<PageShell size="narrow" pad="tight">` with `in:fade` on an inner div; added the PageShell import. The
  key remount + `bind:prompt`/`bind:selectedMatterId` on ConversationPanel are unchanged (PageShell just
  renders children).
- **`cockpit/AreaRail.svelte`** — intentionally NOT touched (sidebar nav on `sidebar-*` tokens, already
  minimal; PageShell/SectionHeader don't fit a rail). Recorded so M9's sweep doesn't expect a change.
- **`__tests__/PageShell.test.ts`** — calls updated to the 3-arg signature + a `pad`-variant `.toBe()`
  assertion locking the exact compact/tight strings (vitest 836). **`cypress/e2e/f2-baseline.cy.ts`** — new
  capture test deep-links `?area=commercial`, captures the matters list, opens a matter, captures the
  conversation view (light+dark × wide+narrow). **No new ADR** — consolidation within ADR-F012; recorded
  here + in-file F2-M6 comments + memory. Evidence: `docs/fork/evidence/f2-m6/`.

## Next slice — pick up exactly here

**Active milestone: F2 (minimalist pass), now with the F013 token layer (F2-VL) sequenced in.** F2-M0…M7a +
**F2-VL0** shipped. The semantic tokens now carry the **Vercel design language** — ink primaries, scarce
`--brand` blue, charcoal `#111` dark, the `--text-*`/`--motion-*` families, 10/12px radius. The cockpit lands
on the centered launcher above a de-emphasised grid; chrome/tab-bar/matters/conversation are calm + on
semantic tokens (which now render the new palette automatically).

1. **F2-VL1 — primitives + AppShell** (next; spec §7/§8). Build `AppShell` (the 264px sidebar — brand · *New
   matter* ink button · Recent matters · account footer — beside the centred cockpit column), `Hero` (display
   type), `Card`/hairline `CardGrid`, `Stack`/`Inline`, `StatusDot`, and button variants — **all consuming the
   VL0 tokens** (`text-display`, `--brand`, the radius/motion scale). Prove them in a **dev-only `_vl-lab`**
   route (the AE `_ae-lab` precedent — unadvertised, auth-gated, leading-`_`). Presentation-only, token-driven,
   unit-test the pure class helpers (`pageShellClass` precedent). NO real surface re-skinned yet (that's VL2).
2. **F2-VL2 — cockpit landing proof (flagship, maintainer design-review gate).** Re-skin `cockpit/` to
   `direction-vercel`: `AreaRail` → the Vercel sidebar, `CenteredEntry` → `Hero`, `AreaGrid` → hairline
   `CardGrid`, matters → dot-status list. **Iterate values here under the maintainer's eye** until it reads
   right.
3. **then resume F2-M7b — Library card/wrapper surfaces** (task #118): the remaining three `(tools)` list
   pages — **`knowledge`** (card grid + inline create form, max-1100px; KB status pills `indexed`/`indexing`/
   `failed`/`empty` → `--status-completed`/`--status-running`/`--status-failed`/`--muted` like tabular),
   **`learn`** (card grid, max-960px), **`saved-prompts`** (thin `SavedPromptsPanel` wrapper, max-920px). Same
   M7a recipe — adopt `<PageShell>`, migrate **color** `--lq-*`→semantic, leave `--lq-radius*`/`--lq-space-*`/
   `lq-text-*` to R-TYPO, status pills → `--status-*` — and now **apply the F013 language** (the tokens already
   carry it). Touch only the page wrapper for saved-prompts. Extend `f2-baseline.cy.ts` with a knowledge/learn
   capture. Then M8 (settings/admin/trust) → R-TYPO (`lq-text-*`→§2 type tokens) → TrustPill tones → M9
   (sweep+verify). **Hard rule (ADR-F012): no tab/route/surface retired or hidden in F2; never re-introduce
   `--lq-*`; the cockpit entry stays a launcher. ADR-F013 relaxes "no new token scale" for SYSTEMATIC
   extensions only.**
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

- **F2-VL0 — checkbox + focus-ring hardcoded blues left as-is (own slice).** The `@layer base`
  `input[type=checkbox]` uses literal `#2563eb` (checked fill) / `#3b82f6` (focus outline). They were NOT
  migrated to `--primary`/`--ring` because the checked fill carries a `fill='white'` SVG checkmark — and
  `--primary` inverts to near-white in dark, which would make the checkmark invisible on a white well.
  Resolving it needs a non-inverting "control ink" token (or a theme-aware checkmark color), so it's deferred
  to a control-styling slice (likely VL1's button/control-variant work). They render as a blue close to the
  new `--brand`, so no visible clash today.
- **F2-VL0 — type-scale vars are JIT-pruned until consumed (expected, not a defect).** Tailwind v4 only emits
  a `text-<name>` utility (and its `--text-*` var) when the class is actually used in markup. VL0 registers the
  scale in `@theme` but consumes none of it, so `--text-display` etc. don't appear in the built `:root` yet —
  they materialise the moment VL1 primitives use `class="text-display"`. Don't reference `var(--text-display)`
  raw in CSS expecting it to resolve before a utility consumes it; use the utility class (the spec §2/§7
  contract).
- **F2-VL0 — motion durations normalised (≤30ms).** Wiring the 7 call sites onto the `MOTION` scale shifted
  fades 120→150ms (base) and the area fly 160→150ms; the inner fade stayed 100ms (fast). Imperceptible and
  intended (the point of the scale); static screenshots are unaffected. The reduced-motion gate is unchanged.
- **F2-VL0 — status pills / multi-area hint still not screenshot-able on the dev stack** (carried from M7a/M4):
  tabular has no executions, only Commercial is configured. The new status-`running`=`--brand` tone and the
  dark status washes are verified against `app.css`/the built bundle, not headed. Recapture in VL2/M9 when the
  data exists.
- **F2-M7a — tabular status pills not screenshot-able (dev stack has no executions).** The migrated
  `--status-*` pill tones (`completed`/`failed`/`cancelled`/`running`) render only with tabular execution
  rows; the dev stack shows the empty state. The mapping is verified against `app.css` (both themes) by the
  fresh-context review; recapture once executions exist (or in M9's sweep). The `formatTabularStatus` label
  helper is already unit-tested.
- **F2-M7a — color-only migration is intentional, not partial.** `--lq-radius*`/`--lq-space-*`/`lq-text-*`
  remain on these three pages — they have no semantic-palette equivalent and no light/dark variance, so they
  are R-TYPO's domain (not re-introduced, just not double-touched). Same staged-rollout transitional state
  M2 accepted. `TrustPill` badges (skills) stay teal/sage (M2 deferral — needs a tone scale first).
- **F2-M4 — stale-draft carry window (accepted, documented in-code).** `pendingDraft` clears only on
  consume (`onDraftConsumed`), so if the user launches into the 0/many-area case (draft held, no nav) and
  then opens *some other* existing matter before fulfilling the launch, that matter's composer receives
  the draft. Accepted: it is the user's last typed intent, fully editable, and the multi-area carry is the
  intended feature (a fragile "clear on any nav" would break it). Documented at the `pendingDraft`
  declaration in `Cockpit.svelte`. If a future slice wants tighter scoping, distinguish the
  "fulfilling-the-launch" matter open from an "abandon" open (hard with the shared `openMatter`).
- **F2-M4 — multi-area hint not screenshot-able on the dev stack.** Only Commercial is configured, so the
  `awaitingAreaPick` hint ("Pick a practice area below…" / 0-area "Configure a practice area…") couldn't be
  captured headed — it's covered by the `launchIntent` unit test + the in-code logic. Re-capture when a
  second area is configured (or in M9's sweep).
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
- **F2-M1 — nit (1) RESOLVED in F2-M6.** The `PageShell` `pad` variant (`default`/`compact`/`tight`) landed
  in M6; MattersPanel (`compact`) and ConversationHost (`tight`) now adopt it. (2) The refactor
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
