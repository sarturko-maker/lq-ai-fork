# Plan — SETUP-3b: Users admin UI + onboarding pages + wizard invite-handover

Status: ACCEPTED (working model: lead plans/verifies, Sonnet implements). Parent:
`docs/fork/plans/SAAS-SETUP-onboarding-architecture.md` §4/§6 (SETUP-3b row). Backend substrate:
SETUP-3a (`docs/fork/plans/SETUP-3a-user-lifecycle-operator-fence.md`, ADR-F061, PR #217).
Grounded in a 4-lens recon (API surface / admin-UI conventions / unauth flows / wizard handover),
2026-07-03.

## Context (recon facts the design hangs on)

- 3a shipped the complete lifecycle API: invites CRUD (`POST/GET /admin/users/invites`,
  `POST .../{id}/resend`, `DELETE .../{id}`), unauth `POST /auth/accept-invite` (creates the user,
  no tokens returned), `POST /auth/password-reset-request` (uniform 202) + `POST /auth/password-reset`
  (204, revokes sessions), `POST /admin/users/{id}/disable|enable`, plus the existing
  `GET /admin/users` (now with `disabled_at`) and `PATCH /admin/users/{id}/role`
  (`_ROLE_ENUM={admin,member,viewer}`; operator targets 403 everywhere).
- **URL mismatch:** `lifecycle_email.py` builds `/accept-invite?token=` and `/reset-password?token=`
  with NO `/lq-ai` prefix (recorded in-code as "a stable placeholder"; SETUP-3b lands the real path).
  Every SPA route lives under `/lq-ai/*`; the auth gate is one file
  (`web/src/routes/lq-ai/+layout.svelte`) with a hardcoded `isAuthExempt()` allowlist
  (login, change-password).
- `DevRoleManagementCard.svelte` (inside `/admin/developer`) is already a user list + role editor
  with filter/pagination/409-handling — ~90% of a Users page.
- Web has two design generations: legacy `--lq-*` (all 5 current admin pages) vs the semantic-token
  primitives (`ModalShell`, `Table`, `Badge`, `Alert`, `FormControl`, shadcn `Table`/`Badge`).
  Design rule: NEW surfaces use the semantic tokens.
- Wizard handover today (`scripts/setup-tenant.sh:666-707`): greps `First-run admin password` from
  the api log and prints the plaintext to the operator's terminal. The wizard does NOT write
  `FIRST_RUN_OPERATOR_EMAIL` (3a config) — tenant stacks currently get no operator account.
- `GET /admin/bootstrap-status` (unauth) + the login page render a "grep the api log" hint while
  the bootstrap admin still has `must_change_password=True` — self-host-critical, but dev-flavoured
  copy on a hosted tenant's login screen.
- Threat-model note that RIGHT-SIZES the handover work: the bootstrap password is a RANDOM,
  `must_change_password=True`, forced-rotate credential. The customer's own chosen password never
  transits the operator even today. What 3b buys is (1) no live credential in terminal
  scrollback/logs during handover, (2) an email-first professional flow, (3) self-serve recovery.
  A bootstrap rewrite (mint-invite-instead-of-user) is NOT required for the stated goal and would
  destabilise the boot invariants the weekend bring-up depends on (bootstrap-status/login-hint
  coupling, three account-creation paths).

## Goals

1. **Users admin page** (`/lq-ai/admin/users`): tenant users table (email, role, status incl.
   disabled/pending-deletion, last login) with role change + disable/enable; pending-invites section
   with create (modal), resend, revoke; SMTP-off surfaces `accept_url` for out-of-band handover.
2. **Unauth token pages**: `/lq-ai/accept-invite` (set password → success → sign-in) and
   `/lq-ai/reset-password` (no token = request form; token = confirm form), plus a
   "Forgot your password?" link on the login page.
3. **Fence gating in the web UI**: org-admins never see pages/actions that now 403
   (`/admin/models` aliases CRUD, `GET /admin/config` consumers on `/admin/developer`); tier policy
   renders read-only for admins; admin sub-nav filtered by role.
4. **Wizard invite-handover**: SMTP-on → the wizard fires `POST /auth/password-reset-request` for
   `ADMIN_EMAIL` and prints "handover email sent" (never scrapes/prints the password); SMTP-off →
   explicit fallback to today's log-scrape print. Wizard also prompts for + writes
   `FIRST_RUN_OPERATOR_EMAIL` (decision #5 of the parent plan needs it on tenant stacks).
5. **Hosted-aware login hint**: `bootstrap-status` gains `hosted: bool`
   (`first_run_operator_email` set ⇒ operator-managed stack); hosted login hint says "check your
   welcome email / use Forgot your password?" instead of the docker-grep instruction (self-host
   copy unchanged).
6. Record the two 3a-review open Qs + the handover decision in an **ADR-F061 addendum**.

## Non-goals (recorded)

- **First-login onboarding checklist** (House Brief → invite users → review area defaults) →
  split out as **SETUP-3c** (own slice; this one is already M without it).
- No RBAC/tenant-data enforcement change: `_MUTATING_ROLES` untouched; `MutatingUser` is dead code
  (zero endpoints wire it, verified on main and the 3a branch) — the viewer AND operator
  tenant-data question is ONE coherent decision, deferred to SETUP-5 as already slated.
- No new `/api/v1` routes, no migration, no gateway change, no new dependency.
- No auto-login after accept/reset (house pattern is redirect-to-login: `change-password` precedent;
  the endpoints deliberately return no tokens).
- No toast system (none exists); feedback via inline `Alert`/banners.
- No email-verification flow; no admin hard-delete (unchanged 3a non-goals).

## Decisions

- **D1 — link paths get the real prefix.** `build_accept_url`/`build_reset_url` →
  `/lq-ai/accept-invite?token=…` / `/lq-ai/reset-password?token=…` (2-line change + test updates).
  Pages live as siblings of `(app)` under `web/src/routes/lq-ai/`; both paths added to
  `isAuthExempt()`. (Alternative — top-level routes outside `lq-ai/` — loses the shared shell/guard
  machinery for zero benefit. Nothing deployed has emitted the placeholder URLs yet.)
- **D2 — accept flow = set password → success panel → "Sign in" → `/lq-ai/login`.** Email shown on
  the success panel from `AcceptInviteResponse.email`; never placed in the login URL/localStorage.
- **D3 — reset page is dual-state.** No/empty `?token=` → request form (email → always the same
  "if an account exists, an email has been sent" message, mirroring the API's uniform 202);
  with token → new-password + confirm form → success → sign-in link. Client mirrors
  `password_min_length` 12 (the `ChangePasswordCard` hardcode precedent).
- **D4 — Users page is generation-B** (semantic tokens + `ModalShell`/`Table`/`Badge`/`Alert`/
  `FormControl`). Deliberate divergence from the legacy sibling admin pages, recorded here: new
  surfaces take the new system; siblings migrate when touched. `<title>Users — LQ.AI Oscar Edition
  admin</title>` (audit-log precedent).
- **D5 — role management consolidates into the Users page.** `DevRoleManagementCard` is removed
  from `/admin/developer` (its logic/patterns move to the Users page — reuse, don't rewrite;
  `formatRelativeDate` etc. lift out). One place to manage users; simplification-pass credit.
- **D6 — operator rows stay visible, badged, locked** (open Q2 decision). The unfiltered
  `GET /admin/users` already includes them; the UI renders a distinct "Platform operator" badge
  and disables role/disable/enable actions for those rows (the server 403s anyway — the UI mirrors
  the fence, never offers `operator` as a selectable role). Transparency is load-bearing in this
  product: a hidden privileged account in a tenant stack is worse than a visible immutable one.
  The role FILTER dropdown offers all/admin/member/viewer only (`role=operator` 400s by design).
- **D7 — wizard handover = reset-email variant** (open ranking confirmed): zero backend change;
  `scripts/setup-tenant.sh` handover block (a) when SMTP configured: POST
  `/auth/password-reset-request` for `$ADMIN_EMAIL` via curl against the deployed stack, print
  "welcome email sent to X — they set their own password; recovery is self-serve via Forgot
  password"; the password grep/print is REMOVED from this branch; (b) when SMTP unset: today's
  log-scrape print, explicitly labelled as the SMTP-off fallback. Rationale: the alternative
  (bootstrap mints an invite, no eager admin row) achieves zero-knowledge only when SMTP is on
  anyway, and has the widest blast radius (bootstrap-status/login-hint coupling, `created_by`
  typing, a third account-creation path).
- **D8 — `hosted` flag on bootstrap-status.** Derived server-side from
  `settings.first_run_operator_email is not None`. Response-schema addition only (no new route, so
  no endpoint-guard test churn beyond the schema assertions).

## Implementation

### A. Backend (small, no new routes)
- `api/app/lifecycle_email.py` — D1 prefix; update its tests (exact-URL assertions).
- `api/app/api/bootstrap.py` — add `hosted` to the response model + derivation; extend
  `test_bootstrap*` (hosted true/false).

### B. Web API clients + types
- `web/src/lib/lq-ai/api/auth.ts` — `acceptInvite`, `passwordResetRequest`, `passwordResetConfirm`
  (all `skipAuth: true, skipRefresh: true`).
- `web/src/lib/lq-ai/api/admin.ts` — `createInvite`, `listInvites`, `resendInvite`, `revokeInvite`,
  `disableUser`, `enableUser` (existing `listUsers`/`patchUserRole` reused).
- `web/src/lib/lq-ai/types.ts` — mirror the 3a Pydantic shapes 1:1 (`InviteResponse` incl.
  `email_sent`/`accept_url`, `InviteRow` incl. derived `status`, `AcceptInviteRequest/Response`,
  `PasswordResetConfirmRequest`, `UserDisableResponse`; `AdminUserRow` + `disabled_at`).

### C. Users admin page
- `web/src/routes/lq-ai/(app)/admin/users/+page.svelte` + `page-helpers.ts` +
  `__tests__/page-helpers.test.ts` (vitest; helpers: status labelling incl. disabled/pending-
  deletion/operator, invite-status labels, filter query building, date formatting, client-side
  validation).
- Copy the per-page `onMount` admin guard (audit-log precedent) — there is no admin layout guard.
- Sub-nav: add `Users` to `admin/+layout.svelte` `navLinks`.
- Invite modal (`ModalShell` + `FormControl`): email + role (admin/member/viewer); on 201 with
  `accept_url` present (SMTP off) show it copy-to-clipboard with a "hand this to the user
  out-of-band; single-use, expires {expires_at}" note; 409 → inline error (user or pending invite
  exists). Resend/revoke on pending rows; accepted/revoked/expired rows badge-labelled.
- Users table: role select (409 last-admin handling lifted from `DevRoleManagementCard`),
  disable/enable with confirm step, self + operator rows action-locked (D6).

### D. Unauth pages + login link
- `web/src/routes/lq-ai/accept-invite/+page.svelte`, `web/src/routes/lq-ai/reset-password/
  +page.svelte`; add both literal paths to `isAuthExempt()` in `web/src/routes/lq-ai/+layout.svelte`.
- Token read via `$page.url.searchParams` on mount; missing/empty token → immediate invalid-link
  state client-side (no request fired). The uniform backend 400 message surfaces via
  `LQAIApiError.message` as-is. No own `DualBrandingFooter` (the exempt-route layout renders one;
  `change-password` precedent — do NOT copy login's duplicate).
- Login page: "Forgot your password?" link → `/lq-ai/reset-password`; hosted-aware hint copy (D8:
  `hosted` → "This workspace hasn't been claimed yet — check your welcome email or use Forgot your
  password?"; else the existing grep hint).
- Never log/store tokens client-side; pages carry no outbound links (referrer hygiene; tokens are
  single-use + TTL'd server-side).

### E. Fence gating (audit-driven)
- Audit every `/admin/*` page's API calls against the fence table (aliases×5 / provider-keys×4 /
  `GET /admin/config` / `PATCH tier-policy` / override-tier-floor = operator-only;
  `GET /admin/tier-policy` stays admin-readable).
- Expected outcome: `/admin/models` (alias CRUD) → operator-only (page guard `role==='operator'` +
  sub-nav link hidden for non-operators); `/admin/developer` — remove `DevRoleManagementCard` (D5),
  gate any card calling fenced endpoints; tier-policy UI (wherever it renders) stays visible
  read-only for admins with the PATCH affordance operator-only. The implementer documents the audit
  result in the PR (page → endpoints → verdict).

### F. Wizard
- `scripts/setup-tenant.sh` — D7 handover rewrite (SMTP-on curl + messaging / SMTP-off fallback);
  prompt + validate + write `FIRST_RUN_OPERATOR_EMAIL` (same email validation as `ADMIN_EMAIL`;
  manifest key `OPERATOR_EMAIL`; optional — empty ⇒ not written ⇒ self-host semantics).
- `.env.prod.example` — `FIRST_RUN_OPERATOR_EMAIL` entry (placeholder only) if 3a didn't add it.
- `api/tests/test_setup_tenant_wizard.py` — extend: SMTP-on renders no password-scrape in the
  handover path + emits the reset-request call; SMTP-off keeps the fallback; `OPERATOR_EMAIL`
  written/omitted; charset fence still applied to the new field. `shellcheck` + `bash -n` clean.

### G. Docs + records
- **ADR-F061 addendum**: D6 (operator rows visible+locked), D7 (handover mechanism + threat-model
  note), Q1 deferral (`_MUTATING_ROLES`/`MutatingUser` dead-code finding → SETUP-5), D1 (real link
  paths), D8 (`hosted` signal).
- `MILESTONES.md`: SETUP-3b ✓ entry; add SETUP-3c (onboarding checklist) to the ladder/backlog.
- `HANDOFF.md` banner: 3b done block + NEXT (SETUP-3c or SETUP-4a — maintainer's ladder order says
  4a next; 3c is UX polish that can ride later); memory update.

## Verification / DoD (ADR-F005 gate)

- **api**: full suite in the dev image (counts quoted); targeted: lifecycle_email URL tests,
  bootstrap hosted flag, wizard tests; `ruff check api scripts` + `ruff format --check` from repo
  ROOT + `mypy app` clean; shellcheck + `bash -n` on the wizard.
- **web**: `npm run check` (0 errors) + `CI=1 npx vitest run` counts; rebuild the `web` container
  before any live verification (pre-built bundle).
- **Live (dev stack, SMTP off)**: create invite via the Users page → `accept_url` shown → open it
  logged-out → set password → sign in as the new member; role change member→admin→member;
  disable → login 401 → enable; forgot-password request state renders uniform success; reset-confirm
  page verified with a token minted via container-exec (`issue_password_reset`); fence check:
  org-admin sees Users but not Models; operator sees both. Screenshots under
  `docs/fork/evidence/setup-3b/`.
- **Fresh-context adversarial review** incl. the mandatory security + simplification pass: no token
  logged/echoed anywhere new; anti-enumeration preserved in UI copy (request form never confirms
  existence); no `operator` ever offered as a role choice; guard-allowlist additions exact-match
  literals; dead `DevRoleManagementCard` fully removed (no orphan imports); no stray files.
- Squash-merge under the full gate; HANDOFF + memory updated.

## Delegation

One Sonnet 5 agent in an isolated worktree cut from post-#217 main (frontend-heavy, no
auth/crypto/migration work — the 3a security surfaces are consumed, not modified). Lead runs all
gates, the live verification, and the adversarial review.

## Risks / gotchas

- Web container serves a pre-built bundle — rebuild before verifying UI.
- `isAuthExempt` misses ⇒ token pages bounce to login (test the literal paths).
- Login page currently renders a duplicate footer — don't propagate that to new pages.
- CORS preflight: only POST/PATCH/DELETE (never PUT).
- The wizard handover curl runs on the tenant node against the public origin — must tolerate
  cold-start latency (reuse `deploy.sh`'s retrying-smoke pattern) and MUST NOT appear in the
  manifest/charset-fenced values.
- Untracked strays (`sample-documents/`, `api/tests/agents/scenarios/test_*_live.py`) belong to
  NO PR.
