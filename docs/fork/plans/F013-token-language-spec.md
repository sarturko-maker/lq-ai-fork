# F013 — Token-language spec (Vercel direction · values + VL slice plan)

Companion to **ADR-F013** (design-language token layer). The ADR fixes the *architecture* (tokens →
primitives → surfaces; the provenance boundary; the F2-constraint relaxation). This spec holds the *concrete
values* and the *slice plan* — values iterate under maintainer review without re-opening the ADR.

## Chosen reference & locked decisions (2026-06-15)

The maintainer reviewed six finished-product mockups (`docs/fork/evidence/f013/refs/`) and chose the
**Vercel** aesthetic:

- **Look** from **vercel/commerce** (MIT) — ultra-minimal, typography-led, near-monochrome, hairline borders,
  generous whitespace, one scarce blue accent.
- **Layout** from **vercel/ai-chatbot** (Apache-2.0) — left sidebar (recent matters + *New matter* + account)
  beside a main **centred cockpit** launcher.
- The fused target is rendered in **`docs/fork/evidence/f013/direction-vercel/`** (light + dark) — that
  mockup *is* the spec's north star; the values below match it.

**Provenance:** both references are permissive (MIT / Apache-2.0). We study the *feel* and re-express it in
our own tokens + our own Svelte; **no reference code is copied** (ADR-F013). No scira code anywhere
(AGPL — ADR-F012). No `NOTICES.md` entry needed (nothing vendored).

**Locked calibration decisions (maintainer):**
1. **Dark floor = charcoal `#111`** — NOT Vercel's pure `#000`; honors the standing rule *"don't use black
   background — charcoal."*
2. **One scarce blue accent** (Vercel blue) — `--brand`, used only for focus / links / running. Everything
   else monochrome; primary actions are ink (black / inverting white).

---

## 1. Colour — the headline change (recolour, mapped to semantic token names)

Today `app.css` is **warm-neutral (hue ≈90) + an indigo `--primary`**. The Vercel direction is **neutral
gray ink/charcoal + a *scarce* blue**. Two structural remaps (this is what makes it "Vercel", and it is a
sweeping change — every primary button/active state recolours):

- **`--primary` becomes INK** (black in light / near-white in dark), no longer the brand blue. Primary
  buttons, active emphasis → ink. (Vercel's inverting black/white primary.)
- **NEW `--brand` = the one scarce Vercel blue.** Focus ring, links, the *running* status — and nothing
  else. This is the "one accent" rule made literal. (`--accent`/`--accent-foreground` stay as shadcn's
  subtle neutral hover-wash, retuned gray.)

| Semantic token | Light | Dark (charcoal floor) | Role |
|---|---|---|---|
| `--background` | `#ffffff` | `#111111` | canvas |
| `--foreground` | `#111111` | `#ededed` | ink |
| `--card` | `#ffffff` | `#161616` | panels/cards |
| `--sidebar` | `#fafafa` | `#0c0c0c` | rail |
| `--muted` | `#f5f5f5` | `#1a1a1a` | hover / subtle bg |
| `--muted-foreground` | `#707070` | `#8f8f8f` | secondary text |
| (faint metadata) | `#999999` | `#6b6b6b` | tertiary (size/weight carries more) |
| `--border` | `#ededed` | `#262626` | hairline |
| `--input` / strong | `#e2e2e2` | `#333333` | field border |
| `--primary` | `#111111` | `#ededed` | **ink** — buttons/active (inverts) |
| `--primary-foreground` | `#ffffff` | `#111111` | on-ink |
| `--brand` (NEW) | `#0070f3` | `#47a3ff` | **scarce blue** — focus/links/running |
| `--ring` | `#0070f3` | `#47a3ff` | focus = brand |
| `--destructive` | `#c4271a` | `#f87171` | failed/danger |
| status: completed | `#0f7b34` | `#4ade80` | done dot |
| status: running | = `--brand` | = `--brand` | running dot |

Notes: WCAG-recheck on adoption (4.5:1 text, 3:1 UI), same contract as today. The existing `status-*` tone
family stays available for dense data tables; the **minimal surfaces prefer a single coloured dot + muted
label over filled pills** (§6). This remap supersedes the warm-neutral/indigo palette in `app.css :root` /
`.dark`.

---

## 2. Type scale (NEW token family — the biggest structural gap)

Today: ad-hoc px + legacy `lq-text-*` (12/12/13.5/14/16/18/22). The Vercel look is **typography-led** — a
big editorial hero + a calm role-named ramp (rem; 1rem = 16px):

| Token (role) | size | line-height | weight | tracking | replaces `lq-text-*` | usage |
|---|---|---|---|---|---|---|
| `--text-display` | **2.75rem (44)** | 1.08 | 600 | -0.04em | (new) | cockpit hero "What are you working on?" |
| `--text-title` | 1.5rem (24) | 1.2 | 600 | -0.02em | `page-h` / `welcome` | page h1 |
| `--text-heading` | 1.125rem (18) | 1.35 | 600 | -0.01em | `panel-h` | section h2 |
| `--text-subheading` | 1.125rem (18) | 1.3 | 500 | -0.02em | (new) | card title (Vercel uses a lighter weight here) |
| `--text-body` | 0.9375rem (15) | 1.6 | 400 | normal | `body` | prose, default |
| `--text-body-sm` | 0.875rem (14) | 1.5 | 400 | normal | `body-sm` | dense tables/meta |
| `--text-caption` | 0.8125rem (13) | 1.45 | 400 | normal | `caption` | secondary meta |
| `--text-label` | 0.6875rem (11) | 1.3 | 600 | 0.12em / uppercase | `label` | eyebrow labels (Vercel's tracked overline) |

**R-TYPO target:** migrate `lq-text-*` → these tokens (the target R-TYPO was missing). Inter stays the face.

---

## 3. Spacing / rhythm (documented system over Tailwind's 4px base)

Vercel feel = generous, consistent rhythm. Keep Tailwind's 4px step; document conventions (encoded in
primitives, not a parallel scale):

| Convention | value | where |
|---|---|---|
| app shell | 264px sidebar + fluid main | `AppShell` |
| cockpit gutter | `px-7` (28) | cockpit container |
| cockpit top | `pt-16/18` (~72) — roomy hero | cockpit |
| section gap | `mt-16` (64) between cockpit blocks | `Stack` |
| card padding | `p-6` (24) | `Card` |
| inline gap (chips/links) | `gap-5/6` (20-24) text-links | `Inline` |
| control height | 38 / 40 px | button/field |

---

## 4. Motion (NEW token family — formalize `motionMs()`)

`motionMs()` (cockpit/helpers.ts, 7 callers) gates on `prefers-reduced-motion` but durations/easings are
inline. Add tokens; keep the gate. Vercel feel = subtle, fast, never bouncy.

| Token | value | use |
|---|---|---|
| `--motion-fast` | 100ms | hovers |
| `--motion-base` | 150ms | enters/exits, panel swaps |
| `--motion-slow` | 240ms | hero / route-level |
| `--motion-ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | most |
| `--motion-ease-emphasized` | `cubic-bezier(0.3, 0, 0, 1)` | hero |

No new dep (`tw-animate-css` already imported).

---

## 5. Radius + elevation

- **Radius:** base **`--radius: 0.625rem` (10px)**; `--radius-lg` 0.75rem (12px) for cards/composer;
  buttons 8px; pills/avatars `9999px`. (Cascades through `--radius-sm…4xl`.)
- **Elevation:** Vercel is **flat** — hairline borders do the work; **shadows only on true float**
  (popover/modal/dropdown). Keep the F1-S2.1 `--elevation-*` scale but apply it sparingly; cards rest on a
  border, not a shadow.

---

## 6. Layout & idioms (the Vercel direction made concrete)

- **App shell = sidebar + cockpit** (NEW `AppShell` primitive): 264px `--sidebar` rail (brand · `New matter`
  ink button · **Recent matters** list with area + relative time · account footer) beside a main column with
  a thin top bar (breadcrumb + theme toggle) and the centred cockpit.
- **Inverting primary:** the one solid button is ink→white (light) / white→ink (dark). Secondary = hairline
  border; tertiary = ghost.
- **Hairline-divided grid** for the practice cards (1px gaps over a `--border` bg, single outer radius), not
  free-floating shadowed cards.
- **Status = a single coloured dot + muted label** on minimal surfaces (running = `--brand`, completed =
  green, failed = `--destructive`, idle = faint) — reserve the filled `status-*` pills for dense data tables.
- **Chips = understated text links** (underline-on-hover), not bordered pills.
- One scarce `--brand` blue; everything else monochrome.

---

## 7. Primitives (consume the tokens; the rollout vehicle)

| Primitive | state | role |
|---|---|---|
| `PageShell` / `SectionHeader` | ✅ exist | centred container + heading roles |
| `AppShell` | new | the sidebar + cockpit shell (§6) |
| `Stack` / `Inline` | new (thin) | rhythm from §3 |
| `Card` / hairline `CardGrid` | new | §6 card idioms on tokens |
| `Hero` | new | the display-type centred launcher block |
| `StatusDot` + button variants | new/consolidate | dot-status + inverting primary / ghost |

Presentation-only, token-driven, unit-tested where a pure class helper exists (`pageShellClass` precedent).
Surfaces shed bespoke `<style>` as they adopt these.

---

## 8. Slice plan (milestone F2-VL — additive, reversible, screenshot-gated)

Each = one PR, full DoD (check/vitest/headed before+after light+dark × wide+narrow / fresh-context review /
HANDOFF). Each visual slice carries a **`direction-vercel` side-by-side** for the maintainer's eye.

- **VL0 — tokens + ADR.** Accept ADR-F013; **recolour `app.css`** to §1 (ink `--primary` + new `--brand` +
  neutral ramp + charcoal `#111` dark) and add **type / motion** tokens (+ radius tune); wire `motionMs()` to
  `--motion-*`. Recolour is global → screenshot the existing surfaces light+dark to confirm no contrast
  regression (the semantic names are unchanged, so consumers move with the values). The one app-wide visible
  shift: brand blue → ink primaries + scarce blue. Tokens only, no new layout.
- **VL1 — primitives + app shell.** Build `AppShell` (sidebar+cockpit), `Hero`, `Card`/`CardGrid`,
  `Stack`/`Inline`, `StatusDot`, button variants on the tokens. Prove in a dev-only `_vl-lab`.
- **VL2 — cockpit landing proof (flagship).** Re-skin `cockpit/` (`AreaRail` → the Vercel sidebar;
  `CenteredEntry` → the `Hero`; `AreaGrid` → the hairline `CardGrid`; matters → dot-status list) to match
  `direction-vercel`. **Maintainer design-review gate** — iterate values here until it reads right.
- **then → resume F2 with the language applied** (each surface touched ONCE):
  - **F2-M7b** (knowledge/learn/saved-prompts) — migrate **and apply** the language.
  - **F2-M8** (settings/admin/trust) — same.
  - **R-TYPO** — `lq-text-*` → §2 type tokens (now has a target).
  - **TrustPill** — resolve tones against §1 (monochrome + dot-status decided).
  - **F2-M9** — consistency sweep + verify (AA-dark / one-accent / rhythm).

## Decisions resolved (were open questions)

1. **Reference:** Vercel — commerce *look* + ai-chatbot *layout* (`direction-vercel/`). ✅
2. **Dark floor:** charcoal `#111`, never `#000`. ✅
3. **Accent:** one scarce blue `--brand`; `--primary` recoloured to ink. ✅
4. **Hero type:** `--text-display` 44px. ✅
5. **Radius:** 10px base / 12px cards. ✅
6. **Tones:** dot-status on minimal surfaces; `status-*` pills retained for dense tables. ✅
7. **Milestone name:** **F2-VL** (visual language), sequenced after F2-M7a, before F2-M7b. ✅
