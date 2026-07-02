# deploy/status — public status page (Uptime Kuma)

The status page for the hosted stacks (SAAS-3, ADR-F060). Uptime Kuma at
`status.<domain>` monitors each tenant's public URL and the backup dead-man
switches, and shows uptime history to customers.

## Why a separate stack

This is intentionally **not** a service in any tenant's `docker-compose.prod.yml`.
A status page that runs inside the thing it monitors goes dark exactly when it is
needed — a tenant node (or the tenant stack) failing must not take its own status
page with it. Run this on a **different, small host** (or the ops/control host),
so it observes the tenant stacks from the outside.

## Run

```sh
docker compose -f deploy/status/docker-compose.status.yml up -d
```

Uptime Kuma listens on `127.0.0.1:3001`. Front it with the host's own reverse
proxy (a small Caddy site for `status.<domain>` with automatic TLS); never
publish `3001` to `0.0.0.0`. Pin the image by digest at bring-up (update on the
app cadence) — the committed tag is major-pinned only so `docker compose config`
works in CI.

## What to monitor (configured in the Kuma UI at first run)

- Each tenant's `https://<tenant-host>/health` (HTTP 200) — the public edge is up.
- Each tenant's backup **dead-man switch** (a push monitor whose URL is the
  `LQ_AI_BACKUP_DEADMAN_URL` that `backup.sh` pings): a missed nightly ping means
  the backup silently failed. `restore-drill.sh` can ping `LQ_AI_RESTORE_DEADMAN_URL`
  the same way.
- The gateway's health, indirectly, via an authenticated agent smoke (optional).

Kuma's own admin account is created on first load — set a strong password and
keep the admin surface behind the status host's proxy / an allow-list.
