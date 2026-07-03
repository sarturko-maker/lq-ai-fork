# SETUP-3a — user lifecycle backend + operator fence

Status: DRAFT (lead-authored slice plan; parent plan `SAAS-SETUP-onboarding-architecture.md`
§1 + §4 is ACCEPTED — maintainer ratified 2026-07-03). Implements task #459.
Working model: Opus implements in a worktree (auth/crypto = security-sensitive); lead
verifies + runs the deep security review pass.

## Context (recon anchors — verified 2026-07-03)

- NO invite / password-reset / email-verification / admin-disable endpoint exists anywhere.
  The only account-creation path is first-boot bootstrap (`api/app/admin_bootstrap.py` —
  random password logged once, `must_change_password=true`).
- `users.role` CHECK is `role IN ('admin','member','viewer')` (migration `0017`, line 58);
  `is_admin` is kept in sync by `update_user_role` (`api/app/api/admin.py:765`) via
  `is_admin = role == "admin"` behind a `_ROLE_ENUM` allowlist + last-admin lockout guard.
- `AdminUser` dependency = `api/app/api/dependencies.py` `get_admin_user` (403 `forbidden`).
- SAAS-2 rate limiter: `app/security/rate_limit.py`, injected `RateLimiterDep` in
  `auth.py` (`enforce_login` at :409 is the pattern to clone).
- Token-at-rest discipline precedent: ADR-F059 `refresh_token_hmac` — domain-separated
  HMAC-SHA256 (key derived from `jwt_secret`), VARCHAR(64) UNIQUE, one indexed lookup.
- Mail transport: `api/app/autonomous/notify_email.py` (`_send_sync` + never-raise async
  wrapper; smtp_host-gated no-op). SMTP env forwarding landed in SETUP-2 (api + arq-worker).
- `api/app/config.py` has NO public-URL field (bare env names, no env_prefix — line 143
  precedent). Emailed links need one.
- Migrations head on main: **0084**. Next free = 0085 — but AIC PRs #188–190 hold unmerged
  0085/0086; **CHECK the actual head at build time** (AIC renumbers on rebase, not us).

## Goals

1. **Invite lifecycle (backend):** admin creates an invite (email + role ∈ {admin, member,
   viewer} — NEVER operator) → single-use, 7-day-TTL token, HMAC-hashed at rest → invited
   user accepts with token + new password (creates the user, marks email verified) →
   resend (revokes + reissues) → revoke. All admin actions audited (IDs/counts, never
   token material).
2. **Password reset (backend):** unauthenticated request → uniform 202 regardless of
   account existence (anti-enumeration) → emailed single-use token (1-hour TTL) →
   reset endpoint sets password, revokes all sessions.
3. **Admin disable / re-enable:** `users.disabled_at`; disable revokes sessions and kills
   live access tokens (checked in `get_current_user`), login stays uniform-401. Last-admin
   guard; operator accounts untouchable from org-admin endpoints.
4. **Operator fence:** new `operator` role value + `OperatorUser` dependency (clone
   `get_admin_user`); reclassify the gateway-proxy surfaces per parent plan §1; bootstrap
   path for the operator account (`FIRST_RUN_OPERATOR_EMAIL`).
5. **Mail generalized:** transport core moved out of `autonomous/` into a shared module;
   `notify_email.py` keeps its public API and delegates.

## Non-goals (recorded, not forgotten)

- **No web UI** — accept-invite/reset pages, Users admin UI, onboarding flow, nav gating of
  `/admin/developer`+`/admin/models` pages, and the wizard's invite-handover switch are
  **SETUP-3b**.
- No standalone email-verification flow (invite-accept IS the verification in
  invitation-only Mode-2; the token table's `purpose` enum keeps `email_verify` possible).
- No admin-initiated hard delete (self-serve GDPR delete exists; offboard = disable v1).
- No `viewer` enforcement (SETUP-5 decision); no Caddy edge-deny of operator paths
  (recorded belt-and-braces option, per-tenant stacks can add it later).
- No gateway change of any kind (the fence is backend roles — parent plan §1 rationale).

## Design decisions

**D1 — one token table.** `user_auth_tokens`: `id` UUID PK · `purpose` TEXT CHECK
(`invite`,`password_reset`) · `email` CITEXT (invite target) · `user_id` UUID NULL FK
(reset target; CASCADE) · `role` TEXT NULL CHECK (`admin`,`member`,`viewer`) ·
`token_hmac` VARCHAR(64) NOT NULL UNIQUE · `created_by` UUID NULL FK · `created_at` /
`expires_at` NOT NULL · `consumed_at` / `revoked_at` NULL. One issuance/validation
service, one hash discipline, one shape for future purposes.

**D2 — token format & storage.** Opaque `secrets.token_urlsafe(32)`; at rest ONLY the
domain-separated HMAC-SHA256 hex (ADR-F059 pattern; domain string distinct per purpose,
e.g. `lq-ai:invite-token:v1`). Validation = one indexed equality + `FOR UPDATE`; single-use
= atomic consume (`consumed_at IS NULL` guard under the row lock). Plaintext token appears
only in the email link and (see D6) the create response.

**D3 — the escalation hole is the review's first target.** `operator` is added to the DB
CHECK but **NOT** to `update_user_role`'s `_ROLE_ENUM` (422 on attempt), and that endpoint
(plus disable/invite) **refuses any target whose role is `operator`** (403). Operator
accounts are minted ONLY by bootstrap (`FIRST_RUN_OPERATOR_EMAIL`, idempotent, random
password logged once, `must_change_password=true`, `is_admin=true` so the operator also
passes org-admin surfaces; `role='operator'`). The `is_admin = role=="admin"` sync in
`update_user_role` is untouched because operator never transits that endpoint.

**D4 — fence = 403, not 404.** `OperatorUser` mirrors `AdminUser` (403 `forbidden` on an
authenticated non-operator). The 404-not-403 rule is for cross-USER resource access;
role-gated admin surfaces already use 403 (`get_admin_user` precedent). Reclassified to
`OperatorUser`: `/admin/aliases*` (5 routes), `/admin/provider-keys*` (4), `/admin/config`,
`PATCH /admin/tier-policy`, `POST /inference/override-tier-floor`. `GET /admin/tier-policy`
stays `AdminUser` (transparency: admins may read the policy they run under).

**D5 — disable semantics.** `disabled_at` timestamp (not bool — carries when). Enforced in
THREE places: login (uniform `invalid credentials` 401 — no enumeration), `get_current_user`
(live access tokens die on next request), refresh (401). Disable revokes all sessions
immediately. Guards: last-admin (mirror the role-endpoint guard), self-disable refused,
operator targets refused (D3).

**D6 — mail is best-effort; invites must survive SMTP-off.** Transport core →
`api/app/email.py` (`send_email(to, subject, body) -> bool`, never-raise, smtp_host-gated
no-op — semantics copied verbatim from notify_email). Invite/reset senders build links from
a NEW `public_base_url` setting (bare env `PUBLIC_BASE_URL`; prod compose forwards
`https://${LQ_AI_PUBLIC_ORIGIN}` — always concrete, SETUP-2 guaranteed). Invite-create
response carries `email_sent: bool` and, when false, `accept_url` so the admin can hand it
over out-of-band (audited; pragmatic v1 for the weekend bring-up — this is also what the
SETUP-3b wizard handover will print). Reset responses NEVER carry the URL (unauthenticated
caller).

**D7 — rate limits + anti-enumeration.** New limiter methods on the SAAS-2 `RateLimiter`
(same Lua fixed-window, same env-knob convention, forwarded in prod compose):
`enforce_password_reset_request` (per-IP + per-submitted-email), `enforce_token_redeem`
(per-IP; shared by accept-invite + reset-confirm). Uniform responses: reset-request always
202 `{status:"ok"}`; invalid/expired/consumed/revoked token → one identical 400 shape.

**D8 — routes.**
- `POST /admin/users/invites` (AdminUser) — create; 409 if an active user or pending invite
  exists for the email.
- `GET /admin/users/invites` (AdminUser) — list pending/consumed/revoked.
- `POST /admin/users/invites/{id}/resend` (AdminUser) — revoke old token, mint new, remail.
- `DELETE /admin/users/invites/{id}` (AdminUser) — revoke.
- `POST /auth/accept-invite` (unauth) — {token, password, display_name?} → creates user
  (role from the invite, `email_verified_at=now()`, no forced change — they just set it).
- `POST /auth/password-reset-request` (unauth) — {email} → 202 always.
- `POST /auth/password-reset` (unauth) — {token, new_password} → resets + revokes sessions.
- `POST /admin/users/{id}/disable` · `POST /admin/users/{id}/enable` (AdminUser).
Audit actions: `user.invited`, `user.invite_resent`, `user.invite_revoked`,
`user.invite_accepted`, `user.password_reset_requested` (count only, no email echo),
`user.password_reset_completed`, `user.disabled`, `user.enabled`.

**D9 — migration (number = main's head + 1 at build time, expect 0085).** (a)
`user_auth_tokens` per D1; (b) `users.disabled_at` + `users.email_verified_at` TIMESTAMPTZ
NULL; (c) drop/recreate the 0017 role CHECK as `role IN ('admin','member','viewer',
'operator')` (look up the real constraint name in 0017, don't guess). Update
`test_migrations.py` inventory.

**D10 — ADR-F061** (actor model + operator fence + config hierarchy, parent plan §1–2)
drafted in this PR, status `proposed`.

## Files (expected)

- NEW `api/alembic/versions/0085_user_lifecycle_operator_fence.py` (number per D9)
- NEW `api/app/models/user_auth_token.py` (+ `models/__init__.py` export);
  `models/user.py` (+2 columns)
- NEW `api/app/auth_tokens.py` — issuance/validation service (HMAC derive, consume-once)
- NEW `api/app/email.py` — shared transport; `api/app/autonomous/notify_email.py` delegates
- NEW `api/app/lifecycle_email.py` (or fold into email.py) — invite/reset messages + links
- `api/app/api/dependencies.py` — `get_operator_user` + `OperatorUser`
- `api/app/api/admin.py` — invites CRUD, disable/enable, D3 guards on the role endpoint,
  reclassify aliases/config/provider-keys/tier-policy-PATCH deps
- `api/app/api/inference_override.py` — `OperatorUser`
- `api/app/api/auth.py` — accept-invite, reset-request, reset; disabled_at checks
- `api/app/security/rate_limit.py` — two new enforce methods + settings knobs
- `api/app/config.py` — `public_base_url` + rate-limit knobs
- `api/app/admin_bootstrap.py` — `FIRST_RUN_OPERATOR_EMAIL` (idempotent, same pattern)
- `docker-compose.prod.yml` + `.env.prod.example` — `PUBLIC_BASE_URL`,
  `FIRST_RUN_OPERATOR_EMAIL`, new `RATE_LIMIT_*` knobs (all `${VAR:-}` optional)
- `docs/adr/F061-*.md` (NEW, proposed) · `docs/db-schema.md` · HANDOFF · MILESTONES
- Tests: NEW `test_user_invites.py`, `test_password_reset.py`, `test_operator_fence.py`,
  `test_admin_disable.py`; extend `test_migrations.py`, `test_admin_users.py` (role-endpoint
  guards), auth wiring drift-guard (SAAS-2 precedent — every new unauth endpoint must
  appear in the limiter-wiring test), notify_email regression must stay green.

## Tests that gate the merge (security-first)

1. Token: parallel accept of the same token → exactly ONE wins (real race, two tasks);
   expired/revoked/consumed → the one uniform 400; DB rows carry HMAC only (assert no
   plaintext substring); resend revokes the prior token.
2. Escalation: `PATCH role=operator` → 422; any mutation (role/disable/invite-role) whose
   target is an operator → 403; invite with `role=operator` → 422; last-admin guards hold.
3. Fence: parametrized sweep — each reclassified route 403s for `role=admin` and passes for
   the bootstrap operator; a drift-guard asserting the exact dependency per route table
   (so a future route can't silently land on the wrong side).
4. Anti-enum: reset-request returns byte-identical status/body for existing vs missing
   email; login for a disabled user is byte-identical to wrong-password.
5. Disable: live access token 401s post-disable; refresh 401s; sessions revoked; enable
   restores; self/last-admin/operator guards.
6. Rate limits: 429 + Retry-After on the new endpoints past the window; fail-open on
   Redis fault (SAAS-2 semantics).
7. Bootstrap: operator created once, idempotent reboot, password logged once,
   `must_change_password` honored on their first API call.
8. Mail: `send_email` no-op-unconfigured + never-raise; invite-create returns
   `email_sent=false` + `accept_url` when SMTP off; notify_email behavior unchanged.

## Verification / DoD (ADR-F005)

- Containerized `api` pytest full-suite counts quoted; ruff + mypy clean (CI commands).
- Migration verified on a throwaway pgvector container (NEVER host-side against dev DB);
  rebuild api + arq-worker + ingest-worker together; `docker image prune -f`.
- Live dev-stack smoke: curl invite (SMTP off → `accept_url`) → accept sets password →
  login → member 403s on `/admin/aliases`; operator passes. Evidence in the PR.
- Fresh-context adversarial review + the ALWAYS security pass, PLUS the deeper
  security-focused pass (auth path — mandated by CLAUDE.md merge policy). Review brief
  names D3 (escalation), D2 (hash-at-rest), D7 (enumeration), token race.
- ADR-F061 drafted; HANDOFF + MILESTONES updated; squash-merge on full gate.

## Sequencing / risks

- Single PR off main after SETUP-2 (#216) merges. Migration-number trap: AIC's unmerged
  0085/0086 renumber on THEIR rebase — we take main's next free number.
- `notify_email.py` refactor risk is LOW (delegation, public API frozen) but its
  never-raise contract is load-bearing for autonomous runs — regression tests must stay.
- The bootstrap operator + `PUBLIC_BASE_URL` compose additions must stay `${VAR:-}`
  optional so existing dev stacks boot unchanged.
- Size L: if the worktree agent runs long, the natural split seam is (invites+reset+mail)
  first, (fence+disable+bootstrap) second — but prefer one PR; the fence tests depend on
  the operator bootstrap anyway.
