# R1a — live verification (modal/form primitives on NewMatterModal)

Captured headed (Electron, `DISPLAY=:0`) on the live dev stack — headless lies about the dark theme
(HANDOFF Gotcha), so all six were taken headed. Spec: `cypress/e2e/shared-primitives.cy.ts`.

## Cypress — `shared-primitives.cy.ts` (live stack, headed)

`6 passing` after the migration:

- opens as a dialog with the title, **traps focus** (focus lands inside `[role="dialog"]`), **closes on Escape** ✓
- Cancel dismisses the dialog ✓
- required-name error shows; dialog stays open ✓
- privileged → `#nmm-tier` appears; tier-floor enforced ✓
- create → routes to `/lq-ai/matters/{id}` ✓
- captures the six screenshots below ✓

Behavior the bits-ui Dialog now owns (focus-trap, Escape, overlay-click, scroll-lock, `aria-modal`,
`aria-labelledby`) — **the old hand-rolled modal failed exactly the focus/Escape check** (5/6 on the
pre-R1a bundle), which the primitive fixes. Kept specs `wave-c-matters` / `f0-s3-agents-tab` stay green
(the `#nmm-name`/`#nmm-privileged`/`#nmm-tier` ids and `[role="dialog"]` are preserved; the one `h2`
title assertion was repointed to the bits-ui `[data-slot="dialog-title"]`, an `aria-labelledby` heading).

## Screenshots (before = pre-R1a bundle, after = R1a bundle)

| State | Before | After |
|---|---|---|
| Light, wide, default | `before-1-modal-light-wide.png` | `after-1-modal-light-wide.png` |
| Light, wide, error | `before-2-modal-light-wide-error.png` | `after-2-modal-light-wide-error.png` |
| Dark, wide, default | `before-3-modal-dark-wide.png` | `after-3-modal-dark-wide.png` |
| Dark, wide, error | `before-4-modal-dark-wide-error.png` | `after-4-modal-dark-wide-error.png` |
| Light, narrow | `before-5-modal-light-narrow.png` | `after-5-modal-light-narrow.png` |
| Dark, narrow | `before-6-modal-dark-narrow.png` | `after-6-modal-dark-narrow.png` |

## Visual verdict (eyeballed)

- **Before**: legacy sage-green accent (`--lq-accent #1f7a6b`) button + focus ring, no close affordance,
  hand-rolled shadow. **After**: indigo semantic `primary`, indigo focus ring, an `×` close button, a
  muted footer bar (`bg-muted/50`) — matches the cockpit `NewMatterDialog` exemplar.
- **Light**: white card on the warm-gray canvas (no black bg — design rule held).
- **Dark**: charcoal surface (never black), both red error strings legible on charcoal (the `destructive`
  token reads AA in dark), the tier `<select>` shows the `aria-invalid` red border.
- **Narrow (480)**: dialog clamps to `max-w-[calc(100%-2rem)]`, content stacks, no overflow.
