# F070 — Network postures: private profile (restricted-egress) as a compose overlay

- Status: proposed
- Date: 2026-07-08
- Deciders: maintainer + agent lead
- Slice: P-1 (private profile — overlay + Caddyfile.private + env example + runbook §8)

## Context

The deployable artifact has, until now, exactly two network postures: (1) the public
VPS/hosted path — `docker-compose.prod.yml` + the public Caddy edge (ADR-F060), which
**hard-requires** a public hostname, an ACME DNS-01 token and an external S3-compatible
bucket (`${VAR:?}` parse-time requirements); and (3, future) the enterprise posture —
AKS/Entra/private endpoints (AZ-6, unplanned). Missing is posture (2): a **private /
restricted-egress VM** — locked-down environments where external integrations are
signoff-gated, there is no public URL, and object-storage procurement is itself an
external dependency to avoid. Posture 2 is also the natural stepping stone to posture 3,
because its egress surface is small and fully enumerable (runbook §8.4 is the canonical
inventory): deploy-time image/repo pulls (`ghcr.io`, Docker Hub, `github.com` — all
eliminable offline via image side-load / registry mirror / repo tarball); a ONE-TIME
first-ingest download of the Docling layout/TableFormer + EasyOCR models from
`huggingface.co` (~700 MB, persisted in the `ingest-hf-cache`/`ingest-easyocr-cache`
volumes; pre-seedable, or avoidable via `LQ_AI_DOCLING_ENABLED=false` at the cost of
structured extraction — only the fastembed embedder + reranker are baked at image build
per ADR-0008/ADR-F049); and, runtime steady-state, the Azure model endpoints (gateway-only,
Private-Link-able) plus — only when KV-1/ADR-F069 is enabled — `<vault>.vault.azure.net` +
link-local IMDS. Nothing else (no ACME, no DNS API, no external S3, no SMTP by default;
PRC fence unchanged).

The constraint that shapes the mechanism: the prod compose must stay the pinned,
byte-identical artifact the public path deploys (rollback = redeploy a SHA), and its
`:?`-required public vars interpolate at **parse time**, so any private posture must
satisfy them even though it never uses them.

## Considered Options

1. **Run the dev compose (`docker-compose.yml`) on the VM** — it already has MinIO and no
   public edge. Rejected: it `build:`s from a checkout instead of running the pinned GHCR
   images, carries dev defaults (dev mode, generous rate limits, host ports) — it is not
   the deployable artifact, so nothing proven on it certifies the shipped stack.
2. **A standalone full private compose file** (copy of prod, edited). Rejected: a second
   350-line copy of every service drifts silently from the prod file; every prod change
   would need a mirrored edit with no mechanism forcing it.
3. **An additive overlay** — NEW `docker-compose.private.yml` composed as
   `-f docker-compose.prod.yml -f docker-compose.private.yml` (CHOSEN). The prod file is
   untouched; the overlay expresses only the delta.

## Decision Outcome

Chosen: **option 3 — the overlay**, with these mechanics:

- **On-box MinIO**: the overlay adds a `minio` service (pinned dated release tag, named
  volume `miniodata`, dev-mirrored healthcheck, prod-style `mem_limit`, **no host
  ports**). The env file points the prod file's required `S3_*` vars at it
  (`http://minio:9000`, credentials = the MinIO root pair); `api`/`ingest-worker`/
  `arq-worker` gain `depends_on: minio: service_healthy` (compose merges long-form
  `depends_on` maps across files — verified in the merged `config` output). Bucket
  creation needs no init sidecar: the api's startup lifespan (`ensure_bucket()`,
  `api/app/storage.py`) creates it — the same mechanism the dev compose relies on.
- **Caddy internal TLS on loopback**: NEW `deploy/caddy/Caddyfile.private` mirrors the
  public Caddyfile stanza-for-stanza (log token-scrub, security headers, internal/WOPI/
  metrics denies, SSE flush, api/web routing) but serves `https://:8443` with
  `tls internal` (Caddy's local CA — zero certificate egress) and drops only the
  ACME/DNS-01/public-host parts. The overlay bind-mounts it over the image's baked-in
  `/etc/caddy/Caddyfile` (the custom image adds no ENTRYPOINT/CMD, so the caddy:2 base
  CMD `caddy run --config /etc/caddy/Caddyfile` picks the mount up unchanged) and
  replaces the port publishes with `ports: !override
  ["127.0.0.1:${LQ_AI_PRIVATE_PORT:-8443}:8443"]` — the `!override` tag is load-bearing:
  without it compose APPENDS ports and 80/443 would still publish.
- **Env-file placeholder mechanism for parse-time `:?` vars**: the prod file's public-only
  required vars (`LQ_AI_PUBLIC_HOST`, `LQ_AI_ACME_EMAIL`, `LQ_AI_DNS_API_TOKEN`) are
  satisfied by documented **inert placeholders** in `.env.private.example`
  (`private.invalid` etc.) — parse-time ballast only; the private Caddyfile references
  none of them and no ACME/DNS code path runs.
- **Origin = the tunnel origin**: `LQ_AI_PUBLIC_ORIGIN=127.0.0.1:8443`, so Collabora's
  `server_name`/`frame_ancestors` and the api's derived `PUBLIC_BASE_URL` match what the
  browser actually sees through `ssh -L 8443:127.0.0.1:8443`. Access is SSH tunnel (or
  Azure Bastion; Tailscale documented as an alternative that needs its own IT signoff —
  it is an external control plane). Collabora stays in by default; the reduced 8-GiB
  profile composes on top and drops it.
- `scripts/gen-secrets.sh --private` emits the MinIO root pair AND matching
  `S3_ACCESS_KEY`/`S3_SECRET_KEY` under a clearly-marked "private profile only" block
  (public-path invocations produce no S3 lines — see Consequences); runbook =
  `azure-vm-sandbox.md` §8, including the egress-inventory table.

## Consequences

- The public path is **byte-identical** — `docker-compose.prod.yml`, the public
  Caddyfile, the image set and the deploy pipeline are untouched; the private profile is
  opt-in at compose time. ADR-F058's delivery modes, ADR-F059's §6 security gate
  (security headers, internal-API/WOPI/metrics denies, access-log token scrub) and
  ADR-F060's deploy topology + D6 env posture (no-default-secrets) carry into the
  private profile unchanged; KV-1 (ADR-F069) composes orthogonally on top.
- `scripts/gen-secrets.sh` gates the MinIO/S3 block behind a `--private` flag instead of
  emitting it always (a deliberate improvement over the slice contract's additive-always
  ruling): the default output stays byte-identical to pre-P-1, so the public path can
  never have procured `S3_*` values shadowed by generated ones.
- **Single-node MinIO durability posture**: object storage now lives on the same disk as
  the stack — no replication/erasure coding/provider durability. Backups (per
  staging-bringup.md, preferably off-box) matter more, not less; stated honestly in
  runbook §8.
- **Enterprise stepping stone**: the §8 egress-inventory table IS the handover to AZ-6 —
  each line is Private-Link-able (model endpoints, Key Vault), eliminable (registry
  mirror / image side-load, a P-2 backlog candidate; repo tarball), or one-time and
  mitigable (the first-ingest Docling/EasyOCR model download: pre-seed the cache
  volumes, use an approved window, or disable Docling).
- The two Caddyfiles must be kept in sync by review discipline (header comments in both
  point at each other); a shared-include refactor was deliberately not done in this slice.
- The `!override` tag and the placeholder mechanism are compose-merge subtleties: the
  merged-config assertions (loopback-only caddy ports; minio + healthcheck present;
  S3/depends_on wiring; placeholders resolving harmlessly) are the slice's regression
  check and should be re-run whenever either compose file changes.
