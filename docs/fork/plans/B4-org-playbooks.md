# B-4 — org-authored playbooks through the harness (plan)

**Status:** scoped 2026-07-09 (workflow-mapped against live code + 2 adversarial critiques) — **maintainer
edits this doc before implementation.** Governing ADR: `docs/adr/F067-module-model.md` (D1/D2/D3/D5).
Milestone: `docs/fork/plans/MODULES-milestone.md` § B-4. Precedent slice: **B-2a** (org-skill harness,
mig 0091) — B-4 mirrors it for `kind=playbook`.

**Maintainer decision (2026-07-09):** **Full skills parity** for the governance model (Q below). Org
playbooks resolve from the approved-snapshot map keyed by the adopted+bound `(kind=playbook, key)` set,
**independent of the live `playbooks` row**; the catalog lists only built-in (`created_by IS NULL`) +
approved-org playbooks; an author soft-deleting their source row is harmless (the snapshot survives; only
an **admin revoke** removes an approved capability). This matches how skills resolve `bound_skill_names`
and eliminates the live-join asymmetries the critics flagged.

## One-line thesis

B-4 is **the same propose→approve→snapshot→compose state machine as B-2a, with a different content
payload (frozen positions, not SKILL.md) and a different injection site (the Practice Playbook tier, not a
SkillsMiddleware backend).** It is a lower-risk kind on **exactly one axis** — playbooks are pure
structured GUIDANCE-DATA behind the **already-existing** `PRACTICE_PLAYBOOK_PROMPT` fence
(`composition.py:380`), so the D3.3 frontmatter-allowlist layer (incl. the `allowed-tools` denial) has **no
analogue and is dropped**. Every *other* D3 control applies in full: mandatory human approve gate,
immutable content-hash-pinned snapshot, size cap, provenance-at-point-of-use, revoke fail-close, body-free
audit.

## What already exists (no work)

`playbook` has been a first-class Library kind since **mig 0088**:

- `org_library_entries` kind CHECK already allows `playbook` — **no CHECK migration**.
- **adopt** (`adopt_library_entry` / `_validate_catalog_key` KIND_PLAYBOOK), **bind**
  (`attach_practice_area_playbook` + `_require_in_library`), **per-matter toggle**
  (`matter_capability_toggles`), **remove** — all accept `playbook`, untouched.
- Web **provenance badge / grouping / where-used / remove-confirm** (`web/src/lib/lq-ai/library/page-helpers.ts`)
  are kind-generic — the `source='org'` badge renders automatically once the backend emits it.
- Review-queue **chrome** (state-filter pills, monotonic-request-id load guard, ADR-F064 operator-403
  hide, content-hash receipt, Approve / Reject-with-note / Revoke modal trio) is kind-generic.
- `DeploymentCapabilityRead` + `LibraryEntry` already carry optional `source/author/version/approver` for
  `kind=playbook` — **no wire-schema change**.

## Goals

1. An easy-builder playbook can be **proposed → admin-approved → adopted → bound**, and its **frozen**
   positions inject as the read-only Practice Playbook tier with `source='org'` + author/approver
   provenance — closing today's TOCTOU where a bound playbook's **live, editable** positions inject
   directly and a post-adopt edit is instantly visible to the agent.
2. **Full skills parity:** the approved snapshot (never the live row) is what composes; post-approval
   edits are invisible until re-approval; revoke fail-closes at the next `build_area_inventory`; the
   capability is removable only by an admin revoke.

## Non-goals

- No change to the **frozen legacy executor** (`api/app/playbooks/executor.py`, `app/autonomous/`,
  `PlaybookExecution`/`EasyPlaybookGeneration`) — only the `render_practice_playbook` / tier / harness path.
- **No frontmatter allowlist / SkillFrontmatter validation** — playbooks are pre-validated closed Pydantic
  shapes (`extra='forbid'`) behind the existing fence; the D3.3 layer collapses to nothing.
- **No SkillsMiddleware backend** — playbooks render into tier TEXT, never through a middleware backend.
- **No `org_library_entries` kind CHECK migration** (`playbook` allowed since 0088); adopt/bind/toggle/
  remove untouched.
- **No true two-version positions diff** in v1 — the review UI renders the pinned snapshot read-only
  (live-vs-snapshot diff → backlog).
- **No upgrade-day auto-backfill** — a pre-existing adopted+bound org playbook with no snapshot
  fail-closes until proposed+approved (no shipped playbook is bound by default; fresh orgs unaffected;
  documented in the ADR + HANDOFF).
- **No new `RECOMMENDED_LIBRARY_SETS` playbook entry** (would trip `test_recommended_library_sets_no_playbooks`).
- **No new gateway/LLM egress** — the propose/approve/render path makes zero model calls.

## Migration

**`api/alembic/versions/0095_org_playbook_versions.py`** — `down_revision='0094'` (confirm 0094 is head
at implement time; next number is 0095). Clone `0091_org_skill_versions.py` verbatim, swapping the
skill content columns for a frozen playbook snapshot and re-keying `slug(TEXT)` → `playbook_id(UUID)`.

Columns: `id` UUID PK; **`playbook_id` UUID NOT NULL — plain column, NOT an FK** (the stable adoption
key; survives live-row delete exactly as org_skill's slug does, so the Library key `str(pb.id)` stays
resolvable); `version_no` INT (CHECK ≥1, per-`playbook_id` monotonic); frozen header `name`/`contract_type`/
`description`/`playbook_version` (TEXT — the capability label); **`positions` JSONB NOT NULL** (canonical
full-fidelity frozen positions); `content_hash` TEXT (sha256 over canonical positions+header JSON);
`source_playbook_id` UUID FK→playbooks.id **ON DELETE SET NULL** (provenance only; snapshot bytes survive);
`author_user_id`/`reviewed_by`/`revoked_by` UUID FK→users.id SET NULL; `state` TEXT DEFAULT `'proposed'`;
`proposed_at`/`reviewed_at`/`revoked_at` TIMESTAMPTZ; `review_note` TEXT. CHECKs: `state IN
('proposed','approved','rejected','superseded','revoked')`; `version_no≥1`. Four indexes (re-keyed to
`playbook_id`): `uq(playbook_id, version_no)`; partial-unique `WHERE state='proposed'` (one open proposal
per playbook); partial-unique `WHERE state='approved'` (the runtime's single source of truth);
`idx(state)`.

**Discipline:** verify up/down/up on a **throwaway pgvector** (NEVER the live dev DB); after it lands
rebuild **api + arq-worker + ingest-worker** together; `docker image prune -f` (dangling only).

## Backend changes

- **`api/app/models/org_playbook_version.py`** (NEW) — `OrgPlaybookVersion`, mirror `OrgSkillVersion`.
  Immutability doctrine in the docstring ("approval pins bytes, not a row"): content columns written once
  at INSERT; only state/review/revoke transition. Runtime reads **only** `state='approved'`.
- **`api/app/agents/playbook_proposal.py`** (NEW pure core — under `app/agents/`, **not** `app/playbooks/`
  which is the frozen legacy dir):
  - `canonicalize_positions(playbook)` → deterministic JSON. **Tiebreaker `(position_order, issue, id)`**
    because `position_order` is non-unique and defaults 0 (critic fix); `fallback_tiers` ordered by
    `rank`; fixed key order; `json.dumps(sort_keys, separators=(',',':'), ensure_ascii=False)`. **Total
    over malformed `fallback_tiers`** (skip non-dict, mirroring `_summarise_fallbacks`) — must not raise or
    hash unstably.
  - `freeze_playbook_snapshot(playbook)` → frozen payload + header + `content_hash` + `size_bytes` +
    `position_count` (a deep-copy freeze; no YAML).
  - `ORG_PLAYBOOK_MAX_BYTES = 32*1024`.
  - `load_approved_org_playbook_versions(db)` → `dict[str, OrgPlaybookVersion]` keyed by `playbook_id::text`
    — the ONE approved reader (single source so "what is a live org playbook" can't drift across the 4 call
    sites). Reuse `render_provenance_banner` **imported verbatim** from `app.skills.org_proposal`.
- **Shared transition helper (simplification — critic):** parametrize **one**
  `_org_module_version_for_transition(model, key_column)` + one approve helper, used by **both** the shipped
  skill routes and the new playbook routes, instead of cloning ~150 lines of security-sensitive
  FOR-UPDATE + two-step-supersede-then-flush logic into a second path that can drift. If the refactor of
  the shipped skill path is deemed too invasive for this slice, fall back to a faithful clone **and record
  the divergence** — but prefer the shared helper.
- **`api/app/api/playbooks.py`** (author side):
  - `_load_owned_playbook(db, id, user_id)` — STRICT owner (`id==playbook_id AND created_by==user_id AND
    deleted_at IS NULL`), **404 not 403**; auto-404s built-ins (`created_by IS NULL`) and cross-user rows.
    Do **not** reuse the admin-OR-owner edit gate.
  - `POST /playbooks/{id}/propose` — load owned → `freeze_playbook_snapshot` → size cap 422 → one-open-
    proposal 409 (+ IntegrityError→409 race guard) → `version_no=COALESCE(MAX,0)+1` → insert immutable
    `proposed` → audit `library.propose` `resource_type='org_playbook_version'` details `{kind,key,version,
    content_hash,size_bytes,position_count}` (**never** positions text).
  - `GET /playbooks/{id}/proposals` — owner-scoped version history.
- **`api/app/api/admin.py`** (admin side): `GET /admin/org-playbooks` (list, optional state filter,
  `tenant_admin_visibility` operator-403, batched author/approver email outerjoin) + `POST
  /admin/org-playbooks/{id}/approve|reject|revoke` via the shared transition helper. **Preserve exactly:**
  the two-step supersede-then-flush (the one-approved-per-key partial index trips mid-flush otherwise);
  reject `note→review_note` (audit `has_note` only); **revoke flips `state→'revoked'` and LEAVES** the
  `org_library_entries` + `practice_area_playbooks` rows (D3.8 fail-close at build). All `AdminUser` +
  operator-excluded; audit reuses `library.approve/reject/revoke`, `kind='playbook'`, body-free.
- **Read models — BOTH (critic: member read was omitted):**
  - `admin.py _deployment_inventory` playbook_entries — join `_approved_org_playbook_snapshots` (batched
    author+approver emails) → `source='org'`/author/version/approver when an approved snapshot exists.
  - `api/app/api/library.py` member `GET /api/v1/library` playbook branch — the parallel snapshot join
    (this is a **different function** than `_deployment_inventory` — needs its own wiring or the member
    card shows no badge).
  - **Catalog gating (full parity):** `_validate_catalog_key` + `_deployment_inventory` + the member read
    list only **built-in (`created_by IS NULL`) + approved-org** playbooks. A `created_by`-NOT-NULL
    playbook with no approved snapshot does **not** appear as adoptable (no badge-less built-in-looking
    entry).
- **`api/app/agents/capabilities.py`** — `build_area_inventory`: add optional `org_playbook_snapshots`
  kwarg (default `None===({})`, fail-closed). **Full-parity resolution:** enumerate the area's **bound**
  `(kind=playbook, key)` set from `practice_area_playbooks` **independent of live rows**; for each bound
  key, resolve the **approved snapshot** if present (org), else a **live built-in** row (`created_by IS
  NULL`, source=None), else **fail-closed drop** with a structured `org_playbook_unresolved_skipped`
  warning (counts/keys only — the D3.8 revoke/never-approved fail-close). One loop, one intersection, no
  second path.
- **`api/app/schemas/`** — `OrgPlaybookProposalResponse` (author status view); `OrgPlaybookVersionAdminRead`
  (the **review** surface — includes the full frozen positions JSON + hash + size + author/approver emails;
  the one deliberate content-exposing read, `AdminUser`+operator-excluded, **not** audited — mirrors
  `OrgSkillVersionAdminRead.raw_yaml/body`); `OrgPlaybookRejectRequest(note, length-capped)`. Prefer a
  shared base for the common state/review/provenance fields.

## Composition wiring (the riskiest, net-new surface)

Both callers of the pure `build_area_inventory` must load + pass the snapshot map or the panel and the
agent disagree.

1. **`composition.py`** — beside the existing org-skill snapshot load (~L774) add
   `org_playbook_snapshots = await load_approved_org_playbook_versions(db)`; pass it into
   `build_area_inventory`. At the render seam (L793–799), for each enabled key: a built-in resolves to the
   **live** `Playbook` (with `selectinload`'d positions) unchanged; an org key rehydrates a lightweight
   `_FrozenPlaybook`/`_FrozenPosition` from the snapshot's frozen positions (exposing `name`,
   `contract_type`, `positions[].{issue,standard_language,fallback_tiers,severity_if_missing}`, plus a
   `provenance_banner`). Feed the **mixed** list to the **same** `render_practice_playbook` — one renderer,
   no parallel path. **Defensive skip** (critic): an enabled org key whose snapshot is unexpectedly absent
   degrades to omission, never `KeyError`.
2. **`playbook_context.py:render_practice_playbook`** — widen the input to a structural Protocol (it already
   reads only `name/contract_type/positions` structurally); under the `### {header}` line emit a
   `> {provenance_banner}` line when present (built-in live rows have no such attr → byte-identical). The
   block still lands inside the `PRACTICE_PLAYBOOK_PROMPT` fence + the 6000-char cap.
   **Fence-delimiter hardening (critic should-fix):** at the freeze or render seam, strip/neutralize any
   rendered position line matching the tier BEGIN/END markers (collapse leading `-----` runs) — B-4 is the
   first slice routing *any authenticated user's* text through this fence. **Add a hostile-content test**
   (delimiter-injection + "ignore instructions").
3. **`api/app/api/matter_capabilities.py`** — the SECOND consumer (cockpit panel): the identical
   `load_approved_org_playbook_versions` load + pass `org_playbook_snapshots`. A test asserts the panel
   drops a revoked org playbook.

## Web changes

- **`web/src/lib/lq-ai/api/playbooks.ts`** — `proposePlaybook(id)` / `listPlaybookProposals(id)` (mirror
  `userSkills.ts`).
- **`.../(app)/playbooks/+page.svelte`** — "Propose to Library" ROW action beside "Apply"; open-proposal-409
  lock + transient success banner (`setTimeout` cleared in `onDestroy` — no toast primitive); inline
  proposal-STATUS chip (playbooks have no `[id]/edit` route to host history — surface status inline).
- **`.../(app)/playbooks/page-helpers.ts`** (+ `__tests__`) — `canProposePlaybook` gates on
  **`created_by === currentUserId`** (critic: admins see *all* playbooks; `!== null` alone shows the button
  on others' rows → 404); `proposePlaybookSuccessMessage`; reuse `isOpenProposalConflict`.
- **`web/src/lib/lq-ai/api/admin.ts`** — `listOrgPlaybookVersions/approve/reject/revoke` against
  `/admin/org-playbooks` + `OrgPlaybookVersionAdminRead` carrying frozen **positions** (replaces
  `raw_yaml/body`).
- **`.../(app)/admin/library/+page.svelte`** — a playbook review-queue section on the **same** page. Reuse
  the generic chrome verbatim; **replace only the per-row CONTENT renderer**: render the frozen positions
  read-only via `PlaybookEditorPosition.svelte` in a non-editable mode (not a `raw_yaml` `<pre>`). Free-text
  position fields go through the existing sanitizer (untrusted author input).
- **`web/src/lib/lq-ai/library/page-helpers.ts`** — **zero code change**; add one vitest case for a
  `source='org'` playbook entry.
- **`web/cypress/e2e/b4-org-playbooks.cy.ts`** (NEW) — b5 intercept style (live login + `cy.intercept` +
  assert request body + `cy.screenshot`). Mind Store(`kind:key`) vs Library(`kind-key`) testid grammar.
  **Rebuild the prebuilt web container** before browser verification.

## Drift guards (🔴 critic BLOCKER — 6 new routes trip 4 pinned tests)

- `api/tests/test_mutation_rbac.py`: mutating **137→141** (propose=MutatingUser; approve/reject/revoke=
  AdminUser), path count **186→192**, MutatingUser-gated **70→71** (propose only).
- `api/tests/test_endpoints.py`: `IMPLEMENTED_ROUTES` **+6 tuples** (`version_id`/`playbook_id` params
  already in `_PARAM_VALUES`).
- `api/tests/test_openapi.py`: `EXPECTED_PATHS` **+6 paths**, len **186→192**.
- `api/tests/test_operator_fence.py`: **NO change** — admin routes use `AdminUser` + in-handler
  `tenant_admin_visibility` (like org-skills), not the operator-only fence. Confirm counts at implement time.

## Tests (deterministic + hermetic — no gateway key)

- `api/tests/test_org_playbook_harness_api.py` — propose happy path (frozen positions + hash persisted;
  audit **body-free**); size cap 422; one-open-proposal 409; authz (other-user 404, built-in 404);
  hash determinism (semantically-equal-but-**reordered** positions/fallback_tiers/keys → one hash; malformed
  tier → deterministic non-raising). Admin: approve pins; re-approve supersedes (no mid-flush double-approved);
  reject `review_note` + `has_note` audit; revoke leaves Library + binding rows; operator-403; unknown id 404.
- `api/tests/agents/test_org_playbook_composition.py` — **approved-snapshot-not-live-row**;
  **post-approval-edit-invisible**; **revoke-fail-closes-next-run**; **built-in-unchanged** (byte-identical
  regression); **no-snapshot-fail-closed**; **live-row-deleted-but-snapshot-still-bound resolves** (the
  full-parity guarantee); **provenance line** present for org, absent for built-in; **fence-delimiter
  hostile content** neutralized.
- migration round-trip on throwaway pgvector; assert kind CHECK **unchanged**.
- vitest (no mount): `canProposePlaybook` ownership gate; `proposePlaybookSuccessMessage`;
  `isOpenProposalConflict`; provenanceBadge org case. `npm run check` svelte-check 0.
- **LIVE ACCEPTANCE (maintainer browser + gateway):** build → propose → approve (review shows read-only
  positions + hash receipt) → adopt → bind → agent cites the company position from the snapshot; then edit
  the live playbook + re-run → agent **still** cites the old snapshot position until re-approval. Screenshots
  in the PR.

## ADR

**ADR-F067 B-4 addendum** (append, mirror the B-2a addendum) — record: proposal state on
`org_playbook_versions` keyed by `playbook_id`; **full skills parity** (snapshot-keyed resolution
independent of the live row; catalog = built-in + approved-org; author-delete harmless; only admin revoke
removes); runtime renders the **snapshot**, never the live row; content_hash over canonical positions JSON;
**no frontmatter allowlist** (GUIDANCE-DATA behind the existing fence) while every other D3 control holds;
provenance as an in-tier line + shown badges; revoke leaves the Library row; **why two ~90%-identical
version tables were not unified** (the shared transition helper is the DRY answer at the code layer);
upgrade-day fail-close (no backfill). Draft in the same PR; maintainer accepts.

## Recommended order

1. mig 0095 + `OrgPlaybookVersion` (throwaway-pgvector up/down/up).
2. pure core `playbook_proposal.py` + unit tests (canonicalization determinism + malformed tier).
3. shared transition helper refactor (or faithful clone + recorded divergence).
4. author side: `_load_owned_playbook` + propose/proposals + schemas + audit + API tests.
5. admin side: list/approve/reject/revoke + operator exclusion + API tests + **drift-guard bumps**.
6. chokepoint (full-parity resolution + fail-closed warning) + render-from-snapshot + provenance line +
   fence hardening; wire **both** `composition.py` and `matter_capabilities.py`; composition tests.
7. read-models: admin `_deployment_inventory` + member `library.py` + catalog gating.
8. web: propose action + client + helpers + vitest; review-queue positions renderer; badge vitest;
   svelte-check 0 / test:frontend green; rebuild web; Cypress + screenshots.
9. ADR-F067 B-4 addendum + HANDOFF + full ADR-F005 gate (CI green, containerized api+web counts quoted,
   fresh-context adversarial + security + simplification review, live acceptance evidence) → squash-merge
   (`--repo sarturko-maker/lq-ai-fork`).

## Risks / gotchas

- **Two-renderer drift** → keep ONE `render_practice_playbook` (Protocol-widened, rehydrated frozen object).
- **Second-consumer miss** → `matter_capabilities.py` must also pass the snapshot map (test the panel).
- **Approve two-step flush** → clone `admin.py:2135-2160` ordering exactly (or the shared helper) + a
  re-approve/supersede test.
- **Content-hash non-determinism** → the `(position_order, issue, id)` tiebreaker is load-bearing.
- **Fail-closed polarity** → default the kwarg to `None==={}` **and** require a snapshot for org keys; the
  composition test proves a live edit is invisible.
- **By-policy immutability** (no DB trigger) — parity with `org_skill_versions`; note in the ORM docstring;
  a stray UPDATE to an approved row's positions would go undetected (hash is a receipt, never re-checked at
  read). Accept parity; optional trigger is defense-in-depth.
- **B-1 discoverability** — a bound org playbook with no approved snapshot is green on the degraded-binding
  chip yet never injects; call it out in the ADR upgrade-day risk (optionally widen the chip later).
- **Module placement** — pure core under `app/agents/`, not `app/playbooks/` (frozen legacy).
- **Untrusted JSONB** — the canonicalizer and the web positions renderer stay defensive.

## Closed low-stakes decisions (maintainer may override)

- **Provenance-in-tier line:** YES — per-org-playbook `> Provenance: …` line (D3.5 provenance-at-point-of-use).
- **Upgrade backfill:** NONE — fail-close until re-approval; documented.
- **Positions diff:** read-only pinned render for v1; live-vs-snapshot diff → backlog.
- **Author status home:** inline chip on the list row; no new detail route.
- **Built-ins:** `created_by IS NULL` resolve LIVE, `source=None`, never proposable.
