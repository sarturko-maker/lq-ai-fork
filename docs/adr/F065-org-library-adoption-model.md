# F065 — Org Library adoption model (Store / Library / Area Binding)

Status: proposed
Date: 2026-07-05
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
