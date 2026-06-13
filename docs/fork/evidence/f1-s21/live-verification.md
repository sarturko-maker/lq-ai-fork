# F1-S2.1 — live verification evidence

Slice: design iteration v2 (responsive collapse · shade/contrast system · motion).
Plan: `docs/fork/plans/F1-S2.1-design-iteration-v2.md`. Stack: local dev compose,
web image rebuilt on the slice commit; api/gateway untouched (web-only diff).

## Benchmark sources (reviewed as images, kept out of the repo)

- Harvey assistant UI: cdn.sanity.io `9d7f5fc3…-2740x1540.jpg` (harvey.ai/products/assistant)
- Legora composer / citation card / split workspace: framerusercontent
  `gzWtcS3V…`, `Ps5B6iWE…`, `4BcnWjhC…` (legora.com/product)
- Linear dark cards / forms: webassets.linear.app changelog shots (`de21aba5…`, `c72160de…`)
- Attio canvas: a.storyblok.com `attio-og-image.jpg`

## Before (pre-slice bundle, F1-S2 merged state)

| Capture | File | What it shows |
|---|---|---|
| Landing 1280 | `before-1-landing-1280.png` | Flat near-white sheet, invisible card separation, body-level horizontal scrollbar |
| Landing 700 | `before-2-landing-700.png` | Rail squashed to ~127px, "Not configured" colliding with area names, "Unf…" truncation |
| Matters 1280 | `before-3-matters-1280.png` | Hairline-only hierarchy |
| Matter view 1280 | `before-4-matter-view-1280.png` | Legacy panel overflows horizontally at FULL width (clipped Run button); edge-to-edge composer; sage/legacy palette colliding with cockpit tokens |
| Matter view 700 | `before-5-matter-view-700.png` | Composer crushed to ~270px next to fixed w-72 list |
| Dark matter 1280 | `before-6-dark-matter-1280.png` | Legacy panel stays hard-white on charcoal (no `.dark` `--lq-*` overrides) |
| Dark settled 1280 | `before-8-dark-settled-1280.png` | Dark tokens DO apply (computed-style probe) — flat depth, light native scrollbar |

## After (slice bundle)

| Capture | File | What it shows |
|---|---|---|
| Landing 1280 | `after-1-landing-1280.png` | Warm-gray canvas under floating white cards (shadow-xs), arrow affordance, rail merged with canvas, rail-toggle in header, body scrollbars gone |
| Landing 700 | `after-2-landing-700.png` | Rail leaves the layout below 880px — full-width grid, no squash |
| Matters 1280 | `after-3-matters-1280.png` | List as a floating card, matched skeleton/empty states |
| Matter view 1280 | `after-4-matter-view-1280.png` | Workspace floats as ONE rounded card; recessed thread aside (muted wash); centered max-w-3xl conversation column; panel on semantic tokens (indigo Run, muted fills); empty area-card bar removed; no horizontal overflow |
| Matter view 700 | `after-5-matter-view-700.png` | Stacked mode: full-width list ⇄ full-width conversation with back row |
| Dark landing 1280 | `after-6-dark-landing-1280.png` | Charcoal canvas (0.23) under raised cards (0.28), never black |
| Dark matter 1280 | `after-7-dark-matter-1280.png` | Full dark coherence incl. the embedded panel (was hard-white) |
| Legacy dark | `legacy-dark-1-chats.png`, `legacy-dark-2-skills.png` | The `--lq-*` `:root.dark` stopgap: legacy tabs render on the charcoal scale (previously fully broken) |

Narrow-mode interaction evidence (drawer open/navigate, stacked back-and-forth) is asserted
by `f1-s21-responsive.cy.ts` (4/4) with its own screenshots.

## Found while verifying (root-caused, both fixed or documented)

1. **Headless captures lie about dark mode.** Headless Electron AND headless Chromium 149
   composite stale light tiles into screenshots after a theme flip — and even on a
   dark-first-paint fresh load — while `getComputedStyle` (probed element-by-element) is
   fully dark; a single element's one background captured as two colors across tile
   boundaries proves it's a rasterizer artifact, not CSS. HEADED runs (Cypress' Xvfb)
   capture correctly — dark evidence here is captured headed. Regression specs assert
   computed styles (authoritative), not pixels.
2. **The `.dark { --lq-* }` stopgap initially lost the cascade**: 16 legacy components
   re-`@import` practice.css inside scoped `<style>` blocks, so duplicate `:root` light
   blocks land later in bundle order and beat an equal-specificity `.dark` block. Fixed
   with `:root.dark` (0,2,0). Side effect: svelte-check's "unused CSS selector .dark"
   warnings dropped 20 → 5.

## Suites (final bundle)

- `npm run check`: **0 errors** (warnings 20 → 5)
- `npx vitest run`: **779/779 passed** (778 pre-slice + motionMs gate test)
- eslint: 0 new errors on touched files (main carries 73 pre-existing; branch total 74 → 74−73=1
  was the audit `cy.wait`, suppressed with justification; net new = 0)
- Cypress live (final bundle): f1-s2-cockpit **5/5**, f1-s21-responsive **4/4** (new),
  f0-s3-agents-tab **1/1** (panel restyle + slot-guard regression), wave-a **3/3**,
  m4 **9/9** — 22/22
- api/gateway: untouched (web-only diff — verified by `git diff --stat`)
