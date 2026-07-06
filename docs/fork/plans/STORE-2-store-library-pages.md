# STORE-2 — Store + Library admin pages (web slice over the STORE-1 substrate)

**Status: implemented with the slice** (lead-drafted 2026-07-06; implemented 2026-07-06). Parent plan:
`docs/fork/plans/STORE-org-library.md` (maintainer-decided); ADR-F065 (proposed). STORE-1
(merged `faba2947`, PR #225) shipped the substrate: `org_library_entries`, POST/DELETE
`/api/v1/admin/library`, the PATCH shim, `in_library` on GET `/admin/capabilities`, bind-time 422.

## Goal

Make the Library visible and the Store browsable — "clean and clear UX" for a **non-technical
admin** (a practice lawyer wearing the admin hat). Two new admin pages + a member-readable
Library view + Library-scoped area pickers + skill-source links (closes ONBOARD gap G5) + the D5
provenance-parser fallback (closes G4b). Thin backend enablers only. **NO migration.**

## Non-goals

- No change to `build_area_inventory`, `guarded_tool_call`, grants-in-code, the gateway, or any
  agent runtime behaviour. `api/tests/agents/test_registry_parity.py` must remain UNMODIFIED.
- No remote store / downloads / version sync; no org-authored skills; no MCP wiring (placeholder
  card only); no operator-fence changes; no template catalog.
- No new mutating endpoints (the mutating-route pin 126 must not move).

## Decisions (lead calls, recorded here + in the ADR-F065 STORE-2 addendum)

- **D-A — Store page data = extended `GET /admin/capabilities`.** `DeploymentCapabilityRead`
  grows additive optional fields: `source: str | None`, `author: str | None`,
  `version: str | None`, `tags: list[str]` (default `[]`), `recommended_for: list[str]`
  (default `[]`, shipped area keys). Populated in `_deployment_inventory`
  (`api/app/api/admin.py:1532-1584`): skills from `record.summary()` (source/author/version/tags
  — D5 makes author/version real for community skills); tool groups get `source="built-in"`,
  author/version `None`; playbooks get `source=None` (DB rows, provenance unknown — the web shows
  a badge only when `source` is present). The PATCH echo carries the same fields (additive, old
  page unaffected during its one-commit remaining life).
- **D-B — Member-readable Library = NEW `GET /api/v1/library` (ActiveUser).** Transparency rule
  ("every prompt/skill/instruction that can shape an agent's behaviour must be inspectable") via
  the house dual-exposure precedent (`GET /api/v1/inference/tier-config`,
  `api/app/api/inference.py:201-219`, is ActiveUser while the admin write surface stays fenced).
  Returns ONLY adopted entries, joined to their catalogs for display metadata. **`adopted_by` is
  NOT on the wire** (member-visible surface; no cross-user IDs). Where-used is computed
  **client-side** from `GET /practice-areas` (already ActiveUser, already returns `bound_skills`
  + `bound_tool_groups` + `bound_playbooks` per area — recon-verified, zero backend needed).
- **D-C — Recommended sets become a drift-guarded code constant.** No runtime source exists today
  (the shipped defaults live in SIX migration literals). New constant in
  `api/app/agents/capabilities.py`: `RECOMMENDED_LIBRARY_SETS: dict[str, dict[str, tuple[str, ...]]]`
  — area key → `{KIND_TOOL: (...), KIND_SKILL: (...)}`, insertion order canonical
  (commercial → privacy → m-and-a → disputes → employment). Content = the union of the seed
  migrations (transcribe EXACTLY, do not invent): `0056_default_area_skill_bindings.py`
  `_DEFAULT_BINDINGS` + the later skill-binding INSERTs in `0067` (commercial surgical-redline),
  `0069` (matter-memory skill, every standard area), `0072` (commercial negotiation-review),
  `0073` (commercial roster skill if it binds one — read the file), `0083` (tabular-review), plus
  `0086` `_SEED_TOOL_GROUPS` (commercial: redlining+tabular; privacy: ropa+assessment). Docstring
  names those migrations as the provenance. A guard test pins that every referenced tool key is
  in `TOOL_GROUP_REGISTRY` and every skill name loads from the real `skills/` corpus — a renamed
  skill must break CI, not silently drop a recommendation. Playbooks: none recommended (no seed
  binds any — verified).
- **D-D — The old Capabilities page becomes a client-side redirect stub.** This SPA has
  `ssr = false` and zero `+page.ts` files — the app's only redirect idiom is `onMount` → `goto`.
  The stub keeps the route (old bookmarks land on `/lq-ai/admin/library` via
  `goto(..., { replaceState: true })`). The page's two non-Library sections relocate or die:
  the **MCP placeholder moves to the Store page** (it is catalog-shaped: "coming soon" card);
  the **read-only Models section is DROPPED** — it re-projected the member-visible
  `GET /api/v1/models` verbatim (the SETUP-4b review's own "check who can ALREADY see the data"
  lesson), and the operator Models page is the authoritative surface. On record for the
  maintainer to veto. Delete the dead `capabilities/page-helpers.ts` + its `__tests__` (the
  redirect stub needs none of it).
- **D-E — D5 fallback (parser): top-level `author:`/`version:` from `SkillFrontmatter.model_extra`,
  used only when the `lq_ai:` block lacks the field; `lq_ai:` wins on conflict; accept `str`
  values only** (a YAML `version: 1.0` float falls through to `"unversioned"` — honest, not
  coerced). Template = `extract_inputs`' dual-location pattern (`api/app/skills/schema.py:324-341`);
  the change lands in `derive_summary` (schema.py:366-402). Recon: 35 community skills carry
  top-level `author:`, 37 carry top-level `version:`; zero built-ins do (theirs nest under
  `lq_ai:`) — so built-in behaviour is provably unchanged.
- **D-F — D6 remove-confirm: always a modal.** If the entry is bound in ≥1 area: list the area
  NAMES + plain-language warning ("The {area} agent will lose this — it stays attached but stops
  resolving until you add it back."). If bound nowhere: "Not attached to any practice area."
  Confirm executes `DELETE /admin/library/{kind}/{key}` then refreshes.
- **D-G — Member Library route `/lq-ai/library`** (read-only render of D-B + where-used), guarded
  only on being authenticated. Add a nav link ONLY if a natural member-nav slot exists (mirror
  wherever `/lq-ai/skills` is linked); if none exists, the route standing alone is acceptable v1 —
  document the call in the PR.

## Backend changes (THIN — no migration, no new mutating route)

1. **`api/app/skills/schema.py`** — D5 in `derive_summary`: resolve
   `version = lq.version or _top_level_str(frontmatter, "version") or "unversioned"` and
   `author = lq.author or _top_level_str(frontmatter, "author")` (tiny helper reading
   `frontmatter.model_extra`, `isinstance(v, str)` + non-empty guard). Update the docstring to
   name both locations (mirror `extract_inputs`' docstring style). Everything else untouched.
2. **`api/app/agents/capabilities.py`** — `RECOMMENDED_LIBRARY_SETS` (D-C) near the
   registry, with the provenance docstring. Nothing else in this module changes.
3. **`api/app/api/admin.py`** — D-A field additions on `DeploymentCapabilityRead` (docstring:
   additive STORE-2 fields; `recommended_for` = shipped-default area keys sourced from
   `RECOMMENDED_LIBRARY_SETS`) + populate in `_deployment_inventory`. Build a small
   `(kind, key) -> [area keys]` reverse map from the constant once per call.
4. **NEW `api/app/api/library.py`** — router `APIRouter(prefix="/library", tags=["library"])`,
   one endpoint `GET /api/v1/library` (D-B), `user: ActiveUser`, returns
   `LibraryResponse { entries: list[LibraryEntryRead] }` where `LibraryEntryRead` =
   `{ kind, key, label: str | None, description: str | None, source: str | None,
   author: str | None, version: str | None, adopted_at: datetime }`. Join each
   `OrgLibraryEntry` to its catalog (TOOL_GROUP_REGISTRY / skill registry snapshot / live
   playbooks — reuse the exact label derivations `_deployment_inventory` uses; factor a tiny
   shared helper if it avoids drift, don't copy-paste two label formats). A dangling entry
   (adopted, then the playbook was deleted / the skill left the catalog) returns `label=None` —
   the web renders it honestly. Ordering: kind in canonical order (tool → skill → playbook), then
   label (case-insensitive, `None` last), then key. Docstring: cite ADR-F065 + the tier-config
   transparency precedent + why no `adopted_by`.
5. **`api/app/main.py`** — mount the router exactly like its siblings.
6. **Pins** — `api/tests/test_openapi.py`: `EXPECTED_PATHS` += `"/library"`, count comment
   `173 → 174` (follow the STORE-1 delta-comment style at lines ~398-400);
   `api/tests/test_mutation_rbac.py:150` path pin `173 → 174` with a matching docstring note.
   The mutating pin (126) and gated pin (68) MUST NOT change.

## Web changes

All pages: gen-B primitives (`PageShell`/`SectionHeader`/`Card`/`cardClass`/`cardGridClass`/
`ModalShell`/`Alert`/`FormControl`), semantic tokens, `data-testid` `lq-*` naming, the uniform
`onMount` auth-guard idiom, `apiRequest`-based typed API modules (no raw fetch in pages), and the
sibling-`page-helpers.ts` + `__tests__/page-helpers.test.ts` pattern (vitest, no Svelte compiler).
Plain language everywhere — never "registry", "capability", "binding" in user-facing copy; say
"tool", "skill", "playbook", "attached to a practice area", "Add to Library".

1. **API types** — `web/src/lib/lq-ai/api/admin.ts`: capability entry type gains `in_library`,
   `source`, `author`, `version`, `tags`, `recommended_for`. NEW `web/src/lib/lq-ai/api/library.ts`:
   `getLibrary()` → `GET /library` (+ types). Export via the api index like siblings.
2. **NEW `/lq-ai/admin/store/+page.svelte`** (admin-gated: the capabilities page's two-tier
   guard). Data: `getDeploymentCapabilities()` + `listPracticeAreas()` (for rail labels only).
   Layout top-to-bottom:
   - Teaching header: "Everything that ships with LQ.AI Oscar Edition. Add what your firm uses to
     your Library." + a link to the Library page.
   - **Recommended rail**: one card per area key present in any `recommended_for` (constant
     order), title "Recommended for {org's area name, else humanised key}", the recommended
     entries as chips with adopted state, and ONE button: "Add all ({N remaining})" → sequential
     `POST /admin/library` for each missing entry (continue past failures, surface
     `describeMutationError`, refresh once at the end). All adopted ⇒ "All in your Library ✓"
     (disabled).
   - Kind sections (Tools / Skills / Playbooks) as card grids. Each card: title (skill titles
     link to `/lq-ai/skills/{name}` — G5), one-line description, provenance badge (skills:
     "LQ built-in" or "Community" + author + version when present; tools: "LQ built-in";
     playbooks: none), and ONE action: **Add to Library** / **In Library ✓** (inert).
   - Search input filtering all sections client-side (label/key/description/tags —
     `SkillPicker.svelte:29-40` is the house pattern).
   - MCP section: the "coming soon" placeholder card relocated from the old page (D-D).
3. **NEW `/lq-ai/admin/library/+page.svelte`** (admin-gated). Data: `getLibrary()` +
   `listPracticeAreas()`. Empty state (teaching, D-decision 3 of the parent plan): "Your library
   is empty — browse the Store to add what your firm uses." + a Browse-the-Store button. Cards
   grouped by kind: provenance badge, skill-name links, **where-used line** ("Attached to:
   Commercial, Privacy" / "Not attached to any practice area") computed from the practice-areas
   response (skills match `bound_skills` names; tools match `bound_tool_groups` keys; playbooks
   match `bound_playbooks[].id` as string), **Remove** → the D-F modal. Dangling entries
   (`label === null`): render the key + "No longer in the shipped catalog", Remove still offered.
4. **NEW `/lq-ai/library/+page.svelte`** (member read-only, D-G): same card list minus all
   actions, header copy "Your organisation's Library — what your firm has adopted for its
   agents. Read-only." Share the rendering (a `$lib` component or shared helpers — implementer's
   structural call, but the where-used/grouping/badge logic must live ONCE, in tested helpers).
5. **Redirect stub** — `/lq-ai/admin/capabilities/+page.svelte` (D-D): auth-guard then
   `goto('/lq-ai/admin/library', { replaceState: true })`. Delete `capabilities/page-helpers.ts`
   + `capabilities/__tests__/` entirely.
6. **Admin nav** — `admin/+layout.svelte:11-21`: replace the `Capabilities` link with `Store` and
   `Library` entries (after `Practice areas`).
7. **Area-detail pickers Library-scoped** — `admin/areas/[key]/+page.svelte`: filter the picker
   catalogs to `in_library === true` before `unboundOptions`. Add the missing `{:else}` empty
   states on all three bind cards (recon: lines ~454/505/556 currently render nothing),
   distinguishing honestly: library has no entries of this kind → "Your library has no
   {tools/skills/playbooks} yet — browse the Store" (link); everything adopted is already
   attached → "Everything in your library is already attached." Skill names in the bound list
   (line ~486) become links (G5).
8. **`web/src/lib/lq-ai/components/matter/CapabilitiesPanel.svelte`** — skill entry labels become
   links to the source viewer (G5). Touch ONLY the label rendering — the panel's toggle logic has
   a known latent snapshot-revert defect (backlogged); do not refactor it in this slice.

## Tests

- **api**: D5 tests in `api/tests/test_skill_loader.py` after the derive-summary block
  (~line 202): top-level fallback for author + version; `lq_ai:` precedence when both present;
  non-str top-level version ignored (float 1.0 → "unversioned"). Provenance + `recommended_for`
  assertions in `api/tests/test_deployment_capabilities_api.py` (additive fields; e.g. redlining
  carries `recommended_for == ["commercial"]`). NEW `api/tests/test_library_read_api.py`
  (style = `test_org_library_api.py`): member AND viewer get 200 (ActiveUser surface); returns
  only adopted entries with catalog metadata; dangling entry → `label is None`; canonical
  ordering; `"adopted_by" not in` any serialized entry; unauthenticated 401. The D-C guard test
  (every recommended key resolves against the real registries/corpus — the corpus-health test in
  `test_skill_loader.py` shows how to load the real `skills/` tree). Pin updates (174/174).
- **web**: `__tests__/page-helpers.test.ts` per new page — Store: rail derivation from
  `recommended_for` + `in_library` (missing count, add-all list), search predicate, badge label
  fn; Library: where-used map across all three kinds (playbook id-as-string match!), grouping/
  ordering, D-F modal listing; shared helpers tested once. `npm run check` (svelte-check) 0
  errors; `CI=1 npx vitest run` green (bare `vitest` is watch mode — never use it).
- **Cypress (write, do NOT run)** — NEW `web/cypress/e2e/store-library.cy.ts`, NET-ZERO on data:
  login → Store renders rail + sections → adopt one currently-unadopted entry → Library shows it
  with where-used → Remove modal (on a BOUND entry assert the area list, then CANCEL) → remove
  the entry adopted earlier → area-detail picker shows the Store empty-state link when the
  library lacks that kind. Parameterize creds via `Cypress.env('LQ_EMAIL')`/`('LQ_PASSWORD')`
  (helpers file pattern). The lead runs it against an isolated stack at the gate.

## Verification the implementer runs (quote outputs in the PR)

- Web (host): `cd web && npm run check && CI=1 npx vitest run`.
- API targeted, in the dev image with the WORKTREE-ROOT mount (api-only mounts break repo-root
  tests) — `<wt>` = your worktree:
  `docker run --rm --network lq-ai_default -v <wt>:/repo -w /repo/api -v <wt>/skills:/skills:ro
  -e LQ_AI_SKILLS_DIR=/skills -e DATABASE_URL="$(docker compose -f
  /home/sarturko/LQ_AI_Fork/docker-compose.yml exec -T api printenv DATABASE_URL)" lq-ai-api-dev
  pytest tests/test_skill_loader.py tests/test_library_read_api.py tests/test_org_library_api.py
  tests/test_deployment_capabilities_api.py tests/agents/test_capabilities.py
  tests/test_openapi.py tests/test_mutation_rbac.py tests/test_endpoints.py -q`
  (command substitution keeps the URL out of your transcript — NEVER print or commit it; the
  conftest creates its own throwaway `lq_ai_test_<hex>` DB and never touches the dev DB).
- Lint/type: from the REPO ROOT of the worktree (the root `ruff.toml`, line-length 100, must
  apply — the dev image's default silently rewraps): `ruff check api scripts &&
  ruff format --check api scripts`; then `cd api && mypy app`. Match CI's commands exactly.
- Do NOT run the full api suite (the lead runs it ALONE at the gate — CPU-contention flakes).
- Do NOT run Cypress (needs a live stack; lead's gate).

## Deliverables

Branch `fork/store-2-store-library-pages` off main. Commit this brief verbatim as
`docs/fork/plans/STORE-2-store-library-pages.md` (status line → "implemented with the slice").
Draft the **ADR-F065 "STORE-2 implementation record" addendum** (D-A…D-G, one paragraph each —
match the STORE-1 addendum's register). Small, reviewable commits; messages reference ADR-F065
and end `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`. Push and open the PR with
`gh pr create --repo sarturko-maker/lq-ai-fork` (NEVER bare — a bare call resolves to the FROZEN
upstream), base `main`, title `[fork] STORE-2: Store + Library admin pages (ADR-F065)`; body =
what/why, decisions D-A…D-G table, quoted verification outputs, and end with
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Hard constraints (violations = the review rejects the slice)

- Public repo: no secrets/keys/URLs-with-creds in code, tests, fixtures, docs, or the PR.
- Authz: the new GET is ActiveUser by design (D-B); everything else keeps its gate. No new
  mutating routes. Parameterized SQL only (SQLAlchemy constructs). Pydantic at the boundary.
- Do NOT touch: `api/tests/agents/test_registry_parity.py`, `build_area_inventory`, the guard/
  grants seams, migrations, the untracked strays (`sample-documents/`,
  `api/tests/agents/scenarios/test_*_live.py`), HANDOFF.md, MILESTONES.md. Never `git add -A`.
- The matter CapabilitiesPanel change is LINK-ONLY (see Web #8).
- `enabled` stays on the wire (deprecated alias) — removing it is a later cleanup, not this slice.
