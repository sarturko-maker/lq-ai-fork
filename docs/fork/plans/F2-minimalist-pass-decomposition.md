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
  R-slice merged, else migrate-and-calm. Coordinate F1 R12/R14a/R15/R19a/R20. **SPLIT by visual family:**
  **M7a** = table-list trio (playbooks/tabular/skills); **M7b** = card/wrapper trio
  (knowledge/learn/saved-prompts). *(M)*
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
- **F2-M5** — done (PR #72): CockpitHeader minimal-chrome restyle (one file, presentation-only). Muted
  ghost buttons gain `hover:text-foreground` (one calm resting state, tab-bar idiom); right cluster gap
  `gap-1.5`→`gap-1`; theme/settings/sign-out grouped into a tight `gap-0.5` cluster behind a decorative
  `bg-border` hairline separator. All handlers/routes/aria-labels/the Tools dropdown (with the M3
  muted-legacy item) byte-identical; no AI furniture (ADR-F002), no new token scale/`--lq-*`/`{@html}`,
  nothing retired. vitest unchanged (835); f2-baseline cypress 2/2 (PHASE=after). Evidence:
  `docs/fork/evidence/f2-m5/`. Review SHIP.
- **F2-M6** — done (PR #73): matters + conversation surfaces consolidated onto PageShell. Added the
  `pad` variant (`default`/`compact`/`tight`) to `PageShell` (M1 carry-over RESOLVED); `MattersPanel`
  container → `<PageShell pad="compact">` (bespoke header kept), `ConversationHost` conversation column →
  `<PageShell size="narrow" pad="tight">` (fade on an inner div, the M1 idiom). Visually equivalent (pads
  copied verbatim — consolidation, not a visible redesign). `AreaRail` intentionally untouched (sidebar,
  doesn't fit). vitest 836 (+1); f2-baseline cypress 3/3 (PHASE=after, new matters+conversation capture
  test). Evidence: `docs/fork/evidence/f2-m6/`. Review SHIP.
- **F2-M7a** — done (this PR): calm table-list trio (playbooks/tabular/skills). Adopted
  `<PageShell size="wide" pad="compact">` (bespoke headers kept — trailing-CTA header, SectionHeader doesn't
  model it); migrated **color** `--lq-*`→semantic (`--lq-accent`→`--primary` teal→blue, unifies with chrome);
  tabular status pills → the existing `--status-*` tone family (both themes, no new scale).
  `--lq-radius*`/`--lq-space-*`/`lq-text-*` left to R-TYPO (documented); `TrustPill` deferred (M2). vitest
  836 (unchanged — presentation-only); f2-baseline cypress 4/4 (PHASE=after, new playbooks+tabular capture).
  Evidence: `docs/fork/evidence/f2-m7a/`. Review SHIP, no blockers/should-fixes/nits.
- **F2-VL0** — done (PR #76): the **F013 design-language token layer** lands first (sequenced between M7a and
  M7b, ADR-F013). `app.css` recoloured to the Vercel palette — ink `--primary` + scarce `--brand` blue +
  charcoal `#111` dark; added the `--text-*` type scale + `--motion-*` tokens; radius 10/12; `motionMs()`
  wired onto a CSS-synced `MOTION` mirror. Tokens only, no layout. check 0 err, vitest 837, cypress 4/4.
  Evidence: `docs/fork/evidence/f2-vl0/`.
- **F2-VL1** — done (PR #77): seven token-consuming primitives (`AppShell`/`Hero`/`Card`/`CardGrid`/`Stack`/
  `Inline`/`StatusDot`) + pure class helpers (unit-tested, vitest 850), proven in a dev-only `_vl-lab` route
  rebuilding `direction-vercel`. No live surface re-skinned. Evidence `docs/fork/evidence/f2-vl1/`. Then
  **VL2** (re-skin `cockpit/` — maintainer design gate).
- **F2-M7b** — done (PR #86): card/wrapper trio (knowledge/learn/saved-prompts). Same recipe + the F013 calm
  card idiom (flat/border-led, hover→`--muted`, no float shadow, scarce-blue focus); bespoke widths snapped
  onto the system reading widths (knowledge→`wide`, learn/saved-prompts→`default`); knowledge KB status pills
  → `--status-*`. vitest 851; f2-baseline cypress 4/4. Evidence: `docs/fork/evidence/f2-m7b/`. Review SHIP.
- **F2-M8** — done (PR #87): settings/admin/trust **nav shells** — the last chrome on the teal `--lq-accent`
  active marker (`#1f7a6b`, not the Vercel blue — visibly off-brand, not cosmetic). settings (vertical rail)
  → the live AreaRail idiom (raised `--card` pill + `--shadow-xs`, no accent); admin (horizontal tab strip)
  → inked `--foreground` underline; trust → `<PageShell size="wide">`. `:focus-visible --ring` added to both
  nav sets. Scope = nav shells only (child page bodies + Trust\*Card internals stay on `--lq-*`/teal — owned
  by R16/R19). vitest 851; f2-baseline cypress 5/5. Evidence: `docs/fork/evidence/f2-m8/`. Review SHIP.
- **F2-M9** — done (PR #__): **consistency sweep + verify — the F2 closer.** Static audit of every F2-touched
  surface: **zero color `--lq-*`** (the `--lq-radius*`/`--lq-space-*`/`lq-text-*` carve-outs are the
  deliberate R-TYPO boundary), **zero `{@html}` sinks**, **zero teal/hardcoded-hex rogue accents** (one-accent
  holds: ink primaries + scarce `--brand`/`--ring`). **Reachability (no-retire contract):** all 11 tab
  surfaces + trust + settings resolve under `(app)`, reachable from the rail Tools group + header gear/
  ShieldCheck. **Cross-surface consistency (44-shot full matrix, light+dark × wide+narrow):** the
  raised-card-pill active-nav idiom is identical across rail + settings; status pills share the family
  (scarce-blue `running`, green `completed`); AA-dark legible, no light-in-dark panels. **No code change** —
  the F2 pass was disciplined throughout; M9 verifies + documents the owned debt (R16/R19 child bodies,
  R-TYPO `lq-text-*`/radius/space, deferred TrustPill tones, the intentional `_vl-lab`/`_ae-lab` scratch
  routes). Evidence: `docs/fork/evidence/f2-m9/`. **F2 milestone COMPLETE.**

## Risks / overlaps

- **F3 / UX-A overlap:** stay additive + de-emphasise only so the later retire flips cleanly.
- **F1 R-series overlap:** same chrome files — migrate-and-calm once, or calm-on-semantic if merged; never
  re-introduce `--lq-*`. Flag landed-state of R-CHROME/R-TYPO in HANDOFF before sequencing M2/M7/M8.
- **Pivot / schema:** the centered entry derives from `practiceAreasApi` + settled `GET /agents/matters`
  (ADR-F004) and invents no content; unconfigured areas degrade to the existing inert AreaGrid state.
