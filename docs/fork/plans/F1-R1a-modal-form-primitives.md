# Plan — R1a: Modal/form primitives (proven on NewMatterModal)

Status: **ready to implement** (explore done; this doc IS the spec — implement against it).
Slice of the F1 legacy-design rollout (`F1-legacy-design-rollout-decomposition.md` → R1a). Follows R0.
The cockpit (`NewMatterDialog.svelte`) is the **already-migrated exemplar** — copy its idiom.

## Goal

Build three reusable primitives and **prove them by migrating the real consumer
`NewMatterModal.svelte`** off its legacy `nmm-*` CSS + `var(--lq-*)` tokens onto the primitives +
semantic Tailwind tokens. After R1a the `nmm-*` style block is gone and NewMatterModal renders through
the shared kit (light + dark, wide + narrow), matching the cockpit dialog's idiom.

## Non-goals

- Do NOT touch the cockpit `NewMatterDialog.svelte` (exemplar — already migrated; verify, don't edit).
- Do NOT migrate other modals yet (R13 does AttachKB/PlaybookExecute; R1a only proves the kit on one
  real consumer). Build the primitives general enough for R13/R17 to reuse, but only wire NewMatterModal.
- No memoization, no behavior changes to validation (R0 already extracted `validators/matter.ts`).

## Files

New primitives (under `web/src/lib/lq-ai/components/primitives/` — new dir):
- `ModalShell.svelte` — wraps shadcn `ui/dialog` (Root/Content/Header/Title/Description/Footer).
- `FormControl.svelte` — label + (Input|Textarea slot) + help + error, semantic tokens, `aria-*` wiring.
- `Alert.svelte` — `role="alert"` banner for submit/inline errors (and reusable for info/warn intents).

Migrate:
- `web/src/lib/lq-ai/components/NewMatterModal.svelte` — replace the custom backdrop/panel + `nmm-*`
  `<style>` block + all `var(--lq-*)` with ModalShell + FormControl + Alert + Button. **44 `var(--lq-)`
  uses → 0.** Delete the entire `<style>` block.

Tests/evidence:
- `web/src/lib/lq-ai/__tests__/primitives.test.ts` (or per-primitive) — vitest.
- `web/cypress/e2e/shared-primitives.cy.ts` — NEW (does not exist yet); exercises the migrated modal.
- `docs/fork/evidence/r1a/` — screenshots.

## Primitive APIs (Svelte 5 runes)

**ModalShell** — generalizes the cockpit idiom. bits-ui `Dialog` ALREADY provides focus-trap, Escape,
overlay-click close, `aria-modal`, and title/description aria wiring — so ModalShell is a thin
composition, NOT a re-implementation:
```svelte
<script lang="ts">
  import * as Dialog from '$lib/components/ui/dialog/index.js';
  import type { Snippet } from 'svelte';
  let { open = $bindable(false), title, description, contentClass = '', children, footer }:
    { open?: boolean; title: string; description?: string; contentClass?: string;
      children: Snippet; footer?: Snippet } = $props();
</script>
<Dialog.Root bind:open>
  <Dialog.Content class={contentClass}>
    <Dialog.Header>
      <Dialog.Title>{title}</Dialog.Title>
      {#if description}<Dialog.Description>{description}</Dialog.Description>{/if}
    </Dialog.Header>
    {@render children()}
    {#if footer}<Dialog.Footer>{@render footer()}</Dialog.Footer>{/if}
  </Dialog.Content>
</Dialog.Root>
```
- Motion: `Dialog.Content`/`Overlay` already animate via `data-open:animate-in`/`data-closed:animate-out`.
  Add `motion-reduce:animate-none motion-reduce:transition-none` on the content wrapper for the
  reduced-motion path (Tailwind variant — simpler + more correct than threading `motionMs` through CSS
  animations). Keep `motionMs` available for any JS transition, but the dialog uses the CSS path.

**FormControl** — label/help/error around a slotted control; wires `for`/`id`/`aria-describedby`/
`aria-invalid`:
```svelte
<script lang="ts">
  import type { Snippet } from 'svelte';
  let { id, label, required = false, optional = false, error = null, help = undefined, inline = false,
    children }: { id: string; label: string; required?: boolean; optional?: boolean;
    error?: string | null; help?: string; inline?: boolean; children: Snippet } = $props();
</script>
```
Renders `<label for={id}>` + `{@render children()}` (the Input/Textarea/select/checkbox, given the
matching `id`) + optional help (`text-muted-foreground text-xs`) + error (`<Alert>` or inline
`text-destructive text-xs`, `id={`${id}-error`}` `role="alert"`). `inline` flips to a checkbox row
(label beside control). Caller sets `aria-invalid={!!error}` and `aria-describedby` on the control —
FormControl supplies the error element id.

**Alert** — semantic banner:
```svelte
<script lang="ts">
  import type { Snippet } from 'svelte';
  let { intent = 'error', children }: { intent?: 'error' | 'warning' | 'info'; children: Snippet } = $props();
</script>
```
`error` → `bg-destructive/10 text-destructive border-destructive/30`; carries `role="alert"`. (info/
warning intents map to muted/status washes — only `error` is needed for R1a, but build the prop.)

## NewMatterModal migration spec

Template → ModalShell with:
- `title="New matter"` — **must still render an `h2`-equivalent containing "New matter"** (wave-c test
  `cy.contains('h2', 'New matter')`; Dialog.Title renders an `h2` by default — VERIFY in dialog-title.svelte,
  else pass an `as`/heading). Keep `[role="dialog"]` (Dialog.Content provides it).
- Form fields via FormControl, **PRESERVING these ids (load-bearing for Cypress):**
  - `#nmm-name` (name Input) — `f0-s3-agents-tab.cy.ts:42`, wave-c.
  - `#nmm-privileged` (checkbox) — `wave-c-matters.cy.ts:120`.
  - `#nmm-tier` (tier select, only when privileged) — `wave-c-matters.cy.ts:123`.
  - description textarea `#nmm-description` (no test depends, keep for parity).
- Buttons via shadcn `Button`: Cancel = `variant="outline"` text "Cancel"; submit text "Create matter"
  (`disabled={submitting}`) — wave-c `cy.contains('button', 'Create matter'|'Cancel')`.
- Errors: name/tier via FormControl `error=`; submit error via `<Alert intent="error">`. Error copy is
  produced by `validateNewMatter` (R0) — unchanged ("…require a minimum tier floor — see PRD §5.x…").
- **Fix the InfoTip copy** (plan backlog): current privileged InfoTip says "defaults to Tier 2" — the
  seeded default is **no floor** (tier-4-only model; a <4 floor 403s every run — see HANDOFF Gotcha).
  Reword to: privileged forces an explicit tier floor (no silent default); operator picks it. Confirm
  exact wording against the privileged-tier semantics before committing.
- Native `<select>` for the tier (shadcn has no select primitive in `ui/`); style with semantic tokens
  (`border-input bg-transparent rounded-lg …`) to match Input. The select keeps `#nmm-tier`.

### Token map (legacy → semantic), for reference
`--lq-canvas`→`bg-popover` (dialog surface); `--lq-inset`→`bg-transparent`/`bg-muted`; `--lq-text-primary`
→`text-foreground`; `--lq-text-secondary`→`text-muted-foreground`; `--lq-text-tertiary`→`text-muted-foreground`;
`--lq-border`→`border-border`/`border-input`; `--lq-accent`→`primary`/`ring`; `--lq-accent-soft`→ring via
`focus-visible:ring-ring/50`; `--lq-error`→`destructive`; `--lq-error-soft`→`bg-destructive/10`;
`--lq-radius`→`rounded-lg`; spacing `--lq-space-*`→Tailwind `gap-*`/`p-*` (4/8/12/16/24 → 1/2/3/4/6).
Elevation: rely on `Dialog.Content`'s built-in `ring-1` + shadow; do not hand-roll the `0 24px 64px` shadow.

## Testing (discipline 1) + screenshots

- **vitest:** FormControl wires `for`/`id`/`aria-describedby`/`aria-invalid` correctly; Alert has
  `role="alert"` + destructive classes; ModalShell renders title/description/footer + closes on
  `open=false`. (Focus-trap/Escape are bits-ui's — assert the wiring, don't re-test the library.)
- **Cypress `shared-primitives.cy.ts`:** open NewMatterModal (from Matters page), assert `[role="dialog"]`,
  focus lands in the dialog, Escape closes, name-required error shows, privileged→`#nmm-tier` appears,
  tier-required error shows, create succeeds (201). Keep `wave-c-matters.cy.ts` + `f0-s3-agents-tab.cy.ts`
  + `f1-s2-cockpit.cy.ts` green (selectors preserved).
- **Screenshots (REQUIRED — this slice changes a rendered surface):** headed capture under
  `docs/fork/evidence/r1a/`: before/after, light+dark, wide(1280)+narrow(~480 modal), modal-default +
  error-state. Headed (headless lies about dark — HANDOFF Gotcha). Eyeball AA contrast on the
  destructive error text in dark.

## Adversarial review (discipline 3) — focus
aria-modal/focus-return on close, dark backdrop dimming (`bg-black/10` overlay over charcoal), error-state
WCAG contrast (`text-destructive` on `bg-destructive/10` in dark), the native select's focus ring parity,
tab order, that the three `#nmm-*` ids survived, Dialog.Title actually emits an `h2`.

## Simplification (discipline 2)
Delete the entire `nmm-*` `<style>` block (~175 lines) and the custom backdrop/keydown/`handleKeydown`
Escape handler (bits-ui Dialog owns Escape now). Net: large deletion + 3 reusable primitives the rest of
the rollout (R13/R17/R14b) consumes instead of re-rolling per-component error/modal CSS.

## Verification (ADR-F005 gate)
`npm run check` 0 errors · `npx vitest run` (counts) · `shared-primitives.cy.ts` + the 3 preserved specs ·
screenshots in evidence/r1a · CI green · fresh-context adversarial review · HANDOFF overwritten · squash-merge.
No new dependency (bits-ui/shadcn `dialog`,`input`,`textarea`,`button` already present).

## Pickup (fresh window)
`git checkout f1-r1a-modal-form-primitives` (this branch already holds this plan). Build
`primitives/{ModalShell,FormControl,Alert}.svelte` → migrate NewMatterModal → vitest +
`shared-primitives.cy.ts` → headed screenshots → adversarial subagent → HANDOFF → merge.
