# PLAN — Admin Skill Fast-Path ("Publish to org")

*Slice plan. Scoped via design + three adversarial critiques (security-governance, simplicity,
correctness-atomicity), every critic point folded in below (accepted or rejected with a reason).
Governing ADR: `docs/adr/F067-module-model.md` (authoring boundary D2/D3). Related: the parallel
B-7b setup wizard (G13/#473) attacks the same "capabilities don't reach agents" pain at the
fresh-org pre-population level; this is the smaller targeted fix. Playbook twin (B-4) deferred.*

---

## Goal

Collapse the admin's four-page org-authoring journey (propose on the skills list → approve in the
review queue → adopt on the Library page → bind on the Areas page) into a single atomic **"Publish
to org"** action on the skill editor. An admin who authored a personal skill can, in one click, mint
the frozen approved `org_skill_versions` snapshot and adopt it into the org Library — then follow a
deliberate "Bind to an area →" link. The fast-path introduces **zero new authority**: self-approval
is already explicitly permitted (`admin.py:2162`, ADR-F067 D2), so this collapses clicks, never
checks. Every propose/approve validation gate, the frozen immutable snapshot, the content hash, the
operator fence, and the content-free audit trail are preserved.

## Non-goals

- **No new authority / no SoD change.** Not adding, weakening, or gating self-approval; not adding a
  two-person rule (see Design decision on where SoD would live if ever wanted).
- **No auto-bind.** Publish stops at Library membership; attaching a capability onto a specific area
  Deep Agent stays a separate, deliberate `practice_area.skill_attach` (choosing *which* agent gets
  it is the real decision).
- **No playbook twin this slice** (backlog `PUBLISH-PB`).
- **No review-queue nav badge, no list-page Publish button** (cut as scope creep — see UI changes).
- **No migration, no new audit action vocabulary, no runtime/serving change.**

> **Maintainer decisions (2026-07-10):** (1) Publish stops at Library membership + a deliberate
> **"Bind to an area →"** link — no inline area picker, no auto-bind. (2) The operator-fence fold-in
> was **reconsidered and DROPPED from this slice** after scoping found ADR-F064 *deliberately keeps*
> the operator on the areas/capabilities/Library surface ("platform config, the fence's own scope",
> F064 D2:85-88). Fencing the existing adopt/bind endpoints would *reverse* an accepted ADR, not
> close a gap, and a coherent narrowing would also have to cover area create/delete/config. That is
> its own deliberate **F064-superseding** decision → backlog `OPERATOR-NARROW-AGENT-CONFIG`. The new
> `/publish` endpoint IS operator-fenced regardless — it performs an approve (tenant-authored
> content), which F064 already fences. *(Proceeding on option A pending the maintainer's return; the
> full-narrowing option B remains open as a separate slice.)*

## Design decision — atomic `POST /api/v1/user-skills/{skill_id}/publish`

**Chosen: a single server endpoint that composes existing service logic in one transaction.** All
three critics converge here. It is a *thin handler composing extracted helpers*, not new route
logic: `_load_owned_user_skill` → gate battery → insert `proposed` row → `promote_to_approved` →
idempotent adopt.

**Rejected — client orchestrates 3 calls.** Two code-grounded reasons dominate: (1) the standalone
`adopt` **409s** on an existing `(kind,key)` Library row (`admin.py:1837-1842`), yet re-publishing a
new version of an already-adopted slug is legitimate and must be a no-op; (2) the operator fence
lives on approve but **not** on adopt, so three round-trips smear the authz decision.

**Final authz gate:** `AdminUser` dependency **+ inner `if not tenant_admin_visibility(admin):
raise Forbidden`** — publish *performs an approve*, which is operator-excluded under ADR-F064;
shipping it as raw `AdminUser` (the looser gate `adopt` uses) would hand the operator a
tenant-content-approval path it is fenced from. **Owner-scoped:** `_load_owned_user_skill(db,
skill_id, user_id=admin.id)` → 404 on non-owned / archived / team-scope. This is the D2 keystone: an
admin can publish **only a skill they themselves authored**; another user's content still travels
propose → *separate*-admin-approve → Library → bind.

**Transaction boundary — one txn, exactly one `commit()` at the end:**
1. `content = freeze_and_validate_org_skill(row)` — extracted gate battery. Pure validation; no
   flush/commit.
2. One-open-proposal check (`state='proposed'` on slug) → 409.
3. Insert `OrgSkillVersion(state='proposed', author_user_id=admin.id, version_no=MAX+1)`; `flush`
   (race `IntegrityError` → 409). **First mutation** (terminal race-rollback). → audit `library.propose`.
4. `promote_to_approved(db, version, reviewer_id=admin.id)` — extracted from
   `approve_org_skill_version`: lock prior `approved` `FOR UPDATE` → `superseded` → flush → flip this
   row `approved`, `reviewed_by`/`reviewed_at` → flush. **INVARIANT: ends at `flush()`, never
   `commit()`** (a mid-txn commit would strand an approve before adopt). Standalone `approve` keeps
   its own `commit()`. → audit `library.approve` (+ content-free `fast_path: true`).
5. Idempotent adopt — **do NOT call the `adopt` endpoint body** (its `except IntegrityError:
   rollback()` would nuke the whole txn). Use
   `postgresql.insert(OrgLibraryEntry).on_conflict_do_nothing(index_elements=["capability_kind","capability_key"]).returning(...)`;
   audit `library.adopt` only if a row was returned. Skip `_validate_catalog_key` — the just-flushed
   approved snapshot satisfies the invariant in-session.
6. `commit()`.

Insert-`proposed`-then-`promote` (not a direct `approved` insert) is retained: it reproduces the
slow path's state history, reuses the one-open-proposal coupling and the `state=='proposed'`
transition guard.

**Audit rows:** the three existing content-free actions — `library.propose` + `library.approve` +
`library.adopt` (all `user_id=admin.id`; kind/key/version/hash/size only), **not** a new
`library.publish`. On idempotent re-publish the adopt is a no-op → **two** rows. A content-free
boolean `fast_path: true` on the `library.approve` `details` lets an auditor answer "which approvals
were one-click" (a boolean, not content — audit contract intact).

**Idempotency / conflict behavior:**

| Case | Behavior |
|---|---|
| Open `proposed` row for the slug (any author) | **409** — admin reviews the in-flight proposal, not race it (slug-keyed, cross-author, consistent with propose) |
| Concurrent insert race | 409 (terminal) |
| Prior `approved` snapshot of same slug | Not an error — supersede it |
| Already in Library | Not an error — `ON CONFLICT DO NOTHING` no-op adopt |
| Approved-but-unadopted strand | Publish heals it — supersede + fresh adopt |
| Re-publish, `content_hash` UNCHANGED, already in Library | **200 OK no-op** — early guard: mint no new snapshot, write no audit rows (genuine idempotency, kills double-click churn). Happy path `201 Created`; no-op `200 OK`. |

**Return:** `201` (or `200` no-op), `OrgSkillVersionAdminRead` (`state=approved`, `reviewed_by`/
`reviewed_at` set, `author_email==approver_email==admin`, `slug` present for the Bind link).

## UI changes

Operator-fence mirror on every surface: **`is_admin === true && role !== 'operator'`** (precedent
`admin/+layout.svelte:26`).

- **Editor `skills/[id]/edit/+page.svelte`** (today only *displays* proposal history):
  - **"Publish to org"** (primary) — gate `is_admin && role!=='operator'`. Calls
    `publishUserSkill(row.id)`; on 201 show success banner + Bind link; map 409/422 via
    `describeMutationError`.
  - **"Propose to Library"** — gate `owner && role!=='operator'` (non-admin owners only). Reuses
    existing `proposeUserSkill`. **Mutually exclusive** with Publish. Closes the discoverability gap
    (Propose lived only on the list) for ~5 lines.
  - **"Bind to an area →"** deep-link — post-publish success state only; links to `/lq-ai/admin/areas`.
- **New api method** `publishUserSkill(id)` in `web/src/lib/lq-ai/api/userSkills.ts`.

**CUT (scope):** review-queue nav badge (→ `PUBLISH-BADGE`); per-row Publish on the skills list.

## ADR-F067 addendum bullets

1. **Admin self-approve is legitimate and adds no authority.** Already permitted on the standalone
   approve path (`admin.py:2162`, D2). Single-admin orgs have no other approver. Collapses clicks,
   not checks.
2. **Same frozen snapshot, same audit actions.** Identical write-once `org_skill_versions` row,
   `content_hash`, `org_library_entries` row, and the same three content-free audit **actions** —
   three on first publish, **two on idempotent re-publish**. `library.approve` carries a content-free
   `fast_path: true`. Runtime serve path byte-identical.
3. **Non-admin authors unchanged; owner-gated.** `is_admin`-gated **and**
   `_load_owned_user_skill(user_id=admin.id)`-gated — an admin publishes only their **own** skill.
   D2 sole-path invariant intact.
4. **Every write-time gate runs.** D3.3 closed frontmatter allowlist (422, write-time-only — no
   serve-time backstop), well-formedness (422), 32 KiB (422), D2 no-shadow fail-closed (409),
   one-open-proposal (409).
5. **`/publish` is operator-fenced, consistent with F064.** Publish gates on
   `tenant_admin_visibility` because it performs an **approve** — tenant-authored content review,
   which F064 already fences (admin.py:2165). This slice does **not** touch the existing standalone
   `adopt`/`bind` endpoints: ADR-F064 D2:85-88 deliberately keeps the operator on the
   areas/capabilities/Library surface ("platform config, the fence's own scope"). Narrowing the
   operator off those surfaces would *supersede* F064 (and, to be coherent, would also have to fence
   area create/delete/config) — a separate deliberate decision, tracked as `OPERATOR-NARROW-AGENT-CONFIG`.
6. **Segregation-of-duties is unsupported by design.** A publish-only "require 2nd approver" flag
   would be security theater (slow-path self-approve stays open). Any future two-person rule MUST
   live at the shared `promote_to_approved` chokepoint honored by **both** approve and publish.
7. **Bind stays deliberate; the human-deliberation checkpoint relocates** from approve → bind.

## Migration

**NONE.** Reuses `org_skill_versions` (mig 0091), `org_library_entries` (mig 0088), `audit_log`.

## Files touched

**API**
- `api/app/api/user_skills.py` — new `POST /{skill_id}/publish` handler (~+70–80 LOC) incl. the
  content-hash no-op guard.
- `api/app/skills/org_proposal.py` — extract **`freeze_and_validate_org_skill(row) ->
  OrgSkillContent`** (synthesize + full gate battery). **Injection-critical:** the D3.3 allowlist is
  the sole line of defense; runs exactly once here.
- `api/app/api/admin.py` — extract **`promote_to_approved(db, version, *, reviewer_id)`** (ends at
  `flush()`); refactor `approve_org_skill_version` to call it (keeps its own `commit()`). *(No
  operator-fence change to `adopt`/`remove` — see ADR bullet 5 / Non-goals.)*

**WEB**
- `web/src/lib/lq-ai/api/userSkills.ts` — `publishUserSkill(id)`.
- `web/src/routes/lq-ai/(app)/skills/[id]/edit/+page.svelte` — Publish (admin) / Propose (non-admin
  owner), mutually exclusive; post-publish "Bind to an area →" link.

**TESTS**
- `api/tests/api/test_user_skills*.py`: happy path (201, `state=approved`, `reviewed_by=admin`,
  Library row, 3 audit rows by count/type, `fast_path:true`); **operator → 403**; non-admin → 403;
  non-owner/team-scope/archived → 404; open-proposal → 409; re-publish supersedes (2 audit rows, no
  adopt); **unchanged re-publish → 200 no-op**; already-in-library idempotent; flush-before-adopt
  ordering; content-free audit assertion. **Injection battery: 422 on EACH denied frontmatter key by
  name + fail-closed when registry absent.**
- Web vitest: Publish visible only for `is_admin && !operator`; Propose visible for non-admin owner;
  mutual exclusivity; post-publish Bind link.

**DOCS**
- `docs/adr/F067-module-model.md` — the addendum bullets. *(No F064 change — this slice leaves the
  operator's areas/capabilities surface exactly as F064 decided.)*
- `docs/fork/HANDOFF.md`, MEMORY topic update.
- `docs/fork/MILESTONES.md §Backlog` — `PUBLISH-PB` (playbook twin), `PUBLISH-BADGE` (nav badge),
  `OPERATOR-NARROW-AGENT-CONFIG` (deliberate F064 supersession: fence the operator off Library
  adopt/remove + all capability attach/detach + area create/delete/config — the full coherent set).

## Verification / DoD

**CI-parity:** API `cd api && ruff format && ruff check && pytest` (name the new module + counts);
Web `cd web && npm run check && npm run test:frontend`.

**Live UAT (behavior changes):** admin authors a personal skill → editor → **Publish to org** →
201 → verify `org_skill_versions` `state='approved', reviewed_by=admin`, `org_library_entries` row,
3 content-free audit rows (+`fast_path:true`) → **Bind to an area →** → bind → run that area's agent
→ confirm it lists/uses + cites the skill. Screenshot Publish-success + the agent citing. Re-publish
idempotency (edit → new version + supersede + 2 audit rows; unchanged → 200 no-op). Negatives:
non-admin owner sees only Propose; operator sees no Publish and `/publish` → 403.

## Risks / gotchas

- **BLOCKER — helpers must not commit mid-txn.** `promote_to_approved` + `freeze_and_validate_org_skill`
  end at `flush()`; publish commits once; standalone approve keeps its own commit.
- **BLOCKER — never reuse the `adopt` endpoint body** (its `IntegrityError→rollback()` nukes the
  publish txn). Use `on_conflict_do_nothing(...).returning(...)`; audit off RETURNING.
- **HIGH — operator fence must be the INNER `tenant_admin_visibility` check**, not raw `AdminUser`;
  explicit operator→403 test.
- **Injection-critical extraction:** any drift/reorder in the gate battery, or loosening the
  fail-closed registry check, lets malicious frontmatter reach the agent with **no serve-time
  backstop**. Per-denied-key + fail-closed tests mandatory.
- One-open-proposal 409 is **slug-keyed across all authors** — document, don't "fix."

## Scope call

**Skills-only this slice.** Playbook twin deferred (`PUBLISH-PB`): it doubles the API+web+test
surface for zero additional proof of the pattern. Skills are the instruction-class (highest
injection risk) and the more common org-authoring case. Prove the fast-path here, let
`promote_to_approved` + the gate helper bake kind-agnostic, then the twin reuses them. Knowledge
collections need no twin (no propose/approve harness).

## Recommended implementation order

1. Extract `promote_to_approved` from `approve_org_skill_version`; refactor approve to call it. Run
   api tests green — proves net-zero behavior change first.
2. Extract `freeze_and_validate_org_skill` from `propose_user_skill`; refactor propose to call it.
   Run propose 422/409 tests green — the security surface verified before publish reuses it.
3. Add `POST /{skill_id}/publish` composing both helpers + `on_conflict_do_nothing` adopt +
   content-hash no-op guard + three audit rows (+`fast_path`).
4. API tests — full matrix incl. injection battery, operator→403, ordering, idempotency, no-op.
5. Web — `publishUserSkill` + editor Publish/Propose (mutually exclusive) + post-publish Bind link.
6. Web vitest.
7. Docs — ADR-F067 addendum, HANDOFF, MEMORY, three backlog entries.
8. CI-parity + live UAT, evidence in PR.
