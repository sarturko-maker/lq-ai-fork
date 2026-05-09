# ADR 0010 — Gateway config hot-reload + admin write API

**Status:** Accepted
**Date:** 2026-05-08
**Owner:** D0.5 — Admin: model alias settings UI

## Context

Before this task, `gateway.yaml` was an immutable startup artifact. The
gateway loaded it once during the FastAPI lifespan, validated it via
Pydantic, and never re-read it. Operator workflow for editing the
alias map was:

1. Edit `gateway.yaml` on disk (often inside the running container).
2. Restart the gateway (`docker compose restart gateway`).
3. Wait for the readiness probe to flip back to ready.
4. Verify the new mapping by sending a chat.

This is a poor experience for a self-hosted product whose central
design constraint is transparency (see CLAUDE.md and PRD §1.3). The
admin alias UI in D0.5 needs a write path that does not require a
container restart.

## Decision

`gateway.yaml` is a **mutable runtime artifact**. The admin alias-CRUD
endpoints (`POST/PATCH/DELETE /admin/v1/aliases/*`) write the file
atomically and trigger an in-process hot-reload. SIGHUP is also a
supported reload trigger (mirrors C1's skill registry pattern).

The implementation has three load-bearing parts:

1. **`MutableConfigHolder`** — atomic-swap container around
   `GatewayConfig`. The router reads the live snapshot through
   `holder.current()` (a single attribute fetch — atomic under
   CPython's GIL); per-request handlers see a coherent view across
   their own dispatch. Writes serialize through a threading lock so
   two concurrent reload attempts cannot tear the snapshot.
2. **Atomic file writes** — `config_writer.upsert_alias` and
   `delete_alias` round-trip the YAML through a `temp + os.replace`
   pattern. On a failed reload (Pydantic rejects the new shape), the
   file is rolled back to its prior bytes and the holder retains the
   old snapshot. **The gateway never silently transitions to a
   malformed config.**
3. **Authentication** — every write endpoint is gated by the existing
   `X-LQ-AI-Gateway-Key` shared secret (the same one the backend
   already uses for service-to-service calls). The user-level
   `is_admin` check is the **backend's** responsibility: the backend
   proxies `/api/v1/admin/aliases/*` and adds the admin gate before
   forwarding to the gateway.

In-flight request semantics: a request that has resolved its alias
chain and dispatched to a provider runs to completion on its own
snapshot of the config. The reload installs a new holder atomically;
the next request picks up the new state. There is no torn read, no
partial state visible to any caller.

### Gateway.yaml vs gateway.yaml.example (decision #2 from the brief)

The repo's `gateway.yaml.example` is source-controlled and reset by
`docker compose up --build`. With write enabled, mutating the
example file would: (a) drift from the committed version; (b) be
clobbered on next image rebuild; (c) corrupt the seed file used by
fresh deployments.

**Decision:** the gateway container's runtime config lives at
`/etc/lq-ai/gateway.yaml` inside a writable named volume
(`gateway-config`). The image bakes the example into
`/usr/share/lq-ai/gateway.yaml.example` (read-only); an entrypoint
script seeds the runtime file from the example on first boot.
Operators who want immutable config (a hardened deployment that
refuses runtime edits) bind-mount their own `gateway.yaml` directly
with `:ro` and accept that the admin write endpoints will fail with
500.

## Trade-offs

### What we accept

* **A compromised gateway can rewrite its own config.** This is a
  meaningful security observation (the gateway is the security
  boundary; the file controls which providers handle which
  requests). Mitigation: container filesystem isolation, per-host
  bind mounts on the operator side, and the unchanged posture that
  provider *keys* live in environment variables and are never written
  through the admin API. Operators concerned about this MAY mount
  `gateway.yaml` read-only and lose the UI editing affordance — file-
  edit + restart still works.
* **Operators who run multiple gateway replicas against the same
  shared config file** get last-write-wins between replicas. The
  M1 default is single-replica; multi-replica deployments are tracked
  as a deferred concern.
* **The named-volume approach means a `docker compose down -v`
  destroys the operator's runtime aliases.** This is the same
  posture as Postgres data (`pgdata`); operators preserve runtime
  state by not running `down -v`. The `gateway.yaml.example` is
  always re-seeded on the next `up`.

### Why not DB-backed overrides

A DB-backed alias table layered over the YAML defaults would avoid
the file-write step entirely. Rejected because:

* It splits the source of truth (`gateway.yaml` *plus* a DB row), and
  every "what is this alias actually configured to do?" question
  needs to merge two sources.
* It adds an availability dependency (alias resolution would need the
  DB at request time).
* The transparency principle (CLAUDE.md) calls for the YAML file to
  remain the canonical, human-readable source. Fragmenting that
  across DB rows works against the principle.

The chosen approach keeps the YAML file as the single source of
truth. Operators who prefer git-managed config can `git pull` an
updated `gateway.yaml`, push it to the writable mount, and SIGHUP the
gateway — same workflow as before, with fewer restarts.

## Consequences

* The web admin UI at `/lq-ai/admin/models` (D0.5) is the operator's
  primary affordance for editing the alias map. Direct YAML editing
  still works.
* `docker-compose.yml` mounts a named volume at `/etc/lq-ai`; the
  example file is exposed at `/usr/share/lq-ai/gateway.yaml.example`
  for the entrypoint to seed from.
* CODEOWNERS auto-routes `gateway/**` changes to security review,
  including this ADR's implementation.

## Forward-looking

* `tier_policy` and `cost_tracking.rates` are equally mutable in the
  same way. D1 (tier-floor enforcement) will surface a tier-policy
  editor on top of the same hot-reload machinery.
* `providers:` (which holds `api_key_env` references and tier
  declarations) is **out of scope** for D0.5 — the threat model for
  editing provider configuration through a UI is heavier than for
  alias edits, and the operator base for that surface is much
  smaller. Tracked as a deferred enhancement.
