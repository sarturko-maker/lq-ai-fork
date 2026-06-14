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

The internal lab at `/lq-ai/_ae-lab` (unadvertised, auth-gated, dev scratch — links nowhere, changes no
live surface) renders these for visual + interaction checks.
