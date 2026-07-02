# F059 — Internet-exposure hardening pack (auth rate limits, HMAC refresh index, edge config)

- Status: proposed
- Date: 2026-07-02
- Deciders: maintainer (Arturs) — drafted with the SAAS-2 slice
- Informed by: `docs/fork/plans/SAAS-HOSTING.md` §6 (the ranked security gate); ADR-F058 (hosted
  SaaS charter — Mode-2 stack-per-tenant, the exposure this hardens for); PR #47 (the session cap
  that first named the deferred HMAC index).

## Context

The app was built "never externally exposed" (SAAS-HOSTING.md §6). SAAS-3 gives each tenant stack
a public URL, so the known internet-facing soft spots must close first. Verified in code: no rate
limiting anywhere on the auth surface (`/auth/login|refresh|mfa/verify|change-password`, and the
unauthenticated `/admin/bootstrap-status` probe); `/auth/refresh` scans EVERY active session and
bcrypt-compares each (a per-row salt is unindexable) — a CPU-DoS deferred since PR #47; the
service-to-service `/api/v1/internal/*` routes sit on the public router behind one static shared
secret; the WOPI editor token rides as an `access_token` URL query param with a 10-hour TTL and
lands in access logs; `/metrics` is unauthenticated; nothing trusts a proxy's `X-Forwarded-For`;
and a non-dev process will happily boot on the shipped default `jwt_secret`.

This slice hardens all of the above. Cookie-based token storage (§6 item 5) is SAAS-5; upload
sniffing/quotas (§6 item 10) and the §6 item 11 misc list are out of scope.

## Decisions

### D1 — Refresh-token verifier: deterministic HMAC index, key derived from `jwt_secret`

Options: (a) keep bcrypt, just add a cache/heuristic — leaves the scan and its DoS; (b) HMAC-SHA256
verifier in a unique-indexed column, key derived from `jwt_secret` with a domain-separation label;
(c) HMAC but provision a brand-new secret.

**Chosen: (b).** Refresh tokens are 32 bytes of CSPRNG output (~256 bits) — not brute-forceable
offline, so bcrypt's salt bought nothing here except the CPU-DoS. A deterministic HMAC is a
sufficient at-rest verifier and turns the lookup into ONE indexed equality query. The index key is
`HMAC-SHA256(jwt_secret, "lq-ai-refresh-token-index-v1")` (domain-separated from the JWT-signing use
of the same secret) → no new secret to provision or leak (rejecting (c)). bcrypt stays for
passwords, where the input is low-entropy and slowness is the point. `.with_for_update()` on the one
lookup query preserves the refresh-double-spend theft signal (Postgres READ COMMITTED re-evaluates
`revoked_at IS NULL` after the winner commits).

### D2 — Migrate by invalidating sessions, not a dual-path backfill

Options: (a) keep both columns, verify bcrypt-or-hmac and lazily rewrite on next refresh; (b) drop
bcrypt, add hmac NOT NULL, DELETE all existing sessions in the migration.

**Chosen: (b).** The HMAC is over the token plaintext, which was never stored — existing rows are
un-backfillable by construction. A dual-path keeps the exact bcrypt-scan DoS alive during the
transition. Deleting sessions costs one re-login; there are no production tenants yet and refresh
rotation already treats sessions as disposable. Migration 0084 documents it.

### D3 — Rate limiting: hand-rolled Redis fixed window, fail-open

Options: (a) add `slowapi`/`fastapi-limiter` — a new SBOM entry for ~40 lines of logic; (b)
hand-rolled fixed-window counters on the EXISTING redis client; and orthogonally fail-open vs
fail-closed on a Redis fault.

**Chosen: (b), fail-open.** No new dependency (CLAUDE.md SBOM posture). Counters use an atomic
`INCR` + first-hit `EXPIRE` inside one Lua script (`register_script`) so a crash between the two
commands can never leave a TTL-less key that jams a bucket forever. Per-IP and per-account buckets
are separate keys; a request passes both where both apply; the account key is a `sha256(id)[:16]`
tag so no email/user-id lands in Redis or logs; the 429 shape is uniform regardless of account
existence. **Fail-open** because Redis is in-stack and an outage must not lock legitimate users out
of authentication — availability beats the brake here; a Redis exception never 500s an auth
endpoint (a *non*-Redis exception still fails open but is logged at `exception` level, so a bug that
disables the brake is loud, not swallowed). Wired once in the lifespan onto `app.state`, reached via
a `get_rate_limiter` dependency (DI; tests inject a fake backend through the same seam).

**Accepted trade-off — account-lockout DoS.** The per-account login bucket keys on the *submitted*
email (so the 429 leaks no account-existence signal). A consequence: anyone who knows a victim's
email can spend that account's bucket (default 5/window) and 429 the victim's own logins while the
attacker sustains the trickle. This is the standard tension between anti-enumeration and
anti-lockout; we accept it for v1 because (i) the per-IP bucket already bounds a single attacker,
(ii) the limit is env-tunable (`RATE_LIMIT_LOGIN_ACCOUNT_PER_WINDOW` — raise it if lockouts bite),
and (iii) MFA and the audit trail cover the credential-stuffing case the account bucket targets. A
"count only failed logins against the account bucket" refinement (so a correct password is never
locked out) is a candidate follow-up.

### D4 — Deny internal + WOPI + /metrics at the edge (uniform 404), not in-app

Options: (a) app-level IP allowlist / new auth on the internal router; (b) `respond 404` at Caddy
for `/api/v1/internal/*`, `/api/v1/wopi/*` and `/metrics`.

**Chosen: (b).** Both the gateway (`/api/v1/internal/*`) AND the in-stack Collabora server
(`/api/v1/wopi/*`) reach api over the compose network, never through the public edge —
`collabora_wopi_host = http://api:8000` (matching the Collabora `aliasgroup1`), and the browser only
mints a token via `POST /files/{id}/editor-session` then talks to Collabora at `web:8080 /cool`. So a
one-line edge deny of each costs nothing and keeps the app router unchanged. Denying `/api/v1/wopi/*`
removes the *external* replay vector for a stolen editor-session token entirely (see D5). Uniform
**404** (never 403) matches the app's own "no existence leak" authz rule; named `path` matchers deny
both the bare prefix and the wildcard. Trusted-proxy handling uses uvicorn's native `--proxy-headers`
(on by default in 0.32+) + `FORWARDED_ALLOW_IPS` (read natively) — no `X-Forwarded-For` parsing in
app code; the closed prod-compose network (zero host ports) makes trusting compose peers acceptable
until SAAS-3 pins Caddy's IP.

### D5 — WOPI token: edge-deny + scrub logs (NOT a TTL cut); proof-key deferred

Options: (a) implement WOPI proof-key (`X-WOPI-Proof`) validation now; (b) shorten the token TTL
(10h→1h); (c) edge-deny the WOPI surface (D4) + scrub `access_token` from both the Caddy and uvicorn
access logs, keeping the 10h TTL.

**Chosen: (c).** The SAAS-2 recon proposed shortening the TTL, but the web editor has **no token-
renewal path** — the token is form-POSTed into the Collabora iframe once per `load()`
(`DocumentEditorPanel`), so a 1h TTL would silently 401 a long legal-editing session mid-work (saves
fail; the 30-min WOPI lock lapses and a second editor could grab the file). The token's actual
exposure is closed more completely and without that regression: (1) the browser side form-POSTs the
token, so it never enters a URL/history; (2) the uvicorn access-log scrub + Caddy log redaction close
the log-capture vector (the token *does* ride as a query param on the internal Collabora→api calls);
and (3) the D4 edge-deny means the WOPI endpoints aren't reachable from the public internet at all,
so a stolen token can't be replayed externally regardless of TTL. TTL stays 10h; a configurable short
TTL *with* client renewal is a follow-up (editor slice). A boot assertion additionally refuses to
start a non-dev process on the default `jwt_secret` (a misconfigured signing secret is fatal — unlike
a missing runtime dependency, which the lifespan degrades on). Proof-key is deferred (finding below).

## Consequences

- One-time forced re-login on deploy (0084 clears `user_sessions`). Rotating `jwt_secret` now also
  invalidates all refresh verifiers (same blast radius as rotating the signing key) — acceptable.
- `/auth/refresh` is O(1); the per-user session cap (PR #47) stays as hygiene, not as the DoS fix.
- New `Settings.rate_limit_*` fields (documented defaults). They are env-tunable, but the api service
  uses an explicit env allowlist (no `env_file`), so they are only overridable in a deployment once
  *forwarded* — `docker-compose.prod.yml` therefore forwards all nine as `${VAR:-default}`. A Redis
  outage silently disables the brake (logged) rather than failing auth.
- WOPI stays at a 10h TTL (D5); the exposure is closed by the D4 edge-deny + the log scrubs, not by a
  TTL cut (the editor has no token-renewal path). A short-TTL-with-renewal is a follow-up.
- The production edge lives in `deploy/caddy/Caddyfile` (validated with `caddy validate`); the caddy
  *service* + TLS + CSP-enforcement are SAAS-3. The report-only CSP must be promoted there.
- Dev stack: the boot assertion is inert (the dev compose sets `LQ_AI_DEV_MODE=true`, and also
  requires `JWT_SECRET` via `${JWT_SECRET:?}`); `FORWARDED_ALLOW_IPS` unset in dev → uvicorn's
  127.0.0.1 default → byte-identical `request.client`. The rate limiter IS wired in dev, but the dev
  compose sets generous login limits (1000/window) so repeated Cypress logins from one account/IP
  don't flake local e2e; unit tests inject their own limiter + fake backend, so they still assert
  enforcement.

### Deferred: WOPI proof-key (`X-WOPI-Proof`) validation — finding

Collabora Online (a WOPI client) signs every WOPI call with `X-WOPI-Proof` + `X-WOPI-ProofOld`
(RSA-SHA256 over `access_token` + WOPI URL + a timestamp). Validating them requires: (1) discovering
the client's public proof key(s) from Collabora's discovery XML (`/hosting/discovery`), (2)
reconstructing the expected proof string, (3) RSA-verifying against BOTH the current and old keys to
survive key rotation, and (4) a timestamp-freshness check to bar replay. Rough effort: ~150–250 LOC
plus a periodic discovery-key refresh and rotation handling; RSA verify is available via the already
present `cryptography`, but the discovery fetch/parse is new surface. Deferred because the WOPI
surface is now edge-denied (D4 — unreachable from the public internet), the token is single-file-
scoped + same-origin + never in a URL/history (browser form-POST), and the log-capture exposure is
closed; proof-key is defense-in-depth against a stolen-token replay from *inside* the stack network —
lower priority than the shipped items, and its own slice with SAAS-3 (also: lock the Collabora
container's outbound network to the WOPI host).
