# Plan — Cockpit chat-UX render polish (dark-mode markdown + quieter tool calls)

**Slice:** `fork/cockpit-chat-ux` · **Type:** web-only presentational fix · **ADR:** none (no
architectural call — presentation only) · **Cadence:** plan-first (this doc), then implement.

## Context

Maintainer steer at the end of C9 (live Commercial UAT), verbatim:

> "proper markdown should be rendered in the chat - this renders in thinking, but when tables are shown
> to user, these don't render for some reason. We also need to think about how to make tool icons smaller
> and hide some of the random text behind the tool expansion button. we are transparent, but by default
> users should just see plain language text of what the model is doing."

Two web-only asks: (1) the user-facing answer must render markdown (esp. **tables**) the way the thinking
stream does; (2) tool calls should read as plain language by default, with raw detail behind the expander.

## Diagnosis (verified, not assumed)

A map workflow's five readers all proposed the same fix — "add `gfm:true` to `marked.parse()`." **That is
wrong**, proven three ways:

- `marked` is **9.1.6**; `gfm` already defaults `true`. Running the *exact* production call
  `marked.parse(raw, {async:false, breaks:false})` on the real model output (pulled from `agent_runs`)
  emits full `<table><thead>…</tbody></table>`. Adding `gfm:true` is a **no-op**.
- DOMPurify's media-forbid policy (`sanitize-markdown.ts:18`) does **not** forbid table tags — they
  survive sanitisation.
- The answer and the thinking stream call the **same** `renderModelMarkdown` sink, so they receive
  byte-identical table HTML.

**So the `<table>` is in the DOM; the defect is CSS.** Headless screenshots (real table HTML rendered
against the *compiled* container CSS, light + dark) pin it exactly:

- The compiled CSS **has** full `.prose table/thead/td` typography styling. In **light mode tables render
  correctly** on every surface.
- In **dark mode** the agent surface breaks: `MessageBubble` answer uses
  `prose prose-sm dark:prose-invert` (`:185`), but every **agent-surface** prose container omits
  `dark:prose-invert` (`ConversationPanel:860,874,881`, `StepRow:85`, `AreaConfigDisclosure:45`). Without
  the invert, prose uses **light-mode tokens** (dark-grey text, near-white borders) on the **charcoal**
  page. The settled answer sits on `.ag-answer` which has **no background** (`ConversationPanel:1512`), so
  its table is dark-text-on-charcoal — looks "unrendered." The **live thinking** escapes because
  `.ag-thinking-live__tail` paints a `--color-muted` panel (`:1489`) that keeps text legible. That is
  *exactly* "renders in thinking, but the answer's table doesn't."

Tool calls (`StepRow.svelte`): the collapsed `<summary>` already shows only a plain-language title +
status, and raw args/output are already inside the `<details>`. Two gaps: (a) icons are `size-4` (16px);
(b) the title falls back to `Calling ${name}…` for tools not in `TOOL_CALL_TITLES` (`helpers.ts:249`) — so
a Commercial run shows raw identifiers like **"Calling apply_redline…"** by default.

## Goals

1. **Dark-mode markdown parity.** The user-facing answer (and all agent-surface model output) renders
   markdown — including tables — with the same contrast in dark mode as the chat answer / thinking stream.
2. **Quieter tool calls.** Smaller icons; every tool reads as plain language by default (no raw
   `snake_case` identifiers); raw params/JSON stay behind the expander (already true — keep it).

## Non-goals

- **No new dependency** (reject the `gfm`/remark suggestion — `marked` already does GFM).
- **No change to the markdown sink or the `{@html}` boundary** — `renderModelMarkdown` stays the single
  hardened sanitiser; this slice adds **zero** new `{@html}` and zero XSS surface.
- **No new SSE frames / backend changes.** Titles stay client-side (`TOOL_CALL_TITLES`); the honest record
  (raw name + args in the step) is untouched.
- **Redline download affordance → DEFERRED to C7.** The redlined file is created `project_id`-scoped but
  **deliberately not attached** ("work product, not a search source" — `commercial_tools.py:350`), so it
  never appears in `MatterRailFiles` (which lists only `attached_file_ids`, `:22`). A clean, discoverable
  download needs a structured artifact reference on the step/answer — that *is* C7's "redline download UI."
  A files-panel download or a tool-result link would either change attach semantics or rely on fragile
  message parsing; out of scope for a minimal render-polish slice. (Task #226 → moved under C7.)

## Files to change

**Sub-goal 1 — dark-mode parity (add `dark:prose-invert`, matching `MessageBubble:185`):**
- `web/src/lib/lq-ai/components/agents/ConversationPanel.svelte` — `:860` (live reasoning), `:874`
  (settled reasoning), `:881` (settled answer).
- `web/src/lib/lq-ai/components/agents/StepRow.svelte` — `:85` (settled reasoning body).
- `web/src/lib/lq-ai/cockpit/AreaConfigDisclosure.svelte` — `:45` (consistency).

**Sub-goal 2 — quieter tool calls:**
- `web/src/lib/lq-ai/components/agents/StepRow.svelte` — wrench icon `size-4`→`size-3` (`:48`); chevron
  `size-4`→`size-3.5` (`:62`); harmonise `.ag-tool__*` spacing if needed.
- `web/src/lib/lq-ai/agents/helpers.ts` — add `apply_redline` / `preview_redline` to `TOOL_CALL_TITLES`;
  humanise the fallback (`Calling ${name}…` → Title-Cased `${humanize(name)}…`) in `stepDisplay` and the
  `toolLabel` fallback so no raw identifier ever shows by default.

**Tests:**
- `web/src/lib/lq-ai/__tests__/sanitize-markdown.test.ts` (new or extend) — assert
  `renderModelMarkdown('| a | b |\n|---|---|\n| 1 | 2 |')` contains `<table>` and `<td>` (regression guard
  for the parser/sanitiser, even though it's already correct).
- `web/src/lib/lq-ai/agents/__tests__/helpers.test.ts` — update the `surprise_tool` fallback assertions
  (`:270,283`) to the humanised form; add cases for `apply_redline`/`preview_redline` titles.

## Verification (DoD)

- `cd web && npm run check` (0 errors) + `npx vitest run` — output shown.
- Rebuild the `web` container (serves a pre-built bundle).
- Headed before/after screenshots (`DISPLAY=:0`, electron) of a Commercial agent run with a **table** in
  the answer, **light + dark × wide + narrow**, into `docs/fork/evidence/cockpit-chat-ux/`: dark answer
  table now legible; tool rows show plain-language titles + small icons collapsed, raw JSON only after
  expand; light mode unchanged.
- Fresh-context adversarial + **security** (confirm no new `{@html}`/dep/XSS; sink untouched) +
  simplification review.
- `HANDOFF.md` updated; merge per ADR-F005 against `sarturko-maker/lq-ai-fork`.

## Risk / reversibility

Lowest-risk class of change: each fix is one CSS class token or a string-map entry. Fully reversible. No
backend, no schema, no dependency, no new sink. The dark-mode fix is the real bug; the tool-title/icon
changes are polish. Light mode is provably unaffected (typography table styles already present).
