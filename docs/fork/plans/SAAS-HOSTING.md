# SaaS hosting review — from single-tenant dev box to a hosted product

**Status: PLAN OF RECORD for the SAAS milestone (to be ratified by ADR-F058, proposed
2026-07-02) — §10 rows 1/2/9 are maintainer-decided; the remaining decisions close in their
named slices.**
Recon 2026-07-02: 5 codebase audits (file:line evidence) + 4 web-research sweeps (current prices),
then an adversarial verification pass (fact-check / completeness / attack-the-recommendation)
whose surviving findings are folded in below. Decisions marked **[MAINTAINER]** are yours;
everything else is my recommendation with the reasoning shown.

## 0. The question and the working interpretation

The ask: prepare the fork for hosting — companies set up an organisation account (tenant), an
admin account, then user accounts; "a proper SaaS in effect". Review how, where (cheap + secure),
and how the hosted version stays current while the product is still in active development.

**Interpretation — CORRECTED by maintainer (2026-07-02):** self-hosting from GitHub **remains a
supported mode**. Anyone may take the repo and run it as a single tenant on their own
infrastructure; that ability must not go away. The hosted multi-tenant offering is the
**market-awareness channel** — people don't know LQ.AI Fork exists; a hosted version where
companies can register a tenant and set up users is how they find out. Consequence: every hosted
convenience must stay *optional and pluggable* (generic SMTP not a hard Scaleway dependency;
any S3-compatible store; the compose stack keeps working out-of-the-box single-tenant), and the
public repo's self-host path is a product surface, not just a dev harness. Three delivery modes,
one codebase: (1) self-host from GitHub (single tenant), (2) operator-hosted dedicated stacks
(§3A — chosen), (3) a future shared multi-tenant deployment (§3B — recorded, trigger-gated).

## 1. A collision you must resolve first — the north star

`docs/fork/NORTH-STAR.md` §Keep-possible invariant **#4** (maintainer direction, 2026-06-11) says
verbatim: *"Deployment unit = one stack per client. Forward deployment means a dedicated instance
per client, which the current single-org model already fits. **Do not 'fix' the architecture
toward SaaS multi-tenancy; that would trade the model we want for one we don't.**"* The business
shape there is "revenue is forward deployment".

**Resolved (maintainer, 2026-07-02): the collision dissolves.** Self-hosting from GitHub is
retained (§0) and the chosen hosted architecture is one automated stack per tenant (§3A) — so
invariant #4 survives *intact*: the deployment unit stays "one stack per client" whether the
client runs it, we run it for them, or a forward-deployment engagement wires it into their
infrastructure. The hosted offering is an awareness/distribution channel layered on the same
model, not a replacement of it. **ADR-F058 "hosted SaaS charter"** (F057 is the highest F-number
taken) records this at SAAS-0 as an *addendum* to the north star, not a supersession: three
delivery modes, hosted-dedicated chosen, Option B recorded with its trigger — only a future
Option B build would supersede north-star #4 and ADR-F019 (whose pre-committed supersession
clause at F019:74-76 anticipates exactly that).

## 2. What the code says today (recon findings, verified file:line)

**Tenancy — none, by accepted design.** No organizations/tenant entity anywhere
(`organization_profile` is a singleton *content* row, partial unique index on `((true))`;
`teams_tenants`/`slack_workspaces` are integration records, not tenancy). Users carry no org FK;
authority is one `is_admin` boolean (`models/user.py:35`) that **conflates deployment-operator
powers (gateway provider keys, tier policy — `api/admin.py:270-635`) with people-admin powers**;
the 3-value `role` column (`user.py:40`) already enforces viewer read-only via
`get_mutating_user` (`dependencies.py:195-218`) and is the seam to extend. All ownership chains
key on `user_id`/`owner_id` only. The ROPA + AI-Act registers are deployment-global shared-read
(ADR-F019); the F021 `visible_filter()`/`can()` authz seam exists only in ADR text — zero code.
langgraph Store company tier is the literal global `("company",)` namespace
(`agents/memory_backend.py:127-146`) — CLAUDE.md's "(org_id, …)" claim is aspirational. S3 keys
are bare file UUIDs in one bucket (`file.py:36-40` reserves a `tenants/<id>/` prefix — see §3,
adopt it from day one). arq workers carry only entity IDs and re-derive identity from rows — org
propagation is nearly free once rows carry it.

**The biggest gap is not tenancy — it's user lifecycle.** There is **no user-creation endpoint at
all**: the only `User` insert in the codebase is the first-run bootstrap admin
(`admin_bootstrap.py:110`). No signup, no invite, no password reset, no email verification; SMTP
exists but is wired only to autonomous notifications. *This must be built under every option in
§3*, so it's on the common trunk.

**Auth core is strong; the exposure hardening is not.** Good: HS256 pinned + typ discriminator,
bcrypt 12 rounds, rotating refresh tokens, absolute+idle session timeouts, session cap, TOTP MFA
support, consistent cross-user-404. Bad (ranked, §6): **zero rate limiting anywhere**
(`passwords.py:15` even falsely claims edge rate-limiting exists); `/auth/refresh` bcrypt-scans
ALL users' sessions per request — an acknowledged CPU-DoS (`auth.py:301-307`); tokens in
`localStorage` (XSS-exfiltratable); no HSTS/CSP/security headers; `request.client` trusted with
no proxy-header handling; unauthenticated `/metrics`; `/api/v1/internal/*` service endpoints
behind one static never-rotated shared secret; WOPI bearer tokens (10 h TTL) in URL query
strings; first-run admin password printed to logs.

**Runtime footprint.** 9 always-on services; api/workers share one 6.64 GB image with bge-base +
MiniLM reranker baked in (296 MB); gateway 995 MB (spaCy); Collabora 1.45 GB. Idle RAM ≈ 1.1 GB
(measured); concurrent peak (agent run + ingest + editor session) ≈ 5.5–7 GB — **a component-
summed estimate, not a measurement** (the dev box has only 6.3 GB total). **Sizing: 8 GB
workable-with-care, 16 GB comfortable, 4 vCPU; disk 40 GB min** (images ~10 GB + rebuild headroom
+ volumes). Caveats: the worker `mem_limit`s (ingest 3g / arq 2.5g) live only on the unmerged
`fork/f2-embedding-oom-hardening` branch, and they cap **only the two workers** — api, Postgres,
gateway, Collabora are uncapped (matters for node packing, §5).

**Deploy readiness — a real pipeline exists but is dormant and mispointed.** `release.yml`
builds/pushes api+gateway+web to GHCR with SLSA provenance + SBOM + cosign, but triggers only on
`v*.*.*` tag pushes (plus a manual dry-run dispatch) — the fork has minted zero tags — and pushes
to `ghcr.io/legalquants`, upstream's org, which our token cannot write. CI builds no images.
Compose builds everything from source; nothing references registry images. **Trap: migration
0032 resolves `/skills` via parent-dir walking and the api image does not COPY `skills/`** — a
registry-pulled image against a fresh DB fails at 0032 unless skills ship in the image. The web
bundle bakes `PUBLIC_LQ_AI_API_BASE_URL` at build time (prod default `/api/v1` relative =
same-origin, CORS off — good), and web's nginx has no `/api` location, so the front proxy must
route `/api/v1 → api:8000`. The live `gateway.yaml` exists only in a named volume (config drift
invisible to git). Migrations auto-run in the api entrypoint under an advisory lock; workers skip
and wait on api health — sane, keep it, but add a dedicated pre-`up` migrate step (§5).
`SECURITY.md` still routes vulnerability reports to **upstream** (security@legalquants.com) —
must be rewritten for the fork before hosting.

**SSE/streaming.** Agent-run stream sends `": ping"` after 15 s silence (`stream.py:86`) — safe
behind any proxy. The legacy chat stream has **no heartbeat** — fix (one-line ping reuse) or
accept it dies behind read-timeout proxies. Collabora needs a long-lived WebSocket at `/cool/`
(36000 s read timeout in web's nginx) — the front proxy must match.

## 3. The architecture decision: how "tenant" is implemented

Two credible shapes. (Schema-per-tenant is dead in 2025-26 practice — alembic fan-out pain,
catalog bloat; DB-per-tenant dies on connection-pool math. Both researched and discarded.)

### Option A — one stack per tenant, behind a thin control plane (CHOSEN — maintainer, 2026-07-02)

Each customer org = one compose stack (own Postgres, own object-storage bucket, own gateway, own
Collabora) on dedicated or packed Hetzner nodes, `acme.yourdomain.com` per tenant, provisioned by
automation. **v1 provisioning is operator-triggered (sales-led), not self-serve**: a company
"sets up their organisation's account" by signing an order form; the control plane stamps the
stack (<30 min on a fresh node; ~minutes on a pre-pulled packed node) and creates their admin,
who then invites their users. A public self-serve signup surface is a later slice if ever wanted
— B2B legal doesn't impulse-buy. The in-app changes reduce to the **common trunk** (§4):
`organization_profile` singleton, deployment-global registers, `("company",)` Store namespace —
all *correct by construction* per-stack, zero refactor.

- **For:** strongest isolation story sellable to legal buyers — **on dedicated nodes** (physical
  separation, per-tenant DB/keys/bucket, contractual data destruction = destroy the stack — the
  named driver for per-tenant DBs in practice); preserves north-star #4 verbatim; fastest path to
  first customer; blast radius of the young security surface is one tenant (dedicated nodes
  only); documented real-world pattern for low-tenant-count high-trust B2B (operators run 300+
  such instances; legal-tech guidance names exactly this profile).
- **Against:** infra cost scales linearly (§5: ~€10–19/tenant/mo — trivial against legal ACV);
  update fan-out (mitigated: the SHA-pinned deploy loops a tenant inventory, **and version skew
  is bounded at N-1 deploy cycles — no indefinite per-tenant pinning**, else contract migrations
  block fleet-wide and the A→B path rots); config drift is the named failure mode absent
  automation — the control plane IS the discipline; no instant trial; no cross-tenant analytics
  without a separate telemetry plane.
- **Packing precondition:** stacks share a node ONLY once (a) the prod compose publishes **no
  host ports** (Caddy joins each stack's docker network; today's fixed `127.0.0.1:<port>`
  bindings collide across stacks) and (b) every heavy service (api, Postgres, gateway, Collabora
  — not just the two workers) carries a `mem_limit` summing under node RAM, else one tenant's
  runaway process OOM-kills another tenant's Postgres. Until then: dedicated nodes, or max 2
  stacks per CX53.
- **Control plane v1 is deliberately dumb:** a **private** repo with a tenant inventory
  (`tenants.yaml`: subdomain, node, image SHA, secrets ref), a provision script (compose project
  + DNS + secrets + seeded admin), and the deploy workflow fanning over it. This *is* a minimal
  bespoke Dokploy — that's the point: ~200 lines we own vs a general panel we must operate,
  secure, and update. Recorded checkpoint: **at ~5 tenants, prototype Dokploy's API** (per-
  customer stamping is feasible-by-API, not proven practice) and switch if the panel pays.
- **BYOK falls out for free:** each tenant has its *own* gateway with Fernet-encrypted provider
  keys, so a customer can bring their own LLM API key today — no Option-B machinery needed. For
  BYOK tenants our LLM-spend exposure drops to ~zero and the model provider moves off our
  subprocessor list (their key, their provider relationship); the per-tenant spend ceiling (§7)
  then protects *them*, not us.

**What this looks like in practice** — one customer: one ~€16/mo Hetzner node running their
complete private copy (own DB, own document store, own gateway/keys, own Collabora) at
`acme.<domain>`; sales-led signup (order form → `provision acme` → live in <30 min → their admin
invited by email, invites their lawyers); offboarding = export + destroy the stack, provably
gone. Ten customers: ~10 small nodes (or ~5 once packing preconditions hold) + staging,
~€160–200/mo infra total; one `tenants.yaml` drives provision and deploys; a release rolls
staging → pilot tenant → rest in one evening (~1 min downtime each), everyone within one version
(the N-1 skew rule); nightly per-tenant encrypted backups with dead-man alerts, one status page,
per-tenant usage reports feeding invoices. Ten identical flats under one set of scripts — the
thing to prevent is drift, and the inventory + skew rule is the prevention.

### Option B — shared-schema multi-tenancy (org_id + RLS backstop)

One deployment for all tenants: `organizations` + `memberships` (+ invitations) tables, `org_id`
denormalized onto hot roots (projects, files, chats, agent_threads/runs, tabular_executions,
knowledge_bases, registers, audit), request-scoped org context at `dependencies.py`, Store
namespaces prefixed `(org_id, …)`, S3 keys `tenants/<org_id>/…`, per-org practice-area rows
provisioned at tenant creation, per-org gateway quotas. Defense-in-depth: **Postgres RLS as
backstop** — two-role split (alembic as owner; app as non-owner role, no BYPASSRLS), `FORCE ROW
LEVEL SECURITY`, `set_config('app.org_id', :id, true)` transaction-scoped as the first statement
(session-scoped `SET` leaks across pooled connections — the classic isolation break), same
pattern inside every arq job. 2025-26 consensus default for real SaaS; one stack to run.

- **For:** marginal tenant cost ≈ 0; single update; instant self-serve signup; cross-tenant ops.
- **Against:** the largest structural milestone since the fork began — from the seam audit:
  organizations/memberships + JWT/org context (L), ownership chains + authz seam (M+M — do F021
  Phase 1 *first* so the flip is one predicate per resource kind), registers re-scoped incl. the
  ROPA practice_area backfill that never happened (L), Store namespace migration + `("company",)`
  leak fix (M), practice-area per-org provisioning (M), RLS done correctly (M, high skill floor),
  per-org gateway quotas (M). Weeks of slices competing with module work (AIC-3…), against zero
  paying customers today. Supersedes ADR-F019; kills north-star #4.

### The A→B path, honestly priced

The **code** delta of B is the ladder above and carries over from the trunk unchanged. The
**data** delta does not: firing the trigger at 20–30 live tenants means merging 20–30 live
Postgres databases, Stores, buckets and gateway configs. Row IDs are safe (every PK is a UUID),
but collisions are guaranteed at: `users.email` (globally-unique CITEXT — the same external
counsel in two stacks is an identity-reconciliation problem), `practice_areas.key` (every stack
seeds the same keys — collides on every merged tenant, with FK rewrites), ROPA vocab
`lower(name)` unique indexes (semantic dedup), the `organization_profile` `((true))` singleton,
plus Store/checkpointer namespace rewrites and S3 re-keying. **Two honest shapes:** (a) Option-A
tenants never migrate — B serves new/self-serve tenants only, two production shapes coexist
indefinitely; or (b) a priced tenant-merge program (per-tenant dump→transform→load with dedup +
freeze windows) added to the Option-B estimate. **ADR-F058 records shape (a) — coexist** —
revisitable at trigger time. Mitigations from day one keep the merge option open cheaply: write
S3 keys under `tenants/<stack-id>/…` now (the prefix is already reserved in `file.py`) and keep
fleet version skew ≤ N-1.

### Recommendation — DECIDED (maintainer, 2026-07-02): start small with Option A

Common trunk first (§4, needed under both), then Option A to revenue. **Option B stays fully
recorded — it is a when, not an if**: the maintainer explicitly anticipates smaller customers who
"simply want to sign up, pay a base subscription, stick their API key in and use the tool". That
self-serve motion IS the Option-B trigger (alongside >20–30 active tenants or per-tenant ops
eating development time). Note the decomposition: the *API-key* half of that wish works under A
today (BYOK per stack, §3A); what genuinely needs B is the *instant sign-up at near-zero marginal
cost* half. Record the trigger AND the A→B shape (above) in ADR-F058 so B arrives as a scheduled
evolution with a priced data plan, not a rewrite under pressure — and keep §3B's ladder + the
merge program in this document as B's standing plan of record.

## 4. The common trunk (needed under every option)

1. **User lifecycle:** admin-invites-user flow (invitation table: org-scoped email + single-use
   token + ~7-day expiry), email verification, password reset, forced first-login password
   change; SMTP wiring for auth mails (provider §7). Invite-only within a tenant — no open
   signup. New auth endpoints **inherit the §6 rate-limit buckets + uniform-response
   anti-enumeration** (reset/invite must not reveal whether an email exists). Model memberships
   WorkOS-style (users/orgs/memberships) even under Option A — the Neon retrofit lesson is
   "ship team accounts from day one".
2. **Admin split:** `platform_admin` (operator: gateway keys, tier policy, usage, audit-all) vs
   `org_admin` (customer: users, org profile, practice-area toggles). Under Option A this is a
   *security* requirement, not cosmetics: a customer admin must never reach the gateway
   provider-key endpoints of their own stack. The enforced `role` column + F021's
   `get_mutating_user` gate are the starting seam.
3. **Security hardening gate** (§6) and **deploy pipeline** (§5).

## 5. Where it lives + how it updates

### Hosting (cheap + secure + EU): Hetzner, Falkenstein/Nuremberg

Customers are EU in-house legal teams handling privileged material — EU-owned infrastructure is a
sales asset (US PaaS at this size: Fly ~$170, Render $225, Railway ~$320/mo — 4–20× the cost
*and* a worse residency story). Prices fetched 2026-07-02 (Hetzner re-priced 2026-06-15):

| Item | Plan | €/mo |
|---|---|---|
| Prod node (full 9-service stack) | CX43 — 8 vCPU / 16 GB / 160 GB | 15.99 |
| Staging node | CX43 (same as prod), **or** CX33 (4/8, €8.49) running a *defined* reduced profile (no Collabora, ingest concurrency 1) — an 8 GB node running the full stack will flake on OOM during verification runs | 8.49–15.99 |
| Snapshots/backups (20 % of nodes) | — | ~5–6.40 |
| Object storage (replaces self-hosted MinIO, §8) | 1 TB incl. storage+egress | 5.99 |
| **Base total** | | **~€36–45** |
| Per additional tenant (Option A) | CX43 dedicated (≈€19 with backups) or 2 packed on a CX53 (16/32, €29.49) once the packing preconditions (§3A) hold | **~€10–19** |

- **Backend and frontend live together**: one node per stack, Caddy (or Traefik) as the only
  public listener — TLS via a **wildcard cert (DNS-01, Hetzner DNS plugin)**, not per-host
  HTTP-01: per-tenant hostnames in Certificate Transparency logs would publish the customer list,
  which legal buyers will mind. Routes: `/api/v1/* → api:8000` **except `/api/v1/internal/*`
  denied at the edge** (§6), `/browser|/hosting|/cool → web:8080` (web's nginx already proxies
  Collabora; `/cool/` needs WS upgrade + long read timeout), rest `→ web:8080`;
  `client_max_body_size ≥ 100 MB`. Prod compose publishes **no host ports** (Caddy joins the
  stack's docker network). Hetzner firewall allows 80/443 only; SSH key-only, ideally via
  WireGuard/Tailscale (the `deploy/caddy-tailscale/` recipe is prior art — note its
  `/lq-ai-api/v1` prefix mismatches the web bundle default). **No Cloudflare proxy in front**:
  its 120 s proxy-read-timeout (Enterprise-only to raise) kills silent SSE; DNS-only + Caddy TLS
  is simpler. (Give the legacy chat stream the agent stream's 15 s ping.)
- **Postgres: self-hosted pgvector container** (as today) + nightly `pg_dump -Fc`, **encrypted
  client-side (age/GPG, operator-held key)**, to object storage + node snapshots; per-tenant
  buckets/credentials provisioned by the control plane (one shared storage key across stacks
  would be a cross-tenant blast radius that contradicts §3A's isolation story). **Enable bucket
  versioning + a lifecycle-protected second copy for customer files** — the object store holds
  every tenant's uploaded contracts; pg_dump alone doesn't cover them. State RPO/RTO (DB ≤24 h →
  hours; files ≈0 via versioning); backup jobs report to a dead-man switch (healthchecks.io
  style); **restore drills are part of the gate** — into a throwaway container, never staging.
  Managed-PG fallback if ever needed: Scaleway (pgvector 0.8 on PG16, from ~€11/mo).
- **Staging data hygiene:** synthetic/sample data only (`sample-documents/` packs exist);
  prod→staging copies prohibited, including in restore drills.
- **Email:** Scaleway TEM (fully-EU stack, free 300/day) or Brevo; dedicated sending subdomain
  with SPF/DKIM/DMARC provisioned alongside DNS, deliverability smoke test in the slice proof.
  Postmark/Resend have better DX but put "US data storage" in the subprocessor list.
- **Monitoring v1:** Uptime Kuma (public status page at `status.<domain>`) + Sentry (EU) +
  backup dead-man checks; Loki/Grafana only when it earns its keep. `/metrics` internal-only.

### Update pipeline (the product is still in active development)

Researched consensus + this repo's shape → **"GHA builds, SSH deploys, SHA pins, backup-then-
migrate, tag promotes."** Watchtower is archived (2025-12) and production-discouraged — no
registry polling. Coolify/Dokploy are deferred per the §3A checkpoint.

1. **CI on every push to `main`:** existing test gates + path-filtered image builds → GHCR
   `ghcr.io/sarturko-maker/...` (fix `release.yml`'s hardcoded `legalquants`), tags `:<git-sha>`
   (immutable) + `:main`, buildx `type=gha` cache. Keep the tag-triggered SLSA/SBOM/cosign
   release flow. Add **Trivy image scanning (scheduled) + Dependabot** and a monthly
   rebuild-and-redeploy rhythm so base-image CVEs don't sit for quarters.
2. **Prod compose file** (new, small): same topology, `image: ghcr.io/...:${IMAGE_TAG}` instead
   of `build:`, no host-port publishing, full per-service `mem_limit`s. **Ship `skills/` in the
   api image** (`COPY skills/ /skills`) — fixes the 0032 fresh-DB trap, removes the bind mount.
3. **Staging auto-deploy** (on main, `environment: staging`): SSH → `deploy.sh <sha>`:
   `compose pull` → `compose run --rm api alembic upgrade head` (dedicated migrate step; the
   advisory-locked entrypoint stays as belt-and-braces) → `compose up -d --wait` → smoke curl.
4. **Prod promote:** git tag `v*` (or `workflow_dispatch` with a SHA input) + GitHub Environment
   required-approval. Same script prefixed by the encrypted `pg_dump` upload. **Rollback =
   redeploy previous SHA; schema is roll-forward-only** — so from the first real tenant on:
   expand-contract discipline + Squawk lint in CI + a `db-migration-ok` PR label for destructive
   migrations, **and contract migrations gate on "all tenants ≥ expand version" tracked in
   `tenants.yaml`** (the N-1 skew bound, §3A). Deploy windows: ~30–60 s downtime is acceptable
   now (deploy when no runs are live — the run-lease/sweeper handles orphans); docker-rollout +
   healthchecks for api/web later. Under Option A the same job loops the tenant inventory
   (staging → ring of friendlies → rest, all within one skew window).
5. **Secrets:** runtime secrets ONLY server-side (root-owned per-stack `.env` + the gateway's
   Fernet-encrypted provider keys) — the public repo never carries them (the `.env.bak` incident
   is the standing lesson); GitHub Environment secrets hold just SSH key/host + registry token.
   The live `gateway.yaml` (named volume) gets a declared home: template in the private
   control-plane repo, applied by the provision script — config drift visible again.
6. **Security-fix discipline for a public repo:** rewrite `SECURITY.md` for the fork (it still
   routes reports to security@legalquants.com — upstream); use GitHub private advisories;
   patch-then-deploy-then-push (or deploy staging+prod in the same run that publishes the fix) —
   public `main` is also the attacker's changelog. This document itself is a vuln map: fine
   (the absences are code-visible in a public repo anyway), but its §6 list must be verified
   fixed before exposure — treat it as the pen-test checklist it accidentally is.
7. **Dev flow unchanged:** local compose stays the dev harness; slices merge under the ADR-F005
   gate as today; staging becomes the live-verification surface for slices (synthetic data only).

## 6. Security gate — blockers before ANY public exposure (ranked)

The app was explicitly designed "never externally exposed"; this is the delta, verified in code:

1. **Rate limiting** (none exists): per-IP + per-account Redis token buckets on `/auth/login`,
   `/auth/refresh`, `/auth/mfa/verify` (6-digit TOTP, currently unlimited tries), password
   change — and later the SAAS-4 invite/reset/verify endpoints; account lockout/backoff.
   (`cache.py:3` even planned this.)
2. **`/auth/refresh` global bcrypt scan** — the known CPU-DoS: land the deterministic HMAC index
   column (designed when the session cap shipped, PR #47).
3. **Edge-deny `/api/v1/internal/*`** — the service-to-service endpoints (skills, org-profile
   for the gateway) sit on the public router behind ONE static, never-rotated shared secret
   (`internal.py:65-99`); the gateway reaches api over the compose network, so a one-line Caddy
   deny costs nothing. Add gateway-key rotation to ops.
4. **WOPI surface:** the editor-session JWT rides as a URL query param (protocol design,
   `wopi.py:19-24`) with a **10-hour TTL** (`config.py:430-436`) — scrub `access_token` from
   Caddy/nginx access-log formats, shorten the hosted TTL (sessions re-mint cheaply), evaluate
   enabling WOPI proof-key validation (no `X-WOPI-Proof` handling exists), lock the Collabora
   container's outbound network to the WOPI host, and update the CODE image on the app cadence.
5. **Token storage:** move access/refresh out of `localStorage` → HttpOnly+Secure+SameSite
   cookies (same-origin serving makes this clean; brings a CSRF-token requirement). At minimum
   the 7-day refresh token must leave JS-readable storage.
6. **Security headers:** HSTS, real CSP (script/style — nginx.conf calls it "future hardening";
   the future is now), Referrer-Policy, Permissions-Policy — at the Caddy layer so it covers
   api + web uniformly.
7. **Trusted-proxy handling:** uvicorn `--proxy-headers` + forwarded-allow-ips;
   `_client_metadata` (`auth.py:240-252`) honours X-Forwarded-For from the trusted proxy only —
   otherwise every audit/session row records the proxy IP.
8. **`/metrics` off the public origin** (observability.py:199-204 registers it with no auth).
9. **Boot assertion:** refuse to start non-dev with `jwt_secret` default
   (`config.py:290` ships `"dev-jwt-secret-change-me"`).
10. **Uploads:** server-side magic-byte sniffing (client MIME trusted today, `files.py:265`),
    per-user/org storage quota + max-file-count (DoS-by-upload).
11. **Misc:** `chat_receipts.py:103` 403→404 alignment; first-run admin password out of logs;
    TOTP mandatory for admin roles (`mfa_mandatory` exists, `config.py:365`); Collabora admin
    surfaces stay 404'd (already done).

Standing invariants that already help: gateway is the only key-holder and only egress; agent
tools fetch no URLs and spawn no subprocesses; loopback-only compose bindings; parameterized SQL;
audit carries counts/types/IDs. **Independent security review / pen test before the first paying
tenant** — this list is the self-assessment, not the certificate.

## 7. Operating duties — GDPR, spend, incidents, and the product's own AI Act posture

- **Model routing is the biggest data exposure.** The live gateway config includes MiniMax
  (api.minimax.io) and DeepSeek (api.deepseek.com) — PRC-affiliated processors; the dev default
  is `smart → deepseek-v4-flash`. Fine for dev; **fence both from any tenant traffic** (the
  gateway tier policy is the enforcement point — it exists for exactly this). EU-resident
  inference mid-2026: Claude via **AWS Bedrock EU** cross-region (Frankfurt/Ireland/Paris/
  Stockholm — Anthropic's first-party API still has *no* EU geo), **Azure OpenAI EU Data Zone**,
  **Mistral La Plateforme** (EU by default; ZDR on Scale plan), sovereign fallbacks (OVH AI
  Endpoints, Scaleway, IONOS). OpenAI EU residency exists (new projects, ZDR amendment, +10 % on
  new models). The bar set by Harvey/Legora/Robin AI trust pages: named providers + contractual
  ZDR + no-training + EU processing + public subprocessor list. Our per-provider data-tier
  system is the differentiator — surface it. **[MAINTAINER]** Decision 3: default EU model menu
  (DeepSeek cannot stay the hosted default).
- **Per-tenant spend ceiling (trunk, not Option-B luxury).** All four brakes are per-RUN
  (`budget.py`); nothing stops a tenant — or one compromised account — starting many runs and
  burning thousands in LLM spend. Under Option A each tenant has its own gateway: enforce a
  **monthly token/EUR ceiling at the gateway** with an 80 % alert. This is also the billing
  meter (`agent_runs.total_tokens`/`cost_usd` already persist).
- **DPA + subprocessor list** (Art. 28(3) set: instructions-only processing, confidentiality,
  Art. 32 measures, subprocessor authorisation + objection, flow-down, DSR/breach assistance,
  deletion-or-return, audit rights). Subprocessors v1: Hetzner (DE), model providers per above,
  Scaleway TEM, Sentry (EU). Per-tenant export + deletion (Option A: destroy-the-stack is the
  clean answer; the GDPR delete cron already exists in-app). **Operator-access policy** (one
  paragraph, questionnaires ask verbatim): named person, access only on customer request or
  incident, host logins logged, disclosed in the DPA Art. 32 annex.
- **Incident response + breach notification:** a one-page IR runbook — severity levels, evidence
  preservation (audit rows, session tables), a 24 h controller-notification commitment matching
  the DPA (their Art. 33 72 h clock starts on our notice), template email, paging path
  (Uptime Kuma → phone). Legal buyers' questionnaires ask for exactly this document.
- **The product's own EU AI Act posture — dogfood the verdict engine.** We ship an EU-AI-Act
  compliance module; the first demo invites "what is your own classification?" Record a
  self-assessment (in-house legal assistance is plausibly not Annex III high-risk — put the
  reasoning on record via `app/aiact/classify`), implement Art. 50 transparency (in-product AI
  disclosure; AI-generated-content marking on exported work product), and a short GPAI flow-down
  note (provider obligations sit with Anthropic/Mistral etc.; we are the deployer/integrator via
  the gateway). Publish the result on the trust page.
- **Commercial pack (SAAS-0, before the first paying tenant):** MSA/ToS with liability cap +
  warranty disclaimer, AUP, SLA schedule (even "best-effort, 99.5 % target, business-hours
  support" + support@<domain> with a stated response window), order form, DPA as annex.
  **Liability framing for AI legal work product**: tool for qualified professionals, output is a
  draft requiring professional review, no attorney-client relationship — mirrored by in-product
  disclaimer surfaces on exports (redlines, verdicts, grids; the verdict engine's disclaimer is
  precedent). Decide on E&O/cyber insurance. **Billing v1**: manual invoicing from a named legal
  entity, B2B reverse-charge VAT; pricing must cover per-tenant LLM spend (flat fee + usage tier
  informed by the §7 meter); Stripe deferred behind the same trigger as Option B.
  **[MAINTAINER]** Decision 4: pricing model + which legal entity sells.

## 8. Licensing / commercial gate (before first paying tenant)

1. **PyMuPDF (AGPL-3.0)** — used only in `pipeline/parsers.py` behind the CI-guarded PdfReader
   boundary. Hosted network use = AGPL §13: the public Apache-2.0 repo substantially mitigates
   (deployed build must correspond to a published commit; add a prominent in-product source
   link), but Artifex enforces commercially. **[MAINTAINER]** Decision 5: Artifex license, or
   swap to pypdfium2 (Apache/BSD) — swap risk is the Citation Engine's byte-offset invariant
   (ADR-0006), re-validate. Already logged as COMM open question #1; hosting forces it.
2. **MinIO server (AGPL, unpinned `latest`, absent from NOTICES)** — dissolved for *our hosted*
   stacks: Hetzner Object Storage speaks S3, `S3_ENDPOINT_URL` is already injectable, MinIO
   leaves the hosted topology (−1 service RAM/attack surface). It stays in the default compose
   for dev **and for self-hosters** (§0 — that path remains supported): pin the image + add a
   NOTICES row (unmodified standalone AGPL service over the S3 API = the standard defensible
   posture for self-host users too).
3. **redis:7-alpine floating tag** — 7.4+ relicensed RSALv2/SSPLv1. Pin `7.2` by digest (or move
   to Valkey deliberately).
4. **Collabora CODE** — MPL fine; the prebuilt CODE binary is support-unwarranted for production
   (a warranty stance, not a license bar). Note an in-repo contradiction to reconcile: the
   compose comment still claims a home_mode 20-connection/10-doc cap while `NOTICES.md:92`
   records that cap as **removed in current CODE** — NOTICES (the provenance pass) is the newer
   record; verify against the pinned image and fix whichever is stale. ADR-F047 deferred the
   production posture: **[MAINTAINER]** Decision 6: CODE-per-tenant now, Collabora subscription
   when revenue justifies, self-build never (CVE burden).
5. **Rename before public release** — ADR-F001 obligation; "LQ.AI Oscar Edition" is memory-noted
   but un-ADR'd. Customer-facing hosting = public release: fold into ADR-F058.
6. Housekeeping: NOTICES rows for MinIO + the Xenova ms-marco ONNX model; per-skill license
   audit before shipping community skills to tenants.

## 9. Proposed slice ladder (SAAS-series, each ≤2–3 days, one PR)

**Trunk (both options):**
- **SAAS-0** — ADR-F058 hosted-SaaS charter: decisions 1–6, north-star reconciliation, rename,
  A/B trigger + A→B shape, commercial pack (MSA/ToS/SLA/AUP/DPA — lawyer-signed), AI-Act
  self-assessment, billing v1. Doc-only, but it is the gate for everything below.
- **SAAS-1** — pipeline: registry namespace fix, push-to-main `:sha` builds, prod compose file
  (no host ports, full mem_limits), `COPY skills/`, merge the mem_limits branch, Trivy +
  Dependabot, fork `SECURITY.md` + private-advisory discipline.
- **SAAS-2** — hardening pack: rate limits + refresh HMAC index + internal/* edge-deny + WOPI
  (log scrub, TTL, proof-key eval) + boot assertion + headers-at-proxy + trusted-proxy IPs +
  `/metrics` gate. (Tests: brute-force, refresh-flood, internal-deny.)
- **SAAS-3** — first hosted environment: Hetzner staging node, Caddy + wildcard DNS-01 cert,
  DNS + SPF/DKIM/DMARC, encrypted backups to object storage + dead-man check, public status
  page. **Proof: the staging URL serves a real agent run end-to-end; a restore drill passes.**
- **SAAS-4** — user lifecycle: invitations + verification + reset + SMTP (Scaleway TEM), forced
  password change, membership modeling, admin split (platform vs org); new endpoints inherit
  rate limits + anti-enumeration; deliverability smoke test.
- **SAAS-5** — cookie-based auth sessions + CSRF (retires localStorage tokens).
- **SAAS-6** — EU routing policy: tenant-tier provider fencing, EU default menu, per-tenant
  monthly spend ceiling at the gateway (+80 % alert), legacy-chat-stream ping; licensing actions
  (redis pin, MinIO→object storage, NOTICES rows, in-product source link).
**Fork point (Option A):**
- **SAAS-7A** — control plane v1 (private repo): tenant inventory, provision script (stack +
  DNS + secrets + per-tenant bucket/keys + seeded admin), deploy fan-out with the skew gate.
  **Proof: `provision acme` → working tenant at acme.<domain> in <30 min on a fresh node.**
- **SAAS-8A** — tenant ops: per-tenant encrypted backup/restore drill, destroy-tenant (data-
  destruction clause), per-tenant usage/cost report feeding invoices, onboarding runbook (org
  profile intake → House Brief, practice-area selection, first document, first witnessed run —
  the known "empty org profile degrades output" failure mode makes this non-optional).
**(Option B ladder — org/memberships → F021 seam → org_id backfill → Store/S3 → RLS → per-org
practice areas + quotas → tenant-merge program per §3 — planned only when its trigger fires.)**

Order of magnitude: trunk ≈ 3 weeks of slices; Option A fork ≈ 1–2 weeks (the restore/onboarding
ops in 8A are real work); Option B ≈ 4–6 weeks code + the data-merge program if shape (b).
Module development (AIC-3…) can interleave after SAAS-3.

## 10. Open decisions (consolidated)

| # | Decision | Status / recommendation |
|---|---|---|
| 1 | North-star #4 vs SaaS | **DECIDED 2026-07-02**: reconcile — self-host from GitHub retained; hosted = per-tenant stacks; ADR-F058 is an addendum, not a supersession |
| 2 | Tenancy architecture + A→B shape | **DECIDED 2026-07-02**: A now; B recorded as standing plan (full trigger set in ADR-F058: self-serve/BYOK motion, >20–30 tenants, or per-tenant ops eating dev time); A→B shape = **coexist** per ADR-F058 |
| 3 | Hosted default model menu (EU) | Bedrock-EU Claude + Mistral; fence MiniMax/DeepSeek from tenants; BYOK offered per stack |
| 4 | Pricing + selling entity | Flat fee + usage tier covering LLM spend (or lower flat + BYOK); manual invoicing v1 |
| 5 | PyMuPDF | Decide at SAAS-0; lean pypdfium2 swap if the citation invariant re-validates cheaply |
| 6 | Collabora posture | CODE-per-tenant now; subscription when revenue justifies |
| 7 | Panel vs plain SSH deploys | Plain SSH/GHA now; Dokploy-API prototype checkpoint at ~5 tenants |
| 8 | Hosting provider | Hetzner (CX43 nodes, ~€36–45 base, ~€10–19/tenant) |
| 9 | Delivery-mode interpretation (§0) | **DECIDED 2026-07-02**: three modes — self-host stays supported; hosted conveniences must remain optional/pluggable |

## Evidence

Recon: 9 agents (5 codebase audits, 4 web sweeps), then a 3-critic adversarial verification pass
(fact-check: ~40 claims checked, 3 corrections applied; completeness: 17 findings folded in;
adversarial: 11 findings folded in, incl. the A→B data-merge blocker). Outputs archived in the
session scratchpad. Prices dated 2026-07-02; re-quote before committing (Hetzner re-priced
2026-06-15).
