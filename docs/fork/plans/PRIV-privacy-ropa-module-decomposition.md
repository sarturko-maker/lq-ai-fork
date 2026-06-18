# PRIV — Privacy / ROPA module (decomposition)

**Milestone:** the first **agentic module** of **LQ.AI Oscar Edition** — maintain a client's **ROPA + privacy
programme** with the Privacy practice-area Deep Agent. Governed by **ADR-F018** (typed domain +
code-validated agent writes). Reference (only): the maintainer's **Oscar Privacy** product — take the idea +
domain, reimplement and **improve** (code-validated entries over Oscar's trusted-model writes); ICO RAG and
Oscar's engine are dropped. Builds on UX-B ([[ux-b-milestone-complete]]).

## Outcome ("done")

A user opens a Privacy matter ("Programme — GDPR / ROPA"), the agent reads the client's documents and
**proposes** ROPA entries, **code validates** them before commit, and the matter accumulates a real,
queryable ROPA that the user **SEES and browses as a OneTrust / TrustArc-equivalent register UI** in the
cockpit (not merely an export) and can export as a deliverable — agent proposes, code disposes, human owns.

## Module UI requirement (maintainer, 2026-06-18)

A "module" in LQ.AI must **render its domain UI** — give the user the **functional equivalent** of what the
reference product shows. For Privacy that means the user can **SEE a OneTrust / TrustArc-equivalent ROPA
register** (a browsable Records of Processing Activities view — list + entry detail, lawful-basis /
special-category / retention visible at a glance), surfaced in the cockpit, not just a file you download.
The agent maintains it; the user reads and owns it.

**Take the information architecture / feature parity from Oscar/OneTrust — NOT their visual style.** The UI
must look and feel like **LQ.AI Oscar Edition**: it lives inside our cockpit and is rendered in our own
calm F013 design language ([[f013-design-language-vercel]]) — charcoal, scarce-blue accent, our type/spacing/
motion tokens, our primitives (`PageShell`/`SectionHeader`/shadcn-svelte). It must **not** inherit
Oscar Privacy's (or OneTrust's) look, chrome, or component styling — only the *what to show* (the register
as a first-class surface, the fields that matter), not the *how it looks*. This is a **first-class module
surface**, sequenced into PRIV-3 (read view) → PRIV-4+ (the full programme cockpit), below.

## Working rules (per maintainer, 2026-06-17)

**SHORT SLICES, COMPACT BETWEEN EACH.** Every slice is one PR, vertical, ≤2–3 days, full four-discipline DoD,
HANDOFF written last. **Compact context after each slice; the next session reads HANDOFF first.** Re-plan at
slice boundaries — do not front-load. Privacy module **first**; redlining is the **next** track.

## What already exists (don't rebuild)

`practice_areas` + matter binding (`projects.practice_area_id`, `context_md`) — F1-S3; Privacy area is
configured with a forward-looking profile + bound skills (UX-B-2/3). Gateway sole-egress +
`guarded_tool_call` (R5/R6); deepagents loop with `parent_step_id`; scenario harness
(`api/tests/agents/scenarios/`); latest migration **0057** (new ones start 0058). **Missing:** the typed ROPA
domain + the validated write path — that is all this milestone adds on the api side.

## Slices (thin-vertical-first; each one PR, compact after)

- **PRIV-0 — Plan + ADR-F018 (THIS slice; docs only).** ADR-F018 (proposed), this decomposition, the
  milestone entry, HANDOFF. Maintainer edits the plan before PRIV-1. **Compact after.**

- **PRIV-1 — ROPA domain spine + code validation (no agent yet).** The smallest useful typed entity:
  **`processing_activities`** (purpose, lawful basis, retention, special-category flag, controller/processor
  role, linked to a Privacy `project_id`) as a SQLAlchemy model + **migration 0058** + a Pydantic domain
  schema carrying **code invariants** (lawful-basis enum; retention required; special-category ⇒ Article 9
  condition required). Authz follows the existing project-ownership pattern (cross-user → 404). Unit tests for
  the invariants (accept + reject cases). NO agent wiring. **Compact after.**

- **PRIV-2 — Validated agent write path.** One or two ROPA tools (`propose_processing_activity`,
  `list_processing_activities`) wired onto the Privacy area agent through `guarded_tool_call`; the tool
  **validates via the PRIV-1 schema before commit** and **returns the rejection reason to the model** on
  failure (propose→validate→commit, or propose→reject→retry — never silent write/fix). Scripted-model test of
  both paths (valid commit; invalid rejected + surfaced). **Compact after.**

- **PRIV-3 — Thin vertical end-to-end + first deliverable + the ROPA register UI (read).** Ingest a doc into
  a Privacy matter → agent extracts + proposes processing-activity entries → code validates → commit → the
  user **SEES the ROPA**: a read-only **OneTrust/TrustArc-equivalent register view** in the cockpit (the
  matter's processing activities as a browsable list + entry detail, lawful-basis/special-category/retention
  visible) — **rendered in LQ.AI's own F013 design language, not Oscar/OneTrust's look** (IA borrowed, style
  ours) — **plus** a **ROPA export** deliverable (structured export view / DOCX-or-XLSX) on
  the run-artifact surface. Live scenario-harness calibration (does the qualified model extract + propose
  valid entries? does a multi-document programme trigger subagent delegation — the open UX-B-4 question?).
  Evidence report under `docs/fork/evidence/priv-3/`. (The read UI may itself split into its own short slice
  if the vertical + export already fill PRIV-3 — re-plan at the boundary.) **Compact after.**

- **PRIV-4+ — Broaden (each its own short slice, re-planned at the boundary):** the **full privacy-programme
  cockpit** (the OneTrust/TrustArc-equivalent surface: ROPA register with create/edit/filter, programme
  dashboard, gap view) — the module's first-class UI per the requirement above; more ROPA entities (systems,
  vendors/processors, data subjects, transfers + transfer-mechanism invariant); gap detection; DPIA/LIA
  deliverables. Sequence decided at the PRIV-3 boundary against what the vertical taught us.

## Non-goals (this milestone — recorded)

- **ICO RAG** (dropped per maintainer). **Oscar's engine/code** (reference-only; we rebuild on deepagents).
- **Redlining** — the NEXT track (Commercial/M&A); adeu (MIT, mechanical) as render layer + a
  "redline-like-a-lawyer" skill/positions-playbook. Its own decomposition.
- **MCP** — not on this module's critical path now that ICO is dropped; later enabler (gateway tool-egress,
  cf. upstream ADR 0014/0015) if a module needs an external source.
- **Multi-tenant end-client portal** (Oscar's shape) — LQ.AI tenancy is org/user for the operating firm.
- The **rebrand mechanical rename** — its own slice + ADR when the maintainer says go (direction recorded:
  [[lq-ai-oscar-edition-rebrand]]).

## Linked ADRs

ADR-F018 (this milestone's call), ADR-F002 (practice areas), ADR-0013 D4 (system proposes, user owns),
ADR-F010 (no gateway bypass), ADR-F015 (scenario qualification — PRIV-3 calibration), ADR-F016/F017
(skills/subagents).

## Verification (per slice)

Schema slices: scripted suite green (CI), migration verified on a **throwaway** pgvector container (never the
dev DB), dev stack rebuilt api+arq-worker+ingest-worker together when a migration lands. Agent slices:
scripted-model tests (CI) + the live scenario harness out-of-CI (PRIV-3). Fresh-context adversarial +
**security + simplification** pass ([[security-review-every-slice]]) every slice. Merge per ADR-F005 against
`sarturko-maker/lq-ai-fork`. **HANDOFF updated last; compact after.**
