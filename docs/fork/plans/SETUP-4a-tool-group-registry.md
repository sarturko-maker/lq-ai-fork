# Plan — SETUP-4a: tool-group registry + practice-area CRUD + deployment capability toggles

Status: ACCEPTED (working model: lead plans/verifies, Opus implements — migration + R6 grant seam).
Parent: `docs/fork/plans/SAAS-SETUP-onboarding-architecture.md` §2/§5/§6 (SETUP-4a row) + ratified
decision rows 4 and 9. Supersedes ADR-F054 **D1 only** (decision already maintainer-ratified; the
F054 status flip + addendum paperwork stays reserved for SETUP-5). Grounded in a 4-lens recon
(composition seam / area data+API / decision record / migration conventions), 2026-07-04.

## Context (recon facts the design hangs on)

- The wiring to replace is ONE elif chain in `compose_and_execute_run`
  (`api/app/agents/composition.py:769-818`): `area_key == "privacy"` → ropa (+RopaChangeLedger)
  + assessment; `area_key == "commercial"` → redlining (+DealChangeLedger, redline_service) +
  tabular (fan_out_quota crossover). No else branch — unknown areas get zero domain groups
  (fails closed by absence). Prompt-side mirror: `tabular_enabled` (composition.py:921-923).
- `AREA_TOOL_GROUPS` (`capabilities.py:99-102`) is the availability map (privacy→ropa,assessment;
  commercial→redlining,tabular); its ONLY consumer is `build_area_inventory`, the single
  chokepoint both the capability panel API and composition resolve through (ADR-F054).
- Grants are structurally per-builder: each `build_*_tools` bakes its own
  `GuardContext(granted=<ITS_OWN>_TOOL_NAMES)` frozenset into its closures; `guarded_dispatch`
  (guard.py:75-129) R6-fail-closes anything not in that set. There is no merged grant set. A
  data row naming an unregistered group must degrade to ABSENCE (skip), never an error path
  that could grant.
- Builders have heterogeneous signatures: ropa(session_factory, run_id, binding, change_ledger) /
  assessment(no ledger) / commercial(+redline_service, change_ledger) / tabular(+fan_out_quota).
  At most one ledger-bearing group per area exists today; composition keeps a single
  `change_ledger` variable.
- `practice_areas` has NO key-format CHECK, no create/delete endpoints; existing writes are all
  `AdminUser` (F061 fence: practice-area config stays org-admin). Downstream FKs:
  `projects.practice_area_id` + `audit_log.practice_area_id` both `ON DELETE SET NULL`
  (deliberate: deleting an area must not delete matters/audit). Join tables
  (`practice_area_skills`/`_playbooks`) CASCADE.
- Migration head on main = 0085 → **this slice takes 0086** (AIC branches carry their own
  incompatible 0084-0086 and renumber on THEIR rebase). Template: 0081 (junction+CHECK, named
  constraints, composite PK, no redundant index); m2m seed precedent: 0056 (NOT-EXISTS inserts,
  the asyncpg CAST(:param AS VARCHAR) trap); never-clobber convention: 0055/0066/0073.
- The no-byte-matching-seed rationale is honored by construction: rows carry group NAMES only;
  the registry (code) owns what a name resolves to (plan §7 row 9; 0081 docstring;
  ADR-F054 rejected-option-2).
- test_openapi pins `len(actual) == 167`; POST /practice-areas + DELETE /{key} reuse existing
  PATHS (only IMPLEMENTED_ROUTES tuples are new); genuinely new paths below bump the count.
- `test_capabilities.py:216-217` pins AREA_TOOL_GROUPS ordering; `test_agent_composition.py`
  pins the downstream wiring per area — these are the existing parity oracles.
- Dev stack is still captive to the AIC migration chain → migration round-trip on a throwaway
  pgvector; live verification ISOLATED (3a/3b precedent).
- Pre-existing nit worth fixing in passing: `practice_areas.updated_at` is never set on PATCH.

## Goals

1. **Tool-group registry (code)**: one `TOOL_GROUP_REGISTRY` mapping `group_key → ToolGroupDef`
   (spec + builder adapter + optional ledger factory); the composition elif chain becomes a
   registry-driven loop; `build_area_inventory` resolves availability from DATA.
2. **`practice_area_tool_groups` (data, migration 0086)**: `(practice_area_id, group_key)` rows,
   seeded (names only) from today's map; admin attach/detach endpoints mirroring the skills pair.
3. **`POST /practice-areas` + `DELETE /practice-areas/{key}`** (AdminUser, registry-bounded).
4. **`deployment_capability_toggles` (Level 0, migration 0086)** + minimal admin GET/PATCH,
   threaded into `build_area_inventory` so a deployment-disabled capability vanishes from the
   panel AND from composition through the one chokepoint.
5. **The hard gate**: composition parity golden — for the seeded areas with default toggles, the
   registry-driven tool set (names, ORDER, ledger type, prompt flags) is IDENTICAL to today's
   elif output; cross-area isolation and unknown-group fail-closed proven by test.
6. **ADR-F062 (proposed)**: tool-group registry + config-hierarchy Levels 0/1 (records the
   D1-supersession implementation; F054's own status flip stays SETUP-5).

## Non-goals (recorded)

- No web UI (SETUP-4b: Practice Areas + Capabilities admin surfaces).
- No F054 status flip / addendum, no budget-profile defaults, no viewer/operator tenant-data
  RBAC (all SETUP-5, reserved).
- No new tool groups, no changes to any `build_*_tools` internals, `*_TOOL_NAMES`,
  `GuardContext`/`guarded_dispatch`, FanOutQuotaMiddleware, or the ungated matter-substrate
  tools.
- No MCP wiring (visible-disabled placeholder unchanged); no model-menu surface (operator-owned).
- No area reorder/enable UI affordances beyond what POST needs (position auto-append).
- No backfill loops: deployment toggles are sparse (absence = available), like matter toggles.

## Decisions

- **D1 — registry shape.** `ToolGroupDef` lives beside `ToolGroupSpec` in
  `api/app/agents/capabilities.py` (fall back to a sibling `tool_groups.py` ONLY if an import
  cycle bites): `spec: ToolGroupSpec`, `build(ctx: GroupBuildContext) -> list[Tool]`,
  `ledger_factory: Callable[[], ChangeLedger] | None`. `GroupBuildContext` (frozen dataclass)
  carries `session_factory, run_id, binding, envelope, redline_service_provider` — each entry's
  adapter maps the uniform ctx onto its builder's real kwargs (tabular takes
  `envelope.fan_out_quota`; redlining calls `redline_service_provider()`). Registry dict
  insertion order is the canonical group order (see D4).
- **D2 — `practice_area_tool_groups`.** Composite PK `(practice_area_id, group_key)`
  (`pk_practice_area_tool_groups`), FK `fk_practice_area_tool_groups_area_id` → practice_areas
  ON DELETE CASCADE, `chk_practice_area_tool_groups_key_len` (1..200), NO extra index (PK
  leftmost prefix serves area reads — 0081 reasoning). Seed (module-level idempotent `_seed()`,
  NOT-EXISTS inserts, 0056 pattern incl. the CAST trap): commercial→{redlining,tabular},
  privacy→{ropa,assessment}. Names only — the 0086 docstring states explicitly that grants,
  builders, ledgers and doctrine stay code (D1-supersession terms).
- **D3 — cross-area attachment is now a FEATURE, not a fault.** The old "a group only grants for
  its OWN area" invariant is exactly what row 9 supersedes (its alternative — keep the code
  map — was rejected BECAUSE admin-created areas then can't get domain tools). The invariant
  transforms into: (a) an area gets exactly the groups its rows name, nothing more; (b) rows are
  writable only via the validated AdminUser attach endpoint or the 0086 seed; (c) a row naming a
  group absent from the registry is SKIPPED with a structured warning log (counts/keys only) —
  fail-closed to absence, proven by test; (d) attach validates `group_key` against the registry
  (unknown → 404, mirroring skill-not-in-registry). Record this transformation in ADR-F062.
- **D4 — deterministic order without a position column.** The composition loop and
  `build_area_inventory` iterate the REGISTRY's canonical order filtered by the area's row set
  (registry-order ∩ rows), NOT DB row order. With the seed this reproduces today's exact
  sequence (redlining→tabular, ropa→assessment) — the parity gate depends on it — and keeps
  ordering code-canonical (no seed-vs-code order drift possible).
- **D5 — single-ledger semantics preserved.** The loop collects each built group's ledger;
  composition keeps the first non-None as `change_ledger` exactly as today. Areas today have at
  most one ledger-bearing group; if data ever attaches two (e.g. ropa+redlining on one area),
  keep BOTH groups' tools but log a structured warning that only the first ledger streams live
  changes (honest, non-breaking; a real multi-ledger design is future work — note in ADR-F062).
- **D6 — `deployment_capability_toggles`.** Mirror `matter_capability_toggles` minus project_id:
  PK `(capability_kind, capability_key)`, `chk_..._kind` IN ('skill','tool','playbook'),
  `chk_..._key_len` (1..200), `enabled` bool NOT NULL, `set_by` FK users ON DELETE SET NULL,
  `updated_at`. Sparse; NO seed (0081 empty-seed precedent). Semantics: Level 0 only NARROWS —
  an `enabled=false` row removes the capability from `build_area_inventory`'s AVAILABLE set
  entirely (panel never shows it, composition never builds it, skills never wire, playbook tier
  never renders); `enabled=true` rows are inert no-ops (absence already means available).
- **D7 — Level-0 admin API (org-admin, F061 fence unchanged).** `GET /admin/capabilities`
  (deployment-wide inventory: every registry group + registry skill + live playbook, each with
  its effective Level-0 state) + `PATCH /admin/capabilities` (sparse toggle writes; validates
  kind against the CHECK enum and key against the matching registry/DB — reject unknown, don't
  sanitize; mirrors the matter-capabilities PATCH). Audited `deployment.capability_toggle`
  (kind/key/enabled only). Both `AdminUser` — Level 0 is the org-admin's surface (plan §5);
  the operator fence list is untouched.
- **D8 — `POST /practice-areas`.** AdminUser. Pydantic (`extra="forbid"`): `key` regex
  `^[a-z][a-z0-9-]{1,62}[a-z0-9]$`-style slug (no edge hyphens — wizard precedent), `name` +
  `unit_label` 1..200, optional `profile_md`/`default_tier_floor` (1..5)/`agent_config` (reuse
  the PATCH handler's `build_area_subagents` validation verbatim — ADR-F010/F017 gates),
  optional `tool_groups: list[str]` validated against the registry. `position` auto-appends
  `max(position)+1` (reorder is 4b). `configured` stays server-derived. Duplicate key
  IntegrityError → 409. Audited `practice_area.create` (key/counts only). 201 → PracticeAreaRead.
- **D9 — `DELETE /practice-areas/{key}`.** AdminUser, `_load_area_or_404`. REFUSES (409, count
  in detail — count only, audit contract) while any non-archived project references the area:
  the SET-NULL FK exists to protect matter/audit data, and silently unfiling live matters is the
  surprise it guards against; the admin archives or re-files matters first. With zero live
  references: delete (skills/playbooks/tool-group rows CASCADE; archived projects + audit rows
  SET NULL). Stale `matter_capability_toggles` rows are already tolerated by
  `enabled_keys`/`is_toggleable` (recon-verified) — note, don't touch. Audited
  `practice_area.delete`. Also fix in passing: set `updated_at` on PATCH/POST mutations.
- **D10 — tool-group attach/detach endpoints.** `POST /practice-areas/{key}/tool-groups`
  (`{group_key}` body, registry-validated 404, duplicate 409) + `DELETE
  /practice-areas/{key}/tool-groups/{group_key}` (idempotent 204) — mirror the skills pair
  line-for-line incl. audit events `practice_area.tool_group_attach/detach`.
- **D11 — route-guard bookkeeping.** New PATHS: `/practice-areas/{key}/tool-groups`,
  `/practice-areas/{key}/tool-groups/{group_key}`, `/admin/capabilities` → test_openapi
  EXPECTED_PATHS +3, count 167→170 (with the house comment convention); IMPLEMENTED_ROUTES also
  gains POST /practice-areas, DELETE /practice-areas/{key} (existing paths, new method tuples)
  + the new-path methods.

## Implementation order

1. Migration 0086 (both tables + seed) + ORM models + test_migrations coverage (0085-section
   pattern: columns/indexes/CHECK positive+negative) + up/down/up on throwaway pgvector.
2. Registry in capabilities.py; `build_area_inventory` goes DB-driven for groups (rows ∩
   registry, registry order) and Level-0 aware for all three kinds; keep its signature/callers.
3. Composition: elif chain → registry loop (D4/D5); `tabular_enabled` becomes "area's built
   groups include tabular" (behaviorally identical for seeded data).
4. Endpoints (D7-D10) + schemas + audit + route-guard files.
5. Tests: parity golden (see gate), fail-closed unknown-group row, cross-area attach grants the
   right tools ONLY for that area's runs, Level-0 disable removes skill/tool/playbook end-to-end
   (inventory + composition + panel read API), POST/DELETE/attach/detach endpoint matrix
   (401/403/404/409/422), seed idempotency (importlib re-run pattern from test_practice_areas).
6. ADR-F062 (proposed) + MILESTONES (4a ✓) + HANDOFF banner draft.

## The hard gate (parity)

A dedicated `test_registry_parity` golden: for EACH seeded area (privacy, commercial), with all
toggles at defaults, assert (a) the exact ordered tool-name list composition builds equals a
FROZEN literal of today's output (captured from the pre-slice elif — the implementer captures it
FIRST, before refactoring, and pins it verbatim); (b) ledger class per area (RopaChangeLedger /
DealChangeLedger); (c) `tabular_enabled` prompt flag per area; (d) an unknown area key still
yields zero domain groups. The existing `test_agent_composition.py` + `test_capabilities.py`
suites must pass with only DELIBERATE edits (the AREA_TOOL_GROUPS ordering pin becomes a
registry+seed pin — each edit justified in the PR). Cross-area isolation: a run in privacy never
builds commercial tools unless a data row explicitly attaches them (new test proves both sides).

## Verification / DoD (ADR-F005 gate)

- Full api suite containerized (counts quoted; conftest self-mints its DB — DATABASE_URL needs
  the real dev-postgres creds; wizard tests need the extra ro mounts recorded in HANDOFF).
- Migration 0086 up/down/up on a throwaway pgvector by IP (never the dev DB — AIC-chain trap).
- ruff + format from repo ROOT; mypy app; no new deps.
- Fresh-context adversarial review incl. mandatory security + simplification pass. Specific
  security targets: the fail-closed unknown-group path (no code path may turn a bad row into a
  grant); attach/PATCH validation rejects (never sanitizes); audit rows carry kinds/keys/counts
  only; POST key regex anchored; no authz regression on the router (AdminUser everywhere,
  404-not-403 for unknown keys); DELETE cannot orphan live matters.
- Isolated live smoke (throwaway pg+redis+api, 3b harness pattern): migrate from empty → seed
  rows present → GET /practice-areas unchanged shape → POST a new area with tool_groups
  [redlining] → attach/detach round-trip → Level-0 disable of a skill+group reflected in the
  matter capabilities panel read → DELETE refused with a live matter, succeeds without.
- HANDOFF + memory updated; squash-merge under the full gate.

## Delegation

One Opus 4.8 agent in an isolated worktree cut from main @ 95e1db52 (migration + the R6 grant
seam = complex tier per the working model). Lead runs all gates, the isolated live smoke, and
the adversarial review.

## Risks / gotchas

- Parity depends on ORDER — capture the golden BEFORE refactoring; registry-order iteration
  (D4) is what makes it deterministic.
- `build_area_inventory` gaining queries must not break its non-DB callers/fakes — check every
  call site + the `_SkillRec .summary()` fake trap from ADR-F054.
- asyncpg CAST trap in the 0086 seed (0056 precedent).
- Don't touch `test_openapi`'s count without the running-comment convention.
- The AIC branches' own 0086 is a DIFFERENT lineage — never reconcile here; they renumber.
- Untracked strays (`sample-documents/`, `api/tests/agents/scenarios/test_*_live.py`) belong to
  NO PR.
