# Runbook — staging bring-up (SAAS-3b)

The ordered, maintainer-run steps that turn the SAAS-3a substrate into a live
staging stack, plus the live-proof definition and the pre-exposure hardening
checklist. Governing: `docs/fork/plans/SAAS-HOSTING.md` §5, ADR-F060, ADR-F058.

SAAS-3a shipped everything the agent can build + verify with no live box (the
custom Caddy image, the prod `caddy` service, `deploy.sh`/`backup.sh`/
`restore-drill.sh`/`gen-secrets.sh`, the deploy workflow, `.env.prod.example`, the
DNS templates, the status stack). **SAAS-3b is this runbook executed once**, then
a thin PR: the checklist ticked with evidence.

> **Staging data hygiene (hard rule, SAAS-HOSTING §5):** synthetic / sample data
> ONLY (`sample-documents/` packs exist). Prod→staging copies are prohibited,
> including in restore drills. A restore drill restores a *staging* backup into a
> throwaway container — never staging itself, never prod data.

## 0. Decisions (confirmed defaults, ADR-F060)

- **Host:** any EU-resident VPS vendor (maintainer's box: **IONOS**; Hetzner CX43
  was the costed reference). 16 GB full stack — or 8 GB running the reduced
  profile (§ Reduced profile below). The VPS vendor is independent of DNS/S3.
- **DNS:** a supported DNS-01 provider hosts the zone — `hetzner` or `ionos`
  (multi-provider SETUP-1; select via `LQ_AI_DNS_PROVIDER`).
- **TLS:** wildcard DNS-01 via the custom Caddy image (already built by `images.yml`).
- **Backups:** `pg_dump -Fc | age` (asymmetric) → object storage; restore drills
  into a throwaway container.
- **Deploy:** SSH-push from the `Deploy staging` workflow; roll-forward-only.

## 1. Provision infra (the credit-card steps)

1. **Domain** — host the zone at a supported DNS provider (`hetzner` | `ionos`);
   set `LQ_AI_DNS_PROVIDER` accordingly.
2. **Node** — an EU VPS with 16 GB (e.g. IONOS VPS; 8 GB → reduced profile),
   Ubuntu LTS. Firewall: allow **80/443 only** (plus SSH from your admin IP /
   via WireGuard-Tailscale). SSH **key-only** (`PasswordAuthentication no`).
3. **DNS API token** — a token for that DNS provider scoped to this zone → this
   is `LQ_AI_DNS_API_TOKEN` (IONOS: the `publicprefix.secret` concatenation from
   the developer console).
4. **Object storage** — any S3-compatible bucket for this tenant (IONOS S3 /
   Hetzner Object Storage — the scripts use the generic aws-cli). Enable
   **versioning** (customer files are covered by versioning, not the DB dump —
   ADR-F060 D4) and a **lifecycle rule** for backup retention (7 daily / 4 weekly
   under `tenants/<id>/backups/`). Create access/secret keys → `S3_*`.
5. **age keypair** — `age-keygen -o operator-identity.txt` on your workstation.
   The **public** recipient (`age1…`) goes in `.env.prod` as
   `LQ_AI_BACKUP_AGE_RECIPIENT`; the **private** identity stays OFF the node
   (offline / a password manager) — the node must not be able to read its backups.

## 2. DNS records

Create the records from `deploy/dns/README.md` (A/AAAA for the app host +
`status`, the CAA lock, and — if sending mail — SPF/DKIM/DMARC). Keep TTL 300 s
during bring-up.

## 3. Node prep

```sh
# On the node, as root (or a sudo user):
apt-get update && apt-get install -y docker.io docker-compose-v2 age
install -d -m 750 /opt/lq-ai
# Log in to GHCR so `compose pull` can fetch the private images (a read:packages PAT):
docker login ghcr.io -u <github-user>            # paste the PAT when prompted
```

Place the stack files (the deploy workflow re-syncs `docker-compose.prod.yml` +
`deploy.sh` on every deploy, but seed them once for the first manual run):

```sh
scp docker-compose.prod.yml scripts/deploy.sh scripts/backup.sh \
    scripts/restore-drill.sh <node>:/opt/lq-ai/
```

Build `.env.prod` (root-owned, chmod 600):

```sh
# On the node:
scripts/gen-secrets.sh >> /opt/lq-ai/.env.prod        # generated secrets
chmod 600 /opt/lq-ai/.env.prod
# Then paste the PROCURED values from .env.prod.example (host, S3_*, DNS token,
# tenant id, age recipient, dead-man URLs, GATEWAY_CONFIG_FILE path).
```

**gateway.yaml seed (model stance — pre-exposure fence).** Provision this
tenant's `gateway.yaml` at `GATEWAY_CONFIG_FILE` from the control-plane template.
For a PUBLIC URL, default tenant traffic to a **non-PRC** model (ADR-F060
consequences; the full EU menu / PRC de-fencing is SAAS-6) — do **not** ship
staging defaulting to DeepSeek/MiniMax.

## 4. GitHub Environment `staging` secrets

Repo → Settings → Environments → `staging` (add a required reviewer if you want a
manual gate). Secrets:

| Secret | Value |
|---|---|
| `STAGING_SSH_HOST` | node hostname / IP |
| `STAGING_SSH_USER` | deploy user |
| `STAGING_SSH_KEY` | the deploy user's PRIVATE key (PEM) |
| `STAGING_SSH_KNOWN_HOSTS` | `ssh-keyscan <host>` output (pins the host key) |
| `STAGING_STACK_DIR` | `/opt/lq-ai` (optional; defaults to it) |
| `STAGING_COMPOSE_PROJECT` | e.g. `lq-ai-staging` (optional; defaults `lq-ai`) |

## 5. First deploy

- **Automatic:** push to `main` → `Images` builds → `Deploy staging` runs
  `deploy.sh <sha>` over SSH.
- **Manual:** Actions → *Deploy staging* → *Run workflow* with a specific SHA
  (also the rollback path: dispatch the previous SHA).
- **Direct (first manual bring-up):** on the node,
  `LQ_AI_IMAGE_TAG=sha-<12hex> bash /opt/lq-ai/deploy.sh`.

Caddy issues the wildcard cert via DNS-01 during `up` (first issuance can lag DNS
propagation — `deploy.sh` retries the smoke). **First boot forces a one-time
re-login** for any existing users: migration 0084 (SAAS-2) clears `user_sessions`
(acceptable — no tenants yet).

## 6. Live proof (the SAAS-3b evidence)

1. **Proof 1 — a real agent turn on the public URL.** Log in at
   `https://<staging-host>`, run a Commercial or Privacy agent turn end-to-end
   (streamed tool calls + a receipt) on synthetic data. Capture a screenshot /
   `curl` transcript.
2. **Proof 2 — a passed restore drill.** After the first nightly backup exists:
   ```sh
   LQ_AI_BACKUP_AGE_IDENTITY=./operator-identity.txt \
     bash /opt/lq-ai/restore-drill.sh            # (with .env.prod sourced)
   ```
   It fetches the latest encrypted dump, decrypts it, restores into a throwaway
   container, and asserts the schema (`alembic_version`) + row counts. Capture the
   output.

## 7. Nightly backup cron + retention

```cron
# /etc/cron.d/lq-ai-backup — nightly at 03:17 UTC
17 3 * * *  root  set -a; . /opt/lq-ai/.env.prod; set +a; /opt/lq-ai/backup.sh >> /var/log/lq-ai-backup.log 2>&1
```

Retention is enforced by the bucket **lifecycle rule** (step 1.4), not the script.
Wire `LQ_AI_BACKUP_DEADMAN_URL` (healthchecks.io-style) so a *missed* nightly ping
alerts. Run a restore drill on a schedule (e.g. weekly) — a backup you have never
restored is not a backup.

## 8. Status page

On the separate status host: `docker compose -f deploy/status/docker-compose.status.yml
up -d`, front `status.<domain>` with its own TLS, and add monitors for each
tenant's `/health` + the backup dead-man switch (`deploy/status/README.md`).

## Pre-exposure hardening checklist (tick before announcing the URL)

The SAAS-2 handoffs (they need the live stack) + the SAAS-3 fences:

- [ ] **`FORWARDED_ALLOW_IPS`** pinned to Caddy's fixed container IP (drop `*`) —
      ADR-F059 D4. Find it: `docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' <project>-caddy-1`.
- [ ] **CSP** promoted from report-only to enforced `Content-Security-Policy`
      after the live violation report is clean (Caddyfile, SAAS-2 (c)).
- [ ] **`LQ_AI_GATEWAY_KEY`** rotated from any value that ever touched a dev box /
      terminal (regenerate with `gen-secrets.sh`, update `.env.prod`, redeploy).
- [ ] **Collabora egress** locked to the WOPI host (`api:8000`) — deny its
      container outbound except the stack network.
- [ ] **Model fence**: gateway.yaml defaults to a non-PRC model for tenant traffic
      (SAAS-6 does the full EU menu).
- [ ] **Synthetic data only** on staging; no prod copies.
- [ ] `docker image prune -f` (dangling only) run after the node's builds/pulls.

## Reduced profile (CX33 / 8 GB)

An 8 GB node running the full 9-service stack will OOM during verification runs
(ADR-F056). If using a CX33: disable Collabora (the in-app editor) and set
`LQ_AI_INGEST_WORKER_CONCURRENCY=1` in `.env.prod`. Document which profile a stack
runs; the default staging target is CX43 full-stack for prod fidelity.
