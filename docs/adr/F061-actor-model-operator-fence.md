# F061 — Three-actor model, operator fence, and user-lifecycle tokens

- Status: proposed
- Date: 2026-07-03
- Deciders: maintainer (Arturs) — drafted with the SETUP-3a slice
- Informed by: `docs/fork/plans/SAAS-SETUP-onboarding-architecture.md` §1–2 (the ratified three-actor
  model + configuration hierarchy — "proceed as you suggest", 2026-07-03); ADR-F058 §5 (hosted-SaaS
  charter — the operator/org-admin split it mandates); ADR-F059 (token-at-rest HMAC pattern reused here).

## Context

Before this slice the only account-creation path was the first-run bootstrap (`admin_bootstrap.py` —
a random password logged once). There was no invite, password-reset, email-verification, or admin-
disable surface anywhere; the only self-serve offboarding was the GDPR grace-period delete. A hosted
tenant admin therefore could not onboard their own users, and a lost password had no recovery path.

Separately, a single flat `is_admin` reached BOTH tenant concerns (users, audit, practice-area config,
House Brief) AND platform concerns (gateway model aliases, provider keys, gateway config, tier policy,
tier-floor override). ADR-F058 §5 requires those be split: a customer's org-admin must not be able to
edit the gateway's key-holding egress. The gateway itself has no user-authz — "the backend's `is_admin`
gate is the user-level authorization layer" (`gateway/app/api/dependencies.py`) — so the split is a
backend role change, not a gateway change.

SETUP-3a is the backend for both: the user-lifecycle endpoints and the operator fence. The web UI is
SETUP-3b; standalone email verification, hard-delete offboarding, and `viewer` enforcement are out of
scope.

## Considered options

**Actor model.** (a) Keep one `is_admin`, edge-deny the gateway paths per stack in Caddy. (b) Add an
in-app `operator` role value on the same users table + an `OperatorUser` dependency. — (a) is
config-drift-prone (the fence lives in per-tenant edge config, not the app) and leaves the app's own
authz flat; (b) makes the fence a property of the actor, survives new gateway surfaces automatically,
and keeps ONE auth system. **Chosen: (b)** (Caddy edge-deny stays available as optional belt-and-braces).

**Lifecycle tokens.** (a) A table per purpose (invites, resets). (b) One `user_auth_tokens` table with a
`purpose` discriminator. — (b) shares the issuance/validation/rate-limit/anti-enumeration machinery and
keeps the purpose enum extensible (a future `email_verification` is a new value, not a new table).
**Chosen: (b).**

**Token at rest.** (a) Store the plaintext (or a reversible form). (b) Store only a domain-separated
HMAC-SHA256, ADR-F059's refresh-token pattern. — Reuse (b): the secret is 32 bytes of CSPRNG (~256 bits,
not offline-brute-forceable), so an HMAC verifier is sufficient and the plaintext need never be stored.

## Decision outcome

The three-actor model (SAAS-SETUP §1) is adopted, and SETUP-3a implements its backend:

- **D1 — one token table.** `user_auth_tokens(purpose ∈ {invite, password_reset}, email CITEXT NULL,
  user_id UUID NULL CASCADE, role NULL, token_hmac VARCHAR(64) UNIQUE, created_by NULL, created_at,
  expires_at, consumed_at NULL, revoked_at NULL)` — migration 0085; a shape CHECK enforces
  invite-carries-email+role / reset-carries-user_id.
- **D2 — token format & storage.** Opaque `secrets.token_urlsafe(32)`; at rest ONLY the
  domain-separated HMAC-SHA256 hex (distinct label per purpose, `lq-ai:invite-token:v1` /
  `lq-ai:password-reset-token:v1`, derived from `jwt_secret`). Validation is one indexed equality under
  `SELECT … FOR UPDATE`; single-use is an atomic `consumed_at` write under the row lock (EvalPlanQual
  gives exactly-one-winner on a concurrent redeem, like `/auth/refresh`).
- **D3 — escalation guard.** `operator` is added to the users role CHECK but NOT to the role-endpoint's
  `_ROLE_ENUM` (so requesting it 422s), and the role/disable/invite endpoints REFUSE any `operator`
  target (403). Operator accounts are minted ONLY by bootstrap (`FIRST_RUN_OPERATOR_EMAIL`, idempotent,
  `is_admin=True` so operator ⊃ org-admin, `must_change_password=True`). The `is_admin = role=="admin"`
  sync in the role endpoint is untouched because operator never transits it.
- **D4 — the fence = 403, not 404.** `OperatorUser` mirrors `AdminUser` (403 on an authenticated
  non-operator). Reclassified from `AdminUser` to `OperatorUser`: `/admin/aliases*`,
  `/admin/provider-keys*`, `GET /admin/config`, `PATCH /admin/tier-policy`,
  `POST /inference/override-tier-floor`. `GET /admin/tier-policy` stays `AdminUser` (transparency).
- **D5 — disable is a timestamp.** `users.disabled_at`. Enforced in three places: login (uniform
  `Invalid credentials` 401, byte-identical to a wrong password), `get_current_user` (live access
  tokens die next request), and refresh (401). Disable revokes all sessions; guards: last-admin,
  self-disable, operator-target.
- **D6 — mail best-effort, invites survive SMTP-off.** The transport core moved from
  `autonomous/notify_email.py` to `app/email.py` (`send_email`, never-raise, smtp_host-gated no-op);
  `notify_email` keeps its public API and delegates. Invite/reset links build from a new
  `public_base_url` setting; the invite-create response carries `email_sent` and, when false,
  `accept_url` for out-of-band hand-off. Reset responses NEVER carry the URL.
- **D7 — rate limits + anti-enumeration.** New limiter methods
  `enforce_password_reset_request` (per-IP + per-submitted-email) and `enforce_token_redeem` (per-IP,
  shared by accept-invite + reset-confirm). Reset-request always returns 202 `{"status":"ok"}`;
  invalid/expired/consumed/revoked tokens collapse to one identical 400. Two security-review
  refinements are load-bearing here: the reset email send runs as a **BackgroundTask after the
  response** (an inline SMTP await would make the exists-branch measurably slower — a timing oracle
  defeating the uniform 202), and **at most one reset token is ever live per user** (issuing revokes
  prior active tokens, a completed reset revokes any sibling, and the confirm side re-checks
  `disabled_at`).
- **D8 — routes + audit actions.** Invite CRUD under `/admin/users/invites*`; disable/enable under
  `/admin/users/{id}/{disable,enable}`; unauth `/auth/{accept-invite,password-reset-request,
  password-reset}`. Audit actions carry IDs/counts only — never token material, and
  `password_reset_requested` never echoes the submitted email.

The configuration hierarchy (SAAS-SETUP §2 — Level 0 deployment / Level 1 practice area / Level 2
matter, resolved through the one `build_area_inventory` chokepoint) is recorded here as the structure
future slices build on; SETUP-4a implements its keystone (the tool-group registry refactor).

## Consequences

- The operator is a genuine superset of the org-admin (`is_admin=True, role='operator'`), so it passes
  every `AdminUser` surface AND the fenced ones; a plain org-admin is denied the gateway surfaces. New
  gateway-proxy routes land on `OperatorUser` and inherit the fence for free.
- A structural drift-guard test asserts the exact dependency per fenced route, so a future route can't
  silently land on the wrong side; the SAAS-2 limiter drift-guard is likewise extended for the three new
  unauth endpoints.
- Downgrading migration 0085 restores the three-value role CHECK, which will reject any lingering
  `operator` row — reclassify before a downgrade (acceptable for a bootstrap-only role).
- Standalone email verification, hard-delete offboarding, `viewer` enforcement, org-admin BYOK, and the
  Caddy edge-deny remain deferred (SAAS-SETUP §7 rows 5/8/10). Disable is the v1 offboarding.

## Addendum — SETUP-3b (2026-07-03): web UI, onboarding pages, wizard handover

Appended with the SETUP-3b slice (plan: `docs/fork/plans/SETUP-3b-users-admin-ui-onboarding.md`).
Records the decisions that consume this ADR's backend, plus one deferral from the 3a review.

- **D1 (addendum) — emailed links carry the real SPA paths.** `build_accept_url`/`build_reset_url`
  now emit `/lq-ai/accept-invite?token=…` and `/lq-ai/reset-password?token=…` — the 3a "stable
  placeholder" paths (no `/lq-ai` prefix) are replaced before anything deployed ever emitted them.
  The pages live as siblings of the `(app)` group under `web/src/routes/lq-ai/` and both literal
  paths are exact-match entries in the auth gate's `isAuthExempt()` allowlist.
- **D6 (addendum) — operator rows stay visible, badged, locked** (3a-review open Q2, decided).
  The unfiltered `GET /admin/users` includes operator rows; the Users admin UI renders them with a
  distinct "Platform operator" badge and every action disabled (the server 403s regardless — the UI
  mirrors the fence). `operator` is never offered as a role choice or filter. Rationale:
  transparency is load-bearing in this product — a hidden privileged account in a tenant stack is
  worse than a visible immutable one.
- **D7 (addendum) — wizard handover = reset-email variant.** With SMTP configured,
  `scripts/setup-tenant.sh` POSTs `/auth/password-reset-request` for `ADMIN_EMAIL` against the
  deployed public origin (deploy.sh's retrying-smoke pattern; cold-start tolerated) and prints
  "handover email sent" — the bootstrap password is never scraped or printed on that branch. With
  SMTP unset, the log-scrape print remains, explicitly labelled as the SMTP-off fallback. The
  wizard also gains an optional `OPERATOR_EMAIL` manifest/prompt field (same email + charset fences
  as `ADMIN_EMAIL`) → `FIRST_RUN_OPERATOR_EMAIL` in `.env.prod` when set, omitted entirely when
  empty (self-host semantics). *Threat-model note (right-sizing):* the bootstrap password is a
  random, `must_change_password=True`, forced-rotate credential — the customer's chosen password
  never transits the operator even without this change. What D7 buys is (1) no live credential in
  terminal scrollback/logs during handover, (2) an email-first professional flow, (3) self-serve
  recovery. The rejected alternative (bootstrap mints an invite instead of a user) achieves
  zero-knowledge only when SMTP is on anyway and would destabilise the boot invariants
  (bootstrap-status/login-hint coupling, a third account-creation path).
- **D8 (addendum) — `hosted` signal on bootstrap-status.** `GET /admin/bootstrap-status` gains
  `hosted: bool`, derived server-side from `settings.first_run_operator_email is not None` (an
  operator-managed stack). The login page's fresh-install hint swaps the docker-log-grep
  instruction (meaningless to a tenant admin with no shell on the node) for "check your welcome
  email or use Forgot your password?"; self-host copy is unchanged. Response-schema addition only.
- **Q1 deferral — `_MUTATING_ROLES`/`MutatingUser` dead code** (3a-review open Q1, recorded).
  `MutatingUser` is wired into zero endpoints (verified on main and the 3a branch); `viewer` is a
  label, not an enforcement boundary. The viewer AND operator tenant-data question is one coherent
  RBAC decision and is deferred to SETUP-5 as already slated — nothing removed or changed here.
