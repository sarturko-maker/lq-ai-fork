# F062 — Tool-group registry (availability as data) + deployment-wide (Level 0) capability toggles

- Status: accepted (maintainer-ratified plan §7 row 9 "proceed as you suggest" 2026-07-03; flip
  recorded SETUP-5a, 2026-07-05)
- Date: 2026-07-04
- Deciders: maintainer (Arturs), agent
- Slice: **SETUP-4a**. Builds on **ADR-F002** (practice-area = agent identity), **ADR-F010**
  (per-area Deep Agent, gateway-bypass guard), **ADR-F054** (per-matter capability toggles +
  the capability-inventory abstraction), **ADR-F061** (operator/admin fence). Companion plan:
  `docs/fork/plans/SETUP-4a-tool-group-registry.md`. Parent onboarding architecture:
  `docs/fork/plans/SAAS-SETUP-onboarding-architecture.md` (§2/§5/§6, decision rows 4 and 9).

## Context

ADR-F054 (D1) settled tool availability as a **per-area CODE map** (`AREA_TOOL_GROUPS` in
`app.agents.capabilities`): the composition point selected an area's domain tools with a hardcoded
`if area_key == PRIVACY_AREA_KEY … elif COMMERCIAL_AREA_KEY` branch. That was right for a fixed set of
built-in areas, but the hosted-SaaS onboarding wants the **org-admin to create practice areas** and give
them domain tools. With availability in code, an admin-created area can never be granted any domain
tools — the exact failure the SETUP onboarding architecture's decision row 9 calls out. ADR-F054's own
rejected-option-2 warned against a `practice_area_tools` **grant** table (it would force a seed that must
byte-match today's grants forever), so the fix must make *availability* data **without** making *grants*
data.

Separately, the hosted deployment needs a **Level 0** (deployment-wide) narrowing surface: an org-admin
should be able to turn a capability off for the whole tenant (e.g. disable a skill or a tool group across
every area) — above the existing per-matter (Level 1/2) toggles.

The grant machinery must not move: each `build_*_tools` bakes its own `GuardContext(granted=<ITS_OWN>_TOOL_NAMES)`
frozenset; `guarded_dispatch` R6-fail-closes anything not in that set. There is no merged grant set, and a
data row must never become a grant a builder didn't already define.

## Considered options

1. **Keep the code map; add areas by editing `AREA_TOOL_GROUPS`.** Zero new tables, but admin-created
   areas still can't get domain tools without a code change and deploy — defeats the onboarding goal.
2. **Fully normalize grants into `practice_area_tools` (tool NAME per row).** Admin-configurable, but
   re-introduces exactly the byte-match-forever seed hazard ADR-F054 rejected — a data row could name a
   tool a builder never grants, or drift from the frozensets.
3. **Hybrid (CHOSEN): availability is DATA, grants stay CODE.** A `practice_area_tool_groups` row names
   only *which* GROUP an area offers; a code **registry** (`TOOL_GROUP_REGISTRY`) maps a group NAME to its
   builder/ledger/spec; the `*_TOOL_NAMES` frozensets remain the sole grant truth. A row naming a group
   absent from the registry is dropped (fail-closed). Composition iterates the registry (canonical order)
   filtered by the area's rows. Add a sparse `deployment_capability_toggles` table for Level-0 narrowing,
   threaded through the one `build_area_inventory` chokepoint.

## Decision outcome

Adopt **option 3**. This **supersedes ADR-F054 D1 only** (tool availability was a code map; it is now
data). The F054 status flip + addendum paperwork is reserved for SETUP-5 — this ADR does not edit F054.

- **Availability is data, grants are code.** `practice_area_tool_groups (practice_area_id, group_key)`
  (migration 0086) is the area↔group availability binding, seeded names-only from today's map
  (commercial→{redlining,tabular}, privacy→{ropa,assessment}). `TOOL_GROUP_REGISTRY` (code) resolves a
  group name to a `ToolGroupDef` (panel spec + builder adapter + optional ledger factory). A group's grant
  set is still its `build_*_tools`' `*_TOOL_NAMES` frozenset — untouched. A grant table was rejected
  (option 2 / F054 rejected-option-2).

- **D3 — the isolation invariant is transformed, not weakened.** The pre-slice invariant was
  operational: "a group only grants for its OWN area" (enforced by the hardcoded area-key branch). That is
  exactly what onboarding decision row 9 supersedes. It becomes a **data invariant**: (a) an area gets
  exactly the groups its rows name — nothing more; (b) rows are writable only via the validated AdminUser
  attach endpoint or the 0086 seed; (c) a row naming a group absent from the registry is **dropped at the
  availability chokepoint (`build_area_inventory`) with a structured warning** (counts/keys only) —
  that is the one place a real DB row meets the registry (composition only ever receives the pre-filtered
  enabled set; the grant-seam loop keeps a defense-in-depth check of its own) — fail-closed to absence,
  never a grant; (d) attach validates
  `group_key` against the registry (unknown → 404). **Cross-area attachment is now a FEATURE** (an
  admin-created area gets domain tools by attaching a group), not a fault. Fail-closed holds at every
  level: a group grants iff (row present) AND (registry entry exists) AND (no per-matter toggle disables
  it) AND (no Level-0 toggle disables it); absence at ANY level ⇒ its tools never enter `tools` and never
  enter any `GuardContext.granted`.

- **D4 — order is code-canonical.** Both `build_area_inventory` and the composition loop iterate the
  **registry's insertion order** (redlining → tabular → ropa → assessment) filtered by an area's rows —
  never DB row order — so ordering can never drift from a seed's row order, and the seeded areas'
  ordered grant sets are **byte-identical** to the pre-slice per-area branch (the parity gate).

- **D5 — single-ledger semantics preserved.** The composition loop keeps the FIRST enabled ledger-bearing
  group's ledger as the run's `change_ledger` (Privacy → `RopaChangeLedger`, Commercial →
  `DealChangeLedger`), exactly as before. Areas today have at most one ledger-bearing group. If DATA ever
  attaches two (e.g. ropa + redlining on one area), BOTH groups' tools are still built, but a structured
  warning records that only the first streams live changes (honest, non-breaking). A real multi-ledger
  design is future work.

- **Level 0 — deployment-wide narrowing.** `deployment_capability_toggles (capability_kind, capability_key)`
  (migration 0086) mirrors `matter_capability_toggles` minus `project_id`. It is SPARSE and only ever
  **narrows**: an `enabled=false` row removes that capability (skill / tool group / playbook) from the
  AVAILABLE set at the single `build_area_inventory` chokepoint — so it vanishes from the panel,
  composition never builds it, skills never wire, and the playbook tier never renders. `enabled=true` rows
  are inert (absence already means available), so there is no seed. Org-admin owned (`AdminUser` — the
  F061 operator fence is unchanged); audited `deployment.capability_toggle` with kinds/keys/enabled only.

- **Endpoints.** All `AdminUser`, 404-not-403 on unknown keys: `POST /practice-areas` +
  `DELETE /practice-areas/{key}` (refuses 409 while a non-archived matter references the area — the
  `projects.practice_area_id` SET-NULL FK protects matter/audit data; the admin re-files first) +
  `POST`/`DELETE /practice-areas/{key}/tool-groups[/{group_key}]` (mirror the skills pair) +
  `GET`/`PATCH /admin/capabilities` (Level-0 inventory + sparse writes, reject-don't-sanitize).

## Consequences

- The capability-inventory abstraction (ADR-F054) gains one input (`tool_group_keys` from data) and one
  narrowing overlay (Level-0 toggles); the guard/`*_TOOL_NAMES`/builder internals are untouched. New tool
  groups still slot in as one registry entry + one seed/attach row — no schema change.
- The hardcoded per-area tool branch is gone; its highest blast radius (the default seeded path) is pinned
  **byte-identical** by a dedicated parity golden (`tests/agents/test_registry_parity.py`, frozen literals
  captured from the pre-refactor builders).
- Deleting a practice area is now possible but guarded: it refuses while live matters reference it
  (SET NULL would silently unfile them); with none, skill/playbook/tool-group rows CASCADE and archived
  matters + audit rows SET NULL. Stale `matter_capability_toggles` rows are tolerated at resolve time.
- ADR-F054 D1 is superseded for *availability*; its status flip + addendum are SETUP-5. No new dependency;
  the gateway is untouched.

## Addendum — SETUP-4b (2026-07-04)

SETUP-4b builds the web admin UI over SETUP-4a's endpoints (`/lq-ai/admin/areas`,
`/lq-ai/admin/areas/{key}`, `/lq-ai/admin/capabilities`) and adds four small backend
enablers to make that UI possible. No F054 status flip, no budget-profile defaults, no
viewer RBAC (all SETUP-5); no migration.

- **Read-model fields (D2).** `PracticeAreaRead` gains `bound_tool_groups: list[str]` and
  `bound_playbooks: list[BoundPlaybook]` (`{id, name}`). `bound_tool_groups` is
  REGISTRY-CANONICAL order — `TOOL_GROUP_REGISTRY` insertion order filtered to the area's
  rows, never DB row or attach order (the same ordering invariant D4 established for
  composition, now surfaced on the read model too). The list path (`GET /practice-areas`)
  batches one query per join table across every area rather than looping per-area, so the
  admin UI's list page costs O(1) extra round-trips, not O(areas).

- **`PATCH .../{key}` gains `name`/`unit_label` (D3).** Same partial-update
  (`exclude_unset`) semantics as the existing `profile_md`/`default_tier_floor`/
  `agent_config` fields; bounds mirror `PracticeAreaCreate` (`min_length=1,
  max_length=200`). Lets the detail page rename an area or relabel its unit-of-work noun
  post-creation without a new endpoint.

- **`POST /practice-areas/reorder` (D4).** Body `{keys: list[str]}` must be EXACTLY a
  permutation of every existing area key — compared as both a set (no missing/extra key)
  and a length (a duplicate collapses the set without changing membership, so length is
  checked separately) — else 422 (reject, don't sanitize: a mismatch means the admin's
  browser tab is looking at a stale list, so the UI's fix is to refetch and retry, not for
  the server to guess intent). The handler locks every area row `FOR UPDATE ORDER BY key`
  (deadlock-safe: two concurrent reorders, or a reorder racing a create/delete, always
  acquire row locks in the same global key order) before renumbering `position = list
  index` and stamping `updated_at`. `position` carries no unique constraint — the existing
  `ORDER BY position, key` keeps ties stable — so this is a plain bulk update, not a swap
  dance. Audited `practice_area.reorder` with the key list + count only.

- **Model menu (D8) — NO new endpoint (simplified in review).** The plan originally called
  for a `GET /admin/model-menu` endpoint stripping the gateway's alias list to
  `{alias, tier}`; it was implemented and then DELETED in this slice's adversarial review.
  The alias+tier pair is ALREADY member-visible: `GET /api/v1/models` (open to every
  `ActiveUser`, rendered by `ModelPicker.svelte`) forwards the gateway's merged
  model-discovery payload verbatim, where each alias row carries `routed_inference_tier` —
  so a new, *narrower*, admin-only projection of already-broader-audience data added
  backend surface without adding any confidentiality. The capabilities page instead calls
  the existing `modelsApi.listModels()` and derives the read-only rows client-side in a
  pure page-helper (`aliasMenuRows`: filter `lq_ai_kind === 'alias'`, map
  `{alias: id, tier: routed_inference_tier ?? null}`), degrading to a muted
  "Model menu unavailable." note on error. The F061 operator fence is untouched throughout
  (alias CRUD, provider keys, and the full sanitized `GET /admin/config` remain
  operator-only); no `/api/v1` path count change from D8.
