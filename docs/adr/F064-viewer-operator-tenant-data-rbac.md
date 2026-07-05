# F064 — Viewer/operator tenant-data RBAC: enforced read-only viewer + operator ⊅ cross-user tenant data

- Status: **proposed**
- Date: 2026-07-05
- Deciders: maintainer (Arturs), agent
- Slice: **SETUP-5b**. Closes the Q1 RBAC deferral opened in **ADR-F061** (actor model / operator
  fence) addendum. Builds on **ADR-F058** (three delivery modes: hosted SaaS + two self-host) and
  **ADR-F062** (deployment→area config hierarchy). Companion plan:
  `docs/fork/plans/SETUP-5b-tenant-data-rbac.md`.

## Context

Two coupled RBAC gaps were deferred from SETUP-3a/3b to SETUP-5 as "one coherent decision". The
ADR-F061 addendum (SETUP-3b) recorded the deferral verbatim:

> **Q1 deferral — `_MUTATING_ROLES`/`MutatingUser` dead code** (3a-review open Q1, recorded).
> `MutatingUser` is wired into zero endpoints (verified on main and the 3a branch); `viewer` is a
> label, not an enforcement boundary. The viewer AND operator tenant-data question is one coherent
> RBAC decision and is deferred to SETUP-5 as already slated — nothing removed or changed here.

The two gaps, both verified in code (recon `docs/fork/plans/` + this slice):

1. **`viewer` is unenforced.** `get_mutating_user` / `_MUTATING_ROLES` (Wave C) exists but has ZERO
   endpoint usages — every mutating route sits on `ActiveUser`, which never reads `role`. The
   SETUP-3b Users admin UI tells the operator "viewers are read-only", but a `viewer` login has the
   exact write capability of a `member`.

2. **`operator` silently inherits admin-sees-all on tenant data.** ADR-F061 D3 makes the platform
   operator an `is_admin` superset ("operator ⊃ org-admin") to pass every `AdminUser` surface. But
   several pre-operator tenant-data endpoints (tabular, playbooks) carry a *business-logic*
   `if not user.is_admin: <scope to own rows>` bypass — so the operator now sees/acts on OTHER
   users' matters/playbooks/tabular runs. The ADR-F061 fence audit scoped only the admin *pages*
   (aliases/provider-keys/config/tier-policy/override); these tenant-data seams were never framed as
   an operator-fence question.

Framing is mode-neutral (ADR-F058: hosted is only one of three delivery modes). The operator is
"whoever runs the platform" — a hosting company in Mode 2, or the firm's OWN IT in self-host Mode 1.
The rationale for D2 is separation of duties (platform operations vs. the firm's legal matters),
which a firm may want from its own IT too; it is confidentiality-critical only in the hosted case.

## Considered options

**D1 — viewer enforcement.**
1. **Enforce now: swap `ActiveUser` → `MutatingUser` on every tenant-data mutating route.** The gate
   already exists; wiring it in is zero new plumbing and makes the 3b UI promise true.
2. **Keep `viewer` label-only.** Cheapest, but ships a documented-but-false "read-only" claim — an
   auditor login can still write.
3. **Delete the `viewer` role.** Removes the false promise, but throws away a genuinely wanted
   read-only-observer capability (auditors, seconded reviewers) and churns the enum + migration.

**D2 — operator tenant-data visibility.**
1. **Exclude operator from the `is_admin` admin-sees-all seams** via a small helper
   (`tenant_admin_visibility = is_admin and role != "operator"`); org-admin keeps sees-all.
2. **Accept the superset.** Leave operator with cross-user tenant-data read/write. Simplest, but in
   the hosted case the platform operator can read every tenant user's matters — a confidentiality
   break, and the exact thing the operator fence exists to prevent.
3. **Full `org_id` row-partitioning of tenant data.** The "correct" long-term model, but this fork's
   Option-A deployment is stack-per-tenant (one DB per firm), so there is no cross-tenant row
   mixing to partition; a full multi-tenant rewrite is disproportionate to the gap.

## Decision outcome

Adopt **D1 option 1** and **D2 option 1**.

- **D1 — `viewer` becomes ENFORCED read-only across the ENTIRE tenant-data surface, legacy
  included.** `operator` is added to `_MUTATING_ROLES` (`{admin, member, operator}`) so the gate
  rejects only `viewer`. `MutatingUser` replaces `ActiveUser` on all 68 tenant-data mutating routes
  (POST/PATCH/PUT/DELETE on owned resources): 52 direct swaps across 14 routers, plus the 16 legacy
  `/autonomous/*` mutations (lead review, §E) — `get_autonomous_enabled_user` now stacks on
  `MutatingUser` so BOTH checks hold (viewer role gate first, then the per-user opt-in flag), and
  `halt` (a mutation without the opt-in gate, M4-C2 split) carries `MutatingUser` directly. Gating
  the legacy API edge is an authz bugfix, not an extension of the frozen executors. The 403 fires on
  the caller's OWN role BEFORE any resource lookup, so it never leaks existence — cross-user access
  stays 404 in the handler body. A new `app.routes` drift guard (`tests/test_mutation_rbac.py`)
  fails CI if any future mutating route is neither role-gated nor in a small, justified allowlist
  (auth self-service, `/users/me` self-service, POST-shaped reads, WOPI token-auth, bridge
  token-auth).

- **D2 — `operator` excluded from cross-user tenant data.** New pure helper
  `tenant_admin_visibility(user) -> bool` (`api/app/api/dependencies.py`) replaces `user.is_admin`
  at the 14 admin-sees-all seams: 13 in `tabular.py` (list / detail / doc-load) and `playbooks.py`
  (list + every ownership check), plus `chat_receipts.py` (receipt read — found during the slice as
  a recon §6 gap and fixed on lead review, §E; the same fix converts its 403-after-fetch into the
  existence-rule 404). The org-admin keeps admin-sees-all; the operator falls back to
  owner-scoped, member-like access on tenant data. It loses ONLY cross-user tenant-data visibility —
  it keeps every `OperatorUser` fence surface, every `AdminUser` admin surface (users/areas/
  capabilities — platform config, the fence's own scope), and normal access to rows it owns (which
  is why it stays in `_MUTATING_ROLES`).

- **No migration, no new routes, no new dependency.** The `/api/v1` path count stays 171; the
  gateway is untouched. `admin.py`'s `_ROLE_ENUM` still excludes `operator` (unchanged).

## Consequences

- **Self-host posture (ADR-F058, load-bearing).** Minting an operator account is OPTIONAL
  (`FIRST_RUN_OPERATOR_EMAIL`). A self-hosted firm that SKIPS it has no operator row; its org-admins
  keep admin-sees-all on tenant data exactly as before this slice, and the gateway fence surfaces
  (aliases/provider-keys/tier-policy/override) then require minting an operator to reach at all. The
  operator / no-operator choice IS the self-hoster's separation-of-duties dial — this slice changes
  nothing for a firm that never mints one, and hardens confidentiality for hosted/segregated
  deployments that do.
- **Stale-UI 403s for viewers.** Server enforcement is the boundary; the web still renders write
  affordances for a `viewer` and surfaces the 403 via `describeMutationError`. Affordance-hiding
  (buttons/compose/toggles hidden for `role==='viewer'`) is UI polish, deferred to the MILESTONES
  backlog.
- **Break-glass is a future explicit feature, not built.** If a hosted operator ever needs
  authorized cross-user tenant-data access (incident response, legal hold), that is an explicit,
  audited, time-boxed grant — never the silent `is_admin` superset this slice removes.
- **`chat_receipts.py` cross-user 403 → 404 (behavior change).** The receipt read previously
  returned 403 "You do not own this chat" after fetching a non-owned chat — an existence leak the
  recon §6 enumeration missed. §E collapses non-owner access into the same `NotFound` as a missing
  chat and excludes the operator via `tenant_admin_visibility`; clients that pinned the 403 must
  treat 404 as the only cross-user signal (the fork's existing convention).
- **Legacy autonomous mutations are viewer-gated too.** Opted-in viewers (if any exist) lose
  autonomous mutation access; the opt-in flag semantics are unchanged for member/admin/operator.
  Reads (sessions/findings/artifacts/lists) stay on `ActiveUser` per the M4-C2 opt-out split.
- **WOPI write-path role re-check (§F, security review).** D1 is enforced at editor-session MINT
  (`POST /files/{id}/editor-session` → `MutatingUser`), but the minted WOPI token lives for
  `wopi_token_ttl_seconds` (default hours) and authorizes on ownership alone — a demotion window the
  bearer path doesn't have (it re-reads the role every request). The MUTATING WOPI ops (PutFile +
  the lock family) now re-verify the caller's CURRENT role and liveness (deleted/disabled, mirroring
  `get_current_user`) per request via one PK select (`wopi._require_live_mutating_user`), answering
  **401** — session-invalid to Collabora, the status it renders correctly — never a 403 body. READ
  ops (CheckFileInfo, GetFile) deliberately stay role-free: a demoted-to-viewer user may still read
  their own file (D1 makes viewer read-only, not no-access).
- **`UserRole` (web) deliberately NOT widened.** The recon read `types.ts` `UserRole` as "stale (no
  operator)"; in fact `PlatformRole = UserRole | 'operator'` already carries operator for DISPLAY,
  and `UserRole` is the ASSIGNABLE-role set (invite / role-update / filter) where the backend
  `_ROLE_ENUM` 422s operator. Widening it would let those assignment types offer a rejected role, so
  this slice documents the split on the line instead (deviation from §C literal, recorded).
