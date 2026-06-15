# F013 — Design-language token layer (the scira-feel, taken as values not code)

- Status: accepted
- Date: 2026-06-15
- Deciders: maintainer (Arturs) — accepted 2026-06-15 (design-language layer approved; visual direction
  chosen = **Vercel**, commerce *look* + ai-chatbot *layout*, after reviewing six finished-product mockups;
  dark floor locked to charcoal `#111`, one scarce blue `--brand` accent)
- Extends: [[F012]] (minimalist pass + UX-redesign placement), [[F006]] (UI stack + design system),
  [[F011]] (AI Elements adoption)
- Supersedes: none (relaxes one specific F2 constraint — see Decision Outcome)

## Context

F2 (F012) has been calming the interface slice by slice — semantic-token migration, `PageShell`
consolidation, condensed chrome, the centered launcher. That work is correct *plumbing*, but the maintainer
observed (2026-06-15) that the interface is **still far from the scira aesthetic** and asked when it lands.

The honest diagnosis: **F2 as decomposed is consolidation, not a visual identity.** It makes the UI calm,
consistent, and semantic — but it never *defines* the aesthetic. A visual identity is not one token family;
it is a small set of deliberate decisions encoded as **design tokens**, with every surface assembled from
**primitives that consume those tokens**. Today only part of that layer exists:

- **Color** — done (`app.css`: semantic intents + `status-*` tones + `sidebar-*`, light + charcoal dark).
- **Radius** — exists (`--radius: 0.5rem` + `--radius-sm…4xl` scale).
- **Elevation** — exists (F1-S2.1 theme-aware `--elevation-xs…lg` → `--shadow-*`).
- **Type** — **NOT a token system.** Sizes live as ad-hoc literals (`font-size: 18px`, `1.5rem`) and as the
  legacy `lq-text-*` px classes in `lib/lq-ai/styles/typography.css` (still on `--lq-text*` colors). The
  deferred **R-TYPO** rollout slice has no defined *target* to migrate toward.
- **Spacing / rhythm** — **NOT a documented system.** Padding/gaps are per-surface literals; `PageShell`'s
  `pad` variants are the only codified rhythm.
- **Motion** — **NOT tokenized.** Only `cockpit/helpers.ts` `motionMs()` exists (a reduced-motion gate, 7
  callers); durations/easings are inline literals.

Until type, spacing, and motion are *values in one place* — and calibrated to a calm minimalist feel — no
amount of per-surface migration converges on a recognizable look, and surfaces already migrated by F2 would
be **re-touched** later to apply the real aesthetic.

**The AGPL constraint shapes how the aesthetic may be sourced.** `scira` is AGPL-3.0; F012 already binds us
to **reference-only** (study look/IA, never fetch or copy code). The clean architectural way to honor that
while still "taking the feel": **design *values* (spacing cadence, radii, type ramp, easing, palette
impressions) are facts/measurements — not copyrightable expression.** We may derive our own values and write
our own Svelte; we may not copy scira's CSS, components, class strings, or config. No copy ⇒ no AGPL
obligation attaches (unlike the MIT AE port we *do* vendor + attribute under F011).

## Considered Options

1. **Keep migrating surface-by-surface (status quo).** Finish F2-M7b/M8/M9, hope the look emerges.
   *Rejected:* it can't — the aesthetic-defining values (type/spacing/motion) are never authored; the result
   is "tidy but not scira," and the aesthetic pass later re-touches every surface (double work).

2. **One big visual redesign PR.** *Rejected:* violates the fork's vertical-slice discipline (CLAUDE.md
   §Iteration), is unreviewable, and isn't reversible.

3. **Define a design-language token layer, prove it on the flagship, then propagate (chosen).** Author the
   missing scales (type, spacing, motion) and formalize the existing ones (color/radius/elevation) into one
   documented language; build/extend primitives that consume it; calibrate on the **cockpit landing** first
   under the maintainer's eye; then let the remaining F2 surface slices adopt the *finished* language as they
   migrate (each surface touched once). Tokens are the single source of truth, so the aesthetic becomes a set
   of values the maintainer tunes — not 40 files re-edited.

4. **Adopt a third-party design system (Skeleton, shadcn theme pack, etc.).** *Rejected:* re-introduces a
   stack decision F006/F011 already settled (KEEP Svelte + our vendored AE primitives + our semantic
   palette), adds supply-chain surface, and still wouldn't be the scira *feel*.

## Decision Outcome

**Chosen: Option 3.** Establish a **design-language token layer** as its own milestone (working name
**F2-VL**, slices **VL0…**), governed by this ADR. Concrete contents and proposed values live in the
companion spec `docs/fork/plans/F013-token-language-spec.md` (a spec, not an ADR — values iterate under
review without re-deciding the architecture).

Architectural commitments:

- **Tokens are the contract.** All design decisions live as tokens in `app.css @theme` / `:root` (+ `.dark`
  where theme-variant). The layer *completes* the system: it adds **type** and **spacing/rhythm** and
  **motion** token families and documents radius/elevation/color as part of the same language. No raw design
  literals in surfaces once a token exists for them.
- **Primitives consume tokens; surfaces consume primitives.** Extend the existing
  `components/primitives/` set (`PageShell`, `SectionHeader`) with the small set the language needs
  (e.g. `Card`/`Surface`, `Stack`/`Inline` spacing, `Hero`, button/pill variants). Surfaces are assembled
  from primitives — bespoke `<style>` blocks are removed as surfaces adopt the language, never added.
- **Calibrate on the flagship first.** VL lands the tokens + primitives, then re-skins the **cockpit
  landing** as the proof, captured before/after for the maintainer's design review *before* broad rollout.
- **Then propagate via the in-flight migrations.** F2-M7b/M8/M9 are redefined from "migrate-and-calm" to
  "migrate **and apply the language**" — each surface touched once. The deferred **R-TYPO** slice gains its
  target: migrate `lq-text-*` → the F013 **type** tokens. The deferred **TrustPill** tone work resolves once
  the language decides whether tones extend the palette.

**Relaxation of one F2 constraint (the reason this is its own ADR).** F012's hard rule "*no new token scale —
the `app.css` semantic palette IS the system*" was correct for F2's reversible *consolidation* scope. F013
**deliberately extends the token system** (type/spacing/motion) — that is the whole point of the work, so it
must be a recorded decision, not smuggled into an F2 slice. The relaxation is **scoped to the design-language
layer**: extensions must be *systematic* (a documented scale, light+dark-checked, consumed via primitives) —
never an ad-hoc parallel scale on one surface (the thing F012 rightly banned, e.g. the TrustPill tone
sprawl). F2's remaining surface slices stay bound by F012; they *consume* F013, they don't invent tokens.

**Chosen visual reference (calibration).** After rendering six finished-product mockups
(`docs/fork/evidence/f013/refs/`, all MIT/Apache), the maintainer chose the **Vercel** aesthetic: the
*look* of **vercel/commerce** (MIT — minimal, typography-led, monochrome) inside the *layout* of
**vercel/ai-chatbot** (Apache-2.0 — sidebar of recent matters + centred cockpit). The fused target is
`docs/fork/evidence/f013/direction-vercel/`; concrete values are in the companion spec. Both references are
permissive, so patterns *may* be borrowed — but we still re-express in our own tokens + Svelte and copy no
code; nothing is vendored, so no `NOTICES.md` entry is required.

**Provenance boundary (scira / AGPL).**
- **Permitted:** studying scira's rendered look/IA; deriving numeric *values* (spacing cadence, radii, type
  sizes/weights, easing curves, neutral-ramp impressions) and re-expressing them in our own tokens; writing
  our own Svelte primitives.
- **Forbidden:** fetching, copying, transcribing, or vendoring any scira source — CSS, component code, class
  strings, Tailwind/theme config. No file-level derivation.
- **Recorded:** the token spec carries a one-line provenance note ("values independently chosen to evoke a
  calm minimalist feel; no scira code copied"). Because no code is copied, **no AGPL obligation attaches** and
  no `NOTICES.md` entry is required (contrast the MIT AE port, which is vendored and attributed). If that ever
  changes (any line of scira is copied), it is a separate maintainer-approved decision and a NOTICES entry.

## Consequences

- **Positive:** the aesthetic becomes tunable in one place; surfaces converge by construction; F2's remaining
  slices do their migration *once*, with the real look; R-TYPO and TrustPill get unblocked targets; the
  scira-feel is sourced legally and auditably.
- **Cost / risk:** a deliberate pause on F2 surface migration (M7b/M8/M9 wait for VL) before they resume;
  the token values need real maintainer design review (the calibration is taste, not a unit test — the
  flagship-first proof exists to front-load that judgment); extending `@theme` touches a global file (every
  VL token change is screenshot-verified light+dark, per the DoD).
- **Reversibility:** additive token families + new primitives are reversible (delete the tokens/primitives,
  surfaces fall back to their prior literals until re-touched); the *adoption* on a surface is as reversible
  as any F2 slice. The architecture (tokens→primitives→surfaces) is the same direction F006/F011/F012 already
  set — this names and completes it, it does not pivot.
- **Sequencing:** VL slots **after F2-M7a (done) and before F2-M7b**; UX-A/UX-B (F012) still follow, now
  riding a finished visual language. This does not touch the pivot/schema blockers.

Companion spec (proposed values + slice plan): `docs/fork/plans/F013-token-language-spec.md`.
