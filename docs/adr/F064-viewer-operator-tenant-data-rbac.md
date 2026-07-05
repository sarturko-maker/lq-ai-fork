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

- **D1 — `viewer` becomes ENFORCED read-only.** `operator` is added to `_MUTATING_ROLES`
  (`{admin, member, operator}`) so the gate rejects only `viewer`. `MutatingUser` replaces
  `ActiveUser` on all 52 tenant-data mutating routes (POST/PATCH/PUT/DELETE on owned resources)
  across 14 routers. The 403 fires on the caller's OWN role BEFORE any resource lookup, so it never
  leaks existence — cross-user access stays 404 in the handler body. A new `app.routes` drift guard
  (`tests/test_mutation_rbac.py`) fails CI if any future mutating route is neither role-gated nor in
  a small, justified allowlist (auth self-service, `/users/me` self-service, POST-shaped reads,
  WOPI token-auth, bridge token-auth, legacy autonomous).

- **D2 — `operator` excluded from cross-user tenant data.** New pure helper
  `tenant_admin_visibility(user) -> bool` (`api/app/api/dependencies.py`) replaces `user.is_admin`
  at the 13 admin-sees-all seams in `tabular.py` (list / detail / doc-load) and `playbooks.py` (list
  + every ownership check). The org-admin keeps admin-sees-all; the operator falls back to
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
- **Known residual — `chat_receipts.py:103`.** A same-class operator cross-user tenant-data READ
  bypass (`if chat.owner_id != user.id and not user.is_admin`) that the recon §6 enumeration missed;
  it additionally returns 403 (existence leak) where the fork convention is 404. Out of the ratified
  13-seam scope this slice; a follow-up seam-fix should narrow it to `tenant_admin_visibility` AND
  return 404 (backlog).
- **Legacy Autonomous Layer viewer-enforcement deferred.** `/autonomous/*` mutations are allowlisted
  in the drift guard (per-user isolated + a per-user opt-in gate); CLAUDE.md freezes the legacy
  executors (bugfix-only), so enforcing viewer read-only there is a separate, deferred item.
- **`UserRole` (web) deliberately NOT widened.** The recon read `types.ts` `UserRole` as "stale (no
  operator)"; in fact `PlatformRole = UserRole | 'operator'` already carries operator for DISPLAY,
  and `UserRole` is the ASSIGNABLE-role set (invite / role-update / filter) where the backend
  `_ROLE_ENUM` 422s operator. Widening it would let those assignment types offer a rejected role, so
  this slice documents the split on the line instead (deviation from §C literal, recorded).
