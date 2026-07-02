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
endpoint. Wired once in the lifespan onto `app.state`, reached via a `get_rate_limiter` dependency
(DI; tests inject a fake backend through the same seam).

### D4 — Deny internal + /metrics at the edge (uniform 404), not in-app

Options: (a) app-level IP allowlist / new auth on the internal router; (b) `respond 404` at Caddy
for `/api/v1/internal/*` and `/metrics`.

**Chosen: (b).** The gateway reaches api over the compose network, never through the public edge, so
a one-line edge deny costs nothing and keeps the app router unchanged. Uniform **404** (never 403)
matches the app's own "no existence leak" authz rule. Trusted-proxy handling uses uvicorn's native
`--proxy-headers` (on by default in 0.32+) + `FORWARDED_ALLOW_IPS` (read natively) — no
`X-Forwarded-For` parsing in app code; the closed prod-compose network (zero host ports) makes
trusting compose peers acceptable until SAAS-3 pins Caddy's IP.

### D5 — WOPI token: shorten TTL + scrub logs at both edges; proof-key deferred

Options: (a) implement WOPI proof-key (`X-WOPI-Proof`) validation now; (b) shorten the TTL
(10h→1h), scrub `access_token` from both the Caddy and uvicorn access logs, and defer proof-key.

**Chosen: (b).** The token is already single-file-scoped and same-origin; the larger exposure was
the 10h life + log capture, both now closed. A boot assertion additionally refuses to start a
non-dev process on the default `jwt_secret` (a misconfigured signing secret is fatal — unlike a
missing runtime dependency, which the lifespan degrades on). Proof-key is deferred (finding below).

## Consequences

- One-time forced re-login on deploy (0084 clears `user_sessions`). Rotating `jwt_secret` now also
  invalidates all refresh verifiers (same blast radius as rotating the signing key) — acceptable.
- `/auth/refresh` is O(1); the per-user session cap (PR #47) stays as hygiene, not as the DoS fix.
- New env-tunable `Settings.rate_limit_*` fields (documented defaults); a Redis outage silently
  disables the brake (logged) rather than failing auth.
- The production edge lives in `deploy/caddy/Caddyfile` (validated with `caddy validate`); the caddy
  *service* + TLS + CSP-enforcement are SAAS-3. The report-only CSP must be promoted there.
- Dev stack unaffected: the dev compose already requires `JWT_SECRET` via `${JWT_SECRET:?}`, so the
  boot assertion is inert there; `FORWARDED_ALLOW_IPS` unset in dev → uvicorn's 127.0.0.1 default →
  byte-identical `request.client` behaviour.

### Deferred: WOPI proof-key (`X-WOPI-Proof`) validation — finding

Collabora Online (a WOPI client) signs every WOPI call with `X-WOPI-Proof` + `X-WOPI-ProofOld`
(RSA-SHA256 over `access_token` + WOPI URL + a timestamp). Validating them requires: (1) discovering
the client's public proof key(s) from Collabora's discovery XML (`/hosting/discovery`), (2)
reconstructing the expected proof string, (3) RSA-verifying against BOTH the current and old keys to
survive key rotation, and (4) a timestamp-freshness check to bar replay. Rough effort: ~150–250 LOC
plus a periodic discovery-key refresh and rotation handling; RSA verify is available via the already
present `cryptography`, but the discovery fetch/parse is new surface. Deferred because the token is
already scoped + short-lived + same-origin and the log-capture exposure is closed; proof-key is
defense-in-depth against a stolen-token replay from an untrusted network position — lower priority
than the shipped items, and its own slice with SAAS-3 (also: lock the Collabora container's outbound
network to the WOPI host).
