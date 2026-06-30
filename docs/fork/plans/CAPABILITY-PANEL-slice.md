# Slice: Capability-Toggle Panel (skills + tools + playbooks; MCP placeholder)

> Status: **DRAFT for maintainer edit** (2026-06-30). Proposed ADR: **ADR-F054**.
> Phase 1 of the "Capability panel + in-matter Tabular review" milestone (MILESTONES.md). Phase 2 =
> tabular as an agent tool + LQ-Grid (NOT designed here).
>
> Produced by a 3-lens design fan-out (ship-fast / schema-clean / future-proof) + synthesis; all
> load-bearing seams re-verified against the code.
>
> **Verified seams (2026-06-30):** `api/app/agents/composition.py::compose_and_execute_run`;
> `api/app/agents/area_agent.py` (`agent_config.playbooks` is **validated** by `_validate_refs` but
> **consumed nowhere**); `api/app/agents/skill_backend.py::build_area_skill_wiring`;
> `api/app/agents/commercial_tools.py` (`COMMERCIAL_TOOL_NAMES`); `api/app/agents/guard.py`
> (`GuardContext.granted: frozenset[str]`, static per run, R6 raises `AgentToolNotGranted`);
> `api/app/models/project.py`; `api/app/models/playbook.py`; `api/app/api/agent_runs.py`
> (the matter-load is an **inline** `owner_id == user.id AND archived_at IS NULL AND is_sandbox IS
> FALSE` 404 filter — there is **NO** `_load_visible_project` helper).

## Context

The cockpit conversation lets a lawyer talk to the matter's practice-area Deep Agent. Today the agent's
capability set is decided wholly inside `compose_and_execute_run`:

- the area's bound skills are **always on** (`practice_area_skills` → `area_spec.skills` →
  `build_area_skill_wiring`);
- domain tools are granted by a **hardcoded** `if area_key == PRIVACY_AREA_KEY … elif COMMERCIAL_AREA_KEY`
  branch that appends `build_*_tools(...)` and bakes a static `GuardContext.granted` frozenset;
- the always-on matter substrate tools (search/read/memory/fact/roster/conversation/review) ride every
  matter run; and
- **playbooks are consumed by nobody** — `Playbook`/`PlaybookPosition` data exists, the linear executor
  is FROZEN (CLAUDE.md), and `agent_config.playbooks` is validated but read nowhere.

This slice adds a right-hand **Capabilities** panel that lists the practice area's capabilities
(PLAYBOOKS, SKILLS, TOOLS, + a disabled MCP placeholder) and lets the lawyer toggle which subset the
agent has, **persisted per matter** (survives across that matter's conversations). Two-layer scope
(decided): the AREA curates the AVAILABLE set (admin/curated); the LAWYER toggles a subset on/off per
matter ("system proposes, user owns"). Primitive deepagents builtins (read/write/edit/bash/task) and the
always-on matter substrate tools are NEVER shown.

This panel is the prerequisite for the next milestone (tabular review as an agent tool in Commercial +
Corporate, augmented by the maintainer's React LQ-Grid). The Tools section + tool-GROUP scheme is
designed so tabular slots in as one new group entry with no schema change — but tabular is NOT designed
here.

## Goals

1. A uniform **capability inventory** abstraction — `(kind, key, label, description, available,
   default_enabled, toggleable)` — computed in one pure module, consumed by BOTH the read API and
   `compose_and_execute_run`, so what the panel shows is provably what the agent gets.
2. Two-layer scope: AVAILABLE = area-curated (skills via existing `practice_area_skills`; playbooks via a
   new area binding; tools via a per-area code-defined group map). ENABLED = the lawyer's per-matter
   toggles overlaid on `default_enabled`.
3. A toggled-off capability is GENUINELY removed from the agent for that matter's runs: an off skill is
   not wired (no source, absent from `ls`, absent from the prompt skill list); an off tool group is not
   built and not in `GuardContext.granted` (R6 then fail-closes — defense in depth); an off playbook is
   not injected.
4. Enabled playbooks reach the agent through ONE new **read-only context tier** ("Practice Playbook") on
   the existing `TierMemoryMiddleware` seam (ADR-F049) — reuse the DATA, never the frozen executor.
5. UI: a right-hand panel mirroring the ROPA-register precedent (co-visible split when wide, tab when
   narrow, conversation stays MOUNTED so live SSE survives). Per-matter, server-persisted — the run
   payload is UNCHANGED.
6. MCP is a visible-but-disabled placeholder section (no DB, no wiring) — its own approval-gated
   milestone (ADRs 0014/0015).

## Non-goals

- Tabular as a tool / LQ-Grid / React (next milestone; the `tool` kind + group map must accept it with
  zero schema change — design-compatible, build nothing).
- Real MCP wiring (placeholder only).
- Per-single-run override (scope is per-matter; a "just this run" override is backlog, and would later
  ride `AgentRunCreate` exactly like `budget_profile` — the seam is named, not built).
- A new playbook-AUTHORING UI (playbooks are authored on the existing legacy surface; this slice only
  *binds* existing playbooks to an area and *injects* them).
- A full area-availability admin UI for the new bindings — this slice ships the area↔playbook binding
  **table + a minimal admin attach/detach endpoint** (mirrors the existing `/practice-areas/{key}/skills`
  attach/detach in `practice_areas.py`), seeded for Commercial; the curation UI is deferred.
- Subagent-level capability scoping — toggles apply to the main agent's universe; the existing ⊆-area
  drift filter in `build_area_skill_wiring` drops a disabled skill from subagents for free.
- Granting capabilities to a matter with NO practice area (unfiled/legacy keeps today's behaviour:
  substrate tools only, empty inventory).

## Data model + migration

One migration, next number **`0081`**, additive only. Two new tables; **no** new column on `projects`.

**Why this model (vs the two alternatives):** the ship-fast lens proposed a single
`projects.capability_overrides` JSONB "disabled set" (zero new tables); the schema-clean/future-proof
lenses proposed a normalized `matter_capability_toggles` row table **plus** a `practice_area_tools`
table. We take the **normalized toggle table** (queryable, FK-integral, one row = one explicit
deviation, sparse) but **reject `practice_area_tools`**: tools are code-canonical (the area-key branch +
the `*_TOOL_NAMES` frozensets ARE the truth), so a per-area tool *table* would duplicate code as data and
force a seed that must byte-match today's grants forever (a standing regression hazard). Tool
availability stays a per-area code map; the ONLY new availability *table* is for playbooks (which
genuinely ARE rows and have no area binding yet).

```sql
-- 1. practice_area_playbooks  (area↔playbook availability; mirrors practice_area_skills)
CREATE TABLE practice_area_playbooks (
  practice_area_id UUID NOT NULL REFERENCES practice_areas(id) ON DELETE CASCADE,
  playbook_id      UUID NOT NULL REFERENCES playbooks(id)      ON DELETE CASCADE,
  attached_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (practice_area_id, playbook_id)
);

-- 2. matter_capability_toggles  (the per-matter on/off — the only thing the lawyer writes)
CREATE TABLE matter_capability_toggles (
  project_id      UUID    NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  capability_kind TEXT    NOT NULL,                 -- 'skill' | 'tool' | 'playbook'
  capability_key  TEXT    NOT NULL,                 -- skill name | tool-group key | playbook_id::text
  enabled         BOOLEAN NOT NULL,                 -- explicit on/off; ABSENT row = default_enabled
  set_by          UUID    REFERENCES users(id) ON DELETE SET NULL,  -- human provenance
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, capability_kind, capability_key),
  CONSTRAINT chk_mct_kind    CHECK (capability_kind IN ('skill','tool','playbook')),
  CONSTRAINT chk_mct_key_len CHECK (char_length(capability_key) BETWEEN 1 AND 200)
);
CREATE INDEX idx_mct_project ON matter_capability_toggles (project_id);  -- hot read: all toggles for a matter
```

Design notes:

- **Sparse override, stored `enabled` (not "row = off"):** absence of a row = the inventory entry's
  `default_enabled`. A row exists only where the lawyer diverged. New area capabilities are thus auto-on
  with no backfill; a stale row for a removed/renamed capability is ignored at resolve time (the
  registry/catalog is source of truth — the established `area_agent` drift posture). Storing the bool
  (rather than "presence = off") lets the lawyer explicitly re-enable after a future default flip and
  records both directions in `set_by`.
- **`capability_key` is TEXT, not a polymorphic FK** — mirrors `practice_area_skills.skill_name`: skills
  are filesystem-canonical, tool-group keys are code-canonical; the playbook key is `playbook_id::text`,
  validated to resolve at the PUT boundary (so no dead rows accumulate) and CASCADE-cleaned via the
  availability binding when a playbook is hard-deleted.
- **`default_enabled` is computed in code, not stored:** every available capability defaults ON except
  MCP (placeholder, always off). This keeps any matter the lawyer never touches byte-identical to today.

Migration tested on a **throwaway pgvector container** (NEVER host-side alembic on the dev DB), with the
known mig-test gotchas (skills `skills:/skills:ro` mount, container IP not bridge DNS). Apply by
rebuilding `api` + `arq-worker` + `ingest-worker` together; `docker image prune -f` (dangling) after.

ORM: new `MatterCapabilityToggle` and `PracticeAreaPlaybook` models (mirror `PracticeAreaSkill`'s shape);
no change to `Project`/`PracticeArea` columns.

## API (endpoints + authz/404)

New router `api/app/api/matter_capabilities.py`, prefix `/matters/{project_id}/capabilities`, registered
in the `_active` dep group. Schemas in `api/app/schemas/matter_capabilities.py`. New pure module
`api/app/agents/capabilities.py` (the inventory — see Composition wiring).

Authz on every endpoint uses the existing inline filter (there is no shared helper today; introduce a
small private `_load_owned_matter(db, project_id, user_id)` in this router that runs
`Project.id == project_id AND owner_id == user_id AND archived_at IS NULL AND is_sandbox IS FALSE`,
returns the row or raises 404). Cross-user / archived / sandbox → **404, never 403**.

1. **`GET /api/v1/matters/{project_id}/capabilities`** → `CapabilityInventoryResponse`
   - 404-load the matter; resolve its `practice_area_id` (NULL → empty sections + MCP placeholder).
   - Build the inventory (pure `build_area_inventory(...)` over the area row, `bound_skill_names`, the
     registry from `app.state.skill_registry`, the area's attached playbooks) and overlay the matter's
     `matter_capability_toggles` to compute `enabled` per entry.
   - Response grouped by kind:
     ```
     { unit_label, practice_area_key,
       sections: [
         { kind: 'playbook'|'skill'|'tool'|'mcp', label,
           entries: [{ capability_kind, capability_key, label, description,
                       available, enabled, default_enabled, toggleable }] } ] }
     ```
     MCP section: `available:false, toggleable:false, "coming soon"`.
2. **`PUT /api/v1/matters/{project_id}/capabilities`** → echoes the resolved inventory
   - Body `CapabilityOverridesUpdate` (Pydantic, validated at the boundary — reject, don't sanitize):
     `toggles: [{ kind: Literal['skill','tool','playbook'], key: str, enabled: bool }]`, length/count
     capped. Reject (422) any `(kind,key)` NOT in the matter's AVAILABLE set, and any non-toggleable
     entry (MCP) — so a stale/forged id can never be stored.
   - Upsert via `insert(...).on_conflict_do_update` on the PK (parameterized SQLAlchemy). Full-replace
     per submitted toggle; a toggle matching the default MAY collapse to a delete (optional — simpler to
     just upsert).
   - One audit row `matter.capability_toggle` (counts/kinds/keys only — never content), `db.commit()`.
3. **Admin curation (deferred-but-seamed):** `POST` / `DELETE`
   `/api/v1/practice-areas/{key}/playbooks` (admin, in `practice_areas.py`), body `{playbook_id}`,
   validated against non-deleted `playbooks`, 409 on re-attach, 404 on unknown area. This is the only NEW
   admin endpoint (skills already have curation; tools are code-defined).

## Composition wiring

In `compose_and_execute_run`, inside the existing `if project.practice_area_id is not None:` block (after
`area`, `bound_skill_names`, and `area_spec` resolve), load the matter's toggles once on the already-open
owner-checked `db` session and compute the enabled set via the SAME pure functions the GET uses (single
source of truth):

```python
toggles = (await db.execute(
    select(MatterCapabilityToggle).where(MatterCapabilityToggle.project_id == project.id)
)).scalars().all()
inventory = build_area_inventory(area_key=area.key, bound_skill_names=bound_skill_names,
                                 registry=registry, area_playbooks=<attached>)
enabled_skills       = inventory.enabled_keys("skill",    toggles)   # subset of area_spec.skills
enabled_tool_groups  = inventory.enabled_keys("tool",     toggles)
enabled_playbook_ids = inventory.enabled_keys("playbook", toggles)
```

Then thread the three at the three EXISTING seams:

- **Skills (off → not wired):** filter `area_spec.skills` to `enabled_skills` before passing into
  `build_area_skill_wiring(registry, area_skill_names=<filtered>, subagents=area_spec.subagents)`. A
  disabled skill gets no source, never appears in `ls`, never in the prompt skill list; the ⊆-area drift
  filter drops it from subagents for free. (Filter the list passed to wiring; do not mutate the frozen
  `area_spec`.)
- **Tools (off → not granted):** replace the hardcoded `if area_key == PRIVACY … elif COMMERCIAL` branch
  with a data-driven loop over a per-area **tool-group map** in `capabilities.py`
  (`{'privacy': [ToolGroup('ropa', ROPA_TOOL_NAMES, build_ropa_tools), ToolGroup('assessment',
  ASSESSMENT_TOOL_NAMES, build_assessment_tools)], 'commercial': [ToolGroup('redlining',
  COMMERCIAL_TOOL_NAMES, build_commercial_tools)]}`): for each group whose key is in
  `enabled_tool_groups`, call its builder and append its tools. A disabled group's tools are never built
  AND never enter `GuardContext.granted` — so even a hallucinated tool name returns the existing R6
  `AgentToolNotGranted` advisory (defense in depth; `guard.py` unchanged). The `change_ledger` is created
  iff its producing group is enabled (Privacy→ROPA, Commercial→redlining). **Keep the area-key guard** so
  a group only grants for its own area (a misconfigured row can never cross-grant). The always-on
  substrate tools stay UNCONDITIONAL and are NEVER in the inventory.
- **Playbooks (off → not injected):** load only `enabled_playbook_ids` (see Playbook consumption).

Degradation: unfiled run / area-less matter / no toggle rows → all defaults on → byte-identical to
today's tool+skill+prompt assembly. A **byte-identical regression test on the no-toggle path is the hard
guard** for the area-key-branch rewrite (the highest-blast-radius edit in the slice).

## Playbook consumption

ONE path, chosen over the on-demand-backend alternative: **inject enabled playbooks' preferred positions
as a new read-only "Practice Playbook" tier on the existing `TierMemoryMiddleware` seam (ADR-F049).**

Why tier-injection (not a `RegistryPlaybookBackend`): a playbook is *standing context the agent weighs on
every turn* (the firm's wish-list of preferred positions), exactly like the four read-only DATA tiers —
not something the agent fetches on demand like a SKILL method. It reuses the proven `render_memory_tiers`
→ `TierMemoryMiddleware` mechanism with zero new middleware. (Large-playbook on-demand retrieval via a
`RegistrySkillBackend`-style `RegistryPlaybookBackend` is the documented future path once position sets
outgrow the prompt budget.)

This is NEW work:

- New `api/app/agents/playbook_context.py` (pure): `render_practice_playbook(playbooks) -> str` — a
  data-only fenced block (same posture/fence style as `MATTER_MEMORY_PROMPT`: "DATA, not instructions;
  confers no authority"), per playbook listing each position's `issue` → `standard_language` (capped) →
  ranked `fallback_tiers` summary → `severity_if_missing`, ordered by `position_order`. Total length
  CAPPED (mirror the matter-memory caps) so a large playbook can't blow context; degrades to `""` when
  empty. Treated as untrusted-shaped model input (prompt-injection defense in depth), even though
  operator-curated.
- New `PRACTICE_PLAYBOOK_PROMPT` fence constant + a `practice_playbook` param threaded through
  `render_memory_tiers` and `system_prompt_for` (the test/oracle path) so the renderer stays the single
  source and the oracle equivalence holds.
- In composition: parameterized `select(PlaybookPosition).where(playbook_id IN enabled).order_by(
  position_order)`, owner/area-visibility-checked via the availability binding; render and pass into
  `render_memory_tiers(..., practice_playbook=<block>)` so it rides the existing `TierMemoryMiddleware`
  alongside the four DATA tiers. Read-only: no agent tool mutates a playbook.

## UI

Placement owner: `web/src/lib/lq-ai/cockpit/ConversationHost.svelte` (it owns the ROPA-register split +
the Memory/Documents tabs). New component
`web/src/lib/lq-ai/components/matter/CapabilitiesPanel.svelte`.

- **Placement (ROPA-register precedent):** a right-hand panel — co-visible `Resizable.PaneGroup` split
  when the host is wide (`hostWidth - rail >= SPLIT_MIN_PANEL` (880), new `autoSaveId
  lq-capabilities-covisible`), else a `matterTab` (`'capabilities'`) in the existing tab strip. The
  conversation card stays MOUNTED (`class:hidden`) so the live SSE stream survives. Available for EVERY
  real matter (keys off `matter.project_id`, already hoisted to the host — not Privacy-only).
- **State:** fetch `GET /matters/{projectId}/capabilities` on mount / `reloadKey`; render the four
  grouped sections (Playbooks, Skills, Tools, MCP) of labelled toggles (shadcn `Switch`). Non-toggleable
  / MCP entries render locked/greyed with a "coming soon" caption. On toggle, `PUT` the change (optimistic
  update, revert on error, debounced). Because state is server-persisted per matter, it survives
  conversation remounts automatically — NO composer-local state, NO `buildRunPayload` change. Disable
  toggles while a run is active (`runActive`) and state in the UI + ADR that toggles apply to the NEXT run
  (composition reads them at run start; the live run's `granted` frozenset is fixed).
- **Payload seam (none built; documented):** runs read the matter's toggles server-side at composition;
  contrast `budget_profile` (per-run, component-local). A future per-run override rides `AgentRunCreate`
  like `budget_profile`.
- New API client methods in `web/src/lib/lq-ai/api/` (`getMatterCapabilities`, `putMatterCapabilities`)
  with TS types mirroring the schemas.
- **Testing idiom:** pure helpers (section grouping, default-on overlay, optimistic-toggle reducer,
  PUT-body diff) exported from `<script module>` + vitest (NO `@testing-library/svelte`). Rebuild the
  prebuilt `web` container before any UI debugging.

## Tests

API (`cd api && pytest`, containerized, counts quoted in the PR):

- Pure `capabilities.py`: inventory composition (skills filtered to the registry; tools from the area
  group map; playbooks from the area binding; MCP placeholder present + disabled); `enabled_keys` applies
  `default_enabled` then overlays toggles; drift (registry-unknown skill, deleted playbook) dropped.
- `GET`: defaults all-on; reflects a written override; unfiled matter → empty; cross-user / archived /
  sandbox → **404**; MCP section disabled.
- `PUT`: persists; rejects unknown `(kind,key)` (422), non-toggleable/MCP (422), oversized key (422),
  unknown kind (422); upsert idempotent; cross-matter → 404; one audit row (kinds/keys only, no content);
  `set_by` recorded; matter isolation (a second matter unaffected).
- **Composition (load-bearing):** real `compose_and_execute_run` with the test DB + scripted model + the
  house DI seams — a disabled skill absent from the wired sources; a disabled tool group absent from
  `GuardContext.granted` (assert R6 `AgentToolNotGranted` if its tool is invoked); a disabled playbook
  absent from the rendered tier text; an enabled playbook's positions present in `tier_text`. **No-toggle
  path byte-identical to pre-slice tool+skill+prompt assembly (regression guard).**
- Migration `0081` on throwaway pgvector: both tables add + downgrade clean, CHECK value sets enforced.
- Admin playbook attach/detach: 409 re-attach, 404 unknown area, non-deleted-playbook validation.
- `playbook_context.render_practice_playbook`: formatting, `position_order`, length cap, `""` on empty,
  data-only fence.

Web (`cd web && npm run check && npm run test:frontend`): vitest on the exported pure helpers (grouping,
default-on overlay, optimistic reducer, PUT-body diff, MCP/non-toggleable flags).

## Verification / DoD (ADR-F005 gate)

- `ruff format && ruff check` from the **repo ROOT** (root `ruff.toml` — the Slice O trap);
  `cd api && pytest`; `cd web && npm run check && npm run test:frontend`. Counts quoted in the PR.
- Throwaway-pgvector migration test for `0081`; then rebuild `api`+`arq-worker`+`ingest-worker` together;
  `docker image prune -f` (dangling only).
- Live dev-stack (behaviour change): screenshot the panel co-visible on a Commercial matter; toggle
  "Redlining" OFF → run "redline this NDA" → show the agent cannot (tool absent from the granted audit /
  R6 advisory); toggle a playbook ON → show its positions in the run's injected context (prompt readable
  in source/UI per the transparency rule); confirm toggles persist across a NEW conversation in the same
  matter.
- Fresh-context adversarial review of the diff vs this plan, including the universal security pass (404-
  not-403 on both endpoints, injection in `capability_key`, no playbook bodies in audit, no stray files)
  + simplification pass.
- ADR-F054 drafted/accepted; referenced in a one-line comment at the composition seam and on the new
  tables. `docs/fork/HANDOFF.md` updated (last action).

## Risks

- **No-toggle path must reproduce today's exact assembly** — the area-key-branch rewrite is the
  highest-blast-radius edit; a byte-identical regression test on the default path is the guard.
- **Privacy ROPA↔Assessment dependency:** assessment tools read ROPA activity ids at runtime; making them
  independent toggles lets a lawyer enable Assessment with ROPA off → assessment degrades to empty lists,
  not a crash. Decision: keep them INDEPENDENT, document the degradation in the entry description and the
  ADR. (Maintainer decision #4.)
- **Playbook injection token cost:** cap positions/chars in `render_practice_playbook`; the ADR-F051/F053
  token-budget brake backstops cost.
- **Prompt injection via playbook prose:** rendered as a DATA-only fence, never instructions (matter-wiki
  posture).
- **Stale toggle rows:** `capability_key` is soft for skills/tools; resolve-time intersection with the
  inventory drops unknowns, and the PUT boundary rejects writing a key absent from the available set.
- **Mid-run toggle:** `granted` is frozen at composition; UI disables toggles while `runActive`; the ADR
  states toggles apply to the next run.

## Recommended order

inventory module (`capabilities.py`, pure) + tests → migration `0081` + ORM models → GET/PUT API +
schemas + authz/404 + admin playbook attach/detach → composition wiring (skills filter → tool-group loop
→ regression guard) → playbook consumption (`playbook_context.py` + tier wiring + oracle update) → web
panel + client + helper tests → throwaway-pgvector migration test → rebuild api+arq+ingest → live
dev-stack verification → ADR-F054 + HANDOFF → adversarial review → PR + merge under ADR-F005.

## Decisions (CONFIRMED by maintainer, 2026-06-30)

All six settled on the recommended defaults — the plan + proposed **ADR-F054**
(`docs/adr/F054-per-matter-capability-toggles.md`) already encode these:

1. **Tool availability source** — ✅ per-area CODE map (no `practice_area_tools` table; no byte-match seed
   hazard). Adding a tool = one code entry in the group map.
2. **Playbook consumption path** — ✅ read-only "Practice Playbook" **tier** on `TierMemoryMiddleware`
   (standing context, weighed every turn). On-demand `RegistryPlaybookBackend` stays the documented future
   path for large playbooks.
3. **Per-matter toggle default** — ✅ all-available-on (MCP placeholder excepted). Keeps any untouched
   matter byte-identical to today (the regression guard).
4. **ROPA ↔ Assessment (Privacy)** — ✅ independent toggles; Assessment degrades to empty lists when ROPA
   is off (proceed-on-default; not separately re-asked).
5. **Tool toggle granularity** — ✅ by GROUP (one "Redlining" switch over `COMMERCIAL_TOOL_NAMES`, one
   "ROPA", one "Assessment"); group key = the `*_TOOL_NAMES` frozenset.
6. **Scope** — ✅ per-MATTER only this slice; the per-run override stays backlog (proceed-on-default; would
   later ride `AgentRunCreate` like `budget_profile`).
