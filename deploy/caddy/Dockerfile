# Custom Caddy edge image for the hosted tenant stack (SAAS-3, ADR-F060 D2/D3).
#
# WHY a custom image: stock caddy:2 ships with NO DNS provider modules, so it
# cannot answer an ACME DNS-01 challenge — and we issue the tenant's TLS cert via
# wildcard DNS-01 (ADR-F060 D2: a per-host HTTP-01 cert would name every tenant in
# the public Certificate Transparency logs). xcaddy compiles in a curated
# MULTI-PROVIDER set (SETUP-1, ADR-F060 amendment): the coupling is to where the
# tenant's DNS ZONE is hosted, not to the VPS vendor, so one fleet image carries
# every provider we support and the Caddyfile selects one per deployment via the
# parse-time {$LQ_AI_DNS_PROVIDER} placeholder.
#
# WHY the Caddyfile is BAKED IN (ADR-F060 D3): the prod host has no repo checkout
# to bind-mount from, and the edge config is code, not per-tenant runtime state.
# Baking it into a SHA-tagged image versions it with the app and keeps the node a
# pure `.env` + `compose pull`. .github/workflows/images.yml publishes this to
# GHCR as lq-ai-caddy:sha-<sha>; docker-compose.prod.yml pins it via
# LQ_AI_IMAGE_TAG so the edge rolls forward/back atomically with api/web/gateway.
#
# Build context is THIS directory (deploy/caddy) so `COPY Caddyfile` resolves:
#   docker build -t lq-ai-caddy deploy/caddy
# Validate the baked config (needs the compiled-in module — stock caddy can't):
#   docker run --rm lq-ai-caddy caddy validate --config /etc/caddy/Caddyfile

# Pin the builder to the same Caddy minor the runtime image resolves to, and pin
# every DNS provider to a released tag — reproducible builds, no floating deps.
# Adding a provider is one `--with` line (tag-pinned; caddy-dns/cloudflare is
# deliberately absent — it publishes no release tags; pin a commit SHA if a
# tenant ever needs it).
FROM caddy:2.11.4-builder AS build
RUN xcaddy build \
    --with github.com/caddy-dns/hetzner@v1.0.0 \
    --with github.com/caddy-dns/ionos@v1.2.0

FROM caddy:2.11.4
COPY --from=build /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
# Fail the BUILD on an invalid Caddyfile (enforces ADR-F060's "image build +
# caddy validate" proof in CI and locally — a syntax error can't ship silently
# to be discovered only at deploy). Needs the compiled-in DNS module; no runtime
# token required (validate does not attempt ACME).
RUN caddy validate --config /etc/caddy/Caddyfile
