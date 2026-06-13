# Plan — Legacy-surface design rollout, decomposed

Status: **draft for maintainer edit** (CLAUDE.md § Iteration: written plan → human edits → implement).
Produced by a map→synthesize→adversarial-critique workflow over the live `web/` surface.
Supersedes the 3-wave sketch in `F1-S2.1-design-iteration-v2.md` §Goals-3 with executable slices.

## Goal

Migrate the entire legacy UI off the `--lq-*` custom-property design system onto the shipped
F1-S2/S2.1 semantic-token system (Tailwind `bg-card`/`text-foreground`/`border-border` + the
`--elevation-*`→`--shadow-*` scale + the `motionMs()` motion gate), per the maintainer design rule
(**light, clean, professional, cutting-edge; never a black background**). The cockpit
(`AreaGrid`/`MattersPanel`/`ConversationHost`/`CockpitHeader`/`StatusPill`/`NewMatterDialog`) is the
**already-migrated exemplar** — copy its idiom; never re-migrate it.

Each slice is vertical, ~one PR, ≤2–3 days, and carries the three disciplines below.

## Scale (measured, not estimated)

`grep -rhoE '\-\-lq-[a-z0-9-]+' src` → **2,843 uses across 103 files**; `grep -rl 'var(--lq-'`
→ **~70 color-token files**. (The S2.1 sketch's "71 components / 1,095 uses" undercounted; S3 grew it.)

## The dark-mode bridge (why slices are order-independent)

`practice.css` `:root.dark` (lines 76–103) maps the 30 legacy tokens onto the charcoal scale, and it
is imported **globally** by `src/routes/lq-ai/+layout.svelte` (lines 23–24) for the whole route tree.
So **every un-migrated surface keeps working dark mode**, and slices can ship in almost any order
without dark-mode breakage. Per-surface migration restores full AA (legacy `--lq-accent` is only
~3:1 in dark). **Consequence (critique fix):** removing a component's local `@import practice.css`
does NOT retire the bridge — the bridge lives in `+layout.svelte`. A dedicated slice (R-BRIDGE) owns
removing the global import; the terminal `--lq-*` deletion (R-LAST) is gated on that + zero consumers.

## Context budget — every slice executes in one ≤200k-token session (operating constraint)

The 1M window works best under ~200k. The constraint is on the **main orchestrating agent per
slice** (subagents — exploration, adversarial review — do NOT count). What accumulates main-context
is iterative edit churn + verify output, not reading. Rules, enforced by sizing:

- **Cap per slice: ≤~6–8 files touched, ≤~1,500–2,000 LOC of edited code.** Split anything bigger.
- **Verify is focused + truncated in the slice loop:** `npx vitest run <file>` / `cypress run --spec
  <one>` piped through `tail`/`grep`. The FULL suite + FULL Cypress run live in CI only (off-context).
- **Push exploration + adversarial review to subagents.** The main agent reads only the files it
  edits + the primitive kit + the exemplar ONCE; never re-reads after an Edit; reads big files in ranges.
- **Compact / write HANDOFF at every slice boundary** so each slice starts near-empty.

This forces three splits beyond the critique's (applied below): **R-CONV → R-CONV-1/-2**,
**R15b → R15b-tab/-pb**, **R14 → R14a/-b**. Slices flagged ⚠ read a >1k-LOC file — read in ranges.

## The three disciplines — baked into EVERY slice (the user's requirement)

Every slice's Definition of Done includes all three. This is the per-slice checklist:

1. **Extensive testing.** Vitest unit tests for any logic touched/extracted; Cypress e2e exercising
   the migrated surface; **before/after visual evidence** (light **and** dark, wide **and** narrow)
   under `docs/fork/evidence/<slice>/`. Named specs per slice below. Existing suites stay green.
2. **Code simplification.** The token swap is the moment to **delete**, not just restyle: dead code,
   duplicated style blocks, component families collapsed to a primitive, surfaces deleted instead of
   migrated. Named targets per slice. A slice that only swaps tokens and simplifies nothing is a smell.
3. **Adversarial review.** Fresh-context review per slice with an explicit regression-hunt focus
   (visual drift, **dark-mode contrast**, lost states/affordances, a11y/focus/keyboard, responsive
   breakage). Security-touching slices (MFA, change-password) get the extra ADR-F005 security pass.

## Coverage model (critique fix — the plan's spine)

The decomposition is **not valid until a coverage table closes to zero unassigned `--lq-*` files.**
Before R-LAST can run, every file in `grep -rl 'var(--lq-' src` must map to a slice **or** a
documented defer-with-owner. Build this table first (a living artifact in this doc), because the
first map pass under-listed ~15–20 surfaces. Known orphans the maps missed (must be assigned):

- `routes/lq-ai/(tools)/agents/+page.svelte` (35) — **the area-home chrome that HOSTS
  ConversationPanel + NewMatterModal**; assign to Wave 1 (near R9/R-CONV).
- `routes/lq-ai/(tools)/playbook-executions/[id]/+page.svelte` (**64 — heaviest file in the repo**),
  `tabular/new` (46), `tabular/[id]` (31), `playbooks/easy` (34) — R15 scoped these OUT; reclaim them.
- Global chrome: `lq-ai/+layout.svelte` (2), `(tools)/+layout.svelte` (7), `login/+page` (4),
  `word-addin/oauth-start` (15), `matters/+page` (6, a NewMatterModal host), `matters/[id]` (2),
  `skills/[id]` (6), `skills/[id]/edit` (12).
- Components: `PlaybookEditor` (12), `PlaybookEditorPosition` (16), `PlaybookEditorFallbackTier` (10),
  `PlaybookDisclaimerBanner` (7), `TabularCell` (15), `TabularCitationModal` (16), `TabularGrid` (8),
  `MatterCard` (11), `SettingsToggleGroup` (13 — R16 only *tests* it), `InfoTip` (6), `CaptureSkillModal`
  (10), `AttachedSkillPill` (5), `MessageOverflowMenu` (6), `DevApiDocsCard` (8), `TopTabBar` (7),
  `AmbientTrustChrome` (4), `SessionTimeoutWarning` (4), `ComingSoonModal` (3), `AmbientFooter` (2).
- **typography.css** (`lq-text-*` used in **96 files**) consumes `--lq-text`/`--lq-text-tertiary`/
  `--lq-font-sans` — and **`--lq-font-sans` is undefined today** (pre-existing latent bug). Decouple
  before deleting the color layer (R-TYPO). Treat `lq-text-*` as orthogonal to color migration.

## Slice sequence (corrected for the critique)

Sizing: XS <0.5d · S ~1d · M ~2d · L = split it. IDs are stable handles, not strict order.

### Foundation
- **R0 — Extract matter validators** → `lib/lq-ai/validators/matter.ts`. *Critique fix:* compose
  **shared helpers** (`validateName`, `validateTierFloor`) behind two thin wrappers — do NOT collapse
  `validateNewMatter`/`validateMetadata` into one context-flagged function (their truth tables differ).
  Cockpit + rail import logic without pulling a legacy `.svelte`. **Test:** `validators/matter.test.ts`
  (both callers' rules); cockpit quick-create + `wave-c-matters` stay green. **Simplify:** kill the
  duplicated validator body. **Adversarial:** import-path breakage; truth-table diff per caller. *(XS)*
- **R1a — Modal/form primitives** `ModalShell` (over `ui/dialog` + focus-trap + `motionMs`),
  `FormControl` (over `ui/input`+`ui/textarea`), `Alert` — **proven on NewMatterModal** (real consumer).
  **Test:** focus-trap/escape/reduced-motion vitest + `shared-primitives.cy.ts`; NewMatterModal light/
  dark/wide/narrow/error evidence. **Simplify:** delete `nmm-*`; fix the wrong "defaults to Tier 2"
  InfoTip copy (backlog). **Adversarial:** aria-modal/focus-return, dark backdrop dimming, error-state
  WCAG. *(M)*
- **R1b — List primitives** `TableBase`, `CardGrid`, `EmptyState` — *critique fix:* built against a
  **real list consumer**, so **fold into R12 (Knowledge list)** rather than shipped speculatively. *(folded)*

### Rail family
- **R2 — MatterRailMetadata** (read/edit/archive/validation/TrustPill) → primitives; migrate TrustPill
  here so the family doesn't each re-touch it; fix the `as Parameters<…>` archive cast. *(M)*
- **R3 — `RailAttachSection` generic + Files.** *Critique fix:* **prototype all three shapes
  (FileMeta|KnowledgeBase|SkillSummary) before committing the generic** — the maps warn detach-confirm
  UX + api signatures differ; don't let R3's abstraction be load-bearing on faith. *(M)*
- **R4 — Knowledge + Skills rails** onto `RailAttachSection`; delete all `var(--lq-*,#fallback)`. *(S)*
- **R5 — MatterRail container** → flex/gap/`border-border`; consolidate the 5 duplicated
  `.rail-section*` blocks; family now has zero `practice.css` imports. *(M)*

### Wave 1 — conversation core (highest risk, highest value)
- **R6 — MessageBubble family + `<think>` ribbon** (TierBadge/TierDetailsPanel/ProvenancePill); ship
  the backlogged collapsed reasoning ribbon; kill `color:white` literal. *Critique fix:* **NO
  memoization here** — `marked.parse`/DOMPurify memoization is a behavior change; do it separately
  with its own tests. *Critique fix:* drop the AppliedSkillsChip claim (it has zero `--lq-*`).
  **Adversarial:** citation single-fetch race, DOMPurify image-beacon gap (backlog), accent-on-accent
  dark contrast, ARIA. *(M)*
- **R7 — Composer satellites** SlashPopover + EnhancePromptExpansion; delete fallback chains.
  **Adversarial:** listbox keyboard/`aria-activedescendant`, popover z-index under every modal combo. *(S)*
- **R8 — Containers** MessageList, ChatSidebar, AttachedFilesPanel, SavedPromptsPanel; `lq-btn-*`
  literals → shadcn `Button`; extract a reusable upload-chip. **Adversarial:** scroll anchoring,
  upload-cancel chip removal, dual-use SavedPromptsPanel. *(M)*
- **R9 — ChatPanel composition** (~1,150 LOC: skill/model pickers, draft, send/consume) + `agents/+page`
  home chrome (orphan, folded here). **Adversarial:** skill-attachment provenance (final source wins),
  tier-mismatch → `TierFloorOverrideModal`. *(M; ⚠ read ChatPanel in ranges; if edit churn pushes the
  200k cap, split `agents/+page` into its own XS slice.)*
- **R-CONV-1 — ConversationPanel logic extraction** (NO styling). Extract the polling/generation-guard
  state machine, the SSE-consume helper, and the auto-scroll composable into `lib/lq-ai/agents/*.ts`
  modules; behavior-preserving. **Test:** vitest for each module (generation-mismatch, poll/stream
  fallback, scroll guards); `f0-s7-stream` + `f0-s5-multi-turn` stay green. **Adversarial (logic-only,
  load-bearing):** SSE/poll ordering, stale-snapshot guard, ADR-F004 settled-rows contract — pure
  equivalence, no visual surface. *(M; ⚠ read the file in ranges.)*
- **R-CONV-2 — ConversationPanel styling** the now-thinner remainder + `<style>` block → semantic
  tokens; `<think>` ribbon idiom from R6; reuse R8 upload-chip. **Adversarial (visual-only):** dark
  contrast, auto-scroll on `<720` stacked, ConversationHost re-home (unchanged exemplar — verify, don't
  edit). *(M; ⚠.) — split is best-practice (logic-equivalence vs visual review) AND fits the 200k cap.*

### Wave 2 — library surfaces
- **R12 — Knowledge list + detail** (folds **R1b** primitives); merge the duplicated status roll-up in
  `knowledge-page-helpers`/`knowledge-detail-helpers`. **Adversarial:** dark row-hover visibility,
  status-pill contrast, long-filename wrap. *(M)*
- **R13 — Embedded modals** AttachKBModal + PlaybookExecuteModal → ModalShell/FormControl; keep
  `kbDisplayStatus`/`filterKBs`/… signatures unchanged. *(M)*
- **R14a — Skills list + read surfaces** skills/+page, SkillDetailTabs, SkillSourceView, SkillTryItPane,
  SkillVersionsTab (TableBase + tabs). *(S)*
- **R14b — Skill authoring** SkillWizard, SkillWizardSection, CaptureSkillModal (FormControl + Alert;
  delete the hardcoded rgba error-banner). **Adversarial:** slug/alias `aria-invalid`, localStorage
  autosave round-trip. *(M)* — split off R14 to hold the 200k cap (wizard + page together exceed it).
- **R15 — Playbooks + Tabular lists** onto TableBase; consolidate format helpers into `lib/format.ts`. *(S)*
- **R15b-tab — Tabular long tail (orphans):** `tabular/new` (46), `tabular/[id]` (31),
  TabularCell (15), TabularGrid (8), TabularCitationModal (16). *(M; ⚠ tabular/new is large.)*
- **R15b-pb — Playbook long tail (orphans):** `playbook-executions/[id]` (**64 — heaviest**),
  `playbooks/easy` (34), PlaybookEditor{,Position,FallbackTier}, PlaybookDisclaimerBanner. *(M; ⚠.)*
  — split off R15b so each holds the 200k cap (≥10 surfaces combined).

### Wave 3 — long tail
- **R16 — Settings/admin nav shells** + **migrate** SettingsToggleGroup (not just test it); `SettingsSection`
  wrapper; delete dead `featured_tools` handling. *(S)*
- **R17a — MFA panel** (isolated per ADR-F005 security blast-radius). Security review pass. *(S)*
- **R17b — Export/delete + change-password** (gray-* → semantic; `lq-btn-*` → Button; delete-confirm via
  ModalShell). Security review pass. *(M)*
- **R18 — Admin audit-log + intake-bridges** + shared `lib/pagination.ts` + `lib/date-utils.ts`. *(M)*
- **R19a — Trust + Learn (presentational)** + `CardShell`. **Adversarial:** Trust markdown
  sanitization unchanged; Learn heading a11y; custom 960/720 breakpoints vs Tailwind. *(M)*
- **R19b — Dev/admin chrome** developer + DevRoleManagementCard/DevApiPlaygroundCard/DevForkCallout +
  admin/models + word-addin (AliasTable/AliasForm). Token-swap-only (F3 demotes these — don't gold-plate). *(M)*
- **R20 — SavedPromptsPanel + CronInput.** CronInput's *logic* survives F3 retargeting → migrate well
  (not deletion-bound), even though its host pages (schedules/watches) are skipped. *(M)*
- **R-CHROME — Global chrome orphans** login, `(tools)/+layout`, word-addin/oauth-start, MatterCard,
  TopTabBar, Ambient*, SessionTimeoutWarning, ComingSoonModal, InfoTip, DevApiDocsCard. *(S–M.)*

### autonomous/* (deletion candidate)
- **R21 — SKIP ALL 10 pages** (resolved default, ↓ Decision 1). Touch nothing; leave the whole family
  on the bridge for F2/F3 to delete wholesale. **Basis:** legacy LangGraph surface slated for
  deep-agents replacement; the bridge already gives functional dark mode; migrating *any* deletion-bound
  page is negative-ROI. **Exception:** migrate `sessions/[id]` (run-receipt) ONLY if it's the interim
  run-inspection UX *and* the replacement is >1 milestone out. Not a slice by default — a one-line
  "deferred to F2/F3" in the coverage table. (CronInput logic is still migrated in R20 — its plumbing
  survives; its host pages don't.)

### Cleanup (gated)
- **R-TYPO — Decouple typography.css** (critique fix, **prerequisite to deletion**): repoint
  `--lq-text`/`--lq-text-tertiary`/`--lq-font-sans` onto Tailwind semantic tokens (or a tiny alias),
  and **fix the undefined `--lq-font-sans`**. Without this, deleting the color layer makes all 96
  `lq-text-*` consumers render unstyled. *(S)*
- **R-BRIDGE — Remove the global imports** from `lq-ai/+layout.svelte` (lines 23–24) — the slice that
  actually retires the dark-mode bridge. Gated on every non-autonomous surface migrated. *(XS, but the
  real moment of truth — full-suite regression.)*
- **R-LAST — Delete the `--lq-*` color layer** from practice.css. *Critique fix:* **conditional/partial**
  — R21 leaves 7 autonomous pages on the layer, so this ships a radius/space-only `practice.css` + a
  color alias **gated on F2/F3 deleting those pages**; the true terminal deletion moves to that F2/F3
  slice. **Gate:** `grep -rl 'practice.css' src` == 0 (non-autonomous) AND
  `grep -rE 'var\(--lq-(?!space|radius)' src` == 0 (non-autonomous). Full-suite regression + spot-check
  evidence. *(S)*

## Resolved decisions (proposed defaults — overturn any you disagree with)

1. **autonomous → SKIP ALL 10** (was "stabilize 3"). Negative-ROI to migrate deletion-bound pages;
   the bridge holds dark mode; F2/F3 deletes the surface. R-LAST stays conditional/partial regardless,
   so skipping 3 more pages costs nothing and simplifies the deferred bucket to one decision.
   Exception: migrate `sessions/[id]` only if it's the interim run-inspection UX and replacement is far.
2. **ConversationPanel → SPLIT** R-CONV-1 (logic extraction, tested, no styling) + R-CONV-2 (style the
   remainder). Best practice (logic-equivalence review separated from visual review) **and** the only
   way the 1,435-LOC file fits the 200k main-context cap.
3. **Scope → WHOLE interface, checkpointed.** Per the standing "entire interface must change" directive,
   don't ship a permanent MVP subset. Sequence: Foundation (R0,R1a) + Wave 1 (R6–R9, R-CONV-1/2) →
   **re-plan checkpoint** (validate the primitive kit + pattern on the flagship) → Waves 2–3 → cleanup.
   The bridge keeps the rest functional, so slices merge independently; the long tail is sequenced,
   not deferred.
4. **typography.css → `@layer base` shim** (lowest risk vs touching 96 files) + the R-TYPO decoupling
   step before any color-layer deletion. Also fixes the undefined `--lq-font-sans` latent bug.
5. **Coverage table is step 0** (non-negotiable): commit the `grep -rl 'var(--lq-'` → slice assignment
   table here before execution, so R-LAST's gate is provably reachable.

Net slice count after the 200k splits: ~29 (R0, R1a, R2–R5, R6–R9, R-CONV-1/2, R12, R13, R14a/b, R15,
R15b-tab/pb, R16, R17a/b, R18, R19a/b, R20, R-CHROME, R-TYPO, R-BRIDGE, R-LAST; autonomous deferred).
Each ≤~6–8 files / ≤~2k LOC, executable in one ≤200k session.

## Verification (per slice, ADR-F005 gate)

`cd web && npm run check` (0 errors) + `npx vitest run` (counts quoted) + the slice's Cypress specs +
visual evidence (light/dark, wide/narrow) under `docs/fork/evidence/<slice>/`; CI green on the PR;
fresh-context adversarial review (security pass on R17a/R17b); HANDOFF updated. No new dependency
(shadcn `ui/*` already present: badge/button/dialog/dropdown-menu/input/resizable/scroll-area/
separator/skeleton/textarea/tooltip — wrap, don't rebuild).
