# Editor Slice 4b — polish evidence (ADR-F047 Slice-4b addendum)

Live headed-Cypress captures (real stack + real Collabora) after fixing the four maintainer-reported
Slice-4 UX defects. The spec (`web/cypress/e2e/libreoffice-editor.cy.ts`) asserts, at each width, that
the document **fills the editor pane** (`docPx / paneWidth ∈ [0.8, 1.0]` — no whitespace, no overflow)
and that the editor `<section>` fills its 2/3 card slot (`>0.98`).

## What was wrong (probed on the live DOM) vs fixed

| # | Defect | Root cause | Fix |
|---|---|---|---|
| 1 | Editor pane ~½ screen | card slot was `flex-1` | card `flex-[2_1_0%]` (2/3 : 1/3) |
| 2 | "What's New" popup | prebuilt image forces welcome on | `--o:home_mode.enable=true` (+`allow_update_popup=false`) |
| 3 | Doc at 30% / ~⅓ of pane | (a) `<section>` lacked `w-full` → shrank to ~iframe intrinsic width; (b) `getScaleZoom` is base-2 but Collabora scales ~1.2×/level → computed jump undershot to ~0.68 | (a) `w-full`; (b) iterative `nextFitAction` off measured docPx + poll/ResizeObserver + stability gate |
| 4 | Whitespace to the right | same as 3(a)+(b) | resolved by 3 |

Measured at the 1920 pane: cold open ~0.30 → **0.98** fill (level 12). Verified holding on shrink
(1920→1440, was overflowing 1.10 before the getSize-stability gate) and at 1024.

## Files

- `after-ultrawide-{light,dark}.png` — 1920×1080 (a real wide monitor; where the bug was starkest)
- `after-wide-{light,dark}.png` — 1440×900 (also the shrink-from-1920 case)
- `after-narrow-{light,dark}.png` — 1024×768
- `after-closed.png` — editor closed, single-pane conversation restored

## Gates

svelte-check 0 errors · Vitest 969 (incl. 6 `nextFitAction` cases) · prettier clean · doc-fill +
section-fill assertions green at 1920/1440/1024 (light+dark). Two adversarial review passes
(4-dim × verify): **0 blockers / 0 should-fixes**; all confirmed nice-to-haves folded.
