# STORE — Catalog vs Org Library vs Area Binding

**Status: DRAFT for maintainer edit** (2026-07-05). Maintainer directive from the ONBOARD-0
walkthrough: *"There needs to be a distinction between LQ inherited skills and logical set up…
I am thinking of LQ 'Store'… My NDA skill may be entirely different to what an LQ lawyer thinks
it is."* and *"We need to move the store vs org idea — this takes priority. We need clean and
clear UX."* This milestone jumps the queue ahead of the template catalog and the other ONBOARD
gaps (which remain queued — see `ONBOARD-admin-experience.md`).

## The model (agreed in conversation, 2026-07-05)

Three layers, one pool, two lenses:

1. **The Store (catalog)** — what LQ ships: skills, playbooks, tool groups (and later, area
   templates). Provenance-labelled, versioned, read-only. It *exists* today as three registries
   (code `TOOL_GROUP_REGISTRY`, filesystem `skills/` scan, DB playbooks) but is invisible as a
   concept — everything shipped just appears in the admin's Capabilities tab as if the org had
   already chosen it.
2. **The Org Library** — what THIS organisation has deliberately **adopted** from the Store
   (and, in a later milestone, authored). The polarity inverts: today everything ships ON and the
   admin un-configures LQ's worldview; after this milestone the admin *builds up* their firm's
   library. Every entry carries provenance (LQ built-in / community / — later — yours).
3. **Area Binding** — what each practice-area Deep Agent carries: bindings pick **from the
   Library only**, never directly from the Store. The practice-area page stays the binding view.

## UX first (the directive is "clean and clear")

The admin nav's single confusing "Capabilities" page becomes two honest pages:

- **Store** (`/lq-ai/admin/store`) — browse everything shipped: cards grouped by kind
  (Skills / Playbooks / Tool groups), each with title, one-line description, provenance badge
  (`LQ built-in` / `Community` + author + version), and a click-through to the full SKILL.md
  source (the existing viewer — closes G5). One primary action per card: **Add to Library** /
  **In Library ✓** (with Remove available from the Library view). Search + filter by kind/tag.
- **Library** (`/lq-ai/admin/library`) — the org's adopted set: same cards, plus **where-used**
  ("bound in: Commercial, Privacy"), and **Remove from Library** (guarded when in use — see D6).
- **Practice-area detail** (existing page, adjusted) — the "Attach" pickers list **Library
  entries only**. If the admin knows something exists in the Store but not the Library, the
  picker's empty state links to the Store ("Not in your library? Browse the Store"). Skill names
  become links to the source viewer everywhere (G5).
- **Viewer/member view** (transparency rule): the Library is readable (not editable) by any
  authenticated user — every prompt/skill/instruction that can shape an agent's behaviour must be
  inspectable. The Store browse can be admin-only (Q-D8).

Everything above is deliberately boring UI: cards, badges, one verb per surface. No wizards here.

**Binding UX constraint (maintainer, 2026-07-05): admins may be non-technical people** (a practice
lawyer wearing the admin hat, not IT). Concretely: plain language everywhere ("Add to Library",
never registry/capability jargon); the Store shows a **"Recommended for Commercial / Privacy /…"
rail** with a one-click *add all* (the human-scale precursor of the template catalog, which later
formalises bulk adoption); empty states teach ("Your library is empty — browse the Store to add
what your firm uses"); and no step ever requires knowing what a tool group or binding *is* to
succeed.

## Decisions the ADR must make (ADR-F065, drafted in STORE-0)

- **D1 — Adoption is data; grants stay code.** A new `org_library_entries` table
  (kind ∈ {skill, playbook, tool}, key, adopted_by, adopted_at) is the single source of "adopted".
  The ADR-F062 invariant is untouched: tool *grants* (which tool names a group unlocks) remain
  code; the Library only narrows availability, exactly like the old toggles — but with adopt-in
  polarity instead of disable-out.
- **D2 — The old deployment toggles are superseded, not kept as a fourth layer.** Under Option A
  (stack-per-tenant) "deployment" and "org" coincide; keeping both a disable-gate AND an adopt-gate
  is two off-switches with different polarities — the opposite of clean. Migration seeds the
  Library from the current *effective* state (everything not-disabled that is bound anywhere, plus
  everything currently enabled-by-absence that the seed migrations bound), then drops the
  disable-only semantics. `deployment_capability_toggles` is either repurposed (rename + polarity
  flip) or replaced-and-dropped — implementer's call in STORE-1, ADR records it. *(Open Q2 from
  ONBOARD-0 is hereby answered "no fourth layer" unless the maintainer overrules in this draft.)*
- **D3 — Resolve chokepoint switches predicate.** `build_area_inventory`
  (`api/app/agents/capabilities.py:402-509`) intersects with Library membership instead of
  not-disabled. Same REQUIRED-kwarg fail-closed posture, same single chokepoint.
- **D4 — Bind-time validation gains a Library check** (closes G4a): attaching a non-adopted
  capability to an area 422s with a message pointing at the Store. Existing bindings that lose
  Library membership degrade exactly as today (resolve-time narrowing) but the Library page's
  where-used makes it visible; removal-while-in-use is confirmed, not silent (D6).
- **D5 — Provenance is surfaced, and the parser gap is fixed** (closes G4b): `SkillSource`
  (built-in/community/user/team) + author + version appear on every Store/Library card and
  binding chip; the loader falls back to top-level `author:`/`version:` frontmatter when the
  `lq_ai:` block lacks them.
- **D6 — Removing a Library entry that is bound in N areas** requires an explicit confirm listing
  the areas (no silent agent-behaviour change; matches "system proposes, user owns").
- **D7 — Namespacing reserved for shadowing.** No org-authored skills in this milestone (§7 no-v1
  stands — they are prompt-content, an injection surface needing the Practice-Knowledge harness
  + own ADR). But slugs/provenance are structured so a future org-authored `nda-review` can
  shadow the catalog's without collision (e.g. resolution order already exists: user > team >
  built-in; the ADR records `org` as a planned tier in that chain).
- **D8 — Naming.** Recommendation: user-facing **"Store"** (maintainer's word; honest today as
  "what ships with your deployment", true tomorrow when remote). Alternative: "Catalog" until a
  remote store exists. **Maintainer decides in this draft.**

## Non-goals (explicit)

- No remote store, downloads, version updates, or lq-skills sync — the Store browses what shipped.
- No org-authored/tenant-authored skills (D7 reserves the namespace only).
- No MCPs (own approval-gated milestone), no template catalog (follows this milestone), no changes
  to the operator fence (models/keys stay operator turf — G8 is separate work).
- No change to `guarded_tool_call`, grants-in-code, the gateway, or any agent runtime behaviour
  beyond the D3 predicate swap.

## Slices (vertical, one PR each, full ADR-F005 gate)

- **STORE-0 — ADR-F065 + this plan accepted.** Maintainer edits/accepts; ADR drafted with the
  D1–D8 outcomes; `MILESTONES.md` reordered (STORE before ONBOARD-1/2). Doc-only PR. *(Can carry
  the two independent quick fixes if convenient: G4b provenance parser fallback + G5 skill-name
  links — both tiny, both testable, zero model changes.)*
- **STORE-1 — Library substrate.** Migration (new table + seed-from-effective-state + toggle
  supersession), adopt/remove admin endpoints (authz: `AdminUser` — the operator PASSES it: F061
  D3 / F064 D2 keep platform-config surfaces like capabilities operator-accessible; F064's
  operator exclusion covers cross-user tenant DATA only), bind-time D4 check,
  `build_area_inventory` D3 predicate swap, drift
  guard: a test that walks every kind and pins catalog-vs-library-vs-binding behaviour (adopted+
  bound=resolves; not-adopted+bound=narrowed; not-adopted+not-bound=absent). Web untouched;
  `GET /api/v1/admin/capabilities` grows `in_library` so the old page keeps working during the
  transition.
- **STORE-2 — Store + Library pages.** The two admin pages above, provenance badges, where-used,
  D6 confirm; old Capabilities page replaced (route redirect); area-detail pickers become
  Library-scoped with the Store empty-state link. Read-only Library view for non-admins.
- **STORE-3 — live dress rehearsal.** Maintainer re-walks the admin journey on a fresh org:
  Store → adopt → bind → member run. Observed gaps appended to `ONBOARD-admin-experience.md`;
  leftovers recorded; milestone closed.

## Verification

Per slice: containerized suites with counts; the STORE-1 drift-guard test; fresh-context
adversarial review with the mandatory security pass (new admin mutation endpoints: authz, 404-not-
403 cross-org posture, audit rows counts/types/IDs only, no injection via kind/key params —
they're validated against the registries exactly like today's PATCH); live UI evidence for
STORE-2; the STORE-3 rehearsal is the milestone's acceptance test.

## Maintainer decisions (2026-07-05 review — all four questions answered)

1. **D8 naming: "Store." DECIDED.**
2. **D2 confirmed: no operator content kill-switch.** The maintainer's reaction — "why would an
   operator need a kill switch?" — is the answer. The old deployment toggles were built when we
   framed availability as deployment configuration; once the Library exists they'd be a second
   off-switch with opposite polarity ("operator disabled" vs "org never adopted"), the opposite of
   clean. Single off-state: *not in your Library*. A genuinely broken capability is fixed by
   shipping an update (it leaves the Store), not by a per-deployment switch. The operator fence
   keeps what it always kept: models, providers, keys — infrastructure, not content.
3. **Fresh orgs start with an EMPTY Library — DECIDED — under the binding non-technical-admin UX
   constraint above** (recommended-rail + one-click add-all makes "empty" a 30-second problem,
   not a cliff). Templates later adopt-on-apply.
4. **Upgrade posture: seed-from-effective-state — explained and locked** (maintainer queried the
   wording, not the substance). "Migration" = the automatic DB upgrade that runs when an EXISTING
   deployment (today's local stack; later the IONOS box; any self-hosted firm) updates to the
   version carrying this feature. If the new Library table started empty for them, every practice
   area's skills/tools would silently stop resolving on upgrade day until an admin re-adopted
   everything by hand. Instead the upgrade pre-fills the Library with exactly what the org was
   already using (bound-anywhere minus explicitly-disabled), so upgrade day changes nothing.
   "Empty Library" (decision 3) applies to brand-new orgs only.
