# SAAS-SETUP — Setup & Onboarding Architecture

**Status:** DRAFT for maintainer edit (2026-07-03). Grounded in a 5-lens code recon (auth/users ·
practice-area substrate · capability registries · deploy/wizard substrate · admin fence); every claim
below is anchored, not assumed.
**Directive (maintainer, 2026-07-03):** bring-up happens on an **IONOS VPS** at the weekend; before
then, everything agent-buildable should be done. Three setups to design: the **operator's** (a wizard
"for me"), the **customer's turn** (admin account → admin creates users), and the **admin's
configuration surface** (practice-area agents + tenant-wide skills/playbooks/tools). The structure
must **survive things we add**.
**Decided at drafting:** Caddy edge goes **multi-DNS-provider** (Option A). Verified: `caddy-dns/ionos`
exists (v1.2.0, official org); Caddyfile `{$VAR}` env substitution is **parse-time**, so
`dns {$LQ_AI_DNS_PROVIDER:hetzner} {env.LQ_AI_DNS_API_TOKEN}` selects a compiled-in module per
deployment from ONE fleet image (the Caddyfile previously hardcoded `dns hetzner` — fixed by SETUP-1).

---

## 0. What the recon changed (read this first)

The skeleton assumed more greenfield than exists. Verified reality:

- **Practice-area config admin API already exists** — `PATCH /practice-areas/{key}` (doctrine, tier
  floor, subagent roster) + skill/playbook attach/detach, all `AdminUser`-gated + audited
  (`api/app/api/practice_areas.py:125-367`). What's missing is **create/delete**, the **tool-group
  data seam**, and **any web UI** (only read-only transparency exists).
- **ADR-F054 per-matter toggles are fully implemented** (mig 0081, `matter_capability_toggles`,
  `CapabilitiesPanel.svelte`) — Level 2 of the hierarchy is DONE; its sparse-override pattern
  (absence=default, explicit enabled, provenance) generalizes verbatim to the deployment level.
- **`capabilities.py` is the single chokepoint** — both the panel API and composition consume
  `build_area_inventory` (`capabilities.py:221`); adding a deployment toggle source there propagates
  to every enforcement point for free (off-at-source is already the mechanism).
- **User admin partially exists** — `GET /admin/users` + `PATCH /admin/users/{id}/role` (with
  last-admin lockout guard, `admin.py:682,765,814-833`). **Zero creation paths** besides first-run
  bootstrap; no invite/reset/verification; `viewer` role defined but enforced nowhere.
- **Email transport exists** (stdlib smtplib, `api/app/autonomous/notify_email.py`) and SMTP settings
  exist in config (`config.py:579-616`) — but the vars are **not in `.env.prod.example` and not
  forwarded in the prod compose api allowlist** → hosted stacks cannot send mail today.
- **Gateway provider keys + model aliases are runtime-editable via authenticated API with hot-swap**
  (`config_writer.py`, `provider_keys.py`) — the wizard can seed a minimal gateway.yaml and manage
  keys post-boot; only tiers/policy/rate-limits need volume-edit + restart. Remember the trap: the
  seed copies into the `gateway-config` volume **only on first boot**.
- **The admin fence is real and currently absent**: one flat `is_admin` reaches BOTH org concerns
  (users, audit, areas, House Brief) AND platform concerns (provider keys, aliases, gateway config,
  tier policy) — ADR-F058 §5 mandates the split.
- **Two config gaps block a clean handover today**: `FIRST_RUN_ADMIN_EMAIL` is not forwarded in prod
  compose (and `admin_bootstrap.py:17` documents a wrong `LQ_AI_`-prefixed name — doc bug), so the
  tenant-admin email is unconfigurable; SMTP likewise.

## 1. The three-actor model

| Actor | Who | Owns | Lives |
|---|---|---|---|
| **Operator** (platform) | Arturs / hosting side | box, OS, docker, `.env` secrets, **gateway provider keys + aliases + tier policy**, backups, upgrades, DNS/TLS | outside the app (SSH + wizard) **plus** a fenced in-app role for the gateway-proxy endpoints |
| **Org-admin** (customer) | tenant's nominated admin(s) | users (invite/disable/role), practice-area config, tenant-wide capability toggles, House Brief, teams, intake bridges, audit/usage visibility | in-app, `role=admin` |
| **Member** (lawyer) | tenant users | matters, conversations, preferences | in-app, `role=member` (`viewer` exists; enforcement optional later) |

**The fence (from the route-by-route recon):**

- **Operator-only** (new `operator` role + `OperatorUser` dependency, same pattern as `AdminUser` at
  `dependencies.py:134`; belt-and-braces optional Caddy edge-deny of these paths per tenant stack):
  `/admin/aliases*`, `/admin/provider-keys*`, `/admin/config`, `PATCH /admin/tier-policy`,
  `POST /inference/override-tier-floor` (default), the `/admin/developer` + `/admin/models` UI pages.
- **Org-admin** (stays `AdminUser`): audit-log, usage, users+roles, teams, intake-bridges, word-addin,
  ingest-health, `PUT /organization-profile`, all `/practice-areas` config endpoints.
- Rationale anchor: the gateway deliberately has no user-authz of its own — "the backend's `is_admin`
  gate is the user-level authorization layer" (`gateway/app/api/dependencies.py:10-16`) — so the split
  is a **backend role change**, not a gateway change.
- Operator in-app presence: an `operator` **role value** on the same users table — no parallel auth
  system. In Mode-2 the operator account is created by the wizard and is the only account allowed to
  touch gateway surfaces. Survivability: future roles (auditor read-only) are new values in the same
  vocabulary.

## 2. The configuration hierarchy (the structure that survives additions)

```
Level 0 — DEPLOYMENT (tenant-wide)         NEW: deployment_capability_toggles
  what is available in this stack at all: skills / playbooks / tool-groups / (MCP slot reserved)
  + model menu (operator-owned via gateway; admin sees read-only)
  + House Brief, branding hook, budget-profile default
Level 1 — PRACTICE AREA                    EXISTS (bindings) + NEW (tool-group seam, create/delete)
  doctrine (profile_md), unit noun, tier floor, subagent roster        [exists — data]
  bound skills (practice_area_skills) + playbooks (practice_area_playbooks)  [exists — data]
  bound tool-groups                                                    [today: CODE map — becomes data]
Level 2 — MATTER                           EXISTS (ADR-F054, shipped)
  sparse matter_capability_toggles over the area's enabled set
```

**Resolution rule:** each level only narrows the one above; absence of a row = inherit. All three
levels resolve through the one chokepoint (`build_area_inventory`), so every enforcement point
(skill wiring, `GuardContext.granted`, playbook tier, doctrine prompts) inherits automatically.

**The keystone refactor (what unblocks admin-created areas).** Today a new area gets domain tools
only via code: the elif chain (`composition.py:770/789/…` — grants + change-ledger class + builder
call per area key) and the `AREA_TOOL_GROUPS` code map (`capabilities.py:99-102`). Replace with a
**tool-group registry**: code registers, per group key, `{tools-builder factory, ledger factory,
doctrine addendum}`; composition iterates the area's **enabled groups** instead of branching on
`area_key`. Which groups an area has becomes **rows** (`practice_area_tool_groups`, seeded from
today's map). What stays code, deliberately: the tool implementations, guard chokepoints, the group
registry itself, gateway egress, doctrine constants.
⚠️ This supersedes **ADR-F054 decision #1** ("tool availability is a code map, not a table") — that
was maintainer-confirmed on 2026-06-30, so this plan asks for it explicitly (decision row #9); the
original rationale (no byte-matching seed) is honored by seeding group *names* only, never grants.

**Seed-vs-edit rule (first-class once admins edit):** migrations only ever seed defaults with
never-clobber guards (the existing 0055/0066/0073 convention); human/admin edits always win; a
config surface never blocks a future seed migration and vice versa.

## 3. The operator's setup (the wizard "for me")

**Form:** CLI wizard `scripts/setup-tenant.sh` — interactive prompts or `--manifest
tenants/<id>.yaml` (repeatable, idempotent). Web control plane stays SAAS-7A.

**Inputs it collects** (exact, from the env/compose inventory):
1. Tenant slug (`LQ_AI_TENANT_ID`, `COMPOSE_PROJECT_NAME`, bucket name)
2. Public host (single or wildcard → `LQ_AI_PUBLIC_HOST`, derives `LQ_AI_PUBLIC_ORIGIN`)
3. **DNS provider** (`LQ_AI_DNS_PROVIDER` ∈ hetzner|ionos — the compiled-in set; the wizard must
   reject anything else, which would brick the edge at startup) + zone-scoped token
   (`LQ_AI_DNS_API_TOKEN`) + node IPs for the A/AAAA/CAA instructions
4. S3: endpoint/region/keys/bucket (any S3-compatible — IONOS S3 fine; optionally creates the bucket
   + versioning + lifecycle via the dockerized aws-cli the scripts already use)
5. Model stance → renders the **gateway.yaml seed** from a new in-repo template (non-PRC default;
   provider keys entered here go in encrypted via the master key, or post-boot via the admin API)
6. Backup: age public recipient (keypair generated offline, private key never on node), dead-man URLs
7. Handover: **tenant-admin email** (→ `FIRST_RUN_ADMIN_EMAIL`, forwarded — gap fix) and SMTP creds
   (→ forwarded — gap fix)
8. Ops: image tag (or latest published sha), node profile (full 16GB vs reduced 8GB), ACME email

**Artifacts it generates (node-side only, nothing in the repo):** `/opt/lq-ai/.env.prod` (0600;
gen-secrets block + inputs) · `/opt/lq-ai/gateway.yaml` seed · stack files sync · DNS record
instructions · bucket (optional) · backup cron · then runs `deploy.sh` and prints the handover
(v1: surfaces the bootstrap admin password from the api log, once; from SETUP-3: sends the admin
**invite** instead — operator never knows the customer password).

## 4. The customer's turn (admin handover + user lifecycle — ex-SAAS-4)

1. Tenant admin receives **invite** (email) → sets password (+ optional MFA) → forced first-run flow.
2. First-login onboarding: House Brief → invite users → review practice-area defaults.
3. **User lifecycle** (all greenfield, verified): invite tokens (single-use, TTL, hashed at rest) ·
   accept/resend/revoke · password reset · email verification · admin disable/offboard (only
   self-serve GDPR delete exists) · anti-enumeration + rate limits inherited from the SAAS-2 limiter.
   Mail via the existing `notify_email.py` transport pattern, generalized out of `autonomous/`.
4. Admin **Users** UI (list exists API-side; invite/disable UI greenfield). Invitation-only — no
   self-serve signup in Mode-2.
5. The **fence lands here too** (§1): `operator` role, `OperatorUser` dep, route reclassification.

## 5. The admin's configuration surface

- **Practice Areas admin UI** (greenfield — API mostly exists): list/enable/reorder; edit doctrine,
  unit noun, tier floor, subagent roster; bind/unbind skills + playbooks (existing endpoints) and
  tool-groups (new seam); **create area** (new `POST /practice-areas`) assembled from the registry —
  bounded by what the registry offers, so an admin cannot mint capabilities, only compose them.
- **Tenant-wide Capabilities admin UI** (Level 0): enable/disable skills/playbooks/tool-groups
  deployment-wide (`deployment_capability_toggles`); model menu shown read-only (transparency);
  MCP slot visible-but-disabled as today.
- Transparency invariant holds throughout: every doctrine, skill, grant readable in the UI.
- **Out of scope v1 (recorded):** tenant-*authored* skills (skills are filesystem-canonical, baked
  into images — admins bind/unbind registry names only; the `user_skills.scope` seam is the future
  path); per-tenant branding hook; MCP wiring (ADRs 0014/0015 approval-gated).

## 6. Slices

| Slice | Scope | Size | Weekend-critical |
|---|---|---|---|
| **SETUP-1** | Multi-DNS edge (Option A): bake `ionos@v1.2.0` + `hetzner@v1.0.0` (cloudflare DEFERRED — the module has no release tags; pin-to-commit one-liner when a tenant actually needs it); `dns {$LQ_AI_DNS_PROVIDER:hetzner} {env.LQ_AI_DNS_API_TOKEN}`; generalize `HETZNER_DNS_API_TOKEN`→`LQ_AI_DNS_API_TOKEN` (compose `:?`, env example, guard test); de-Hetzner the runbook (IONOS VPS/DNS/S3 paths); ADR-F060 amendment | S | **YES** |
| **SETUP-2** | Operator wizard v1 (§3): manifest→artifacts renderer + gateway.yaml template + bucket/cron/DNS-instructions + deploy call; fix the two compose gaps (FIRST_RUN_ADMIN_EMAIL + SMTP forwarding, + the env-name doc bug); bootstrap-password handover (interim). Testable boxless: golden-file render tests + shellcheck + optional local-compose e2e | M | **YES** |
| **SETUP-3a** | User lifecycle backend: invite/accept/resend/revoke, reset, verification, admin disable; mail sender generalized from notify_email; anti-enumeration + rate limits; **operator role + fence** (route reclassification per §1) | L | no |
| **SETUP-3b** | Users admin UI (invite/disable/role) + first-login onboarding flow + wizard switches to invite-handover | M | no |
| **SETUP-4a** | Tool-group registry refactor (kill the elif chain), `practice_area_tool_groups` (seeded from today's map), `POST/DELETE /practice-areas`, `deployment_capability_toggles` threaded into `build_area_inventory` | L | no |
| **SETUP-4b** | Practice Areas + Capabilities admin UI (§5) | M–L | no |
| **SETUP-5** | Reconcile: flip ADR-F054 to accepted with the D1-supersession addendum; per-area/deployment budget-profile defaults; `viewer` enforcement decision; polish | S–M | no |

ADRs: **F061** (actor model + fence + configuration hierarchy — §1–2), **ADR-F060 amendment**
(multi-DNS edge), **F054 addendum/supersession** (decision #9).

## 7. Decision table (maintainer edits)

| # | Decision | Recommendation | Alternatives / notes |
|---|---|---|---|
| 1 | Where does the DNS zone live? | wherever the domain is registered (IONOS if IONOS) — Option A covers hetzner/ionos (cloudflare deferred: no release tags) | move the zone; CNAME-delegation recorded as the fleet-scale pattern |
| 2 | SMTP for auth mail | plain SMTP creds per tenant (wizard input; generic, self-host-friendly) | transactional API adapter later |
| 3 | Wizard form | CLI + manifest | web control plane (SAAS-7A) |
| 4 | Can org-admins CREATE areas? | yes, from the registry (bounded) | configure-seeded-only first |
| 5 | Operator in-app account | yes — `operator` role value, wizard-created, gateway surfaces only | none (edge-deny only) — weaker, config-drift-prone |
| 6 | Model menu visibility to org-admin | read-only visible (transparency) | hidden |
| 7 | Invite token policy | single-use, 7-day TTL, hashed at rest, rate-limited | shorter/longer |
| 8 | BYOK: provider-keys delegated to org-admin? | NO for v1 — operator-only; revisit per-tenant BYOK on first ask (F058 notes it "falls out free") | scoped org-admin BYOK surface |
| 9 | Tool-group availability becomes DATA (supersedes F054 D1, maintainer-confirmed 2026-06-30) | yes — group *names* as rows, grants stay code (honors the original no-byte-matching-seed rationale) | keep code map; admin-created areas then can't get domain tools |
| 10 | Tenant-authored skills | OUT of v1 (bind/unbind baked registry only) | DB-backed org-scope skills (extend `user_skills`) as its own future slice |

## 8. Sequencing to the weekend

SETUP-1 and SETUP-2 are the weekend-critical pair and are already unblocked (Option A decided;
wizard shape robust to plan edits). SETUP-3+ start after this plan is maintainer-edited. The
weekend bring-up then needs only: box + DNS records + running the wizard.

## 9. Verification (per slice, ADR-F005 gate as always)

- SETUP-1: image builds + `caddy validate` for EVERY provider value of `LQ_AI_DNS_PROVIDER`
  (hetzner/ionos + default), PLUS the negative case — an uncompiled provider (e.g. cloudflare)
  must FAIL validation loudly; compose config valid; guard test green; runbook coherent.
- SETUP-2: golden-file tests — same manifest in, byte-identical artifacts out; secrets never in
  manifest or repo; shellcheck; optional local end-to-end (fresh compose stack from wizard output on
  a throwaway project name).
- SETUP-3a: full api suite + new lifecycle tests (token single-use/TTL/hashing, anti-enumeration
  uniformity, rate limits, fence — operator routes 403 for org-admin, org routes intact); deeper
  security review pass (auth path).
- SETUP-4a: composition parity test — for the seeded areas, the registry-driven grant set is
  **identical** to today's elif output (golden); cross-area isolation unchanged.
