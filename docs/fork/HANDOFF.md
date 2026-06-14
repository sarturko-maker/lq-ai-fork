# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (end of R8 — conversation containers + chat-shell responsive collapse)

- **R8 on branch `f1-r8-conversation-containers`** (PR pending to
  `sarturko-maker/lq-ai-fork`). Slice of the legacy `--lq-*` → semantic-token design
  rollout (full plan: `docs/fork/plans/F1-legacy-design-rollout-decomposition.md`).
- Dev stack: 8 services healthy; **DB at 0054**; web rebuilt on R8 + review fixes.
  Login: http://localhost:3000/lq-ai/login · admin@lq.ai / LQ-AI-local-Pw1!
  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched
  files); **vitest 803**; **Cypress `r8-conversation-containers.cy.ts` 6/6** headed/live.
  Evidence: `docs/fork/evidence/r8/` (before/after × wide/narrow × light/dark, 8 PNGs).
  Adversarial review (Workflow, 13 agents): 9 raw → **8 confirmed (0 blocker, 2 should-fix,
  6 nit); ALL actioned** (security pass CLEAN — see below).

### SECURITY INCIDENT (2026-06-14) — RESOLVED

- `.env.bak-f0-s4` (tracked; `.gitignore` missed it) leaked LIVE `MINIMAX_API_KEY`,
  `JWT_SECRET`, `LQ_AI_GATEWAY_KEY`, Postgres/MinIO/S3 creds to the public repo.
- **Fixed:** all secrets ROTATED + verified live (new MiniMax key in untracked `.env`);
  **PR #56** removed the file + hardened `.gitignore` (`.env.*` + `!.env.example`) + added
  the security-review discipline; **git history rewritten** (filter-repo, force-pushed —
  origin/main AND local have 0 commits with the file). R8 rebased onto the clean main.
- **New per-slice discipline (CLAUDE.md §Definition-of-done + §Merge-policy):** EVERY slice
  gets a security + simplification pass folded into the adversarial review, with a
  pause-and-check. The R8 review honored this — security pass came back clean (no secrets,
  no `@html`/unsafe sinks, all file metadata auto-escaped, no authz surface).

## Done (R8, this slice)

- **4 leaf containers → 0 `var(--lq-)`:** `ChatSidebar` + `AttachedFilesPanel` migrated to
  **Svelte-5 runes** (so shadcn `Button onclick` forwards); `MessageOverflowMenu` +
  `AttachedSkillPill` stay Svelte 4 (token swap + `<style>` deleted). `lq-btn-*` → shadcn
  `Button`. Cockpit list idiom: selected rows `bg-accent text-accent-foreground`,
  hover `hover:bg-muted/60`, sidebar `bg-muted/40`.
- **NEW `primitives/UploadChip.svelte`** (runes) collapses the duplicated file-row markup;
  module-exported `statusTone()` with dark-safe AA tones (now unit-tested — see review fix).
- **Chat-shell responsive collapse (SHELL slice — maintainer directive).** `ChatPanel`
  **layout region only** (stays Svelte 4; its own `--lq-*` tokens are R9's job): below 880px
  the sidebar → left drawer, files → right drawer (computed wrapper class + CSS transform),
  shared scrim `bg-foreground/20` + `transition:fade`/`motionMs`, ☰ + Files header toggles
  (plain Svelte-4 buttons). Mirrors `cockpit/Cockpit.svelte`.
- **Review fixes (all 8 confirmed findings actioned):**
  - *should-fix* — closed off-canvas drawers were still Tab-reachable/SR-announced
    (focus trap). Added **`inert={(isNarrow && !open) || undefined}`** to both drawer wrappers.
  - *should-fix* — active project-filter label `text-primary` on `bg-muted/40` failed AA in
    dark (4.12:1). Now `bg-accent font-semibold text-accent-foreground` (9.08:1 dark) — same
    backing surface as the chat rows.
  - *nit* — drawer dialog semantics: added conditional `role="dialog"` + `aria-label`
    (narrow only) + static `tabindex="-1"` + **focus-on-open** (`await tick(); el.focus()`
    in the toggle handlers). Dropped `aria-modal` (background isn't `inert` — would over-claim).
  - *nit* — `UploadChip` detach `hover:text-destructive` was 4.15:1 dark → added
    `dark:hover:text-red-300`; detach Button `size="sm"` → **`size="xs"`** (closer to the old
    text-link weight).
  - *nit* — added `__tests__/UploadChip.test.ts` (6 tests) locking the AA `dark:` tone lifts.
  - *nit (accept)* — cypress dev-password fallback follows the 8-spec convention (not changed).

## Next slice — pick up exactly here

1. **R9 — ChatPanel token/composition swap ONLY.** The responsive shell is **already done in
   R8**, so R9 is NO LONGER split into R9a/R9b — it's just the token migration of ChatPanel's
   remaining `<style>` block (the `.lq-composer*`, `.lq-btn-send/abort/secondary` rules at
   `ChatPanel.svelte` ~lines 1157-1237, still using `--lq-canvas/text/border/accent/radius`)
   plus the inline `border-gray-200 dark:border-gray-800` / `text-gray-500` / `lq-text-panel-h`
   in the header + composer. Convert the composer buttons to shadcn `Button` (ChatPanel is
   Svelte 4 — it must go **runes** for `onclick` to forward, OR keep plain `<button on:click>`;
   note ChatPanel is large + holds heavy stream logic, so prefer the minimal token swap and
   keep `on:click` rather than a full runes conversion unless clean). **Reuse the R6/R7/R8
   kit:** `text-accent-foreground` on accent washes (NOT `text-primary`), `dark:` lifts on
   destructive text, the `Alert` primitive for `sendError`. Coverage table → R9 row.
   **Backlog (from R6):** converge `ConversationPanel` + `SkillSourceView` onto
   `renderModelMarkdown` in R-CONV-2 / R14a.
2. Other rollout slices (any order — the dark-mode bridge holds un-migrated surfaces):
   Foundation/rail R2–R5, Wave 1 R-CONV-1/2, Wave 2 R12/R13/R14a-b/R15/R15b-tab-pb/R16,
   Wave 3 R17a-b/R18/R19a-b/R20/R-CHROME, cleanup R-TYPO → R-BRIDGE → R-LAST. autonomous
   R21 = SKIP (deferred to F2/F3, stays on bridge). Net ~24 slices left after R8.
3. **F1-S4** (subagent tree + SSE v3-projection adapter) / **F1-S5** (idempotency ledger +
   attribution fan-out) — `docs/fork/plans/F1-replan.md`. **Area skills/subagents ACTIVATION**
   (S9-gated) — wires `composition.py` to pass area skills/subagents + re-runs the S9 matrix.

## Rollout progress (R-series)

- **Step 0 coverage table ✅** (PR #50) — all 101 `var(--lq-)` files assigned; R-LAST gate reachable.
- **R0 ✅** (PR #50) — `validators/matter.ts` (logic-only). **R1a ✅** (PR #51) —
  `primitives/{ModalShell,FormControl,Alert}` + NewMatterModal. **R6 ✅** (PR #52) —
  MessageBubble/`<think>` ribbon + `sanitize-markdown.ts`. **R7 ✅** (PR #55) — SlashPopover +
  EnhancePromptExpansion. **Responsive parity folded in** (PR #53). **CI unblocked** (repo public).
- **R8 ✅ (this slice, PR pending)** — conversation containers + chat-shell responsive collapse.

## Carry-overs / review deferrals

- **R8 deferred-on-record:** focus-on-open is implemented but NOT asserted in Cypress
  (headed-Electron/Xvfb programmatic focus doesn't set `document.activeElement` without OS
  window focus). Drawers are not full focus-traps (cockpit defers this too — partial parity
  is the established bar); ESC + scrim-click + `inert`-on-close cover the practical cases.
- auth/refresh: per-user session cap + web gate timeout SHIPPED (PR #47). REMAINING: the
  **deterministic-HMAC index** (removes the global bcrypt scan + bad-token-spam DoS; needs a
  migration + security review — Backlog).
- F1-S3 deferrals: subagent-spec skill names bypass registry validation (validate on the
  activation slice); `audit_log.practice_area_id` unindexed; area tier floor operator-set
  until a model > tier 4 qualifies.
- ADR-0011 disclosure after F1-S5 attribution. Live SSE token deltas DEAD until a Redis
  pub/sub publisher lands (F1-S4). ADR-0011/F003 conversation memory + compaction → F2.

## Gotchas (carried + new)

- **NEW (R8): chai-jquery subject rebinding** — `.and('have.attr', name[, val])` and
  `.and('not.have.attr', name)` REBIND the chained subject to the attr value/undefined, so a
  following `.and('have.attr', …)` runs on a non-element ("neither DOM nor jQuery"). Put
  multiple attribute checks in ONE `.should(($el) => { expect($el)… })` callback.
- **NEW (R8): `inert` for off-canvas drawers** — a CSS `translate-x-full` only hides
  visually; descendants stay focusable + in the a11y tree. Use `inert={(isNarrow && !open) ||
  undefined}` on the closed wrapper. A DYNAMIC `role={isNarrow ? 'dialog' : undefined}` defeats
  svelte-check's a11y static analysis, so use a **static `tabindex="-1"`** (negative → no
  `a11y_no_noninteractive_tabindex` warning) rather than `tabindex={isNarrow ? -1 : undefined}`.
- **NEW (R8): active row on a translucent wash needs a backing surface for AA** — bare
  `text-primary` over `bg-muted/40` fails AA in dark (4.12:1). Give active rows
  `bg-accent text-accent-foreground` like the chat rows (9.08:1 dark / 11.32:1 light).
- shadcn `Button onclick` only forwards from a **runes** parent (legacy `on:click` = silent
  no-op). `text-primary` on `bg-accent` fails WCAG AA → use **`text-accent-foreground`**.
  `text-destructive` on a tinted bg fails AA in dark → add a **`dark:` lift** (`dark:text-red-300`).
- web CI gates only `npm run check` + vitest (eslint NOT gated). `test:frontend` is vitest
  WATCH mode — run `npx vitest run`. vitest env is `node` (no jsdom) — DOMPurify/sanitisation
  must be Cypress-tested. Long multi-`cy.visit` screenshot loops outlive the token TTL →
  shoot all frames on ONE page load. **headless cypress lies about dark theme — capture headed**
  (`DISPLAY=:0`), and rebuild the `web` container before screenshotting a UI change.
- `gh pr create` defaults to FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork` AND
  `--head <branch>` (ADR-F001). jq NOT installed — parse `gh --json` with python3.
- migrations: NEVER host-side alembic against the live dev DB; api auto-migrates on boot;
  rebuild api+arq-worker+ingest-worker together + web. **NEVER `docker compose down -v`.**
- MiniMax-M3 is tier 4 (weak) — `default_tier_floor` < 4 makes every run 403. Seed areas with
  NO floor. deepagents subagent `model` string = gateway-bypass (ADR-F010 guard at
  `build_deep_agent`). New API endpoints register in tests/test_openapi.py (count assert).
