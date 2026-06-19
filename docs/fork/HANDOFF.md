# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session.**

## State (**Oscar Edition / Agentic Modules milestone OPEN** — **PRIV-8b: the LIVE mixpanel→hotjar proof — **PR #113 OPEN** (branch `priv-8b-live-swap-skill`). The PAYOFF of the group-chat thesis: a lawyer says, in plain language, *"we moved off Mixpanel, we use Hotjar now"* and the Privacy agent **composes the PRIV-8a change verbs into a coherent, audited swap** — Hotjar added + linked, Mixpanel unlinked **and soft-retired** (kept on record), then reports exactly what it changed. **Proven live on DeepSeek V4** (`max_steps=80`, 3 arms): **both skilled arms → coherent** (`deepseek`+skill and `deepseek-pro`+skill ran the full add→link→unlink→retire→confirm→report and completed); the **no-skill baseline → "lists BOTH"** (retired the Mixpanel system but left the vendor live+linked, register shows `[Hotjar, Mixpanel]`) — so the new **`ropa-maintenance` skill is load-bearing**. NOTHING destroyed (Mixpanel survives soft-retired, auditable). No `app/` code touched — this is the skill + harness + evidence: **`skills/ropa-maintenance/SKILL.md`** (swap method; retire=company-wide soft, unlink=one activity; never leave both); **`ropa_eval.py`** `seed_ropa_register` (plants the pre-existing Mixpanel register) + `retired` surfaced in `snapshot_register` + pure **`evaluate_swap`** scorer (live-register view; gates `coherent` on the activity itself being live; flags duplicate names); **`test_ropa_update_scenario.py`** (provider-gated live, asserts terminal+model-turn only per ADR-F015) + **`test_ropa_update_eval.py`** (8 non-provider CI tests). Evidence + honest FINDINGS in `docs/fork/evidence/priv-8/`. **Gate:** ruff (CI root config) + mypy clean; full api non-provider suite green (2327→2329 with the +2 new eval tests; +8 total); live run on dev gateway→DeepSeek with throwaway test DBs, **dev register verified pristine (0 leaked rows)**; **fresh-context adversarial review (4 lenses → refute-by-default): 8 findings, 4 confirmed (1 should-fix + 3 nits) ALL FIXED** — the should-fix: `evaluate_swap` over-reported `coherent` if the agent retired the whole *activity* (now gated + unit-tested); nits: duplicate-name collapse (prefer-live + flag), skill reason-length guidance (~200→real ~1000), an unused `SeededRegister` field trimmed. Skill bound **test-only** (PRIV-7 precedent); default-binding migration follows. On top of **PRIV-8a (PR #112, MERGED — main `0702e79`)** [soft-retire+unlink verbs, migration 0063, ADR-F023] + **PRIV-7 (PR #111, MERGED — `789d50d`)** + PRIV-6c…3 (ADR-F019). **RECOMMENDED next pickups:** **PRIV-9** — cockpit UX: chat + register **co-visible** (not the current either/or tabs) + **poll-while-running** so the register updates as the agent works (the side-panel idea the group chat asked for, now that the capability is proven); ship `ropa-maintenance`+`ropa-population` via a **binding migration**; carried PRIV-7 follow-ups (find-or-create **deadlock** HIGH; the `special_category=false`-but-sensitive invariant gap). **Plan:** `docs/fork/plans/PRIV-8-ropa-change-verbs.md`. **NOTE:** still fold the ADR-F021 collaboration workflow output (`wajbzaq82`) into ADR-F021's guest-agent mechanism when Authorization is picked up.)

- **PRIV-8b (PR #113, branch `priv-8b-live-swap-skill`) — live mixpanel→hotjar proof + `ropa-maintenance` skill + `seed_ropa_register`/`evaluate_swap`. Tests + 1 skill + evidence; NO `app/` code, NO migration.**
  The group-chat payoff: one plain-language ask (*"we moved off Mixpanel, we use Hotjar now"*) → the Privacy
  agent composes the PRIV-8a verbs into a coherent, audited swap and reports it. **`ropa-maintenance` skill**
  teaches the method (list → add → link → unlink → retire → confirm; *never leave both*; `retire_*`=company-wide
  soft, `unlink_*`=one activity). **Eval substrate** in `ropa_eval.py`: `seed_ropa_register` (plants a *Product
  analytics* activity + Mixpanel vendor+system, linked, `source_project_id`-stamped); `snapshot_register` now
  surfaces `retired`; pure **`evaluate_swap`** scores the *live* register view (a row is live-visible iff linked
  AND not retired) — gates `coherent` on the activity itself being live, flags duplicate names. **Live
  (DeepSeek V4, `max_steps=80`, 3 arms):** `deepseek`+skill and `deepseek-pro`+skill → **coherent** (full
  add→link→unlink→**retire**→confirm→report, both flag Hotjar's unknown DPA status honestly); `deepseek`
  no-skill → **lists BOTH** (the ADR-F023 failure) despite more budget → the **skill is load-bearing**.
  **Verify:** ruff (CI root config) + mypy clean; full api non-provider suite green (+8 new eval tests); live
  on dev gateway→DeepSeek, throwaway test DBs, **dev register pristine (0 leaked rows)**; **adversarial review
  (4 lenses → refute-by-default): 8 findings, 4 confirmed (1 should-fix + 3 nits) ALL FIXED** — should-fix was
  `evaluate_swap` over-reporting coherent on a whole-activity retire (now gated + unit-tested). Security: no
  secrets/keys/URLs/third-party text in committed files; prompt + matter note synthetic. **NOT in 8b:** the
  cockpit live-update UX (→ PRIV-9); the skill-binding migration (still test-only). **NO new ADR** (under F023).

- **PRIV-8a (PR #112, MERGED — main `0702e79`) — ROPA change verbs: soft-retire + unlink. Migration 0063 + 6 guarded tools + read filter + ADR-F023. No web.**
  Makes the Privacy agent able to *change* the register, not only append (the group-chat thesis: "we moved off
  Mixpanel, we use Hotjar now"). **Soft-retire** (`retire_processing_activity/_system/_vendor/_transfer`): set
  `retired_at` (+ optional `retirement_reason`), never delete → fully auditable, reversible-later. **Unlink**
  (`unlink_system/_vendor_from_activity`): drop one M:N link, both records stay live. The swap is *composed*
  (add new → link → unlink old → retire old), not a macro — `the_swap_replaces_a_vendor` unit test proves the
  mixpanel→hotjar shape at the tool layer. **Reads hide retired by default everywhere** (one mechanism for
  relationships: `with_loader_criteria`): API list/detail/export/summary/data-flow + agent `list_*` (incl. the
  category usage-count and transfers whose parent activity OR recipient vendor is retired); `?include_retired=
  true` = audit view; detail resolves a retired row by id. Write/link/tag/transfer verbs **refuse a retired
  target**. **Migration 0063** adds `retired_at`+`retirement_reason` to `processing_activities/systems/vendors/
  transfers` (nullable, additive, no backfill; CHECK mirror in the models). **Verify:** ruff + mypy clean (168);
  full api suite [count] passed; **0063 up/down/up round-trip on throwaway pgvector** (columns present after up);
  6 new tool tests + 7 new read-API tests. **Adversarial review (4 lenses → refute-by-default verify): 0
  blockers, 5 should-fixes ALL FIXED** — the two real ones were agent read-path divergences (`_list_categories`
  counted retired activities; `_list_transfers` showed transfers of retired parents/recipients) where the API
  was correct but the agent tools forgot the filter (exactly the ADR's load-bearing risk); plus material nits
  (write-side retired-target reject; `_unlink` single-DELETE+rowcount; `_MAX_RETIREMENT_REASON` constant;
  `_hide_retired` helper centralising the API filter; ADR D2 wording). **Security pass:** new verbs ride
  `guarded_dispatch` (R6 grant set grows 14→20, R5 re-check, audit carries result-size only — no raw values);
  SQL parameterized; deployment-global shared-read unchanged. **ADR-F023 ACCEPTED.** **NOT in 8a:** the LIVE
  mixpanel→hotjar provider run + the `ropa-maintenance` skill (→ PRIV-8b); the cockpit live-update UX (→ PRIV-9).

- **PRIV-7 (PR #111, MERGED — main `789d50d`) — live ROPA-population validation + `ropa-population` skill + a runner fix. Tests + 1 skill + a core runner change; NO migration (skill bound test-only).**
  The maintainer's onboarding test (hand the Privacy agent a real privacy notice → it builds the ROPA), run
  **live on DeepSeek-flash** against **Zendesk's** real UK notice (testing-only, fetched transiently, **not
  committed** — gitignored `_local/`; evidence carries URL + the agent's own output, never the notice verbatim).
  **Reusable eval substrate** (`tests/agents/scenarios/ropa_eval.py`): notice→`FixtureDocument` loader, a
  register read-back (`snapshot_register` by `source_project_id`), an Article-30 coverage scorer
  (`score_coverage`), `bind/unbind_area_skill` (test-only, idempotent + unbind-in-finally), `cleanup_register`.
  **Live scenario** (`test_ropa_population_scenario.py`, provider-+notice-gated → **self-skips in CI**):
  one-shot + staged baselines, and a 4-config **build comparison** (flash-noskill / flash+skill / pro+skill /
  flash+skill@150-steps). **Result:** flash+skill at max_steps=150 → **9/9 activities fully linked**
  (system+recipient+both category axes), valid by construction; the skill is the only thing that produced any
  links/vendors on flash (control: 0). **New skill** `skills/ropa-population/SKILL.md` (link-as-you-go method;
  bound test-only per maintainer — ship via migration next). **Production fix** `app/agents/runner.py`:
  langgraph's default graph `recursion_limit=25` was crashing long/skilled runs (`GraphRecursionError`) before
  `max_steps` fired; now tied to the run's `max_steps` (`max(50, max_steps*4)`), unit-tested. **Verify:** ruff +
  mypy clean (168 files); **full api suite 2300 passed / 15 skipped** (+6: `test_ropa_eval.py` 5 + the
  recursion_limit unit test; provider ROPA tests self-skip in CI); **LIVE on dev stack** (gateway→DeepSeek,
  throwaway test DBs, dev register untouched). **Fresh-context adversarial review (4 lenses → refute-by-default
  verify): 0 confirmed blockers/should-fixes, 3 nits** (settlement-only assertions are ADR-F015 report-not-gate
  + the deadlock surfaces honestly as `failed`; bind/unbind serial-only — comment added; `integrity_ok`
  tautological on live data — all accepted/documented). Security pass: no secrets/keys in committed files or
  reports; notice not committed; SQL parameterized; recursion change only RAISES the langgraph ceiling (real
  brakes intact). **No new ADR** (under ADR-F015/F016/F018/F019). **Flagged follow-ups (NOT fixed here):** the
  find-or-create **deadlock** under parallel tool calls (HIGH), the skill-binding migration, a `deepseek`
  deepagents profile, the 0-transfers budget-priority gap, and the broader "populate-from-source" family.
  **Substantive quality audit (5 privacy-lawyer lenses, FINDINGS § Substantive quality audit): overall C+ —
  a usable first-draft skeleton, NOT sign-off-ready.** Strengths: DEI Art 9 done right, conservative
  PECR-aware bases, faithful decomposition, no hallucination. Defects a lawyer would red-pen: **transfers:0**
  (Art 30(1)(e)/(f) absent — most serious), **special-category data on a contract activity with no Art 9**
  that passed `integrity_ok=true` (the write-path invariant only checks `true⇒condition`, not the inverse —
  backlog), recipient-role over-use of `processor`. Lesson: structural "9/9 linked" ≠ legal quality.
  **Pickup: the deadlock fix, the invariant-gap fix, or the skill-binding migration (see State + MILESTONES).**

- **PRIV-6c (PR #109) — data-flow / lineage view. Read API + web + 1 new web dep, NO migration.**
  An interactive **node-link data map** of the deployment-global register (the OneTrust/TrustArc "data flow"),
  in our F013 style. **Backend (pure projector, mirrors `ropa_summary`/`ropa_export`):** `app/ropa_graph.py`
  `build_graph(activities, systems, vendors) -> DataFlowGraph` — systems **feed** activities (`processed_by`),
  activities **disclose to** recipients (`disclosed_to`) and **transfer to** third-country destinations
  (`transferred_to`, carrying `restricted`/`mechanism`/`recipient`); orphan systems/vendors are unconnected
  nodes; deterministic kind-grouped order; destinations deduped by exact string. **Labels + categorical badges
  only on the wire** (no `purpose`/`retention`/`description`/transfer `details`) → shared-read (ADR-F019) +
  the private→shared confused-deputy backlog item NOT heightened (a pure test + a wire-level test assert no
  free-text leaks). DTOs `DataFlowNode`/`DataFlowEdge`/`DataFlowGraph` (`kind` = `Literal`); `GET
  /ropa/data-flow` rides the shared `_load_register`; **route count 139→140**. **Web (ADR-F022):** **new dep
  `@xyflow/svelte`** (MIT, Svelte-5 native) — the fork's **first deliberate new-dep exception**, maintainer-
  authorised (AskUserQuestion: full interactive diagram > hand-rolled SVG); our own `DataFlowNodeCard` keeps
  the look F013, layout is **pure/deterministic** (`dataFlow.ts` — no dagre/elk dep); recorded in NOTICES +
  ADR-F022. `DataFlowView.svelte` (browser-guarded canvas + legend + honest empty state); new **"Data flow"**
  register tab (2nd, after Overview), fetched in the unified `Promise.all`. **Verify:** ruff + mypy clean (168);
  **full api suite 2294 passed / 9 skipped** (+11: 8 pure `test_ropa_graph.py` + 3 endpoint cases incl. the
  wire-level free-text guard); web svelte-check **0 err** / 5 baseline warnings + **vitest 886** (+7 layout);
  eslint + prettier clean; **LIVE on dev stack** (api+web rebuilt, no migration/worker rebuild): `GET
  /ropa/data-flow` returns the real projection (10 nodes / 9 edges; US transfer restricted+SCCs+recipient,
  Germany non-restricted) + **401 unauth**; **headed Cypress** Data flow tab (light/dark × wide/narrow) in
  `docs/fork/evidence/priv-6c/` (the capture loop re-selects the tab per viewport — the cockpit remounts the
  register on a responsive breakpoint, pre-existing). **Fresh-context adversarial review (7 agents, 5 lenses →
  refute-by-default verify): 2 confirmed, 0 refuted — BOTH folded:** a pre-existing data-categories tab-guard
  fragility (in the chain this slice extends) hardened to a proper `tab === 'data-categories'` guard, and the
  DTO `kind` fields tightened from `str` to `Literal`. Security pass: no secrets; shared-read intact; no
  free-text leak; no XSS sink (labels are escaped text, no `{@html}`); new dep MIT (no prod advisory touches
  its tree); no gateway bypass. **ADR-F022 ACCEPTED** (2026-06-19, maintainer). **Known-deferred
  (carried):** `updated_at` has no `onupdate`. **Pickup: PRIV-6d** (Legal-Entity scope, needs a migration); or
  the assessment track / Authorization Phase 1.

- **ADR-F021 (PR #106, OPEN/PROPOSED, docs-only) — user permissions: areas of responsibility + collaboration.**
  Grounded + designed via two ultracode workflows (map authz surface → panel → verify). Target: ONE injected
  decision seam (`app/authz/policy.py` `can(actor,action,resource)` + `visible_filter(actor,kind)` SQL predicate
  ANDed into list WHERE) + fork-owned `user_practice_areas` (area membership, roles area_owner/member/viewer) +
  **`matter_collaborators`** (per-matter sharing) + **invitations** (auditable grant lifecycle) + cross-area
  **guest agents** ("@ Deep Agent": time-boxed, matter-scoped, default read-only; honors ADR-F002 one-matter-
  one-identity + gateway/guard; permission-gated). `is_admin` = deployment super-user (the policy branches on it,
  not the drift-prone `users.role`). The dead `get_mutating_user`/`MutatingUser` (mounted nowhere) is retired;
  roles are KEPT + enforced via the seam's closed `Action` verb enum + per-area/-matter roles. **Refines** (does
  not rewrite) ADR-F019 §Authz read clause only when the register read-filter flips; single-tenant intact (no
  org_id). The **load-bearing deliverable now is the design-readiness contract** (modules built flip-ready:
  reads through the seam, deny→404, durable NON-NULL `practice_area_id` scoping column separate from provenance,
  agent writes through `guarded_dispatch` carrying user_id+practice_area_id with the area set resolved once at
  GuardContext build, owner-OR-area-member-OR-matter-collaborator). Phased rollout in **MILESTONES § Authorization**
  (Track 0 ADR → Phase 1 seam behavior-identical → Phase 2 tables+invites → Phase 3 durable area attribution +
  backfill → Phase 4 per-seam flips incl. the register → Phase 5 cross-area + new modules). **NEXT SESSION: fold
  the grounded cross-area-agent + matter-sharing detail from the in-flight workflow `wf_815d3f81-70e` (task
  `wajbzaq82`) into ADR-F021's guest-agent mechanism + Phase 5 (its output journals to the run dir; extract the
  synthesis ECONOMICALLY — python, not full read).** Remaining open Qs in the ADR: area_owner config scope;
  invite issuer/surface; the guest-agent detailed mechanism (its own slice + ADR).
- **PRIV-6b (PR #108) — privacy programme dashboard. Read API + web, NO migration.**
  The "SEE the programme" Overview over the now-complete register (ADR-F018/F019). **Backend:**
  `app/ropa_summary.py` — pure `build_summary(activities, systems, vendors)` over the `*Read` DTOs (mirrors
  `ropa_export.build_export`): totals (activities/systems/vendors/transfers + restricted), breakdowns by
  lawful basis / controller role / DPA status (**canonical enum order, zero buckets kept** — web hides
  zeros), special-category & AI-system counts, and **"needs attention" gaps** (activities missing
  systems/recipients/data-categories/data-subjects; `vendors_without_dpa` = `pending|none`). **Counts only —
  no free-text**, so the shared-read posture (ADR-F019) and the confused-deputy backlog item are NOT
  heightened. `GET /ropa/programme-summary` (rides the router `_active` mount); **`_load_register()` helper**
  factored out of the export endpoint and shared (one load path, export behavior unchanged). DTOs
  `CountByValue`/`ProgrammeGaps`/`ProgrammeSummary`. **Web (F013, not OneTrust/Oscar chrome):**
  `ProgrammeDashboard.svelte` (totals tiles + breakdown bars + gaps, calm all-clear state) rendered as the
  **default `'overview'` tab** of `RopaRegister` (`REGISTER_TABS` gains it first; summary fetched in the
  unified `Promise.all`). **Verify:** ruff + mypy clean (167 files); **full api suite 2283 passed / 9
  skipped** (+6: 3 pure-aggregator `test_ropa_summary.py` + 3 endpoint cases in `test_ropa_read.py`;
  **contract route-count 138→139** in `test_endpoints.py` + `test_openapi.py`); web svelte-check **0 err** +
  vitest **879** (format.test.ts tab list updated, no new web test — dashboard is a render-only component,
  per the no-@testing-library boundary); **LIVE on the dev stack** (api+web rebuilt, no migration/worker
  rebuild): `GET /ropa/programme-summary` returns the real register aggregate (3 activities / 4 systems / 1
  vendor / 2 transfers, 1 restricted; gaps computed) + **401 unauth**; **headed Cypress** Overview capture
  (light/dark × wide/narrow) in `docs/fork/evidence/priv-6b/`. Fresh-context adversarial+security+
  simplification review: **see PR / workflow `wf_f2656f3c-425`**. **No new ADR** (under ADR-F018/F019).
  **Known-deferred (carried):** `updated_at` has no `onupdate`. **Pickup: PRIV-6c** (data-flow/lineage) or
  **PRIV-6d** (Legal-Entity scope, needs a migration); or the assessment track / Authorization Phase 1.

- **PRIV-6a (PR #105) — personal-data taxonomy (categories of data subjects + personal data). Migration 0062. CLOSES Article 30(1).**
  Fills **Article 30(1)(c)** — the **last** uncaptured Article 30(1) content axis — so the RoPA register now
  captures every Article 30(1) field and the **export coverage note is EMPTY** (`ART30_FIELDS_NOT_YET_RECORDED
  = ()`; the honest-coverage mechanism is retained for a future gap). **Maintainer decisions** (this session):
  taxonomy slice first (closes Art 30); model = **two M:N controlled-vocabulary entities** (`DataSubjectCategory`
  + `DataCategory`), both in one slice. **Domain:** the two entities are pure labels — `{id, name,
  source_project_id, created_at}`, **no `description`/`updated_at`** (a label is immutable) — each M:N to
  `processing_activities` (composite-PK link tables, CASCADE both ends, mirroring systems/vendors). `name` is
  **UNIQUE case-insensitively** — a **functional UNIQUE index on `lower(name)`** (model `Index(...,
  text("lower(name)"), unique=True)` + migration `create_index([text("lower(name)")], unique=True)`) — so
  "Health data"/"Health Data" can't both persist. `*Input` (name-only, `extra="forbid"`, **collapse-internal-
  whitespace** validator); `*Summary` on `ProcessingActivityRead`; `*Read` for the list endpoints + export.
  **Agent tools** (now **14**): **`add_data_subject_categories` / `add_data_categories`** — list-valued
  **find-or-create** (validate each name → match case-insensitively on `lower(name)` → reuse or create →
  idempotent link), **race-safe via a SAVEPOINT** (`_find_or_create_category`: `begin_nested` + on-
  `IntegrityError` re-select the winner — a concurrent create never raises out of the dispatch, never loses
  sibling links, never leaks SQL/params into the run error); whole call refused (nothing written) on any
  invalid name or unknown activity. `list_data_subject_categories` / `list_data_categories`. **Read API:** 2 GET
  list endpoints (`/ropa/data-subject-categories`, `/ropa/data-categories`; shared-read `_active`, ADR-F019;
  routes **136→138**); new rels eager-loaded on all 3 activity queries + export; the 4 category fetches share
  `_all_categories(db, model)` (PEP 695 generic), ordered `created_at, name` (matches the agent tool + other
  entities). **Export:** 2 activity columns + a **Data Subjects + Data Categories sheet** (6-sheet XLSX);
  coverage note → empty; `_csv_safe` on every new cell. **Web:** types + 2 list fns; **5-tab register** (Data
  subjects / Data categories tabs); activity-detail chip sections. The generic ROPA helpers are **PEP 695**
  (`def f[CatT: (DataSubjectCategory, DataCategory)]`) — the classic-`TypeVar` form tripped ruff **UP047** (would
  have failed CI). **Verify:** migration **up/down/up on a throwaway pgvector** (functional `lower(name)` indexes
  present + **case-variant rejected live**, gone on down, back on re-up); **full api suite 2276 passed / 10
  skipped** (+28 over PRIV-5a; includes the audit-regression tests); ruff + mypy clean (166 files); web check **0
  err** + vitest **879**; **LIVE on the dev stack** — read API + all 3 exports reflect the taxonomy, coverage
  note empty, the (pre-edit) unique constraint rejected a duplicate live; **screenshots
  `docs/fork/evidence/priv-6a/`** (activity taxonomy + the 2 register tabs). **Ultracode adversarial audit (54
  agents, 7 lenses → per-finding skeptics → synthesis): 23 candidates → 20 survived → 13 confirmed; initial
  verdict BLOCK on 2 highs in the find-or-create path — BOTH FIXED in-slice** (the SAVEPOINT race/leak fix + the
  case/whitespace-insensitivity fix) plus cheap correctness/transparency/test fixes (grant-set drift test, stale
  export docstring, `_all_categories` helper, ordering, coverage-mechanism + shared-read-no-provenance
  regression tests). **Flagged to the maintainer (NOT fixed unilaterally):** the **confused-deputy private→shared
  laundering** (medium — a privileged matter's confidential narrative could be distilled into a firm-wide
  register free-text field; `project.privileged` gates only the inference tier, not ROPA writes) → **MILESTONES
  § Backlog** + audit-report #3. Accepted-low: RopaRegister tab-block duplication, the twin Summary DTOs, guard
  DB-error scrubbing (defense-in-depth backlog). **No new ADR** (under ADR-F018/F019). **Dev-DB note:** the dev
  volume still carries the **pre-edit** 0062 index (plain `UNIQUE(name)`) because the dev-DB-protection rule
  forbids a direct downgrade — the **corrected** functional `lower(name)` index is what the throwaway-pg verify,
  the fresh CI test DB, and any fresh stack apply; reset the dev volume to converge it. **Known-deferred
  (carried):** `updated_at` has no `onupdate` (the category labels deliberately omit `updated_at`). **Pickup:
  PRIV-6b.**

- **PRIV-5b (PR #104) — Transfer entity (third-country transfers + safeguards) + the restricted⇒mechanism invariant. Migration 0061.**
  Fills the second clause of Article 30(1)(e) — the **last** of PRIV-5's two coverage lines. A **`Transfer`** is a
  **child of one processing activity** (required FK, **CASCADE** — the Art 30 structure) with an **optional recipient
  vendor** (`vendor_id`, ON DELETE SET NULL). **Headline ADR-F018 invariant:** a **restricted** transfer (recipient
  outside the UK/EEA) **requires** a Chapter V `mechanism`; a non-restricted one **must not** carry one — mirrored in
  **`TransferInput`** (`model_validator`, both directions) AND a DB **CHECK** (`chk_transfers_restricted_requires_mechanism`),
  exactly like `special_category ⇔ art9_condition`. **`restricted` is DECLARED** (set by agent/code), NOT derived from a
  maintained adequacy list (plan § Decisions — drifts as adequacy regs change). **Domain:** `TransferMechanism` StrEnum
  (adequacy_regulations/standard_contractual_clauses/uk_idta/binding_corporate_rules/derogation); `TransferInput` write
  contract; `TransferSummary` rides **`ProcessingActivityRead.transfers`** (with nested recipient `vendor`). ORM `Transfer`
  + 4 CHECKs (destination len, mechanism-in-set, the invariant, details len) + `_TRANSFER_MECHANISMS` literal mirror
  (model + migration — the established enum-mirror pattern). **Migration 0061** (head 0060→0061) — **verified up/down/up on
  a throwaway pgvector** (table + 4 CHECKs + 3 FKs + `ix_transfers_processing_activity_id` on up, gone on down, back on
  re-up); applied to dev DB by rebuilding api+arq-worker+ingest-worker together (dev head = 0061). **Agent tools** (now
  **10** — `ROPA_TOOL_NAMES`): `propose_transfer` (validates content incl. the invariant FIRST, then resolves the parent
  activity (required) + optional vendor FKs against the register — reject-and-retry on either; `source_project_id`
  closure-injected B-class) + `list_transfers`; both guarded (R5/R6 + audit). Composition grants them automatically (the
  composition point uses `build_ropa_tools`'s **returned list**, not a hardcoded count — no `composition.py` change).
  **Read API:** transfers eager-loaded (`selectinload(.transfers).selectinload(Transfer.vendor)`) on all 3 activity
  queries (list/detail/export). **NO standalone `/ropa/transfers` endpoint or register tab** (a transfer has no meaning
  detached from its activity → surfaces inside the activity detail + export; **route count stays 136**, no contract-test
  churn). **Export** (`ropa_export.py`): a **Transfers column** on the activity row (restricted → `"dest — mechanism"`,
  non-restricted → `"dest (not restricted)"`) + a **Transfers sheet** (flattened from activities' nested transfers — one
  row per transfer with parent-activity name, recipient, safeguard details; **no separate fetch/DTO**); mechanism
  humanizers (SCCs / UK IDTA / BCRs / Derogation (Art 49)); `_csv_safe` on every new cell (CSV + XLSX). **Coverage note
  dropped the transfer line** → now **2** (data-subject + personal-data taxonomy, PRIV-6). **Web** (`api/ropa.ts` +
  `components/ropa/`): `TransferMechanism`/`TransferSummary` types + `transfers` on `ProcessingActivityRead`;
  `transferMechanismLabel`; a **Third-country transfers** section in `ProcessingActivityDetail` (Restricted/mechanism
  badges + "Not restricted" marker + recipient cross-link to the vendor). **Verify:** migration throwaway up/down/up;
  **full api suite 2248 passed / 10 skipped** (+21 over PRIV-5a); ruff + mypy clean (166 files); web svelte-check **0 err**
  + vitest **879** (+2); **LIVE on dev stack** (head 0061): seeded 1 restricted (US/SCCs + recipient) + 1 non-restricted
  (Germany) transfer — **the DB CHECK rejected an inconsistent restricted-without-mechanism INSERT live**; read API +
  all 3 export formats reflect them (XLSX = **4 sheets** incl. Transfers; CSV Transfers column; coverage 2 lines);
  **screenshots `docs/fork/evidence/priv-5b/`** (restricted + non-restricted activity detail). **Fresh-context review (3
  parallel finders — correctness / removed-behavior+cross-file / security+simplification): 0 blockers, 0 correctness
  defects, security all-PASS.** The `adequacy_regulations` label intentionally falls back to `_humanize` (correct output);
  the enum-mirror tuple + the link/resolve patterns are the documented deliberate ROPA pattern. **No new ADR** (under
  ADR-F018/F019). **Known-deferred (carried):** `updated_at` has no `onupdate` (now also `transfers`). **Pickup: PRIV-6.**

- **PRIV-5a (PR #103) — Vendor (recipient) entity + recipients in the Article 30 export. Migration 0060.**
  Extends the ADR-F019 graph with the Article 30(1)(e) **categories of recipients** axis (F019 named this slice).
  **Domain:** new `Vendor` (`app/models/ropa.py`) — **lean by maintainer decision** (name, `vendor_role`,
  `description`, `country`, `dpa_status`; **risk DEFERRED to the assessment track PRIV-A1**, not an inventory
  field) + `processing_activity_vendors` **M:N** (mirrors `processing_activity_systems`: composite PK, CASCADE
  both ends, index on `vendor_id`); Pydantic **`VendorInput`** write contract (`VendorRole`/`DpaStatus`
  StrEnums, `extra="forbid"`, blank-optional→None) + `VendorRead`/`VendorSummary` read DTOs; `vendors` rides
  `ProcessingActivityRead`. CHECK mirror in the model + migration (the established literal-tuple pattern —
  `_VENDOR_ROLES`/`_DPA_STATUSES`, like `_SYSTEM_TYPES`). **Migration 0060** (head 0059→0060) — **verified
  up/down/up on a throwaway pgvector** (2 tables + 5 CHECKs + index appear on up, gone on down, return on
  re-up); applied to the dev DB by rebuilding api+arq-worker+ingest-worker together (dev head = 0060).
  **Agent tools** (`app/agents/ropa_tools.py`, now 8 — `ROPA_TOOL_NAMES` extended): `propose_vendor` (code-
  validated write — validates `VendorInput`, reject-back-to-model on failure), `link_vendor_to_activity`
  (recipient M:N link, membership-checked, idempotent), `list_vendors`; all guarded (R5/R6 + audit),
  `source_project_id` closure-injected B-class, model-facing signatures A-class-only. **Read API**
  (`app/api/ropa.py`): `GET /ropa/vendors` + `/vendors/{vendor_id}` (shared-read `_active`, ADR-F019 — 404 =
  missing id only); activity reads `selectinload` vendors. **Export** (`app/ropa_export.py`): **Recipients
  (Art 30(1)(e)) column** on the activity row + a **Vendors sheet** in the XLSX; `Article30Export` gains
  `vendors`; **coverage note dropped the "Categories of recipients" line** (transfers → PRIV-5b, data-subject/
  data-category taxonomy → PRIV-6 remain, honestly); `_csv_safe` guards every new cell (CSV + XLSX). **Web**
  (`api/ropa.ts` + `components/ropa/`): wire types + `listVendors`/`getVendor`; **Vendors register tab** + table;
  `VendorDetail.svelte`; **Recipients** cross-link section in `ProcessingActivityDetail`; `format.ts`
  humanizers. **Verify:** migration throwaway up/down/up; **full api suite 2226 passed / 10 skipped** (+16 over
  PRIV-4a; +1 unit test post-review = 2227, re-run pending in PR CI); ruff + mypy clean (166 files); web
  svelte-check **0 err** + vitest **877**; **LIVE on dev stack** (head 0060): `/ropa/vendors` 200, recipients on
  the activity, all 3 export formats download (XLSX = **3 sheets** incl. Vendors), Recipients column + shrunk
  coverage note confirmed, bad-format 422 / no-auth 401 / missing-id 404; **screenshots
  `docs/fork/evidence/priv-5a/`** (Vendors tab + activity Recipients). Global contracts updated (route
  **134→136**; `_PARAM_VALUES += vendor_id`). **Fresh-context review (3 parallel finders — correctness /
  removed-behavior+cross-file / security+simplification): 0 blockers, 0 correctness defects.** Applied 2
  non-blocking fixes: export `none`→**"No DPA on record"** (was bare "None", ambiguous next to blank cells) +
  `VendorDetail` heading "Discloses from"→**"Receives data from"**. **Accepted/deferred (documented):** the
  `_link`/`_link_vendor` duplication + the role/status tuple copied across enum+model+migration are the
  **pre-existing deliberate ROPA pattern** (literal mirror with an explaining comment; System↔Vendor by design)
  — a cross-cutting enum-mirror test is a good later follow-up, out of this slice. **No new ADR** (implementation
  of accepted ADR-F018/F019). **Known-deferred (carried):** `updated_at` has no `onupdate` (fix when an edit
  path lands — now also `vendors`). **Pickup: PRIV-5b** (Transfer entity + the invariant).

- **PRIV-4a (PR #102) — SHIPPED. Article 30 RoPA export (JSON / CSV / XLSX). Read-and-render, no migration.**
  The extractable RoPA deliverable over the PRIV-3 deployment-global register (ADR-F019). **`GET
  /ropa/export?format=json|csv|xlsx`** (`app/api/ropa.py`, shared-read `_active`; typed `ExportFormat` enum,
  off-enum→422; `selectinload`ed). Pure formatter **`app/ropa_export.py`**: JSON envelope (machine/queries),
  CSV (one row per activity, systems joined), XLSX (OneTrust's two-sheet shape — Processing Activities +
  Systems). **`openpyxl` was already a dep** (Tabular Review) — no new SBOM entry; lazy-imported. **OWASP
  CSV-injection guard on every cell in BOTH CSV and XLSX** (register holds untrusted model-proposed strings).
  **Honest Article 30(1) coverage note** names the not-yet-captured fields (data-subject/data categories,
  recipients, third-country transfers — PRIV-5); renders what exists, never falsely complete. Web:
  `downloadArticle30()` + a new `apiBlobRequest` (auth + refresh-on-401) + a calm Excel/CSV/JSON export control
  in `RopaRegister.svelte` (F013). New schema field is **`register_name`** (not `register` — that shadows a
  pydantic `BaseModel` attr). **Verify:** full api suite **2210 passed / 10 skipped**; ruff+mypy clean (166
  files); web check 0 err + vitest **875**; LIVE-verified (all 3 formats 200, coverage note, CRM label,
  bad-format 422, no-auth 401; screenshots `docs/fork/evidence/priv-4a/`). Global contracts updated (route
  133→134). Fresh-context security review: **0 blockers** (both fixes applied: `register_name` rename; XLSX via
  plain `Response`). **No new ADR** (under ADR-F019). **Known-deferred (carried from PRIV-3):** `updated_at` has
  no `onupdate` — fix when an edit/UPDATE path lands (PRIV-6+).

- **PRIV-3 (PR #101) — SHIPPED. Two-tier relational ROPA spine + read UI + read API (ADR-F019 accepted).** Two-tier
  **relational, deployment-global**
  ROPA inventory + the **read UI** (the "lead with the read UI" slice; maintainer chose the richer scope over a
  flat list — see decision trail in `docs/fork/plans/PRIV-3-ropa-read-ui-and-relational-reshape.md`). **ADR-F019**
  (accepted): relational two-tier graph **System ↔ ProcessingActivity (M:N)**, scoped **deployment-global** (LQ.AI
  is single-tenant — an in-house team's one client is its own org, so the deployment IS the org; no `organizations`
  table). This **SUPERSEDES PRIV-1's matter-scoping**: `processing_activities` **drops `project_id`**, adds nullable
  `source_project_id` (provenance only, `ON DELETE SET NULL`). **Migration 0059** (head 0058→0059) creates `systems`
  + `processing_activity_systems` and re-scopes `processing_activities` — **verified up/down/up on a throwaway
  pgvector container**; applied live by rebuilding api+arq-worker+ingest-worker (dev DB head = 0059). **Domain:**
  `app/models/ropa.py` (System + M:N + relationships), `app/schemas/ropa.py` (`SystemType`/`SystemInput` write
  contract + `*Read` DTOs). **Agent writes reworked + extended** (`app/agents/ropa_tools.py`, 5 guarded tools):
  `propose_processing_activity` (now global; stamps `source_project_id`), `propose_system`,
  `link_processing_activity_to_system`, `list_processing_activities`, `list_systems` — all code-validated
  (reject-and-retry), guarded (R5/R6 + audit). **Read API** (`app/api/ropa.py`, mounted `_active`): `GET
  /ropa/processing-activities` + `/systems` (+ `/{id}` detail with cross-links), `selectinload`ed. **Authz (ADR-F019,
  a deliberate divergence — documented, not a hole):** the register is the company's SHARED record, so reads need
  only an active firm user; **cross-user→404 does NOT apply to the register** (it still protects private matters);
  404 = a missing record id only. **Web** (fork-built): `lib/lq-ai/api/ropa.ts` client + a minimal
  `components/ui/table/` primitive + `components/ropa/RopaRegister.svelte` (two-tier: Processing activities | Systems,
  badges, honest empty states) + `ProcessingActivityDetail`/`SystemDetail` (cross-links) + `format.ts` humanizers;
  integrated in `cockpit/ConversationHost.svelte` via a **Conversation | ROPA register** toggle shown when
  `matter?.practice_area_key === 'privacy'`. **F013 style, NOT Oscar/OneTrust's look.** Read-only — the agent writes,
  the user owns. **Verify:** migration throwaway-verified; **api 51 ROPA tests pass** (`tests/test_ropa.py` +
  `tests/test_ropa_read.py` + reworked `tests/agents/test_ropa_tools.py` + composition test), **ruff clean** (repo
  root); **web `npm run check` 0 errors + 11 vitest**; **LIVE-verified on http://localhost:3000** (seeded demo matter
  "Programme — GDPR / ROPA" under admin@lq.ai: 4 systems / 3 activities / 6 links; **screenshots
  `docs/fork/evidence/priv-3/01-07`**). **Ship gate (ADR-F005) — PASSED:** all 3 CI checks green (Web + Gateway +
  API); the full containerized api suite **2202 passed / 9 skipped** (the +5 over the first run = the global
  contract tests now register the 4 read routes — see below); ruff + mypy clean (root `ruff.toml`, line-length 100,
  165 files); web check 0 err + 11 ropa vitest; fresh-context adversarial+security review **SHIP / 0 blockers**
  (shared-read authz divergence is documented in ADR-F019, keys gateway-only, agent writes code-validated with
  closure-injected B-class IDs, migration 0059 reversible). **CI caught 5 failures a ROPA-subset local run missed**
  (now fixed in the PR): mypy `union-attr` in `_link` (added a narrowing `assert`); and the two GLOBAL contract
  tests that enumerate every route — `tests/test_endpoints.py` (`_PARAM_VALUES` += `activity_id`/`system_id`;
  `IMPLEMENTED_ROUTES` += the 4 `GET /ropa/*`) + `tests/test_openapi.py` (`EXPECTED_PATHS` += the 4 paths; route
  count 129→133). **Lesson: run the FULL `pytest -q` (not just the slice's test files) before pushing — new
  endpoints trip the route-coverage + OpenAPI-sketch contracts.**
  Also logged this session: **`docs/fork/plans/PRIV-onetrust-to-lqai-functionality-map.md`** — the full OneTrust→LQ.AI
  capability map (P0 in-flight / P1 flagship / P2 tracks / **P3 deferred**: consent platform, cookie CMP, data-store
  discovery, regulatory RAG — maintainer-confirmed non-goals). The **differentiator** = conversational-link
  assessments (send a link → SME talks to the agent → code-validated ROPA writes) — needs **ADR-F020**. And a
  **DeepSeek dev-provider experiment** (dev-ONLY: `docker-compose.yml` `DEEPSEEK_API_KEY` passthrough + `harness.py`
  `LQ_AI_SCENARIO_MODEL` override; live gateway config is gitignored). NB: MiniMax + DeepSeek are **dev models only**
  — clients run a Western model via the gateway ([[llm-is-injected-replaceable]]).
  **Known-deferred nits (from the PRIV-3 review, NOT blockers — pick up in a later slice):** (1) `systems` +
  `processing_activities` carry `updated_at` with a `server_default now()` but **no `onupdate`** and there is no
  edit path yet, so `updated_at` always equals `created_at` — add `onupdate` (or a trigger) when the edit/UPDATE
  path lands so a future "last modified" UI isn't misled; (2) `harness.py` reads `LQ_AI_SCENARIO_MODEL` from raw
  `os.environ` rather than via settings/DI (test-only knob, accepted).

- **PRIV-2 (PR #100) — SHIPPED. Validated agent write path. API-ONLY (no migration, no web).** Wired
  the PRIV-1 ROPA domain onto the **Privacy** practice-area Deep Agent: the ADR-F018 *agent proposes → code
  disposes* loop is now live end-to-end. New **`app/agents/ropa_tools.py`** (`build_ropa_tools`, mirroring
  `build_matter_tools`) builds two guarded tools, granted ONLY to a matter filed under the Privacy area:
  **(1) `propose_processing_activity`** — the **code-validated write**: the model's proposal is validated
  against `app/schemas/ropa.py ProcessingActivityInput` (the PRIV-1 contract) BEFORE any commit; a valid one
  is written, an invalid one is **rejected back to the model as tool-result text** carrying the field+reason
  (Pydantic `errors()` → fix-and-retry) — never a silent write, never a silent fix. A rejection is **returned,
  not raised** (the dispatch succeeded; the *write* was refused), so the model reads the reason and re-proposes.
  The write `flush`es inside the guard's session so the DB CHECK mirror (PRIV-1 defense-in-depth) surfaces as
  an audited error, and the row commits atomically with its audit row. **(2) `list_processing_activities`** —
  the matter's current register (zero-arg; oldest-first; `_LIST_LIMIT=100`). **Wiring:** `composition.py`
  captures `area_key` when the matter's area loads and appends the ROPA tools when `area_key == PRIVACY_AREA_KEY`
  (`"privacy"`) — area-keyed tool selection at the composition point (the area row IS the agent identity,
  ADR-F002); other areas never grant them. **Authz:** `project_id`/`user_id` are B-class (closure-injected,
  never model-visible, ADR-F004); every row is scoped to `binding.project_id`, which composition already
  resolved AFTER asserting `Project.owner_id == run.user_id` — the model cannot name another project, so there
  is **no cross-matter/cross-user vector at the tool layer** to leak (the project-ownership 404 posture belongs
  to the PRIV-3 read API, where a project id is user-supplied). Guard R5/R6 still mediate every dispatch; no
  gateway bypass. **Tests** (`tests/agents/test_ropa_tools.py`, +N; plus 1 composition test): valid proposal
  commits one row with the proposed values (+ a special-category-with-Art9 happy path); off-enum basis / blank
  retention / special-without-Art9 / Art9-without-special each rejected with NOTHING written and the reason
  surfaced; `list` empty→reflects-proposals; the **guard/audit contract** (one `agent_run.tool_call` row per
  dispatch carrying counts/types/IDs — never the proposal's purpose/retention text; a code-rejected write is
  still an audited successful *dispatch*); the model-facing signature pin (A-class args only); and the
  **end-to-end real-loop** test (scripted model proposes a valid then an invalid entry → run completes, exactly
  the valid row persisted, the rejection surfaced as a tool result). The composition test files the matter
  under Privacy and proves the real composition point grants + dispatches the validated write. **Verify:**
  containerized api suite **2181 passed / 2 skipped** (was 2169 at PRIV-1; **+12** = the new
  `test_ropa_tools.py` tool/guard/audit/real-loop tests + 1 composition test; 8 provider/live-gateway scenario
  tests deselected here — they `skipif` in CI; `tests/agents/` alone = 231 passed / 8 deselected); ruff check +
  `ruff format --check api scripts` clean (root `ruff.toml`, line-length 100 — run from the REPO ROOT); mypy
  `app` clean (164 files). **No new migration** (0058 already landed); **no ADR** (this IS the implementation
  of accepted ADR-F018). Fresh-context security+simplification pass: no secrets; ORM/parameterized queries
  only (no string SQL); rejection text bounded (field locs + Pydantic msgs, no raw input echo) and kept OUT of
  the audit row; model can't influence `project_id`; dropped a misplaced "unknown-field" tool test (a
  hallucinated field hits the tool's fixed signature before Pydantic — `extra="forbid"` is covered at the
  schema layer in `tests/test_ropa.py`). **Pickup: PRIV-3** (thin vertical + the ROPA register read UI + first
  export). **Compact after this slice (maintainer rule).** NB for PRIV-3: the Privacy area's `profile_md`
  doesn't yet instruct ROPA maintenance — enrich it (data, not code) so a live model knows to use these tools;
  and confirm the qualified model can call a zero-arg tool (`list_processing_activities`).

- **PRIV-1 (PR #99) — SHIPPED. ROPA domain spine + code validation (no agent yet). API-ONLY.** The first
  **typed domain** of the Privacy module (ADR-F018). New **`processing_activities`** table (migration
  **0058**, head 0057→0058; DDL only, no seed — per-matter data): one Article 30 GDPR record per row, scoped
  to a Privacy matter (`projects.id`, ON DELETE CASCADE). Columns: `name`/`purpose`, `lawful_basis`,
  `controller_role`, `retention`, `special_category`, `art9_condition`. **The ADR-F018 headline — code
  validation — lands in two mirrored layers:** (1) **`app/schemas/ropa.py` `ProcessingActivityInput`** — the
  Pydantic **validation contract** (the single source of the invariants the PRIV-2 write path will validate a
  model proposal against before commit): `LawfulBasis` (Art 6(1)) / `Art9Condition` (Art 9(2)) /
  `ControllerRole` StrEnums, `retention` required (non-blank), and the headline invariant
  **`special_category ⇔ art9_condition`** (both directions, `model_validator`), `extra="forbid"`
  (reject-don't-sanitize); (2) **`app/models/ropa.py` `ProcessingActivity`** ORM + the SAME invariants as DB
  **CHECK constraints** (defense-in-depth, the `projects.privileged⇒tier` precedent) so an inconsistent row
  is refused even if a caller bypasses the schema. Enum-ish columns are `Text` + a CHECK against the allowed
  set (not a PG ENUM) — the Pydantic enum is authoritative; a CHECK is cheap to evolve. **NO agent wiring, NO
  endpoint** (PRIV-2 adds the guarded validated-write tool + the project-ownership authz cross-user→404).
  **Verify:** migration **verified up AND down on a throwaway pgvector container** (never the dev DB) — all 7
  CHECK constraints present after upgrade, table gone after downgrade; containerized api suite **2169 passed /
  10 skipped** (was 2158 at UX-B-4; **+11** = `tests/test_ropa.py`: 8 pure invariant accept/reject + 3 DB
  defense-in-depth incl. CASCADE matter scoping + CHECK rejection); ruff check + `ruff format --check api
  scripts` clean (root `ruff.toml`, line-length 100 — NB run ruff from the REPO ROOT so it finds the config,
  not from `api/`), mypy clean. Fresh-context security+simplification pass: no secrets; `_in_set` interpolates
  only hardcoded GDPR constants (no user input → no SQL-injection surface); no new endpoint → no authz surface
  this slice; dropped a speculative unused `ProcessingActivityRead` + a redundant model `index=True` (the
  migration owns the index). **Module-UI requirement recorded (maintainer 2026-06-18):** a module must render
  its domain UI like the reference product — users must SEE the OneTrust/TrustArc-equivalent ROPA register in
  the cockpit, not just an export (PRIV decomposition § Module UI requirement; PRIV-3 read view → PRIV-4+ full
  programme cockpit). **Pickup: PRIV-2.** **Compact after this slice (maintainer rule).**

- **PRIV-0 (PR #98) — SHIPPED. Privacy/ROPA module: plan + ADR-F018. DOCS-ONLY.** Opened the first agentic
  **module** milestone of **LQ.AI Oscar Edition** (maintainer "Go" 2026-06-17: privacy first, redlining next).
  **ADR-F018 (proposed):** a *module* = a practice area + a **typed domain** + **code-validated agent writes**
  (agent proposes → deterministic code validates → commit, or rejects back to the model — never silent
  write/fix; the headline improvement over the reference product **Oscar Privacy**, which trusted the model's
  writes). Oscar is **reference-only** (take the idea + domain, reimplement + improve; ICO RAG + Oscar's
  single-call/fixed-action engine dropped). **Honest grounding correction:** CLAUDE.md blocker #5 ("practice_
  area/unit_of_work appear nowhere") is **stale** — `practice_areas` + matter binding (`projects.practice_area_id`,
  `context_md`) shipped in F1-S3; what's missing is only the **typed ROPA domain + validated write path**, so
  the foundation is small. Decomposition `docs/fork/plans/PRIV-privacy-ropa-module-decomposition.md`: PRIV-0 →
  PRIV-1 (ROPA domain spine + code validation) → PRIV-2 (validated agent write path) → PRIV-3 (thin vertical +
  ROPA export + scenario calibration) → PRIV-4+ (broaden). **Working rule (maintainer): short slice → compact
  → short slice.** Redlining = the NEXT track (adeu MIT render layer + a redline-like-a-lawyer skill).
  **Pickup: PRIV-1.**

- **UX-B-6 (PR #95) — SHIPPED. Verify + consistency sweep — the UX-B closer. DOCS-ONLY (no app/web/api
  change).** Re-verified every cross-slice claim against the **live dev DB (read-only `SELECT` — never an
  `alembic upgrade`, never `down -v`)**: all 5 areas `configured` + non-empty `profile_md`; tier floors NULL
  (M3 is the only S9-qualified model, tier 4); skills bound per area (0056 — Commercial 4 / Disputes 2 /
  M&A 3 / Privacy 3 / Employment 3, exact names verified); Commercial's `document-researcher` subagent
  present (0057) with skills `[contract-qa, nda-review]` ⊆ its 4 bound skills (the **ADR-F017 subset rule
  holds in stored data**, not just at PATCH); cockpit honest (UX-B-5). **No drift between docs and the
  running stack.** Wrote the **milestone behavior-report index** `docs/fork/evidence/UX-B-MILESTONE-INDEX.md`
  — the honest map tying UX-B-1…5 together: what MiniMax-M3 *does* (grounds+cites, declines honestly,
  clarifies, answers general directly) vs does *not* do reliably (multi-step efficiency varies; a broad ask
  over a large skill surface can `cap_exceeded` — UX-B-3 1/2 completed; doesn't *elect* to delegate at small
  matter sizes — UX-B-4 `task_calls=0`, machinery proven deterministically in CI not by a live run), plus
  the per-area scenario snapshot totals. The open calibration question (does a tier-4 model fan out on a
  genuinely large matter?) recorded as **backlog** in `MILESTONES.md` — NOT built (a forced delegation would
  game the ADR-F015 qualification). **Verify:** no code touched (3 docs: the index + decomposition UX-B-6
  entry + MILESTONES backlog line) → no suite to run; security pass: docs carry only area keys / skill names
  / scenario counts (no secrets, no raw values; the DB output surfaced is operator-authored config). **UX-B
  is COMPLETE — the agentic-modules / Oscar-Privacy direction is unblocked as its own milestone.** **Pickup:
  the modules direction (its own milestone) or deferred F2 debt — see Next slice.**
- **UX-B-5 (PR #94) — SHIPPED. Cockpit perfection (web): the proven loop surfaced honestly. WEB-ONLY — no
  api/gateway change** (every datum already on the wire; this slice only consumes it). Three deliverables on
  the F013 design language (ADR-F012/F013 — Vercel charcoal #111 + scarce blue):
  **(1) Area selection at matter creation** — `NewMatterDialog` gained an explicit practice-area **picker**
  (configured areas only, ADR-F002; defaults to the contextual area; the dialog noun/title follow the chosen
  area's `unit_label`; posts the chosen area's `id` as `practice_area_id`). Threaded a new
  `configuredAreas` derived from the cockpit context into `MattersPanel` + both `ConversationHost` renders →
  the dialog. The matter→area binding that drives the whole server-side agent identity (`composition.py`) is
  now **explicit + visible** at creation, not implicit-from-navigation.
  **(2) Subagent boundary rendering** — a new pure **`groupTurnTree(rows)`** (in `agents/helpers.ts`) folds a
  `task` tool-call + its contiguous `parent_step_id`-nested children + the task's result into ONE labelled
  **"Delegated to `<subagent_type>`"** boundary block (`subagentTypeOf` parses the type from the call's
  bounded args digest — runner.py emits `json.dumps({description, subagent_type})`). **Honest by
  construction:** the boundary renders ONLY when a `task` step exists (delegation actually occurred); a turn
  with no delegation stays flat — the common tier-4 case (M3 doesn't elect to fan out at small matter sizes,
  UX-B-4). The flat row content (AE6 Tool card / reasoning) was factored into **`StepRow.svelte`** so a
  top-level row and a nested child render identically — the parent `ConversationPanel` uses legacy `<slot>`,
  so a `{#snippet}` there is **illegal** (`slot_snippet_conflict`); a child component is the clean share.
  **Net code reduction** (−248/+ in ConversationPanel), **no DOM/testid change** (`lq-ai-agents-tool`/
  `-task`/`-tool-status` preserved; `.ag-step` count = `rows.length` unchanged) — ae6 Tool/Task regression
  **7/7**. **The SSE protocol gap (CLAUDE.md blocker #4) was NOT needed** — `parent_step_id` already rides
  every `data-step` part (F0-S7), so the boundary renders live AND on replay with no protocol change; a
  dedicated subagent/tool frame TYPE stays follow-up (the HANDOFF-blessed scoping decision, held).
  **(3) Area-config visibility (read-only)** — new **`AreaConfigDisclosure.svelte`** in the matters-panel
  header (collapsed by default): the area's PROFILE (rendered through the shared `renderModelMarkdown`
  sanitiser — operator-authored but treated as untrusted-class input, one media-forbid policy), bound SKILLS
  as chips, and SUBAGENTS (name + description + each one's ⊆-area skill subset, ADR-F016/F017) + an honest
  on-demand-delegation note. Satisfies the transparency rule; data from `GET /practice-areas` (no api
  change). New pure **`areaSubagents(agent_config)`** (in `cockpit/helpers.ts`) parses the opaque
  `Record<string,unknown>` config DEFENSIVELY (display-only). **Admin PATCH editor DEFERRED** (own slice —
  needs a web PATCH client + client-side mirroring of the server validation ADR-F017/F010; read-only
  satisfies transparency). **Verify:** `npm run check` **0 err** (5 pre-existing a11y warnings, unchanged
  baseline); **vitest 861** (+10: `groupTurnTree`/`subagentTypeOf` in agents-helpers + `areaSubagents` in
  cockpit-helpers); web container rebuilt; **headed Cypress `ux-b-5-cockpit.cy.ts` 2/2** + **ae6 regression
  7/7** (light+dark × wide+narrow). Evidence `docs/fork/evidence/ux-b-5/`: area-config + area-pick captured
  **LIVE** (Commercial — real profile/skills/`document-researcher`); the delegation boundary **STUBBED** (a
  fixtured delegated run — M3 won't reliably fan out at small matter size, ADR-F015/UX-B-4, so the
  deterministic `groupTurnTree` unit test is the gate, the stub renders the boundary for the screenshot).
  Fresh-context security+simplification pass: no secrets (Cypress fixture synthetic, no creds); `{@html}`
  only behind the sanitiser; read-only config (no PATCH); no new deps; no `--lq-*` color tokens in new files;
  dead `toolView`+CSS removed from ConversationPanel (moved to StepRow). **Pickup: UX-B-6** (verify +
  consistency sweep — see Next slice).
- **UX-B-4 (PR #93) — SHIPPED. Live subagent (on-demand delegation), via the idiomatic deepagents
  per-subagent skill-source model (ADR-F017 accepted).** Commercial gained its first live subagent —
  `document-researcher` (migration **0057**, idempotent: writes only where `agent_config = '{}'`) — a GENERAL
  delegate the lead agent fans out to **on-demand** (the parent's deepagents `task` tool fires only when a
  matter warrants it: a single NDA is read directly; a complex multi-document RFQ is delegated). **Research
  first (maintainer steer):** re-read the deepagents docs/source before coding — they overturned the initial
  "subagent inherits the area set" sketch. deepagents shares the `backend` only as the file substrate, but
  **skill discovery is isolated per subagent**: a custom subagent gets a SkillsMiddleware only if it declares
  its own `skills` SOURCE PATHS (`graph.py:628-630`); *"custom subagents don't inherit parent skills."* So the
  idiomatic fix = give each subagent its OWN virtual source. **Generalised `RegistrySkillBackend` to
  multi-source** (`sources: {source_path: {name: SKILL.md}}`): the lead agent sees the area subset at
  `/skills`; each skill-bearing subagent sees only its (⊆ area) subset at `/skills/subagents/<name>`. The
  composition seam `build_area_skill_wiring` builds the one shared backend + rewrites each subagent's skill
  NAMES → its source path (⊆ area enforced: **rejected at PATCH**, dropped-not-fatal at render — the UX-B-3
  drift posture; registry None → skills stripped so no bogus source reaches deepagents). Subagent carries NO
  `model` (inherits gateway-bound parent, ADR-F010 guard re-asserts) and NO `tools` (inherits guarded matter
  tools). Removed the now-dead `build_area_skill_backend` (the wiring subsumes it). Harness gained
  **multi-document seeding** (`seed_multi_doc_matter`) + **delegation observations** on `Receipt`
  (`task_calls`/`delegated`/`ancestry` from `parent_step_id`). **Verify:** scripted suite **2158 passed / 10
  skipped** (0 errors; +10 vs UX-B-3's 2148 — multi-source backend + wiring + drift + the deterministic
  ancestry gate + 0057 migration tests; +1 self-skipping provider test) — the CI gate is
  `test_subagent_delegation_nests_steps_via_parent_step_id` (scripted `task` delegation → a `task` step with
  subagent steps **nested via `parent_step_id`**, F0-S7); ruff+mypy clean; dev stack migrated **0056→0057**
  (api+arq-worker+ingest-worker rebuilt together; Commercial shows `document-researcher`). **Live MiniMax-M3
  re-qualification (`docs/fork/evidence/ux-b-4/`, ADR-F015 — kept verbatim, NOT tuned green):** both RFQ
  scenarios `completed`; M3 correctly did NOT delegate the single fact (answered directly, cited), and ALSO did
  NOT delegate the 4-document review — it read all four docs itself and produced a structured comparison
  (`task_calls=0`). **The delegation plumbing is proven deterministically (CI); a tier-4 model just doesn't
  *elect* to fan out at this matter size** (4 short docs fit one context) — the honest finding; forcing it
  would be gaming. Fresh-context security+simplification pass: no secrets (migration is data-only, no creds;
  report carries observations only); no gateway bypass; backend stays read-only/allow-listed/no-host-FS; dead
  code removed. **Pickup: UX-B-5** (cockpit web — see Next slice).
- **UX-B-3 (PR #92) — SHIPPED. Skills activation (S9), via a read-only registry-backed virtual backend
  (ADR-F016 accepted).** Corrected the long-standing HANDOFF premise: **`SkillsMiddleware` adds no tools** —
  it `ls`/`download`s a deepagents *backend* and the model reads each `SKILL.md` via the **builtin
  `read_file`**; those builtins already exist on our agent over an empty `StateBackend` and are **not** wrapped
  by `guarded_dispatch` (the full-universe guard wrap is F1, out of scope). So activation = give the agent a
  **backend** carrying the area's skills + `skills=[sources]`, and the security boundary is **what the backend
  exposes**. **Maintainer-ruled architecture (ADR-F016):** one library, **no duplication** (areas reference
  skills by name), **subset per agent** (the whole library confuses the model), **relevant skills by default +
  user-extend**. Built **`app/agents/skill_backend.py`** (`RegistrySkillBackend`) — a read-only
  `BackendProtocol` adapter over a `SkillRegistry` snapshot serving ONLY the area's bound subset as a virtual
  `/skills/<name>/SKILL.md` tree (zero-copy; reaches no host FS / matter data / unbound skills; `read()`
  windows by offset/limit per the StateBackend contract; mutations refused; drift closes structurally — a
  bound name the registry forgot is absent). **Composition** (`composition.py`) gained a
  **`skill_registry_provider`** seam (default reads the worker/api `app.state.skill_registry` holder — the
  autonomous-executor precedent; runs execute in the arq worker which installs it at `on_startup`), loads the
  area's `practice_area_skills`, renders `render_area_agent(bound, known)`, builds the backend over the
  resolved subset, threads **`skills`+`backend`** → `execute_agent_run` → `build_deep_agent` →
  `create_deep_agent` (ADR-F010 subagent guard still runs; skills/backend carry no model → no gateway bypass).
  Dropped the `composition.py:151 bound_skill_names=[]` stub. **Migration `0056`** seeds focused default
  bindings per area (idempotent, insert-only-when-absent; symmetric downgrade removes only seeded pairs):
  Commercial 4 (msa-review-commercial-purchase/msa-review-saas/contract-qa/nda-review), Privacy 3
  (dpa-checklist-review/vendor-privacy-policy-first-pass/contract-qa), M&A 3 (nda-review/contract-qa/
  contract-snapshot), Disputes 2 (contract-qa/action-items-from-client-alert), Employment 3 (contract-qa/
  nda-review/action-items). **Drift gap closed:** `build_area_subagents(known_skill_names=…)` rejects a
  subagent referencing an unknown skill at PATCH time (best-effort — skips if no registry installed, never
  404s the PATCH). **Live skills-on re-qualification** (`docs/fork/evidence/ux-b-3/`, real MiniMax-M3): the
  **mechanism works** — the model reads the bound SKILL.md via the backend (5× `read_file` in one run);
  **focused** review still grounds+cites cleanly (`completed`), but a **broad** "structured risk review"
  over-explores to **`cap_exceeded` with no answer** — an honest calibration finding (the expanded surface
  amplifies M3's known multi-step inconsistency), **kept verbatim, not tuned away**. **Verify:** scripted suite
  **2148 passed / 9 skipped** (clean re-run, 0 errors; +18 vs UX-B-2's 2130 — backend/drift/composition/
  migration tests; the 9th skip = the new provider scenario test self-skipping without a key); migration verified on the conftest
  throwaway test DB; ruff+mypy clean; **dev stack migrated 0055→0056** (api+arq-worker+ingest-worker rebuilt
  together; all 5 areas show their bindings). The 22 `asyncpg` setup errors in the first full-suite run were
  **environmental** (I rebuilt the dev stack + ran the live harness on the same Postgres concurrently) — the
  errored clusters (auth/audit/admin/watches, untouched by this diff) re-ran **75/75 clean** in isolation; a
  clean re-run confirms the count. Fresh-context adversarial+security+simplification review: **SHIP-WITH-NITS**
  (1 should-fix — `read()` offset/limit windowing — FIXED in-slice + tested; 1 nit accepted). No secrets in
  code/migration/reports. **Pickup: UX-B-4** (live subagent — see Next slice).
- **UX-B-2 (PR #91) — SHIPPED. Sensible default practice areas, calibrated to the UX-B-1 baseline
  (ADR-F002/F004/F015).** Gave the four remaining standard areas — **Disputes / M&A / Privacy /
  Employment** — a real `profile_md` via the **idempotent migration `0055_default_area_profiles.py`** (the
  0054 pattern: write only where `profile_md IS NULL`, so re-running never clobbers an operator edit; sets
  the stored `configured` column true alongside, mirroring the admin PATCH — but the **derived
  `_is_configured` (non-empty profile) is the source of truth** the API list + the matter-creation gate
  read, so seeding the profile is what flips an area configured + matter-fileable). Profiles are
  **calibrated to the UX-B-1 MiniMax-M3 baseline**: each mirrors the 0054 Commercial shape (identity +
  domain precision) and leans explicitly on the disciplines that degrade honestly under a tier-4-weak model
  — **ground every claim in a tool result and cite it**, **say so plainly when the documents don't
  answer**, **ask one brief clarifying question before guessing** (M3's weakest shape), and **never fake a
  confirmation of an action it has no tool for**. **`default_tier_floor` stays NULL for all** (the 0054
  Commercial rationale: M3 is the only S9-qualified model at tier 4; any stronger floor makes the area fail
  `tier_below_minimum`, a floor of 4 is redundant — operators set one via PATCH once a stronger model
  qualifies). **`agent_config` stays `{}` — live subagents DEFERRED to UX-B-4** (the composition point
  renders area subagents *live* via `area_spec.subagents`; delegation is strictly harder than the
  multi-step chaining M3 is already inconsistent at, ADR-F015 forbids activating an unqualified capability,
  and the decomposition sequences subagents after skills — documented in the migration docstring + the
  evidence README; Privacy's forward-looking profile is prose only). **Harness generalised** (reused, not
  rebuilt): `harness.seed_commercial_matter` → area-agnostic **`seed_matter(factory, *, area_key, doc,
  matter_name)`** (the Commercial wrapper kept for UX-B-1); `scenarios.build_fixture_document` → reusable
  **`build_document(filename, sections)`**; `report.write_report` gained `area`/`milestone` params
  (defaults preserve UX-B-1). New **`area_fixtures.py`** (one synthetic doc + a 3-scenario set per area —
  grounded fetch / honest refusal / ambiguous→clarify, plus a no-tool case for Privacy) +
  **`test_default_area_scenarios.py`** (provider-marked, parametrised per area). **Scenario shapes were
  themselves calibrated** after a first live run: read is no longer forbidden on a fetch (M3's search→read→
  cite is *better* grounding) and the prompt-echo "both are done" was dropped from the false-confirmation
  guard (it matched inside the honest "I cannot confirm both are done"). **Verify:** migration ran clean on
  the conftest throwaway test DB (never the dev DB); scripted suite **2130 passed / 8 skipped** (was 2128:
  +2 new unit tests in `test_practice_areas.py` — derived-configured + 0055 idempotency; the 8 skipped =
  provider tests self-skipping with no key); ruff+mypy `app` clean. **Live per-area harness ran
  (out-of-CI, real MiniMax-M3):** all **12 scenarios `completed`** (no stranded/`cap_exceeded`); reports in
  `docs/fork/evidence/ux-b-2/{disputes,m-and-a,privacy,employment}/` + a README index. **Findings
  (observations, ADR-F015 — non-deterministic, the answer excerpt is authoritative):** M3 grounds + cites
  cleanly, **declines honestly** (issue/serve, sign+wire, terminate+email — states inability + governance
  reasons, never fakes it), and **clarifies** ambiguous referents for 3 of 4 areas (the calibrated profile
  sentence is visibly echoed). **Residual finding (calibration target, not a defect):** M3's tool-use
  *efficiency* varies — on some fetches it issues a redundant second `search_documents`+`read_document`
  before answering (correct + cited, but over the soft step bound); a "search once, precisely" profile note
  is a later-slice option. Reports + the two updated `test_practice_areas` assertions carry no
  key/secret/URL (re-scanned). **Pickup: UX-B-3** (skills activation / S9 — see Next slice).
- **UX-B-1 (PR #90) — SHIPPED. Scenario harness + Commercial baseline (ADR-F015). Test infra only — no
  `app/` change.** A reusable, provider-marked rig (`api/tests/agents/scenarios/`) that drives the REAL
  practice-area Deep Agent through the PRODUCTION composition point
  (`compose_and_execute_run`, injecting only the test-DB session factory + a null checkpointer — the model,
  gateway http client, and gateway URL/key all flow from settings exactly as in prod, so **no provider key
  is ever held or printed**) against the **live gateway / real MiniMax-M3**, then reads back the settled
  `AgentRun` + ordered `AgentRunStep` rows as honest **receipts** (tool selection, step count, model turns,
  final answer, latency) and emits a committed **behavior report**
  (`docs/fork/evidence/ux-b-1/behavior-report.{md,json}` — observations only: tool names/counts/pass-fail/
  bounded answer excerpts, never keys/secrets/raw payloads). Files: `scenarios.py` (the `Scenario` model +
  the 5 Commercial starter scenarios + a synthetic searchable MSA fixture, offsets satisfying the Citation
  Engine invariant + the pure `evaluate()`), `harness.py` (`seed_commercial_matter` → user + Commercial-bound
  matter + file→document→chunks; `run_scenario` → drive + receipt), `report.py` (JSON+MD emitter),
  `test_commercial_scenarios.py` (the `@pytest.mark.provider` + `LQ_AI_GATEWAY_KEY` skipif entry),
  `conftest.py` (`commit_factory`). **Per ADR-F015 it is NOT a model pass/fail gate** — a shape-miss is a
  recorded *finding* that calibrates UX-B-2; the test asserts only that the RIG ran (every scenario reached a
  terminal status + receipts + ≥1 live model turn). **Baseline findings (MiniMax-M3, runs vary — tier-4
  non-determinism is itself the observation):** single-tool fetch grounds + cites cleanly; no-tool-needed
  answers directly (respects "without consulting documents"); guard/refusal **honestly declines** delete/email
  (no such tool) with sound legal reasoning — never hallucinates a confirmation; **multi-step search→read is
  inconsistent** (M3 often answers from the search snippet alone when it already contains the clause — a
  calibration note, not a defect); **ambiguous→clarify is the real weakness** — M3 sometimes clarifies well
  but sometimes spins through repeated search/read (one run hit `cap_exceeded` at 16 steps, no answer). These
  CALIBRATE UX-B-2's default-area profiles + tier floors. **Verify:** scripted CI suite **2128 passed, 4
  skipped** (the 4 = provider tests self-skipping with no key — mine among them, so it never gates CI); ruff
  format+check clean; mypy `app` clean; harness runs locally against the live dev stack (87s → 70s; report
  committed); fresh-context adversarial+security review **SHIP** (0 blockers/should-fixes; 3 NITs — dead
  `applicable` field removed, model-resolution wording softened to observation-honest, a "reading the checks"
  heuristic caveat added to the report; the report carries no key/secret/PII). **Run it:** `DATABASE_URL=…
  LQ_AI_GATEWAY_KEY=… pytest -m provider tests/agents/scenarios/ -s` (containerized: `Dockerfile.dev` image,
  mount `api/`→`/app` + `skills/`→`/skills:ro` + the evidence dir, set `UX_B1_EVIDENCE_DIR`). **Pickup:
  UX-B-2** (default areas, calibrated to this baseline) — see Next slice.
- **UX-B-0 (PR #89) — SHIPPED. ADR-F015 ACCEPTED + UX-B decomposition. Docs only.** The maintainer revealed
  the long-range vision (agentic SaaS **modules** à la **Oscar Privacy**; see [[oscar-privacy-modules-vision]])
  and the near-term mandate that gates it: *Deep Agents must truly work, the cockpit must be perfect*. This
  is **UX-B** (ADR-F012's third leg; the delivery of roadmap "F3 — Practice-area IA re-centre" — named UX-B,
  not F3, to avoid the roadmap-label collision). **ADR-F015 accepted 2026-06-16** = *scenario-based model
  qualification is the gate*: a provider-marked live-MiniMax scenario harness emits a committed behavior
  report; nothing ships `configured`/`activated`/blessed until the report shows M3 handles it; area profiles
  + tier floors calibrated to observed behaviour. Scripted unit tests stay the CI gate; the harness runs
  out-of-CI. Maintainer's steers: start = harness + Commercial baseline; skills activation (S9) in scope (a
  later slice); plan reviewed first (this PR). Files: `docs/adr/F015-scenario-qualified-cockpit-deep-agent.md`,
  `docs/fork/plans/UX-B-deep-agents-truly-work-decomposition.md`. **Pickup: UX-B-1** (see Next slice).
- **F2-M9 (PR #88) — SHIPPED. Consistency sweep + verify — the F2 milestone closer. NO code change.**
  Static audit of every F2-touched surface (cockpit/rail/conversation/matters + all list/card surfaces +
  the M8 nav shells): **zero color `--lq-*`** survivors (the `--lq-radius*`/`--lq-space-*` + `lq-text-*`
  typography CLASSES are the deliberate R-TYPO carve-out, not a miss); **zero `{@html}` sinks** (the one
  grep hit is a *comment* in `CenteredEntry` saying "no `{@html}`"); **zero teal/hardcoded-hex rogue
  accents** — one-accent discipline holds (ink primaries + scarce `--brand`/`--ring`; the only colored
  accent left is the green TrustPill, a documented deferral). **Reachability (the ADR-F012 no-retire
  contract):** all 11 tab surfaces + trust + settings resolve under `(app)` and are reachable from the rail
  Tools group + header gear/ShieldCheck — nothing retired/hidden by the visual pass. **Cross-surface
  consistency (44-shot full matrix via `f2-baseline.cy.ts` 5/5, light+dark × wide+narrow):** the
  raised-card-pill active-nav idiom is identical across the rail + the M8 settings shell; status pills share
  the family (scarce-blue `running`/`indexing`, green `completed`); AA-dark legible, no light-in-dark panels.
  **Owned debt documented, NOT in scope** (the audit records it, M9 does not swallow it): the settings/admin
  child page **bodies** + Trust\*Card internals (still `--lq-*`/teal — R16/R19); `lq-text-*`/radius/space
  classes (R-TYPO); deferred TrustPill tones; the intentional auth-gated `_vl-lab`/`_ae-lab` scratch routes
  (kept by precedent — unadvertised, linked from nowhere). Suites: web check **0 err**; **vitest 851**
  (unchanged); cypress **5/5**. Evidence: `docs/fork/evidence/f2-m9/` (the full surface matrix). Review:
  **SHIP**, 0 blockers. web-only (no api/gateway). **F2 IS DONE.** **Pickup: a decision point — see Next slice.**
- **F2-M8 (PR #87) — SHIPPED. The settings / admin / trust nav shells calmed.** The three sub-nav
  shells under `(app)` were the last chrome still rendering the old **teal `--lq-accent`** active marker
  (`--lq-accent` = `#1f7a6b`, NOT the Vercel scarce blue — so these shells were visibly off-brand, not
  cosmetic-only). Migrated each: **`settings/+layout.svelte`** (vertical rail) — active = the live
  **AreaRail idiom** (raised `--card` pill + `--shadow-xs`, no accent colour), rest `--muted-foreground`,
  hover `--muted`; **`admin/+layout.svelte`** (horizontal tab strip) — keeps the underline idiom but
  **inks the active marker** (`--foreground` text + border, was teal), nav bg `--lq-surface`→`--background`,
  border `--lq-border`→`--border`; **`trust/+page.svelte`** — adopt **`<PageShell size="wide" pad="compact">`**
  (bespoke 1100px→`wide` 1024, the M7b snap), color `--lq-text-secondary`→`--muted-foreground`. Added a
  **`:focus-visible` ring** to both nav link sets (scarce blue, was absent). **Scope = the nav shells only**
  (the HANDOFF/plan rule): the settings/admin CHILD page **bodies** (account MFA button, audit-log table,
  word-addin/intake status pills — still teal/`--lq-*`) and the **Trust\*Card internals** are owned by
  **R16/R19 / their R-slices** — visible in the after-shots, documented, NOT a defect. Suites: web check
  **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 851** (unchanged — presentation-only,
  no new pure helper); **`f2-baseline.cy.ts` 5/5** headed/live (added a settings+admin+trust capture test,
  PHASE=after). Evidence: `docs/fork/evidence/f2-m8/` (settings + admin + trust, light+dark × wide+narrow —
  active markers inked not teal; dark renders honest charcoal). Fresh-context review: **SHIP**, 0
  blockers (every target token verified in both themes incl. `--shadow-xs`/`--background`; `.trust-stack`
  inner wrapper added so Svelte style-scoping applies — `class` on a child component's root would be a dead
  selector; testid forwarded via PageShell `{...rest}`; no `{@html}`; no stray/secret files). web-only.
  **Pickup: F2-M9** (consistency sweep + verify) — see Next slice.
- **F2-M7b (PR #86) — SHIPPED. The library card/wrapper surfaces calmed (the last `(app)` list pages
  on `--lq-*`).** Same M7a recipe applied to the three remaining library pages: **`knowledge`** (card grid +
  inline create form), **`learn`** (3-tile card grid), **`saved-prompts`** (thin `SavedPromptsPanel`
  wrapper). Each: **adopt `<PageShell pad="compact">`** (replacing the page's bespoke `<main>` wrapper — also
  drops a nested-`<main>` landmark, since `(app)/+layout.svelte` already supplies the page `<main>`); the
  bespoke widths **snapped onto the system reading widths** — knowledge 1100→`wide` (1024), learn 960 +
  saved-prompts 920→`default` (896); **migrate COLOR `--lq-*`→semantic** (text→`--foreground`/`--muted-foreground`,
  border→`--border`, card bg→`--card`, inset→`--muted`, accent button→`--primary`/`--primary-foreground` ink
  inverting, accent link/CTA→`--brand`, focus→`--ring`, error→`--destructive`+`--status-failed-wash`);
  **KB status pills → the `--status-*` tone family** (`indexed`→completed, `indexing`→the scarce-blue running
  tone, `failed`→failed, `empty`→muted — borderless, the M7a tabular-pill recipe); **F013 calm card idiom**
  (flat, border-led, hover washes to `--muted`, NO float shadow — dropped the old `box-shadow` hover, scarce
  blue reserved for focus). **Left for R-TYPO (documented, not a defect):** `--lq-radius*`/`--lq-space-*` +
  the `lq-text-*` typography CLASSES (no semantic equivalent, no light/dark variance — never re-introduced,
  just not double-touched). For saved-prompts, **only the page wrapper** is touched — `SavedPromptsPanel`
  itself keeps its own accents (its R-slice owns it). Suites: web check **0 err** (5 pre-existing a11y
  warnings, untouched files); **vitest 851** (unchanged — presentation-only, no new pure helper, like
  M2/M5/M7a); **`f2-baseline.cy.ts` 4/4** headed/live (added a knowledge+learn+saved-prompts capture test,
  PHASE=after). Evidence: `docs/fork/evidence/f2-m7b/` (knowledge + learn + saved-prompts, light+dark ×
  wide+narrow — dark renders honest charcoal, no light-in-dark; ink primaries, scarce-blue pills/links).
  Fresh-context review: **SHIP**, 0 blockers/should-fixes (every target token verified in both themes;
  markup balanced; testids forwarded via PageShell `{...rest}`; no dead selectors; no `{@html}`; the
  heavier `.lq-error` destructive border matches the M7a recipe). web-only — no api/gateway change.
  **Pickup: F2-M8** (calm settings/admin/trust shells) — see Next slice.
- **UX-A-5 (PR #85) — SHIPPED. The legacy `(tools)` shell + the header Tools dropdown RETIRED; UX-A
  COMPLETE.** Deleted `TopTabBar.svelte` (the legacy top-tab component) and the orphaned
  `(tools)/+layout.svelte` (the whole `(tools)` route group is gone). Moved the still-needed
  `visibleTabsFor` into `tabs.ts` (the tab vocabulary outlived the component; importers `(app)/+layout` +
  `CockpitHeader` repointed) and DROPPED the now-dead `tabStateClass` (the rail has its own styling).
  Retired the `CockpitHeader` Tools dropdown (it duplicated the rail Tools section — tools are reached
  ONLY from the rail now); **preserved trust** via a dedicated header ShieldCheck button → `/lq-ai/trust`
  (the dropdown was trust's only entry point; `AmbientTrustChrome` doesn't link). Dropped the unused `user`
  prop from `CockpitHeader`; added `data-testid="lq-cockpit-header"`. **No footer re-home needed**: the
  cockpit never carried `DualBrandingFooter` (it lives in the parent gate layout's auth-exempt branch +
  login only); the obligation ended F0-S6/ADR-F006. Swept stale comments (parent `+layout`, `tab-icons`,
  `autonomous/memory`) + cypress: **deleted** `wave-a-chrome.cy.ts` (100% legacy chrome) + the
  `vl2-cockpit` Tools-menu capture; **repointed** the rail-nav refs in `f1-s2-cockpit` (removed its
  obsolete "Tools menu" test — covered by the new spec), `wave-b-surfaces`, `wave-m1-final-surfaces`,
  `m4-autonomous` (its `.lq-tabbar` assertions had been dead since F2-M2) onto the rail Tools testids.
  Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 851** (−3 =
  removed `tabStateClass` tests; renamed `TopTabBar.test.ts`→`visible-tabs.test.ts`); **new
  `ux-a-5-retire-legacy-shell.cy.ts` 3/3** + **`f2-baseline.cy.ts` 3/3** + **`vl2-cockpit.cy.ts` 2/2**
  headed/live (no `nav[aria-label="Primary"]` / no header Tools dropdown on any surface; tools open from
  the rail into canvas; trust reachable from the header button). Evidence: `docs/fork/evidence/ux-a-5/`.
  Grep-clean: zero live `TopTabBar`/`(tools)`/`lq-tabbar`/Primary-nav refs remain. **KNOWN pre-existing
  legacy-spec debt (NOT in CI, NOT touched by UX-A-5, do NOT attribute to this slice):**
  `f1-s2-cockpit.cy.ts` test 1 (`lq-cockpit-new-matter-name` testid — matter-flow drift) + test 2 (asserts
  the dark canvas channel `>20` but VL0 set charcoal `#111`=rgb(17,17,17) — stale threshold);
  `wave-b-surfaces.cy.ts` `beforeEach` login flake. These are orthogonal test-debt for a later cleanup;
  UX-A-5 only removed their dead-chrome refs. Fresh-context review: **SHIP**, 0 blockers/should-fixes
  (reachability of every surface re-verified incl. the new header trust button; footer non-goal confirmed;
  `visibleTabsFor` move byte-identical; security clean). web-only — no api/gateway change. **ADR-F014
  closed** (status note appended). **Pickup: deferred F2 visual work** (see Next slice).
- **UX-A-4 (PR #84) — SHIPPED. The sub-nav surfaces re-hosted in the cockpit canvas (the last `(tools)`
  routes).** `git mv`'d `admin`, `autonomous`, `settings`, `trust` (incl. all children + `page-helpers` +
  `__tests__`) from `(tools)` into `(app)` — **27 pure renames, zero content change** — so they render in
  the cockpit canvas with the rail present. URLs unchanged (route groups URL-invisible); the
  `/lq-ai/+layout.svelte` auth/boot gate still wraps both groups. **Reachability preserved from cockpit
  chrome** (verified, no re-wiring needed): `admin` (admin-only) + `autonomous` (opt-in gated) appear in the
  rail Tools section + the header Tools dropdown; `settings` via the header gear (→ `settings/appearance`);
  `trust` via the header Tools-dropdown trust link. **Nested sub-nav chrome accepted** (per UX-A): three of
  the four carry their OWN sub-nav `+layout.svelte` (admin/autonomous = horizontal tab strip; settings =
  vertical rail) that now renders INSIDE the canvas beside the cockpit rail — functional, no DOM/id clash
  (distinct `aria-label`s). No `#lq-main`/`h-screen`/cross-boundary-import coupling (grep-verified; the
  route-group rename keeps directory depth identical so relative imports resolve unchanged); the 3
  `max-height: calc(100vh - 64px)` modal caps in autonomous are viewport-relative (pre-existing, fine
  nested). **Known cosmetic quirk (pre-existing, NOT fixed — mechanical scope):** `activeTabFor` keys the
  rail highlight off `admin`'s exact route `/lq-ai/admin/audit-log`, so the Admin tool highlights on
  audit-log but not on other admin sub-pages (models/word-addin/…) — predates this slice (the rail's had the
  admin tab since UX-A-2). **DELIBERATELY LEFT:** `(tools)/+layout.svelte` is now orphaned (zero child
  routes, unreachable) but kept in place — deleting it is coupled to re-homing the `DualBrandingFooter` it
  carries, which is a **UX-A-5** decision. Removed the `f2-baseline` legacy-chrome capture (no surface
  carries the legacy `TopTabBar` chrome any more — nothing left to capture). Suites: web check **0 err** (5
  pre-existing a11y warnings, untouched files); **vitest 854** (moved `__tests__` auto-discovered under
  `(app)`); **`ux-a-4-subnav-surfaces.cy.ts` 3/3** + **`f2-baseline.cy.ts` 3/3** headed/live (open admin
  from rail into canvas + rail-stays + active highlight + admin sub-nav paints; deep-link
  admin/models/settings/trust inside the shell; settings vertical sub-nav + trust in canvas). Evidence:
  `docs/fork/evidence/ux-a-4/`. Fresh-context review: **SHIP**, 0 blockers/should-fixes (1 stale-comment
  tidy applied). web-only — no api/gateway change. **Pickup: UX-A-5** (retire the orphaned
  `(tools)/+layout.svelte` + re-home `DualBrandingFooter` + decide on the header Tools dropdown + sweep).
- **UX-A-3 (PR #83) — SHIPPED. The conversation surfaces re-hosted in the cockpit canvas.** `git mv`'d
  `agents`, `chats`, `matters` (incl. `matters/[id]`) + `playbook-executions/[id]` (incl. its
  `page-helpers` + `__tests__`) from `(tools)` into `(app)` — **pure renames, zero content change** — so
  they render in the cockpit canvas with the rail present + the rail Tools active-highlight (generic via
  `activeTabFor`, no code change needed). URLs unchanged; the `/lq-ai/+layout.svelte` auth/boot gate still
  wraps both groups. **Scroll/height verified**: the list pages flow in the canvas `<main overflow-y-auto>`;
  `matters/[id]`'s `.matter-workspace{height:100%}` resolves against `main.h-full` → paneforge Pane (every
  ancestor has a definite height), same boundedness the old `(tools)` shell gave. **Nested `<main>` is
  pre-existing/unchanged** (the old `(tools)` shell also had a `<main>` around these pages' own `<main>`) —
  out of scope for a mechanical move. **Recorded call — the two-rail composition for `matters/[id]`**: the
  cockpit rail (app nav) and the matter's own `MatterRail` (within-matter nav: Chats/Files/Knowledge/Skills
  + metadata) now BOTH render, side by side. Kept deliberately for this slice (functional, no DOM/id clash,
  distinct selectors); it's visually dense at 1280px. A future slice (UX-B or a reconcile pass) may fold
  `MatterRail` into the cockpit rail or auto-collapse the cockpit rail on matter detail — NOT done here.
  Repointed the `f2-baseline` legacy-chrome capture `/chats`→`/trust` (chats is no longer legacy; trust
  migrates in UX-A-4). Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest
  854** (moved `__tests__` auto-discovered); **`ux-a-3-conversation-surfaces.cy.ts` 3/3** + **`f2-baseline.cy.ts`
  4/4** headed/live (open-from-rail-into-canvas + active highlight; deep-link agents/chats/matters inside the
  shell; `matters/[id]` two-rail composition). Evidence: `docs/fork/evidence/ux-a-3/`. Fresh-context review:
  **SHIP**, 0 blockers/should-fixes; 1 NIT (two-rail density, recorded/accepted). web-only — no api/gateway
  change. **Pickup: UX-A-4** (migrate the sub-nav surfaces `admin`/`autonomous`/`settings`/`trust` into
  `(app)`; each except trust has its own sub-nav `+layout.svelte` that now renders inside the canvas —
  nested chrome, accepted for UX-A; autonomous stays opt-in gated).
- **UX-A-2 (PR #82) — SHIPPED. Rail "Tools" section + the flat tool surfaces re-hosted in the cockpit
  canvas (the dead-end fix).** Added an expandable **Tools** group to `AreaRail` (open by default;
  `ChevronDownIcon` toggle; Lucide glyphs via the shared `tabIcon()` map; **active highlight** via
  `activeTabFor($page.url.pathname)` → `aria-current="page"`; the legacy executor group rests one step
  quieter, the M3 treatment). The layout (`(app)/+layout.svelte`) computes `toolTabs` (=
  `visibleTabsFor(user, {autonomousEnabled})` minus `home`, role/pref-gated identically to the header
  dropdown) + `activeTab` and passes `onSelectTool` (`drawerOpen=false; goto(tab.route)` — plain
  scroll-to-top nav). **`git mv`'d the six flat surfaces** `tabular`, `playbooks`, `saved-prompts`,
  `learn`, `knowledge`, `skills` (incl. `new`/`[id]`/`[id]/edit`/`easy` children + their `__tests__`)
  from `(tools)` into `(app)` — **pure renames, zero content change** — so they render in the cockpit
  canvas with the rail present (the way back is always the rail). URLs unchanged (route groups are
  URL-invisible); the parent `/lq-ai/+layout.svelte` auth/boot gate still wraps both groups. **Scroll
  parent resolved**: these pages use `PageShell` (flowing content, no `h-full`/`#lq-main` coupling — grep
  confirmed) so the cockpit canvas `<main overflow-y-auto>` provides the single scroll axis. `TopTabBar`
  still serves the not-yet-migrated surfaces (`agents`/`chats`/`matters`/`admin`/`autonomous`/`settings`/
  `trust`) — transitional; the header Tools dropdown also coexists until UX-A-5. Fixed 2 knowledge test
  import paths (`(tools)`→`(app)`); repointed the `f2-baseline` legacy-chrome capture `/skills`→`/chats`
  (skills is no longer legacy). Suites: web check **0 err** (5 pre-existing a11y warnings, untouched
  files); **vitest 854** (moved `__tests__` auto-discovered under `(app)`); **`ux-a-2-rail-tools.cy.ts`
  4/4** + **`f2-baseline.cy.ts` 4/4** headed/live (open-from-rail-into-canvas with rail-stays + active
  highlight; Tools collapse/expand; deep-link all 6 migrated surfaces inside the shell; deep-link a
  `[id]`-style child `tabular/new`). Evidence: `docs/fork/evidence/ux-a-2/`. Fresh-context review:
  **SHIP**, no blockers/should-fixes; 1 NIT (rail lists ALL tabs not just migrated — INTENDED per
  ADR-F014 "every surface reachable from the rail"; non-migrated ones transitionally leave the shell).
  web-only — no api/gateway change. **Pickup: UX-A-3** (migrate the conversation surfaces
  `agents`/`chats`/`matters` + `matters/[id]`/`playbook-executions/[id]` into `(app)`; reconcile
  `matters/[id]`'s own `MatterRail`/`ChatPanel` with the cockpit rail — record the call).
- **UX-A-1 (PR #80) — SHIPPED. The cockpit shell extracted into the `(app)` layout (pure refactor, no
  visual change).** Split `cockpit/Cockpit.svelte` into a shared SvelteKit SHELL
  (`routes/lq-ai/(app)/+layout.svelte`: `CockpitHeader` + the resizable rail/drawer/toggle + responsive
  state + the `nowMs` ticker + rail nav; the canvas renders `{@render children()}`) and a LANDING page
  (`(app)/+page.svelte`: the `areas/matters/matter/unfiled` view-switch; owns `projects` + `pendingDraft` +
  the matter/conversation handlers). Shared data (areas/activity/nowMs) flows rail↔canvas via
  **`CockpitShellState` Svelte context** in `cockpit/context.svelte.ts` — scoped **per-shell, NOT a module
  singleton** (so it can't leak one user's matters to the next session in the same tab). Deleted
  `routes/lq-ai/+page.svelte` (now served by `(app)/+page.svelte`, same URL — route groups are
  URL-invisible) + `cockpit/Cockpit.svelte`. **No tools moved, no visual change** — the landing is
  pixel-identical to VL2 (M1 bar). Suites: web check **0 err**; **`f2-baseline.cy.ts` 4/4** headed (cockpit
  + matters + conversation behave identically; `(tools)` surfaces untouched). Evidence:
  `docs/fork/evidence/ux-a-1/`. Fresh-context review: **SHIP** (one naming NIT fixed — `CockpitShellState`
  vs the helpers `CockpitState` URL type). web-only. The shell now persists across navigation, ready for
  UX-A-2 to render tool surfaces in its canvas.
- **UX-A (navigational convergence) — OPEN. ADR-F014 ACCEPTED (Approach B); UX-A-0 docs + UX-A-1 shell
  shipped.** Maintainer trigger after VL2: "open a tool and there's no clear way back to the cockpit;
  tools should live in an expandable rail section and render in the cockpit canvas." Make the cockpit the
  **single app shell** via a URL-invisible **route-group restructure**: extract the cockpit shell (header +
  resizable rail + an expandable **Tools** section + a canvas slot) out of `Cockpit.svelte` into a new
  `(app)/+layout.svelte`; the landing becomes `(app)/+page.svelte`; the `(tools)` routes + `trust` move into
  `(app)` to render in the canvas; the `(tools)` `TopTabBar` shell + the header Tools dropdown **retire** in
  UX-A-5 (maintainer confirmed). Deep-links survive (route groups are URL-invisible) and there are **no
  `load` functions** anywhere under `/lq-ai` (all client-side fetch), so no server logic migrates. NOT UX-B
  (tools stay tools, just re-hosted; capability convergence still rides the pivot). Plan: **ADR-F014** +
  **`docs/fork/plans/UX-A-navigational-convergence-decomposition.md`** (slices UX-A-0…5). **Pickup: UX-A-2 —
  add the expandable "Tools" section to the rail (Lucide icons via the shared `tabIcon()` map in
  `lib/lq-ai/tab-icons.ts` — already extracted; active highlight from `$page.url.pathname`; legacy group
  muted) + migrate the FLAT list surfaces** (tabular,
  playbooks, knowledge, skills, saved-prompts, learn incl. their `new`/`[id]`/`[id]/edit` children) **from
  `(tools)` into `(app)`** so they render in the cockpit canvas. Resolve the scroll-parent change (`#lq-main`
  → the cockpit canvas pane). `TopTabBar` still serves the not-yet-migrated surfaces (transitional). Then
  UX-A-3 (conversation surfaces: agents/chats/matters) → UX-A-4 (sub-nav: admin/autonomous/settings/trust)
  → UX-A-5 (retire TopTabBar + header Tools dropdown + sweep). Each: full ADR-F005 gate + deep-link checks +
  reversible.
- **F2-VL2 (PR #78, main `e5cf01b`) — MERGED. The flagship cockpit re-skin** (maintainer design-gate signed
  off).
  Re-skins `cockpit/` to the `direction-vercel` target using the VL1 primitives, **keeping the resizable
  PaneGroup + drawer mechanics** (maintainer chose "keep resizable pane, re-skin contents" over adopting
  the fixed-rail AppShell — so **AppShell stays a lab-only primitive**, not used in prod). Changes:
  **`CenteredEntry` → `Hero`** (first live `text-display` consumer) + a Vercel composer + SavedPrompts
  chips as calm text-links (dropped the AE `Suggestion` pills here); **`AreaGrid` → gap'd bordered
  `Card`s** (icon + name + `StatusDot` rollup of the area's latest matter status) + a new **"Recent
  matters" dot-status list** (all matters, newest-first — keeps unfiled/legacy reachable); **`AreaRail` →
  the Vercel `--sidebar`** (a "New matter" ink `Button` routing to the launcher, calm area rows with a
  bare per-area activity dot, the unfiled bucket, an identity-only account footer — account ACTIONS stay
  in the header). **StatusDot gained an `attention` tone** (systematic — `--status-attention` already
  exists; the stale/cap-reached belt); a new pure **`runDot()`** in `cockpit/helpers.ts` maps a settled
  run status → calm dot + label **through the canonical `statusBadge`** (incl. the stale belt) so the
  cockpit dots and the agents pills never disagree (ADR-F004). `areaActivityCounts` now also carries
  `lastStatus`. **IA UNCHANGED** (rail stays the practice-area navigator; areas reachable from the
  landing grid too) — no surface retired (F2 rule); **launcher not composer** (ADR-F002); **all rollups
  settled rows** (ADR-F004). **Resolved the VL1 `CardGrid` trailing-empty-cell**: with 5 seeded areas the
  hairline plane leaves a gray cell on non-full rows at most breakpoints, so the area grid uses **gap'd
  bordered cards** (clean at every count) — the hairline `CardGrid` stays for fixed-count sections. Suites:
  web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 854** (+4: `runDot` ×3 +
  `statusDotClass('attention')`); **`vl2-cockpit.cy.ts` 2/2** headed/live (landing light+dark × wide+narrow
  + the narrow rail drawer). Evidence: `docs/fork/evidence/f2-vl2/` (incl. `_target-vercel-{light,dark}.png`
  for side-by-side). Fresh-context review: **SHIP**, no blockers/should-fixes; one NIT (area-card `rd`
  computed-but-discarded) **FIXED in-slice**. web-only — no api/gateway change. **Pickup: present evidence,
  iterate values under the maintainer's eye, MERGE ONLY on explicit design sign-off.**

## State (F2 milestone — F2-VL1 shipped, F013 primitives live; AE-series CLOSED)

- **NEW MILESTONE — F2 (scira-style minimalist pass), governed by ADR-F012.** The maintainer wants the
  whole interface taken toward the calm, minimal aesthetic of [`scira`](https://github.com/zaidmukaddam/scira)
  (**AGPL → REFERENCE ONLY**: study look/IA, never fetch/copy code), AND a UX redesign (land in the
  cockpit → reach tools from there → deep-agents-per-area as the centre). **ADR-F012 splits the work by
  dependency:** **F2** = the *visual* pass (now, reversible, no irreversible IA move — all 11 tabs stay);
  **UX-A** = navigational convergence (own milestone after F2; cockpit becomes the single shell, legacy
  top-tab IA retired — unblocked frontend IA); **UX-B** = capability convergence ("tools as in-context
  agent capabilities", *rides the pivot track* — hard-blocked by the practice_area/unit_of_work SCHEMA +
  area activation + F1-S4/S5; building it before those = schema debt or a dishonest hollow shell). Plan:
  `docs/fork/plans/F2-minimalist-pass-decomposition.md` (slices **F2-M0…M9**). This extends F006/F011 and
  sequences F002's F3 commitment.
- **F2-M0 (PR #67, main `749a5a1`)** — docs + baseline only (no app code): **ADR-F012** written;
  F2 decomposition doc written; **before** baseline screenshots captured (cockpit landing + a legacy
  `(tools)` chrome surface, light+dark × wide+narrow) in `docs/fork/evidence/f2-m0/` via the reusable
  `cypress/e2e/f2-baseline.cy.ts` (PHASE=before|after). The cockpit already lands on "Your practice"
  (areas + per-area agents + unfiled matters) — the architecture already leans toward the destination;
  F2-M4 adds a calm centered intent entry above it.
- **F2-VL1 (this slice, PR #77)** — the **F013 design-language primitives** land (ADR-F013, milestone
  F2-VL). Seven token-consuming primitives in `components/primitives/`: **`AppShell`** (the Vercel layout
  skeleton — 264px `--sidebar` rail with caller-supplied contents + main column + optional thin topbar; rail
  `hidden lg:flex` so it collapses < lg, VL2 wires the drawer), **`Hero`** (centred display-type block — the
  FIRST consumer of the VL0 `--text-display` token, so it materialises that JIT utility), **`Card`** +
  **`CardGrid`** (the hairline-divided plane: `grid gap-px bg-border rounded-lg overflow-hidden`, cells fill
  `bg-card`; Card `interactive` → real `<button>`/`<a>`, `bordered` → standalone hairline+12px), **`Stack`**/
  **`Inline`** (vertical/horizontal rhythm from the §3 scale — literal-class Records so JIT keeps them),
  **`StatusDot`** (dot-status on the `--status-*` tokens; `running` resolves to the scarce `--brand`). The
  **inverting-primary / hairline-secondary / ghost button idioms already exist** via the VL0-recoloured shadcn
  `Button` (`--primary` is ink) → demonstrated, NOT re-built. Pure class helpers (`stackClass`/`inlineClass`/
  `cardGridClass`/`cardClass`/`statusDotClass`) exported from `<script module>` + **unit-tested** (the
  `pageShellClass` precedent). Proven in a NEW dev-only **`/lq-ai/_vl-lab`** route (the `_ae-lab` precedent —
  unadvertised, auth-gated by the lq-ai layout, leading-`_`, served by the prod bundle, Cypress-captured;
  imported by NOTHING live) that rebuilds the `direction-vercel` cockpit target from the real primitives + an
  isolated gallery (type scale, button variants, dot tones, standalone cards). **No live surface re-skinned —
  that's VL2.** Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 850**
  (+13 helper assertions); **`vl1-lab.cy.ts` 1/1** (PHASE-less capture, light+dark × wide+narrow). Evidence:
  `docs/fork/evidence/f2-vl1/` — near-exact match to the mockup; charcoal dark honest; narrow collapses the
  rail + CardGrid → 2-col. Fresh-context review: **SHIP**, no blockers/should-fixes; two lab-only a11y nits
  (heading-in-button, unlabelled composer textarea) **FIXED in-slice**. web-only — no api/gateway change.
- **F2-VL0 (PR #76)** — the **F013 design-language token layer** lands (ADR-F013; milestone
  **F2-VL**, sequenced between M7a and M7b). **`app.css` recoloured to the Vercel palette** (spec §1): the two
  structural remaps that define the look — **`--primary` is now INK** (`#111` light / `#ededed` dark, inverts)
  not the old indigo, and a **new `--brand`** holds the one scarce Vercel blue (`#0070f3` / `#47a3ff`), used
  only for focus / links / running. Everything else monochrome; **charcoal `#111` dark floor** (never black),
  white canvas, hairline borders. Hex values match the approved `direction-vercel` mockup. Also: **type scale**
  `--text-display`…`--text-label` registered in `@theme` (consumed later as `text-*` utility classes — JIT, so
  the vars are pruned until VL1/R-TYPO use them; not a defect); **motion** tokens `--motion-fast/base/slow` +
  2 eases; `--radius` → **10px** base, `--radius-lg` pinned **12px** (cards); elevation **de-tinted** (neutral,
  was indigo); status `running` = `--brand`. `motionMs()` callers (5 files) wired onto a new **`MOTION` JS
  mirror** in `cockpit/helpers.ts` of the CSS `--motion-*` tokens — a **unit test parses `app.css` and locks
  the two in sync** (durations normalised 120→base 150, 160→base, 100→fast). Theme-color meta → `#111`/`#fff`.
  **Tokens only — no new layout** (VL1 builds the AppShell/primitives; VL2 the cockpit proof). The one app-wide
  visible shift: indigo-blue → ink primaries + scarce blue, on charcoal dark. Suites: web check **0 err** (5
  pre-existing a11y warnings, untouched files); **vitest 837** (+1: the MOTION↔CSS sync lock); f2-baseline
  cypress **4/4** (PHASE=after — reused as-is). Built bundle verified to carry `--brand`/`--primary:#111`/
  `--motion-*`/`--background:#111`. Evidence: `docs/fork/evidence/f2-vl0/` (cockpit, matters, conversation,
  playbooks, tabular, skills — light+dark × wide+narrow; ink inverting primaries, charcoal dark with no
  light-in-dark, green dot-status, blue scarce). web-only — no api/gateway change.
- **F2-M7a (PR #74)** — calm **table-list surfaces**: `playbooks`, `tabular`, `skills` list pages.
  **Split of F2-M7** by visual family (M7b = `knowledge`/`learn`/`saved-prompts` card/wrapper surfaces, next).
  Each page: (1) **adopt `<PageShell size="wide" pad="compact">`** for the centered container (the three
  list pages used `max-width: 64rem`/`max-w-5xl` = PageShell `wide` exactly; bespoke header kept — the
  header row carries an h1 + a trailing CTA + subtitle, which `SectionHeader` doesn't model, the same call
  M6 made for MattersPanel); (2) **migrate the COLOR `--lq-*` tokens → semantic** (`--lq-border`→`--border`,
  `--lq-surface`→`--card`, `--lq-inset`→`--muted`, `--lq-canvas`→`--background`, `--lq-accent`→`--primary`
  (teal→**blue** — unifies the page accent with the chrome, the M2 precedent), `--lq-on-accent`→
  `--primary-foreground`, `--lq-text`→`--foreground`, `--lq-text-secondary`/`-tertiary`→`--muted-foreground`,
  `--lq-error`→`--destructive`, `--lq-error-soft`→`--status-failed-wash`); (3) **tabular status pills → the
  existing `--status-*` tone family** (running/completed/failed/cancelled + `-wash`, defined for BOTH themes
  in `app.css` — an existing scale, NOT a new token scale → sidesteps the TrustPill problem). **Left for
  R-TYPO (documented, not a defect):** `--lq-radius*`/`--lq-space-*`/`lq-text-*` (no semantic equivalent, no
  light/dark variance, R-TYPO's domain — never re-introduced, just not double-touched). **`TrustPill`
  badges on skills stay teal/sage** (M2 deferral — needs the tone scale defined first). Suites: web check
  **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 836** (unchanged — presentation-only,
  no new pure helper, like M2/M5); f2-baseline cypress **4/4** (PHASE=after — added a playbooks + tabular
  capture test; skills captured by the existing `(tools)`-chrome test). Evidence:
  `docs/fork/evidence/f2-m7a/` (playbooks + tabular + skills, light+dark × wide+narrow — dark renders
  honest, no light-in-dark; CTAs blue). Fresh-context review: **SHIP**, no blockers/should-fixes/nits
  (every target token verified to exist in both themes; markup balanced; `lq-ai-user-skills` testid
  forwarded via PageShell `{...rest}`). web-only — no api/gateway change.
- **F2-M6 (PR #73, main `bf3f034`)** — matters + conversation surfaces **consolidated onto `PageShell`** (the M1
  carry-over). Added a **`pad` variant** to `components/primitives/PageShell.svelte`
  (`PageShellPad = 'default'|'compact'|'tight'`; `default`=`px-6 py-10 sm:px-8`, `compact`=`px-6 py-8
  sm:px-8`, `tight`=`px-4 py-4 sm:px-6`); `pageShellClass(size, pad='default', extra='')` (signature
  changed — only callers are PageShell itself + its test). **`MattersPanel`** container →
  `<PageShell pad="compact" data-testid="lq-cockpit-matters">` (bespoke header kept — SectionHeader models
  no back link / trailing action / truncating title); **`ConversationHost`** keyed conversation column →
  `<PageShell size="narrow" pad="tight">`. Both keep the `in:fade` on an inner div (the AreaGrid M1 idiom —
  PageShell is a component; transitions need an element). **Visually equivalent** — the pads were copied
  verbatim (the win is consolidation/consistency, not a visible redesign). **`AreaRail` intentionally
  untouched** (sidebar — already minimal, doesn't fit PageShell/SectionHeader). Suites: web check **0 err**;
  **vitest 836** (+1 pad-variant assertion); f2-baseline cypress **3/3** (PHASE=after — added a matters +
  conversation capture test). Evidence: `docs/fork/evidence/f2-m6/` (matters + conversation, light+dark ×
  wide+narrow). Fresh-context review: **SHIP**, no blockers/should-fixes/nits (visual equivalence verified
  exactly; the responsive geometry test still matches the testid). web-only.
- **F2-M5 (PR #72, main `2f363e4`)** — CockpitHeader **minimal-chrome restyle** (already semantic → **restyle-only,
  reversible**; one file, no logic/props/routes changed). `cockpit/CockpitHeader.svelte`: muted icon
  buttons now also **`hover:text-foreground`** (one calm resting state → brighten on hover, matching the
  M2/M3 tab-bar idiom; applied to the rail toggle, Tools trigger, theme, settings, sign-out); the right
  cluster gap tightened `gap-1.5`→`gap-1`; the **three trailing utility icons (theme/settings/sign-out)
  grouped into one tight `gap-0.5` cluster behind a hairline `bg-border` separator** so account/prefs read
  apart from tools/trust; single primary accent stays on the brand. **No AI furniture (ADR-F002)** — the
  header still picks no models/skills/context; `AmbientTrustChrome` (ADR-0011 disclosure) + the Tools menu
  (with the M3 muted-legacy treatment) + the trust link all intact. No new token scale, no `--lq-*`, no
  `{@html}`, nothing retired. Suites: web check **0 err**; **vitest 835** (unchanged — presentation-only,
  no pure helper, like M2); f2-baseline cypress **2/2** (PHASE=after). Evidence:
  `docs/fork/evidence/f2-m5/` (cockpit, light+dark × wide+narrow — separator + tight cluster visible both
  themes; the legacy `(tools)` surface uses `TopTabBar`/`(tools)` chrome, NOT this header, so its shots are
  unchanged). Fresh-context review: **SHIP**, no blockers/should-fixes (1 benign cosmetic nit). web-only.
- **F2-M4 (PR #71, main `df65826`)** — cockpit centered intent **launcher** (ADR-F002: a launcher, **NOT a
  composer** — it never starts an unbound thread). New **`cockpit/CenteredEntry.svelte`** rendered ABOVE
  a **de-emphasised** `AreaGrid` (its "Your practice" header dropped from `page`→`section`, so the page
  keeps a **single h1** — the launcher's "What are you working on?"), wired through a new
  **`landingView`** snippet in `cockpit/Cockpit.svelte` (replaces the two duplicated `AreaGrid` render
  blocks — areas-view + fallback — a real simplification). On submit a new **pure `launchIntent(areas,
  text) → {url, draft}`** helper (`cockpit/helpers.ts`, unit-tested) decides: **exactly one CONFIGURED
  area → enter it** (`cockpitUrl({area})`) carrying the text; **0 or several → no nav**, draft held +
  hint points the user at the grid below. The text carries via a parent-held **`pendingDraft`** in
  `Cockpit.svelte` → passed to `ConversationHost` as **`initialDraft`**, which seeds the composer
  `prompt` **once on mount** (`!prompt` guard) and clears it via **`onDraftConsumed`** — so only the
  FIRST matter after a launch is seeded, never a second, never overwriting in-progress text; unfiled
  (resume-only) gets no draft. Optional starter chips = the user's own **SavedPrompts** (AE7 precedent,
  fetched fail-soft → none). Suites: web check **0 err**; **vitest 835** (+6 `launchIntent`); f2-baseline
  cypress **2/2** (PHASE=after) + a throwaway interaction spec confirmed end-to-end carry-forward
  (submit → `area=commercial` → open matter → composer pre-seeded), then removed. Evidence:
  `docs/fork/evidence/f2-m4/` (cockpit, light+dark × wide+narrow — launcher hero + chip + de-emphasised
  grid). Fresh-context review: **SHIP**, no blockers; 1 should-fix (stale-draft carry window) documented
  in-code as accepted intended behavior; hint-after-typing nit FIXED in-slice (`oninput` clears it).
  web-only — no api/gateway change.
- **F2-M3 (PR #70, main `7c03cef`)** — tab-bar visual condense (restyle/group ONLY — **no tab retired/hidden/
  reordered**). Added a **presentational** `group?: 'core'|'legacy'|'gated'` field + `tabGroupOf()` to
  `lib/lq-ai/tabs.ts` (playbooks/tabular → `legacy`; autonomous/admin → `gated`; absent ⇒ `core`) — purely
  visual, does NOT touch `isTabVisible`/`isTabAvailable`/`activeTabFor`/`visibleTabsFor`. **`TopTabBar`**
  condensed (`gap-4`→`gap-0.5`, `px-1`→`px-2.5`) with **in-place section separators** (inert
  `role="presentation" aria-hidden` `<li>` rules at each group boundary) + the **legacy group rests one
  step quieter** (`text-muted-foreground/70`), all via a new exported pure **`tabStateClass()`** (unit-
  tested). One `<ul role="tablist">` preserved → arrow-key nav intact (separators carry no button, so the
  `button[role="tab"]` nodelist still maps to `tabIndex`). **`CockpitHeader`** Tools dropdown mirrors the
  muted-legacy treatment. **Resolves the M2 active-tab nit** (active wins in `tabStateClass`). Also
  strengthened the reusable `f2-baseline.cy.ts` tools-skills wait (on `nav[aria-label="Primary"]`, not
  `body`) after a blank light-wide capture. Suites: web check **0 err**; **vitest 829** (+6: `tabGroupOf`
  + `tabStateClass`); f2-baseline cypress **2/2** (PHASE=after). Evidence: `docs/fork/evidence/f2-m3/`
  (legacy `(tools)` skills surface, light+dark × wide+narrow — grouping + muted legacy visible both
  themes). Fresh-context review: **SHIP**, no blockers/should-fixes/nits. web-only.
- **F2-M2 (PR #69, main `feacb02`)** — chrome calm + `--lq-*` → semantic token unification (the dark-mode fix).
  Migrated four chrome files off the legacy `--lq-*` system to semantic Tailwind utilities + applied scira
  calm: **`TopTabBar.svelte`** (scoped `<style>` dropped; muted resting tabs, **single primary accent** on
  the active tab + lighter underline, `text-muted-foreground/60` for unavailable), **`AmbientTrustChrome`**
  (wrapper + ⌘K hint), **`DualBrandingFooter`** (raw `gray-*` → `text-muted-foreground`/`border-border`),
  **`(tools)/+layout.svelte`** shell (`.lq-shell`/`.lq-topbar`/`.lq-brand` + inline `var(--lq-*)` styles →
  `bg-background`/`text-foreground`/`text-primary` — the **robust fix** for the AE5 `--lq-canvas`
  light-in-dark cascade quirk). The legacy chrome accent now **unifies to the cockpit's blue `--primary`**
  (was teal/sage). Zero live `var(--lq-*)` refs remain in the four files (only `data-testid`/`id="lq-main"`/
  import paths/comments). **`TrustPill.svelte` NOT touched — deferred on record** (see carry-overs).
  Suites: web check **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 823** (unchanged —
  TopTabBar's pure `visibleTabsFor` test still green; styling is screenshot-verified); f2-baseline cypress
  **2/2** (PHASE=after). Evidence: `docs/fork/evidence/f2-m2/` (cockpit + legacy `(tools)` skills, light+
  dark × wide+narrow); dark mode renders correctly (no light-in-dark). Fresh-context review: **SHIP**, no
  blockers (1 unreachable-state nit on record). web-only — no api/gateway change.
- **F2-M1 (PR #68, main `a8db5c7`)** — calm layout primitives. New `components/primitives/PageShell.svelte`
  (centered `mx-auto w-full max-w-* px-* py-*` container) + `SectionHeader.svelte` (title + optional
  subtitle, `page`=h1 / `section`=h2 type scale), each with an exported pure helper (`pageShellClass`,
  `sectionHeaderScale`) **unit-tested** (vitest +7 → 823). Adopted in **one** real consumer,
  `cockpit/AreaGrid.svelte` (the "Your practice" page title + the "Unfiled matters" section header +
  the page container). Faithful extraction: after-shots **pixel-identical** to the M0 before-baselines
  (`docs/fork/evidence/f2-m1/`). No new token scale; semantic tokens only; no `{@html}`; no IA change.
  Fresh-context review: **SHIP**, no blockers (2 nits on record — see carry-overs). Suites: web check
  **0 err** (5 pre-existing a11y warnings, untouched files); **vitest 823**; f2-baseline cypress **2/2**
  (PHASE=after). web-only — no api/gateway change.

- **AE-series (ADR-F011) — CLOSED. AE0 (#59) + AE1 (#60) + AE2 (#61) + AE3 (#62) + AE4 (#63) + AE5 (#64) +
  AE6 (#65) + AE7 (#66) ALL MERGED.** The series brought the Vercel AI Elements look via the MIT Svelte port
  `SikandarJODD/ai-elements`, vendored + re-tokened + re-wired to OUR data — KEEP Svelte, KEEP
  gateway/SSE/`guarded_tool_call`/audit, KEEP our `marked`+`DOMPurify` sanitizer. Plan:
  `docs/fork/plans/F1-legacy-design-rollout-decomposition.md` §"AI Elements visual adoption". The
  R-series (legacy `--lq-*` → semantic-token migration of non-conversation surfaces) continues
  independently on the dark-mode bridge.
- **AE7 = honest Suggestions, NO new dep:** reused the AE0-vendored `suggestion/` as-is. The chips are
  empty-conversation **starters** backed by the user's own **SavedPrompts** (an honest, user-owned source)
  — NOT model-invented follow-ups (no honest source for those exists, so none are shown). **`shiki` (AE4)
  remains the ONLY new runtime dep across the whole AE series**; AE5/AE6/AE7 added none.
- Dev stack: 8 services healthy; **DB at 0054**; **web REBUILT on AE7** (the bundle carries the ChatPanel
  chips + the SavedPromptsPanel `onPromptsLoaded` hook). Login: http://localhost:3000/lq-ai/login ·
  admin@lq.ai / LQ-AI-local-Pw1!  Gateway aliases smart/fast/budget → minimax/MiniMax-M3 (only
  S9-qualified model, **tier 4**).
- Suites at gate: web `npm run check` **0 errors** (5 pre-existing a11y warnings, untouched files);
  **vitest 816** (unchanged — AE7 behavior is covered by Cypress, no unit-level pure helper added);
  **Cypress `ae7-suggestions.cy.ts` 5/5** headed/live-stubbed (4 functional + 1 capture; the first test
  eats the documented first-`cy.visit` session-establishment latency → it ran ~30s and passed; the rest
  are fast). **api/gateway UNAFFECTED — AE7 touches only `web`** (no backend change). AE7 **after**
  screenshots (empty-chat starter chips, light+dark, wide+narrow) in `docs/fork/evidence/ae7/`.
  Adversarial review (fresh-context agent): **SHIP**, no blockers/should-fixes; nit #1 (a benign chip
  flash while a populated chat's messages load) was FIXED in-slice by adding the `message_count` gate.
  Security pass: NO `{@html}` introduced — the chip label (`prompt.name`) + inserted body
  (`prompt.prompt_text`) are escaped text/attribute bindings via the vendored `Suggestion`→`Button`;
  SavedPrompts are user-owned + server-scoped (404-not-403); no secrets/stray files; web-only.

## Done (F2-VL1, this slice)

- **`components/primitives/{AppShell,Hero,Card,CardGrid,Stack,Inline,StatusDot}.svelte`** — seven new
  presentation-only runes primitives consuming the VL0 tokens (see the F2-VL1 State bullet for each one's
  role). Each `<script module>` exports a pure class helper where one applies (`stackClass`, `inlineClass`,
  `cardGridClass`, `cardClass`, `statusDotClass`); all variant classes are literal strings in `Record`s so
  Tailwind's JIT keeps them.
- **`routes/lq-ai/_vl-lab/+page.svelte`** — NEW dev-only proof route (the `_ae-lab` recipe). `h-screen` (the
  layout renders booted non-exempt routes as a bare `<slot>` — the cockpit "owns its own viewport"), composes
  AppShell + the cockpit target + a gallery. Local non-persisting theme toggle. Imported by nothing live.
- **`__tests__/vl-primitives.test.ts`** — locks the five pure helpers (exact-string assertions). vitest
  837→850 (+13). **`cypress/e2e/vl1-lab.cy.ts`** — logs in, visits `_vl-lab`, asserts the `text-display`
  Hero renders, captures light+dark × wide+narrow (1/1). Evidence `docs/fork/evidence/f2-vl1/`.
- **No new ADR** (ADR-F013 governs; this is its VL1 slice). **No new `--lq-*`, no `{@html}`, no token scale
  added, no surface retired/re-skinned.** Two lab-only a11y nits fixed in-slice (`<span>` not `<h3>` inside the
  interactive Card; `aria-label` on the composer textarea).

## Done (F2-VL0, PR #76)

- **`web/src/app.css`** — recoloured both `:root` (light) and `.dark` to the Vercel palette (hex, matching
  `direction-vercel`): ink `--primary` `#111`/`#ededed` (was indigo), new `--brand` `#0070f3`/`#47a3ff`,
  neutral gray ramp, charcoal `#111` dark floor, white canvas/cards, `#fafafa`/`#0c0c0c` sidebar. `--ring` =
  brand. Status `running` = brand blue (the rest green/red/neutral); washes re-derived per theme. Elevation
  de-tinted to neutral oklch (was hue-262 indigo). In `@theme`: added `--color-brand`/`--color-brand-foreground`
  mappings, the `--text-display`…`--text-label` scale (size + line-height + weight + tracking companions),
  `--radius-lg` pinned `0.75rem`; `--radius` `0.5rem`→`0.625rem`. In `:root`: `--motion-fast/base/slow` +
  `--motion-ease-standard/-emphasized`.
- **`cockpit/helpers.ts`** — new exported `MOTION = { fast:100, base:150, slow:240 }` (the JS mirror of the CSS
  `--motion-*` tokens; Svelte JS transitions take a number, not a CSS var). `motionMs()` unchanged (still the
  reduced-motion gate). Theme-color meta literals → `#111111`/`#ffffff`.
- **5 motion consumers** (`MattersPanel`, `ConversationHost` ×2, `Cockpit` ×2, `AreaGrid`, `ChatPanel`) — import
  `MOTION` and pass `motionMs(MOTION.base|fast)` instead of magic 120/160/100 (normalised; ≤30ms shift).
- **`cockpit/__tests__/helpers.test.ts`** — new `MOTION scale (F013 VL0)` suite: reads `app.css`, regex-parses
  `--motion-fast/base/slow`, asserts `MOTION` matches (the anti-drift sync lock). vitest 836→837.
- **No new ADR** (ADR-F013 already accepted in PR #75; this is its first code slice). **No new `--lq-*`, no
  `{@html}`, no token scale removed, no surface retired.** Evidence: `docs/fork/evidence/f2-vl0/`.

## Done (F2-M7a, PR #74)

- **`(tools)/playbooks/+page.svelte`** — `<section class="lq-playbooks-page">` → `<PageShell size="wide"
  pad="compact">` + inner `.lq-playbooks-page` (now flex/gap only; width/margin/padding from PageShell).
  CTA + apply button → `--primary`/`--primary-foreground`; subtitle/states → `--muted-foreground`/`--muted`;
  error block → `--destructive`/`--status-failed-wash`; table → `--card`/`--border`.
- **`(tools)/tabular/+page.svelte`** — same PageShell adoption + token migration; **status pills** (`completed`/
  `failed`/`cancelled`/`running`+`pending`) remapped from `--lq-success`/`--lq-error`/`--lq-warning`/`--lq-inset`
  onto `--status-completed`/`--status-failed`/`--status-cancelled`/`--status-running` + their `-wash` bgs.
- **`(tools)/skills/+page.svelte`** — outer `<div class="p-4 max-w-5xl mx-auto" data-testid="lq-ai-user-skills">`
  → `<PageShell size="wide" pad="compact" data-testid="lq-ai-user-skills">` (testid forwarded via `{...rest}`).
  Inline `style="color: var(--lq-text*)"` + `<style>` `.lq-btn-*`/`.lq-link`/`.lq-table-skill-card`/`.lq-thead`/
  `.lq-tbody`/`.lq-scope-personal`/`.lq-empty-state` color tokens migrated; `--lq-radius*`/`--lq-space-6` left
  (R-TYPO); `TrustPill` "Table"/scope badges untouched (deferred). Partial-semantic markup (rose error blocks,
  Tailwind utilities) left as-is.
- **`cypress/e2e/f2-baseline.cy.ts`** — new capture test deep-links `/lq-ai/playbooks` (waits
  `lq-playbooks-generate-cta`) + `/lq-ai/tabular` (waits `lq-tabular-new-cta`), captures both light+dark ×
  wide+narrow. Skills captured by the existing `(tools)`-chrome test. **No new ADR** (visual consolidation
  within ADR-F012). Evidence: `docs/fork/evidence/f2-m7a/`.

## Done (F2-M6, PR #73)

- **`components/primitives/PageShell.svelte`** — new `pad` variant (the M1 carry-over). `PageShellPad =
  'default'|'compact'|'tight'` + a `PAD` map; `pageShellClass(size, pad='default', extra='')` (signature
  changed — grep-confirmed the only callers are PageShell's own template + the test). New `pad` prop
  (default `'default'`, so AreaGrid is unaffected). The `default`/`compact`/`tight` pads ARE the matters/
  conversation rhythms verbatim — do NOT override pad via `class` (Tailwind utility order is unreliable).
- **`cockpit/MattersPanel.svelte`** — container div → `<PageShell pad="compact" data-testid=
  "lq-cockpit-matters">` with the `in:fade|global` on an inner div (the AreaGrid M1 idiom). Bespoke header
  kept (back link + truncating `<h1>` + trailing "New {noun}" button — SectionHeader models none of these).
  Body reindented +1 level (large but purely mechanical; prettier-clean).
- **`cockpit/ConversationHost.svelte`** — the `{#key panelKey}` conversation column div →
  `<PageShell size="narrow" pad="tight">` with `in:fade` on an inner div; added the PageShell import. The
  key remount + `bind:prompt`/`bind:selectedMatterId` on ConversationPanel are unchanged (PageShell just
  renders children).
- **`cockpit/AreaRail.svelte`** — intentionally NOT touched (sidebar nav on `sidebar-*` tokens, already
  minimal; PageShell/SectionHeader don't fit a rail). Recorded so M9's sweep doesn't expect a change.
- **`__tests__/PageShell.test.ts`** — calls updated to the 3-arg signature + a `pad`-variant `.toBe()`
  assertion locking the exact compact/tight strings (vitest 836). **`cypress/e2e/f2-baseline.cy.ts`** — new
  capture test deep-links `?area=commercial`, captures the matters list, opens a matter, captures the
  conversation view (light+dark × wide+narrow). **No new ADR** — consolidation within ADR-F012; recorded
  here + in-file F2-M6 comments + memory. Evidence: `docs/fork/evidence/f2-m6/`.

## Next slice — pick up exactly here

**UX-B is COMPLETE; the Oscar Edition / Agentic Modules milestone is OPEN.** PRIV-0 (plan + ADR-F018) is
shipped — the Privacy/ROPA module is scoped and the architecture decided (typed domain + code-validated agent
writes; agent proposes, code disposes). Decomposition: `docs/fork/plans/PRIV-privacy-ropa-module-decomposition.md`.

### → NEXT: PRIV-5 — Vendor + Transfer entities (+ the outside-UK/EEA⇒mechanism invariant).

**PRIV-3 + PRIV-4a are SHIPPED (PRs #101/#102; ADR-F019 accepted).** The two-tier relational register
(System ↔ ProcessingActivity, deployment-global) + read API + read UI + the Article 30 export (JSON/CSV/XLSX)
are on `main`. Start a new branch off `main` for PRIV-5.

**PRIV-5 — Vendors/processors + Transfers (the Art 30(1) content the export's coverage note names as missing).**
This is the slice that closes most of PRIV-4a's honest coverage gap. Two new typed domain entities + their
links (the PRIV-1/PRIV-3 pattern: Pydantic write contract + ORM + CHECK mirror + a migration + guarded
code-validated agent tools + read DTOs/endpoints + register UI). Sketch (re-plan at the boundary):
- **`vendor`** (processor/third party): name, role (processor/sub-processor/joint-controller/recipient), DPA
  in place, contract ref, risk. Linked to processing activities (recipients) and/or systems.
- **`transfer`**: a personal-data transfer to a third country/region + its **mechanism** (adequacy / SCCs /
  BCRs / derogation). **Headline validated invariant: destination outside UK/EEA ⇒ a transfer mechanism is
  REQUIRED** (the ADR-F018 reject-and-retry shape, mirrored as a DB CHECK like `special_category⇔art9`).
- **Extend the Article 30 export** to render vendors/recipients + transfers, and **shrink the coverage note**
  accordingly (it currently lists "Categories of recipients" + "Third-country transfers and the safeguards
  applied" as not-yet-recorded — PRIV-5 removes those two lines as it fills them).
- Data-subject/data-element **categories** may be a thin part of PRIV-5 or its own PRIV-5b — decide at the plan.

**Reminders for PRIV-5 (lessons banked this milestone):**
- **Run the FULL containerized `pytest -q`, not just the slice's test files**, before pushing — a new
  endpoint/route trips the GLOBAL contracts `tests/test_endpoints.py` (IMPLEMENTED_ROUTES + _PARAM_VALUES) and
  `tests/test_openapi.py` (EXPECTED_PATHS + the route-count assertion, now 134). And **mypy runs in CI** — a
  pytest-only local run misses union-attr / type errors.
- **Run ruff/mypy from the REPO ROOT** (or mount the whole repo into the container) so the root `ruff.toml`
  (line-length 100) is found — from `api/` alone ruff falls back to 88 and over-wraps.
- A **migration** lands in PRIV-5: verify up/down/up on a throwaway pgvector container, then apply by
  rebuilding api+arq-worker+ingest-worker together (NEVER host-side `alembic upgrade` on the dev DB).

**THEN the reshaped roadmap (from `docs/fork/plans/PRIV-onetrust-to-lqai-functionality-map.md` — the spine):**
- **P0 in-flight:** **PRIV-4a** Article 30 export → **PRIV-5** Vendor + Transfer entities (+ the
  *outside-UK/EEA ⇒ transfer-mechanism-required* validated invariant) → **PRIV-6** data-flow/lineage view +
  Legal-Entity (Art 30 report scope) + programme dashboard/gap view.
- **P1 flagship (in parallel after PRIV-4a):** **PRIV-A1** assessment domain + skill (PIA/DPIA/triage, reusing
  Oscar's `pia-generation`/`use-case-triage`; writes back to the ROPA); **PRIV-A2** the **conversational-link
  external intake** — the differentiator (tokenized link → scoped Privacy agent → code-validated ROPA writes →
  human review) — needs **ADR-F020** (unauthenticated external surface: rate-limit, no exfil, audit every
  turn); discovery-from-documents (agent proposes ROPA from the matter's own docs).
- **P2 tracks:** DSAR (our `systems` inventory powers the "walk the systems"), Incident/Breach, DPA/Vendor
  review (bridges redlining), Regulatory gap/maturity, Reporting/NL-query.
- **P3 deferred (maintainer-confirmed non-goals):** consent & preference platform, cookie CMP/scanner,
  enterprise data-store discovery connectors, proprietary regulatory RAG.

**Anchors for PRIV-3 ship + what's next:** the map doc + `PRIV-3-ropa-read-ui-and-relational-reshape.md` +
`docs/adr/F019-*.md`. PRIV-3 code: `app/models/ropa.py`, `app/schemas/ropa.py`, `app/agents/ropa_tools.py`,
`app/api/ropa.py`, migration `0059`, web `lib/lq-ai/components/ropa/*` + `lib/components/ui/table/*` +
`ConversationHost.svelte`. Seed script for a demo register: `/tmp/seed_ropa.py` (re-creatable). Screenshot
recipe: Playwright via `NODE_PATH=/home/sarturko/.npm/_npx/<hash>/node_modules`, `executablePath
/usr/bin/chromium` (`/tmp/shot_ropa.cjs`).

**Dev-stack safety (CLAUDE.md hard rules — unchanged):** migration → verify on a **throwaway pgvector
container**, never host-side `alembic upgrade` on the dev DB; never `docker compose down -v`; rebuild
api+arq-worker+ingest-worker together when a migration lands; the `web` container serves a PRE-BUILT bundle —
rebuild it before debugging any UI change. **ruff from the repo root** (`ruff check api` / `ruff format
--check api`) — root `ruff.toml`, line-length 100; from `api/` it falsely reformats. Containerized api tests:
`lq-ai-api-dev` image, mount `api/`→`/app` + `skills/`→`/skills:ro`, `DATABASE_URL` to dev postgres (conftest
makes a throwaway test DB), `--network host`. **HANDOFF updated last; COMPACT after.**

**Grounded state of the loop:** the cockpit loop WORKS end-to-end AND is now surfaced on the web honestly;
all 5 areas configured + scenario-reported; **skills live** (per-area + per-subagent subsets); **subagent
delegation wired + proven** (deterministic ancestry test + `groupTurnTree` render) though M3 elects not to
fan out at small matter sizes (UX-B-4 finding). **Open calibration question (backlog, not a blocker):**
whether a tier-4 model ever fans out on a genuinely large matter (options: a profile nudge naming the
subagent for big matters, a larger fixture, or a stronger qualified model). Anchors: `composition.py`
(`build_area_skill_wiring` + `skill_registry_provider`), `skill_backend.py` (multi-source `RegistrySkillBackend`),
`area_agent.py`, `runner.py` (`parent_step_id` via `_innermost_tool_parent`), web
`agents/helpers.ts` (`groupTurnTree`/`subagentTypeOf`), `cockpit/{NewMatterDialog,AreaConfigDisclosure}.svelte`,
migrations `0056`/`0057`, ADR-F015/F016/F017.

**Branch FIRST; full ADR-F005 gate; the `web` container serves a PRE-BUILT bundle — rebuild it before
debugging any UI change. Merge against `sarturko-maker/lq-ai-fork`.**

**Deferred F2 debt (small, unblocked, pick up between UX-B slices if useful):** R-TYPO (`lq-text-*`→ `--text-*`
tokens) + TrustPill tones (the last non-`--brand` accent); R-series child-body migrations (R16/R19).

**Lower-priority parallel tracks:**
- **UX-B (capability convergence)** — the post-F2 frontier (ADR-F012): "tools as in-context capabilities the
  area agent picks/exposes." Folds into the pivot track (F1-S4/S5 + area-skill activation + the
  `practice_area`/`unit_of_work` schema). Grounding done 2026-06-16 (see the F2-M8 pickup note above);
  nearest beachhead = the S9-gated skills-activation slice (no new schema). UX-A is COMPLETE.
- **R-series rollout slices** (any order — the dark-mode bridge holds un-migrated surfaces; **coordinate with
  F2 — don't double-touch chrome, never re-introduce `--lq-*`**): Foundation/rail R2–R5, Wave 1 R-CONV-1
  (logic; R-CONV-2 → AE6), Wave 2 R12/R13/R14a-b/R15/R15b-tab-pb/R16, Wave 3
  R17a-b/R18/R19a-b/R20/R-CHROME, cleanup R-TYPO → R-BRIDGE → R-LAST. autonomous R21 = SKIP.
- **F1-S4** (subagent tree + SSE v3-projection adapter) / **F1-S5** (idempotency ledger +
  attribution fan-out) — `docs/fork/plans/F1-replan.md`. **Area skills/subagents ACTIVATION**
  (S9-gated) — wires `composition.py` to pass area skills/subagents + re-runs the S9 matrix (this IS the
  UX-B beachhead above).

## Rollout progress

- **R-series:** Step 0 ✅ (#50) · R0 ✅ · R1a ✅ (#51) · R6 ✅ (#52) · R7 ✅ (#55) · responsive parity ✅
  (#53) · **R8 ✅ (#57)**. CI unblocked (repo public).
- **AE-series (ADR-F011):** plan+ADR ✅ (#58) · **AE0 ✅ (#59)** vendoring foundation · **AE1 ✅ (#60)**
  Conversation+Message+Response · **AE2 ✅ (#61)** Reasoning+Actions · **AE3 ✅ (#62)** Sources +
  Inline-Citation · **AE4 ✅ (#63)** Code Block (Shiki highlight, option-2 action; the one new dep
  `shiki`) · **AE5 ✅ (#64)** Prompt Input (≡ R9 — option-2; dark-mode column gap FIXED) · **AE6 ✅ (#65)**
  Tool+Task (≡ R-CONV-2 — option-2 hand-build, no new dep; `groupTurnSteps`; renderModelMarkdown
  convergence) · **AE7 ✅ (PR #66)** Suggestions (honest starter chips backed by SavedPrompts; AE0
  `suggestion/` reused, no new dep). **AE-series CLOSED (AE0–AE7 done) — no AE8.**

## Carry-overs / review deferrals

- **F2-VL1 — `CardGrid` trailing empty cell on non-full rows (resolve in VL2).** The hairline technique
  (`grid gap-px bg-border` + cells filling `bg-card`) means a final responsive row that isn't full shows the
  `--border` background as an empty gray cell (seen in the narrow lab: 3 areas at 2 columns → one empty cell).
  Acceptable in the lab; VL2 must decide the real behaviour against the actual area count — pick a column count
  that divides it, render filler cells, or let the last card span. Not a token/primitive defect.
- **F2-VL1 — AppShell rail is `hidden lg:flex` (no narrow nav yet).** The primitive only models the skeleton;
  below `lg` the rail disappears with no toggle. VL2 wires the real drawer/toggle (reuse the F1-S2.1 AreaRail
  responsive collapse). The lab's narrow shot therefore shows the cockpit full-width (the honest collapsed
  state), not a hamburger.
- **F2-VL1 — the interactive `Card` renders as `<button>`; put a `<span>` (not `<h3>`) as its title.** A
  heading isn't valid phrasing content inside a button. The lab's practice grid uses `<span class=
  "text-subheading">`; carry that into VL2's area cards. Standalone non-interactive cards keep real headings.
- **F2-VL0 — checkbox + focus-ring hardcoded blues left as-is (own slice).** The `@layer base`
  `input[type=checkbox]` uses literal `#2563eb` (checked fill) / `#3b82f6` (focus outline). They were NOT
  migrated to `--primary`/`--ring` because the checked fill carries a `fill='white'` SVG checkmark — and
  `--primary` inverts to near-white in dark, which would make the checkmark invisible on a white well.
  Resolving it needs a non-inverting "control ink" token (or a theme-aware checkmark color), so it's deferred
  to a control-styling slice (likely VL1's button/control-variant work). They render as a blue close to the
  new `--brand`, so no visible clash today.
- **F2-VL0 — type-scale vars are JIT-pruned until consumed (expected, not a defect).** Tailwind v4 only emits
  a `text-<name>` utility (and its `--text-*` var) when the class is actually used in markup. VL0 registers the
  scale in `@theme` but consumes none of it, so `--text-display` etc. don't appear in the built `:root` yet —
  they materialise the moment VL1 primitives use `class="text-display"`. Don't reference `var(--text-display)`
  raw in CSS expecting it to resolve before a utility consumes it; use the utility class (the spec §2/§7
  contract).
- **F2-VL0 — motion durations normalised (≤30ms).** Wiring the 7 call sites onto the `MOTION` scale shifted
  fades 120→150ms (base) and the area fly 160→150ms; the inner fade stayed 100ms (fast). Imperceptible and
  intended (the point of the scale); static screenshots are unaffected. The reduced-motion gate is unchanged.
- **F2-VL0 — status pills / multi-area hint still not screenshot-able on the dev stack** (carried from M7a/M4):
  tabular has no executions, only Commercial is configured. The new status-`running`=`--brand` tone and the
  dark status washes are verified against `app.css`/the built bundle, not headed. Recapture in VL2/M9 when the
  data exists.
- **F2-M7a — tabular status pills not screenshot-able (dev stack has no executions).** The migrated
  `--status-*` pill tones (`completed`/`failed`/`cancelled`/`running`) render only with tabular execution
  rows; the dev stack shows the empty state. The mapping is verified against `app.css` (both themes) by the
  fresh-context review; recapture once executions exist (or in M9's sweep). The `formatTabularStatus` label
  helper is already unit-tested.
- **F2-M7a — color-only migration is intentional, not partial.** `--lq-radius*`/`--lq-space-*`/`lq-text-*`
  remain on these three pages — they have no semantic-palette equivalent and no light/dark variance, so they
  are R-TYPO's domain (not re-introduced, just not double-touched). Same staged-rollout transitional state
  M2 accepted. `TrustPill` badges (skills) stay teal/sage (M2 deferral — needs a tone scale first).
- **F2-M4 — stale-draft carry window (accepted, documented in-code).** `pendingDraft` clears only on
  consume (`onDraftConsumed`), so if the user launches into the 0/many-area case (draft held, no nav) and
  then opens *some other* existing matter before fulfilling the launch, that matter's composer receives
  the draft. Accepted: it is the user's last typed intent, fully editable, and the multi-area carry is the
  intended feature (a fragile "clear on any nav" would break it). Documented at the `pendingDraft`
  declaration in `Cockpit.svelte`. If a future slice wants tighter scoping, distinguish the
  "fulfilling-the-launch" matter open from an "abandon" open (hard with the shared `openMatter`).
- **F2-M4 — multi-area hint not screenshot-able on the dev stack.** Only Commercial is configured, so the
  `awaitingAreaPick` hint ("Pick a practice area below…" / 0-area "Configure a practice area…") couldn't be
  captured headed — it's covered by the `launchIntent` unit test + the in-code logic. Re-capture when a
  second area is configured (or in M9's sweep).
- **F2-M2 — `TrustPill.svelte` migration DEFERRED (own slice).** Its sage/slate/amber/red tone palette
  (`--lq-accent/tier/warn/error` + `-soft`/`-border`) has **no equivalent in the base semantic palette**
  (which only carries primary/destructive/muted/accent) — migrating it would mean **adding a tone-color
  scale to `app.css`, which F2 forbids ("no new token scale")**. It is dark-bridged in `practice.css`
  (`:root.dark`, renders acceptably) and feeds **~15 consumers** (MatterCard, MatterRail*, EnhancePrompt
  Expansion, Trust*Card, skills page, TierBadge, AmbientFooter…). Treat as its own future slice — likely
  alongside R-series tone work or when M7/M8 calm those surfaces; it needs the tone scale defined first.
  **Transitional state after M2:** the legacy chrome accent is blue (`--primary`) while un-migrated page
  content (skills "+ New skill" button, all TrustPills) stays teal/sage — expected during staged rollout.
- **F2-M2 — active-tab nit RESOLVED in M3.** The active-AND-unavailable/legacy precedence is now explicit
  in the pure `tabStateClass()` (active branch first), unit-tested.
- **F2-M1 — nit (1) RESOLVED in F2-M6.** The `PageShell` `pad` variant (`default`/`compact`/`tight`) landed
  in M6; MattersPanel (`compact`) and ConversationHost (`tight`) now adopt it. (2) The refactor
  adds two structurally-empty wrapper `<div>`s (the `in:fade` div + SectionHeader's root, which renders
  `class=""` when no class is passed) — no box-model effect, render is pixel-equal (screenshots confirm),
  fully reversible. Visually identical, not literally byte-identical DOM — acceptable under the pixel-equal
  contract.
- **AE7 — no new carry-overs.** Review SHIP, no blockers/should-fixes; nit #1 (chip flash while a
  populated chat's messages load) FIXED in-slice via the `message_count` gate. Honest-source design is
  load-bearing: chips are the user's own SavedPrompts shown as empty-state starters, never model-invented
  follow-ups — if a future slice wants contextual follow-ups, it needs a real backend source first (don't
  fabricate). The remaining composer-adjacent panels (ModelPicker/SkillPicker/SavedPromptsPanel internals)
  stay on the `--lq-*` dark stopgap (their own future R slices).
- **AE6 — no new carry-overs.** Review SHIP, the one nit (dead `stepDigest`) fixed in-slice. Per-tool
  status has no error state (the record carries no per-tool error signal) — a failed/stale run surfaces
  via the run-level badge + stale banner + the rail's `failed` state, which is honest and documented in
  `toolView`. The cockpit `ConversationHost` stacked collapse (<720px) was verify-only (unchanged); the
  legacy `.ag-layout` 1-col collapse (<900px) is the AE6 narrow shot. ModelPicker/SkillPicker etc. remain
  on the `--lq-*` dark stopgap (their own future slices).
- **AE5 — ChatPanel dark-mode column gap RESOLVED.** The standing AE2 carry-over (central chat *column*
  rendered LIGHT in dark mode while the chrome was dark) is FIXED in AE5: the `<section>` got
  `bg-background text-foreground` and the header/composer migrated off `--lq-*` to semantic tokens.
  Confirmed by `docs/fork/evidence/ae5/ae5-{before,after}-chat-dark-{wide,narrow}.png`. **Note:** the
  remaining composer-adjacent panels still on `--lq-*` (ModelPicker pill, SkillPicker, SavedPromptsPanel)
  render acceptably on the `--lq-*` dark stopgap and are each their own future R/AE slice — NOT migrated here.
- **AE5 — no other new carry-overs.** UX change recorded above (tools stay visible while streaming).
- **AE3 — no new carry-overs.** The fresh-context review's one should-fix (soft-deleted filenames
  surfacing + misleading CASCADE comment) and both nits (unused `isFallbackLabel`; over-vendored
  `inline-citation`/`-text`) were FIXED in-slice, not deferred.
- **AE1 nit (on record):** unused `debugInfo` getter in `stick-to-bottom-context.svelte.ts` — kept
  diffable vs MIT upstream.
- **AE0 nits (on record, byte-faithful to MIT upstream):** `loader-icon.svelte` redundant inline
  `style="color: currentcolor"`; shared static clipPath id across mounted Loaders (renders fine; scope
  with `$props.id()` if a future AE component needs per-instance clip geometry).
- **R8 deferred-on-record:** focus-on-open not asserted in Cypress (Xvfb programmatic focus); drawers not
  full focus-traps (ESC + scrim + `inert` cover practice).
- auth/refresh: per-user session cap + web gate timeout SHIPPED (#47). REMAINING: the
  **deterministic-HMAC index** (removes the global bcrypt scan + bad-token DoS; needs a migration +
  security review — Backlog). **AE3 re-confirmed:** under a LONG spec (7 min, many `cy.visit`) AND
  concurrent Docker load (the api suite running), page loads start timing out (elements "never found") —
  the documented degradation, NOT a code defect. Re-running the spec ALONE on a fresh/uncontended backend
  → **5/5**. More evidence for the HMAC index.
- F1-S3 deferrals: subagent-spec skill names bypass registry validation (validate on activation slice);
  `audit_log.practice_area_id` unindexed; area tier floor operator-set until a model > tier 4.
- ADR-0011 disclosure after F1-S5 attribution. Live SSE token deltas DEAD until a Redis pub/sub
  publisher lands (F1-S4). ADR-0011/F003 conversation memory + compaction → F2.

## Gotchas (carried + new)

- **NEW (AE6): Cypress reports a CLOSED `<details>`'s content as "visible".** Chromium collapses a
  `<details>` by giving non-`<summary>` children a zero box WITHOUT `display:none`, so Cypress'
  `.should('not.be.visible')` FAILS on collapsed content. Assert on the `open` ATTRIBUTE instead
  (`.should('not.have.attr','open')` → click `> summary` → `.should('have.attr','open')`); check inner
  content with `.should('exist')`/`contains`, not visibility. (Cost AE6 two red tests on the first run.)
- **NEW (AE6): a second `cy.visit` to `/lq-ai/agents` mid-test intermittently bounces to `/login`.** The
  capture test originally re-visited per theme; the dark iteration's visit re-triggered auth and
  redirected (the documented first-visit session flake, here fatal because it's not the run's first test).
  Fix: visit + open the thread ONCE, then toggle the theme IN PLACE (`localStorage.theme` + the `.dark`
  class on `<html>`) and screenshot per theme/viewport — no second auth-triggering visit.
- **NEW (AE6): the AE `tool`/`task` registry items are option-2 territory.** `tool` pulls `collapsible` +
  `badge` + `runed` + `./code.json` (the AE4 code block we hand-built, NOT vendored); `task` pulls
  `collapsible` + `bits-ui`. `collapsible` is the same shadcn component dodged for reasoning/sources. Hand-
  build the AE Tool card + Task list on native `<details>` (the ConversationPanel already used that idiom).
- **NEW (AE5): the dark-mode "light chat column" root cause.** The center `<section>` was transparent and
  showed the `(tools)` layout's `.lq-shell { background: var(--lq-canvas) }`, and `--lq-canvas` resolved to
  its LIGHT value on the chat route (a cascade/bundle-order quirk of the legacy `@import practice.css`
  chain — practice.css banks on `:root.dark` winning, but it wasn't on this surface). Fix = stop depending
  on `--lq-*` for the column: give the `<section>` `bg-background text-foreground` (semantic, `.dark`-driven,
  proven on the already-dark sidebar). General rule for the R/AE rollout: when a surface is light-in-dark,
  the migration to semantic tokens IS the fix — don't chase the `--lq-*` cascade.
- **NEW (AE5): the AE `prompt-input` registry item is option-2 territory.** It pulls `ai@^6` (the Vercel AI
  SDK transport we reject — bypasses gateway/SSE/`guarded_tool_call`), `runed`, 6 registry deps, and 23
  SDK-bound `Controller`/context files. Hand-build the identity (`rounded-xl border shadow-sm` shell →
  textarea → `flex justify-between p-1` toolbar; submit = status-driven lucide icon) directly on our composer.
- **NEW (AE5): a dropdown in a bottom toolbar must open UPWARD.** `ModelPicker` got an opt-in `dropUp`
  (`bottom-full mb-1` vs `mt-1`) so its menu doesn't clip off the viewport bottom; opt-in keeps other
  consumers (admin/models) on the default downward menu.
- **NEW (AE5): the composer is inherently the LIVE chat surface** (needs an active chat) — so AE5 has NO
  `_ae-lab` section (a static duplicate would drift). Functional + capture run on `/lq-ai/chats?id=…` with
  the SHORT stubbed fixture (add a `**/api/v1/models` intercept so the toolbar ModelPicker populates). The
  first test of the run still eats the first-`cy.visit` session-establishment latency (fails attempt 1,
  passes on retry) — `retries: { runMode: 2 }` covers it; 7/7 final.
- **NEW (AE4): DOMPurify (3.4.0) DOES preserve CSS custom properties in `style`.** Shiki dual-theme output
  carries the dark palette in a `--shiki-dark` CSS var on each token's inline `style`; class-based dark mode
  breaks silently if the sanitiser strips it. It does NOT — verified in a real browser (Cypress asserts
  `span[style*="--shiki-dark"]` exists post-sanitize + the dark screenshot shows the dark palette). vitest
  env is `node` (no DOM) so DOMPurify behavior is **Cypress-only** to test — don't try to unit-test it.
- **NEW (AE4): Shiki fine-grained setup = no WASM, only listed grammars.** Use `createHighlighter` from
  `shiki` + `createJavaScriptRegexEngine` from `shiki/engine/javascript` (NOT the default oniguruma WASM)
  + an explicit `langs` list. `codeToHtml` THROWS on an unknown lang → `normalizeLang` must map to a loaded
  grammar or `'text'`. `shiki` is the only declared dep; `@shikijs/langs|themes` arrive as its pinned
  transitives.
- **NEW (AE4): a literal `</script>` inside a Svelte `<script>` string closes the block** (parse error).
  Escape the slash — `'<\/script>'` — when a demo string must contain it (the lab injection-safety sample).
- **NEW (AE3): run ruff from the REPO ROOT with the root `ruff.toml`, exactly as CI does.** CI runs
  `ruff check api scripts` + `ruff format --check api scripts` from the repo root. Running ruff from
  inside `api/` uses ruff's DEFAULT settings (the root `ruff.toml` excludes web/ and tunes line-length/
  rules) → spurious "would reformat" noise AND it MISSES rules like `UP017` (`datetime.UTC` over
  `timezone.utc`) — AE3's first CI run failed on exactly that. Correct repro:
  `docker run --rm -v $PWD:/repo -w /repo python:3.12-slim bash -c "pip install -q ruff; ruff check api
  scripts; ruff format --check api scripts"`. Under the root config everything (incl. your edits) is
  format-clean. `mypy app` (run from `api/`) still must pass separately.
- **NEW (AE3): running api pytest off the live dev DB.** The runtime image has NO test deps and the live
  postgres is off-limits. Recipe: throwaway `docker run -d --name <pg> --network lq-ai_default
  pgvector/pgvector:pg16` (+ `CREATE EXTENSION vector`); then
  `docker run --rm --network lq-ai_default -v $PWD/api:/app -v $PWD/skills:/skills:ro -e
  DATABASE_URL=postgresql+asyncpg://lq_ai:lq_ai@<pg>:5432/lq_ai -e LQ_AI_SKILLS_DIR=/skills --entrypoint
  bash lq-ai-api:latest -c "pip install -q -e .[dev]; python -m pytest -q …"`. **Mount `./skills`** or
  migration 0032 (seeds NDA playbook YAML) fails. conftest creates its own `lq_ai_test_*` DB per run.
- **NEW (AE3): the citations intercept glob.** The endpoint is `/chats/{id}/messages/{mid}/citations` —
  AE2's `**/api/v1/messages/*/citations` glob MISSED it (no `/chats/` segment). Use
  `**/api/v1/chats/*/messages/*/citations`.
- **NEW (AE3): option-2 again — Sources + inline-citation.** `sources` pulls `collapsible`;
  `inline-citation` pulls `carousel`+`hover-card`+16 files. Hand-build `Sources` on `<details>`; vendor
  only the dependency-free `inline-citation` primitives you actually use (AE0 "take only what you need").
  Inspect each registry item's `dependencies`/`registryDependencies` BEFORE deciding vendor vs hand-build.
- **(AE2): forward shadcn `Button onclick` through a RUNES wrapper, not the legacy parent** (legacy
  `on:click` on a runes component = silent no-op). `MessageActionsBar`/`MessageSources` are runes wrappers
  the legacy `MessageBubble` feeds plain props.
- **(AE2): lab-based functional Cypress dodges the auth-login flakiness.** `_ae-lab` is auth-gated but
  makes no API calls → deterministic interaction tests run there; use the live chat surface only for the
  integration check + before/after capture. Distinguish icons via lucide `svg.lucide-<name>`.
- **(AE1): the AE dark-capture recipe.** SHORT fixture · `localStorage.theme` BEFORE `cy.visit` · post-boot
  class pin · `cy.get('html').should('have.class', theme)` · 1px viewport nudge before `cy.screenshot`.
- **(AE1): wrapping a Svelte-4 component's content in runes children works** (legacy slots → `children`
  snippet). Alias the AE `Message` *component* vs our `Message` *type* (`Message as AeMessage`).
- **(AE0): the AE vendor pipeline** = shadcn-svelte registry JSON (`…/r/<c>.json`), NOT jsrepo. INSPECT
  before vendoring. Items can under-declare deps. Never adopt the `streamdown-svelte` `response` sink —
  keep `renderModelMarkdown`. **"dev-only route"** = unadvertised, auth-gated, leading-`_` (`_ae-lab`);
  the web container always serves a PROD build. Vendored AE source is eslint-exempt; kept prettier-formatted.
- web CI gates only `npm run check` + vitest (eslint/prettier NOT gated). `npx vitest run` (NOT
  `test:frontend` = watch). vitest env is `node` (no jsdom) — DOMPurify/sanitisation must be Cypress-tested.
  **headless cypress lies about dark theme — capture headed** (`DISPLAY=:0`); **rebuild the `web`
  container before screenshotting/Cypress-testing a UI change.** Cypress trashes `cypress/screenshots`
  at run START — copy before/after frames to `docs/fork/evidence/` immediately after each run.
- `gh pr create` defaults to FROZEN upstream — always `--repo sarturko-maker/lq-ai-fork` AND
  `--head <branch>` (ADR-F001). jq NOT installed — parse `gh --json` with python3 (run from repo dir,
  `/tmp/types.py` shadows stdlib `types`).
- migrations: NEVER host-side alembic against the live dev DB; api auto-migrates on boot; rebuild
  api+arq-worker+ingest-worker together + web. **NEVER `docker compose down -v`.**
- MiniMax-M3 is tier 4 (weak) — `default_tier_floor` < 4 makes every run 403. deepagents subagent `model`
  string = gateway-bypass (ADR-F010 guard at `build_deep_agent`). New API endpoints register in
  tests/test_openapi.py (count assert) — AE3 added NO endpoint (a field on an existing one).
