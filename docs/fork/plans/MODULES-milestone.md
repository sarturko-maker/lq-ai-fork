# MODULES milestone — Workstream B re-plan (B-1…B-7)

**Status:** accepted (maintainer, 2026-07-08 — ladder in execution; B-1 started same day).
Governing ADR: `docs/adr/F067-module-model.md` (**accepted** — the module vocabulary, the
org-authored harness D2/D3, agent profiles D4, the HITL seam D5, non-goals D6). Substrate map:
`docs/fork/plans/CAPABILITY-SOURCES-birdseye.md`. Intent: `docs/fork/plans/PIVOT-modular-azure.md`
§ Workstream B.

Every slice is vertical (end-to-end runnable/testable, ≤2–3 days, one PR, full ADR-F005 gate).
The riskiest slice (B-2, the injection harness) is honestly decomposed into three sub-slices.
Non-goals repeat from F067 D6: no marketplace, Practice Knowledge stays future, legacy executors
frozen, no MCP wiring, no remote lq-skills sync.

## Ladder at a glance

| # | Slice | Depends on | Parallelizable with |
|---|---|---|---|
| B-1 | House Brief admin page (+ degraded-binding warning chip) | — | everything |
| B-2a | Org skills → agent: harness backend | F067 accepted | B-1, B-6 spike |
| B-2b | Org skills → agent: propose/review/provenance UI | B-2a | B-3, B-6 spike |
| B-2c | Org skills: red-team eval + deep security pass | B-2a/b | B-3, B-4, B-5 |
| B-3 | Knowledge-collection search tool group | F067 accepted | B-2b/c, B-5 |
| B-4 | Org playbooks through the same harness | B-2a | B-3, B-5 |
| B-5 | Sub-agent roster admin UI (no JSON) | — | B-2*, B-3, B-4 |
| B-6 | HITL: research spike → ADR → policy slice | spike: —; slice: spike ADR | spike parallel to all |
| B-7a | Profile manifests + apply transaction | B-1..B-5 landed | B-6 slice |
| B-7b | The wizard (absorbs ONBOARD-1/2 + G13/#473) | B-7a (+ B-6 for the HITL step) | — |

Suggested execution order: **B-1 → B-2a → {B-2b ∥ B-3} → {B-2c ∥ B-4 ∥ B-5} → B-6 → B-7a → B-7b**,
with the B-6 *spike* started early in parallel (it is read/research, zero product code).

---

## B-1 — House Brief admin page (+ the G13 degraded-binding signal)

**Goal:** an admin can state who the company is and who its legal team acts for (G2/G9 — today every fresh org's
agents run with a blank House Brief), and an area page warns when a binding is not adopted
(G13(a) — "configured for redlining" yet the agent can't redline).

- **Files/seams:** web only for the Brief — new `/lq-ai/admin/house-brief` page over the existing
  `GET/PUT /api/v1/organization-profile` (`api/app/api/organization_profile.py:38` — admin-gated
  PUT already exists; ZERO backend). Markdown textarea + preview (reuse `renderModelMarkdown`),
  teaching empty state ("this text is injected read-only into every agent run — ADR-F049 House
  Brief tier"). Admin nav link. The G13 chip: area detail page (`/lq-ai/admin/areas/[key]`)
  cross-checks `bound_*` against the member-readable `GET /api/v1/library` (both already fetched
  client-side per STORE-2 D-B) and badges any bound-but-unadopted entry with "not in your Library —
  the agent will not receive this" + a link to the Store.
- **Verification:** vitest + svelte-check; Cypress: save Brief → re-open → content persists;
  live: run a matter agent and see the Brief in the run's system-prompt transparency surface;
  chip: bind-without-adopt → warning renders, adopt → warning clears.
- **Dependencies:** none. Cheapest high-value slice; do first.

## B-2 — org-authored skills → agent (THE harness slices — riskiest, decomposed)

Implements F067 D2/D3 for kind=skill. Security-sensitive path ⇒ each sub-slice gets the deeper
ADR-F005 security review.

### B-2a — harness backend (propose → approve → snapshot → compose)

**Status: SHIPPED 2026-07-08** (migration 0091 `org_skill_versions`; implementation calls in the
ADR-F067 B-2a addendum — proposal state on the version table, serve-time banner, operator
excluded per ADR-F064). One correction to the text below: the chip/source data for org skills
surfaces through `GET /admin/capabilities` (`source="org"`), and revoke leaves the Library row
(runtime fail-close + dangling read-model entry).

**Goal:** an approved org skill resolves through the real pipeline into a live Deep Agent run;
an unapproved/revoked/edited-after-approval one provably does not.

- **Files/seams:**
  - Migration: `org_skill_versions` (immutable approved snapshots: slug, content, raw frontmatter,
    content hash, author, approver, approved_at, revoked_at) + proposal state on the flow (either
    a status column on `user_skills` or a small `org_skill_proposals` table — implementer's call,
    recorded in the migration docstring); extend `org_library_entries` CHECK if the kind set moves
    (skills stay kind=`skill`, `source='org'` derives from the snapshot join).
  - Propose endpoint (author-owned artifact → 422 on the F067 D3.3 strict frontmatter allowlist
    incl. the `allowed-tools` denial, 409 on shipped-slug collision, size cap) + admin
    approve/reject/revoke endpoints. Audit: `library.propose/approve/reject/revoke`
    (kind/key/version/hash/counts only).
  - Runtime: composition merges approved org snapshots into the run's skill sources —
    `build_area_skill_wiring` (`app/agents/skill_backend.py:271`) gains an org-snapshot map beside
    `resolve_skill_files`; `build_area_inventory` + bind-time validation recognise adopted org
    skill keys (same chokepoint, no second path); the served SKILL.md body carries the provenance
    banner (F067 D3.5).
- **Verification:** deterministic tests — approve→adopt→bind→compose resolves the snapshot bytes
  (not the live row); post-approval edit does NOT change what the agent reads until re-approval;
  revoke drops it at `build_area_inventory` (fail-closed, warning logged); frontmatter with
  `allowed-tools`/`minimum_inference_tier`/unknown keys → 422; shipped-slug collision → 409;
  audit rows content-free. Live: author → propose → approve → adopt → bind → run; agent lists +
  reads the skill with the provenance banner visible in the transcript.
- **Dependencies:** F067 accepted.

### B-2b — propose/review/provenance UI

**Goal:** the whole loop is walkable by a non-technical admin: a "Propose to Library" action in
the skill builder/detail page, an admin review queue (diff-style view of frontmatter + body,
approve/reject with reason), and `org` provenance badges rendered on the Store/Library/binding
surfaces (the STORE-2 badge slot).

- **Files/seams:** `web/src/routes/lq-ai/skills/*` (propose action + proposal status),
  `web/src/routes/lq-ai/admin/library/*` (review queue section + org badges),
  `$lib/lq-ai/library/page-helpers.ts` (shared provenance derivation — keep the two Library
  surfaces from drifting). No new backend beyond B-2a's endpoints.
- **Verification:** vitest; Cypress full loop vs the dev stack; screenshot evidence of the badge on
  Store + Library + area binding card + the review queue.
- **Dependencies:** B-2a.

### B-2c — red-team eval + deep security pass

**Goal:** measured evidence (ADR-F015 findings, not gates) that the harness holds: a hostile org
skill (instructs tool exfiltration, claims extra tools, demands role/budget changes, embeds an
`allowed-tools` list in the BODY text) is either rejected at propose or, once approved by a
careless admin, still cannot exceed its grants — R6 refuses un-granted tools, brakes hold, and
the agent's behaviour is observable in the transcript.

- **Files/seams:** `api/tests/agents/scenarios/` — a masked-judge scenario pack (the UX-B-1 rig);
  hostile fixtures under the test tree (never `skills/`). Plus the standalone fresh-context
  security review of the whole B-2 diff (auth/injection path per ADR-F005).
- **Verification:** eval report in `docs/fork/evidence/modules-b2c/`; deterministic denial tests
  already in B-2a re-checked against the hostile corpus; findings feed prompt/doctrine tweaks, not
  runtime gates.
- **Dependencies:** B-2a/b. Parallel with B-3/B-4/B-5.

## B-3 — knowledge-collection search tool group

**Goal:** an admin-uploaded knowledge collection becomes a bindable module: adopt (Library kind
`knowledge`) → bind to an area → the area's agents get a guarded `search_knowledge` tool whose
fenced results carry citations.

- **Files/seams:** FIRST the 20-minute confirm the birdseye flagged: whether
  `project_knowledge_bases` attach reaches `search_documents` (it does not, per the traced
  matter-files-only path — verify before schema work). Then: migration —
  `practice_area_knowledge_bases` join (mirror `PracticeAreaPlaybook`) + extend the
  `org_library_entries` kind CHECK with `knowledge`; new `KNOWLEDGE_GROUP` in
  `TOOL_GROUP_REGISTRY` (`app/agents/capabilities.py:215` — one more `ToolGroupDef`, no schema
  for the group itself) whose builder wraps the existing KB `hybrid_search`
  (`app/knowledge/retrieval.py:82`) scoped to the area's bound + adopted + matter-toggled
  collections; results rendered as a fenced data block (F049 posture) with collection/doc/chunk
  provenance; tool routed through `guarded_dispatch` (own `KNOWLEDGE_TOOL_NAMES` frozenset,
  confined like `TABULAR_TOOL_NAMES`); Store/Library pages list collections (label from
  `knowledge_bases.name`); bind card on the area page.
- **Verification:** deterministic — grant confinement (group off ⇒ tool absent from
  `GuardContext.granted`), area/org scoping (cross-org/cross-area → empty, never 403), fenced
  output shape, audit body-free; retrieval quality — a small bounded eval on a seeded KB (the F2
  Track-B instrument pattern; a finding, not a CI gate — dev-box OOM discipline applies). Live:
  upload → adopt → bind → agent answers a question only the KB can answer, with citations.
- **Dependencies:** F067 accepted. Touches `capabilities.py` alongside B-2a — rebase-coordinate,
  or run after B-2a merges; otherwise independent.
- **B-3b deferral (recorded at B-3 ship time):** the web surfaces (Store/Library sections for
  kind `knowledge` + the area-page bind card) are deferred to B-3b — B-2b concurrently edits
  those exact files; backend endpoints and panel sections shipped in B-3.
  **B-3b SHIPPED 2026-07-08 (PR #247)** — Store/Library knowledge sections, area-detail bind card, matter-
  panel TS type honesty; web-only, no `api/` changes.

## B-4 — org-authored playbooks through the same harness

**Goal:** a playbook built in the easy builder can be proposed → approved → adopted → bound, and
its positions inject as the (already fenced) Practice Playbook tier.

- **Files/seams:** reuse B-2a's propose/approve plumbing for kind=`playbook` (approved snapshot =
  a frozen copy of the positions set + hash; the live `playbooks` row stays editable in the
  builder). Smaller risk class than skills (GUIDANCE-DATA — `PRACTICE_PLAYBOOK_PROMPT` fence
  exists, `composition.py:323`); the work is the harness wiring + provenance: playbooks currently
  ship `source=None` (STORE-2 D-A) — org ones get `source='org'` + author/approver badges.
  Bind/adopt/toggle paths already exist (`practice_area_playbooks`, inventory kind `playbook`).
- **Verification:** deterministic — approved-snapshot (not live-row) positions render in the tier;
  post-approval edits invisible until re-approval; revoke drops the tier next run. Live: build a
  playbook in the easy builder → propose → approve → adopt → bind → the agent cites the company's
  position in a negotiation answer.
- **Dependencies:** B-2a (shared harness plumbing). Parallel with B-3/B-5.

## B-5 — sub-agent roster admin UI (surface ADR-F034's roster, no JSON)

**Goal:** an admin configures the area's sub-agent roster — names, plain-language instructions,
skill subsets — in a form, never a JSON textarea (replaces SETUP-4b's D6 roster-JSON card).

- **Files/seams:** web — area detail page gains a "Sub-agents" card: list/add/edit/remove; fields =
  name, description, instructions (`system_prompt`), skills multi-select bounded to the area's
  bound skill set. Backend is ALREADY the validator we need: PATCH `agent_config` runs
  `build_area_subagents` (`app/agents/area_agent.py:121` — strict key allowlist, required
  name/description/system_prompt, `model` rejected per F010, `skills` ⊆ bound per F017); the UI
  emits exactly that shape. Possibly a thin read model if the raw `agent_config` echo is awkward —
  prefer none. Seeded rosters (0057/0073: document-researcher, clause-drafter, clause-reviewer)
  render as editable rows — the F034 roster becomes visible, honest config.
- **Verification:** vitest + svelte-check; deterministic — UI payload round-trips
  `build_area_subagents` unchanged; a forged `model` key is impossible from the form and still 422s
  at the boundary. Live: edit clause-drafter's instructions → run a fan-out matter → the subagent
  step in the run timeline reflects the edit (fan-out remains model-chosen — a shape-miss is a
  finding per ADR-F015, not a failure).
- **Dependencies:** none (existing PATCH path). Parallel with everything.

## B-6 — human-in-the-loop: research spike → ADR → policy slice

**Goal (spike, PR 1 — doc-only):** answer, against pinned deepagents 0.6.8 + langgraph 1.x and OUR
runner: how does `interrupt()`/resume actually behave under our checkpointer + lease/settle
lifecycle (`runner.py`, ADR-F009)? What do langchain's HITL middleware primitives offer vs a fork
middleware at the `guarded_dispatch` seam? What does a paused run look like over SSE + in
`agent_runs` state, and who may resume (authz)? Output: a research report +
**ADR-F0xx (HITL policy)** — F067 D5 reserved the seam; the spike ADR designs it.

**Goal (policy slice, PR 2+ — after the ADR is accepted):** minimal end-to-end stop-and-ask: a
per-area `hitl_policy` (JSONB column reserved by F067 D5) naming tool classes that require
confirmation; the run pauses BEFORE executing a matching tool, surfaces a confirm affordance in
the cockpit, and resumes/refuses on the human's answer — audited (action + tool name + decision,
counts/IDs only).

- **Files/seams (slice, subject to the spike ADR):** migration (`practice_areas.hitl_policy`);
  a middleware/guard extension at or beside `guarded_dispatch`; SSE frame + web confirm UI; area
  admin card for the policy. Expect the spike to force re-slicing — that is its job.
- **Verification:** deterministic pause/resume/refuse tests incl. run-cancel-while-paused and
  lease-sweep interaction; live: a redline apply under a "confirm applies" policy stops, the
  lawyer confirms, the run completes.
- **Dependencies:** spike has none (start early, parallel); the slice needs the spike ADR accepted.
- **Status:** spike DONE (deepagents-native `interrupt_on` chosen — Option A, probe-proven).
  Re-sliced into a 3-PR ladder (ADR-F071):
  - **HITL-1 — substrate + pause: SHIPPED.** Mig 0093 (`awaiting_input` status,
    `hitl_request` step kind, `practice_areas.hitl_policy` JSONB default `{}`); policy
    compiler ∩ run grant set (`app/agents/hitl.py`); runner pause detection + settle
    `awaiting_input` + one `hitl_request` step row + instant `data-run` tail; subagent
    opt-out (lead-only v1); zero-config invariant regression-pinned; defensive web badge
    ("Waiting"). Paused threads are LOCKED (409 follow-up) until HITL-2; delete-thread is
    the escape hatch.
  - **HITL-2 — resume round-trip (NEXT):** `POST /runs/{run_id}/resume`
    (approve/reject), `Command(resume=…)` input, SKIP-repair-on-resume, `awaiting_input`
    continuable + cancel-while-paused. New route ⇒ the five route drift guards trip.
  - **HITL-3 — cockpit + admin:** confirm card from the settled `hitl_request` step,
    pending chip, area admin card writing `hitl_policy` (422 on names outside
    `hitl_eligible_tool_names()`); the live "confirm before applying a redline" verify.

## B-7 — the wizard (absorbs ONBOARD-1 template catalog + ONBOARD-2 admin wizard + G13/#473)

### B-7a — profile manifests + apply transaction

**Goal:** F067 D4 made real: shipped `profiles/*.yaml` manifests (Commercial, Privacy, blank) —
doctrine, unit vocabulary (incl. the maintainer's unit-of-work TYPES refinement: Matter /
Project / Programme / Investigation), tier/budget defaults, module bindings by kind+key, sub-agent
roster, HITL defaults — plus a loader (validated at startup like the skills catalog) and ONE
transactional apply endpoint (create/patch area + adopt Library entries + write bindings + set
roster; copy-not-link, admin owns the rows afterwards).

- **Files/seams:** `profiles/` (new, in-repo); loader beside the skills registry pattern; apply
  endpoint (AdminUser, audited `profile.apply` with counts/keys); fold `RECOMMENDED_LIBRARY_SETS`
  provenance into the manifests with the drift-guard tests moved along
  (`capabilities.py:252` — the constant's guard already pins keys against registry + corpus).
- **Verification:** deterministic — manifest schema validation (unknown kind/key → refuse at load,
  never at apply-time surprise); apply is idempotent + all-or-nothing; applying Commercial on a
  fresh org reproduces today's seeded-effective state (the parity oracle). Live: fresh org →
  apply Commercial → agent redlines out of the box (kills the G13(c) first-run cliff).
- **Dependencies:** B-1..B-5 landed (manifests reference every module kind).

### B-7b — the guided wizard

**Goal:** the maintainer's flow, end to end: pick a starting profile (Commercial / Privacy /
blank) → House Brief (B-1 page embedded) → review + adopt modules (Store rail + org Library,
adoption UNSKIPPABLE so no fresh org ships bare agents — G13(c)) → confirm bindings → sub-agents
(B-5 card) → HITL defaults (B-6) → a live test run in a scratch matter → done. First-login admin
checklist (old SETUP-3c / G2b) becomes the wizard's entry point.

- **Files/seams:** web — a `/lq-ai/admin/setup` multi-step flow COMPOSING the existing surfaces
  (B-1/B-5 components, Store add-all rail, B-7a apply endpoint); minimal new backend (possibly a
  wizard-progress flag on first login). The test-run step reuses the normal run path — no special
  pipeline.
- **Verification:** Cypress full-journey on a fresh org (reset dress-rehearsal, the ONBOARD-0/
  STORE-3 method): wizard → invite a member → member runs the Commercial agent successfully;
  screenshot evidence per step. This is the milestone's acceptance test, maintainer-walked.
- **Dependencies:** B-7a; B-6 slice for the HITL step (degrade to "coming soon" copy if B-6
  re-slices long — recorded, not silent).

---

## Backlog (out of scope, one line each — do not expand)

- Org-skill shadowing of shipped slugs with an explicit override badge (F067 D2 rejected for v1).
- Remote `lq-skills` store sync (birdseye F; supply-chain milestone after B-2 proves the harness).
- Cross-area sub-agent profile sharing (F067 D1 boundary call).
- MCP module kind (ADRs 0014/0015 gate).
- Per-subagent tool subsetting (F034 deferral) — the roster UI would grow a tools field then.
- Knowledge-collection retrieval-quality eval at scale (bigger-box batch eval; F2 OOM discipline).
