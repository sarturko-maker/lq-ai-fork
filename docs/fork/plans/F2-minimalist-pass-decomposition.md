# F2 — Minimalist (scira-style) visual pass: decomposition

Governing decision: **ADR-F012** (minimalist visual pass + UX-redesign placement). Reference aesthetic:
[`scira`](https://github.com/zaidmukaddam/scira) — **AGPL-3.0 → REFERENCE ONLY** (study look/IA, never
fetch/copy code). This plan is the **visual** half (F2). The **UX redesign** is split out by dependency
(ADR-F012): **UX-A** navigational convergence (own milestone after F2) and **UX-B** capability convergence
(rides the pivot track — F1-S4/S5 + area activation + the practice_area/unit_of_work schema). F2 makes
**no irreversible IA move**.

## Goal

Take the whole interface toward calm, minimal, scira-style chrome — lots of whitespace, quiet borders,
one accent, clean typographic hierarchy — and make the cockpit a calm **area / deep-agent-first** landing,
while keeping every surface reachable. Unify touched chrome onto semantic tokens (the dark-mode fix).

## Non-goals (F2)

- No surface/tab/route retirement or hiding (all 11 tabs stay visible + clickable) — that is UX-A/F3.
- No unbound composer / no "type → new free-floating chat" (F002): the centered entry is a *launcher*.
- No new token scale; no new runtime dep; no change to gateway/SSE/guarded_tool_call/audit/sanitizer.
- No invented content (recents, suggestions) — honest sources only.

## Slice format

F-series continues as **F2-M0 … F2-M9** (M = minimalist). Each = one PR, ≤2–3 days, independently
shippable + screenshot-able, full four-discipline DoD (build / `npm run check` / vitest **shown** ·
fresh-context adversarial+security+simplification review · **headed** before/after screenshots
light+dark × wide+narrow in `docs/fork/evidence/<slice>/` · HANDOFF updated). Merge per ADR-F005 against
`sarturko-maker/lq-ai-fork`. Order = dependency → risk → visibility; M6/M7/M8 reorder freely behind M2–M5
(the dark-mode bridge keeps everything functional between merges).

## Slices

### Foundation
- **F2-M0 — ADR-F012 + this decomposition + baseline.** Docs + *before* screenshots of the landing, a
  legacy `(tools)` surface, and the tab bar (light+dark × wide+narrow). Docs/baseline only — no code.
  Files: `docs/adr/F012-*.md`, `docs/fork/plans/F2-minimalist-pass-decomposition.md`,
  `docs/fork/evidence/f2-m0/`. *(XS)*
- **F2-M1 — Calm layout primitives, proven on one consumer.** Extract the repeated
  `mx-auto max-w-* px-* py-*` page-shell + heading idiom (see `cockpit/AreaGrid.svelte`) into
  `components/primitives/PageShell.svelte` + `SectionHeader.svelte`; adopt in **one** real surface
  (AreaGrid). No speculative kit; semantic tokens only. *(S)*

### Global chrome (highest visibility, touches every surface)
- **F2-M2 — Chrome calm + token unification.** `components/TopTabBar.svelte`,
  `components/AmbientTrustChrome.svelte`, `components/TrustPill.svelte`,
  `components/DualBrandingFooter.svelte`, `routes/lq-ai/(tools)/+layout.svelte` inline chrome →
  `--lq-*` → semantic (dark-mode fix) + scira calm (lighter borders, tighter type, muted resting state,
  single accent on active). Coordinate with F1 R-CHROME. *(M)*
- **F2-M3 — Tab-bar visual condense (restyle/group only; all 11 stay visible & clickable).** Tighter
  spacing + subtle section separators grouping core / legacy-executor / gated; muted styling on the legacy
  group. Add an optional presentational `group?: 'core'|'legacy'|'gated'` field to `lib/lq-ai/tabs.ts`
  (additive, no behavior change). Mirror calm in `cockpit/CockpitHeader.svelte`'s Tools dropdown.
  Forward-compatible with UX-A (de-emphasised → retired). *(S)*

### Flagship new UI
- **F2-M4 — Cockpit centered intent entry (area / deep-agent-first).** New `cockpit/CenteredEntry.svelte`
  rendered in the `view==='areas'` branch of `cockpit/Cockpit.svelte`, above a de-emphasised `AreaGrid`.
  A calm centered **launcher** (NOT a composer — F002): greeting + a single prompt-styled field that
  routes via `cockpit/helpers.ts` `cockpitUrl(...)` into the area→matter binding flow (carrying the typed
  text forward as the `ConversationHost` draft); exactly-one-area → enter it, multiple → anchor/filter the
  grid. Optional honest starter chips (AE `suggestion/` backed by the user's SavedPrompts — AE7
  precedent). Optional pure `launchIntent(areas, text) → {url, draft}` helper (unit-testable). Reuse
  `AreaGrid`, `helpers.ts`, `components/ai-elements/suggestion/`, shadcn `ui/{input,button}`. Do **not**
  reuse the AE5 `ChatPanel` composer / `ConversationPanel` (they manufacture an unbound thread → F002).
  Reversible: delete the component + one render line. *(M)*
- **F2-M5 — CockpitHeader minimal-chrome pass.** Quieter icon buttons, tighter chrome, single accent on
  brand, calmer Tools menu. Already semantic → restyle-only. File: `cockpit/CockpitHeader.svelte`. *(S)*

### Per-surface visual calm (grouped by visual family)
- **F2-M6 — Matters + conversation surfaces.** `cockpit/MattersPanel.svelte`,
  `cockpit/ConversationHost.svelte`, `cockpit/AreaRail.svelte` — whitespace/type calm + adopt
  `PageShell`/`SectionHeader` where they fit (already semantic; light tightening). *(M)*
- **F2-M7 — Library list surfaces.** `routes/lq-ai/(tools)/{knowledge,skills,playbooks,tabular,
  saved-prompts,learn}/+page.svelte` — calm container + muted-legacy treatment; calm-on-semantic if its
  R-slice merged, else migrate-and-calm. Coordinate F1 R12/R14a/R15/R19a/R20. *(M)*
- **F2-M8 — Settings / admin / trust shells.** `routes/lq-ai/(tools)/settings/+layout.svelte`,
  `routes/lq-ai/(tools)/admin/+layout.svelte`, `routes/lq-ai/(tools)/trust/+page.svelte` — calm nav
  shells + section headers. Coordinate F1 R16/R19. *(S–M)*

### Cleanup / verify
- **F2-M9 — Consistency sweep + verify.** Cross-surface spacing / one-accent / AA-dark check; confirm
  **zero new `--lq-*`** on touched files, **no new `{@html}` sinks**, **all 11 tabs + Tools menu still
  reachable** (the no-retire contract). Full screenshot matrix; final HANDOFF. *(S)*

## Progress

- **F2-M0** — done (PR #67, main `749a5a1`): ADR-F012 + this doc + before-baselines.
- **F2-M1** — done (PR #68, main `a8db5c7`): `PageShell` + `SectionHeader` primitives (with exported
  pure helpers `pageShellClass` / `sectionHeaderScale`, unit-tested), adopted in `cockpit/AreaGrid.svelte`.
  Faithful extraction — after-shots pixel-identical to the M0 before-baselines
  (`docs/fork/evidence/f2-m1/`). PageShell padding default = AreaGrid's rhythm only; a `pad`
  variant is deferred to M6 (MattersPanel `py-8` / ConversationHost `px-4 py-4` differ).
- **F2-M2** — done: structural chrome migrated `--lq-*` → semantic Tailwind (the dark-mode fix) + scira
  calm. `TopTabBar` (muted resting / single primary accent on active / lighter underline),
  `AmbientTrustChrome` wrapper + ⌘K hint, `DualBrandingFooter` (raw `gray-*` → semantic), and the
  `(tools)/+layout.svelte` shell (`bg-background`/`text-foreground` — the robust fix for the AE5
  `--lq-canvas` light-in-dark quirk). Legacy chrome accent now unifies to the cockpit's blue `--primary`.
  Evidence: `docs/fork/evidence/f2-m2/` (cockpit + legacy `(tools)` skills, light+dark × wide+narrow).
  **`TrustPill.svelte` migration DEFERRED on record** — its sage/slate/amber/red soft+border tone
  palette has no semantic-palette equivalent (migrating = a new token scale, forbidden in F2); it is
  dark-bridged (renders fine) and feeds ~15 consumers → its own slice. Transitional: un-migrated page
  content (e.g. the skills "+ New skill" button, TrustPills) stays teal/sage until M7 + the TrustPill
  slice — expected during the staged rollout.
- **F2-M3** — done: tab-bar visual condense (restyle/group ONLY). Added a presentational
  `group?: 'core'|'legacy'|'gated'` field + `tabGroupOf()` to `tabs.ts` (playbooks/tabular = legacy,
  autonomous/admin = gated); `TopTabBar` condensed (`gap-0.5`, `px-2.5`) with in-place section separators
  + a muted legacy group via the new exported pure `tabStateClass()` (unit-tested); CockpitHeader Tools
  dropdown mirrors the muted-legacy treatment. **All 11 tabs stay visible/clickable/in source order**
  (`visibleTabsFor`/`isTabVisible`/`activeTabFor` untouched; one `<ul role="tablist">` keeps arrow-key
  nav). Resolves the M2 active-tab nit (active wins in `tabStateClass`). Strengthened the f2-baseline
  tools-skills wait (nav, not body) after a blank light-wide capture. Evidence: `docs/fork/evidence/f2-m3/`.
- **F2-M4** — done: cockpit centered intent **launcher** (ADR-F002: launcher, NOT a composer — never
  starts an unbound thread). New `cockpit/CenteredEntry.svelte` above a de-emphasised `AreaGrid` ("Your
  practice" → `section` header so the page keeps a single h1), wired via a new `landingView` snippet in
  `Cockpit.svelte` (dedupes the two `AreaGrid` render blocks). New pure `launchIntent(areas, text) →
  {url, draft}` (`helpers.ts`, unit-tested): exactly-one-configured-area → enter it carrying the text;
  0/several → no nav, draft held + a hint to pick an area below. The text carries via a parent-held
  `pendingDraft` → `ConversationHost`'s new `initialDraft`/`onDraftConsumed` (seeds the composer once on
  mount, guarded by `!prompt`, then cleared — only the first matter after a launch is seeded). Honest
  starter chips from the user's own SavedPrompts (AE7 precedent, fail-soft → none). vitest 835 (+6);
  f2-baseline cypress 2/2 (PHASE=after) + a throwaway interaction spec confirmed end-to-end carry-forward
  then removed. Evidence: `docs/fork/evidence/f2-m4/`. Carry-overs (HANDOFF): the stale-draft window
  (accepted/documented) + the multi-area hint not screenshot-able with one configured area.
- M5–M9 pending.

## Risks / overlaps

- **F3 / UX-A overlap:** stay additive + de-emphasise only so the later retire flips cleanly.
- **F1 R-series overlap:** same chrome files — migrate-and-calm once, or calm-on-semantic if merged; never
  re-introduce `--lq-*`. Flag landed-state of R-CHROME/R-TYPO in HANDOFF before sequencing M2/M7/M8.
- **Pivot / schema:** the centered entry derives from `practiceAreasApi` + settled `GET /agents/matters`
  (ADR-F004) and invents no content; unconfigured areas degrade to the existing inert AreaGrid state.
