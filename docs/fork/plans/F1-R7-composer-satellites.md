# Plan — R7: Composer satellites (SlashPopover + EnhancePromptExpansion)

Slice **R7** of the legacy `--lq-*` → semantic-token design rollout
(`F1-legacy-design-rollout-decomposition.md`). One PR, ≤200k session.

## Goal

Migrate the two composer "satellite" surfaces off the `--lq-*` custom-property
system onto the shipped semantic tokens (cockpit idiom), reusing the R1a/R6 kit.

| File | `var(--lq-)` before | After |
|---|---|---|
| `C/SlashPopover.svelte` | 18 | **0** |
| `C/EnhancePromptExpansion.svelte` | 49 | **0** |

R7 is a **satellite/popover** slice, not a shell/container — the 2026-06-13
responsive-parity directive does **not** add a deliverable here (that lands on
R5/R8/R9/R-CONV-2/R-CHROME). The existing `max-[640px]` single-column reflow in
EnhancePromptExpansion is preserved (re-expressed as Tailwind `sm:` breakpoint).

## Non-goals

- ChatPanel (`.lq-composer-popover` wrapper + its `z-index:50`) — that is R9's
  file; not touched here. R7 only restyles the popover's own surface, which sets
  no competing z-index (the wrapper owns stacking).
- TrustPill (rendered by EnhancePromptExpansion) — owned by **R2**; left on the
  bridge. EnhancePromptExpansion keeps `<TrustPill variant="tier" …>` unchanged.
- The pure module helpers + keyboard/aria state machine in SlashPopover — logic
  is behaviour-frozen (token-only migration); only `<style>` → Tailwind.

## Approach

### SlashPopover (stays Svelte 4)
- Keep the entire `<script context="module">` (tested pure helpers) and the
  instance keyboard logic (`<svelte:window>`, `aria-activedescendant`, `role`s)
  **byte-for-byte**.
- Delete the whole `<style>` block; move every rule to Tailwind semantic classes
  on the markup. Mapping:
  - panel `--lq-surface/--lq-canvas` → `bg-popover text-popover-foreground`,
    `--lq-border` → `border-border`, box-shadow → `shadow-md` (= `--elevation-md`,
    the same float), `--lq-radius` → `rounded-md`.
  - status `--lq-text-tertiary` → `text-muted-foreground`; error
    `--lq-error` → `text-destructive dark:text-red-300` (R1a gotcha b: destructive
    fails AA in dark on light surfaces).
  - active row `--lq-accent-soft` → `bg-accent` (soft wash; text stays
    `text-foreground`, matching the legacy "soft bg, normal text"); link/focus
    `--lq-accent` → `text-primary` / `ring-ring`.
  - The `class:active` driving the row bg becomes `class:bg-accent`.

### EnhancePromptExpansion (→ Svelte 5 runes + shadcn Button)
- Convert `export let` → `$props()`; `let state` / `let jitDismissed` → `$state`;
  keep `export async function open()` (ChatPanel calls it via `bind:this`).
  `JIT_SEEN_KEY` has no external importer → demote to a local `const`.
- Replace the three local button families (`.lq-btn-primary/secondary/ghost`)
  with shadcn **`Button`** (R8 does this app-wide; R7 owns this file):
  primary → `<Button>` (default), secondary → `variant="outline"`,
  ghost → `variant="ghost"`, the `×` → `variant="ghost" size="icon-sm"`.
  (Native `on:click`→`onclick` flows through Button's `restProps` to the DOM
  button now the parent is runes — legacy `on:click` on a runes child would NOT
  forward, which is the reason for the runes conversion.)
- Delete the `<style>` block entirely (incl. `@import practice.css`, the
  `lq-spin` keyframes → Tailwind `animate-spin`, and the local `.lq-text-caption`
  redefinition → `text-xs text-muted-foreground`). Token mapping:
  panel/card `--lq-canvas` → `bg-card`, `--lq-border` → `border-border`,
  enhanced card `--lq-accent-border`/`--lq-inset-secure` → `border-primary/40
  bg-accent`, label `--lq-accent` → `text-primary`, `--lq-error` →
  `text-destructive dark:text-red-300`, JIT warn band → amber tone
  (`border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300`,
  the R6 ProvenancePill amber idiom).
- **Preserve every `data-testid`** (`lq-ai-enhance-panel/-loading/-jit/
  -jit-dismiss/-original/-enhanced/-use/-edit/-keep/-skipped/-skipped-ok/
  -error/-retry/-error-dismiss`) and the exact prop names ChatPanel passes
  (`originalText`, `chatId`, `onUseEnhanced/onEditEnhanced/onKeepOriginal/
  onDismiss`).

## Simplify (discipline 2)
- SlashPopover: `<style>` (≈100 lines) deleted.
- EnhancePromptExpansion: `<style>` (≈200 lines incl. 3 button families +
  keyframes + practice.css import) deleted; one less `practice.css` consumer.

## Verification (ADR-F005 gate)
1. `cd web && npm run check` (0) + `npx vitest run` (counts in PR — the two
   existing helper specs must stay green; they import only module helpers /
   inline mappings, unaffected by the runes conversion).
2. New `cypress/e2e/r7-composer-satellites.cy.ts` — deterministic intercepts
   (`/skills/autocomplete`, `/enhance-prompt`): listbox a11y (role/option/
   `aria-activedescendant` tracks ArrowDown), enhance panel original/enhanced,
   and phase-tagged screenshots. Run headed (electron, `DISPLAY=:0`).
3. Screenshot evidence under `docs/fork/evidence/r7/` — before/after, light+dark,
   wide+narrow (popover open; enhance panel shown with the JIT strip).
4. CI green (repo public now — full gate restored).
5. Fresh-context adversarial review — focus: listbox keyboard/`aria-activedescendant`,
   popover z-index/stacking, dark-mode contrast on `bg-popover`/`bg-accent` and
   the amber JIT band, Button event-forwarding under the runes conversion, no
   lost state/affordance across the 5 enhance states.
6. HANDOFF.md overwritten → NEXT = R8.
