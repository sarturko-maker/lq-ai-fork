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

**Consistency is four-fold, not just colour** (maintainer directive 2026-06-13, restoring the v1
verdict's "collapse panels when narrow"): the legacy surfaces must reach the cockpit's (1) semantic
colours, (2) elevation/shade, (3) motion, **and (4) responsive collapse** — panels/tabs reflowing as
the window narrows. The dark-mode bridge gives colour parity for free while a surface waits; it does
**not** give responsive parity, so (4) is an explicit per-slice deliverable on the shell/container
slices (see "Responsive parity" below), not a "don't-break-narrow" afterthought.

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

## The four disciplines — baked into EVERY slice (the user's requirement)

Every slice's Definition of Done includes all four. This is the per-slice checklist; a slice is **not
done** until all four are satisfied and shown (not asserted).

1. **Extensive testing + visual screenshot verification.** Vitest unit tests for any logic
   touched/extracted; Cypress e2e exercising the migrated surface; existing suites stay green.
   **A slice that changes a rendered surface is not "worked" until screenshots prove it** — capture
   **before/after**, **light AND dark**, **wide AND narrow**, on the dev stack (headed Chrome — headless
   captures lie about the dark theme, see Gotchas), saved under `docs/fork/evidence/<slice>/` and
   referenced in the PR. Eyeball each: correct semantic colors, AA contrast, no drift, states intact.
   **Logic-only slices (R0, R-CONV-1) are screenshot-exempt** — they must say so explicitly in the PR
   and lean on unit-test equivalence instead. Named specs per slice below. **On shell/container slices
   (see "Responsive parity") the narrow capture must show the cockpit's COLLAPSE behaviour, not merely
   an un-broken wide layout** — a non-responsive shell that "doesn't break" is a FAIL on those slices.
2. **Code simplification.** The token swap is the moment to **delete**, not just restyle: dead code,
   duplicated style blocks, component families collapsed to a primitive, surfaces deleted instead of
   migrated. Named targets per slice. A slice that only swaps tokens and simplifies nothing is a smell.
3. **Adversarial review — EVERY slice, no exceptions.** Fresh-context (subagent) review per slice with
   an explicit regression-hunt focus (visual drift, **dark-mode contrast**, lost states/affordances,
   a11y/focus/keyboard, responsive breakage; for logic slices: behavior equivalence). Blockers /
   should-fixes fixed or deferred on record before merge. Security-touching slices (MFA,
   change-password — R17a/R17b, and any gateway/auth/audit/crypto/anonymization path) get the **extra
   ADR-F005 security pass**.
4. **Session handoff at slice close (we compact every slice).** The context window is compacted at
   every slice boundary, so the LAST act of every slice — before merge — is to **draft/overwrite
   `docs/fork/HANDOFF.md`** for the next (near-empty) session: mark this slice done, point NEXT at the
   following slice with its exact pickup, and carry any new gotcha. Committed with the slice's PR
   (CLAUDE.md § Session handoff). A slice is not finished until HANDOFF says where the next one starts.

## Responsive parity (maintainer directive 2026-06-13 — folded into the shell slices)

Goal target (4) — the cockpit's **collapse-on-narrow** behaviour — is owned by the slices that already
refactor a shell/container, so the responsive work lands in the SAME diff as the token swap (no
touching these files twice). The standard: **mirror the cockpit's breakpoints and collapse idiom**
(F1-S2/S2.1 — `AreaGrid`/`MattersPanel`/`ConversationHost`; reuse its container query / `motionMs`
pattern, don't reinvent), so the whole app reflows identically.

**Shell/container slices that MUST deliver responsive collapse (DoD upgraded from "don't break narrow"
→ "matches the cockpit collapse"):**
- **R5 — MatterRail container** (the rail collapses / docks as the workspace narrows).
- **R8 — MessageList / ChatSidebar / AttachedFilesPanel** (the chat side panes collapse).
- **R9 — ChatPanel composition** — the flagship: today a **non-responsive flex row** (fixed sidebar +
  attachments squeeze the `flex-1` conversation below ~700px; R6 had to shoot "narrow" at 860px). R9
  must make the three-pane workspace collapse like the cockpit. **Re-scope note:** this enlarges R9 —
  if the responsive layout + the ~1,150-LOC token/composition swap blow the 200k cap, split R9 into
  **R9a (token/composition)** + **R9b (responsive shell)**.
- **R-CONV-2 — ConversationPanel** (stacked/collapsed layout at narrow, beyond the existing `<720`
  auto-scroll).
- **Global chrome:** the **TopTabBar** "collapsible tabs when the window size changes" lives in
  **R-CHROME** (or its own XS slice) — give it the cockpit's tab-collapse, not just a token swap.

Library/list surfaces (R12/R14a/R15/R16) already have their own breakpoints; for those, "don't break
narrow" remains the bar UNLESS the surface visibly diverges from the cockpit idiom — then align it.
The adversarial-review focus on these slices gains a first-class **"responsive collapse matches the
cockpit"** check (not just "responsive breakage").

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

### Coverage table — committed (step 0, closes to zero)

Built + verified by `cov_tmp.py` (R0): the union of the rows below equals
`grep -rl 'var(--lq-' src` exactly — **101 files, each assigned once, zero unassigned / extra / dup**
(2,752 `var(--lq-)` uses; the ~91-use gap to the 2,843 raw-token total is bare `--lq-*` refs outside
`var()` — `@media`, comments, the bridge definitions themselves — retired by R-BRIDGE/R-LAST/R-TYPO).
Re-run the verifier (or `grep -rl 'var(--lq-' src` minus this table) before R-LAST to prove the gate
is reachable. Legend: `C/` = `src/lib/lq-ai/components/`, `R/` = `src/routes/lq-ai/`.

Slices absent from the table by design: **R0** (logic-only — extracts validators, touches no token),
**R-CONV-1** (logic-only — ConversationPanel state extraction), **R-BRIDGE** (retires the global
import, deletes no per-surface token), **R-LAST** (deletes the `--lq-*` color layer). All four are in
the sequence below; they gate on the table, they don't appear in it.

| Slice | Files (`var(--lq-)` count) |
|---|---|
| **R1a — Modal/form primitives** | `C/NewMatterModal.svelte` (44) |
| **R2 — MatterRailMetadata + TrustPill** | `C/MatterRailMetadata.svelte` (70), `C/TrustPill.svelte` (18) |
| **R3 — RailAttachSection + Files** | `C/MatterRailFiles.svelte` (43) |
| **R4 — Knowledge + Skills rails** | `C/MatterRailKnowledge.svelte` (27), `C/MatterRailSkills.svelte` (37) |
| **R5 — MatterRail container** | `C/MatterRail.svelte` (24) |
| **R6 — MessageBubble family + `<think>`** | `C/ProvenancePill.svelte` (12), `C/M2Citations.svelte` (1) |
| **R7 — Composer satellites** | `C/SlashPopover.svelte` (21), `C/EnhancePromptExpansion.svelte` (50) |
| **R8 — Conversation containers** | `C/ChatSidebar.svelte` (17), `C/AttachedFilesPanel.svelte` (9), `C/MessageOverflowMenu.svelte` (8), `C/AttachedSkillPill.svelte` (7) |
| **R9 — ChatPanel composition + agents home** | `C/ChatPanel.svelte` (15), `C/ModelPicker.svelte` (17), `C/SkillPicker.svelte` (19), `R/(tools)/agents/+page.svelte` (60) |
| **R-CONV-2 — ConversationPanel styling** | `C/agents/ConversationPanel.svelte` (46) |
| **R12 — Knowledge list + detail** | `R/(tools)/knowledge/+page.svelte` (74), `R/(tools)/knowledge/[id]/+page.svelte` (77) |
| **R13 — Embedded modals** | `C/AttachKBModal.svelte` (87), `C/PlaybookExecuteModal.svelte` (25) |
| **R14a — Skills list + read** | `R/(tools)/skills/+page.svelte` (35), `R/(tools)/skills/[id]/+page.svelte` (12), `C/SkillDetailTabs.svelte` (9), `C/SkillSourceView.svelte` (46), `C/SkillTryItPane.svelte` (10), `C/SkillVersionsTab.svelte` (6) |
| **R14b — Skill authoring** | `R/(tools)/skills/[id]/edit/+page.svelte` (15), `C/SkillWizard.svelte` (10), `C/SkillWizardSection.svelte` (4), `C/CaptureSkillModal.svelte` (10) |
| **R15 — Playbooks + Tabular lists** | `R/(tools)/playbooks/+page.svelte` (16), `R/(tools)/tabular/+page.svelte` (27) |
| **R15b-tab — Tabular long tail** | `R/(tools)/tabular/new/+page.svelte` (46), `R/(tools)/tabular/[id]/+page.svelte` (31), `C/TabularCell.svelte` (15), `C/TabularGrid.svelte` (8), `C/TabularCitationModal.svelte` (16) |
| **R15b-pb — Playbook long tail** | `R/(tools)/playbook-executions/[id]/+page.svelte` (64), `R/(tools)/playbooks/easy/+page.svelte` (34), `C/PlaybookEditor.svelte` (12), `C/PlaybookEditorPosition.svelte` (16), `C/PlaybookEditorFallbackTier.svelte` (10), `C/PlaybookDisclaimerBanner.svelte` (7) |
| **R16 — Settings/admin nav shells** | `R/(tools)/settings/+layout.svelte` (12), `R/(tools)/settings/account/+page.svelte` (15), `R/(tools)/settings/appearance/+page.svelte` (9), `R/(tools)/settings/autonomous/+page.svelte` (6), `C/SettingsToggleGroup.svelte` (23), `R/(tools)/admin/+layout.svelte` (9) |
| **R17a — MFA panel (security)** | `C/MfaEnrollmentPanel.svelte` (65) |
| **R17b — Export/delete + change-password (security)** | `C/AccountExportDeletePanel.svelte` (62), `R/change-password/+page.svelte` (1) |
| **R18 — Admin audit-log + intake-bridges** | `R/(tools)/admin/audit-log/+page.svelte` (18), `R/(tools)/admin/intake-bridges/+page.svelte` (42) |
| **R19a — Trust + Learn (presentational)** | `R/(tools)/trust/+page.svelte` (5), `R/(tools)/learn/+page.svelte` (19), `R/(tools)/learn/build/+page.svelte` (57), `R/(tools)/learn/how/+page.svelte` (45), `R/(tools)/learn/use/+page.svelte` (36), `C/TrustArtifactsCard.svelte` (10), `C/TrustDataResidencyCard.svelte` (15), `C/TrustExternalTurnsCard.svelte` (14), `C/TrustProvidersCard.svelte` (11) |
| **R19b — Dev/admin chrome** | `R/(tools)/admin/developer/+page.svelte` (6), `R/(tools)/admin/models/+page.svelte` (10), `R/(tools)/admin/word-addin/+page.svelte` (51), `R/word-addin/oauth-start/+page.svelte` (19), `C/DevRoleManagementCard.svelte` (51), `C/DevApiPlaygroundCard.svelte` (25), `C/DevForkCallout.svelte` (22), `C/DevApiDocsCard.svelte` (17) |
| **R20 — SavedPromptsPanel + CronInput** | `C/SavedPromptsPanel.svelte` (19), `C/CronInput.svelte` (46), `R/(tools)/saved-prompts/+page.svelte` (4) |
| **R-CHROME — Global chrome orphans** | `R/login/+page.svelte` (7), `R/(tools)/+layout.svelte` (13), `R/+layout.svelte` (2), `C/MatterCard.svelte` (20), `C/TopTabBar.svelte` (13), `C/AmbientFooter.svelte` (5), `C/AmbientTrustChrome.svelte` (6), `C/SessionTimeoutWarning.svelte` (10), `C/ComingSoonModal.svelte` (9), `C/InfoTip.svelte` (6), `R/(tools)/matters/+page.svelte` (19), `R/(tools)/matters/[id]/+page.svelte` (4) |
| **R-TYPO — typography.css decouple** | `src/lib/lq-ai/styles/typography.css` (9) |
| **R21 — autonomous/\* (DEFER to F2/F3 — skip, leave on bridge)** | `R/(tools)/autonomous/+page.svelte` (100), `R/(tools)/autonomous/+layout.svelte` (10), `R/(tools)/autonomous/configure/+page.svelte` (11), `R/(tools)/autonomous/memory/+page.svelte` (57), `R/(tools)/autonomous/notifications/+page.svelte` (62), `R/(tools)/autonomous/precedents/+page.svelte` (54), `R/(tools)/autonomous/proposals/+page.svelte` (63), `R/(tools)/autonomous/schedules/+page.svelte` (95), `R/(tools)/autonomous/sessions/[id]/+page.svelte` (74), `R/(tools)/autonomous/watches/+page.svelte` (92) |

**R-LAST gate (now provably reachable):** all 101 files migrate (or defer to F2/F3 via R21). The 10
R21 files (621 uses, the largest single bucket) stay on the bridge — which is exactly why R-LAST is
conditional/partial (ships a radius/space-only `practice.css` + color alias, terminal deletion moves to
the F2/F3 slice that deletes the autonomous surface). Non-R21 surfaces = 91 files / 2,131 uses.

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
  `.rail-section*` blocks; family now has zero `practice.css` imports. **+ Responsive parity:** the rail
  collapses/docks as the workspace narrows (cockpit idiom). *(M)*

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
  literals → shadcn `Button`; extract a reusable upload-chip. **+ Responsive parity:** the chat side
  panes collapse on narrow (cockpit idiom). **Adversarial:** scroll anchoring,
  upload-cancel chip removal, dual-use SavedPromptsPanel, **collapse-matches-cockpit**. *(M)*
- **R9 — ChatPanel composition** (~1,150 LOC: skill/model pickers, draft, send/consume) + `agents/+page`
  home chrome (orphan, folded here). **→ NOW SUBSUMED BY AE5 (Prompt Input)** — see § "AI Elements visual
  adoption" (ADR-F011): R9 is no longer a token swap, it becomes the AE Prompt Input restyle. The R9a/R9b
  split is **moot** — the responsive chat shell already shipped in **R8**. **Adversarial:** skill-attachment
  provenance (final source wins), tier-mismatch → `TierFloorOverrideModal`. *(M→L; ⚠ read ChatPanel in ranges.)*
- **R-CONV-1 — ConversationPanel logic extraction** (NO styling). Extract the polling/generation-guard
  state machine, the SSE-consume helper, and the auto-scroll composable into `lib/lq-ai/agents/*.ts`
  modules; behavior-preserving. **Test:** vitest for each module (generation-mismatch, poll/stream
  fallback, scroll guards); `f0-s7-stream` + `f0-s5-multi-turn` stay green. **Adversarial (logic-only,
  load-bearing):** SSE/poll ordering, stale-snapshot guard, ADR-F004 settled-rows contract — pure
  equivalence, no visual surface. *(M; ⚠ read the file in ranges.)*
- **R-CONV-2 — ConversationPanel styling** the now-thinner remainder + `<style>` block → semantic
  tokens; `<think>` ribbon idiom from R6 (adopt `primitives/ReasoningRibbon.svelte` + the shared
  `renderModelMarkdown`); reuse R8 upload-chip. **→ NOW SUBSUMED BY AE6 (Tool + Task)** — see § "AI
  Elements visual adoption" (ADR-F011): the agent-step timeline (`ag-step--tool_call/tool_result`) is
  restyled to the AE **Tool** + **Task** cards instead of a bare token swap. **+ Responsive parity:**
  stacked/collapsed layout at narrow (cockpit idiom). **Adversarial (visual-only):** dark contrast,
  auto-scroll on `<720` stacked, ConversationHost re-home (unchanged exemplar — verify, don't edit). *(M; ⚠.)*

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
  TopTabBar, Ambient*, SessionTimeoutWarning, ComingSoonModal, InfoTip, DevApiDocsCard. **+ Responsive
  parity:** give **TopTabBar** the cockpit's "collapsible tabs when the window narrows" (the literal
  behaviour the maintainer flagged) — not just a token swap; split it into its own XS slice if it grows.
  *(S–M.)*

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
Each ≤~6–8 files / ≤~2k LOC, executable in one ≤200k session. **+ Responsive parity (2026-06-13)** may
add ~1–2 slices: R9 likely splits into **R9a** (token/composition) + **R9b** (responsive shell), and
**TopTabBar** may peel out of R-CHROME — finalise at the Wave-1 re-plan checkpoint.

## Verification (per slice, ADR-F005 gate)

Every slice closes the same gate, in order:

1. `cd web && npm run check` (0 errors) + `npx vitest run` (counts quoted in the PR) + the slice's
   named Cypress specs. Existing suites stay green.
2. **Screenshot evidence** (discipline 1) under `docs/fork/evidence/<slice>/` — before/after, light
   **and** dark, wide **and** narrow, captured **headed** (headless lies about dark theme), referenced
   in the PR. Logic-only slices (R0, R-CONV-1) state the screenshot-exempt reason instead.
3. **CI green** on the PR (all three jobs).
4. **Fresh-context adversarial review** (subagent) — every slice; extra security pass on
   R17a/R17b and any gateway/auth/audit/crypto/anonymization path.
5. **HANDOFF.md drafted/overwritten** for the next compacted session and committed with the PR.

No new dependency (shadcn `ui/*` already present: badge/button/dialog/dropdown-menu/input/resizable/
scroll-area/separator/skeleton/textarea/tooltip — wrap, don't rebuild). Then squash-merge per ADR-F005.
**Exception:** the AE-series below adds `shiki` (justified in ADR-F011) — the one sanctioned new runtime dep.

## AI Elements visual adoption (AE-series) — folded in 2026-06-14 (ADR-F011)

**Goal:** adopt the look-and-feel of Vercel **AI Elements** on the conversation + agent surfaces —
document-style full-width assistant responses, polished streaming (shimmer + auto-collapsing reasoning
with a duration), syntax-highlighted code blocks, hover actions, collapsible tool/task/sources cards.
**Hard rule honored:** default clean light/white theme + dark mode (we re-token to our existing palette).

**Why this is additive, not a detour:** the R-series builds the semantic-token foundation AI Elements
*requires*; we're already on its exact substrate (shadcn-svelte 1.3 + bits-ui 2.18 + Tailwind v4). So AE
layers on top of the migration — it does not replace it. **Svelte is retained — no React rewrite** (ADR-F011).

**Approach — VENDOR, re-token, re-wire (not a drop-in):**
- Vendor the MIT Svelte port [`SikandarJODD/ai-elements`](https://github.com/SikandarJODD/ai-elements)
  component **source** via `jsrepo` (dev-only CLI) into **`web/src/lib/lq-ai/components/ai-elements/`** —
  source we own, same model as `ui/*`. Re-skin to our semantic tokens (born 0 `var(--lq-)` → no R-LAST
  regression). Where the port lags or is low-quality, **fall back to hand-building on shadcn-svelte**.
- **KEEP our transport + chokepoint:** gateway + custom SSE + `guarded_tool_call` + audit. Do **NOT**
  adopt `@ai-sdk/svelte`'s `Chat` (it expects an AI-SDK-shaped endpoint and bypasses all of the above).
  Feed the AE components from our existing message store / SSE frames / Citation Engine / agent steps.
- **KEEP our hardened sink:** render model output through `renderModelMarkdown` (`marked`+`DOMPurify`,
  media-forbid). Adopt the "Response" *prose styling*, not its markdown renderer. Any vendored `{@html}`
  is a per-slice security item.
- **Deps/governance:** `shiki` (code highlight) = SBOM entry (tokenizes text; no eval/network). `jsrepo`
  = dev-only. **Each vendored component = SBOM + supply-chain review on its slice + MIT attribution in
  `NOTICES.md`.** Confirm each compiles under our Svelte 5 / Tailwind v4 build.

**Message identity (proposed default — overturnable):** **full-width assistant** (document-style
Response) **+ soft right-aligned user bubble** (the AI Elements signature; suits long legal answers with a
provenance/citation row beneath).

**Each AE slice carries the same four disciplines + the ADR-F005 gate** (testing + headed before/after
screenshots light+dark/wide+narrow · simplification · adversarial review WITH the mandatory security pass
· HANDOFF at close). Shell slices (AE1, AE5, AE6) must show the responsive collapse in the narrow shot.

### AE slices
- **AE0 — Vendoring foundation ✅ DONE (PR #59).** *(infra; screenshot-exempt.)* Distribution turned
  out to be the **shadcn-svelte registry JSON** (`…/r/<c>.json`), not jsrepo; vendored `loader` +
  `suggestion` (zero new deps), proved the pipeline behind `/lq-ai/_ae-lab`, NOTICES MIT row added.
  **Re-plan checkpoint PASSED → vendor approach confirmed for AE1–AE7** (token-remap ≈ identity; port
  quality high). Original spec below for reference. ~~`jsrepo init` against~~
  the registry; verify Tailwind v4 + shadcn-svelte interop; establish the **token-remap convention**
  (registry tokens → our semantic tokens); add the MIT `NOTICES.md` entry; prove the pipeline by vendoring
  + re-skinning **two trivial components (Shimmer/Loader, Suggestion)** behind a `/lq-ai/_ae-lab` dev
  route (no live-surface change). **Adversarial:** dep/SBOM review of what `jsrepo` pulled; confirm no
  `@ai-sdk/svelte` runtime coupling crept in. *(S)*
- **AE1 — Conversation + Message + Response (full-width) ✅ DONE (PR #60).** Vendored `conversation/`
  (full) + `message/` CORE only (Message + MessageContent); assistant = full-width prose via OUR
  `renderModelMarkdown` (port's Streamdown sink NOT taken); user = soft `bg-secondary` right bubble;
  sticky scroll-to-bottom. `runed` promoted to a declared devDep. Original spec below. ~~`MessageList` → **Conversation**
  (scroll container + sticky scroll-to-bottom); `MessageBubble` → **Message + Response** (full-width
  assistant, soft user bubble); **Response renders OUR sanitized markdown**. Restyles the already-merged
  R6 bubble look on the chat surface. Keep the ProvenancePill / tier / citation row beneath the Response.
  **Responsive:** narrow = full-bleed. **Adversarial:** streaming append correctness, citation-decorate
  action still binds, dark contrast, ARIA, scroll anchoring. *(M; ⚠ touches the live chat surface.)*
- **AE2 — Reasoning + Actions ✅ DONE (PR #61).** Vendored `message/actions/` (action/actions/toolbar);
  per-assistant-message **Actions** toolbar (Copy / Retry / Copy-sources) in a NEW runes wrapper
  `MessageActionsBar.svelte` (isolates shadcn-Button `onclick` forwarding from the legacy bubble), Retry
  reuses the extracted `rerunPrecedingPrompt` (shared with refusal re-run). `ReasoningRibbon` upgraded to
  the AE **Reasoning** *identity* (brain icon, chevron, "Thinking…" shimmer, "Thought for Ns", auto-open-
  while-streaming + one-shot auto-collapse) — **option-2 hand-build** kept on the accessible `<details>`
  because the AE `reasoning` registry block pulls 4 avoided deps (streamdown/shiki/mode-watcher/
  collapsible). Streaming/duration are DORMANT on the live chat surface (no separate reasoning stream
  until F1-S4) — exercised in `_ae-lab`. Zero new deps. Original spec: ~~`primitives/ReasoningRibbon` → AE
  **Reasoning** (shimmer while streaming, auto-collapse on complete + a duration); add per-message
  **Actions** (copy / retry / copy-citation) wired to the existing rerun + stream handlers.~~ *(M)*
- **AE3 — Sources + Inline Citation.** Wrap the M2 Citation Engine in AE **Sources** (collapsible "Used
  N sources") + **Inline Citation** styling; preserve the 5-state verification UI + lazy `GET
  /messages/{id}/citations`. **Adversarial:** verification-state contrast, single-fetch race, untrusted
  source-title escaping. *(S–M)*
- **AE4 — Code Block** *(new dep: `shiki`).* Vendor **Code Block** (language header + copy + Shiki
  highlight); hook into `renderModelMarkdown`'s `<pre><code>` output — **highlight runs client-side on
  already-sanitized text** (no injection). **Adversarial + security:** confirm Shiki receives escaped
  text only; SBOM + ADR-F011 dep note; copy-button clipboard a11y; dark theme of the code surface. *(M)*
- **AE5 — Prompt Input** *(REPLACES R9's scope; shell).* Composer → AE **Prompt Input**: unified rounded
  shell + toolbar (model selector, attach 📎, enhance ✨, receipts 📜, submit/stop). Keep SlashPopover,
  EnhancePromptExpansion, SkillPicker, SavedPromptsPanel wiring + every `data-testid`. **Also migrates
  ChatPanel's remaining `<style>` `--lq-*` block** (the R9 token debt). **Responsive.** **Adversarial:**
  slash provenance (final source wins), tier-mismatch → `TierFloorOverrideModal`, send/stop state,
  collapse-matches-cockpit. *(M→L; ⚠ read ChatPanel in ranges.)*
- **AE6 — Tool + Task** *(REPLACES R-CONV-2's styling; shell).* ConversationPanel agent steps
  (`ag-step--tool_call/tool_result`) → AE **Tool** (collapsible name/input/output/status) + **Task**
  (step list); keep the Reasoning idiom; **keep all polling / stale-detection / statusBadge logic
  untouched** (R-CONV-1 already extracted it). **Responsive.** **Adversarial:** status-state mapping,
  nested-step indentation, dark contrast, ConversationHost re-home (verify, don't edit). *(M; ⚠.)*
- **AE7 — Suggestions** *(optional, lowest priority).* AE **Suggestion** chips for follow-ups
  above/below the composer **only if a clean data source exists** (else back them with SavedPrompts).
  **Defer** if no honest source — don't invent suggestions. *(S)*

**Sequencing:** AE0 first (foundation). AE1–AE4 are chat-surface and land in any order on the dark-mode
bridge. AE5 fills the R9 slot; AE6 fills the R-CONV-2 slot. AE7 last/optional. The R-series continues for
non-conversation surfaces (rails, library, chrome, cleanup). **Re-plan checkpoint:** review AE0's output
(port quality + token-remap ergonomics) before committing AE1–AE7 — if the port disappoints, switch those
slices to hand-build-on-shadcn-svelte (ADR-F011 option 2 fallback).

**Net add:** ~7 AE slices, of which AE5/AE6 absorb R9/R-CONV-2 → **net new ≈ 5** (AE0–AE4 + AE7).
