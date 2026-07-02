# deploy/caddy — production edge (Mode-2 hosted tenant stack)

The `Caddyfile` here is the public edge for a hosted per-tenant stack
(`docker-compose.prod.yml`). It is the **only** public listener: the prod
compose publishes zero host ports, so Caddy joins that compose network and
reverse-proxies to services by name (`api:8000`, `web:8080`).

This is separate from `deploy/caddy-tailscale/` (the dev/Tailscale edge, which
uses a different path prefix and no TLS). **Do not edit that one for hosting.**

## What it does (SAAS-HOSTING.md §6 security gate, ADR-F059)

- **(a)** `respond 404` for `/api/v1/internal/*` — the gateway↔backend service
  API never belongs on the public edge (uniform 404, never 403).
- **(b)** `respond 404` for `/metrics` — the api's Prometheus endpoint is
  unauthenticated; keep it off the public origin.
- **(c)** Security headers for api + web uniformly: HSTS (1y, includeSubDomains,
  **no preload** yet), `X-Content-Type-Options: nosniff`, `Referrer-Policy`,
  `Permissions-Policy`, `Content-Security-Policy: frame-ancestors 'self'`
  (Collabora self-frames — kept consistent with `web/nginx.conf`), plus a
  starter **CSP in report-only** mode (enforcement is SAAS-3 tuning).
- **(d)** Access-log scrub: the WOPI editor-session token rides as an
  `access_token` query param; the `query` log filter redacts it so it never
  lands in Caddy's access log. (The api scrubs its own uvicorn log too.)
- **(e)** SSE: `flush_interval -1` on the api proxy so agent/chat streams flush
  immediately.
- **(f)** Routing (SAAS-HOSTING.md §5): `/api/v1/*` → `api:8000` (after the
  denies); everything else → `web:8080` (whose nginx also proxies Collabora at
  `/browser`, `/hosting`, `/cool`, WebSocket upgrades included).
- **(g)** TLS via **wildcard DNS-01** (Hetzner DNS plugin) — SAAS-3, ADR-F060 D2.
  A per-host HTTP-01 cert would name every tenant in the public Certificate
  Transparency logs (the customer list); a wildcard cert never does. Stock
  `caddy:2` has no DNS modules, so the `tls { dns hetzner … }` block only runs in
  the custom image (`Dockerfile`, `caddy-dns/hetzner`).

## Configuration

Environment variables (set by the SAAS-3 deploy in the root-owned `.env.prod` on
the node, never committed):

| Var | Default | Meaning |
|---|---|---|
| `LQ_AI_PUBLIC_HOST` | `localhost` | The tenant hostname Caddy serves + provisions TLS for (a single host for staging; a wildcard `*.tenant.example.com` for prod). |
| `LQ_AI_ACME_EMAIL` | `ops@example.com` | ACME account email for cert-expiry notices. |
| `HETZNER_DNS_API_TOKEN` | — (required at run) | Hetzner DNS API token for the ACME DNS-01 challenge, scoped to the tenant's zone. A runtime env value only — `caddy validate` does not need it. |

The `localhost` default exists only so the file validates with no DNS/cert
dependency; a real deployment always sets `LQ_AI_PUBLIC_HOST`.

## Validate

The Caddyfile now carries a `tls { dns hetzner … }` block, so it validates **only
in the custom image** (stock `caddy:2` lacks the DNS module). Build the image
(context is `deploy/caddy` so `COPY Caddyfile` resolves) and validate the baked
config — no token needed:

```sh
docker build -t lq-ai-caddy deploy/caddy
docker run --rm lq-ai-caddy caddy validate --config /etc/caddy/Caddyfile
```

## Not here yet

- Promoting the report-only CSP to enforced, and CSP tuning — SAAS-3b, once the
  violation report from the live URL is observed.
- Pinning `FORWARDED_ALLOW_IPS` to Caddy's fixed container IP (drop the `*`
  default) — SAAS-3b, once the live stack's container IP is known.
