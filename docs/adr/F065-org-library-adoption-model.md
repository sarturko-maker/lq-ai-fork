# F065 — Org Library adoption model (Store / Library / Area Binding)

Status: proposed
Date: 2026-07-05
Deciders: maintainer + agent lead
Slice: STORE-0
Plan of record: `docs/fork/plans/STORE-org-library.md` (maintainer-reviewed 2026-07-05, all open
questions answered). Supersedes the Level-0 *deployment capability toggle* semantics of ADR-F062
(the registry and availability-as-data decisions of F062 stand).

## Context

The ONBOARD-0 dress rehearsal (2026-07-05, `docs/fork/plans/ONBOARD-admin-experience.md` G4)
surfaced a structural UX confusion: everything LQ ships — skills (filesystem registry), playbooks
(DB rows), tool groups (code registry) — appears in the admin's "Capabilities" tab as if the
organisation had already chosen it. Availability is governed by ADR-F062's sparse, disable-only
`deployment_capability_toggles`: everything ships ON, and a row exists only where an admin turned
something OFF. Three consequences: (1) the admin experiences "un-configure LQ's worldview" instead
of "build my firm's library"; (2) LQ-inherited content is indistinguishable from organisational
set-up (maintainer: *"My NDA skill may be entirely different to what an LQ lawyer thinks it is"*);
(3) an area can bind a deployment-disabled capability with no warning — it silently vanishes at
resolve time in `build_area_inventory`. Maintainer directive: *"There needs to be a distinction
between LQ inherited skills and logical set up… I am thinking of LQ 'Store'… this takes priority.
We need clean and clear UX."*

Provenance metadata largely exists already (`SkillSource` built-in/community/user/team;
`lq_ai:` frontmatter `author`/`version`) but is surfaced nowhere.

## Considered Options

1. **Label-only** — keep the disable-only toggles; add provenance badges and better copy to the
   existing Capabilities tab.
2. **Adopt-in Org Library replacing the toggles** — a new `org_library_entries` table is the single
   source of "this org adopted X"; area bindings validate against and resolve through Library
   membership; the disable-only toggle layer is superseded and migrated.
3. **Four layers** — add the Library but keep the deployment toggles as an operator-level content
   kill-switch beneath it.
4. **No org layer** — areas bind directly from the shipped catalog; provenance badges only.

## Decision Outcome

**Option 2.** Three layers, one pool, two lenses: **Store** (shipped catalog, read-only,
provenance-labelled) → **Org Library** (what this organisation adopted) → **Area Binding** (what
each practice-area Deep Agent carries, picked from the Library only).

- Option 1 fixes the label, not the polarity — the org still never *chooses* anything.
- Option 3 was put to the maintainer explicitly; rejected ("why would an operator need a kill
  switch?"). Two off-switches with opposite polarities is the confusion this ADR exists to remove;
  under the Option-A stack-per-tenant charter (ADR-F058) deployment and org coincide anyway. A
  genuinely broken capability is fixed by shipping an update (it leaves the Store), not by a
  per-deployment switch. The F061 operator fence keeps infrastructure (models/providers/keys) —
  content availability becomes purely the org's Library.
- Option 4 loses the org-level identity ("what our firm uses") that motivates the whole change,
  and gives future org-authored content no home.

Recorded sub-decisions (D-numbers per the plan):

- **D1** Adoption is data (`org_library_entries`: kind ∈ {skill, playbook, tool}, key, adopted_by,
  adopted_at); tool *grants* stay code — the ADR-F062 invariant is untouched; the Library only
  narrows availability, adopt-in instead of disable-out.
- **D2** `deployment_capability_toggles` is superseded. The migration seeds the Library from the
  current **effective** state (bound-anywhere ∧ not-disabled), so **existing deployments change no
  behaviour on upgrade day**; "fresh org starts empty" applies to new orgs only.
- **D3** `build_area_inventory` (the single fail-closed chokepoint, `api/app/agents/capabilities.py`)
  swaps its narrowing predicate from not-disabled to Library membership; REQUIRED-kwarg posture kept.
- **D4** Bind-time validation gains the Library check (422 pointing at the Store) — closes the
  silent bind-while-unavailable trap.
- **D5** Provenance surfaced everywhere (source/author/version badges); loader falls back to
  top-level `author:`/`version:` frontmatter when the `lq_ai:` block lacks them.
- **D6** Removing a Library entry bound in N areas requires an explicit confirm listing the areas
  (no silent agent-behaviour change — "system proposes, user owns", ADR-0013 D4).
- **D7** No org-authored content in this milestone (ratified §7 no-v1: skills are prompt content —
  an injection surface requiring its own harness + ADR). Namespacing/resolution order is structured
  now so a future `org` tier can shadow a catalog slug (existing chain user > team > built-in).
- **D8** User-facing name: **"Store"** (maintainer-decided). UX is bound by the non-technical-admin
  constraint: plain language, a "Recommended for {area}" one-click add-all rail, teaching empty
  states.

## Consequences

- **Good:** the admin story becomes "build up your firm's library" with honest provenance; one
  off-state (*not in your Library*); bind-time errors instead of silent narrowing; a home for
  future org-authored content and for the template catalog (templates adopt-on-apply); the
  remote-store milestone gets a truthful UI to grow into.
- **Bad / cost:** a migration with seeding logic (and the toggle table's retirement — repurpose vs
  drop is the implementer's call in STORE-1, recorded in the migration docstring); a new admin
  mutation surface (authz: AdminUser, cross-org 404-not-403, audit counts/types/IDs only); the old
  Capabilities page is replaced (route redirect).
- **Invariants untouched:** grants-in-code (F062), `guarded_tool_call`, the gateway, the F061
  operator fence, viewer read-only enforcement (F064).
- Slices and verification: `docs/fork/plans/STORE-org-library.md` (STORE-0…3; STORE-3 is a live
  maintainer dress rehearsal as the acceptance test).

## STORE-1 implementation record (2026-07-06)

Backend-only slice implementing D1–D4 (D5–D8 are STORE-2/UX). The D1–D8 outcomes above are
unchanged; this records the implementer's calls the ADR left open.

- **Toggle supersession — DROP, not repurpose** (D2 left this to STORE-1). Migration `0088`
  reads `deployment_capability_toggles`' disabled set once (for the seed), then DROPs the table.
  Rationale: repurposing carries no data — the polarity inverts (a toggle row meant "disabled";
  a Library row means "adopted") and the shape changes (no `enabled` column), so a rename would
  leave every `enabled=false` row meaning the OPPOSITE. `downgrade()` recreates the toggle table
  EMPTY (byte-matching 0086's DDL) and drops `org_library_entries` — lossy by design (the seeded
  Library does not round-trip; there is no downgrade round-trip test). The
  `DeploymentCapabilityToggle` ORM model and all its usages are deleted; `OrgLibraryEntry`
  replaces it (PK `(capability_kind, capability_key)`, `adopted_by` FK SET NULL, no `enabled`).

- **Fresh-vs-existing discriminator = users-table emptiness at migration time.** A brand-new org
  runs migrations BEFORE the app lifespan mints the first operator/admin, so `users` is empty at
  0088's execution — the gate `EXISTS (SELECT 1 FROM users)` skips the seed and the Library starts
  EMPTY (decision 3). An existing deployment always has users, so it seeds from effective state:
  "bound anywhere ∧ not explicitly disabled" (`practice_area_skills` ∪ `practice_area_tool_groups`
  ∪ non-deleted `practice_area_playbooks`, minus `deployment_capability_toggles` rows with
  `enabled=false`), so upgrade day changes nothing (decision 4). The seed reads binding tables
  ONLY — a pure-SQL seed cannot consult the in-memory skill registry / code tool-group registry,
  so a bound name the registry no longer knows becomes a harmless ORPHAN Library row under the
  established drift-drop posture (`build_area_inventory` drops it at resolve time). The seed is a
  pure module-level `_seed(conn)` (idempotent NOT-EXISTS inserts, resilient to the toggle table
  being absent via `to_regclass`) so the test conftest can call it to emulate an upgraded
  deployment and the fresh-empty path is pinned independently on a throwaway DB.

- **D3 chokepoint predicate** — `build_area_inventory`'s required kwarg `deployment_toggles`
  became `library_entries` (still keyword-only + required); a binding resolves iff its
  `(kind, key)` is in the adopted set. Under adopt-in polarity a forgotten kwarg fails CLOSED
  (nothing adopted ⇒ nothing available); kept required anyway so call sites stay explicit.

- **PATCH-shim mapping** (D-compat, old Capabilities page kept working): `GET /admin/capabilities`
  grows `in_library` and reports `enabled` as its deprecated alias (single off-state). `PATCH
  /admin/capabilities` maps `enabled=true ⇒ adopt` (upsert `org_library_entries`) and
  `enabled=false ⇒ remove` the entry — a compatibility shim over the Library, audited as one
  `library.update` row (`adopted`/`removed` kind+key lists + counts).

- **Audit action names.** New endpoints: `library.adopt` / `library.remove` (`resource_type`
  `org_library`, `resource_id` = key, `details` = `{kind, key}`). The shim: `library.update`.
  All carry kinds/keys/counts only — never document content.

- **Authz.** All three surfaces are `AdminUser` (the operator passes it; F061 D3 / F064 D2 keep
  content-config operator-accessible). The F061 operator-fence route list is untouched. The adopt
  endpoint 409s a duplicate (house attach pattern); remove is idempotent 204 (house detach). D4
  adds a literal `HTTPException(422)` at all four bind surfaces AFTER the existing 404-unknown and
  BEFORE insert (distinct layers; existing 404/409 tests unchanged).

## STORE-2 implementation record (2026-07-06)

Web slice implementing D5–D8 (the Store + Library pages) over the STORE-1 substrate, plus a few
thin backend enablers. Plan: `docs/fork/plans/STORE-2-store-library-pages.md`.

- **D-A — provenance surfaced via additive fields on `DeploymentCapabilityRead`.** `source`,
  `author`, `version`, `tags`, `recommended_for` are populated in `_deployment_inventory`: skills
  from `SkillRecord.summary()` (real source/author/version/tags now that D5 closes the parser gap
  for community skills); tool groups get `source="built-in"` only; playbooks get `source=None` —
  DB rows carry no provenance field today, so the web shows a badge only when `source` is present.
  `recommended_for` is built once per call from a small `(kind, key) -> [area keys]` reverse map
  over `RECOMMENDED_LIBRARY_SETS`. The PATCH echo (the old Capabilities page's compatibility shim)
  reuses `_deployment_inventory`, so it carries the same fields for free — no separate wiring.

- **D-B — member-readable Library via a NEW `GET /api/v1/library` (`ActiveUser`).** Mirrors the
  `GET /api/v1/inference/tier-config` dual-exposure precedent: the admin write surface
  (`POST`/`DELETE /admin/library`) stays `AdminUser`-fenced; this GET is a separate, narrower read
  model over the same `org_library_entries` table, joined to catalog display metadata via the same
  derivations `_deployment_inventory` uses (a shared `playbook_display_label()` helper prevents the
  two surfaces' playbook label format from drifting apart). Returns ONLY adopted entries;
  `adopted_by` is deliberately never serialized (no cross-user identifiers on a member-visible
  surface). A dangling entry (adopted, then the catalog entry vanished) returns `label=None` so the
  web renders it honestly instead of guessing. Where-used is computed **client-side** from the
  already-`ActiveUser` `GET /practice-areas` response — recon confirmed it already returns
  `bound_skills`/`bound_tool_groups`/`bound_playbooks` per area, so no second backend read model
  was needed.

- **D-C — `RECOMMENDED_LIBRARY_SETS` is a new, drift-guarded code constant**
  (`app.agents.capabilities`), not a runtime derivation. No live source of "what ships bound to
  each area by default" existed before this slice — the shipped defaults were spread across six
  migration literals (`0056`'s initial seed plus five later one-off skill bindings, `0086`'s tool-
  group seed). The constant is a verbatim transcription of that union, area key -> `{tool: (...),
  skill: (...)}` in canonical area order (commercial, privacy, m-and-a, disputes, employment); no
  area recommends a playbook (verified — no seed migration binds one). It feeds ONLY the Store
  page's display rail; it does not touch `build_area_inventory` or any resolution chokepoint. Guard
  tests pin every referenced tool key against `TOOL_GROUP_REGISTRY` and every skill name against
  the real `skills/` corpus, so a rename breaks CI instead of silently dropping a recommendation.

- **D-D — the old Capabilities page becomes a client-side redirect stub.** This SPA has `ssr =
  false` and no `+page.ts` anywhere, so `onMount` -> `goto(..., { replaceState: true })` is the only
  available redirect idiom (there is no SvelteKit `redirect()` to reuse). Old bookmarks land on
  `/lq-ai/admin/library`. Of the old page's two non-Library sections: the MCP "coming soon"
  placeholder relocated to the Store page (catalog-shaped); the read-only Models section was
  DROPPED — it only re-projected the already member-visible `GET /api/v1/models` (the SETUP-4b
  review's "check who can ALREADY see the data" lesson), and `/lq-ai/admin/models` is the
  authoritative surface. The dead `capabilities/page-helpers.ts` + its `__tests__/` were deleted
  (confirmed no other module imported from them).

- **D-E — the D5 provenance-parser fallback lands in `derive_summary`.** `version = lq.version or
  _top_level_str(frontmatter, "version") or "unversioned"`; `author = lq.author or
  _top_level_str(frontmatter, "author")` — `lq_ai:` wins on conflict, and the new
  `_top_level_str` helper accepts `str` values only (a YAML `version: 1.0` float is left honestly
  absent rather than coerced). Mirrors `extract_inputs`'s existing dual-location read of
  `frontmatter.model_extra`. Zero built-in skills are affected (all nest under `lq_ai:`); the
  community submodule (35+/37+ skills with top-level `author:`/`version:`) is the corpus this
  closes the gap for.

- **D-F — the remove-confirm is ALWAYS a modal**, never a bare click-to-delete. Where-used (an
  entry's bound area names, from the same client-side `GET /practice-areas` computation as D-B)
  decides the copy: bound in ≥1 area lists the area names plus a plain-language warning ("The
  {area} agent will lose this — it stays attached but stops resolving until you add it back.");
  bound nowhere shows "Not attached to any practice area." and no warning line. Confirm calls
  `DELETE /admin/library/{kind}/{key}` (already idempotent from STORE-1) then refreshes.

- **D-G — member route `/lq-ai/library`, guarded only on being authenticated.** No admin gate,
  same card rendering as the admin Library page minus the Remove action, sharing every non-trivial
  derivation (grouping/where-used/provenance badge) via a new `$lib/lq-ai/library/page-helpers.ts`
  module so the two surfaces cannot disagree about the same adopted capability. No nav link was
  added: no natural member-nav slot exists without extending the shared `TABS`/`tabs.ts`
  vocabulary, a materially bigger change with its own blast radius and no icon/placement guidance
  in the plan — the brief explicitly allows the route to stand alone in v1.

- **Web client gap closed in passing.** STORE-1 shipped `POST`/`DELETE /admin/library` with no web
  client at all (nothing in the UI called them). This slice adds `adoptLibraryEntry` /
  `removeLibraryEntry` to `admin.ts` — the Store/Library pages are their first callers.
