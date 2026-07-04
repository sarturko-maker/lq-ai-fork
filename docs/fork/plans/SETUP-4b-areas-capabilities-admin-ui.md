# Plan — SETUP-4b: Practice Areas + Capabilities admin surfaces

Status: ACCEPTED (working model — lead-authored, maintainer-ratified ladder)

## Context

SETUP-4a (ADR-F062, PR #219) shipped the backend: tool-group availability as DATA
(`practice_area_tool_groups`), a code registry (`TOOL_GROUP_REGISTRY`) resolving group
names to grants, `POST`/`DELETE /practice-areas` CRUD, the tool-group attach/detach pair,
and deployment-wide (Level 0) capability toggles (`GET`/`PATCH /admin/capabilities`). None
of it has a web surface yet — an org-admin can only reach these endpoints via curl. This
slice builds the two admin pages over that backend (plus four small backend enablers the
UI needs) so an org-admin can actually create/configure/reorder/delete practice areas and
narrow the deployment's capability set from the browser.

## Goals

1. `/lq-ai/admin/areas` — list areas (position order), create (registry-bounded), reorder,
   per-area detail/edit (doctrine, name, unit noun, tier floor, subagent roster JSON),
   bind/unbind skills + playbooks + tool-groups, delete with the 409 live-matter UX.
2. `/lq-ai/admin/capabilities` — Level-0 enable/disable of tool-groups/skills/playbooks
   with optimistic flip + revert, MCP visible-but-disabled, model menu read-only.
3. Four enabling backend additions (below).
4. Full gen-B discipline; both pages transparent (every doctrine/skill/grant readable).

## Non-goals

- NO F054 status flip, NO budget-profile defaults, NO viewer RBAC (all SETUP-5). NO
  tenant-authored skills, NO branding, NO MCP wiring, NO per-tool toggles (group
  granularity only), NO migration, NO change to TOOL_GROUP_REGISTRY / composition loop /
  build_area_inventory / guarded_dispatch, NO operator-surface changes, NO rebuild of the
  matter-level CapabilitiesPanel.

## Decisions

- D1: Two new gen-B admin pages + one detail sub-route: `/lq-ai/admin/areas`,
  `/lq-ai/admin/areas/[key]`, `/lq-ai/admin/capabilities`. Nav links "Practice areas" +
  "Capabilities" added to `web/src/routes/lq-ai/(app)/admin/+layout.svelte` navLinks array
  (plain admin links, NOT operator-gated). Per-page onMount admin guard (Users-page idiom:
  redirect to /lq-ai/login when unauthenticated, to /lq-ai when not is_admin; server 403s
  regardless).
- D2: `PracticeAreaRead` gains `bound_tool_groups: list[str]` (REGISTRY-CANONICAL order =
  TOOL_GROUP_REGISTRY insertion order ∩ the area's rows — never DB row order, ADR-F062 D4)
  and `bound_playbooks: list[BoundPlaybook]` where `BoundPlaybook{id: uuid, name: str}`
  (join to non-soft-deleted playbooks). Extend `_to_read` in
  `api/app/api/practice_areas.py`; batch queries on the list path (one query per join
  table across all areas — no N+1). The flat list stays the only read path (no
  GET /{key} endpoint; the detail page picks from the list client-side).
- D3: `PracticeAreaConfigUpdate` gains optional `name` + `unit_label` (min_length=1,
  max_length=200, same as create). Partial-update (exclude_unset) semantics preserved;
  `configured` derivation untouched; updated_at stamped; audit details keep listing changed
  field names.
- D4: NEW `POST /practice-areas/reorder`, AdminUser. Body
  `PracticeAreaReorderRequest{keys: list[str]}` (extra="forbid", min 1, max 200 items, item
  bounds 1..200 chars). Server validates the payload is EXACTLY a permutation of ALL
  existing area keys (compare as sets AND lengths — duplicates rejected) else 422
  HTTPException (reject, don't sanitize — a mismatch means a stale client; the UI
  refetches). Lock all area rows FOR UPDATE ordered by key (deadlock-safe), renumber
  position = list index, stamp updated_at, audit `practice_area.reorder` (details = key
  list + count only), return the reordered PracticeAreaListResponse. Note: position has no
  unique constraint; existing ORDER BY position, key keeps ties stable.
- D5: "Enable" = the existing `configured` semantics (derived from non-empty profile_md).
  NO new enabled column, NO migration. UI shows a "Not configured" badge and the hint "Add
  doctrine to activate" instead of a fake toggle.
- D6: Subagent roster (`agent_config`) edited as a raw JSON textarea on the detail page:
  pretty-print on load (JSON.stringify(v, null, 2)), client-side JSON.parse gate on save,
  server 400 (ValidationError, field=agent_config) message surfaced verbatim. Show a
  caption noting a NEW area must attach skills before its roster may reference them (POST
  validates against an empty allow-list).
- D7: Attach catalogs for both pages come from `GET /admin/capabilities` (tools section =
  registry order, skills = live registry, playbooks = live rows; labels + descriptions
  included). No new catalog endpoints. Attach controls offer only catalog entries not yet
  bound.
- D8: NEW `GET /admin/model-menu`, AdminUser (NOT OperatorUser). Locate the existing
  operator alias-list endpoint in `api/app/api/admin.py` (the gateway proxy seam the
  /admin/models page uses) and reuse the SAME gateway client/config seam — but strip the
  response to exactly `{"aliases": [{"alias": str, "tier": int|null}]}`. NOTHING else
  forwarded: no provider names, no model ids, no base URLs, no fallbacks, no key material.
  Rationale (record in code comment): plan §7 row 6 ratified — model menu read-only visible
  to org-admins; alias+tier is already member-visible in the run composer; the F061 fence
  (writes + full config) is untouched. Gateway unreachable → return 502/503/504 consistent
  with the existing proxy's error handling; the UI degrades to an "unavailable" note.
  Read-only GET — no audit row (matches GET /admin/capabilities).
- D9: Level-0 toggle writes: ONE PATCH per flip (`{toggles: [{kind, key, enabled}]}` single
  element), optimistic flip + revert-on-error + an in-flight Set keyed `${kind}:${key}`
  preventing double-submit. No run-lock (deployment-wide). 422 unknown-key surfaces
  verbatim.
- D10: Route-guard bookkeeping for the 2 new routes (guard files updated, count verified
  against the actual openapi test).
- D11: Tests — web: page-helpers.ts + __tests__/page-helpers.test.ts per page (pure
  vitest, NO @testing-library/svelte — it is not installed); api: dedicated endpoint tests
  for the read-model fields, PATCH name/unit_label, reorder, and the model-menu strip-down.

## Implementation

### A. Backend

- A1. `api/app/schemas/practice_areas.py`: add `BoundPlaybook` (id: uuid.UUID, name: str);
  extend `PracticeAreaRead` with `bound_tool_groups: list[str]` + `bound_playbooks:
  list[BoundPlaybook]`; extend `PracticeAreaConfigUpdate` with `name`/`unit_label`; add
  `PracticeAreaReorderRequest` (extra="forbid").
- A2. `api/app/api/practice_areas.py`: extend `_to_read` (it currently takes bound skill
  names — extend its signature to also take bound group keys + bound playbooks; keep all
  callers correct: list path batches, mutation paths may load per-area); PATCH handles
  name/unit_label; NEW reorder route per D4 (registered above the parameterized routes for
  clarity, even though no real ambiguity exists today).
- A3. `api/app/api/admin.py`: NEW GET /admin/model-menu per D8 + response models
  (Pydantic, exact fields only).
- A4. Tests: extend `api/tests/test_practice_areas.py`: read-model fields present +
  bound_tool_groups CANONICAL order proven by attaching in reverse-canonical order; PATCH
  name/unit_label happy + bounds; reorder happy (positions renumbered, response ordered) /
  missing key 422 / extra key 422 / duplicate key 422 / non-admin 403 / audit row written
  (counts+keys only). New model-menu tests (`api/tests/test_admin_model_menu.py`): strips
  to alias+tier (feed a fake gateway payload with extra fields incl. a would-be secret
  field and assert absence), member 403, admin 200, gateway-error degradation. Update guard
  files per D10.

### B. Web API clients + types

- B1. `web/src/lib/lq-ai/api/practiceAreas.ts`: add createPracticeArea,
  updatePracticeArea, deletePracticeArea, reorderPracticeAreas, attachSkill/detachSkill,
  attachPlaybook/detachPlaybook, attachToolGroup/detachToolGroup — all via `apiRequest`
  from './client'. Extend the `PracticeArea` type with the two new read fields.
- B2. `web/src/lib/lq-ai/api/admin.ts`: add getDeploymentCapabilities,
  patchDeploymentCapabilities, getModelMenu + local types mirroring
  DeploymentCapabilitiesResponse / DeploymentCapabilitySection /
  DeploymentCapabilityRead / DeploymentToggleInput / the model-menu shape (mirror
  `api/app/api/admin.py` models exactly).

### C. `/lq-ai/admin/areas` list + create page

`web/src/routes/lq-ai/(app)/admin/areas/+page.svelte` + `page-helpers.ts` +
`__tests__/page-helpers.test.ts`. Gen-B ONLY: PageShell(size="wide")/SectionHeader/
ModalShell/Table/Badge/Alert/FormControl/Button/Input from the exact paths the Users page
imports; semantic tokens only; Svelte 5 runes. Table in server order: name, key, unit
label, status Badge, tier floor (or "—"), bound counts, ↑/↓ reorder buttons; row name links
to the detail page. "New practice area" ModalShell: key/name/unit label/doctrine
(optional)/tier floor select/tool-group checkboxes from the D7 catalog. NO roster field. On
201 → goto the detail page. Load: onMount guard then Promise.all([listPracticeAreas(),
getDeploymentCapabilities()]).

### D. `/lq-ai/admin/areas/[key]` detail page

`.../areas/[key]/+page.svelte` + `page-helpers.ts` + `__tests__/page-helpers.test.ts`.
Loads listPracticeAreas + getDeploymentCapabilities; picks the area by route param; unknown
→ inline not-found state + back link. Edit card: name/unit label/doctrine
(maxlength 20000, char count)/tier-floor select — Save = ONE PATCH containing ONLY dirty
fields (diffPatch). Roster card per D6. Three bind cards (tool groups/skills/playbooks):
current bindings + Detach; attach `<select>` of not-yet-bound catalog entries + Attach.
When 2+ ledger-bearing tool groups are attached, a caption notes only the first streams
live changes (LEDGER_BEARING_GROUPS = ['redlining', 'ropa']). Danger zone: Delete with
inline-confirm; 409 renders the server message + active_matter_count; 204 → goto the list.

### E. `/lq-ai/admin/capabilities` page

`.../capabilities/+page.svelte` + `page-helpers.ts` + `__tests__/page-helpers.test.ts`.
Sections from getDeploymentCapabilities (Tools/Skills/Playbooks), each with a "N of M on"
summary + a hand-rolled role="switch" (copied from, not imported from, the matter
CapabilitiesPanel — deployment surface, no run-lock). Toggle per D9. MCP section:
visible-but-disabled placeholder. Models section: read-only rows from getModelMenu, muted
"unavailable" note on error. Page-level explainer: "Disabling a capability here removes it
from every matter's capability panel."

### F. Docs + nav + plan

- F1. Nav links in `web/src/routes/lq-ai/(app)/admin/+layout.svelte`.
- F2. ADR addendum on `docs/adr/F062-tool-group-registry-deployment-toggles.md`.
- F3. This plan file.

## Verification

- Backend: targeted `pytest` on `tests/test_practice_areas.py`,
  `tests/test_admin_model_menu.py`, `tests/test_deployment_capabilities_api.py`,
  `tests/test_practice_area_playbooks_api.py`, `tests/test_endpoints.py`,
  `tests/test_openapi.py` inside the containerized dev image (`lq-ai-api-dev`), plus
  `mypy app` (standard mode). New `/api/v1` routes added to `IMPLEMENTED_ROUTES` +
  `EXPECTED_PATHS` and the `len(actual)` count bumped.
- Frontend: `npm run check` (svelte-check, 0 errors) + `CI=1 npx vitest run` (all
  page-helpers suites green, full repo suite green — no regressions).
- `ruff format`/`ruff check` from the repo root (root `ruff.toml`, line-length 100) on
  every touched Python file.
- Live verification (lead): exercise the two pages against the dev stack — create an area,
  reorder, bind/unbind a skill/playbook/tool-group, edit the roster, delete a
  live-matter-blocked area, flip a Level-0 toggle and confirm it narrows a matter's
  capability panel.
