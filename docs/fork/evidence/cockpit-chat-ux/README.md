# Evidence — Cockpit chat-UX render polish

Slice `fork/cockpit-chat-ux`. Two web-only fixes (maintainer steer at end of C9):
**(1)** dark-mode markdown parity for the agent answer (tables); **(2)** quieter tool calls.

## The diagnosis (why the "fix gfm" hypothesis was wrong)

`marked` is **9.1.6**; `gfm` already defaults `true`. The exact production call
`marked.parse(raw, {async:false, breaks:false})` on the **real** model output (pulled from `agent_runs`)
already emits `<table>…</table>`, and DOMPurify's media-forbid policy does not strip table tags. So the
`<table>` was always in the DOM — the defect was **CSS**.

## The real bug + fix (sub-goal 1)

The agent-surface prose containers omitted `dark:prose-invert` (`MessageBubble:185` had it;
`ConversationPanel:860/874/881`, `StepRow:85`, `AreaConfigDisclosure:45` did not). In dark mode prose then
uses light-mode tokens (dark text) on the charcoal page; the settled answer sits on `.ag-answer` which has
no background, so its table renders dark-on-charcoal — "doesn't render." Live thinking escaped because
`.ag-thinking-live__tail` paints a `--color-muted` panel. Fix: add `dark:prose-invert` to those five
containers.

## Screenshots

These are rendered against the **production compiled CSS** (extracted from the running `web` container,
`_app/immutable/assets/0.*.css`) with the **real** model answer HTML — i.e. the exact bytes the browser
uses, only the one class string varied.

- `dark-answer-table-before-after.png` — the proof. **BEFORE** (`prose prose-sm`): table illegible
  (dark-on-charcoal). **AFTER** (`prose prose-sm dark:prose-invert`): crisp, legible table.
- `tables-light-all-surfaces.png` — light mode is unaffected: tables already render correctly everywhere.
- `tables-dark-before-fix.png` — dark mode before the fix, showing the agent answer (no invert, broken)
  vs the chat answer (with invert, fine) side by side — the asymmetry that was the bug.

## Sub-goal 2 (quieter tool calls)

Unit-tested in `web/src/lib/lq-ai/agents/__tests__/helpers.test.ts`: the Commercial tools
(`apply_redline`, `preview_redline`) now carry curated plain-language titles, and any unmapped tool is
humanised (`surprise_tool` → "Surprise tool…") so a collapsed tool row never shows a raw identifier. Icons
shrunk `size-4`→`size-3` (wrench) / `size-3.5` (chevron). Raw params/JSON stay behind the `<details>`
expander (unchanged).

## Not in this slice

Redline **download** affordance → **C7** (the redlined file is deliberately unattached work product, so a
clean discoverable download needs C7's structured artifact reference). See the plan
`docs/fork/plans/cockpit-chat-ux-render-polish.md`.
