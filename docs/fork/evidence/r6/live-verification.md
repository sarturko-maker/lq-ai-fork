# R6 — live verification (MessageBubble family + `<think>` reasoning ribbon)

Captured headed (Electron, `DISPLAY=:0`) against the live dev stack on the legacy chat
surface (`/lq-ai/chats`), with a deterministic intercept fixture
(`cypress/e2e/r6-message-bubble.cy.ts`) so BEFORE (pre-R6 bundle) and AFTER (R6 bundle)
render the identical message set for a clean A/B. Fixture exercises every R6 surface in one
chat: a `is_enhanced` user message (✨ ProvenancePill), an assistant message carrying
`<think>…</think>` + a verified citation marker + a Tier-4 badge, and an assistant message
with `error_code` (the error banner).

## The fix, visually

| | BEFORE (`main` @ a2061a1) | AFTER (R6) |
|---|---|---|
| `<think>` reasoning | **leaks as prose** at the top of the assistant bubble ("The user asks whether… controlling language is in §12.3… flag the 6-year limitation…") | **collapsed into a "▸ Reasoning" ribbon**; bubble shows only the clean answer. Expanding the ribbon reveals the reasoning in a muted inset panel (`after-r6-ribbon-expanded.png`) |
| bubble colours | hardcoded palette (`bg-indigo-600`, `bg-white dark:bg-gray-800`, rose error box) | semantic tokens (`bg-primary` / `bg-card` + `border-border` / `bg-muted`; error → R1a `Alert`) — near-identical render, now token-driven (no bridge) |
| ProvenancePill | `--lq-accent/tier/warn-*` `<style>` | semantic `bg-accent`/`bg-muted`/amber tones |

## Files

- `before-r6-{light,dark}-{wide,narrow}.png` — pre-R6 baseline; the `<think>` leak is visible.
- `after-r6-{light,dark}-{wide,narrow}.png` — R6; reasoning collapsed, semantic tokens, AA in dark.
- `after-r6-ribbon-expanded.png` — the ribbon open: reasoning in the muted inset panel, answer below.

## Checks run

- **Cypress (live stack), 2/2 pass** on the R6 bundle:
  - *extracts `<think>` into a collapsed Reasoning ribbon, leaving clean prose* — asserts the
    reasoning text is absent from `[data-testid=lq-ai-message-content]`, present in
    `[data-testid=lq-ai-reasoning-ribbon]`, collapsed by default (`not.have.attr('open')`),
    and revealed on summary click (`have.attr('open')`).
  - *captures the chat surface across themes and widths* — the 5 screenshots above.
  - On the pre-R6 bundle the first test fails (no ribbon) — that IS the bug it documents.
- **svelte-check**: 0 errors (5 pre-existing warnings in unrelated legacy files).
- **vitest**: 797 passing / 76 files (unchanged; ProvenancePill 5, RefusalMessageBubble 3 green).
- **Token deletion**: `ProvenancePill.svelte` + `M2Citations.svelte` at **0 `var(--lq-)`** (R-LAST gate).

## Notes / re-scope (verified on entry)

- MessageBubble itself had **no `var(--lq-)`** and **no `color:white` literal** (the plan's
  "kill color:white" line was inaccurate for this file). TierBadge/TierDetailsPanel already clean.
- The legacy ChatPanel shell is a non-responsive flex row (fixed sidebar + attachments squeeze
  the `flex-1` conversation below ~700px) — that is **R9's** surface, not R6's. The narrow shots
  use 860px so the bubble column (~340–495px) stays visible; the bubbles reflow cleanly there.
- **RefusalMessageBubble deferred to R-CONV-2** (no `var(--lq-)`; conditional refusal surface,
  un-triggerable on the tier-4-only dev stack — can't get an honest live screenshot here).
