# `ai-elements/` — vendored AI Elements component source (ADR-F011)

Source we own — the same model as `src/lib/components/ui/*` (shadcn-svelte). These components
give the LQ.AI conversation + agent surfaces the **Vercel AI Elements** look (document-style
responses, polished streaming, hover actions, collapsible tool/task/source cards) **on Svelte** —
no React rewrite. See `docs/adr/F011-ai-elements-design-adoption.md`.

## Provenance

Vendored from the **MIT-licensed** Svelte port [`SikandarJODD/ai-elements`](https://github.com/SikandarJODD/ai-elements)
("Svelte AI Elements"), distributed as a **shadcn-svelte registry** at
`https://svelte-ai-elements.vercel.app/r/<component>.json`. Each component's registry JSON was
**inspected before vendoring** (dependencies / registryDependencies / source), then copied here with:

- the CLI alias placeholders substituted for our real aliases
  (`$COMPONENTS$` → `$lib/components`, `$UTILS$` → `$lib/utils`); and
- house formatting applied (these are owned source, not held byte-diffable against upstream — unlike
  `ui/*`, the AE series is expected to be re-tokened and re-wired as it lands).

Recorded in `NOTICES.md` § "Web client provenance". MIT requires the copyright + permission notice be
preserved — it travels with the upstream `LICENSE` (linked above) and the NOTICES row.

## Token-remap convention (the AE0 finding)

The port is built on **the same shadcn-svelte token system we already run** (Tailwind v4 + bits-ui +
the semantic palette `--background/foreground/card/muted/accent/primary/secondary/border/input/ring/
popover/destructive` and their `-foreground` pairs). So the remap is **mostly identity** — a vendored
component's `bg-background`, `text-muted-foreground`, `border-border`, `rounded-lg`, `shadow-sm` etc.
resolve through *our* tokens unchanged. Re-tokening rules when porting a component:

1. **Born `0 var(--lq-)`.** Vendored components must never reference the legacy `--lq-*` layer, so they
   do not regress the R-LAST deletion gate. (Loader + Suggestion use no color token at all — Loader is
   `currentColor`; Suggestion delegates color to our `Button`/`ScrollArea`.)
2. **No hardcoded hex / named colors.** Map any literal to the nearest semantic token. (Watch for
   `bg-white`/`text-black`/`zinc-*` — none in the two AE0 components.)
3. **Tokens the port introduces that we don't have** → add to `app.css` `@theme` deliberately, or map to
   an existing token. None needed so far; our palette is a superset.
4. **Keep our hardened sink.** Any component that renders model markdown must route through
   `renderModelMarkdown` (`marked` + `DOMPurify`, media-forbid) — adopt the *prose styling*, replace the
   *renderer*. Any `{@html}` in a vendored component is a per-slice security item. (Neither AE0 component
   has `{@html}`.)

## Transport stays ours

These are **pure presentation**. We do **not** adopt `@ai-sdk/svelte`'s `Chat` — components are fed by
our existing message store / custom SSE frames / Citation Engine / agent steps, behind the Inference
Gateway + `guarded_tool_call` + audit (CLAUDE.md "KEEP unchanged").

## Inventory

| Component | Upstream deps | Our deps | Notes |
|---|---|---|---|
| `loader/` | none | none | Pure inline SVG spinner (`currentColor` + `animate-spin`). |
| `suggestion/` | `button` (registry) | `ui/button`, `ui/scroll-area`, `cn` | Chip (`Suggestion`) + horizontal scroller (`Suggestions`). Upstream item under-declares `scroll-area` as a registry dep — already present here. |
| `conversation/` | `@lucide/svelte`, `runed`, `button` | `ui/button`, `cn`, `@lucide/svelte`, `runed` | AE1. Scroll container (`Conversation`) + scroller (`ConversationContent`) + sticky scroll-to-bottom (`ConversationScrollButton`) + `EmptyState`, backed by a runes `StickToBottomContext` (observers auto-scroll on append unless the user scrolled up). **Fix:** upstream `conversation-content.svelte` bound BOTH `element` and `ref` to one `<div>` (two `bind:this` = a Svelte 5 compile error) — we bind `ref` only and register it as the scroll element. No new deps (lucide ^1.17 ⊇ item's ^1.16; runed already transitive). |
| `message/` (core + actions) | (full block pulls `streamdown-svelte`, `mode-watcher`, `@shikijs/themes`) | `cn`, `ui/button`, `ui/tooltip`, `@lucide/svelte` | AE1 core + **AE2 `actions/`**. Core: `core/message.svelte` + `core/message-content.svelte` (identity: user `bg-secondary` soft right bubble, assistant plain full-width `text-foreground`). AE2 added `actions/{message-action,message-actions,message-toolbar}.svelte` — the hover toolbar (`MessageAction` = ghost icon-button + tooltip + sr-only label; deps `ui/button`+`ui/tooltip` both already present). Wired in `MessageActionsBar.svelte` (a runes wrapper — see below) as Copy / Retry / Copy-sources. **NOT vendored:** the upstream `response/` (a `streamdown-svelte` wrapper — we keep `renderModelMarkdown`), `branching/`, `attachments/`. `context/message-context.svelte.ts` trimmed to the shared types. |
| `reasoning/` (**not vendored — option-2**) | `streamdown-svelte`, `@shikijs/themes`, `mode-watcher`, `runed`, + `collapsible` & `./response.json` (registry) | — | AE2. The AE `reasoning` block pulls four deps we avoid plus a `collapsible` we don't ship and the Streamdown `Response` sink. Per **ADR-F011 option-2** ("hand-build on shadcn for any weak component") the AE Reasoning *identity* (brain icon, rotating chevron, "Thinking…" shimmer, "Thought for Ns", auto-open-while-streaming + one-shot auto-collapse) was hand-built onto our existing accessible `<details>` `primitives/ReasoningRibbon.svelte` — zero new deps, keeps the sanitized slot. |
| `sources/` (`Source` vendored; `Sources` **option-2**) | `@lucide/svelte`, + `collapsible` (registry) | `cn`, `@lucide/svelte` | AE3. `source.svelte` vendored faithfully (book-icon entry; `href` made optional → non-navigating `<span>` for our internal docs, viewer is M2-D2). `sources.svelte` is **option-2**: the upstream Sources/SourcesTrigger/SourcesContent trio sits on shadcn `collapsible` (not shipped — same dep dodged for `reasoning/`), so the trio is collapsed into one component on the native `<details>` (trigger = `<summary>` "Used N sources" + rotating chevron; content snippet = body). Zero new deps. |
| `inline-citation/` (2 of N primitives vendored; **option-2**) | `@lucide/svelte`, + `badge`, `carousel`, `hover-card` (registry) | `cn` | AE3. Only the two dependency-free primitives this slice uses are vendored — `inline-citation-source` (name/meta block) + `inline-citation-quote` (cited passage), each needs just `cn`. The block's heavier pieces (the hover-card `Card` + the embla `Carousel`, ~12 files) and the `inline-citation`/`-text` prose-wrappers pull `hover-card` + `carousel` registry deps we don't ship and aren't needed: our Sources card is a static disclosure, not a hover carousel (**option-2** + AE0 "take only what you need"). Used by `MessageSources.svelte` for the per-source name/meta/quote styling. |

**`response` deliberately not vendored:** the registry `response` item is a thin wrapper over
`streamdown-svelte` (its own markdown renderer + Shiki). Per ADR-F011 we keep our hardened
`renderModelMarkdown` (`marked`+`DOMPurify`, media-forbid) and adopt only the *prose styling* (the
`prose prose-sm dark:prose-invert` wrapper in `MessageBubble`).

**`code` deliberately not vendored (AE4, option-2):** the registry `code` item pulls `svelte-toolbelt`,
a separate `copy-button` registry item, `runed` Context, and line-number/overflow machinery, and exposes
a controlled-`code`-prop API that doesn't fit our `renderModelMarkdown` → single `{@html}` sink (we do
NOT split markdown into a streamdown-style Response). Per **ADR-F011 option-2** the AE code-block
identity (bordered card, language header, copy button, Shiki GitHub light/dark dual-theme) is hand-built
in **`web/src/lib/lq-ai/code/`** as a Svelte action (`enhanceCodeBlocks`) that post-processes the
already-sanitized `<pre><code>` output — mirroring `citations/decorate-inline.ts`. The one new runtime
dep `shiki` lands there (its only home); highlight runs on already-sanitized `.textContent` and Shiki's
output is re-sanitized with DOMPurify before re-entering the DOM. See `NOTICES.md` § Web client
provenance.

**`prompt-input` deliberately not vendored (AE5, option-2):** the registry `prompt-input` item pulls
`ai@^6` (the Vercel AI SDK transport we explicitly reject — it bypasses our gateway/SSE/`guarded_tool_call`),
`runed`, six registry deps (`aspect-ratio`/`button`/`dialog`/`dropdown-menu`/`textarea`/`tooltip`) and
23 files of SDK-bound `Controller`/context machinery. Per **ADR-F011 option-2** the AE **Prompt Input**
identity (one unified `rounded-xl border shadow-sm` shell holding the textarea + a bottom toolbar — model
selector + attach/enhance/receipts tools on the left, submit/stop on the right) is hand-built directly on
our existing composer in **`ChatPanel.svelte`** (KEEP `SlashPopover` + `EnhancePromptExpansion` + the
gateway/SSE send path; lucide toolbar icons replace the prior emoji). The same slice migrated ChatPanel's
header + composer off the legacy `--lq-*` tokens to semantic tokens, fixing the standing dark-mode
chat-column gap. Zero new deps. No lab section — the composer is inherently the live chat surface.

**`tool` / `task` deliberately not vendored (AE6, option-2):** the registry `tool` item pulls
`collapsible` + `badge` + `runed` + `./code.json` (the AE code block we hand-built in AE4, NOT vendored),
and `task` pulls `collapsible` + `bits-ui` — `collapsible` is the same shadcn registry component dodged
for `reasoning`/`sources`. Per **ADR-F011 option-2** the AE **Tool** card (wrench header + tool name +
status badge + collapsible Parameters/Result) and the **Task** step list (search-glyph trigger + a single
left rail) are hand-built on native `<details>` directly in `ConversationPanel.svelte` — the call/result
pair into one card via the pure `groupTurnSteps` helper (presentational only; the settled step record and
all polling/staleness/`statusBadge` logic are untouched). The same slice converged `ConversationPanel`
**and** `SkillSourceView` off their local `marked`+`DOMPurify` copies onto the shared `renderModelMarkdown`
sink. No new deps; no `_ae-lab` section — the timeline is inherently the live agent surface.

**`suggestion` reused as-is, backed by an honest source (AE7, the AE-series closer):** the AE0-vendored
`suggestion/` (`Suggestion`/`Suggestions`) is rendered in `ChatPanel.svelte` as empty-conversation
**starter chips** — shown only when the conversation has no messages AND the user has saved prompts. They
are backed by the caller's own `SavedPrompts` (an honest, user-owned data source) surfaced from
`SavedPromptsPanel`'s single existing fetch via a new `onPromptsLoaded` callback (no duplicate request);
the chip label is the prompt name and clicking fills the composer with its body (shared
`insertIntoComposer` helper). They are **not** model-invented follow-ups — no honest source for those
exists, so none are shown (an empty saved-prompts list renders no chips). No new deps. **With AE7 the
AE-series closes (AE0–AE7 done).**

The internal lab at `/lq-ai/_ae-lab` (unadvertised, auth-gated, dev scratch — links nowhere, changes no
live surface) renders the trivial primitives (Loader, Suggestion) plus the AE2 Reasoning ribbon (with a
streaming toggle so the shimmer + duration + auto-collapse path — dormant on the live chat surface until
F1-S4 wires reasoning deltas — is visible + testable), the message actions bar, and the **AE3 Sources
card** (three documents with mixed verification states), and the **AE4 code blocks** (four fences —
python, sql, an unsupported `cobol` → plain text, and a no-language block whose body holds a literal
`<script>` to prove the escaped-text → highlight pipeline is injection-safe), for visual + interaction
checks. The conversation/message primitives + the Sources card + the code-block action are also
exercised on the live chat surface (`MessageList`/`MessageBubble` → `MessageSources` /
`use:enhanceCodeBlocks`).
