# F021 — User permissions: areas of responsibility (authorization model + design-readiness contract)

- Status: proposed
- Date: 2026-06-18
- Deciders: maintainer (accepts); drafted from the `permissions-roadmap-design` multi-agent grounding +
  design workflow (map current authz surface → judge-panel of targets → claim verification, 28/32 code
  claims SUPPORTED).
- Relates to: ADR-F002 (matter→area binding), ADR-F004 (B-class runtime injection), ADR-F018 (agentic
  modules + code-validated writes), ADR-F019 (relational deployment-global ROPA register — this ADR
  **refines its §Authz read-posture clause**, see Consequences). Closes the design gap behind the PRIV-6a
  "confused-deputy" finding (`docs/fork/evidence/priv-6a/audit-report.md` #3).

## Context

LQ.AI Oscar Edition is an **enterprise** in-house legal / agentic-modules product (**not** a law firm — read
F019's "firm-wide" wording as *deployment-wide*). It is single-operator-voice today. The real requirement,
stated by the maintainer (2026-06-18): **users have areas of responsibility** — one user handles Privacy, a
colleague does not; several users may share Privacy. That is a many-to-many **users ↔ practice-areas**
authorization model with **roles within an area**, which **does not exist** yet. The ask is *not* to build it
now: it is to (1) put a real permissions track on the roadmap and (2) commit a **design-readiness contract**
so the Privacy/ROPA module and every future module (redlining, assessments) are built ready to flip into
that model with **minimal rework**.

Grounded state of authorization today (verified in code):

- Authority is effectively a **single boolean `users.is_admin`**. `get_admin_user`
  (`api/app/api/dependencies.py:134`) is the only live coarse gate; the JWT carries only `is_admin`.
- A three-value `users.role` (`admin|member|viewer`, DB CHECK, migration 0017) exists and is assignable
  (`admin.update_user_role`, which writes `role` + `is_admin` together atomically with last-admin lockout),
  but its enforcement gate `get_mutating_user`/`MutatingUser` (`dependencies.py:194`) is **mounted on zero
  endpoints** — so `role` carries no runtime authority (dead scaffolding).
- Resource authz is the **cross-user→404** convention, scattered across per-module `_load_visible_*` helpers
  (`projects.py`, `chats.py`) hand-writing `owner_id == actor` predicates; there is no central seam.
- **No `user ↔ practice_area` association exists anywhere.** `team.py`/`TeamMember` is upstream-legacy
  (frozen, ADR-F001) and scopes **skills**, not areas — useful only as a *structural template* (composite
  PK + per-row role + `granted_by` RESTRICT + CASCADE). `teams_tenant.py` is an unrelated Microsoft-365 OAuth
  record (name-only false friend).
- The ROPA register is **deployment-global shared-read** (ADR-F019): reads need only an active user; the
  PRIV-6a confused-deputy finding (any authenticated user can read a privileged matter's confidential
  narrative laundered into a register free-text field) is the concrete symptom of this missing layer.
- `guarded_dispatch` (`api/app/agents/guard.py`) already carries `user_id` + `practice_area_id` as B-class
  (ADR-F004) — used only for audit slicing today, never for allow/deny. `GuardContext` is built **once per
  run** at composition.

## Considered Options

1. **RBAC + area-membership** — a fork-owned `user_practice_areas(user_id, practice_area_id, role)` M:N join
   (modeled on `TeamMember`) consulted by an area-scope authorizer; `is_admin` stays the super-user. Maps 1:1
   to the maintainer's mental model and is UI-auditable, but on its own says nothing about *where* the check
   attaches — risks scattering enforcement like today's `_load_visible_*`.
2. **ABAC / single policy seam** — route every decision through one injected `can(actor, action, resource)`
   that today returns "allow if active/owner/admin" and is the one place a future policy slots in. Makes the
   flip a one-function edit, but under-specifies the data model the maintainer actually wants.
3. **Area-scope incremental** — add only the `user ↔ area` join (no roles yet) + an injected actor-context
   threaded through every seam allowing-all today; flip = a one-line predicate per seam. Maximally reversible,
   but defers the roles the maintainer explicitly asked for, risking a second migration + a second
   dead-enum debate.

## Decision Outcome

**Adopt a graft of all three: a central decision seam + a `user_practice_areas` membership table (with
roles), shipped maximally reversibly.** None is right alone — take the *seam discipline* from (2), the *data
model + admin model* from (1), and the *staged "table-empty → allow-all → flip-the-body" reversibility* from
(3). The role column ships from the start (the maintainer wants roles-within-areas; an unused column is
cheaper than a second migration + dead-enum debate — but ADR must settle the dead `users.role`, see below).

**Target shape:**

- **One injected authorizer** `app/authz/policy.py`, wired once in the composition root (no module-level
  singleton, no import-time I/O — match the `get_db`/`app.state` exemplar), injected via `Depends` at the API
  edge and constructor args in the worker. Two methods: `can(actor, action, resource_ref) -> Decision`
  (point decisions; a read-deny on an owned/area-scoped resource renders as **404**, never 403) and
  `visible_filter(actor, kind) -> ColumnElement[bool]` (a SQLAlchemy predicate **ANDed into list-query
  WHERE clauses** so out-of-scope rows are never materialized — never fetch-all-then-403). `Action` is a
  **closed verb enum**: `read | write | launch_agent | configure_area | export`.
- **One fork-owned table** `user_practice_areas(user_id FK→users CASCADE, practice_area_id FK→practice_areas
  CASCADE, role TEXT CHECK in {area_owner, area_member, area_viewer}, granted_by_user_id FK→users RESTRICT,
  created_at)`, composite PK `(user_id, practice_area_id)` — copying `TeamMember`'s *shape* into a **separate**
  table (never extending the frozen `team_members`). `area_member` = read + drive matters/runs (the default
  "I handle Privacy"); `area_viewer` = read only; `area_owner` = + grant/revoke membership in that area.
- **`is_admin` stays the single deployment super-user / escape hatch**, honored first (short-circuit to
  allow-all-areas) and the authority that grants the first membership. The policy branches on `is_admin`
  only — never on the `role` string. (Accurate note: `role`/`is_admin` drift is narrow — `update_user_role`
  writes both atomically with last-admin lockout — but there is no DB invariant, so `is_admin` is the single
  branch point.)

### Design-readiness contract — applies NOW to every module and all new code

The load-bearing deliverable. Even before any enforcement exists, build to these so the future flip is a
per-seam one-line predicate change, not a rewrite. Each new slice's security pass (CLAUDE.md DoD) checks them.

1. **Authorization is one injected seam, not inline SQL.** New reads call `can(actor, read, ref)` after load
   (point) and AND `visible_filter(actor, kind)` into list WHERE clauses. No new endpoint hand-writes an
   `owner_id == actor` predicate or runs an unscoped register query.
2. **Read-deny → 404, never 403, for owned/area-scoped resources** (preserves the cross-user→404
   no-existence-leak convention through the flip). Admin-authority denials (`get_admin_user`) keep their 403.
3. **Every new module domain row is area-attributed at creation with a durable, NON-NULL `practice_area_id`**
   — a *scoping* column, kept **separate** from any nullable provenance FK (ROPA's `source_project_id` is
   provenance-only, ON DELETE SET NULL — never a scoping key). Without a durable area column `visible_filter`
   has nothing to scope on; this is the hard prerequisite for ever closing the register gap.
4. **Every agent write goes through `guarded_dispatch` carrying `user_id` + `practice_area_id`.** The future
   per-call area check is an **R6-sibling inside the one chokepoint**; tool bodies validate domain content
   only (zero identity/authz logic). The actor's **area set is resolved once at `GuardContext` construction
   (per run) and frozen into the context** — never re-queried per dispatch (avoid compounding the known
   `/auth/refresh` lookup cost).
5. **The two write-admission seams call the seam, not inline `owner_id`:** matter creation
   (`projects.py` area-fetch block) and agent-run launch (`agent_runs.py` + the worker re-validation in
   `composition.py`) replace bare `Project.owner_id == actor` with `can(actor, launch_agent, matter_ref)` so
   the flip changes *who may drive a Privacy matter* from "owner" to "owner OR area-member" without touching
   call sites. **Owner always retains access to matters they created**, independent of area membership (the
   predicate is owner-OR-area-member — never area-only).
6. **The agent tool-grant stays matter-area-keyed; the actor-area predicate is orthogonal.**
   `composition.py` keeps granting which tools *exist* by the matter's area; the new user↔area predicate
   gates *who may launch* (admission) and *who may dispatch* (guard R6-sibling).
7. **`Action` is a closed verb enum, not free strings** — this is where verb-level read/write authority
   lives (subsuming the dead `users.role` intent). **No module may revive or newly mount `get_mutating_user`.**
8. **Resolve membership once per request, DB-backed** (the JWT carries only `is_admin`); pass a frozenset
   down. Do not bloat the token with areas in this iteration.
9. **Audit the decision seam on the existing contract** (counts/types/IDs, never raw values; `guard.py`
   already passes `user_id` + `practice_area_id`) so area-scoped audit queries work the day the flip lands.
10. **Do not extend/overload `team`/`team_members`** (frozen, ADR-F001; scopes skills, mutate branch never
    landed) — copy the shape into the new fork-owned table only. Don't confuse `teams_tenant.py` (M365 OAuth).
11. **On ship the seam is behavior-identical** — `can` = today's owner/admin result, `visible_filter` =
    `true()` for the ROPA register — proven by a **no-op-on-ship test** so the seam lands as a pure refactor
    before any permission exists; the test is the regression anchor for the eventual flip.

## Consequences

- **Refines ADR-F019 §Authz (does not rewrite it).** F019 is immutable-once-accepted and stays accepted. On
  ship this ADR contradicts nothing — `visible_filter('ropa_*')` returns `true()`, so the register stays
  deployment-global exactly as F019 chose. When (and only when) the register read-filter flips
  (rollout Phase 4e, gated on durable area attribution + maintainer acceptance), it **supersedes F019's
  specific clause** "the register is shared across the firm's users … cross-user→404 does not apply to the
  register" — narrowing "any active user" to "any active user *responsible for the area*". F019's
  **relational-schema** and **single-tenant** decisions are untouched.
- **Stays single-tenant — no `org_id`, no `organizations` table.** Areas-of-responsibility scopes *within*
  the one deployment (the `practice_areas` axis already exists). This is distinct from F019's pre-committed
  *multi-org* supersession (that would be a separate `org_id` milestone); this ADR is not that.
- **ADR-F004 / F002 untouched and reused.** `GuardContext` already carries the B-class `user_id` +
  `practice_area_id`; the new predicate consumes them, adds no model-visible tool argument. The matter→area
  binding is purely additively joined.
- **Dead-scaffolding decision:** ADR-F021 **retires** the never-mounted `get_mutating_user`/`MutatingUser`
  and treats the global `users.role` viewer/member distinction as superseded by the seam's `Action` verb axis
  + per-area roles (pending maintainer confirmation — open question 5). Do not leave two role vocabularies
  coexisting.
- **`visible_filter` returns a SQLAlchemy `ColumnElement`** — a little ORM leaks into the authz layer; this
  is the deliberate price of filtering in-query (vs post-filter-403, which leaks counts/existence). Noted so
  it is not "cleaned up" into a bool later.
- **Adoption is discipline, not compiler-enforced:** a future module that hand-writes an inline predicate
  silently escapes the policy. The contract + the per-slice security pass are the guardrail.
- **Phased rollout** (each its own slice; full detail in MILESTONES § Authorization): Track 0 = this ADR +
  roadmap (no code). Phase 1 = ship the seam behavior-identical (refactor `_load_visible_*` + ropa reads to
  delegate; no-op test; the only one-way door). Phase 2 = `user_practice_areas` table + admin grant surface
  (schema only; policy ignores it). Phase 3 = durable `practice_area_id` on ROPA rows + backfill (the hard
  prerequisite). Phase 4 = flip enforcement per seam (creation, launch, guard R6-sibling, owned reads, and
  LAST the register read-filter — closing PRIV-6a). Phase 5 = new modules (redlining/assessments) born
  flip-ready from the contract.

### Open questions for the maintainer (settle before Phase 2+)

1. **Owner retains own-matter access** independent of area membership — confirm (the predicate keeps owner as
   an unconditional allow-path; "simplifying" to area-only is a correctness landmine).
2. **ROPA backfill** when the durable area column lands: attribute all existing register rows to Privacy
   (the only area that writes ROPA today), or derive from `source_project_id`→project→area where non-null?
3. **`area_owner` scope:** may an area_owner *configure* the area (today `AdminUser`-only) and grant
   membership in that area, or only grant membership (area config stays deployment-admin)?
4. **Catalog visibility:** should a user *see* areas they are not responsible for (non-actionable) or are
   those hidden from their cockpit? (UX-vs-leak, not a security boundary itself.)
5. **Retire `users.role` + `get_mutating_user`?** (Recommended: retire; the seam's `Action` carries
   verb-level authority.) Maintainer call since the column is in the DB CHECK.
6. **Granularity ceiling:** area-grain = "responsible for Privacy" grants the whole Privacy set, not
   per-matter sharing. Sufficient, or is per-matter ACL a near-term need (a further model)?

## Update — maintainer decisions + expanded scope (2026-06-19)

The maintainer answered the open questions and **expanded the scope** beyond v1's "area membership only". The
six answers (now settled): **(1)** an owner ALWAYS keeps access to matters they created. **(2)** existing ROPA
rows → stamp **Privacy**; the register is a **programme-level** artifact (area-owned, like OneTrust/TrustArc),
**not** traced per matter, so register reads scope to Privacy-**area** membership. **(4)** non-responsible
areas show **greyed-out** (not hidden) — and the product needs a real **admin-setup + sharing/invitation
system** (below). **(5)** **KEEP roles** — areas must be genuinely segregated + enforced (this **reverses v1's
"retire `users.role`" lean**: an enterprise client needs real area segregation; do not gut roles — wire them
up). **(1/3/6)** confirmed via the expansions below.

**Expanded target (decided; supersedes v1's "area-grain only"):** authorization is **two tiers of grant** plus
cross-area collaboration, all consulted through the one ADR-F021 seam:

- **Area membership** (`user_practice_areas`, v1) — "I handle Privacy" → the area's programme + matters.
- **Per-matter sharing** (NEW, near-term) — share a *single* matter with specific user(s) + a role
  (e.g. `matter_collaborators(project_id, user_id, role)`). The seam's read predicate becomes
  **owner OR area-member OR matter-collaborator** (owner always allowed — decision 1).
- **Invitations** (NEW) — a user invites another **into an area** or **onto a matter**; an issued, auditable,
  revocable grant with a lifecycle (invited → accepted/revoked). Who may invite: admin, area_owner (their
  area), matter owner/collaborator (their matter). Build on the tokenized-link/notification prior art noted
  for PRIV-A2/ADR-F020 where it fits.
- **Cross-area collaboration — person** (NEW) — a Commercial matter needing TUPE input invites an Employment
  **colleague** as a **matter-collaborator**. The matter STAYS single-area (ADR-F002: one matter → one area →
  one agent identity); the colleague is a guest *on that matter*, not a second owning area.
- **Cross-area collaboration — agent ("@ Deep Agent")** (NEW) — the matter's lead agent calls in **another
  area's Deep Agent as a GUEST**: a **time-boxed, matter-scoped, default read-only loan** of that area's
  agent/skills for one consult (the TUPE weigh-in). **Maintainer-confirmed direction.** It honors ADR-F002
  (the matter keeps its own identity; the guest is a scoped subagent à la ADR-F017 multi-source skills), the
  gateway-only egress, and the `guarded_dispatch` chokepoint; **gated by the permission model** (who may
  invoke a guest agent on a matter). **Implementation mechanics are deferred to a dedicated design slice** —
  grounding is in flight (workflow `wf_815d3f81-70e`, to fold next session) and it lands as **rollout Phase 5+
  / its own ADR** when built; this ADR fixes only the *direction* + the *permission gate*.

**Design-readiness contract — additions (v2):** beyond the v1 list — (a) module reads scope through
**owner OR area-member OR matter-collaborator**, never area-only; (b) any "who can see/act on this matter"
decision goes through the seam so per-matter sharing is a predicate change, not a rewrite; (c) invitations/
shares are **first-class auditable grant records** (subject → scope{area|matter} → role, with granted_by +
lifecycle), not ad-hoc flags; (d) a guest (person or agent) added to a matter is a **scoped, revocable grant**
— a guest agent's tool/skill loan is matter-scoped + time-boxed + (default) read-only and still flows through
the gateway + guard.

**Remaining open questions** (the rest are settled above): **(3)** may an `area_owner` *configure* the area
(today admin-only) or only *invite/grant membership*? (lean: invite-only; config stays admin). **(B-invite)**
who exactly may issue each invite type, and is there an email/notification surface or in-app only?
**(guest-agent)** the detailed mechanism (guest subagent vs skills-loan) + its permission verb — deferred to
the dedicated slice.
