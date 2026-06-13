# F1-S3 — `practice_areas` config vocabulary + per-area Deep Agent

Slice plan per CLAUDE.md § Iteration. Ratified scope: `docs/fork/plans/F1-replan.md` § F1-S3
(maintainer-accepted PR #42). Pickup: `docs/fork/HANDOFF.md` § Next slice items 1–2.
Linked ADRs: **F002** (practice areas as backend entities — the schema authority), **F004**
(declarative shapes / one renderer / A·B·C params), **F009** (at-most-once runs), and the
NEW **ADR-F010** drafted in this PR (per-area Deep Agent: gateway-only model binding,
model-bearing subagent specs rejected).

## The vertical thread

Commercial stops being a presentation placeholder and becomes a real backend **agent
identity**: an area profile that shapes the system prompt, a default tier floor, area-scoped
skills, and declarative subagent specs — built into a per-area Deep Agent through the existing
`build_gateway_chat_model` → `build_deep_agent` seam, every tool dispatch still on
`guarded_tool_call`. Matters file under their area via `projects.practice_area_id`; the cockpit
derives `configured` from real config and shows each area only its own matters.

## Goals (ratified hard requirements)

1. **EXTEND `practice_areas` (migration 0054, additive only — never recreate 0053's table)**:
   - `profile_md` `Text` nullable — area profile markdown, folded into the system prompt
     (mirrors `projects.context_md`).
   - `default_tier_floor` `SmallInteger` nullable, `CHECK (… IS NULL OR BETWEEN 1 AND 5)`
     (copies `projects.minimum_inference_tier` exactly) — composed with the matter floor via
     `min()` API-side, so no gateway change.
   - `agent_config` `JSONB NOT NULL DEFAULT '{}'::jsonb` — declarative shape data consumed by
     ONE renderer (ADR-F004): `subagents` (list of declarative SubAgent specs — see Goal 4),
     and by-reference `playbooks`/`mcp_servers` (ids/names only, NO credentials — NORTH-STAR
     inv 3; recorded for forward config, NOT consumed by the renderer yet — playbooks/MCPs are
     not wired to deep agents anywhere today; documented as such).
   - Pydantic-validated at the boundary on every write (reject, don't sanitize); `agent_config`
     has a strict schema (unknown keys rejected; subagent specs forbid a `model` key — Goal 4).
2. **`projects.practice_area_id`** — nullable FK `→ practice_areas.id ON DELETE SET NULL`
   (legacy/unfiled matters keep NULL; no backfill — the 0052 no-backfill posture). `CHECK`
   forbidding `is_sandbox = true AND practice_area_id IS NOT NULL` (sandbox rows are not
   matters). New matters created under an area set it; the area must be `configured`.
3. **`audit_log.practice_area_id`** — nullable FK (first-class column per the ratified scope and
   F002 "audit slicing"), threaded through `audit_action(...)` and `guard.py`'s dispatch audit
   via `GuardContext.practice_area_id`. Contract unchanged (counts/types/IDs only).
4. **Per-area Deep Agent renderer** (`api/app/agents/area_agent.py`, new — ONE renderer, no
   per-area code branches): area row → `create_deep_agent` kwargs:
   - system prompt = `SYSTEM_PROMPT` + (matter addendum) + area `profile_md`;
   - tier floor = `min(project floor, area default_tier_floor)`;
   - area-scoped skills attached (Goal 6);
   - declarative `subagents` built into deepagents `SubAgent` TypedDicts.
   **SECURITY (load-bearing, ADR-F010)**: `build_deep_agent` REJECTS any subagent spec carrying
   a `model` key (`ValueError`). Verified-from-source rationale (deepagents 0.6.8
   `graph.py:608` → `_models.py:33` → `init_chat_model`): a string `model` constructs a provider
   SDK client directly from env keys = total gateway bypass (no key header, no tier floor, no
   anonymization, no routing log). App-authored subagents OMIT `model` so they inherit the
   parent's already-gateway-bound `ChatOpenAI` instance (verified: `spec.get("model", model)`
   returns the parent instance, `resolve_model` passes `BaseChatModel` through untouched). The
   renderer emits COMPLETE per-subagent declarations (deepagents semantics, source-verified:
   `permissions` REPLACE the parent's, `tools` OVERRIDE when the key is present else inherit,
   middleware never inherits — a fresh default stack is built per subagent).
5. **Config/admin API** (extend `api/app/api/practice_areas.py`): reads stay `ActiveUser`
   (transparency, like Organization Profile); config writes are `AdminUser`. `PATCH
   /practice-areas/{key}` (profile_md, default_tier_floor, agent_config, configured) +
   skill attach/detach. 404-not-403 for unknown keys; `audit_action` on every write.
6. **Area-scoped skills** — `practice_area_skills` join table `(practice_area_id, skill_name)`
   (skills stay filesystem-canonical per ADR-0004 — TEXT, not FK; mirrors `project_skills`).
   The renderer resolves bound skill names against `app.state.skill_registry` and attaches them
   to the agent (deepagents `skills=`); unknown/removed skill names are skipped with a logged
   warning (registry is the source of truth).
7. **`configured` becomes derived** server-side (area is configured ⇔ has a profile and the
   agent renderer can build it) — the frontend contract stays a bool, only the source changes.
8. **Cockpit consumes S3** (web, same slice — HANDOFF item 2): `MatterActivity` gains
   `practice_area_id`/`area_key`; `list_matter_activity` filters/groups by area; `AreaGrid`
   per-card counts only that area's matters; `MattersPanel` shows the selected area's matters;
   `NewMatterDialog`/create sets `practice_area_id`; `configured` flows from derived config.
9. **Reject sandbox `project_id` at `POST /agents/runs`** (HANDOFF carry-over tagged S3 — closes
   the sandbox-thread state at the source).
10. **Qualification hook**: Commercial uses only the qualified `smart/fast/budget → MiniMax-M3`
    empty-baseline pair → the S9 hook stays DORMANT (no new `model-compatibility.md` row). The
    plan asserts this explicitly; if any area config later names a different pair, that's a
    separate qualified row before merge.

## Non-goals

- Playbook/MCP **execution** wiring into the deep agent (recorded by-reference in `agent_config`
  only; consuming them is a later slice — neither is wired to deep agents today).
- Per-area memory backends (the `CompositeBackend` `/memories/{company,practice,user,matter}/`
  plan is its own slice).
- A general area-creation UI (admin edits the seeded rows; user-added areas are schema-supported
  — declarative, no code branches — but the create-area surface is later).
- The subagent TREE rendering in the UI (F1-S4 consumes deepagents v3 projections); S3 only
  stands up the per-area agent that CAN fan out, with the security guard enforced.
- Legacy-surface design rollout (separate slices, S2.1 plan §Goals-3).

## Files

- `api/alembic/versions/0054_practice_area_config.py` — additive columns + FK + audit column +
  `practice_area_skills` join + module-level testable `_seed_commercial_config(conn)` (extends
  Commercial with a real profile + tier floor; check-before-write idempotent, 0053 precedent).
- `api/app/models/practice_area.py` (+config columns, skills relationship),
  `models/project.py` (+`practice_area_id`), `models/audit.py` (+`practice_area_id`),
  new `models/practice_area_skill.py`.
- `api/app/schemas/practice_areas.py` (+config Read/Write schemas, strict `agent_config`
  validation), `schemas/agent_runs.py` (MatterActivity +area fields).
- `api/app/api/practice_areas.py` (+admin PATCH + skill attach/detach),
  `api/app/api/agent_runs.py` (`list_matter_activity` area filter/group; sandbox `project_id`
  rejection at `POST /agents/runs`), `api/app/api/projects.py` (set `practice_area_id` on
  create, validate area `configured`).
- `api/app/agents/area_agent.py` (NEW — the renderer + the `reject_model_bearing_subagents`
  guard), `agents/factory.py` (`build_deep_agent` calls the guard), `agents/composition.py`
  (load area, fold profile/tier/skills/subagents), `agents/guard.py` (+`practice_area_id` in
  `GuardContext`+audit), `app/audit.py` (+`practice_area_id` param).
- `web/src/lib/lq-ai/api/practiceAreas.ts` (+config fields + admin client),
  `api/agents.ts` (MatterActivity +area), `cockpit/{AreaGrid,MattersPanel,Cockpit,NewMatterDialog}.svelte`.
- `docs/adr/F010-per-area-deep-agent.md` (NEW), `docs/db-schema.md`, `docs/fork/HANDOFF.md`.
- Tests: extend `tests/test_practice_areas.py` (config + idempotent re-seed + admin authz +
  404), new `tests/agents/test_area_agent.py` (renderer + **model-bearing-subagent rejection**
  + tier-floor min + skills attach), `tests/agents/test_matter_activity.py` (area filter/group),
  `tests/test_openapi.py` (count 126 → new N + EXPECTED_PATHS), `tests/test_endpoints.py`
  (IMPLEMENTED_ROUTES), web vitest for the cockpit area-filtering.

## Verification (ADR-F005 gate — security-sensitive: agent composition + gateway path)

- Containerized: `api` pytest on throwaway pgvector at alembic head incl. 0054 (counts quoted);
  `web` `npm run check` + `npm run test:frontend` (counts quoted). ruff pinned to CI's version.
- CI green ×3.
- Live: rebuild `api`+`arq-worker`+`ingest-worker` together (migration) AND `web`; cockpit files
  a matter under Commercial and the agent runs a real MiniMax-M3 turn grounded by the area
  profile (evidence: receipt + screenshot); a second area stays inert; cypress f1-s2-cockpit +
  f1-s21-responsive regression.
- **Extra security pass** (ADR-F005, gateway/agent path): adversarial review focused on the
  subagent model-bypass guard (can a string `model` reach `init_chat_model` by any path? nested
  subagents? `CompiledSubAgent`/`AsyncSubAgent`? config round-trip from the API?), B-class param
  leakage (matter/user/scope never in an LLM-visible tool schema), authz (config writes
  admin-only, 404-not-403), and that area config (untrusted-ish operator input) can't inject a
  provider call or escape the gateway.
- Fresh-context adversarial review of the full diff; blockers fixed or deferred on record.
- ADR-F010 drafted; HANDOFF overwritten for the next slice.

## Deviations

(filled during implementation)
