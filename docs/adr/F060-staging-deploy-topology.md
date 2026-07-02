# F060 — Staging deploy topology (custom Caddy edge, SSH-push pipeline, encrypted backups)

- Status: proposed
- Date: 2026-07-02
- Deciders: maintainer (Arturs) — drafted with the SAAS-3a slice
- Informed by: `docs/fork/plans/SAAS-HOSTING.md` §5 (where it lives + how it updates) and §6 (the
  security gate SAAS-2 closed); ADR-F058 (hosted-SaaS charter — Mode-2 stack-per-tenant); ADR-F059
  (the edge config + rate limits SAAS-2 shipped, which this puts on a public URL for the first time).

## Context

SAAS-1 published the fleet images and the prod compose; SAAS-2 hardened the auth surface and wrote
the edge config (`deploy/caddy/Caddyfile`) but shipped **no `caddy` service** — the prod compose
still publishes zero host ports and is "not internet-facing by construction." SAAS-3 turns "images
exist" into "a real agent run answers on a public staging URL, and a restore drill passes."

That work splits cleanly along a procurement line: config/scripts/runbook the agent can write and
**fully verify in-repo with no live box** (SAAS-3a, this slice) versus the infra only the maintainer
can procure — a domain, a Hetzner node, a DNS-provider token, an object-storage bucket — and the
joint first bring-up (SAAS-3b). A single PR cannot be "runnable + testable" (CLAUDE.md) if half of
it needs a credit card, so SAAS-3a ships the whole substrate, each artifact proven by a local
mechanism (compose config, image build + `caddy validate`, `shellcheck`, `actionlint`, a
restore-drill against a throwaway pgvector — exactly how SAAS-2's migration round-trip was proven),
and SAAS-3b is the thin bring-up PR that ticks the runbook with live evidence.

This ADR records the topology decisions that outlive the slice. Cookie auth (SAAS-5), the EU model
menu / PRC de-fencing (SAAS-6), and the multi-tenant control plane / `tenants.yaml` (SAAS-7A) are
explicitly out of scope: staging is **one** stack.

## Decisions

### D1 — Deploy trigger: SSH-push from a GitHub `environment: staging` job, roll-forward-only

Options: (a) a GHA job that SSHes to the node and runs `deploy.sh <sha>` — `compose pull` →
dedicated `compose run --rm api alembic upgrade head` → `compose up -d --wait` → smoke `curl`
(SAAS-HOSTING §5.3); (b) a pull-based agent on the node (Watchtower — **archived 2025-12**,
production-discouraged, polls the registry); (c) a PaaS control panel (Coolify/Dokploy — deferred at
the §3A checkpoint).

**Chosen: (a).** It matches §5 verbatim, adds no new always-on infra on the node, and keeps the
deploy an auditable, on-demand GitHub run gated by an Environment. The image tag is always a pinned
`:sha-<12>` the images pipeline published — **never `:main`** (a moving pointer breaks the "deploy =
one SHA" contract that rollback depends on). **Rollback = redeploy the previous SHA**; the schema is
**roll-forward-only** (expand-contract from the first real tenant — a later slice adds Squawk lint +
the N-1 skew gate; staging with no tenants needs neither yet).

### D2 — TLS: wildcard DNS-01 via a custom Caddy image — for staging too, not HTTP-01

Options: (a) wildcard cert via **DNS-01** (Hetzner DNS plugin) built into a custom Caddy image;
(b) per-host **HTTP-01** with stock `caddy:2` (simplest for a single host, no DNS token).

**Chosen: (a), and deliberately for staging as well as prod.** Two reasons. First, **CT-log
hygiene**: per-tenant hostnames in Certificate Transparency logs publish the customer list, which
legal buyers mind — a wildcard cert never names a tenant. That is a multi-tenant concern, but the
second reason forces it onto staging anyway: **staging is the prod dress-rehearsal.** If prod issues
via DNS-01 and staging via HTTP-01, the wildcard path stays untested until the first paying tenant —
exactly the "half of it can't run" the split exists to avoid. A single staging host *could* use
HTTP-01; we run DNS-01 so the one path we ship is the one prod uses. **Stock `caddy:2` has no DNS
modules compiled in** — DNS-01 therefore *requires* a custom `xcaddy` build (`caddy-dns/hetzner`,
Hetzner being the chosen host so the DNS is same-vendor). The Caddyfile carries a
`tls { dns hetzner {env.HETZNER_DNS_API_TOKEN} }` block; the token is a runtime env placeholder, so
`caddy validate` needs only the module present (built in the image), never a real token. No
Cloudflare proxy sits in front (its 120 s read timeout silently kills SSE agent streams — DNS-only +
Caddy TLS is the rule).

### D3 — Caddy image: Caddyfile **baked in**, published to GHCR, pinned by `${LQ_AI_IMAGE_TAG}`

The prod host has **no repo checkout** (prod-compose philosophy: `image:` refs from GHCR, never
`build:`), so the Caddyfile cannot be bind-mounted from the tree. Options: (a) bake the Caddyfile
into the custom image (`COPY Caddyfile /etc/caddy/Caddyfile`) and publish `lq-ai-caddy` from
`images.yml` alongside api/gateway/web; (b) provision the Caddyfile onto the node as a mounted file,
like `gateway.yaml`.

**Chosen: (a).** The edge config is code, not per-tenant state — baking it into a SHA-tagged image
versions it with everything else and keeps the node a pure `.env` + `compose pull`. The `caddy`
service refs `ghcr.io/…/lq-ai-caddy:${LQ_AI_IMAGE_TAG}`, so the edge moves atomically with the app
on every deploy (one SHA, one rollback). `images.yml` gains one matrix entry (context
`deploy/caddy`); the build's only cost is the `xcaddy` compile, cheap under `type=gha` cache.
(`gateway.yaml` stays mounted — it is genuinely runtime-mutable per-tenant state, D0.5; the Caddyfile
is not.) The `caddy` service is the **only** `ports:` block in the prod compose (80/443); it joins
the stack network and reverse-proxies `api:8000` / `web:8080` by name.

### D4 — Backups: `pg_dump -Fc | age` (asymmetric) → object storage; restore-drill into a throwaway DB

`scripts/backup.sh` streams `pg_dump -Fc` through **`age`** encryption to an object-storage key under
`tenants/<id>/backups/` (ADR-F058 day-one per-tenant prefix). **Asymmetric** (`age -R <recipients>`)
so the node holds **only the public recipient** — a compromised node cannot read its own history;
decryption needs the operator-held identity, offline. `age` over GPG: one small static binary, no
keyring ceremony. Retention 7 daily / 4 weekly; every run pings a **dead-man switch**
(healthchecks.io-style) so a *silent* backup failure is itself an alert. `scripts/restore-drill.sh`
pulls the latest dump, restores into a **throwaway** container, and asserts row counts / a smoke
query — **never** into staging (SAAS-HOSTING §5: restore drills into a throwaway container only), and
never from prod data into staging (prod→staging copies are prohibited; staging is synthetic-only).
**Object files are out of `pg_dump`'s scope** — uploaded contracts live in the object store; their
durability is **bucket versioning + a lifecycle-protected second copy** (provisioned in 3b), stated
here so nobody mistakes the DB dump for a full backup.

### D5 — Migration safety: a dedicated migrate step, belt-and-braces with the entrypoint lock

`deploy.sh` runs `compose run --rm api alembic upgrade head` as its **own** step between `pull` and
`up`, even though the api entrypoint already runs an advisory-locked `alembic upgrade head` on boot.
The explicit step makes a failed migration fail the **deploy** (before the new containers take
traffic) instead of surfacing as a crash-loop, and keeps the boot lock as the race guard for the
workers (`LQ_AI_SKIP_MIGRATIONS=1` on both). One-time note for the first prod boot: migration 0084
(SAAS-2) `DELETE`s `user_sessions`, forcing a single re-login — acceptable with no tenants yet;
recorded in the runbook.

### D6 — Secrets: server-side only; the public repo carries placeholders, never values

Runtime secrets live **only** server-side: a root-owned per-stack `.env.prod` on the node (from
`gen-secrets.sh` + procured provider keys) plus the gateway's Fernet-encrypted provider keys. The
GitHub `staging` Environment holds **only** the SSH key/host and a registry token — never app
secrets. `.env.prod.example` in the repo is **placeholders that look like placeholders** (the
`.env.bak` leak is the standing lesson); `scripts/gen-secrets.sh` emits fresh
`JWT_SECRET`/`LQ_AI_GATEWAY_KEY`/Fernet/Postgres values to **stdout only**, never to a file in the
tree. A guard test greps the committed `.env.prod.example` for any real-looking secret.

## Consequences

- **Staging exercises the exact prod edge** — custom Caddy image, DNS-01 wildcard, SSH-push,
  encrypted backup, restore-drill — so SAAS-3b is a thin, low-risk bring-up: procure infra, set the
  `staging` Environment secrets, run `deploy.sh`, capture the two proofs (a real agent turn on the
  public URL + a passed restore drill). The SAAS-2 hardening handoffs (pin `FORWARDED_ALLOW_IPS` to
  Caddy's container IP, promote the report-only CSP to enforced, rotate `LQ_AI_GATEWAY_KEY`, lock
  Collabora's egress to the WOPI host) land in 3b once the live IPs/reports exist.
- **The status page is its own tiny stack** (`deploy/status/`, Uptime Kuma at `status.<domain>`),
  *not* a service in the tenant compose — a tenant outage must not take down the page that reports
  it. It watches the public URL from outside.
- **Staging model stance is a 3b bring-up requirement, not a topology choice:** the gateway ships
  provider-agnostic, and a **public** URL must not default tenant traffic to a PRC provider
  (MiniMax/DeepSeek). The provisioned `gateway.yaml` seed defaults staging to a non-PRC model; the
  full EU routing menu / PRC de-fencing is SAAS-6. Called out in the runbook's pre-exposure checklist.
- **`deploy/helm/lq-ai`** (unmaintained) is superseded for hosting by this compose-based path; it
  stays only as a self-host reference, marked deprecated — the fork's hosting story is Mode-2 compose,
  not Kubernetes.
- **Cost of the extra image:** one more `xcaddy` build per push to `main`. Cheap under the existing
  `type=gha` cache and worth the atomic-SHA edge; revisit only if build minutes become real.
- **Reusable for prod:** `deploy.sh`/`backup.sh`/`restore-drill.sh` are host-generic; the prod
  promote path (tag `v*` + required-approval + a pre-migrate encrypted dump, SAAS-HOSTING §5.4) reuses
  them unchanged — a later slice adds only the approval gate and the tenant-inventory loop.
