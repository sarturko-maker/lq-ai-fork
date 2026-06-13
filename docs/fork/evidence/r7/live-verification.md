# R7 — live verification (composer satellites)

Slice: SlashPopover + EnhancePromptExpansion → semantic tokens. Dev stack
(8 services healthy), admin@lq.ai, headed Electron Cypress (`DISPLAY=:0`),
captured against the running bundle BEFORE and the rebuilt bundle AFTER.

## Gate

| Gate | Result |
|---|---|
| `npm run check` (svelte-check) | **0 errors** (5 pre-existing warnings in unrelated files) |
| `npx vitest run` (full) | **797 passed** (76 files) — unchanged vs main; SlashPopover (20) + EnhancePromptExpansion (4) helper specs green after the runes conversion |
| `eslint` (the two migrated files) | clean (note: eslint is **not** a CI gate — the web CI job runs only `npm run check` + `vitest -- --run`; matches CLAUDE.md's web command list) |
| `prettier --check` (migrated files) | clean |
| Cypress `r7-composer-satellites.cy.ts` | **4/4 passing** on the AFTER bundle (a11y, enhance panel, 2 screenshot tests) |
| `grep -c 'var(--lq-'` both files | **0 / 0** (was 18 / 49) |

## Adversarial review (fresh-context, 4 dimensions → per-finding skeptical verify)

27 agents; **23 findings raised → 3 confirmed** (3 refuted-as-pre-existing/non-issues
incl. retry-button aria-label that predates this diff). All 3 fixed + re-verified:

1. **BLOCKER (WCAG AA)** — Enhanced-card label was `text-primary` on `bg-accent`
   (2.69:1 light / 2.16:1 dark, fails 4.5:1). **Fixed →** `text-accent-foreground`
   (the token designed for ink on the accent wash). Re-shot dark: now light-indigo,
   clearly readable.
2. **should-fix (a11y)** — SlashPopover active-row selection affordance too weak in
   dark (bg-accent step alone). **Fixed →** active row pairs `bg-accent` with
   `text-accent-foreground`; the title drops its hard-coded `text-foreground` and
   inherits, so its colour flips on selection — a clear affordance + AA in both themes.
3. **should-fix (correctness)** — `handleDismiss` fired `recordOutcome` (async)
   un-awaited inside a sync try/catch → possible unhandled rejection. **Fixed →**
   explicit `void recordOutcome(...).catch(() => {})` fire-and-forget.

After the fixes: svelte-check 0, eslint clean, Cypress 4/4 re-run on the rebuilt
bundle, after-screenshots refreshed.

## Cypress (deterministic, intercept-driven)

`autocompleteSkills` / `enhance` / `recordOutcome` stubbed; `/lq-ai/chats?id=…`
with an empty-message chat so the composer is the surface under test.

1. **SlashPopover listbox a11y** — `role=listbox[aria-label="Skill suggestions"]`;
   `aria-activedescendant` starts at `lq-slash-row-0`, advances on ArrowDown
   (`row-0 → row-1`), **wraps** (`row-2 → row-0`); the active row carries
   `aria-selected="true"`; Escape dismisses. (The composer keeps focus; the
   popover's `<svelte:window on:keydown>` owns the arrows — logic frozen, only
   tokens changed.)
2. **EnhancePromptExpansion** — ✨ click → panel shows the Original/Enhanced
   diff (both columns), the three action buttons, and the Tier-4 pill.
3–4. **Screenshots** — one page load per surface, theme + viewport toggled live
   (a multi-`cy.visit` loop outlived the access-token TTL and got redirected to
   /login mid-capture — single-load is the robust fix).

## Screenshots (before/after, light+dark, wide+narrow)

`before-r7-{slash,enhance}-{light,dark}-{wide,narrow}.png` (8),
`after-r7-{slash,enhance}-{light,dark}-{wide,narrow}.png` (8).

- **Enhance, wide (light+dark):** the legacy teal/sage palette is gone — "Use
  enhanced" is now the scarce indigo `bg-primary`; the Enhanced card is
  `bg-accent` + `border-primary/40` with an indigo `text-primary` label; "Edit
  enhanced"/"Keep original" are neutral `outline`/`ghost` (hierarchy: one primary
  action). The amber JIT tip strip reads in both themes (`text-amber-700` /
  `dark:text-amber-300`). Original card faded (`opacity-60`).
- **Slash, wide (light+dark):** panel on `bg-popover` with `shadow-md`; active
  row `bg-accent` (soft indigo wash, normal ink), readable in charcoal dark.
- **Narrow (760px):** the satellite components render their semantic tokens
  correctly, but the surrounding **legacy ChatPanel shell** is a non-responsive
  flex row that squeezes the `flex-1` composer column at this width (sidebar +
  Attached-files panel). That cramped shell is **R9's** deliverable (responsive
  parity), explicitly out of scope for R7 (a satellite/popover slice). The
  before narrows show the same squeeze — no regression introduced here.

## Code simplification (discipline 2)

- SlashPopover: entire `<style>` block deleted (≈100 lines); utility classes only.
- EnhancePromptExpansion: entire `<style>` deleted (≈200 lines) incl. the three
  hand-rolled button families (`.lq-btn-primary/secondary/ghost`) → shadcn
  `Button`, the `lq-spin` keyframes → `animate-spin`, the local `.lq-text-caption`
  redefinition → `text-xs text-muted-foreground`, and one fewer `practice.css`
  importer. Converted to Svelte 5 runes (the precondition for `Button`'s
  `onclick` to forward).
