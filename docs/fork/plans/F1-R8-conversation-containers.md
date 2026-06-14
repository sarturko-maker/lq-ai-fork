# Plan — R8: Conversation containers (+ chat-shell responsive collapse)

Slice **R8** of the legacy `--lq-*` → semantic-token design rollout
(`F1-legacy-design-rollout-decomposition.md`). One PR, ≤200k session.

## Goal

1. Migrate the four conversation-container leaf components off the `--lq-*` system onto the
   shipped semantic tokens (cockpit idiom), reusing the R1a/R6/R7 kit.
2. **Shell-slice responsive parity (maintainer directive, decided this slice):** add the
   cockpit's collapse-on-narrow behaviour to the chat workspace. The collapse mechanism lives
   in `ChatPanel.svelte`'s **layout region** (R9 still owns ChatPanel's token/composition swap —
   this slice touches only the layout shell + adds responsive state, **no `var(--lq-)` change in
   ChatPanel**). Maintainer chose "R8 absorbs chat-shell collapse" over deferring to R9.

| File | `var(--lq-)` before | After |
|---|---|---|
| `C/ChatSidebar.svelte` | 17 | **0** |
| `C/AttachedFilesPanel.svelte` | 9 | **0** |
| `C/MessageOverflowMenu.svelte` | 8 | **0** |
| `C/AttachedSkillPill.svelte` | 7 | **0** |
| `C/ChatPanel.svelte` | 15 | **15** (untouched tokens — layout-region edits only; R9 owns its tokens) |

## Non-goals
- ChatPanel's `<style>`/`var(--lq-)` token migration + composer/picker composition → **R9**.
- `SavedPromptsPanel` (19) → **R20** (coverage table is canonical; the R8 slice-prose mention is
  superseded). `MessageList` is already **0** `var(--lq-)` (no work).
- Wiring `AttachedSkillPill` into the live composer (it is currently mounted **nowhere** — verified:
  no `<AttachedSkillPill>` consumer; the SkillWizardSection/SlashPopover refs are comments). Token
  migration only; visual captured via a throwaway harness (below).
- `ReceiptsDrawer` (already a drawer; not an R8 file) — left as-is inside the shell.

## Approach

### Responsive shell — added to ChatPanel layout region (Svelte 4, no runes conversion)
Mirror `cockpit/Cockpit.svelte` exactly (the exemplar):
- `<svelte:window bind:innerWidth={viewportWidth} on:keydown={onShellKey} />`; `$: isNarrow = viewportWidth < 880`.
- `import { motionMs } from '$lib/lq-ai/cockpit/helpers'` (shared motion gate); `import { fade } from 'svelte/transition'`.
- Single instance of each pane (no remount/duplication): a reactive class string switches the
  sidebar/files wrappers between **inline flex child** (wide) and **off-canvas drawer** (narrow),
  sliding via `transition-transform duration-200 ease-out motion-reduce:transition-none`
  (CSS transform, reduced-motion-safe). Scrim = one conditional `<button>` with
  `transition:fade={{ duration: motionMs(120) }}`, `bg-foreground/20` (tokenised wash, never black),
  closes drawers; Escape closes drawers.
- Shell root gains `relative` for the absolute drawers/scrim.
- Wide (≥880): sidebar inline (`w-72`), conversation `flex-1`, files panel inline (`w-72`) when
  `activeChat` — current behaviour, un-broken.
- Narrow (<880): sidebar → **left** drawer (`-translate-x-full` when closed); files panel → **right**
  drawer (`translate-x-full` when closed); both `z-40`, `bg-background shadow-lg`, share one scrim
  (opening one closes the other). Toggles in the chat header: a **☰** (left, nav) and a **Files**
  toggle (right, when `activeChat`), shadcn `Button variant="ghost" size="icon-sm"`/`"sm"`,
  `onclick` prop form, shown only `{#if isNarrow}`.
- data-testids added: `lq-ai-nav-toggle`, `lq-ai-files-toggle`, `lq-ai-chat-scrim`,
  `lq-ai-sidebar-drawer`, `lq-ai-files-drawer`. Existing testids (`lq-ai-chat-shell`,
  `lq-ai-chat-sidebar`, `lq-ai-attached-files-panel`, `lq-ai-chat-header`) preserved.

### ChatSidebar (→ Svelte 5 runes + semantic tokens)
- `export let` → `$props()`; checkbox `bind:checked` → `checked={archivedToggle}
  onchange={(e) => onToggleArchived(e.currentTarget.checked)}` (source of truth is the parent —
  behaviour-equivalent). Delete `<style>` (+ `@import practice.css`).
- aside → `w-72 flex flex-col bg-muted/40 border-r border-border` (ConversationHost list-pane idiom).
- `.lq-btn-primary` "+ New Chat" → shadcn `<Button class="w-full" onclick={onNewChat}>`.
- section label → `px-3 py-2 flex items-center justify-between text-xs text-muted-foreground border-b border-border`.
- project row → `block w-full text-left rounded-sm px-3 py-1 text-xs uppercase tracking-wider
  transition-colors duration-150`; inactive `text-muted-foreground hover:bg-muted/60`,
  active `text-primary font-semibold` (no accent bg under it → AA-safe).
- chat row → `block w-full text-left rounded-md px-3 py-1.5 text-sm transition-colors duration-150 ease-out`;
  inactive `text-foreground hover:bg-muted/60`, active `bg-accent text-accent-foreground font-medium`
  (cockpit selected idiom; drops the legacy accent border-left — deliberate simplification toward the exemplar).
- PRIVILEGED badge `bg-rose-100 text-rose-700` → dark-safe `bg-rose-500/10 text-rose-700 dark:text-rose-300`
  (opportunistic dark-mode fix; was light-only).
- empty hint → `text-muted-foreground`.

### AttachedFilesPanel (→ Svelte 5 runes + semantic tokens + UploadChip)
- `export let` → `$props()`. Delete `<style>`.
- section → `w-72 flex flex-col gap-3 overflow-y-auto border-l border-border bg-card p-3`.
- headings `text-foreground` / `text-muted-foreground`.
- `.lq-btn-secondary` "+ Files" → shadcn `<Button variant="outline" size="sm" onclick={() => fileInput?.click()} disabled={uploading}>`.
- `statusBadge()` tones → dark-safe: ready `bg-emerald-500/10 text-emerald-700 dark:text-emerald-300`,
  processing `bg-amber-500/10 text-amber-700 dark:text-amber-300`,
  failed `bg-destructive/10 text-destructive dark:text-red-300`, pending `bg-muted text-muted-foreground`.
- **Extract `primitives/UploadChip.svelte`** (runes; the slice's simplification deliverable):
  one file row — name (truncate+title), status badge, KB size, ingestion-error line, and a detach
  `<Button variant="ghost" size="icon-sm">×`-style affordance when `!readonly`. Consumed for both
  `chatFiles` (detachable) and `projectFiles` (`readonly`). Preserves `lq-ai-detach-{id}` testid.

### MessageOverflowMenu (stays Svelte 4; plain semantic buttons)
- Keep ALL logic (focusout microtask defer, Escape, `bind:this` DOM refs, `hasItems`). Delete `<style>`.
- `.overflow` → `relative inline-block`. `.trigger` ⋯ → `rounded-sm px-2 py-1 text-base leading-none
  text-muted-foreground transition-colors hover:bg-muted hover:text-foreground`. `.menu` →
  `absolute right-0 top-full z-10 mt-1 min-w-[180px] rounded-md border border-border bg-popover py-1
  shadow-md`. menu button → `w-full px-3 py-1.5 text-left text-sm text-popover-foreground
  transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40`. Keep both testids.
- (Plain `<button>` not shadcn: the trigger needs `bind:this` to the DOM node for `.focus()`; a runes
  Button `bind:ref` across a Svelte-4 parent is the risk we avoid.)

### AttachedSkillPill (stays Svelte 4; keep module helpers)
- Keep `<script context="module">` helpers byte-for-byte (vitest imports them). Delete `<style>`.
- pill → `inline-flex items-center gap-1 rounded-full border border-border bg-accent px-2 py-0.5
  text-xs font-medium text-accent-foreground` (`text-accent-foreground` ink on the accent wash — R7
  gotcha l). `×` remove → `ml-0.5 rounded-sm px-0.5 leading-none opacity-60 transition-opacity
  hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2
  focus-visible:ring-ring`. Keep `role="status"`, `aria-label`, `on:click`.

## Simplify (discipline 2)
- 5 `<style>` blocks deleted (4 components + ChatPanel keeps its style for R9). Three `lq-btn-*`
  literals (ChatSidebar primary, AttachedFilesPanel secondary) → shadcn Button.
- `primitives/UploadChip.svelte` collapses the duplicated chat-file / project-file row markup into one.
- Single-instance drawer pattern (no pane duplication) in ChatPanel.

## Verification (ADR-F005 gate)
1. `cd web && npm run check` (0) + `npx vitest run` (AttachedSkillPill helper specs stay green; counts in PR).
2. New `cypress/e2e/r8-conversation-containers.cy.ts` — deterministic intercepts (R7 idiom):
   chat list (incl. a **privileged** project), messages (incl. an assistant message), attached files
   (ready/processing/failed statuses), new-chat POST. Asserts: New-Chat shadcn Button fires
   `createNewChat` (proves Svelte-4→runes Button `onclick` forward); chat-row select; archived toggle;
   detach; **responsive collapse** — at 760px the sidebar is off-canvas, ☰ opens the drawer + scrim,
   Files toggle opens the right drawer, scrim/Escape close. Phase-tagged screenshots, one page load.
3. Throwaway harness `routes/_r8harness/+page.svelte` (NOT committed) renders AttachedSkillPill
   (icon/no-icon) + MessageOverflowMenu (clicked open) for isolated light/dark capture; removed before commit.
4. Screenshot evidence `docs/fork/evidence/r8/` — before/after, light+dark, wide+narrow; **narrow MUST
   show the COLLAPSE** (drawer + scrim), not just an un-broken wide layout (shell-slice DoD).
5. CI green (3 jobs).
6. Fresh-context adversarial review (Workflow) — focus: scroll anchoring, upload-cancel/detach removal,
   drawer focus/Escape/scrim a11y, **collapse-matches-cockpit**, Svelte-4↔runes Button `onclick`
   forward, dark contrast on `bg-accent`/`bg-muted/40`/status badges, no lost states across panes.
7. HANDOFF.md overwritten → NEXT = R9 (now token/composition only; responsive shell done here).
