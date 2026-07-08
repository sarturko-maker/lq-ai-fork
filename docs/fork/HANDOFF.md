# HANDOFF — live pickup document

Overwritten at the end of every slice (CLAUDE.md § Session handoff). **Read this first in every session**,
then CLAUDE.md, then the ADRs/plans named below.

> ═══════════════════════════════════════════════════════════════════════════════════════════════════════
> ▶▶▶ **PIVOT (2026-07-07): MODULAR AGENT-BUILDER + AZURE FOUNDRY + REDLINE CONTINUITY — the CURRENT
> direction. Maintainer approved ALL of it verbatim ("Approved and go on all").** Governing docs (read in
> order): **`docs/fork/plans/PIVOT-modular-azure.md`** (the breakdown: Workstreams R / AZ / B, incl. the
> R-1 fix spec and the B-0…B-7 wizard ladder) → **`docs/fork/plans/AZURE-FOUNDRY-phase1.md`** (Azure
> Phase-1 research report, **Phase 2 APPROVED 2026-07-07**; verdicts + confirmed endpoints/auth/regions +
> repo coupling flags) → `docs/fork/plans/CAPABILITY-SOURCES-birdseye.md` (two-universe map behind B).
> Memory: [[pivot-modular-azure]]. This supersedes the "PICK UP = STORE-3" pointer below (STORE done).
>
> **THE SLICE LADDER (execute top-down; one PR each; full ADR-F005 gate every time):**
> - **PR #227 ✓ MERGED** — the pivot record (5 plan docs, doc-only).
> - **R-1 ✓ SHIPPED (PR #228 merged `08cceb99`, ADR-F066 accepted, mig 0089) — redline
>   continuity.** Follow-up redlines now continue from the agent's own latest working version:
>   `files.parent_file_id` + `files.is_snapshot` (mig 0089, up/down/up verified on throwaway
>   pgvector); write-side lineage on redline/response outputs + WOPI snapshots;
>   `resolve_working_docx` (breadth-first newest NON-SNAPSHOT LEAF — a greedy per-hop walk was a
>   review catch; matter-scoped every hop via the shared `_DOCX_COLUMNS` projection; depth-capped);
>   `apply_redline`/`preview_redline` grow `start_fresh=false` + a continuity note naming the
>   resolved version; version-aware naming `(redlined)→(redlined v2)→…` with the version-digit run
>   BOUNDED to 8 digits (hostile-filename review catch); inventory renders honest provenance
>   ("agent work product — derived from X" / "editor snapshot of X") instead of "not ingested yet";
>   SKILL/doctrine/docstrings corrected. `extract_counterparty_position`/`respond_to_counterparty`
>   deliberately KEEP exact-name semantics. Orchestrated as a 3-implementer + 3-reviewer + fixer
>   workflow; 3 should-fixes all applied, nothing deferred. Gate: full containerized api suite
>   **3387 passed / 47 skipped** (baseline 3369 + the slice's tests); ruff (root config) + mypy
>   clean; live in-container probe (real Adeu + real S3 + live DB, no LLM): apply×2 → v1 parent =
>   original, v2 parent = v1, continuity note names v1, resolver leaf = v2, start_fresh bypasses —
>   throwaway matter cleaned. **TRAPS:** (1) workflow verify runners MUST return structured output —
>   the suite runner died reporting nothing (agents_empty_result); lead re-ran. (2) ruff inside a
>   container with ONLY api/ mounted falls back to line-length 88 and mass-rewraps — ALWAYS mount
>   the repo root. (3) targeted in-container tests need /skills mounted (mig 0032 seeds from it).
> - **AZ-CONFIG ✓ SHIPPED (branch `az-config-foundry`) — AZ-1 + AZ-2a + AZ-3 + AZ-4a in one
>   config-only PR; each provider independently enableable; nothing changes when unset.**
>   `gateway.yaml.example`: azure-openai api_version → GA `2024-10-21`; NEW `azure-claude`
>   (`type: anthropic`, native Messages route on `…services.ai.azure.com/anthropic`, TEXT-ONLY until
>   AZ-2b, no agent alias); NEW `azure-mistral` (`type: azure_openai` on the services.ai host,
>   Mistral-Large-3 — the agent-capable Mistral pick on Azure); commented azure aliases + cost-rate
>   placeholders + Door-B embedding variant (AZ-4 PARKED per budget — local Door-A embedder stays);
>   ACTIVE `inference_tiers.overrides: azure-claude: 3` (review catch: `defaults.anthropic: 4` would
>   shadow the entry's tier 3 — red/green-proven vs `derive_routed_inference_tier`). Env plumbing:
>   AZURE_ANTHROPIC_*/AZURE_FOUNDRY_* in `.env.example` + `.env.prod.example` +
>   `deploy/caddy-tailscale/.env.example`, forwarded `${VAR:-}` in both compose files;
>   tenant-gateway.yaml.example commented blocks. Test loads the REAL example with zero AZURE_* env
>   (types/tier-3/api_version/DERIVED runtime tier). Gate: gateway suite **596 passed / 2 skipped**,
>   ruff + mypy --strict clean (CI-parity container); boot probe (example mounted, no AZURE_* env):
>   key-less providers skipped non-fatally, /health 200. Live smoke vs a real Foundry resource =
>   AZ-5, on record. Operator story: point `smart`/`fast`/`budget` at Foundry deployments via the
>   Models page (hot-apply proven in ONBOARD-0) — GPT + Mistral-Large-3 agent-capable with ZERO code;
>   Claude joins after AZ-2b. REMEMBER the `gateway-config` NAMED-VOLUME trap: the example seeds
>   FIRST boot only; existing stacks edit the live gateway.yaml/admin API.
> - **AZ-2b ✓ SHIPPED — Anthropic adapter tool-calling (RETIRES fork blocker #2; Claude agent-capable
>   direct AND on Foundry).** `gateway/app/providers/anthropic.py`: request — `_translate_tools`
>   (function→input_schema), `_translate_tool_choice` (auto/required/none/named + parallel_tool_calls
>   false→disable_parallel_tool_use), assistant `tool_calls`→`tool_use` blocks (JSON-string args
>   parsed; ""/malformed/**RecursionError from deep nesting — security-review catch**→`{}`; missing id
>   synthesized `call_lqgw_`), CONSECUTIVE tool messages MERGE into one user turn of `tool_result`
>   blocks (parallel fan-out breaks without it), `_extract_text` ends the block-content-collapses-to-""
>   behavior (langchain 1.x block form now translates); response — `tool_use`→OpenAI `tool_calls`
>   (args re-serialized), content None only when tool-calls-only; streaming — `content_block_start`
>   opening delta (real Anthropic id ⇒ F0-S9 by construction) + `input_json_delta` continuations,
>   OpenAI index = ordinal over TOOL CALLS ONLY (not Anthropic's block index). Doc flips:
>   CLAUDE.md blocker #2 RESOLVED, example TEXT-ONLY comments → tool-capable, schema docstrings.
>   Gate: gateway suite **616 passed / 2 skipped** (baseline 596; wire-format reviewer: zero findings;
>   conformance reviewer independently re-ran the suite), ruff + mypy --strict clean. Live smoke vs a
>   real Anthropic/Foundry key DEFERRED to AZ-5 on record (no key on this box; respx route-level tests
>   prove tools survive app+middleware unary+streaming).
> - **NEXT ▶ AZ-5 — Azure VM sandbox runbook** (draft exists: reviewed, stashed in session scratchpad
>   `azure-vm-sandbox.md`; land as `docs/fork/runbooks/azure-vm-sandbox.md` with the Claude sections
>   updated to post-AZ-2b tool-capable reality + §5.4 gaining an azure-claude tool smoke).
> - **AZ-5 — Azure VM sandbox runbook** (compose on an Azure VM; secrets via env; per-provider
>   synthetic smoke commands from the maintainer's brief; region: **Sweden Central or East US2** —
>   Claude's restriction binds; builds on `docs/fork/runbooks/staging-bringup.md` patterns). AZ-4b
>   (Voyage) stays DEFERRED until this resource exists; AZ-6 (AKS/Entra) unplanned.
> - **BRAND-1 — tenant white-labeling (maintainer, 2026-07-07: clients brand the product — palette,
>   logo, product name — WITHOUT coding; task #480).** The substrate makes this cheap BY DESIGN:
>   (a) the ADR-F013 token layer means palette = overriding a handful of `--lq-*` CSS custom
>   properties at runtime (light+dark variants); (b) the Oscar-Edition rebrand slice ALREADY MAPPED
>   every product-name surface (12: app.html shell title, CockpitHeader wordmark, DualBrandingFooter,
>   8 per-page title suffixes) — see the rebrand addendum's KEEP boundary. Shape: one small
>   deployment-level branding row (product_name, logo file ref, palette overrides as a validated
>   token subset) + `GET /api/v1/branding` (unauth, cacheable — the shell fetches at boot, injects
>   CSS vars, swaps wordmark/titles/favicon) + an admin Branding page (name field, colour pickers
>   w/ contrast validation, logo upload — RASTER ONLY at first: SVG can carry scripts) + wizard
>   passthrough (setup-tenant.sh seeds BRAND_* from the manifest). Emails: invite/reset templates
>   must read the configured name too. HARD LINES: NOTICES.md + footer attribution stay intact
>   (Apache-2.0 provenance is not brandable); `lq-ai-*`/`--lq-*`/`LQ_AI_*` code identifiers NEVER
>   rename (the rebrand KEEP boundary); Word add-in manifest stays deferred. Option-A
>   stack-per-tenant means deployment-level branding IS tenant-level — no per-org rows needed.
>   Org-admin edits it (their brand); operator pre-seeds via wizard. Slot: after AZ-2b (or parallel
>   to AZ-5 — disjoint files).
> - **B-0 — module-model ADR + milestone re-plan (starts Workstream B).** One vocabulary: module =
>   skill | knowledge | playbook | tool group | sub-agent profile; how org-AUTHORED content enters the
>   Library (reopens ADR-F065 D7 WITH the injection harness it demanded — org-authored skills are a
>   prompt-injection surface); what an "agent profile" is. Then re-plan B-1…B-7 (House Brief page →
>   org skills → knowledge → playbooks → sub-agent config → HITL policy (needs a langgraph-interrupts
>   research spike) → the wizard, absorbing ONBOARD-1/2 + G13/#473) as its own milestone doc.
> - **GOTCHAS:** background Workflow runs are SESSION-scoped — after a compaction, resume from the
>   branch diff + this banner, not the run id. Strays stay uncommitted (`sample-documents/`,
>   `api/tests/agents/scenarios/test_*_live.py`). Ruff CI-parity trap (run CI's exact version +
>   commands). SKILL.md colon-space guard applies to the surgical-redline edit. Dev box: run full
>   suites ALONE (6.3 GiB, no swap — [[devbox-oom-shield]]).
> ═══════════════════════════════════════════════════════════════════════════════════════════════════════

> ═══════════════════════════════════════════════════════════════════════════════════════════════════════
> ▶▶▶ **PIVOT (2026-07-02): SAAS — HOSTED PRODUCT. Maintainer-directed; the CURRENT direction.**
> Make the fork hostable: companies register an org (tenant) → admin → users, on operator-hosted,
> EU-resident, **dedicated stacks (one per tenant)** — while **self-hosting from GitHub stays supported**
> (three delivery modes; the hosted offering is the market-awareness channel). Governing docs (read in
> this order): **`docs/fork/plans/SAAS-HOSTING.md`** (plan of record: recon findings with file:line
> evidence, the A/B architecture decision, hosting = Hetzner ~€36–45/mo base, the update pipeline, the
> §6 security gate, §10 decision table) → **ADR-F058** (charter: 3 delivery modes; Mode-3 shared-schema
> RECORDED + trigger-gated (full trigger set in F058); A→B shape = COEXIST; day-one rules:
> S3 `tenants/<id>/` keys, fleet skew ≤ N-1, per-tenant monthly spend ceiling, PRC-model fencing,
> platform-vs-org admin split) → `MILESTONES.md § SAAS` (ladder SAAS-0…8A) →
> `plans/SAAS-COMMERCIAL-PACK.md` + `plans/SAAS-AIACT-SELF-ASSESSMENT.md`. Memory: [[saas-hosting-pivot]].
>
> - **WORKING MODEL (maintainer, 2026-07-02):** the lead model (Fable 5) DRAFTS small slices,
>   ORCHESTRATES, and runs ALL verification/tests/review; **implementation is delegated to smaller
>   models** (Sonnet 5 default; Opus 4.8 for complex work — migrations, auth/crypto, RLS). Compaction
>   expected roughly per slice — this banner + memory must always carry the goal and the NEXT slice.
> - **SAAS-0 ✓ SHIPPED (branch `fork/saas-0-hosted-saas-charter`, base main — doc-only):** ADR-F058
>   **ACCEPTED (maintainer, 2026-07-02)** + product name DECIDED at acceptance: **"LQ.AI Oscar
>   Edition"** (upstream's name is a group the maintainer belongs to — F001 tension dissolved,
>   SAAS-3 public DNS unblocked); NORTH-STAR **addendum** (invariant #4 SURVIVES — hosted = per-tenant
>   stacks; do NOT bake org_id into slices ahead of the Mode-3 trigger); MILESTONES § SAAS;
>   commercial-pack checklist (MSA/SLA/AUP/DPA/IR/billing — lawyer-maintainer owns; ALL are
>   first-paying-tenant blockers, not staging blockers); AI-Act self-assessment (expected verdict
>   LIMITED/art50_transparency — seal the `verdict_hash` once PR #190 merges); SAAS-HOSTING.md committed.
> - **SAAS-1 ✓ SHIPPED (branch `fork/saas-1-deploy-pipeline`) — pipeline to a deployable artifact.**
>   First slice run under the delegation working model (Sonnet implemented in a worktree; lead
>   verified + reviewed). Landed: `release.yml` GHCR namespace → `sarturko-maker`; NEW `images.yml`
>   (push-to-main `:sha-<12>`+`:main` builds, gha cache, all 3 services unconditionally — deliberate
>   simplicity); NEW `docker-compose.prod.yml` (Mode-2 per-tenant stack: image refs only, ZERO host
>   ports, mem_limits on all 8 services ≈12.7 GB, `${VAR:?}` secrets, NO MinIO — external S3 required);
>   api image bakes `skills/` via REPO-ROOT build context (+ root `.dockerignore`, atomic across
>   Dockerfile/dev-compose/workflows; `Dockerfile.dev` untouched); PR #186 absorbed by merging it;
>   Dependabot (deepagents ignored ENTIRELY — exact 0.x pin, a major-only ignore doesn't silence it);
>   weekly Trivy (SARIF needs `limit-severities-for-sarif: true` or the severity filter is IGNORED);
>   fork `SECURITY.md` (GitHub Security Advisories only; Private Vulnerability Reporting toggle
>   ENABLED on the repo 2026-07-02). Review catches worth remembering: `skills/community` is a
>   SUBMODULE → CI build checkouts need `submodules: true` or images silently ship it empty;
>   ingest-worker now forwards `EMBEDDING_PROVIDER` in BOTH composes (fault (1) of the ADR-F056
>   incident). NOTE: `deploy/helm/lq-ai/` EXISTS (SAAS-0 recon claimed it didn't) — unmaintained;
>   deprecate-or-adopt is an open maintainer decision.
> - **SAAS-2 ✓ SHIPPED (branch `fork/saas-2-hardening`, PR #212) — internet-exposure hardening pack.**
>   Implemented by Opus in a worktree; lead verified + reviewed (deep security pass — auth/crypto path).
>   ADR-F059 (proposed). Landed: (1) Redis rate limiting (per-IP + per-account, hand-rolled atomic Lua
>   fixed-window on the EXISTING redis client — NO new dep) on login/refresh/mfa-verify/change-password/
>   mfa-manage + the unauth `/admin/bootstrap-status` probe; 429 + Retry-After, uniform shape (no
>   existence leak), FAIL-OPEN on Redis fault (RedisError = quiet; other exc = `log.exception`, still
>   open); DI via `app.state` + `get_rate_limiter`. (2) `/auth/refresh` HMAC index — migration **0084**
>   (chains off 0083; DELETEs sessions, drops bcrypt `refresh_token_hash`, adds `refresh_token_hmac`
>   VARCHAR(64) NOT NULL UNIQUE); verifier = HMAC-SHA256 with a domain-separated key derived from
>   `jwt_secret`; single indexed `.with_for_update()` lookup preserves the double-spend theft signal;
>   kills the O(n) global bcrypt scan (deferred since PR #47). (3) `deploy/caddy/Caddyfile` (+README,
>   `caddy validate`-clean) — uniform-404 edge-deny of `/api/v1/internal/*`, **`/api/v1/wopi/*`** (review
>   catch S1 — Collabora reaches WOPI over the compose-internal `api:8000`, never the edge), `/metrics`
>   (all via named `path` matchers = bare-prefix + wildcard); HSTS/nosniff/Referrer/Permissions headers +
>   frame-ancestors 'self' (Collabora iframe preserved) + report-only CSP; access-log `access_token`
>   redaction; SSE `flush_interval -1`. (4) trusted-proxy: `FORWARDED_ALLOW_IPS` in prod compose only
>   (uvicorn ≥0.32 proxy-headers on by default, reads env natively — no entrypoint change). (5) boot
>   assertion `assert_boot_secrets_configured` (refuse non-dev boot on default/empty `jwt_secret`); dev
>   compose sets `LQ_AI_DEV_MODE=true`. (6) WOPI: uvicorn access-log scrub filter + Caddy redaction;
>   **TTL stayed 10h** (review catch S3 — the editor has NO token-renewal path, so 1h would 401 long
>   sessions; edge-deny + scrub are the complete fix); proof-key DEFERRED (ADR finding). Rate-limit
>   knobs forwarded in prod compose (`${VAR:-default}`) so they're operator-tunable (S4); generous dev
>   login limits so Cypress e2e doesn't flake. Review verdict SHIP-AFTER-FIXES → all S1–S7 + nits
>   applied (WOPI edge-deny, account-lockout DoS recorded in ADR D3, TTL reverted, tunability fixed,
>   narrowed fail-open except, db-schema.md updated, wiring drift-guard test for every auth endpoint).
>   **TRAPS:** Caddy `handle` takes ONE matcher — multi-path needs a named `@name path a b` matcher;
>   the account-login bucket keys on the submitted email = a known-victim lockout DoS (accepted v1,
>   `RATE_LIMIT_LOGIN_ACCOUNT_PER_WINDOW` is the lever); test_migrations `partial_indexes_exist` had to
>   drop the bcrypt index; 0084 will re-parent when the AIC stack rebases.
> - **SAAS-3a ✓ SHIPPED (branch `fork/saas-3a-staging-ready`, off main) — the staging-ready substrate.**
>   Authored by the lead (Opus — complex security-sensitive infra per the working model); independent
>   fresh-context adversarial security review. **ADR-F060 (proposed).** Landed: **custom Caddy image**
>   (`deploy/caddy/Dockerfile`, xcaddy `caddy:2.11.4` + `caddy-dns/hetzner@v1.0.0`, Caddyfile BAKED in —
>   prod host has no checkout) published by `images.yml` (one matrix entry) + the **`caddy` SERVICE** in
>   `docker-compose.prod.yml` (the ONLY host-ports block: 80/443 tcp+443/udp, joins the stack net,
>   persisted `caddy-data`/`caddy-config`, admin-API healthcheck); Caddyfile gains a wildcard **DNS-01**
>   `tls { dns hetzner {env…} }` block (DNS-01 even for staging = prod dress-rehearsal + CT-log hygiene;
>   validates only in the custom image). `scripts/deploy.sh` (pull → dedicated `-e LQ_AI_SKIP_MIGRATIONS=1
>   … alembic upgrade head` → `up -d --wait` → retrying public smoke; rejects any tag not `sha-<hex>`),
>   `deploy-staging.yml` (`workflow_run` after Images + `workflow_dispatch`, `environment: staging`, raw
>   pinned-host-key SSH, no third-party actions). `scripts/backup.sh` (`pg_dump -Fc` IN-container | `age -r`
>   asymmetric → dockerized aws-cli → `tenants/<id>/backups/`, PGDMP-magic guard, dead-man on success only)
>   + `scripts/restore-drill.sh` (latest → decrypt with the operator identity → throwaway pgvector →
>   assert `alembic_version`+`users`) — **verified END-TO-END vs MinIO+pgvector with real age/pg_dump/
>   pg_restore**. `scripts/gen-secrets.sh` (stdout only; hex secrets + a valid Fernet master key).
>   `.env.prod.example` (placeholders only; NEW guard test `api/tests/test_env_prod_example.py` +
>   `!.env.prod.example` gitignore negation — it was caught by the `.env.*` catch-all). `deploy/status/`
>   (Uptime Kuma, SEPARATE stack), `deploy/dns/` (A/AAAA/CAA + SPF/DKIM/DMARC), the SAAS-3b runbook. Also
>   forwarded optional `LQ_AI_GATEWAY_MASTER_KEY` in the gateway service (closes the Fernet-encrypted-
>   provider-keys gap). **VERIFIED (all local, no box):** caddy image builds + `caddy validate` clean;
>   `compose config` valid (prod + status); `shellcheck` clean (one annotated SC2016); `actionlint` clean
>   (one annotated SC2029); guard test 3/3; the backup↔restore round-trip. **TRAPS:** stock `caddy:2`
>   can't validate the DNS block (custom image only); `.env.prod.example` needs the gitignore negation;
>   the aws-cli pin `amazon/aws-cli:2.17.0` exists (verified). Merge under the ADR-F005 gate.
> - **SAAS-rebrand ✓ SHIPPED (branch `fork/saas-rebrand-oscar-edition`) — "LQ.AI Oscar Edition"
>   executed.** The ADR-F058-accepted name applied to the 12 user-facing product-name surfaces
>   (shell `<title>` in `app.html`, CockpitHeader wordmark two-weight lockup, DualBrandingFooter,
>   8 per-page `<title>` suffixes, README H1 + a fork-identity note), scoped by a 4-lens branding
>   audit. **Surgical display-strings-only** — the KEEP boundary (recorded in the ADR-F058
>   rebrand-execution addendum + `plans/SAAS-REBRAND-oscar-edition.md`) protects the `lq-ai/` code
>   namespace, `--lq-*` CSS tokens, `LQ_AI_*` env vars, `lq-ai-*` package/image/testid identifiers
>   (~1,300 Cypress-asserted), `X-LQ-AI-*` wire headers, infra literals, and ALL provenance
>   (NOTICES.md untouched by design — its entries are extend-never-edit; `LegalQuants` = org name,
>   stays). DECIDE calls on record: running-prose/`Sign in to LQ.AI`/`/learn`/FastAPI-docs-titles/
>   TOTP-issuer all KEEP the short mark. **Deferred:** Word add-in display-name + manifest
>   tokenisation (own M365-validation pass); README body rewrite; DevForkCallout repo-URL repoint
>   (maintainer call). **TRAP:** "Oscar" in `ropa/*` comments = a COMPETITOR product, not us — never
>   rename those.
> - **REDIRECT (maintainer, 2026-07-03): bring-up box = an IONOS VPS (not Hetzner); weekend task.**
>   Before then, build the SETUP ladder from **`docs/fork/plans/SAAS-SETUP-onboarding-architecture.md`**
>   (DRAFT for maintainer edit; grounded in a 5-lens recon): 3-actor model (operator outside the app /
>   org-admin / member; fence = new `operator` role — provider-keys/aliases/gateway-config/tier-policy
>   become operator-only, per the route table in the plan §1); config hierarchy deployment→area→matter
>   (Level 2 = ADR-F054, ALREADY SHIPPED; Level 0 `deployment_capability_toggles` = new; keystone =
>   tool-group REGISTRY replacing composition.py's per-area elif chain — supersedes F054 D1, decision
>   row #9 needs maintainer sign-off); operator CLI wizard (manifest → .env + gateway seed + DNS
>   instructions + deploy; two compose gaps to fix: FIRST_RUN_ADMIN_EMAIL + SMTP not forwarded);
>   SAAS-4 absorbed as SETUP-3 (invites/reset/verification + fence). Slices: SETUP-1 multi-DNS edge ✓
>   / SETUP-2 wizard (both weekend-critical) / SETUP-3a/b lifecycle+UI / SETUP-4a/b registry+areas UI /
>   SETUP-5 reconcile. AIC-3 PARKED (task #456).
> - **SETUP-1 ✓ (branch `fork/setup-1-multi-dns-edge`) — multi-DNS edge (Option A, ADR-F060
>   amendment):** the caddy image now compiles `caddy-dns/hetzner@v1.0.0` + `caddy-dns/ionos@v1.2.0`;
>   the Caddyfile selects per deployment via PARSE-time `dns {$LQ_AI_DNS_PROVIDER:hetzner}
>   {env.LQ_AI_DNS_API_TOKEN}` (unknown module fails validate/startup loudly — proven by a negative
>   test); env generalised `HETZNER_DNS_API_TOKEN`→`LQ_AI_DNS_API_TOKEN` (+`LQ_AI_DNS_PROVIDER`,
>   default hetzner) across compose/.env.prod.example/READMEs; runbook de-Hetzner'd (IONOS VPS/DNS/S3
>   paths). caddy-dns/cloudflare DELIBERATELY absent (no release tags — pin a commit if ever needed).
>   TRAP: `{$VAR}` parse-time substitution CAN pick the dns module; `{env.VAR}` runtime CANNOT.
> - **PLAN RATIFIED (maintainer "proceed as you suggest", 2026-07-03):** every §7 recommendation is
>   the decision of record — notably row 9 (ADR-F054 D1 SUPERSEDED: tool-group availability becomes
>   DATA) and row 5 (`operator` in-app role). Plan status flipped to ACCEPTED.
> - **SETUP-2 ✓ (branch `fork/setup-2-tenant-wizard`) — the operator tenant-setup wizard.**
>   Implemented by Opus in a worktree (working model); lead verified + security-reviewed.
>   `scripts/setup-tenant.sh` (interactive or `--manifest` flat KEY=VALUE; SECRETS FORBIDDEN in the
>   manifest — the script refuses; secrets come from env or silent prompts): renders `.env.prod`
>   (0600, no-overwrite without `--force`) + `deploy/gateway/tenant-gateway.yaml.example`-based seed
>   (Anthropic-only, `api_key_env` indirection — NO key material in yaml; **tier 4** = honest cloud
>   tier, 3 for ZDR; no PRC tokens) + `dns-records.txt` + backup cron + optional `--create-bucket`
>   (dockerized aws-cli, versioning + ~GFS lifecycle) + `deploy.sh` + a ONE-TIME admin-password
>   handover (log-scrape of `First-run admin password`). Fixed the two prod-compose gaps:
>   `FIRST_RUN_ADMIN_EMAIL` (api) + `SMTP_*` (api AND arq-worker — that's where autonomous mail
>   sends) now forwarded, optional `${VAR:-}`; `.env.prod.example` extended; `admin_bootstrap.py`
>   env-name doc bug fixed (`FIRST_RUN_ADMIN_EMAIL`, config.py has no env_prefix). Two-round review
>   (round 2 security-focused) found + FIXED: (S1) S3 secrets out of docker argv (`-e VAR` names only,
>   values env-prefixed — argv is world-readable via /proc/*/cmdline) in `--create-bucket` AND the
>   same pre-existing pattern in `scripts/backup.sh`; (S2) generic conservative charset fence +
>   anchored per-field formats on ALL manifest values (the backup cron root-executes `.env.prod` via
>   `set -a; . file` — unvalidated values = latent root RCE; ADMIN_EMAIL is customer-originated) +
>   refusal tests; (N3) slug regex no edge hyphens; (N4) `rm -f` before `--force` overwrite (mode
>   window); (N5) wildcard PUBLIC_HOST requires explicit PUBLIC_ORIGIN; (N6) secret fence +=
>   `*APPLICATION_CREDENTIALS`; (N7) `awscli()` dedup + 0600 tests for gateway.yaml/manifest.
>   Boxless gate: pytest **25 passed** (22 wizard + 3 guard) in the dev image; shellcheck CLEAN;
>   `bash -n` OK; ruff clean. NOT live-verified: the deploy+handover path + `--create-bucket`
>   (needs the box — weekend). Session traps: Edit tool needs a fresh Read after branch switches;
>   `gh pr checks` exits 8 while checks are pending; bare `vitest` is watch-mode (use
>   `CI=1 npx vitest run`); commit strays NEVER (`sample-documents/`,
>   `api/tests/agents/scenarios/test_*_live.py`).
> - **SETUP-3a ✓ (branch `fork/setup-3a-user-lifecycle`, off main) — user-lifecycle backend + operator
>   fence. ADR-F061 (proposed), migration 0085.** Opus implemented in a worktree (working model); lead
>   verified + ran an INDEPENDENT deep security review (auth path) + an isolated live smoke. Plan:
>   `docs/fork/plans/SETUP-3a-user-lifecycle-operator-fence.md`. Landed: ONE `user_auth_tokens` table
>   (`purpose` invite 7d | password_reset 1h; single-use, opaque `token_urlsafe(32)`, ONLY a
>   domain-separated HMAC-SHA256 at rest per ADR-F059; atomic consume under `FOR UPDATE`). Admin
>   invite CRUD + resend/revoke (one live invite per email) + `POST /auth/accept-invite` (creates the
>   user at the invite's role, `email_verified_at`); `POST /auth/password-reset-request` (uniform 202
>   anti-enum, **SMTP send scheduled via `BackgroundTasks` after the response** so exists/not-exists
>   return in equal time — the login handler's timing-equalisation lesson) + `/auth/password-reset`
>   (revokes ALL sessions + sibling reset tokens); admin `disable`/`enable` (`users.disabled_at`
>   enforced at login = byte-identical 401, `get_current_user`, refresh). **THE FENCE:** new `operator`
>   role + `OperatorUser` dep (403) on aliases×5/provider-keys×4/GET config/PATCH tier-policy/
>   override-tier-floor; GET tier-policy stays org-admin (transparency). **ESCALATION GUARD (D3, the
>   review's #1 target — INTACT):** `operator` is NOT in `update_user_role`'s `_ROLE_ENUM` (422),
>   invites can't carry it (CHECK + 422), every role/disable path refuses an operator target (403), the
>   JWT carries no role (fence reads the fresh DB row), operator is minted ONLY by bootstrap
>   (`FIRST_RUN_OPERATOR_EMAIL`). Mail transport generalised to `app/email.py` (notify_email delegates,
>   never-raise preserved). Gate: full api suite **3191 passed/42 skip**; lead re-ran the 5 touched
>   files **111 passed**; ruff+mypy clean; mig 0085 up/down/up on throwaway pgvector; isolated live
>   smoke 17/19 (the 2 "fails" = harness expected 200 for change-password which correctly 204s) —
>   evidence `docs/fork/evidence/setup-3a/live-smoke.md`. Security review = SHIP-AFTER-FIXES → 4 fixes
>   applied (reset timing oracle → background send; reset-token multiplicity → revoke prior+sibling;
>   scheme-only base-url → path fallback; confirm-path disabled_at re-check). **TRAP:** the api test
>   conftest CREATEs its own `lq_ai_test_<hex>` from `{base}/postgres` — point `DATABASE_URL` at the
>   real dev postgres creds (NOT a made-up dbname) or every DB test errors on connect; it never touches
>   the AIC-chain dev DB. Migration-number trap holds: 0085 is main's next free; AIC #188-190 renumber
>   on THEIR rebase.
> - **SETUP-3b ✓ — Users admin UI + onboarding pages + wizard email handover. ADR-F061 ADDENDUM
>   (D1/D6/D7/D8 + Q1 deferral), NO migration, NO new route/dep.** Sonnet-line implemented in a
>   worktree; plan `docs/fork/plans/SETUP-3b-users-admin-ui-onboarding.md`. Landed: (A) emailed
>   links now carry the REAL paths `/lq-ai/accept-invite|reset-password` (D1) +
>   `bootstrap-status.hosted` (D8, derived from `first_run_operator_email`). (B/C)
>   `/lq-ai/admin/users` — generation-B (ModalShell/Table/Badge/Alert/FormControl, semantic
>   tokens): role select w/ last-admin handling, disable/enable w/ inline confirm, self+operator
>   rows LOCKED + "Platform operator" badge (D6 — visible, badged, locked; filter offers
>   all/admin/member/viewer only), invites create-modal/resend/revoke, SMTP-off `accept_url`
>   copy-to-clipboard handover panel (never logged). (D) unauth `/lq-ai/accept-invite` +
>   dual-state `/lq-ai/reset-password` (uniform "if an account exists" copy — anti-enum preserved
>   in UI), both in `isAuthExempt()`; login gains "Forgot your password?" + hosted-aware hint
>   swap. (E) fence audit `docs/fork/evidence/setup-3b/fence-audit.md`: `/admin/models` page-guard
>   `role==='operator'` + sub-nav link hidden; `DevRoleManagementCard` DELETED (D5 — function
>   moved to Users page); provider-keys/tier-policy have NO web consumers (nothing to gate);
>   RefusalMessageBubble's tier-floor-override button now OPERATOR-ONLY (review fix — ChatPanel
>   previously collapsed operator→'admin', so the true role is now passed through the bubble chain).
>   (F) wizard: SMTP-on handover = curl POST `/auth/password-reset-request` for ADMIN_EMAIL w/
>   deploy.sh-style retries, NEVER scrapes/prints the password; SMTP-off keeps the labelled
>   log-scrape fallback; optional `OPERATOR_EMAIL` → `FIRST_RUN_OPERATOR_EMAIL` (written/omitted;
>   email+charset fences); handover tests run the REAL deploy path against docker/curl PATH shims.
>   **TRAP:** wizard/env-example tests resolve `_REPO_ROOT = parents[2]` — the containerized run
>   needs `-v scripts:/scripts -v deploy:/deploy -v docker-compose.prod.yml:/docker-compose.prod.yml
>   -v .env.prod.example:/.env.prod.example` (ro) or 16 tests fail on a missing repo root.
>   Adversarial review: security lens ZERO findings; 8 review fixes landed, headline TRAP =
>   `bootstrap-status.hosted` must derive by TRUTHINESS, not `is not None` — prod compose always
>   injects `${FIRST_RUN_OPERATOR_EMAIL:-}` so an unset key reaches pydantic-settings as `""`
>   (same trap for ANY optional `${VAR:-}`-forwarded setting). Cypress specs updated for the
>   deleted role card + operator-only models page (Cypress is not CI-gated — keep specs honest).
> - **SETUP-4a ✓ — tool-group registry (availability as DATA) + practice-area CRUD + deployment-wide
>   (Level 0) capability toggles. ADR-F062 (PROPOSED), migration 0086 (chains off 0085). Opus in a
>   worktree; plan `docs/fork/plans/SETUP-4a-tool-group-registry.md`.** Landed: (A) `TOOL_GROUP_REGISTRY`
>   (code) in `app/agents/capabilities.py` maps a group NAME → `ToolGroupDef` (spec + builder adapter +
>   optional ledger factory); insertion order (redlining→tabular→ropa→assessment) IS the canonical group
>   order (D4). (B) migration 0086: `practice_area_tool_groups` (seeded names-only from today's map,
>   idempotent `_seed`, CAST trap) + `deployment_capability_toggles` (Level 0, sparse, NO seed).
>   (C) the composition elif chain → a registry loop (`build_area_tool_groups`): a group grants iff
>   (row present) AND (registry entry) AND (no per-matter toggle) AND (no Level-0 toggle) — absence at
>   ANY level = never built, never in `GuardContext.granted`; grants/`*_TOOL_NAMES`/guard UNTOUCHED.
>   `build_area_inventory` is now DATA-driven (`tool_group_keys`) + Level-0-aware (`deployment_toggles`)
>   — the ONE chokepoint the panel + composition share. (D) endpoints (all AdminUser, 404-not-403):
>   POST `/practice-areas` (slug regex, `agent_config` reuse, `tool_groups` registry-validated,
>   position auto-append, dup-409) + DELETE `/{key}` (409-with-count while a non-archived matter
>   references it, else CASCADE) + POST/DELETE `/{key}/tool-groups[/{group_key}]` (mirror skills pair)
>   + GET/PATCH `/admin/capabilities` (Level-0 inventory + sparse writes, reject-don't-sanitize,
>   audited kinds/keys/enabled). Cross-area attach is now a FEATURE (supersedes F054-D1 for
>   availability; grants stay code). **HARD GATE PASSED:** `tests/agents/test_registry_parity.py`
>   pins FROZEN pre-refactor tool-name literals per seeded area → the registry loop reproduces them
>   byte-identically (tools/order/ledger/`tabular_enabled`). Gates: api suite green; migration 0086
>   up/down/up on throwaway pgvector; ruff+mypy clean. **TRAP re-confirmed:** run `ruff format` with
>   the repo-ROOT `ruff.toml` mounted (line-length 100) — the dev image's default (88) + magic trailing
>   comma silently rewraps pre-existing lines; dev-ruff 0.15.20 also false-flags migration import
>   blocks (I001) that CI's pip-cached older ruff accepts (matched 0056/0084 precedent, left as-is).
>   NO web UI (SETUP-4b). NOT touched: F054 status flip/addendum (SETUP-5).
>   **Adversarial review (3 lenses + independent verification): 3 should-fixes CONFIRMED + 4 nits,
>   ALL FIXED (`e4355dd0`); full suite after fixes 3251/43.** Review traps worth carrying: (1)
>   count-then-delete on an FK parent is a TOCTOU — FK inserts take FOR KEY SHARE, which does NOT
>   conflict with a plain SELECT; lock the parent `FOR UPDATE` BEFORE the guard count. (2) parity/
>   golden assertions must drive PRODUCTION seams — comparing a test's own literals to each other is
>   a tautology. (3) a chokepoint that pre-filters makes downstream warnings unreachable — log at
>   the drop point. (4) an optional kwarg at a security chokepoint fails OPEN — make it required
>   (`deployment_toggles`). Isolated live smoke **21/21** (dev stack still AIC-captive):
>   seed/create/attach/detach/Level-0-narrows-matter-panel/delete-semantics/authz-fence — evidence
>   `docs/fork/evidence/setup-4a/live-smoke.md`.
> - **SETUP-4b ✓ — Practice Areas + Capabilities admin surfaces (web UI over the 4a endpoints).
>   ADR-F062 addendum, NO migration. Plan `docs/fork/plans/SETUP-4b-areas-capabilities-admin-ui.md`
>   (D1-D11). Sonnet-line implemented in a worktree; lead verified/reviewed/live-tested.** Landed:
>   (a) `/lq-ai/admin/areas` — gen-B list (position order, status badge honest to the `configured`
>   derivation — D5: NO fake enable toggle, "Add doctrine to activate"), create modal
>   (registry-bounded tool-group checkboxes), ↑/↓ reorder; `/lq-ai/admin/areas/[key]` detail —
>   edit name/unit-label/doctrine/tier-floor (dirty-fields-only PATCH), roster JSON (D6, parse-gated,
>   server 400 verbatim), three bind cards (groups/skills/playbooks, catalogs from
>   GET /admin/capabilities — D7), delete w/ 409 live-matter count UX. (b) `/lq-ai/admin/capabilities`
>   — Level-0 sections w/ optimistic switch grammar, MCP placeholder, models READ-ONLY from the
>   member-visible `GET /api/v1/models` (graceful unavailable state). (c) Backend enablers:
>   `PracticeAreaRead` += `bound_tool_groups` (REGISTRY-canonical order) + `bound_playbooks`
>   (name,id tiebreak); PATCH += name/unit_label (explicit-null rejected 422 by field_validator —
>   the `str | None` union arm SKIPS min_length for null, review catch); NEW
>   `POST /practice-areas/reorder` (exact-permutation 422, FOR UPDATE ordered by key); openapi
>   count 171. (d) Shared `web/src/lib/lq-ai/admin/page-helpers.ts` (describeMutationError +
>   catalog helpers; users page re-pointed). **Review traps worth carrying:** (1) `GET
>   /admin/model-menu` was built then DELETED in review — an admin-only projection of data the
>   member-visible /models already returns verbatim is redundant surface; check who can ALREADY
>   see the data before minting a "stripped" endpoint. (2) optimistic-UI revert must restore ONLY
>   the failed entry — a whole-state snapshot clobbers interleaved toggles (the matter-level
>   CapabilitiesPanel.svelte still has this latent pattern — recorded follow-up, not fixed here).
>   (3) Cypress `cypress run` TRASHES `cypress/screenshots/` per run — copy evidence out
>   immediately. Gate: full api suite **3264/43** (fixed branch), web vitest 105 files/1141,
>   svelte-check 0 errors, isolated API smoke **32/32**, browser pass (real login → create area →
>   attach group → Level-0 toggle flip, Cypress 1/1 + width probe no-overflow) — evidence
>   `docs/fork/evidence/setup-4b/live-smoke.md` + 4 screenshots.
> - **SETUP-5a ✓ — ADR reconcile paperwork + budget-profile defaults. ADR-F063 (proposed),
>   migration 0087 (chains off 0086). Plan `docs/fork/plans/SETUP-5a-reconcile-budget-defaults.md`.
>   Sonnet-line implemented in a worktree (survived a mid-slice session-limit death — resumed via
>   SendMessage with full context, 4th proven recovery); lead verified/reviewed/live-tested.**
>   Landed: (A) paperwork — **F054 flipped to accepted** with a D1-supersession addendum (D1
>   availability-as-code superseded by F062's registry+rows for AVAILABILITY ONLY; grants stay
>   code — option-2's "grants never live in data" survives intact; D2–D6 unchanged) + **F062
>   flipped to accepted** (maintainer-ratified plan §7 row 9); MILESTONES hygiene (4b done-line,
>   backlog += SETUP-3c / SETUP-6 / matter-CapabilitiesPanel snapshot-revert defect). (B) backend —
>   mig 0087 `practice_areas.default_budget_profile` TEXT NULL + named CHECK (IS NULL OR IN the 3
>   profiles); `Settings.run_default_budget_profile` (env `RUN_DEFAULT_BUDGET_PROFILE`) with a
>   before-validator normalizing ""→None (the `${VAR:-}` trap) and REFUSING boot on unknown values;
>   run-create resolves the chain **run-explicit > area default > deployment default > balanced**
>   ONCE and persists the RESOLVED value on `agent_runs.budget_profile` (a later default change
>   never re-prices an existing run — proven live); `AgentRunCreate.budget_profile` → `| None`;
>   compose (dev+prod, api+arq)/.env examples/wizard all forward the knob (wizard: anchored regex
>   fence BEFORE the .env.prod write; line omitted when unset, mirrors FIRST_RUN_OPERATOR_EMAIL).
>   (C) web — area-detail "Default budget profile" select (`lq-admin-area-budget-profile`; Inherit
>   sends an EXPLICIT null only when changed — on THIS field null CLEARS, the deliberate opposite
>   of name/unit_label's reject-null, documented at both seams); composer Budget gains a FIRST
>   "Default" option ('' ⇒ payload OMITS budget_profile). **Adversarial review (3 lenses + skeptic
>   verify): security lens ZERO findings; 1 confirmed should-fix FIXED (`1cf9109d` — the static
>   composer caption claimed "set by your area or deployment" even after an explicit pick; now
>   flips to "Applies to this run — overrides the default"); 2 refuted on record, one worth
>   knowing: a STALE browser bundle keeps sending explicit `balanced` and thereby beats a newly
>   set area default until reload — judged intended override semantics (persisted per-run, same
>   as a live user leaving the dropdown on Balanced), not a defect.** Gate: full api suite
>   **3283/43** (worktree-root mounts — 5a touches 6 repo-root files, mount them from the
>   WORKTREE); web vitest 1146/105 files, svelte-check 0 errors; mig 0087 round-trip on throwaway
>   pgvector; isolated API smoke **33/33** (two-boot harness: ""-boot + all 4 chain tiers +
>   at-create persistence + boot-rejection probe); browser pass Cypress **2/2** (null-clears PATCH
>   protocol + caption flip + payload omission live) — evidence
>   `docs/fork/evidence/setup-5a/live-smoke.md` + 4 screenshots. **TRAPS:** (1) openapi count
>   checks must count `/api/v1` paths only (`test_openapi.py:292`) — the raw dict adds
>   /health+/ready. (2) a STALE vite dev server from a previous slice's browser pass can survive
>   on :5173 and silently serve the OLD worktree — `ss -tlnp | grep 5173` and kill the NODE pid
>   (not the npx wrapper) before probing. (3) serving a worktree web app whose node_modules is a
>   symlink into the main checkout needs a temp vite config widening `server.fs.allow`, else
>   SvelteKit's client entry 403s via /@fs.
> - **SETUP-5b ✓ — tenant-data RBAC: viewer ENFORCED read-only + operator excluded from
>   cross-user tenant data. ADR-F064 (proposed — the Q1 decision, FLAGGED for maintainer review),
>   NO migration, NO new routes (171 pinned). Plan `docs/fork/plans/SETUP-5b-tenant-data-rbac.md`
>   (full route classification table). Opus implemented in a worktree (§A–§F, two lead-review
>   rounds); lead verified + ran the DEEP security pass (auth path).** Landed: (D1) ActiveUser →
>   MutatingUser on **68** tenant-data mutating routes across 15 routers INCLUDING legacy
>   /autonomous/* (mechanism: `get_autonomous_enabled_user` now takes `user: MutatingUser` —
>   role-gate stacks BEFORE the opt-in gate, zero handler churn; `halt_session` swapped directly,
>   its outside-the-opt-in-gate semantics preserved); `operator` ADDED to `_MUTATING_ROLES`
>   (mutates rows it OWNS); drift-guard `api/tests/test_mutation_rbac.py` walks app.routes and
>   pins 68 mutating / 26 admin / 8 operator / **22 allowlisted** (/auth 11, /users/me 5,
>   POST-reads 2, /wopi 2, /integrations 2). (D2) `tenant_admin_visibility(user) = is_admin AND
>   role != 'operator'` replaces bare `is_admin` at **14** seams (tabular ×3, playbooks ×10, +
>   chat_receipts — whose cross-user response ALSO changed 403→404, an existence-leak fix; the
>   implementer FOUND the 14th seam, the recon had 13). MODE-NEUTRAL framing (maintainer,
>   2026-07-05): operator = whoever runs the platform — hosting company OR the firm's own IT;
>   self-host posture in the ADR (no FIRST_RUN_OPERATOR_EMAIL ⇒ no operator row, admins keep
>   sees-all; operator/no-operator = the self-hoster's separation-of-duties dial). **Deep review
>   (4 lenses incl. an Opus bypass-hunter + skeptic verification): 4 confirmed → ALL FIXED
>   (`67afc2ba`), 3 refuted on record.** Headline fix: the WOPI WRITE path trusted token claims
>   for up to 10h after a role demotion — now re-checks role+liveness per write op via
>   `_require_live_mutating_user` (imports `_MUTATING_ROLES` so bearer/WOPI gates can't drift;
>   reads stay open; 401-as-session-invalid). Gate: full api suite (counts in the PR), role-matrix
>   smoke **30/30** on the final branch (three-layer stacking live: viewer role-403 → opted-out
>   member opt-in-403 → opted-in member 404 owner-lookup; operator cross-user probes 404 NEVER
>   403; admin sees-all + F061 fence regressions) — evidence
>   `docs/fork/evidence/setup-5b/live-smoke.md`. **TRAPS:** (1) FastAPI stacks role gates cleanly
>   by making the outer dep take the inner as a param (`get_autonomous_enabled_user(user:
>   MutatingUser)`) — prefer that over touching handlers. (2) token-authed side doors (WOPI,
>   bridge, invite links) bypass per-request role reads — any future role/fence change must audit
>   token-LIFETIME surfaces, not just bearer routes. (3) a smoke asserting "member passes the
>   gate" must account for OTHER stacked gates (the autonomous opt-in 403 ≠ the role 403 — assert
>   on body text, not just status).
> - **THE SETUP LADDER IS COMPLETE (SETUP-1 → 5b all merged).** Sequencing was decided 2026-07-05
>   — see the ONBOARD-0/STORE bullet below (which is the live pickup). The options were: (a)
>   SAAS-3b IONOS bring-up (maintainer's weekend task, runbook
>   ready); (b) SETUP-6 actor guides (on hold, below); (c) AIC-3 resume (task #456, parked "after
>   the SETUP ladder"); (d) backlog UX slices (SETUP-3c onboarding checklist, viewer
>   affordance-hiding, matter CapabilitiesPanel revert defect, T5 live cell fill). SETUP-6 — ACTOR
>   GUIDES (maintainer,
>   2026-07-04, explicitly ON HOLD until called; task #462): human-facing operating documentation,
>   one guide per F061 actor — Operator (wizard/provisioning, backups+restore drill, the fence,
>   invite handover, ongoing ops; links the staging-bringup runbook, no duplication) / Admin
>   (claiming the workspace, Users admin, areas + Level-0 capabilities, House Brief, read-only
>   transparency surfaces) / User (matters with the area agent, capabilities panel, matter memory,
>   documents/redlines/grids, budget profiles, honest limits). Suggested home `docs/guides/`;
>   sequenced after 4b/5 so the described UI exists — the operator guide is separable and can be
>   pulled forward for the weekend bring-up on request.** SETUP-3c (first-login onboarding
>   checklist: House Brief → invite users → review area defaults) split out of 3b as UX polish —
>   can ride after the ladder. SAAS-3b bring-up (maintainer, weekend, IONOS): provision
>   domain/node/DNS token/bucket → run `setup-tenant.sh` → **Proof = a real agent run on the
>   staging URL + a passed restore drill.** Then the SAAS-2 handoff hardening (pin
>   `FORWARDED_ALLOW_IPS` to Caddy's IP, promote CSP, rotate gateway key, lock Collabora egress).
>   Runbook: `docs/fork/runbooks/staging-bringup.md`.
> - **ONBOARD-0 ✓ DONE + STORE-0 ✓ (2026-07-05).**
>   ONBOARD-0 dress rehearsal: dev stack RESET onto main (maintainer-sanctioned `down -v`; fresh DB
>   @0087; admin (maintainer's own email) + operator `operator@lq-ai.internal` + one invited
>   member live — creds in the session scratchpad, passwords since changed by the maintainer where
>   prompted); full multi-role journey PROVEN (admin → invite copy-link →
>   member → Commercial agent run completed). **8 gaps → `plans/ONBOARD-admin-experience.md`**
>   (G1 boot-email asymmetry; G2 House Brief has NO web UI; G3 SMTP invites = dormant config; G4
>   Store/Library fusion; G5 skill viewer exists but unlinked; G6 blank areas; G7 FIXED — merged
>   PR #223 `2f3039e0`, replaceState-before-router-init on accept-invite/reset-password, live
>   Cypress vs :3000 2/2; G8 model routing operator-fenced + `fallback: []` everywhere + raw
>   provider error shown to member). MiniMax token plan EXHAUSTED mid-rehearsal → maintainer
>   repointed `smart`/`fast`/`budget` → `deepseek-v4-flash` LIVE via the operator Models page
>   (hot-apply works; dev gateway now runs DeepSeek — restore MiniMax only after the plan renews).
>   **PRIORITY (maintainer): "move the store vs org idea — this takes priority. We need clean and
>   clear UX."** Plan `plans/STORE-org-library.md` REVIEWED (4 decisions: name = "Store"; NO
>   operator content kill-switch — single off-state = not-in-Library; fresh orgs start EMPTY under
>   a binding non-technical-admin UX constraint (Recommended-for-{area} rail + one-click add-all);
>   existing deployments upgrade via seed-from-effective-state). **ADR-F065 proposed.**
>   STORE-1 spec executed — see the next bullet. Memory: [[onboard-milestone-plan]].
> - **STORE-1 ✓ (branch `fork/store-1-org-library`, PR #225).**
>   The Library substrate is LIVE. Opus implemented in a worktree (working model); lead verified,
>   ran the 4-lens adversarial review (security deep pass on the new admin mutation endpoints:
>   ZERO findings; 1 nit fixed — the composition.py grant-seam comment) + live-verified. Landed:
>   **mig 0088** `org_library_entries` (PK capability_kind+capability_key ∈ {skill,tool,playbook};
>   playbook key = uuid::text; adopted_by/adopted_at) — seed-from-effective-state (bound-anywhere ∧
>   not-disabled) GATED on users-table non-emptiness at migration time (fresh deployment ⇒ EMPTY
>   Library, maintainer decision 3; the gate lives in upgrade(); `_seed(conn)` stays pure /
>   idempotent / importlib-testable and tolerates the toggles table being absent via to_regclass);
>   `deployment_capability_toggles` DROPPED (implementer call recorded in the mig docstring + the
>   F065 addendum; downgrade recreates it EMPTY = lossy, on record). `build_area_inventory` kwarg
>   `deployment_toggles`→`library_entries` (REQUIRED kw-only, fail-closed posture kept), membership
>   predicate for all 3 kinds; a per-matter toggle can NOT resurrect a non-adopted capability
>   (never an entry). NEW `POST /api/v1/admin/library` (409 dup / 422 unknown-key, validated per
>   catalog like the old PATCH) + `DELETE /api/v1/admin/library/{kind}/{key}` (idempotent 204) —
>   AdminUser (the operator PASSES: platform config, F061 D3 / F064 D2); audit `library.adopt` /
>   `library.remove` / `library.update` with {kind,key} only. PATCH `/admin/capabilities` is now a
>   compat SHIM over the Library (enabled=true ⇒ adopt / false ⇒ remove); GET grows `in_library`
>   (`enabled` = deprecated alias) so the old Capabilities page keeps working — web untouched.
>   Bind-time 422 "not in your organisation's library" on the 3 attach endpoints + area
>   create-with-tool_groups, DISTINCT from the 404-unknown-registry layer. Gate: CI green; pristine
>   full suite **3347/42**; registry-parity golden UNMODIFIED; mig up/down/up on throwaway
>   pgvector; **isolated HTTP smoke 20/20** (fresh-org: whole catalog in_library=false → adopt →
>   bind lifecycle → shim → audit rows); **live upgrade rehearsal on the dev stack** — 0087→0088
>   applied on boot, seeded EXACTLY 13 skills + 4 tool groups + 0 playbooks (the maintainer's inert
>   enabled=true redlining toggle row correctly didn't subtract), users/projects/runs intact, api
>   healthy — upgrade day changed NOTHING visible (the D2 promise, proven on real data). Route pins
>   now 173 paths / 126 mutating. **TRAPS:** (1) a bare `gh pr create` resolves to the FROZEN
>   upstream — `gh repo set-default` now pinned + a CLAUDE.md line; ALWAYS pass
>   `--repo sarturko-maker/lq-ai-fork`. (2) full-suite container mounts must be the WORKTREE ROOT
>   (`-v <wt>:/repo -w /repo/api`) — an api-only mount breaks the env-example/wizard tests
>   (parents[2] repo-root resolution). (3) run the full suite ALONE on this box (CPU-contention
>   flakes ~10 timing-sensitive agents tests; identical tests pass solo). (4) container alembic
>   runs need `/skills` mounted (mig 0032 seeds built-in playbooks from it).
>   STORE-2 spec executed — see the next bullet.
> - **STORE-2 ✓ (branch `fork/store-2-store-library-pages`, PR #226) — ▶▶ PICK UP EXACTLY HERE =
>   STORE-3 (maintainer live re-rehearsal on a FRESH org = the milestone's acceptance test).**
>   The Store/Library UX is LIVE. Sonnet implemented in a worktree (working model); lead ran the
>   full gate + applied the 4 review fixes. Plan `docs/fork/plans/STORE-2-store-library-pages.md`
>   (decisions D-A…D-G); ADR-F065 STORE-2 addendum; NO migration. Landed: **Store**
>   (`/lq-ai/admin/store`) — "Recommended for {area}" rails w/ one-click Add-all (source = NEW
>   drift-guarded `RECOMMENDED_LIBRARY_SETS` in `app/agents/capabilities.py`, transcribed from the
>   six seed migrations; guard test pins every key against the real registries), kind sections w/
>   provenance badges + search + MCP placeholder, ONE verb per card; **Library**
>   (`/lq-ai/admin/library`) — where-used ("Attached to: …" computed client-side from
>   GET /practice-areas), D6 always-confirm remove modal listing area names, teaching empty state;
>   **member read-only `/lq-ai/library`** on the NEW `GET /api/v1/library` (ActiveUser — the
>   tier-config dual-exposure transparency precedent; `adopted_by` deliberately NOT on the wire;
>   dangling entries honest via label=None); old Capabilities page → onMount-goto redirect stub
>   (dead helpers deleted; MCP placeholder moved to the Store; the read-only Models section
>   DROPPED on record — it re-projected member-visible GET /models); area-detail pickers
>   Library-scoped w/ honest empty states (library-empty vs all-attached) + G5 skill links
>   (Store/Library cards, area bind rows, matter CapabilitiesPanel — link-only there); **D5
>   provenance fallback** in `derive_summary` (top-level `author:`/`version:` via model_extra,
>   str-only, `lq_ai:` wins — 35 community skills for author, 37 for version). Capability entries
>   grew `source/author/version/tags/recommended_for` (additive). Pins 173→174 paths (mutating 126
>   UNCHANGED — the only new route is a GET). Gate: CI green; pristine full suite **3369/42**
>   (+22 = the slice's tests); web vitest 1169/106 files, svelte-check 0 errors; 4-lens review
>   (security deep pass on the ActiveUser surface: ZERO findings) → 1 should-fix + 3 nits ALL
>   FIXED (`610ae79d` — "vunversioned" badge sentinel, bound-row labels must use the FULL catalog
>   while pickers stay Library-scoped, search-miss copy, dead patch client); isolated fresh-org
>   live pass **5/5 + 7/7 curl probes** (D5 live on the real community corpus; member fence;
>   adopted_by absent) + **Cypress 3/3** (teaching states / the committed net-zero
>   Store→Library loop on an upgraded-org emulation = 17 adopted entries byte-matching the 0088
>   seed / member read-only) — evidence `docs/fork/evidence/store-2/live-smoke.md` + 3 screenshots.
>   **TRAPS:** (1) Store-page testids use `kind:key`, Library-page `kind-key` — translate when a
>   spec crosses pages (caught live). (2) `cypress run` TRASHES screenshots/ per run — copy out
>   immediately (re-confirmed). (3) the vite dev server's first cold hit can fail a spec in <15s
>   pre-mutation — re-run warm. (4) a fresh-org stack has seeded BINDINGS but an empty Library —
>   a spec assuming "first unadopted entry is unattached" needs the upgraded-org emulation first.
>   **STORE-3 spec:** maintainer walks the admin journey on a FRESH org (Store → adopt via the
>   rail → bind → member run); needs either a maintainer-sanctioned dev-stack reset onto main
>   (ONBOARD-0 precedent — the current dev stack is an UPGRADED org with walkthrough data) or an
>   isolated stack; the dev `web` container serves a prebuilt bundle — REBUILD it from main first
>   or the new pages 404. Observed gaps append to `plans/ONBOARD-admin-experience.md`; milestone
>   closes. Memory: [[onboard-milestone-plan]].
> - **OPEN/GOTCHAS:** AIC PRs **#188 → #189 → #190** still open/stacked — their HANDOFF carries the AI
>   Compliance banner, so expect a keep-both merge conflict in this file (resolve by stacking banners,
>   SAAS on top); AIC-2 ruleset counsel-review OPEN; **AIC-3 PARKED (task #456; resumes after the
>   SETUP ladder)**; untracked side files
>   (`sample-documents/`, `api/tests/agents/scenarios/test_*_live.py`) belong to NO PR — leave or clean
>   deliberately (rebrand slice already cleaned two: `.vite/` now gitignored, empty `api/rl_smoke.py`
>   deleted; the dev web container now serves a main+rebrand bundle — rebuild from the AIC branch if the
>   Compliance UI needs demoing before AIC merges); dev `.env` `LQ_AI_GATEWAY_KEY` still needs rotating (2026-06-30 terminal dump)
>   — PLUS dev Postgres password + `DEEPSEEK_API_KEY` (2026-07-01 diagnosis transcript; values gitignored,
>   never in git — rotation is a maintainer/dev-box action).
> ═══════════════════════════════════════════════════════════════════════════════════════════════════════

> ▶▶ **PICKUP (2026-07-02): ▶ TABULAR REVIEW T6 — grid review WORKSPACE + human cell-override — MERGED PR #184
> (`de393216`).** ADR-F055 **T6 addendum**; **NO migration** (the override rides the `results` JSONB). Dev stack
> fully rebuilt + healthy `http://localhost:3000` (web + api + arq + ingest); model `smart → deepseek-v4-flash`.
> Full plan: `docs/fork/plans/TABULAR-REVIEW-agentic.md` "### T6 (core)"; evidence
> `docs/fork/evidence/tabular-review/T6-workspace-drawer.md`.
>
> - **OPEN follow-up — PR #185 `fork/f2-tabular-t6-sticky-col-fix` (2 fixes; merge when CI green):**
>   **(1) THE IMPORTANT ONE — cockpit stage was non-interactive.** Navigating to a grid THROUGH Commercial
>   (Expand → the `TabularWorkspace` fly-in): a cell click showed **no drawer** and the cells **wouldn't scroll
>   horizontally** — though the standalone `/tabular/[id]` path worked. Cause: `.lq-tabws` (the workspace root) is
>   the direct child of the fly-in's flex ROW but only set `height:100%` — no `flex`/`width` — so it sized to its
>   max-content grid and overflowed the fly-in's `overflow:hidden` pane (grid unscrollable + drawer off-screen
>   right). `/tabular/[id]` is a normal `max-width` block so it was fine — which is why the original T6 Cypress
>   test (that path) MISSED it. Fix: `.lq-tabws { flex:1; min-width:0; width:100% }`. Guard: NEW
>   `f2-tabular-t6-cockpit-stage.cy.ts` drives the REAL cockpit Expand→workspace path (6-col grid) and asserts
>   h-scroll + a cell click shows the drawer within the viewport — **passes live** (evidence
>   `T6-cypress/f2-tabular-t6-cockpit-stage.png`). LESSON: TabularWorkspace is ONLY used in the cockpit fly-in;
>   the standalone page inlines its own grid+drawer — so ALWAYS test the cockpit path, not just `/tabular/[id]`.
>   **(2)** grid first column (doc name) read too large + a long name overflowed its 14rem column (overlaid the
>   body on scroll): `font-size:0.8125rem` + ellipsis + `title` tooltip; Wrap-on = plain wrap (NOT
>   `-webkit-line-clamp`, which needs `display:-webkit-box` and breaks the `<th>` table-cell). svelte-check 0
>   errors; web rebuilt + live. **First action next session: confirm CI green → squash-merge #185.**
> - **🔬 QUEUED RESEARCH (post-compaction, maintainer-requested) — is `max_steps` the right brake, or should the
>   token cap govern?** Long contracts (the customer/CUAD sample) make the Commercial deepagent hit the **400-step
>   limit** (`run_max_steps`, the *balanced* `BudgetEnvelope` in `api/app/agents/budget.py`; economy=100 /
>   balanced=400 / generous=600, each paired with `token_budget` 2M/8M/16M + `fan_out_quota` + wall-clock — the
>   R4 token brake is ADR-F051, profiles ADR-F053). **Question:** is hitting the step ceiling a *real* token-cost
>   problem, or is step-count an arbitrary iteration cap that should defer to the **token cap** (which may be far
>   more generous)? **Initial framing to test, not conclude:** `max_steps` and `token_budget` are independent
>   brakes (whichever fires first). For the observed **thrash** ([[tabular-fanout-live-behavior]]: ~35k-tok docs →
>   150+ searches, 0 `record_tabular_row`), `max_steps` is a *cheap* catch — remove it and the 8M token cap lets
>   the loop burn far more before stopping. But for **legitimate** large grids (many docs × columns, every step
>   productive), 400 may *wrongly truncate* a valid, still-cheap run. So the likely answer isn't "steps don't
>   matter" but "steps are a cheap loop-backstop that's mis-sized for real work": options to weigh — scale
>   `max_steps` with work size (doc_count × columns, or `fan_out_quota`); raise it and lean on token + wall-clock
>   caps; and/or fix the thrash root cause (T4 retrieval-fill + doctrine so it stops re-searching). Also research
>   how **deepagents/langgraph** intend step/recursion limits vs token control (langgraph `recursion_limit`). This
>   is ADR-worthy (touches ADR-F051/F053). **Do NOT implement — research + recommend first.** Memory:
>   [[max-steps-vs-token-cap-research]].
> - **⏳ MAINTAINER WANTS TO VERIFY LIVE (do this next):** the FULL agentic loop — the Commercial agent *builds*
>   a grid → it appears **inline in chat** as a `TabularPreview` card with an **Expand** button → Expand opens the
>   **stage-takeover** workspace (conversation slides back, docked cell drawer). A ready matter exists:
>   **"Tabular Test"** (Commercial, owner `admin@lq.ai`, project `03f556b9-0885-4e08-b419-d6f71beb7a5a`) with a
>   completed 5×5 grid `a0beca15-58eb-4492-bb1e-0db085ac4068` (direct: `/lq-ai/tabular/<id>`). To exercise the
>   agent-build path, ask the Commercial agent to "compare/tabulate these contracts" over a few matter docs (small
>   docs + a "fan out one subagent per contract" nudge = clean completion; see [[tabular-fanout-live-behavior]]),
>   then Expand the preview. Grid-list rows also open the stage via the **Grids** tab (onOpenGrid). NOTE the design
>   phrase "expanding into a new **tab**": T6 shipped Expand → an in-cockpit **stage-takeover** (fly-in, SSE-safe),
>   NOT a browser tab — confirm that matches intent, or file a tweak.
>
> - **WHAT SHIPPED — the grid is a review WORKSPACE, not a stacked modal.** Killed the `ag-grid-overlay` (z-60)
>   and the `TabularCitationModal` (z-100, **DELETED**). Expand (in-chat preview) / a Grids-tab row now open the
>   grid as a **cockpit stage-takeover** — the `DocumentEditorPanel` fly-in reused verbatim, so the conversation
>   stays MOUNTED and **live SSE survives** — hosting NEW `TabularWorkspace` = the full `TabularGrid` beside ONE
>   docked `TabularCellDrawer` that **PUSHES** the grid (no modal, no backdrop). Drawer shows value · confidence
>   · tier · cost · verbatim `source_quote` · notes · citations · **Open source document** (new tab via
>   `GET /files/{source_file_id}/content`) · the **override + note** form.
> - **The load-bearing add = a human cell-override (ADR-F042 human-write, NOT an agent tool).** NEW `POST` +
>   `DELETE /api/v1/tabular/executions/{id}/cells/override` — owner-scoped (`user_id` from the SESSION),
>   `mode=='agentic'`-gated (→ 404 on a linear/cross-user row, never touches the frozen executor),
>   `.with_for_update()` before the JSONB read-modify-write, audit **IDs/counts only**. Mirrors
>   `create_matter_correction`. The override rides the cell dict in `results` JSONB (+4 `CellResult` fields, all
>   default `None`). **"Human wins" is STRUCTURAL:** `tabular_tool._upsert_row` **preserves** the `override_*`
>   keys, so `record_tabular_row`/`update_tabular_cells` can refresh the agent value underneath but can never
>   clobber the lawyer's override. Effective display value everywhere = `override_value ?? value`.
> - **Also fixed:** cell-squish (real **fixed 16rem column widths + horizontal scroll + a Wrap line-clamp
>   toggle**, not `width:100%`); the composer-overlap cosmetic (the drawer docks in-stage — no fixed overlay).
>   `‹ Grids / <derived title>` breadcrumb; NO standing "Grid" tab.
> - **Files.** NEW `web/.../components/{TabularWorkspace,TabularCellDrawer}.svelte` +
>   `agents/tabular-workspace-helpers.ts` (+ `__tests__/*.test.ts`). Wiring: `ConversationHost.svelte`
>   (`gridOpen`/`gridId` + `openGrid`/`closeGrid` + fly-in sibling + `cockpit.editorOpen = editorOpen||gridOpen`
>   rail-collapse), `GridsPanel.svelte` (`onOpenGrid`), `TabularPreview.svelte` (Expand → `dispatch('expand')`,
>   overlay+modal deleted), `ConversationPanel.svelte` (forwards `expandgrid`), `/tabular/[id]/+page.svelte`
>   (inlines grid+drawer, KEEPS its export/cancel/banner chrome). `TabularGrid`/`TabularCell` gained `wrap`
>   (+`fill`) + render `override_value ?? value` + an "edited" mark. `types.ts` extended (the TS
>   `TabularCellResult` was a LOSSY subset — `source_quote`/`notes` were already on the wire). Backend:
>   `api/app/api/tabular.py`, `schemas/tabular.py`, `agents/tabular_tool.py`. **DELETED** `TabularCitationModal`.
> - **GATE — met.** api **48** (tabular endpoints+tool: set/clear/404×3/422×2/human-wins-across-agent-write/
>   audit-no-value) + **4** guards (endpoints IMPLEMENTED_ROUTES + openapi EXPECTED_PATHS + `len==158→159`) +
>   **mypy** 217 + **ruff** clean. web **1051** vitest (+12 new helper) + **svelte-check 0 errors** (1485→1484
>   files, modal gone). Cypress T2/m3-c specs updated to the workspace/drawer test-ids (mock-based; not
>   CI-gated). Evidence: `docs/fork/evidence/tabular-review/T6-workspace-drawer.md`.
> - **KEY TRAPS.** (1) the override is a HUMAN endpoint — never a `guarded_dispatch` tool; `overridden_by` from
>   the session, and `_upsert_row` MUST preserve override keys (else the agent silently reverts a correction).
>   (2) a new `/api/v1` path ⇒ BOTH guard files + the `len==159` count. (3) new UI = app.css semantic tokens
>   (`bg-brand` #0070f3 / `var(--brand)`), NOT legacy sage; the existing grid stays on `--lq-*`. (4) do NOT add
>   `gridOpen` to `panelKey` (would remount `ConversationPanel` → drop the live SSE). (5) run the CI-parity
>   `ruff` in a fresh `python:3.12-slim` on changed py; rebuild `web` before Cypress/screenshots. (6) forward
>   DATABASE_URL to the dev-container tests BY NAME (`-e DATABASE_URL` + a `DATABASE_URL="$(docker inspect …)"`
>   prefix) — never put the secret literally on the command line.
> - **NEXT = T5** (live cell fill — a transient `data-tabular-cell` frame) · then **T4** (retrieval-fill +
>   crossover eval, OOM-aware) · **T8b** (combine_documents). **T6 later phases:** P2 verified/flagged +
>   completion meter (migration) · P3 column output-types + semantic colour · P4 party column/filter · P5
>   deliverables (skill → `.docx` → Documents → Collabora). Grid-workspace design + LQ-Grid reference: memory
>   [[t6-grid-workspace-redesign]]. **Untracked side-investigation** (NOT in this PR): `sample-documents/` demo
>   packs + `api/tests/agents/scenarios/test_*_live.py` — keep or delete; live findings in
>   [[tabular-fanout-live-behavior]].

> ▶ **PREVIOUS (2026-07-01): EMBEDDING PROVIDER — tabular-thrash root cause FOUND + FIXED; ADR-F056 plan drafted
> (merged via PR #186).**
> The "tabular review hits 600 steps and kills the box" symptom is **semantic search being OFF**, not chunking or
> model quality. On matter `20ce20fb` the agent ran **235 `search_documents`, 0 `record_tabular_row`** → 600-step
> cap → context bloat/DB+gateway hammer → box overload. Three compounding causes on the `embedding_local` path:
> (1) **ingest embedded with `local`, the query with `gateway`** (compose wires `EMBEDDING_PROVIDER` to api+arq but
> NOT ingest) = two vector spaces in one column, no provenance to tell them apart; (2) the dev gateway `embedding`
> alias → `openai-prod/text-embedding-3-small` has **no OpenAI key** → `/v1/embeddings` **503** → `_embed_query`
> silently degrades to **FTS-only** (keyword search collapses on long contracts); (3) **half-built index** (78/245
> chunks embedded — local embedder OOM'd mid-ingest, silent).
> **FIX APPLIED + VERIFIED LIVE:** `.env EMBEDDING_PROVIDER=gateway→local` (RERANK stays false — box OOMs both ONNX
> models; embedder-alone OK), recreated api+arq+ingest, re-embedded matter `20ce20fb` via
> `embed_local_chunks_for_file` → **245/245**, `matter_hybrid_search` (alpha 0.5) returns relevant clauses across
> all 5 docs. **Retest tabular review on `20ce20fb` now — search should hit first-try, not thrash.**
> **BIGGER TO-DO (maintainer direction) = ADR-F056 (proposed) + plan `docs/fork/plans/EMBEDDING-PROVIDER-choice.md`:**
> per-matter selectable embedding provider (local vs OpenAI-via-gateway now, Voyage later) with a single
> ingest↔query resolver, per-chunk provenance, re-embed-on-change, and coverage health. **Confirmed scope:**
> per-matter (firm default inherited); **build AFTER tabular T4**; local+gateway v1. Memory:
> [[embedding-provider-mismatch-and-choice]]. NOTE: `FAN_OUT_QUOTA` binds the **balanced** budget profile only
> (economy=8/generous=48 hardcoded in `budget.py`) — the worker `mem_limit` is the only containment for a
> generous run.

> ▶ **PREVIOUS (2026-07-01): TABULAR REVIEW T8 — MERGED PR #183 (`444c6c62`); ADR-F055, no migration.**
> Branch `fork/f2-tabular-t8-grid-ops` (merged). The Commercial agent can
> now EDIT a finalized grid in place ("bash" loop). Full plan: `docs/fork/plans/TABULAR-REVIEW-agentic.md`.
> Dev stack healthy on `http://localhost:3000`; model `smart → deepseek-v4-flash`; DeepSeek has quota.
>
> - **DONE tonight (all merged to main):** T2 (in-chat preview + Expand, #180 `91660db9`) · T3 (discoverability
>   skill, #181 `9e7b4f26`, mig 0083) · T7 (Grids tab, #182 `fab000f6`) · **T8 (this branch).** (T1 grids
>   tool `e9fdb2d0` was pre-session.) **All 3 explicit maintainer priorities (grid tool / discoverability /
>   artifacts-tab) + the in-chat preview + editing are shipped.**
> - **T8 — WHAT SHIPPED:** NEW `update_tabular_cells(grid_id, document, cells)` in `tabular_tool.py` — edits a
>   **completed** grid in place (distinct from `record_tabular_row`, running-only); shares ONE `_apply_cells`
>   core with record (resolve→verify-in-grid→validate-columns→upsert→audit); audited `tabular.cells_updated`;
>   added to `TABULAR_TOOL_NAMES` (grant) + `build_tabular_tools` returns 4 tools; `TABULAR_FILL_DOCTRINE`
>   teaches the edit loop (ADR-F042 the lawyer owns/undoes). **`combine_documents` DEFERRED → T8b** (merging
>   B's row into A breaks cell-citation integrity: a cell's `cited_chunk_ids` resolve against the ROW's
>   `document_id`; needs a per-cell document_id — data-model decision, not a shipped bug).
> - **GATE — met:** `ruff`+`mypy`(217) clean; **30** `test_tabular_tool.py` (+7; guarded end-to-end now
>   start→record→finalize→UPDATE) + **54** capability/composition tests green. **LIVE (ADR-F015, DeepSeek):**
>   the agent SELECTS `update_tabular_cells` + corrects a seeded-wrong cell ("One (1) year"→"Two (2) years",
>   `cell_changed=true`) — `test_tabular_update_eval.py` + `docs/fork/evidence/tabular-review/T8-grid-ops.md`.
> - **NEXT = T5** (live cell fill): a TRANSIENT `data-tabular-cell` frame (animation, ADR-F004 — the RIGHT use
>   of a live-only frame) modeled on `data-deal-change`; a `TabularChangeLedger` (`LiveChange`/`ChangeLedger`);
>   grid + T2 preview fill row-by-row. **Ledger coexistence:** ONE run-scoped Commercial ledger passed to BOTH
>   `build_commercial_tools` and `build_tabular_tools`. Then **T6** (stage takeover + cell drawer; also fixes
>   the composer-overlap cosmetic — the T2 preview mini-table sits behind the composer at rest) · **T4**
>   (retrieval-fill + crossover eval — HIGH risk: dev-box OOM, FTS-only, ship honest) · **T8b** (combine).
> - **KEY TRAPS (each cost CI cycles this session):** (1) **a new `/api/v1` endpoint MUST be added to the
>   governance guards:** `test_endpoints.py` `IMPLEMENTED_ROUTES` + `test_openapi.py` `EXPECTED_PATHS` + the
>   `len(actual)==N` count. (2) **ruff drift:** the dev image's ruff lags CI; run `ruff format` **WRITE** with
>   a fresh `pip install 'ruff>=0.6'` (`python:3.12-slim`) on changed py before pushing, not `--check` on the
>   dev image. (3) **eval attribution** ([[eval-attribution-confirm-capability]]): pass
>   `skill_registry=load_registry(LQ_AI_SKILLS_DIR)` to `run_scenario` or the skill is dropped as drift. (4)
>   adding a tool to `TABULAR_TOOL_NAMES`/`build_tabular_tools` breaks the exact-set + unpack assertions in
>   `test_tabular_tool.py` (update them). (5) **durable in-chat artifacts derive from settled `data-step`, NOT
>   custom `data-*` frames** (live-only; correct for T5 cell-fill). (6) web: no `@testing-library/svelte` →
>   `.ts` helper + unit-test, verify live (Cypress); rebuild `web` before screenshots; Svelte-5
>   `untrack(()=>prop)` + key `{#each}` on a real item. (7) **dev-container recipe:** `lq-ai-api-dev`,
>   `--network lq-ai_default`, mount `api/app`+`api/tests`+`api/alembic`+`skills:/skills:ro`, `DATABASE_URL`
>   from the api container, `LQ_AI_SKILLS_DIR=/skills`; add `LQ_AI_GATEWAY_KEY`+`LQ_AI_GATEWAY_URL` ONLY for
>   provider evals; migration round-trip = throwaway pgvector by IP. (8) **dev `LQ_AI_GATEWAY_KEY` surfaced in
>   a terminal dump 2026-06-30 → still needs rotating** in the gitignored `.env`.
> ▷ **CLOSED side-quest (2026-06-30): K2-Think model eval — PARKED, do NOT resume unless asked.** A "test a
> model quickly" detour for one specific client. Conclusion: native deepagents + K2 is **not viable**
> (streaming multi-turn tool-calls emit malformed JSON → upstream "Invalid JSON payload for chat completion
> request" → run aborts; the gateway repairs args only on the NON-streaming path); the **planner-executor**
> workaround (K2 emits JSON content, code applies) works mechanically (NDA redline: parse 8/8, surgicality
> 5/5) but legal quality is supervised-first-pass only (0/8 send-ready; residuals clause + downstream-conflict
> reconciliation are the weak spots). **The dev stack was FULLY REVERTED to DeepSeek — git tree CLEAN, all K2
> tweaks removed (gateway provider/alias, factory reasoning_effort, web buildRunPayload force, docker-compose
> env), live gateway config k2think-free.** Only inert leftovers: the gitignored `.env` `K2THINK_API_KEY`
> and `scratchpad/k2_*` scripts. Full detail: memory [[k2-think-tooluse-test]].
>
> ▶ **PREVIOUS (2026-06-30): CAPABILITY PANEL (Phase 1) — ✅ SHIPPED + MERGED PR #177 (`29d9d027`)
> (ADR-F054, migration 0081). Maintainer-confirmed working in the browser. Phase 1 of the "Capability panel
> + in-matter Tabular review" milestone — the prerequisite before Phase 2 (tabular as an in-matter agent TOOL
> in Commercial + Corporate, grid UX informed by the maintainer's React repo LQ-Grid, REFERENCE-ONLY).**
> - **WHAT SHIPPED:** a per-matter capability panel. The AREA curates the AVAILABLE set; the LAWYER toggles
>   a subset on/off **PER MATTER** (persisted; survives the matter's conversations; "system proposes, user
>   owns"). Sections: **Playbooks / Skills / Tools** (real now) + a disabled **MCP** placeholder. Primitives
>   (read/write/edit/bash/task) + always-on matter substrate tools are NEVER shown. All 6 design calls were
>   confirmed on the recommended defaults (see ADR-F054).
> - **ARCHITECTURE:** ONE pure `app/agents/capabilities.py` inventory `(kind,key,label,available,
>   default_enabled,toggleable)` + `enabled_keys`/`is_toggleable`/`enabled_map`, consumed by BOTH the read
>   API AND `compose_and_execute_run` (single source of truth → the panel shows what the agent gets).
>   Migration **0081** (additive, named FKs, no redundant index): `practice_area_playbooks` (area↔playbook
>   availability, mirrors `practice_area_skills`) + `matter_capability_toggles` (SPARSE per-matter on/off;
>   absent row = `default_enabled`). **NO `practice_area_tools` table** — tools are code-canonical
>   (`*_TOOL_NAMES`); availability is a per-area CODE group map (`AREA_TOOL_GROUPS`). New `GET/PATCH
>   /matters/{id}/capabilities` (404-not-403, owner-scoped via `_load_visible_project`) + admin
>   `POST/DELETE /practice-areas/{key}/playbooks`.
> - **OFF → genuinely removed at 3 EXISTING seams:** skills filtered before `build_area_skill_wiring`; tool
>   GROUPS not built (so absent from `GuardContext.granted`, R6 fail-closes; change_ledger created iff its
>   group enabled); playbooks injected as a NEW read-only **"Practice Playbook" tier** on
>   `TierMemoryMiddleware` (ADR-F049, `playbook_context.render_practice_playbook`, length-capped, data-only
>   fence — REUSES the playbook DATA, the legacy executor stays frozen). The Practice Playbook tier renders
>   at the practice-area level (after House Brief, before the matter tiers).
> - **UI:** a "Capabilities" **tab** (full-width panel like Memory/Documents; conversation stays MOUNTED →
>   live SSE survives) — `web/.../components/matter/CapabilitiesPanel.svelte` (accessible role=switch toggles,
>   optimistic + revert, run-locked while a run is active), `api/matterCapabilities.ts`, wired in
>   `ConversationHost.svelte`. (Co-visible resizable split = a noted follow-up; the tab is the shipped form.)
> - **THE HARD GUARD (met):** the area-key tool branch became a per-group gate; the **no-toggle (default)
>   path is byte-identical** to pre-slice (all skills wired in order, all area tool groups built with their
>   ledgers, no playbook tier when nothing bound) — proven by the composition tests + the adversarial review.
> - **GATE:** ruff (CI cmd, repo root) + format + **mypy 215** clean; migration 0081 **up→down→up on a
>   throwaway pgvector** (named FKs, PK-only index); **full api suite green** (last full run 3002 passed/1
>   fixed = the test_openapi/test_endpoints route-contract entries — REMEMBER to add new routes there);
>   web `npm run check` **0 errors** + **1014 passed** (96 files). **Adversarial review: 0 blockers / 0
>   should-fixes / 5 nits** — 3 actioned (dropped redundant index, dropped dead `ToolGroupSpec.tool_names` +
>   tautological test, named the migration FKs); nits 4–5 (resolve-inventory duplication; sparse-row writes
>   a == default row) accepted as harmless/intentional. **LIVE-VERIFIED** on the dev stack: attach playbook
>   (204) → GET shows all 4 sections (real commercial skills, bound playbook, redlining, MCP-disabled) →
>   toggle redlining off (persists across a fresh GET) → wrong-area tool 422.
> - **POST-MERGE GATE:** CI green on #177 (API + Gateway + Web); **full api suite 3003 passed / 5 skipped**.
>   **LIVE BUG fixed during testing — toggle endpoint PUT → PATCH:** the api CORS `allow_methods` is
>   GET/POST/PATCH/DELETE/OPTIONS (NO PUT — the codebase has zero PUT endpoints), so the browser's PUT
>   preflight was blocked → "Failed to fetch" → toggles silently reverted. Switched to PATCH (convention +
>   semantically a sparse update); the web client method is `updateMatterCapabilities` (PATCH). **TRAP for
>   any future mutating endpoint: use POST/PATCH/DELETE, never PUT, or the browser CORS preflight fails.**
> - **DEV STACK:** api+arq+ingest+web rebuilt (mig 0081 live, tables confirmed); panel live + maintainer-
>   confirmed on `http://localhost:3000` (use localhost, NOT 127.0.0.1 — CORS allow-list is localhost:3000
>   only). A demo playbook "NDA — Mutual" is bound to Commercial for testing (unbind via the admin DELETE).
>   NOTE: the dev DB carries the FIRST-cut 0081 (redundant index + auto-named FKs) — harmless; the SHIPPED
>   (clean) migration applies on a fresh deploy; no host-side downgrade was run.
> - **TRAPS (carry forward):** (1) a new route MUST be added to BOTH `test_endpoints.py` IMPLEMENTED_ROUTES
>   (skip the 501-scaffold) AND `test_openapi.py` EXPECTED_PATHS **+ the `len(actual) == N` count** (3 path
>   templates here → +3). (2) `build_area_inventory` calls `record.summary()` on every area-bound run → any
>   test fake registry needs a `.summary()` returning `.title`/`.description` (fixed the `_SkillRec` fake in
>   `test_agent_composition.py`). (3) the ASGI endpoint test has NO skill registry installed → the skills
>   SECTION is empty there (graceful None); skills coverage is the pure + composition tests; the LIVE server
>   DOES have the registry (skills show). (4) commit ruff from the REPO ROOT (`ruff check api scripts`).
> - **NEXT after merge:** Phase 2 — Tabular review as an in-matter agent tool (Commercial + Corporate),
>   grid UX learning from LQ-Grid (React, REFERENCE-ONLY — its own plan + ADR). Deferred (resume after this
>   milestone): Slice P/PageIndex; N=150 hybrid+rerank calibration; cost_usd exact attribution + pre-run
>   hint; per-turn conversation granularity.
>
> ▶ **PREVIOUS (2026-06-30): F2 SLICE O-2 — per-run COST ESTIMATE (`agent_runs.cost_usd`) + a UI receipt —
> MERGED PR #176 (`c9df336b`) (ADR-F053 Slice O-2 addendum). The actioned upstream-reuse finding; finishes
> the cost-envelope story Slice O started. NO migration, NO new dep, gateway untouched.**
> - **Two assumptions flipped (both favourable):** (a) `agent_runs.cost_usd` (`NUMERIC(10,4)`, nullable)
>   ALREADY exists + is exposed on `AgentRunRead` + TS `AgentRun` → **no migration, no new column**; (b) every
>   deep-agent call is tagged `purpose='agent_loop'` and the gateway records a real per-call `cost_estimate`
>   on the routing-log row → a rolling average over `agent_loop` has **live data**, not cold-start-only.
> - **NEW `api/app/agents/cost.py`** — `estimate_agent_run_cost_usd(db, *, total_tokens)`: a **blended
>   per-token** rate `SUM(cost_estimate)/SUM(tokens_in+tokens_out)` over the last 100 priced `agent_loop` rows
>   (≤30 days) × `total_tokens`. Blended (not upstream's per-CALL average) because a run is many calls of
>   varying size and we only persist `total_tokens` (Slice G). Fallback `DEFAULT_AGENT_PER_TOKEN_USD` (~$3/Mtok)
>   when <5 priced rows. **No cache** (runs once per settlement, not per-message like the judge estimator → no
>   module singleton). An ESTIMATE — routing log has no run id (exact attribution = deferred `run_id` slice).
> - **Seam:** `runner.execute_agent_run` computes the cost in a **SEPARATE** short-lived session before
>   `_finalize` (a failed rate query can't poison the settle txn), **gated on truthy `total_tokens`**, best-
>   effort (failure → NULL). `_finalize` + `lease.settle_run` gained a `cost_usd` param persisted in the one
>   terminal UPDATE. Timeout/error paths settle unpriced (NULL).
> - **UI (post-run actual only):** `ConversationPanel.svelte` renders "Est. cost ~ $X" on the settled run card
>   (`formatRunCostUSD` in `<script module>`, reuses `formatCostUSD`; tooltip "not an exact bill"). Deliberately
>   NOT a pre-run per-profile number — ceiling × rate (8M/16M tok) would show a scary backstop, not expected
>   spend. (A "typical run ~ $X" dropdown hint = possible honest follow-up.)
> - **GATE — met:** targeted api **41 passed** (`test_agent_cost` blended/size-weighted/fallback/filters/
>   None-0/db-None/DB-error; `test_agent_lease` cost_usd persisted + NULL default; `test_agent_runner` normal
>   priced / timeout unpriced); ruff(root) + format + **mypy(211)** clean; web `npm run check` 0 errors +
>   `ConversationPanel-helpers` 14 passed (full `test:frontend` <RESULT — see PR>). CI on the PR is
>   authoritative. **TRAP** (caught): a no-usage run has `total_tokens=0` (a number, not None) — `if
>   total_tokens is not None:` opened a session that ATE the fault-injection ordinal in `test_finalize_*`
>   (one passed vacuously); gate on **truthy** `total_tokens` (a 0-token run is unpriceable anyway).
> - **NEXT (queue):** **Slice P — PageIndex** (gateway-bound retrieval; strongly favoured — this box can't run
>   local ONNX during runs; ADR-F052 to draft; `plans/PAGEINDEX-SLICE-P.md`; eval-first). Lower-priority
>   follow-ups: cost_usd **exact** attribution (routing-log `run_id`, cross-service); a "typical run ~ $X"
>   pre-run hint. Still-open housekeeping: the unpushed `fork/c3-update-memory-ux` branch (2 local commits).
>
> ▶ **PREVIOUS (2026-06-30): DEV-STACK STABILITY + STREAMING-RENDER FIX — MERGED PR #175 (`b30240ed`).
> Two separable fixes surfaced while live-testing Slice O on the 6.3 GB dev box; NOT part of the Slice O feature.**
> - **(1) Agent runs OOM the box** loading the in-process ONNX retrieval stack (local bge embedder +
>   cross-encoder rerank) in the **arq-worker** during `search_documents` → memory 2.6→5.3 GB → OOM →
>   **Postgres broken-pipe crash loop** → API 500 → browser "Failed to fetch / lost contact". Fix:
>   `docker-compose.yml` adds `EMBEDDING_PROVIDER`/`RERANK_ENABLED` env passthroughs to api + arq-worker
>   (defaults preserve prod: local + rerank-on); the **dev box** sets `EMBEDDING_PROVIDER=gateway` +
>   `RERANK_ENABLED=false` in gitignored `.env` → runs embed via the gateway + skip the cross-encoder → no
>   in-process ONNX → **memory flat ~1.6 GB through a full run** (proven). The gateway exposes an `embedding`
>   model, so hybrid retrieval still works (FTS + gateway-vector). Generalises the CLAUDE.md trap: not just
>   *evals* — **agent runs** can't hold the local ONNX stack on a ~6 GB box.
> - **(2) Browser tab froze mid-run** (before completion): `ConversationPanel.svelte` had
>   `$: liveReasoningHtml = renderModelMarkdown(liveReasoning)` — re-parsing (marked+DOMPurify) the WHOLE
>   growing reasoning buffer on EVERY `reasoning-delta`. With a reasoning model (deepseek-v4-flash) streaming
>   100k+ tokens that's **O(n²)** main-thread work → freeze. Fix: render on a `requestAnimationFrame` throttle
>   over a bounded **tail** (`LIVE_REASONING_TAIL=8000`); one `autoScroll` per frame; clear on settle; removed
>   the reactive statement. Live-verified by the maintainer (page stays responsive; settled markdown renders).
> - **GATE:** `npm run check` 0 errors; web bundle rebuilt + live-verified; backend stable (no OOM, memory
>   flat). CI on the PR is authoritative. No migration, no new dep.
> - **NEXT (queue):** **Slice O-2** (cost_usd estimate in the budget UI — the actioned upstream-reuse
>   finding) OR **Slice P — PageIndex** (gateway-bound retrieval; now strongly favoured since this box can't
>   run local ONNX during runs; ADR-F052 to draft; `plans/PAGEINDEX-SLICE-P.md`). Maintainer to pick.
>
> ▶ **PREVIOUS (2026-06-30): F2 SLICE O — per-run BUDGET PROFILES + ≥4× default ceilings + a UI knob —
> MERGED PR #174 (`38318028`) (ADR-F053, **migration 0080**). The maintainer ask: raise the
> default brakes ≥4× so the agent works freely + an EASY way to dial DOWN in the UI. Companion/prereq to
> the PageIndex slice (`plans/PAGEINDEX-SLICE-P.md`). NO new dep; gateway untouched.**
> - **What:** `BudgetProfile` (economy/balanced/generous) → a four-brake `BudgetEnvelope` (token_budget,
>   fan_out_quota, max_steps, wall_clock). **economy** `(2M,8,100,900s)` = the conservative pre-Slice-O tier
>   (dial-down); **balanced (default)** `(8M,32,400,3600s)` = exactly 4× economy, read from `Settings` so
>   env can shift the default; **generous** `(16M,48,600,5400s)`. `app/agents/budget.py:resolve_envelope`
>   is the single source of truth (NULL/unknown legacy → balanced).
> - **Flow (load-bearing):** the arq worker is enqueued with ONLY the run id + reads `agent_runs` columns →
>   the profile MUST be persisted. **Migration 0080** adds `agent_runs.budget_profile` (nullable TEXT,
>   additive). The endpoint resolves the envelope, materializes `max_steps` on the row (runner reads it; an
>   explicit request `max_steps` overrides — ceiling raised 100→**600**), stores the profile. Composition
>   re-resolves the other three from the stored profile (was a direct `get_settings()` read) → passes
>   `token_budget` + `wall_clock_seconds` + `FanOutQuotaMiddleware(quota=…)`. arq `AGENT_RUN_JOB_TIMEOUT`
>   1020→**5520s** (must exceed the generous 5400s wall clock; guarded by `test_agent_run_timeout_layering`,
>   now asserting against `MAX_PROFILE_WALL_CLOCK_SECONDS`).
> - **UI:** composer `ConversationPanel.svelte` gains a Budget `<select>` (Economy/Balanced/Generous, default
>   balanced) via a pure exported `buildRunPayload` helper; `api/agents.ts` `AgentRunCreate.budget_profile`
>   + `AgentRun` echo. **One dropdown, three named tiers** (not 4 raw integer fields).
> - **GATE — met:** `test_budget.py` (profile→envelope map + the **≥4× requirement** + legacy/NULL→balanced
>   + string==enum); `test_agent_runs_api.py` (profile persisted + resolves max_steps; explicit override;
>   invalid profile→422; ceiling now 601→422); timeout-layering strengthened. Migration **0080 up→down→up on
>   a THROWAWAY pgvector** verified (`budget_profile | text | YES`). Affected modules **116 passed**; full api
>   suite <RESULT — see PR>; ruff(root) + format + mypy(210) clean. Web `npm run check` clean + `test:frontend`
>   **997 passed**.
> - **TRAPS:** (1) **ruff config = repo-root `ruff.toml`** — run ruff from the REPO ROOT (mount whole repo),
>   NOT api/=/app (api-local config flags 344 unrelated files; root config → only your files). dev-image ruff
>   is 0.15.20, same as CI's `pip install -e .[dev]`. (2) the arq timeout MUST exceed the LARGEST profile wall
>   clock — raise both together (the test guards it). (3) `max_steps` is materialized on the row; the other
>   three brakes are re-resolved from the profile at composition — don't expect them on the row. (4) deploy
>   needs api+arq+ingest rebuilt (migration 0080). (5) economy/generous are FIXED; only balanced is
>   env-tunable (via the 4 `Settings.run_*` defaults).
> - **NEXT — Slice O-2 (the actioned upstream-reuse finding):** populate `agent_runs.cost_usd` at
>   `settle_run` by mirroring upstream's rolling-average-from-`inference_routing_log` estimator
>   (`citation/cost.py:estimate_judge_call_cost_usd` is NOT directly reusable — per-call +
>   `purpose='judge_paraphrase'`; write a new `agent_loop` per-TOKEN estimator) × the persisted
>   `total_tokens`; surface "~$ est." in the budget UI. Exact attribution still needs routing-log `run_id`
>   (separate cross-service slice). THEN the PageIndex slice (`plans/PAGEINDEX-SLICE-P.md`, ADR-F052 to draft)
>   — gateway-bound, runs on THIS box; eval-first.
>
> ▶ **PREVIOUS (2026-06-30): RETRIEVAL & MEMORY Phase-3 SLICE G — persist per-run token usage —
> on branch `fork/f2-slice-g-token-persistence` (ADR-F051 Slice G addendum, **migration 0079**). The
> Slice-F observability deferral, discharged. NO new dep, NO behavioural change beyond the additive column.**
> - **What:** migration 0079 adds `agent_runs.total_tokens` (nullable INTEGER, additive/non-destructive;
>   `cost_usd` stays NULL — dollars need per-model rates the runner doesn't see). `_drive_agent` returns the
>   cumulative total as a 4th tuple element; `execute_agent_run` threads it via `_finalize` → the fenced
>   `settle_run` terminal write (one new SET column) on the NORMAL path (completed/cap_exceeded). Timeout/
>   error paths persist NULL (best-effort — they bypass the normal return). Exposed read-only on
>   `AgentRunRead.total_tokens`. Makes per-run spend queryable → enables calibrating `run_token_budget`.
> - **GATE — met:** `test_agent_runner.py` asserts the persisted total (completed=200, budget-disabled=20000,
>   capped=300 — the total that tripped the brake). **Migration round-trip up→down→up on a THROWAWAY pgvector
>   container** (CLAUDE.md: NEVER host-side alembic on the dev DB; mount `skills:/skills:ro` — mig 0032 needs
>   it; use the container IP, default bridge has no name DNS). Full `tests/agents/` 688 passed / 38 skipped / 0 failed; ruff+format+mypy
>   (209) clean. conftest runs `alembic upgrade head` on a fresh DB so 0079 is exercised by the whole suite.
> - **TRAPS:** (1) `cost_usd` (dollars) stays NULL — out of scope (rates). (2) timeout/error runs persist NULL
>   total_tokens (best-effort). (3) deploy needs the migration applied → rebuild api+arq+ingest (NOT done
>   autonomously). (4) `_drive_agent` now a 4-tuple; `settle_run`/`_finalize` gained a `total_tokens` param.
> - **NEXT:** Phase-3 remainder (recency / Documents-MAP — eval-gated on unmet measured triggers; PageIndex
>   Slice P / batch hybrid+rerank — need a ≥16 GB box) all await a trigger/box/go-ahead. Deriving `cost_usd`
>   from the token total (per-model rates) is the natural follow-up.
>
> ▶ **PREVIOUS (2026-06-30): RETRIEVAL & MEMORY Phase-3 SLICE F — R4 realised: a per-run TOKEN-BUDGET
> brake — MERGED PR #172 (`67ee1bb4`) (ADR-F051). NO migration, NO dep, NO behavioural
> gateway change. NEXT = the remaining Phase-3 (recency; Documents-MAP; PageIndex Slice P) — all gated on
> measured need; + the deferred token-total PERSISTENCE follow-up (a migration); own slice + go-ahead.**
> - **What it does:** closes the R4 gap Slice E deferred. R4 (the per-action cost cap) was a documented
>   no-op; nothing enforced a per-run token/dollar budget (only step/time caps fired). Slice F makes the
>   runner halt a run once its cumulative model tokens cross a ceiling — the hard cost stop that bounds a
>   runaway loop / over-eager fan-out (the ADR-F015 vector).
> - **Enabler (load-bearing):** `factory.build_gateway_chat_model` now sets `stream_usage=True`. The gateway
>   ALREADY forces `stream_options.include_usage=true` upstream + forwards the final usage chunk in its SSE;
>   the api-side ChatOpenAI just never ASKED. With the flag, langchain populates `usage_metadata` on the
>   merged `on_chat_model_end` message (verified in-container: usage on a streamed chunk surfaces summed on
>   the merged event — true for nested subagent turns too).
> - **Accumulate + brake:** `runner._drive_agent` sums `usage_metadata.total_tokens` per model turn
>   (helper `_usage_total`, returns 0 when usage absent → fail-open) and halts mirroring `max_steps`:
>   `if token_budget > 0 and cumulative_tokens >= token_budget and not is_final → token_cap_hit; break`. The
>   not-mid-final-answer guard means a deliverable turn is never cut off. Settles `cap_exceeded` with a
>   DISTINCT `error="token_budget_exceeded"` (the step cap leaves error NULL). `execute_agent_run` gains a
>   `token_budget` param; `composition` passes `get_settings().run_token_budget`.
> - **Config:** `Settings.run_token_budget` default **2,000,000** — a CONSERVATIVE, UNCALIBRATED runaway
>   backstop (~10× the 200k window; ≤0 disables). Not a tuned cap — calibration needs per-run token telemetry
>   (the deferred persistence follow-up).
> - **guard.py R4:** the tool-dispatch R4 STAYS an honest no-op (tools are free local reads; zero marginal
>   inference cost) — the docstring + inline comment now point to the runner brake. The cost is the MODEL
>   calls, so the brake lives in the runner loop, NOT at the guard.
> - **In-memory, NO migration.** The brake needs only the live running total. Persisting a per-run
>   `total_tokens` (+ deriving `cost_usd`, still NULL) is a DEFERRED observability/calibration follow-up
>   (needs a migration → api+arq+ingest rebuild). Recorded, not built.
> - **THE GATE — met (ADR-F015; the runaway-token-budget halt is the hard CI gate).** Deterministic, $0,
>   zero-LLM: `test_agent_runner.py` — a looping model reporting fixed tokens/turn halts as
>   `cap_exceeded`+`token_budget_exceeded` BEFORE max_steps; `budget<=0` disables; a normal under-budget run
>   completes unaffected; a final-answer turn is never cut off mid-deliverable. The fake
>   `ScriptedToolCallingModel` gained `usage_per_turn` (emits a trailing usage chunk like ChatOpenAI's
>   include_usage chunk). Full `tests/agents/` 688 passed / 38 skipped / 0 failed; ruff + format + mypy (209) clean. Live finding:
>   `docs/fork/evidence/retrieval-eval-slice-f/`.
> - **TRAPS (carry forward):** (1) usage only surfaces if `stream_usage=True` AND the model streams (the
>   runner uses astream_events) AND the provider returns usage — a provider that omits usage → fail-open
>   (brake silent, still bounded by max_steps). (2) usage must be on a streamed CHUNK to surface on the
>   merged on_chat_model_end (the fake emits a trailing usage chunk; ChatOpenAI's include_usage does the
>   same). (3) the default budget is UNCALIBRATED — a backstop, tunable. (4) nested subagent turns count
>   toward the run budget (intended — fan-out is the runaway vector); the budget is whole-run, not per-subagent.
>   (5) `_drive_agent` now returns a 3-tuple `(final_answer, cap_hit, token_cap_hit)`.
>
> ▶ **PREVIOUS (2026-06-30): RETRIEVAL & MEMORY Phase-3 SLICE E — cost-aware fan-out + a fan-out quota
> brake — MERGED PR #171 (`ae973717`) (ADR-F049 Slice E addendum). NO migration, NO dep, NO gateway change.**
> - **What it does:** Slices A–D made the matter retriever good; Slice E makes the agent COST-AWARE about
>   how it consumes documents and puts a REAL enforced ceiling on subagent fan-out. Implements S1–S4 of the
>   strategy research (`research/retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md` §8); S5 (R4 as a
>   live per-run token budget) is explicitly DEFERRED.
> - **S1+S2 — estimate read cost:** `tools.py:_inventory` renders `~k tokens to read` per document from the
>   stored `character_count` (capped at the read limit ÷ ~4). New guarded read-only tool
>   `estimate_read_cost(filenames)` (in `MATTER_TOOL_NAMES`, same `guarded_dispatch` + `_matter_files_query`
>   matter+owner scope) returns the set's est read tokens (`Σ min(char_count, read_limit)/4`), the turn-start
>   remaining budget, and the fitting mode (read-in-full ≤ ½ budget / fan-out if independent & won't fit /
>   else passages). Empty list ⇒ whole matter. **Budget is an ESTIMATE** (compaction floor − a coarse
>   standing reserve), NOT live accounting — the tool says so. *(Postgres `LEAST(NULL,n)==n` trap →
>   `coalesce(char_count,0)` first, else an un-ingested file phantom-counts as the cap.)*
> - **S3 — doctrine (taste):** `RETRIEVAL_STRATEGY_DOCTRINE` injected for matter-bound runs (after the
>   conversation doctrine): three modes + the cost rule keyed on `estimate_read_cost` + cheap-first-escalate
>   + fan-out anti-patterns (don't fan out a set that fits or a dependent question — one mind reconciles).
>   Prose (ADR-F041); `system_prompt_for` stays the byte-identical oracle.
> - **S4 — fan-out quota (safety):** the deepagents builtin `task` tool BYPASSES `guarded_dispatch` (it's a
>   `SubAgentMiddleware.tools` entry). NEW `app/agents/fan_out_middleware.py:FanOutQuotaMiddleware`
>   (`AgentMiddleware`, overrides `(a)wrap_tool_call`) is its chokepoint: langchain's factory builds the
>   `ToolNode` with a `wrap_tool_call` chain from EVERY middleware overriding the hook (`langchain.agents.
>   factory:1005`), and `task` is a normal registered tool → our hook sees every `task` BEFORE it runs. Past
>   the per-run ceiling (`Settings.fan_out_quota`, default 8; ≤0 disables) it returns a model-visible refusal
>   `ToolMessage` WITHOUT calling the handler — no subagent spawns, run NOT killed, agent adapts. Check+increment
>   has no `await` between → exact cap even on a gathered multi-`task` turn. Built per-run in `composition.py`
>   (beside `TierMemoryMiddleware`), only when subagents are configured. SAFETY ceiling, NOT a taste limit.
> - **The honest R4 gap (S5 deferred):** R4 (`guard.py`) is still a no-op; no per-run TOKEN budget exists.
>   Slice E makes runaway fan-out unlikely+bounded (estimate + doctrine + quota) but NOT impossible — the hard
>   token stop needs S5 (routing-log aggregation + halt-at-ceiling: `inference_routing_log` has tokens_in/out,
>   `agent_runs.cost_usd` NULL mig 0048, runner captures no usage → ~100-200 LOC). Do NOT claim cost-safety.
> - **THE GATE — met (ADR-F015; the runaway-fan-out cost test is the hard CI gate, A7 strategy is a finding).**
>   Deterministic, $0: `test_fan_out_middleware.py` (allows N then denies (N+1) with a refusal, handler never
>   runs; non-task passes through & never counts; quota≤0 disables; sync==async; + an INTEGRATION test on a
>   REAL deepagents graph with a subagent proving the builtin `task` IS routed through our `awrap_tool_call`);
>   `test_agent_tools.py` (read-cost render; `estimate_read_cost` SUM/cap math, whole-matter vs named,
>   matter+owner scope isolation, read-in-full vs fan-out suggestions, audit body-free; grant set + schema +1);
>   `system_prompt_for` oracle updated. **Full `tests/agents/` 683 passed / 38 skipped / 0 failed**; ruff +
>   format + mypy (209) clean. **Live finding (best-effort, dev stack DeepSeek): the RFQ multi-doc subagent
>   scenario PASSED (43.96s) — the doctrine + estimate tool + quota are live and benign end-to-end.** Evidence
>   `docs/fork/evidence/retrieval-eval-slice-e/`.
> - **TRAPS (carry forward):** (1) `LEAST(NULL,n)==n` in Postgres → coalesce first (the bug a test caught).
>   (2) `wrap_tool_call` DOES fire for the builtin `task` — proven at factory.py:1005 + the integration test;
>   fallback if ever falsified = runner-side halt on observed `task` starts. (3) the budget is a turn-start
>   ESTIMATE, not live accounting (S5). (4) nested fan-out (a subagent calling `task`) runs under the
>   subagent's own middleware → the quota bounds the LEAD's breadth (the primary runaway vector), a known limit.
>   (5) `build_matter_tools` now returns 4 tools — the only unpacking site is `test_agent_tools.py`.
> - **A7-large** (over-window corpus where inline must fail / fan-out must win) is DESIGNED (research §6) but
>   DEFERRED as its own eval finding: DeepSeek's known no-autonomous-fan-out (E1 A7 0/10) means a live A7-large
>   mostly re-confirms that, and the over-window fixture build is its own slice. The live subagent RFQ scenario
>   is the strategy live finding here.
>
> ▶ **PREVIOUS (2026-06-30): RETRIEVAL & MEMORY Phase-3 SLICE D — local cross-encoder rerank — MERGED
> PR #170 (`3694adf0`) (ADR-F049 Slice D addendum), DEFAULT ON. NO migration, NO dep, NO gateway change.
> - **What it does:** C1 lit up recall (hybrid fusion); the bi-encoder embeds query/passage independently so
>   the top-k order is imprecise. Slice D adds a cross-encoder reranker that scores (query, passage) JOINTLY
>   and reorders a WIDER candidate set down to top-k — the textbook retrieve-wide-then-rerank precision stage.
> - **The wiring (a thin wrapper; the retriever is UNTOUCHED):** `app/knowledge/retrieval.py:matter_search_reranked`
>   fetches `rerank_candidates` (30) via the unchanged `matter_hybrid_search`, scores each `content`, stable-sorts
>   by cross-encoder score (tiebreak file_name, char_offset_start), truncates to top-k. `reranker=None` ⇒
>   delegates straight to `matter_hybrid_search` at top_k = BYTE-IDENTICAL (frozen E0/Slice-A baselines +
>   `_REFERENCE_FTS` drift guard hold). Error / score-count mismatch ⇒ hybrid-order fallback (never hard-fails,
>   mirrors the embedder). `tools.py:_search` routes through it gated on `rerank_enabled`; production
>   `search_documents` + Track-B eval both go through it (Slice A "agent mode == retriever").
> - **Provider (mirrors C1):** `app/knowledge/rerank_provider.py` — `RerankProvider` Protocol +
>   `LocalRerankProvider` (lazy fastembed `TextCrossEncoder`, `asyncio.to_thread`) + `build_/get_/set_rerank_provider`.
>   Door A only (no gateway `/rerank` endpoint; seam left for Door B). Default model
>   `Xenova/ms-marco-MiniLM-L-6-v2` (~5 MB, bundled at build in both Dockerfiles via `RERANK_CACHE_DIR`). Config:
>   `rerank_enabled` (DEFAULT TRUE), `rerank_model`, `rerank_cache_dir`, `rerank_candidates`.
> - **THE GATE — met, default ON (ADR-F015 finding, N=30, `docs/fork/evidence/retrieval-eval-slice-d/`):**
>   real MiniLM-L-6 over the production path vs the frozen FTS floor — ZERO recall harm; within-doc p@1 +15.5%,
>   MAP +11% (precision@5 *flat* = single-clause-gold artifact: 1 gold chunk caps p@5 at 0.2, so rank-3→1 moves
>   p@1/MAP not p@5); cross-doc precision@5 +20%, recall@5 +36%, hit@8 +32%, MAP +21%. Maintainer ruling:
>   **default ON** (SOTA precision fix + measured lower-bound lift, zero harm, ~1 GB memory peak in real runs,
>   minor latency). Deterministic CI (hermetic fake reranker): `test_rerank_provider`, `test_matter_search_reranked`
>   (passthrough byte-identical / wide-fetch promotion / ≤1 no-op / error+mismatch fallback / scope isolation),
>   rerank arm in `test_cuad_retrieval_smoke`, tool rerank-path+fallback in `test_agent_tools`. **Full
>   `tests/agents/` 671 passed / 38 skipped / 0 failed** (with default ON); ruff + mypy (208) clean.
> - **TRAPS (carry forward):** (1) **dev box (6.3 GB) OOMs loading the bge embedder + cross-encoder while
>   batch-evaluating** (876-chunk backfill + ~23k inferences grow the ONNX arena) → hybrid+rerank AT SCALE is a
>   DEFERRED finding for a ≥16 GB box; the measured FTS+rerank arm is a conservative lower bound. Run any
>   two-model eval ALONE; a REAL agent run holding both models peaks ~1 GB (safe — the OOM is eval-batch-only).
>   (2) keep `matter_hybrid_search` wrapper-only (byte-identical guard); (3) `rerank_enabled=True` default →
>   the autouse `_hermetic_rerank_provider` (conftest, identity fake) keeps the suite model-free; the matter
>   rerank path is tests/agents-only so non-agents/CI never load the model; (4) `OMP_NUM_THREADS` + run evals
>   alone; chown root-written evidence; the nested `-v docs:/app/docs` mount lands evidence in repo-root docs.
> - **NEXT (deferred, own slice + go-ahead):** batch-measure hybrid+rerank + `bge-reranker-base` vs MiniLM on a
>   bigger box; tune `rerank_candidates`/model. Then the rest of Phase-3 (Strategy+R4, recency, Documents-MAP,
>   PageIndex Slice P) — each gated on measured need.
>
> ▶ **PREVIOUS (2026-06-29): RETRIEVAL & MEMORY Phase-2 SLICE C2 — langgraph Store `IndexConfig` for
> conversation/memory SEMANTIC recall — MERGED PR #169 (`fdc096a8`) (ADR-F049 Slice C2
> addendum). NO migration, NO dep, NO gateway change. Reuses the Slice-C1 provider.**
> - **What it does:** N0 built the `AsyncPostgresStore` filter-only, so `store.asearch(query=…)` was a no-op
>   and N3's `search_matter_conversations` scanned transcripts lexically. C2 wires the C1 `EmbeddingProvider`
>   as the Store's `IndexConfig.embed` so `asearch(query=)` ranks by cosine → cross-thread PARAPHRASE recall a
>   keyword scan misses. The A5 semantic objective is now met end to end.
> - **The wiring (ONE point):** `app/agents/store.py:build_store_index_config(provider)` →
>   `{dims, embed, fields:["content"]}`; `init_agent_store()` passes it to `AsyncPostgresStore(pool, index=…)`.
>   BOTH composition roots route through `init_agent_store`, so one edit covers api + arq. `setup()` builds the
>   pgvector `store_vectors`/`vector_migrations` tables NON-destructively (N0 left them absent; library owns its
>   own schema, ADR-F008 — no alembic). The SAME helper builds the `InMemoryStore` index in tests.
> - **Symmetric embedding:** `embed` is a plain async `AEmbeddingsFunc`; langgraph wraps it
>   (`ensure_embeddings`→`EmbeddingsLambda`) so `aembed_query` AND `aembed_documents` route to the SAME closure
>   → symmetric regardless of which a store calls (pg store uses `aembed_documents`, InMemoryStore uses
>   `aembed_query`; verified). bge's query-instruction asymmetry (C1 document path) is intentionally NOT applied
>   to the Store. Indexing is store-WIDE (every `/memories/*` + conversation `put` embeds; local door $0, model
>   loads lazily → cheap startup).
> - **The tool — TWO reads (review-caught blocker, FIXED):** an indexed `AsyncPostgresStore` runs `query=` as
>   `store JOIN store_vectors` (INNER JOIN), so a row written BEFORE the index existed (every pre-C2 transcript,
>   no `store_vectors` row) is DROPPED → first cut silently regressed N3 recall (thread skipped before the
>   lexical scan). FIX: `_read_thread_transcript` does a query-LESS read for `content` (returns every row,
>   exactly N3) + a SEPARATE best-effort `query=` read for the semantic `score` (None for un-embedded/pre-index
>   rows → lexical fallback). Surfaces a thread on lexical match OR `score ≥ _SEM_THRESHOLD` (0.6); a
>   semantic-only hit shows leading summary lines. Recall is thread/summary-granular — per-turn = Backlog.
> - **THE GATE — met:** deterministic (hermetic concept embedder, NO model download): `test_store_index_config`
>   (4), `test_agent_store` (3: indexed `setup()` builds `store_vectors` + ranks on real pgvector; no-index
>   posture preserved; **pre-index INNER-JOIN regression guard**), `test_matter_conversation_tools` (+6:
>   paraphrase surfaces / filter-only misses same paraphrase / honest absence / **threshold-boundary 0.577<0.6≤0.707**
>   / indexed cross-matter isolation / **end-to-end pre-index pg row still surfaces lexically**). Targeted run
>   **26 passed**; full `tests/agents/` **651 passed/37 skipped/0 failed** locally → CI authoritative, count → PR.
>   ruff + mypy (207) clean. **Live gate (ADR-F015, REAL bge on throwaway pgvector, production index path):
>   paraphrase hits 0.62–0.68 vs off-topic/related-wrong 0.43–0.46 → surfaces the right thread, preserves
>   honest absence; the 0.6 threshold sits in the gap with a precision margin. `docs/fork/evidence/retrieval-eval-slice-c2/`.**
> - **TRAPS (carry forward):** (1) **indexed pg `asearch(query=)` INNER-JOINs `store_vectors`** → rows without a
>   vector (pre-index, or any row written index-OFF) are DROPPED — read CONTENT query-less, score separately;
>   pre-C2 conversation history gets semantic ranking only after it's next offloaded (re-embed on `put`); a
>   `store_vectors` backfill is the optional upgrade (not needed — lexical recall is preserved). (2) the REAL
>   local embedder + heavy PG load crash the dev-box Postgres — run any live embedder check ALONE; C2's CI tests
>   use the hermetic FAKE provider so the suite is safe. (3) `query=` on a filter-only store is a silent no-op
>   (score None) — that None-check is the back-compat seam, don't remove it. (4) NO dev-stack rebuild was needed
>   for C2's gate (throwaway pgvector + the C1-bundled model at `/opt/fastembed-cache`); a real deploy DOES need
>   api+arq rebuilt so `setup()` creates `store_vectors` on the live store DB (non-destructive).
>
> ▶ **PREVIOUS (2026-06-29): RETRIEVAL & MEMORY Phase-2 SLICE C1 — local embedder + matter-document hybrid
> retrieval — MERGED PR #168 (squash `8c424795`); ADR-F049 Slice C1 addendum. Migration 0078 (ADDITIVE), ONE
> new SBOM dep (`fastembed`), gateway change = additive `dimensions` passthrough only.** Configurable injected
> `EmbeddingProvider` (Door A in-process `fastembed`/`bge-base-en-v1.5` 768-dim default $0 + Door B gateway
> `dimensions=768`); `matter_hybrid_search` vector branch reads the additive `document_chunks.embedding_local`
> (KB `embedding vector(1536)` untouched); `tools.py:_search` embeds the query + fuses at alpha 0.5 with FTS
> fallback. Gate (Track-B N=30, local, alpha=0.5): within-doc recall@5 0.314→0.629 (+100%). Traps: local
> embedder + eval volume crash dev-box PG at N≥60 (full-150 → Backlog); per-file backfill sessions; dev-image
> rebuild bundles the model at `/opt/fastembed-cache`. Detail: `f2-slice-c1-local-embedder-shipped` memory.
>
> ▶ **PREVIOUS (2026-06-29): RETRIEVAL & MEMORY Phase-2 SLICE A — matter document tool wired to ONE hybrid
> retriever — SHIPPED (MERGED PR #167, squash `a5efce37`); ADR-F049 Slice A addendum. NO migration/dep/gateway
> change.**
> - **What it does:** collapses THREE copies of the matter FTS query into one retriever
>   `app/knowledge/retrieval.py:matter_hybrid_search`. The production `search_documents` tool AND the Track-B
>   eval `fts_retrieve` both route through it → *"agent mode matches retriever-only"* is structural. With no
>   embedder wired (`query_embedding=None`) it takes the **FTS-only fast path** = byte-identical to the frozen
>   E0 baseline; the **fusion branch** (FTS + pgvector candidates, min-max fused, hydrated) is present +
>   unit-tested with synthetic 1536-dim vectors but **DORMANT** until Slice C passes a real embedding + alpha.
> - **What shipped:** `app/knowledge/retrieval.py` (NEW `matter_hybrid_search` + `MatterSearchHit` +
>   `_MATTER_FROM_WHERE` single-source scope + 3 matter SQL templates; reuses the KB `_min_max_normalize`/
>   `_hydrate_chunks`/`_format_vector` — KB `hybrid_search` UNTOUCHED); `app/agents/tools.py` (`_search`
>   routes through it; `_FTS_SQL` DELETED; unused `text` import dropped);
>   `tests/agents/scenarios/cuad_eval.py` (`fts_retrieve` routes through it; `_EVAL_FTS_TEMPLATE` DELETED);
>   `test_cuad_retrieval_smoke.py` (drift guard repurposed to a frozen `_REFERENCE_FTS` oracle);
>   `test_matter_hybrid_search.py` (NEW — fusion branch, scope isolation, document_id filter).
> - **Load-bearing scope divergence (do NOT converge onto the KB scope):** matter scope = `project_files` ∪
>   `files.project_id`, owner re-asserted, `deleted_at IS NULL`, **NO `ingestion_status='ready'` filter** (a
>   matter chunk is searchable as soon as it exists; the KB path filters, the matter path never did), and
>   **`websearch_to_tsquery`** not the KB side's `plainto_tsquery`. `_MATTER_FROM_WHERE` is the single source
>   of that security boundary (test_agent_tools already guards the no-ingestion-filter behaviour — the
>   searched file is seeded `ingestion_status='processing'` yet must return).
> - **THE GATE — met:** full api suite **2906 passed / 9 failed / 3 skipped** locally — ALL 9 failures are
>   NON-Slice-A and pass/skip in CI: 7 are `pytest.mark.provider`+`skipif(no LQ_AI_GATEWAY_KEY)` live/eval
>   scenario tests (they SKIP in CI; ran locally only because `--env-file ./.env` carries the key, then
>   failed against the local gateway), and 2 `test_ropa_tools` tests that PASS **61/61 in isolation** but were
>   contaminated in the full run by `test_default_area_scenarios.py` (a provider-marked live fixture seeding
>   "Customer Analytics" that ALSO skips in CI). CI (no key) is the authoritative gate — green like N3's
>   2877. (Pre-existing local-run-only isolation flake; out of Slice A scope, NOT introduced here.) ruff
>   (root, CI cmd `ruff … api scripts`) +
>   mypy `app` (206 files) clean; targeted **25/25** (`test_matter_hybrid_search` 3 + `test_cuad_retrieval_smoke`
>   2 + `test_agent_tools` 20 — the tool contract unchanged through the new path). **Track-B re-freeze
>   (ADR-F015 finding, `docs/fork/evidence/retrieval-eval-slice-a/LIVE-VERIFICATION.md`):** the full
>   150-contract CUAD baseline re-run THROUGH THE NEW PATH is **BYTE-IDENTICAL to the frozen E0 baseline** —
>   every metric to full float precision (within-doc hit@8 0.39107 / MAP 0.29645 / recall@5 0.34427; cross-doc
>   hit@8 0.04415 / MAP 0.01834), and the entire within/cross/absent/per-category blocks compare equal. Slice A
>   changes the call path, not the numbers (the run's duplicate baseline.json/md were not committed).
> - **Gotchas (carry forward):** keep the FTS-only fast path byte-identical (the frozen `_REFERENCE_FTS` +
>   the CUAD re-freeze are the guards — don't "optimise" the fast path through the fusion/hydrate flow, which
>   loses the `filename ASC, chunk_index ASC` tiebreak); `matter_hybrid_search` takes raw
>   `project_id`/`user_id` (NOT a `MatterBinding`) to avoid a `retrieval.py → app.agents` import cycle; the
>   CUAD corpus IS present at `api/tests/fixtures/cuad/CUADv1.json` (39 MB, gitignored) — set `LQ_AI_CUAD_DIR`
>   + a SEPARATE `LQ_AI_RETRIEVAL_EVIDENCE_DIR` so the re-freeze never clobbers the frozen E0 baseline; run
>   pytest/ruff in `lq-ai-api-dev` (api→`/app`, `skills→/skills:ro` NOT `/app/skills`, `--network
>   lq-ai_default`, `DATABASE_URL`→postgres via `--env-file ./.env`).
>
> ▶ **PREVIOUS (2026-06-29): RETRIEVAL & MEMORY N3 — cross-thread conversation recall
> (`search_matter_conversations`) — SHIPPED (MERGED PR #166, squash `32cbdd34`); ADR-F049 N3 addendum. NO
> migration/dep/gateway change. The N-LADDER N0→N3 IS COMPLETE.**
> - **What it does:** a thin, area-agnostic, matter-scoped READ tool granted to every matter-bound run
>   whose Store is live. N2 made each thread's transcript persist to the Store (`("conversation",
>   str(thread_id))`); N3 adds the agent's READER so a run in thread 2 can recall what was said in thread 1
>   of the same matter (CLAUDE.md blocker #3). The new tool is the only production code beyond its wiring.
> - **The SQL↔Store join (load-bearing):** the conversation namespace is thread-keyed; the matter→thread
>   link is ONLY in SQL (`AgentThread.project_id`, and the namespace component == `str(AgentThread.id)`). So
>   the tool: validate input → `_load_owned_matter` (404-conflate to `_GONE_MSG`) → **SQL-enumerate the
>   matter's threads `WHERE user_id AND project_id`** (recent-first, capped 20, current thread excluded for
>   whole-matter) → `store.asearch(("conversation", str(tid)))` per thread → Python lexical scan → digest
>   wrapped as untrusted data. **NEVER a bare `("conversation",)` prefix search** (it spans every tenant) —
>   the SQL `WHERE` is the security boundary (commented load-bearing).
> - **Lexical, not semantic (yet):** the production Store is filter-only (no IndexConfig), so
>   `store.asearch(query=…)` is a silent no-op without an embedder (verified in-container) → N3 does its own
>   Python keyword scan (reuses `matter_read_tools._query_tokens`/`_match_score`); Slice C's embedder layers
>   `query=` ranking on top later (no rewrite).
> - **What shipped:** `app/agents/matter_conversation_tools.py` (NEW — `MATTER_CONVERSATION_TOOL_NAMES` +
>   `build_matter_conversation_tools(session_factory, store, *, run_id, binding, current_thread_id)` +
>   `_search_matter_conversations`); `app/schemas/matter_memory.py` (`MatterConversationSearchInput`:
>   query min1/max500, `thread_id: uuid|None`, `extra="forbid"`, malformed→reject); `composition.py`
>   (moved `store = store_provider()` ABOVE the tool block; build+grant the tool gated on `store is not
>   None`; new `MATTER_CONVERSATION_DOCTRINE` injected after the roster doctrine). Tests:
>   `test_matter_conversation_tools.py` (NEW, 13) + grant-disjointness +1 in `test_matter_consolidation.py`
>   + the A5 gate (`harness.Receipt.thread_id`; `_A5` flipped expected-fail→pass with
>   `inject_conversation_store`+`seed_thread_one_transcript`+answer-key expectations+recall rubric;
>   `test_track_a_eval` A5 followup shares the store_provider + seeds-if-not-offloaded;
>   `test_track_a_unit` A5 retargeted) + the prompt-assembly oracle updated for the new doctrine.
> - **THE GATE — met:** deterministic reader lock (`test_matter_conversation_tools.py` 13/13: cross-thread
>   find, cross-matter/owner + foreign-thread_id isolation, current-thread exclusion, reject-not-crash,
>   injection-as-data, audit-body-free) + full api suite **2877 passed / 37 skipped** with the one
>   prompt-oracle test updated+re-verified for the new doctrine (CI re-runs the full suite authoritatively) +
>   ruff (root) + mypy `app` (206 files) clean. **Live A5 finding (ADR-F015,
>   `docs/fork/evidence/n3-search-matter-conversations/`):** A5 **grounded PASS** — thread 2 CALLED
>   `search_matter_conversations`, retrieved thread 1's transcript, answered "Manchester" (judge PASS,
>   `recalled_correctly=true`, `hallucinated_detail=false`); `fixture_valid` (no thread-1 memory writes);
>   `conversation_seeded_t1=true` (short ack didn't compact → seed path fired, the "seed + best-effort live"
>   design). No-regression: A1/A6/A8 PASS; **A7 `cap_exceeded` FAIL is PROVEN unchanged-path DeepSeek
>   variance** (A7 has no store → no conversation tool; its 28-step timeline shows ZERO
>   search_matter_conversations attempts — the N3 tool/doctrine played no role; same failure mode as the E1
>   A7 baseline). Recorded, not re-rolled.
> - **Adversarial review** (4-dim × adversarial verify, 6 agents): **SHIP, 0 blockers**; 1 should-fix folded
>   (the `thread_id` param documented in the tool docstring — the only text deepagents shows the model);
>   security/correctness/regression/simplification all clean (owner+matter SQL boundary, 404-conflation,
>   audit body-free, untrusted-text framing, store-move-up is a pure provider call, no dep/migration).
> - **Maintainer rulings (settled):** (a) scope default = WHOLE-MATTER (no `thread_id` ⇒ cross-thread within
>   owner+matter; supplied ⇒ within-chat, intersected against the matter's set — foreign id silently
>   no-matches); (b) transcript source = STORE-FIRST (offloaded content only; "also search the SQL
>   `AgentRun` transcript for short un-offloaded threads" = a BACKLOG item iff the eval shows Store-only is
>   too sparse); (c) A5 gate = SEED + best-effort live (mirrors N2).
> - **Gotchas (carry forward):** the doctrine is injected unconditionally for matter-bound runs but the tool
>   is store-gated → in a degraded-Store run the agent gets a graceful R6 "not granted" (benign; production
>   always has a live Store so the tool is always present); the conversation Store key races under subagent
>   fan-out (read-only tool tolerates it — `(item.value or {}).get("content","")`); offload fires only on
>   compaction so short threads may have nothing to search (the Store-first limitation → the SQL-transcript
>   backlog item); `query=` stays a no-op until Slice C's embedder; re-verify deepagents/langgraph Store
>   signatures at the next boundary; run pytest/ruff in `lq-ai-api-dev` (repo ROOT + `./skills` mounted,
>   `--network lq-ai_default`, `DATABASE_URL`→postgres); provider eval needs `LQ_AI_GATEWAY_KEY` +
>   `-o addopts=""` and runs the WHOLE matrix (the single matrix test loops all scenarios internally — `-k`
>   can't isolate A5).
>
> ▶ **PREVIOUS (2026-06-29): RETRIEVAL & MEMORY N2 — conversation-history offload + within-chat recall (A6)
> — SHIPPED + MERGED (PR #165, `main` `7063e61f`) (ADR-F049 N2 addendum). NO production code, NO migration,
> NO new dependency. NEXT SLICE = N3 (DONE — above).**
> - **The N2 premise was FALSIFIED in our favour** (recorded so we don't relitigate, like N1): the
>   conversation-history offload was **already wired by N0**. `create_deep_agent` ALWAYS installs the default
>   `SummarizationMiddleware(model, backend)` (deepagents graph.py); N0 passes it our `CompositeBackend`,
>   whose `/conversation_history/` route maps the offload path `/conversation_history/{thread_id}.md` (from
>   `artifacts_root='/'`) verbatim into the Store ns `("conversation", thread_id)`; recall is the path the
>   summary embeds (builtin `read_file`). N0's "installed but unwritten until N2" was satisfied the moment N0
>   shipped — the writer was always the default middleware. So **N2 = verify + test + eval, ZERO production
>   code.**
> - **What shipped (test-only):** `tests/agents/test_summarization_offload.py` (NEW, 5 tests) — the
>   deterministic offload drift-guard: builds the REAL deepagents `SummarizationMiddleware` (via
>   `create_summarization_middleware`, exactly as `create_deep_agent` does) over our `build_memory_backend`
>   composite + an `InMemoryStore`, driven through a langgraph runtime; asserts routing
>   (`artifacts_root=='/'` → prefix `/conversation_history` → `CONVERSATION_ROUTE`, a writable StoreBackend),
>   offload → ns `("conversation",thread_id)` key `/{thread_id}.md`, append-on-2nd (single key), thread
>   isolation, read-back. `tests/agents/scenarios/harness.py` — `run_scenario` gained `compaction_max_input_tokens`
>   (→ `model_builder=partial(build_gateway_chat_model, max_input_tokens=…)`) + `store_provider`, both
>   existing `compose_and_execute_run` params (no production change). `track_a_fixtures.py` — the **`_A6`**
>   scenario (forces compaction over the RFQ matter, recalls a non-fileable aside `ORION-7741`).
>   `test_track_a_eval.py` — A6 wiring + a post-run **`conversation_offloaded`** probe (searches the injected
>   Store → observed proof compaction fired). `test_track_a_unit.py` — A6 well-formedness.
> - **THE GATE — met:** deterministic offload lock (`test_summarization_offload.py` 5/5) + full api suite
>   **2864 passed / 38 skipped / 0 failed** + ruff (root) + mypy `app` (205 files) clean. **Live A6 finding
>   (ADR-F015, not a baseline freeze; `docs/fork/evidence/n2-conversation-offload/`):** at
>   `compaction_max_input_tokens=7000` A6 forced a REAL compaction (`conversation_offloaded=True`, 378 B —
>   opening turn evicted to the Store) and the agent **correctly recalled `ORION-7741`** (L1
>   `recalled_code=True`, verdict PASS) — carried by the LLM summary, `read_file` NOT needed. So native
>   compaction suffices for within-chat recall when the summary preserves the detail; the offload-file read +
>   N3's search tool are the backstop for dropped details / cross-thread. No-regression smoke (N=1): A5/A7/A8
>   verdict PASS as baseline; A1 a transient empty-answer run failure on its UNCHANGED path (E1 baseline
>   8/10 — noise, recorded not re-rolled).
> - **Maintainer rulings (settled):** (1) degraded-key edge (Store live + checkpointer `None` + a single run
>   crossing ~170k → offload file-name falls back to `session_<hex>` while the ns key is `str(run.thread_id)`)
>   = **ACCEPT + DOCUMENT** (doubly moot: degraded runs refuse follow-ups, within-run recall still works) →
>   ADR-F049 **N2 addendum**, no guard; (2) plain-chat transcripts **persist** too (the conversation route
>   is thread-keyed, installs whenever a thread is bound — not matter-gated); (3) A6 exercises the **full**
>   offload→`read_file` path via an injected `InMemoryStore`.
> - **NEXT = N3** (`plans/RETRIEVAL-MEMORY-eval-first.md`): a thin `search_matter_conversations` over
>   `store.asearch` (matter-scoped, 404-conflated, optional `thread_id` filter). *Gate: A5 recall via the
>   tool + a cross-matter 404 security check.* This lifts A5 (cross-thread recall, still ~0) and is the
>   robust backstop when a summary drops a detail.
> - **Gotchas (carry into N3):** the masked judge can't grade a SELF-STATED fact (it strips the user prompt)
>   → A6 puts the ground-truth code in `expectations` as an answer key (fine; docs/prompt/run-id masking
>   preserved); the compaction trigger is content-/model-dependent — at small fixture-doc scale the
>   conversation sits near the boundary (windows 12000/9000 completed but did NOT compact — in-context only;
>   7000 was where it fired) → the robust path is N3's explicit search, not trigger-tuning; **subagent
>   fan-out writes the SAME `/conversation_history/{thread}.md` key via adownload→aedit → a read-modify-write
>   race** (note for N3's reader); offload is best-effort (write failure → `file_path=None`, nothing to
>   recall); re-verify deepagents/langgraph signatures in-container (the oracle); run pytest/ruff in
>   `lq-ai-api-dev` with repo ROOT + `./skills` mounted on `--network lq-ai_default` + `DATABASE_URL`→postgres.
>
> ▶ **PREVIOUS (2026-06-28): RETRIEVAL & MEMORY N1 — the read-only DATA memory tiers moved onto a fork
> middleware seam (`TierMemoryMiddleware`) — SHIPPED + MERGED (PR #164, ADR-F049). NO
> migration, NO new dependency. NEXT SLICE = N2 (DONE — above).**
> - **The N1 premise was FALSIFIED by exploration** (recorded so we don't relitigate): (a) the Matter
>   File (wiki) can't move to the Store without a separate cross-module ADR'd slice — it would desync the
>   cockpit C3-UM APIs, split the single-SQL wiki+fact-ledger+snapshot transaction, and weaken the
>   `guarded_tool_call` chokepoint + structural pin-immutability; (b) deepagents' STOCK `MemoryMiddleware`
>   injects generic `edit_file` self-learning guidance that conflicts with ADR-F042. So **SQL stays the
>   source of truth** and N1 shipped a thin **fork** middleware, NOT the stock one.
> - **What shipped:** `app/agents/tier_middleware.py` — `TierMemoryMiddleware(AgentMiddleware)` (overrides
>   `wrap_model_call`/`awrap_model_call`; appends the rendered tier text via a local `_append_text_block`,
>   no deepagents private-path dep). `composition.py` — new `render_memory_tiers` (the SINGLE source of the
>   4 fence constants + order + degradation); `system_prompt_for` delegates to it (byte-identical, stays the
>   equivalence oracle); `compose_and_execute_run` now passes `system_prompt_for(binding, area_spec)`
>   (base = identity + matter doctrine + area suffix) + `middleware=[TierMemoryMiddleware(tier_text=…)]`
>   (None when nothing renders). `runner.py` — `execute_agent_run` gained a `middleware` param → `agent_kwargs`
>   (factory forwards via `**kwargs`; no factory change).
> - **The tiers (CLAUDE.md § Memory tiers names):** House Brief, Matter File, Matter Corrections, Matter
>   Roster — injected read-only, data-only-fenced, same relative order. **The ONE deliberate, documented,
>   benign delta:** the tiers now render AFTER deepagents' `BASE_AGENT_PROMPT` + the area suffix (the area
>   method is no longer the literal last text; data — incl. human pins — sits closest to the conversation).
> - **THE GATE — met:** prompt-equivalence (the 4 blocks render byte-identical and reach the model — proven
>   by `test_tier_middleware.py` incl. a real-assembly ordering lock + the `test_agent_composition.py` e2e
>   `seen_messages` tests) + **full api suite 2857 passed / 38 skipped / 0 failed** + ruff (root) + mypy
>   `app` (205 files) clean + **Track-A N=1 live smoke green** (4 scenarios terminal through the gateway with
>   the middleware live; rates not re-frozen — N1 is not a baseline freeze, ADR-F015).
> - **Adversarial review** (4-dim × verify, 15 agents): **0 blockers / 0 should-fixes**; 4 nits folded (a
>   real-area-suffix ordering regression test + a tightened `system_prompt_for` docstring covering the
>   oracle-scope + the area-suffix/ordering delta); 7 findings refuted (incl. a non-reproducing
>   ruff-0.15.20 claim and benign content-block-shape/middleware-order observations).
> - **THE PRIZE registered (not built):** the Store-vs-SQL **convergence** + the shared **Practice
>   Knowledge** cross-matter learning tier → **ADR-F050** (proposed) + `plans/PRACTICE-KNOWLEDGE-prize.md`
>   (the two-direction gate: anti-leakage/confidentiality + anti-poisoning; staging→de-id→guard→curator
>   approval→provenance→revoke). Its own multi-slice, research-led, eval-gated milestone AFTER the N-ladder.
>   Lighting up **Lawyer Preferences** (read-back of `autonomous_memory`) belongs to THAT track, not N1.
> - **NEXT = N2** (`plans/RETRIEVAL-MEMORY-eval-first.md`): `SummarizationMiddleware` (profile already set,
>   `factory.py:111`) + verbatim offload to the N0 Store `/conversation_history/` route → persistent
>   within-thread recall post-compaction. *Gate: A6 within-chat recall post-compaction.* N1 does NOT unblock
>   N2 (summarization operates on the message list, not the system prompt) — they're independent.
> - **Gotchas (carry into N2):** middleware can only APPEND after the static base (so tiers land after
>   `BASE_AGENT_PROMPT` — that's the N1 delta); a middleware-injected system message is a CONTENT-BLOCK LIST
>   not a str → tests must flatten via `_seen_system_text`/`_flatten` (the gateway's OpenAI adapter
>   concatenates blocks fine; the Anthropic adapter drops list-content but is unreachable — no `tools`
>   forwarded, CLAUDE.md blocker #2); `system_prompt_for`'s 4 tier params are now test/oracle-only
>   (production renders via `render_memory_tiers` + the middleware); re-verify deepagents/langchain
>   middleware signatures at the N2 boundary; run pytest/ruff in `lq-ai-api-dev` with repo ROOT + `./skills`
>   mounted on `--network lq-ai_default` + `DATABASE_URL`→postgres.
>
> ▶ **PREVIOUS (2026-06-28): RETRIEVAL & MEMORY N0 — the native langgraph `Store` + deepagents
> `CompositeBackend` substrate — SHIPPED + MERGED (PR #163, ADR-F049 now
> ACCEPTED). NO migration, NO new dependency.** N0 gets the agent onto the framework's memory tier
> (the prompt-block swap was N1, above); the agent's builtin `write_file`/`read_file` now persist to a
> matter-scoped, **thread-independent** Store.
> - **What shipped:** `app/agents/store.py` — `AsyncPostgresStore` DI module mirroring
>   `checkpointer.py` (own autocommit psycopg pool, `store.setup()` = library-managed tables NOT alembic,
>   degrade-not-crash), inited+closed in BOTH composition roots (`main.py` lifespan AND `arq_setup.py`
>   worker — runs execute in the WORKER). `app/agents/memory_backend.py` — `AgentRuntimeContext`
>   (frozen dataclass keying the namespaces) + namespace callables + `ReadOnlyStoreBackend` (the
>   storage-level read-only wrapper for company/practice) + `build_memory_backend` (per-run
>   `CompositeBackend(default=skills backend, routes={/memories/{company,practice,user,matter}/ +
>   /conversation_history/})`). Wiring threaded through `composition.py` (a `store_provider` seam
>   mirroring `checkpointer_provider`; builds the backend + `AgentRuntimeContext` from the binding) →
>   `runner.py` (`store=` + `context_schema=` into `agent_kwargs`; `context=` into `stream_kwargs`) →
>   `factory.py` (unchanged — `**kwargs` forwards both).
> - **Namespaces (no `org_id` exists — single-tenant):** company `("company",)` RO · practice
>   `("practice", practice_area_id)` RO · user `("user", owner_id)` RW · matter `("matter", project_id)`
>   RW · conversation `("conversation", thread_id)` RW (installed but UNWRITTEN until N2). Owner segment
>   = `run.user_id`; a run only resolves its OWN owner-checked `project_id`, so no cross-user reach.
>   **No semantic index** (filter-only; `setup()` makes no pgvector table).
> - **THE GATE (maintainer-ruled HONEST gate — corrected from the over-promised "A5 lights up"):** the
>   substrate is proven by a deterministic integration test (`tests/agents/test_memory_backend.py`:
>   cross-thread persistence + cross-matter isolation + company/practice read-only + skills-resolve +
>   an **e2e builtin `write_file`→Store through `create_deep_agent`**) + `test_agent_store.py` (Postgres
>   `setup()` filter-only/idempotent on a throwaway DB). **A5's cross-thread *recall rate* is a tracked
>   finding (ADR-F015), expected ~0 until N3** — N0 ships the substrate, not the recall behaviour (it
>   structurally cannot rise until N2's offload + N3's search tool; the 3 docs were realigned).
> - **Verify:** full api suite **2851 passed / 38 skipped / 0 failed**; `tests/agents` 607 (added the
>   e2e guard); ruff (root) + mypy `app` clean. Adversarial
>   review (4-dim: security/correctness/regression/simplification × verify): **0 blockers**; 1 should-fix
>   folded (couple `runtime_context` to `store` so "rt.context populated" == "routes installed"), 1
>   should-fix folded (the e2e store-ON regression guard), nits folded. **Live (api+arq rebuilt, DeepSeek;
>   `docs/fork/evidence/n0-native-store/`):** api boot "agent memory store ready (filter-only)";
>   `store`+`store_migrations` present (no `store_vectors`); a real run in the arq worker had the agent
>   `write_file` `/memories/matter/n0_check.md` → landed in the Store under `("matter", project_id)` and
>   read back — the full live path proven end-to-end.
> - **NEXT = N1** (`plans/RETRIEVAL-MEMORY-eval-first.md`): replace the hand-assembled prompt blocks
>   (`composition.py` ~305-391: client/wiki/corrections/roster) with `MemoryMiddleware(sources=[…])` per
>   tier reading the Store. *Gate: prompt-equivalence regression (injected digests match the old prompt)
>   + all Track-A scenarios stay green.* This is where the N0 `/memories/*` Store routes start being
>   READ into the prompt — and where the **`/memories/matter/` Store vs the SQL matter wiki**
>   (`project.context_md`, ADR-F042) convergence must be decided (N0 kept them deliberately separate).
> - **Gotchas (carry into N1):** `context_schema` is MANDATORY or `rt.context` is empty and every
>   namespace callable raises (the single load-bearing wiring detail); the Store pool MUST be
>   `autocommit` (`setup()` runs `CREATE INDEX CONCURRENTLY`); namespace components must match
>   `^[A-Za-z0-9\-_.@+:~]+$` (UUIDs fine); `StoreBackend.write` REFUSES overwrite → use `edit` for the
>   auto-write-then-correct flow; deepagents **subagent permissions REPLACE the parent's** → company/
>   practice read-only lives at the STORAGE layer (the wrapper), not a `FilesystemPermission` rule;
>   subagents DO inherit the parent runtime context (same matter namespace) — verified; re-verify
>   deepagents/langgraph signatures at the N1 boundary (minor churn); run pytest/ruff in `lq-ai-api-dev`
>   with repo ROOT + `./skills` mounted on `--network lq-ai_default` + `DATABASE_URL`→postgres.
>
> ▶ **PREVIOUS: RETRIEVAL & MEMORY E1 — the Track-A agentic baseline (masked-judge scenarios)
> SHIPPED + MERGED (PR #161, `main` `a2eabaab`). Phase-E exit REACHED.** E1 is the
> subjective/agentic half of the eval-first instrument (E0 = the objective Track-B retrieval floor).
> *(Follow-up shipping separately: a fan-out "when to delegate for document knowledge work" research note
> → `docs/fork/research/` — input for the Phase-3 strategy/R4 slice, NOT a blocker for N0.)*
> - **What shipped (all `tests/agents/scenarios/`):** `track_a_lib.py` — `build_judging_packet` (the
>   **masked judging packet**: projects steps to the 5 audited `fetch_steps` fields + strips `<think>`;
>   carries ONLY timeline + visible answer + rubric/expectations — never docs / agent prompt / `run_id`),
>   `JudgeRubric`/`JudgeVerdict`, `parse_verdict` (evidence-quote-must-be-in-answer), and `masked_judge`
>   (the gateway fallback judge, generalises `craft_judge`). `track_a_fixtures.py` — A1/A5/A7/A8
>   `TrackAScenario`s. `test_track_a_unit.py` — **free CI net** (masking-leak assertion, verdict parsing,
>   fake-gateway wiring, L1 via `score_all`). `test_track_a_eval.py` — provider-marked live matrix.
>   `harness.Receipt` gained `run_id` (additive). **L1 reuses `evals.scoring.score_all`; masking reuses
>   `evals.runner.fetch_steps` + `evals.scoring.visible_answer` — no new scorer/dependency.**
> - **THE JUDGE (maintainer call):** the **orchestrator (Claude) is the primary judge** over the frozen
>   masked packets (a fan-out Workflow, one independent judge per packet — "Claude-judged DeepSeek", $0 on
>   the gateway); the gateway `deepseek-pro` `masked_judge` is the automated fallback. Masking is what makes
>   Claude-as-judge fair (it never sees the docs/prompt, only what the agent surfaced).
> - **FROZEN BASELINE (N=10, DeepSeek agent, Claude-judged; `docs/fork/evidence/retrieval-eval/track-a/`):**
>   **A1** multi-doc grounding **8/10** (grounded 9/10, no cross-doc bleed 10/10; the 2 fails are
>   cap-exceeded **empty answers** — grounded in the timeline, never delivered); **A5** cross-thread recall
>   **0/10 (RED — turns green with N2/N3)** but **honest-abstention 10/10**; **A7** strategy: **no *autonomous*
>   fan-out 0/10** — DeepSeek synthesises inline on a bounded 4-doc task (judge-appropriate 8/10).
>   INVESTIGATED (not a bug): the `task` tool + the mig-0073 subagents WERE wired/available, and DeepSeek
>   delegates 3× when *coached* (C7b `test_commercial_fan_out_scenario.py`) — uncoached strategy-selection on
>   a small matter, NOT a capability limit; the Phase-3 strategy/R4 question is *at what corpus scale*
>   autonomous fan-out is needed; **A8** negative control honest-absence **10/10**, fabrication 0/10.
> - **Maintainer calls settled (plan §Open calls):** #3 rubric strictness = **record rates, bars unset**
>   (set later vs this baseline); #5 spend = **N=1 smoke / N≥10 freeze**, Claude-judging free; #6 = **single
>   DeepSeek family** now (2nd family = later one-env-var expansion).
> - **PICK UP EXACTLY HERE → START N0:** instantiate `AsyncPostgresStore` in the lifespan (mirror the
>   checkpointer DI seam), pass `store=` + a `CompositeBackend` with
>   `/memories/{company,practice,user,matter}/` + `/conversation_history/` routes to `create_deep_agent`;
>   read-only wrapper for company/practice; namespace-distinctness assertion; key via `rt.context`. **No
>   semantic index yet** (filter-only). **Gate: A5 must light up** (cross-thread recall 0/10 → rises) with
>   nothing else regressing — re-run the Track-A matrix and compare. ADR-F049 is *accepted* with N0.
> - **Gotchas (carry forward):** the **agent's retrieved CHUNK set is still not observable** from steps
>   (only doc filenames in `tool_result` summaries, bounded ~2000 chars) — chunk-level retrieval attribution
>   (a `retrieved_chunks` column) is deferred to N0+ if doc-level proves too coarse; **A5 fixtures must use a
>   NON-matter aside** (the agent auto-writes matter facts via `record_matter_fact` → cross-thread recall of
>   *matter* facts already works via memory; the fixture asserts thread-1 fired no matter-memory write tool);
>   the **`args` Workflow param arrives as a STRING** (`JSON.parse` it in the script); the dev container
>   writes evidence as **root** → chown back; R4 cost cap still a **no-op**; deepagents minors break →
>   re-verify Store/CompositeBackend signatures at the N0 boundary; run pytest/ruff in the dev image with the
>   repo ROOT + `./skills` mounted.
> - **Decision context still live:** ADR-F049 (native Store + CompositeBackend substrate, eval-gated, accepts
>   at N0) + the eval-first plan `plans/RETRIEVAL-MEMORY-eval-first.md` (Phase-E exit reached); PageIndex =
>   eval candidate (Slice P), not a skip; reuse `retrieval_metrics.py`/`cuad_eval.fts_retrieve` (Track B) +
>   `track_a_lib`/`evals.scoring.score_all` (Track A) for any new gate.
>
> ▶ **PREVIOUS (2026-06-28): RETRIEVAL & MEMORY E0 — the CUAD Track-B retrieval-eval instrument + the
> FTS-only baseline SHIPPED + MERGED (PR #160, `main` `d0b117c8`).** Frozen floor
> (`docs/fork/evidence/retrieval-eval/`): within-doc hit@8 **0.39** / MAP 0.30; **cross-doc (150 docs) hit@8
> 0.04 / MAP 0.02 — lexical FTS collapses at scale**, 0.00 for semantically-named clauses — the headroom
> embeddings/rerank/PageIndex must earn. Reuse `retrieval_metrics.py` + `cuad_eval.fts_retrieve`; the matter
> `_FTS_SQL` projects no offsets (the eval mirrors it, drift-guarded); seed `normalized_content` verbatim;
> CUAD CC-BY-4.0/gitignored. (E1 above builds on this harness.)
>
> ▶ **PREVIOUS (2026-06-26): AUTHORSHIP Slice 2 — roster-aware negotiation + richer authorship signals —
> SHIPPED + MERGED (PR #156, main `c661c70`) (ADR-F048 addendum; migration `0077`; NO new HTTP
> route / no new dependency).**
>
> ✅ **MERGED (2026-06-27): PR [#156](https://github.com/sarturko-maker/lq-ai-fork/pull/156) squash-merged under
> the full ADR-F005 gate (all 3 CI jobs SUCCESS on `e07d48c`).** `main` is now at `c661c70`; branch
> `fork/authorship-roster-slice2` deleted. The dev stack already runs the Slice-2 code (api+arq+web at mig `0077`,
> healthy) — no rebuild needed. **NEXT = the maintainer's-call line above** (don't start a new slice without
> confirmation).
>
> Delivers the four Slice-1 deferrals. Maintainer rulings: distinct THIRD-PARTY bucket for `'other'`; lazy
> operator auto-seed; `get_document_metadata` exposes email + docx author.
> - **`'other'` third-party side** (mig `0077` = drop+recreate the `side` CHECK, precedent `0070`; literals
>   in sync across `app.models.project._MATTER_PARTICIPANT_SIDES` / `schemas.matter_memory.MatterParticipantSide`
>   / frontend `PARTICIPANT_SIDES`+`sideLabel`('Third party')+`sideToneClass`(violet)). A known third party
>   (escrow agent, lender's counsel) renders in its OWN bucket — "weigh, don't silently adopt" — in both the
>   editor hand-back and the negotiation render.
> - **`get_document_metadata` tool** (`tools.py`, in `MATTER_TOOL_NAMES`, granted every matter-bound run):
>   email → stored `Document.structured_content` headers (From/To/Cc/Date/Subject, no re-parse); docx →
>   `core_properties` author/last-modified via the shared `load_matter_docx_bytes`. Matter-scoped, 404-conflated,
>   counts-only guard audit. **No new HTTP route → no `test_endpoints`/`test_openapi` change.** UNTRUSTED/forgeable
>   — informs candidacy, never authenticates.
> - **Roster-aware C5a render** (`commercial_tools._render_state_of_play` + `_negotiation_side` + `_group_by_side`):
>   groups marked-up changes/comments by side (OUR SIDE / THIRD PARTY / COUNTERPARTY). **KEY:** an unplaced author
>   defaults to COUNTERPARTY here (the agent opened the counterparty's doc → preserves the C5a respond-to-every-ref
>   loop) — UNLIKE the editor hand-back which ASKs on unknown. Classification is ADDITIVE LABELLING ONLY — every ref
>   still requires one decision; `evaluate_coverage`/`evaluate_anchoring` + the no-silent-action guarantee UNCHANGED.
> - **Lazy operator auto-seed** (`matter_roster_tools.ensure_operator_participant`, called in `composition.py` at
>   run start when a matter is bound): seeds the run owner (the authenticated session user, NEVER model input) as
>   `side='ours'`/`trust='confirmed'` (email as alias), so the agent needn't ask who its own side is. Committed in
>   its OWN session so it's visible to the same run's roster block + tool-time `classify_author`. Idempotent over
>   **active OR retired** rows — a lawyer-retired operator is NOT resurrected (ADR-F042 B2).
> - **DURABLE TRAP — coverage parity.** The negotiation render must keep EVERY change/open-comment ref in the
>   "decide one verdict per ref" list after grouping (the gate keys on refs, not authors). The editor and
>   negotiation renders deliberately do NOT share a bucketer (different unknown-default + the editor drops the
>   agent's own/resolved); they share only the public `classify_author`.
> - **DURABLE TRAP — operator seed must COMMIT in its own session** (the long compose read-session doesn't commit);
>   and probe idempotency over active+retired, else a human removal is undone.
> - **Verify:** mig `0077` round-trip; full api suite **2818 passed / 35 skipped / 0 failed**; mypy + ruff clean.
>   Web svelte-check 0, vitest **987**, prettier clean. Live: Cypress `authorship-roster.cy.ts` **3/3** (Third-party
>   badge, light/dark) + DeepSeek scenario (operator seeded + third party 'other' recorded). Adversarial review
>   (4-dim × verify, 14 agents): **0 blockers / 1 should-fix (fixed: retired-operator re-seed) / nits folded**.
>   Evidence `docs/fork/evidence/authorship-slice2/`.
>
> ▶ **PREVIOUS (2026-06-26): AUTHORSHIP Slice 1 — matter who-is-who roster + hand-back author
> resolution — SHIPPED on branch `fork/authorship-roster-slice1` (ADR-F048; migration `0076`; no new
> dependency).**
> A negotiation has many people redlining; the agent now knows who is who. Replaces the editor Slice-5
> naive author filter (over-trust: every non-agent author treated as the lawyer).
> - **Data** (`matter_participants`, mig `0076`): identity (display name + `aliases` JSONB match-set) →
>   `side` ∈ {ours, counterparty, unknown} + `role_label`, `trust` ∈ {inferred, confirmed}. Matter-scoped
>   (CASCADE); soft-retire via `superseded_at`; CHECK literals mirror `app.models.project` (keep in sync).
> - **Agent** (`app/agents/matter_roster_tools.py`, ZERO model calls): `record_matter_participant`
>   (auto-write `inferred`; **human-confirmed never overridden** — at most aliases widen) +
>   `list_matter_roster` + the pure `classify_author(author, roster) → agent|ours|counterparty|unknown`
>   (Python alias-match, normalised lower/trim — never SQL from the untrusted author string). Granted to
>   EVERY matter-bound run (all areas), grant set disjoint. Roster injected read-only (`format_roster_block`
>   → `MATTER_ROSTER_PROMPT`) + `MATTER_ROSTER_DOCTRINE` (record from emails/statements; on a re-read
>   incorporate ours, treat counterparty as a position, **ASK** on unknown then record the answer).
> - **The over-trust fix** (`review_edited_document_tools.py`): `_classify_edits` buckets each
>   change/comment via the roster (agent's own `DEFAULT_AUTHOR` dropped); `_render_supervised_edits` renders
>   OUR SIDE (incorporate) / COUNTERPARTY (negotiating position) / UNIDENTIFIED (ASK the user) distinctly.
> - **Check-in needs NO new machinery** — there is no langgraph interrupt and no `ask_user` tool; the agent
>   asks in its answer, the run ends, the user replies → existing thread-resume (ADR-F008). Doctrine, not a gate.
> - **Email signal is already agent-visible** (`read_document()` returns the `From:` line) — no ingestion
>   change for Slice 1; a structured `get_document_metadata` tool is deferred to Slice 2.
> - **Human surface** (`app/api/matter_roster.py`): `POST /matters/{id}/roster` (create, `trust='confirmed'`,
>   `user_id` from session), `PATCH /…/roster/{entry_id}` (partial edit, re-confirms), `POST /…/roster/{entry_id}/retire`
>   (soft). Owner-scoped 404; counts/IDs+side-only audit (`matter_roster.*`, no name/role text). The active
>   roster folds into the composite `GET /matters/{id}/memory` (`roster` field). Cockpit **Participants**
>   section in `MemoryPanel.svelte` (add/edit/remove; side badge; confirmed marker).
> - **DURABLE TRAP — author strings are untrusted/forgeable** (ADR-F048 §Consequences): a counterparty could
>   set their docx author to our lawyer's name → classified `ours`. The roster *reduces* over-trust (unknown
>   → ask) but is NOT cryptographic identity. Trusted authorship (WOPI-stamped) is future work.
> - **DURABLE TRAP — meta-test path count.** New roster routes → `test_endpoints.IMPLEMENTED_ROUTES` (PATCH
>   counts) + `test_openapi.EXPECTED_PATHS` + the `len(actual)` assertion (151 → 154; 3 path STRINGS:
>   `/roster`, `/roster/{entry_id}`, `/roster/{entry_id}/retire`).
> - **Verify:** migration `0076` upgrade→downgrade→upgrade round-trip on a throwaway pgvector container;
>   new `test_matter_roster` (20) + `test_matter_roster_api` + rewritten `test_review_edited_document` +
>   composition roster grant/inject tests; **full api suite 2800 passed / 34 skipped / 0 failed**, mypy +
>   ruff clean. Web: svelte-check 0, vitest **987**, prettier clean. Live Cypress `authorship-roster.cy.ts`
>   (add/edit/remove + light/dark) — run after rebuilding the `web` container.
> - **Deferred → authorship Slice 2 (on record):** C5a negotiation-path classification
>   (`extract_counterparty_position`/`respond_to_counterparty`); structured `get_document_metadata`; an
>   `'other'` side for third parties; auto-seed the operator/WOPI user as `ours`.
>
> ▶ **PREVIOUS (2026-06-26): editor Slice 5 "Done — hand back to agent" — SHIPPED on branch
> `fork/libreoffice-editor-slice5` (ADR-F047 Slice-5 addendum; NO migration / no new HTTP route / no new
> dependency). ✅ THE IN-APP WORD-EDITOR MILESTONE IS COMPLETE.**
> The lawyer clicks **Done — hand back** in the editor → the doc is saved → the editor closes and the
> conversation composer is **primed + focused** with an editable instruction naming the doc; the lawyer sends
> it (the existing `createRun({prompt, thread_id})` path) and the agent re-reads their edits.
> - **Resume was already real** — the agent-run subsystem continues a thread via the langgraph checkpointer
>   (`create_agent_run(thread_id=…)`); the CLAUDE.md "single-turn" blocker is the LEGACY CHAT endpoint, NOT
>   agent runs. The frontend resume is the existing `ConversationPanel.submit()` path — no new run code.
> - **"Zero new agent code" was wrong** (maintainer: *trusted supervisor*): C5a `extract_counterparty_position`
>   frames markup as the UNTRUSTED other side — wrong for a trusted lawyer. New **generic, area-agnostic** tool
>   `review_edited_document` (`app/agents/review_edited_document_tools.py`), granted to EVERY matter-bound run
>   beside the matter-memory tools: reuses `read_state_of_play` in a TRUSTED frame + **filters out the agent's
>   own pending redline** (author == `DEFAULT_AUTHOR`). Doctrine `MATTER_REVIEW_DOCTRINE` in the prompt (no
>   migration). Matter-docx loaders factored `commercial_tools` → generic `tools.py` (DRY).
> - **DURABLE TRAP — track-changes recording.** An Adeu redline has tracked CONTENT but NOT the
>   `<w:trackChanges/>` recording flag → the editor opens with Record Changes OFF → the lawyer's edits are
>   UNTRACKED (invisible to the re-read). Fixed in the BYTES: `redline_service.ensure_track_changes_recording`
>   (lxml) injects the flag into the redline output's `settings.xml`, **schema-ordered** (CT_Settings is an
>   ordered sequence) and handling an explicit `w:val="false"` (Word's "tracking off" → flip ON). Do NOT use a
>   client `.uno:TrackChanges` postMessage — it's a TOGGLE (turns recording OFF if already on) + races the load.
> - **DURABLE TRAP — hand-back button enablement.** Gate it on `phase==='ready'`, NOT on `saveState` leaving
>   `'loading'` (Collabora's `Document_Loaded` postMessage is ~50/50 under automation → a saveState gate traps
>   the user with a dead button + breaks Cypress). The CLICK guarantees the save (dirty → save-then-handback;
>   pure `saveTickOutcome` decides saved/failed/pending). Live Cypress: inject the `Document_Loaded` postMessage
>   to drive saveState deterministically.
> - **Authorship is naive for now** (one agent author == "ours"; ANY other author → "the lawyer", incl. a
>   counterparty's markup if present — bounded by the R6 grant + a per-author "flag it" cue, not eliminated); a
>   proper "who's on our team" identity model is a flagged Backlog slice (maintainer).
> - **Verify:** API suite **2775 / 0 failed** (+ Slice-5 tests), mypy + ruff clean; web svelte-check 0, Vitest
>   **976**, prettier clean; live headed-Cypress hand-back (editor → close → primed composer), evidence
>   `docs/fork/evidence/libreoffice-slice5/`. Adversarial review (4-dim × verify, 18 agents): **0 blockers**;
>   4 should-fixes + cheap nits folded (recording val=false + schema order, trusted-frame author cue, clean_view
>   label, EditorPhase reuse, `saveTickOutcome` test, this HANDOFF); deferred-on-record nits: lawyer-reply
>   `parent_id` handling, `_render_redline` inline dup (divergent), `_render_supervised_edits` over-passing.
>
> ▶ **PREVIOUS (2026-06-26): editor POLISH slice (4b) — SHIPPED on branch `fork/libreoffice-editor-slice4b`
> (ADR-F047 Slice-4b addendum; frontend + compose only — NO backend/migration/dependency).**
> Fixed the 4 maintainer-reported Slice-4 UX defects, live-verified at 1920/1440/1024 (light+dark):
> 1. *Editor too narrow* → `ConversationHost` editor card `flex-[2_1_0%]` vs conversation `flex-1` (2/3 : 1/3)
>    **+ the load-bearing companion: `DocumentEditorPanel` `<section>` needs `w-full`** or it shrinks to ~iframe
>    intrinsic width and leaves the blank gap (the "white space reserved for a panel" — was complaint #4).
> 2. *"What's New"/feedback/update popups* → compose `extra_params`: `--o:home_mode.enable=${COLLABORA_HOME_MODE:-true}`
>    (**the ONLY lever that sticks on prebuilt `collabora/code`**; **TRADE-OFF: caps 20 conn / 10 docs**, env-override)
>    + `--o:allow_update_popup=false`. `COLLABORA_HOME_MODE` + `COLLABORA_SSL_TERMINATION` now in `.env.example`.
> 3+4. *Doc tiny at 30% / whitespace-right* → **client-side iterative fit-to-width** off the **same-origin** internal
>    map (`iframe.contentWindow.app.map.setZoom` — there is **NO zoom postMessage**), fully `try/catch`-guarded.
>    THREE hard-won facts (all probe-verified, probes since deleted): **(a)** drive it from a **poll + ResizeObserver**,
>    NOT the one-shot `Document_Loaded` postMessage (unreliable + docPx lags it); the observer re-fits on every width
>    change (slide-in / rail-collapse / window-resize). **(b)** `getScaleZoom` is **base-2 but Collabora's real pixel
>    scaling is ~1.2×/level**, so a single computed jump lands ~0.68 short → **iterate ONE level/tick off the MEASURED
>    docPx** (pure unit-tested `nextFitAction`: grow to a 92–99% band, back off 1 level on overflow). **(c)** gate
>    convergence on **`getSize()` being STABLE across ticks** (it lags the iframe resize → a shrink vs a stale large
>    width leaves the doc overflowing the new pane) + separate the long cold-boot wait from the short fit budget.
>    A `fitted` spinner overlay masks the cold-zoom→fit jump.
>
> **DURABLE TRAPS (4b):** the internal-map reach (`app.map`/`_docLayer._docPixelSize`/`getSize`/`setZoom`) is
> version-fragile — keep it isolated behind `getCoolMap()`+`nextFitAction`, fully guarded (no-op → Collabora's default
> zoom, never a crash). `getScaleZoom` ≠ Collabora's pixel scaling (don't trust it; iterate off measured docPx).
> `getSize()` lags element resize (gate on stability). The `<section>` filling its flex slot needs **`w-full`** not
> just `h-full`. **Verify:** svelte-check 0; Vitest **969** (+6 `nextFitAction`); headed Cypress asserts doc fills pane
> (ratio∈[0.8,1.0]) at 3 widths; evidence `docs/fork/evidence/libreoffice-slice4b/`. Adversarial review (4-dim×verify,
> 20 agents): **0 blockers / 0 should-fixes**; all confirmed nice-to-haves folded (resize-refit, fit overlay,
> `nextFitAction` unit tests, `.env.example` vars, symmetric `load()` teardown).
>
> **NEXT = Slice 5 = "Hand back to agent"** (editor milestone's last slice): "Done — hand back" action beside Close →
> save → resume the run on the same `thread_id`; the agent re-reads the lawyer's tracked changes + comments via the
> existing **C5a** `extract_counterparty_position` path — **zero new agent code**.
>
> ▶ **PICKUP (2026-06-25): in-app Word editor — Slice 4 (cockpit Editor panel + reskin) SHIPPED**
> (branch `fork/libreoffice-editor-slice4`; **ADR-F047 Slice-4 addendum**; NO backend/gateway change, NO
> migration, NO new dependency). Slices 1–3 MERGED (S3 = PR #151, `8710af4`). **NEXT (after 4b) = Slice 5 = "Hand back to
> agent"** (the editor milestone's last slice): save → resume the run on the same `thread_id`; the agent re-reads
> the lawyer's tracked changes + comments via the existing **C5a** `extract_counterparty_position` path — **zero
> new agent code**. Put the hand-back affordance in the editor chrome (a "Done — hand back" action beside Close).
>
> **What Slice 4 shipped.** The lawyer opens an agent-redlined `.docx` IN the cockpit: it renders in a reskinned
> Collabora iframe + edits save back through the S3 WOPI PutFile.
> - **Asset-URL blocker solved (the S1 open question):** `cool.html` uses **absolute root asset paths**
>   (`/browser/<hash>/…`) + a `/cool/<wopisrc>/ws` socket (`data-service-root=""`), so the S1 `/collabora/`
>   sub-path could never serve the iframe. Fix = host Collabora at its **native root paths** in `web/nginx.conf`
>   (`/browser/`, `/cool/` WS-upgrade, `/hosting/`, **no strip**); the admin-deny stays a **regex** location so
>   nginx matches it BEFORE the plain-prefix proxies (admin paths still 404). `docker-compose`:
>   `COLLABORA_SSL_TERMINATION` defaults **false** for HTTP dev (→ `ws://`); **prod MUST set `true`**. Frontend
>   re-homes the discovery `urlsrc` PATHNAME onto `window.location.origin`.
> - **UX (maintainer-specified):** agent redlines (or lawyer clicks *Edit* in Documents) → editor **slides in
>   from the right**, conversation stays **left**, the practice-area **rail gracefully collapses** (shared
>   `cockpit.editorOpen` signal; `+layout.svelte` restores it only if it collapsed it). Conversation **never
>   remounts** (live-SSE): always the first flex child; editor flies in as a sibling (hidden+mounted on a
>   narrow/stacked host so the editor gets the whole pane). Auto-open fires only for a **freshly** produced
>   redline — baseline of existing redline ids snapshotted EAGERLY when the matter is known (NOT on the first
>   completed-run refresh — a review-caught bug where the headline "fresh conversation, first ask is a redline"
>   silently never opened); won't yank a doc the lawyer is editing.
> - **Launch = WOPI form-POST:** `POST /files/{id}/editor-session` (exists) → `GET /hosting/discovery` urlsrc →
>   iframe carries only `WOPISrc`; a hidden `<form method=POST>` POSTs the `access_token` (never in a URL).
>   **Reskin** = WOPI `ui_defaults` (classic toolbar, no sidebar/ruler — RELIABLE) + best-effort
>   `Hide_Menubar`/save-pill via same-origin (origin-checked) postMessage (one-shot `App_LoadingStatus` races the
>   `Host_PostmessageReady` handshake → reliable on a real cold open, ~50/50 under rapid automation; degrades
>   gracefully). **Deferred (incremental):** charcoal toolbar theming (`css_variables`) + reliable menubar-hide.
> - **Verify:** svelte-check 0 errors; **Vitest 963**; prettier/eslint clean (lone eslint = pre-existing
>   `catch (e)` in untouched code). **Live (headed Cypress, real Collabora):** agent redline renders with tracked
>   changes + comments (light/dark × wide/narrow); **edit→save round-trips through PutFile** (DB: `(agent draft)`
>   snapshot + live row flipped human-authored + `editor.file_saved` audit); **auto-open regression test passes**.
>   Evidence `docs/fork/evidence/libreoffice-slice4/`. Adversarial review (4-dim × verify, 13 agents): **5
>   confirmed / 4 refuted**, all 5 folded (auto-open seed + yank-guard + stacked-full-width + `isRedlineOutput`
>   dedup + failed-save `success` flag).
>
> **Slice 3 verified (MERGED):** ruff + mypy clean; migration **0075**
> round-trip on a throwaway DB; targeted `test_wopi`+storage+meta **68 passed**; **live smoke 20/20** on the
> rebuilt api (real MinIO+DB) incl. snapshot-then-mutate at the storage level
> (`docs/fork/evidence/libreoffice-slice3/`); adversarial review (4-dim × verify, 11 agents) **5 confirmed / 2
> refuted**, all folded. **The live dev stack is at mig 0075 with api+arq rebuilt on the merged code.**
>
> **Slice 3 what shipped (the WOPI write half; api only — no web/nginx change).** `POST /wopi/files/{id}/contents`
> (`X-WOPI-Override: PATCH`); session now **editable** (`UserCanWrite=true`/`SupportsUpdate=true`/`ReadOnly=false`).
> **Version model = snapshot-then-mutate (maintainer's call), as TWO durable commits:** on the FIRST human save of
> an agent redline (`created_by_run_id` set) the agent's bytes are `copy_object`'d to a NEW immutable `File` row
> (`(agent draft)`, provenance kept → C7a Documents tab, key==id per ADR-0005) and the live row is flipped to
> `created_by_run_id=NULL` — **committed BEFORE** the live object is overwritten — so a PutFile retry after a later
> commit failure never re-snapshots the edited bytes. Then the live row is overwritten in place (`hash`/`size`/
> `updated_at`). Later saves mutate only; identical-hash = no-op. Untrusted body gated: size cap → 413,
> `guard_ooxml` (REUSED, in `pipeline/readers/_base.py`) + `ooxml_subtype=='docx'` → 400; lock via pure
> `decide_putfile_lock` (409 + `X-WOPI-Lock`); `X-COOL-WOPI-Timestamp` save-race → `409 {"COOLStatusCode":1010}`.
> **GetFile streams CHUNKED (no pinned Content-Length)** so it's correct across any DB/storage divergence window.
> **`files.updated_at`** (mig **0075**, nullable) makes `LastModifiedTime = updated_at or created_at` honest.
> Counts-only audit `editor.file_saved`; no model calls / no gateway reach / no new dependency. Decisions =
> **ADR-F047 Slice-3 addendum**. Research `docs/fork/research/libreoffice-editor.md`; Slice 1 = isolated
> `collabora` service + `/collabora/` proxy; Slice 2 = the WOPI read host (Slice-2 addendum).
>
> **Slice-4 durable traps (carry into S5 / any UI work):** Collabora's lifecycle postMessages only flow after
> the host pings `Host_PostmessageReady`, and `App_LoadingStatus` is ONE-SHOT — so the save-pill/menubar-hide are
> best-effort (retry the ping; degrade gracefully; don't gate a test on the pill). The redline-render canvas
> tiles paint several seconds AFTER the `<canvas>` element exists — settle generously before a screenshot.
> Cypress `trashAssetsBeforeRuns` (default true) WIPES `cypress/screenshots/` before EACH spec run — copy
> evidence out to `docs/` immediately, and run capture specs LAST. A real edit→save round-trip is drivable via
> Collabora postMessage `Action_Paste` + `Action_Save` (then verify the DB), but it MUTATES the file one-shot
> (agent→human-authored + a snapshot). The committed `libreoffice-editor.cy.ts` is live (needs the stack +
> Collabora + a redline in the Atlas matter) — not a CI gate.
>
> **Build/licence posture (resolved, unchanged):** **Collabora is MPL-2.0, NOT AGPL** (lighter than the
> grandfathered PyMuPDF AGPL). Dev + every integration slice run the **prebuilt `collabora/code`** pinned by
> digest (`sha256:75859dc9…` = 26.04.1.4). Clean unbranded/supported **production** posture (self-build OR
> subscription) is a deferred productionisation decision (MILESTONES Backlog). PyMuPDF-AGPL-cleanup is a separate
> backlog slice.
>
> **Carry into Slice 5 (durable traps):** run api ruff/pytest in the **dev image** (`lq-ai-api-dev`) with
> **`./api` mounted at `/app` AND `./skills` at `/skills:ro`** on `--network lq-ai_default` with `DATABASE_URL` →
> postgres; ruff uses the **repo-root** `ruff.toml` (mount repo root). Web: `cd web && npm run check && npm run
> test:frontend`; **rebuild the prebuilt `web` container before any UI/Cypress check** (it serves a built bundle).
> Cockpit Cypress nav: narrow needs `lq-cockpit-new-conversation` first; tabs use `class:hidden` (no-remount
> invariant); `{@html}` only via `renderModelMarkdown`. When a migration lands, rebuild api (+arq-worker) — api
> auto-migrates on boot; NEVER host-side `alembic upgrade` on the live DB; `docker image prune -f` (dangling) after
> a build. New api routes → BOTH `test_endpoints.IMPLEMENTED_ROUTES` AND `test_openapi.EXPECTED_PATHS` (a GET+POST
> on the same path string is ONE OpenAPI path). `gh pr create` → **`--repo sarturko-maker/lq-ai-fork`**. The
> `collabora/code` image ships **only bash**; the sandbox runs on **MKNOD alone**.

## North star (the goal, not a prompt)

**A practice-area agent is, in effect, a legal counsel a human is supervising — qualified in that area.**
*counsel* = real tools + gates + client memory + work product; *qualified* = enforced model/harness
qualification (F0-S9 tier floor) + area competence via curated tools and **controlling skills**; *supervised* =
human-owns every material write + escalation gates + auditable receipts. Full statement at the top of the COMM
plan (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`).

## State — **COMMERCIAL milestone OPEN; C-R0 ✓ C0 ✓ C-CLIENT ✓ C1 ✓ C2 ✓ C4 ✓ C8 ✓ C9 ✓ + cockpit chat-UX ✓. C3 REFRAMED → matter-memory track (C3a/b/c); ADR-F042 ACCEPTED. C3a ✓ · C3b-1 ✓ · C3b-2 ✓ (ADR-F043) · C3c-1 ✓ (READ backend, ADR-F044) · C3c-2 ✓ (cockpit Memory panel) · C3-UM ✓ (the human "update memory" UX — pin composer + inline correct-a-fact + retire). The ENTIRE matter-memory track (read + write + human-correct) is SHIPPED. **C8/C9 redline-eval RE-RUN ✓** (2026-06-24): re-ran both
craft evals with the `surgical-redline` skill LOADED — confound removed, finding CONFIRMED. **REDLINE WORD-DIFF ✓**
(2026-06-24, branch `fork/redline-worddiff-adeu`, **ADR-F045**): the redline tool now renders surgically via Adeu's
NATIVE `adeu.diff.generate_edits_from_text` (applied via `engine.apply_edits` to bypass `validate_edits`) instead of
the wholesale prefix/suffix-trim path that SWALLOWED interiors; skill simplified to "quote the clause, change only the
necessary words — the tool diffs it." **Live-judged (Claude Opus 4.8): C9 surgical-pass 3/7 → 6/7, the Aegis NDA
pervasive-mutualisation case now STRONG·surgical (survived the refuter), seam defects eliminated.** **C7 SPLIT →
C7a redline-download SHIPPED** (2026-06-24, branch `fork/c7a-redline-download`, **ADR-F046**, migration `0071`): a
cockpit **Documents tab** + an **inline run-timeline download** surface the agent's redlined `.docx` over a new
`GET /matters/{id}/files` + a `File.created_by_run_id` provenance column, reusing the existing
`GET /files/{id}/content` (no new bytes path / SSE change). Live-proven on Atlas: a real DeepSeek redline →
output carries `created_by_run_id` → appears in the tab + inline. **C5 SPLIT → C5a PROVABLE NEGOTIATION LOOP
SHIPPED** (2026-06-24, branch `fork/c5a-negotiation-core`, **ADR-F032**, NO migration/endpoint/dep): the agent
reads the counterparty's marked-up `.docx` (Adeu-native tracked changes + comments) via
`extract_counterparty_position` → a `StateOfPlay` checklist, and responds to **every** change/comment via
`respond_to_counterparty` (closed taxonomy accept/reject/counter/leave_open/escalate + reply) under a
**code-enforced no-silent-action gate** (upfront coverage: exactly one decision per ref; post-write
reconciliation: every decision proved to land). Live-proven on DeepSeek: round-2 NDA → extract→respond,
accepted benign edits, rejected the one-directional swap (reverted to mutual), **escalated the below-floor
perpetuity demand (left visible, not conceded)**, replied to the comment; full coverage in one pass
(`docs/fork/evidence/c5a/`). **C5 SPLIT further → C5b-1 COMMENT-WIPE FIX SHIPPED** (2026-06-24, branch
`fork/c5b1-comment-wipe-fix`, ADR-F032 addendum, NO migration/endpoint/dep): the C5a guarantee was lossy at the
*document* level — a comment `reply` was silently deleted when the agent accept/reject-ed the change it was
anchored to (Adeu reports it `applied`; only raw-OOXML inspection caught it). Fixed with three code layers —
anchor-map capture (`StateOfPlay.comment_anchors`), an upfront `evaluate_anchoring` gate (reject `reply` on an
accept/reject-ed anchored change), and document-level reply-survival reconciliation. Live-re-verified at the
OOXML level (`docs/fork/evidence/c5b1/`): the counterparty comment now SURVIVES the round (it was deleted
before). **C5b-2 NEGOTIATION-REVIEW SKILL SHIPPED** (2026-06-25, branch `fork/c5b2-negotiation-review-skill`,
ADR-F032 addendum + ADR-F041, migration `0072`): the **craft layer** — a curated `negotiation-review` skill
(round-2 companion to `surgical-redline`) bound to Commercial + the stale 0066 negotiation doctrine refreshed +
a provider-marked DeepSeek/Claude-judged craft eval. Live (DeepSeek, `docs/fork/evidence/c5b2/`): **3/3
substantive craft pass** (one-sided strip reverted to mutual, below-floor perpetuity held, full coverage,
nothing conceded); **counter-with-reply 0/3** — an honest recorded tuning finding (the model reverts §3 rather
than counter-with-reply, so the comment is preserved-but-orphaned; the guarantee holds, no silent loss).
**C5b-3 NEGOTIATION LIVE VERDICT CHIPS SHIPPED** (2026-06-25, branch `fork/c5b3-deal-change-chips`, ADR-F032 +
ADR-F024 addenda, NO migration/endpoint/dep): the **live signal** on the round-2 loop — as the agent responds to
the counterparty, the cockpit flashes a transient **verdict chip per item** inline in the conversation ("C1 ·
accepted", "C3 · countered", "Com:1 · escalated"). Clones the `data-ropa-change` ledger→drain→transient-frame
seam (PRIV-9b), generalised to a `LiveChange`/`ChangeLedger` Protocol (area-agnostic runner drain; `RopaChange` +
new `DealChange` each `publish` themselves). `respond_to_counterparty` records `(ref, verdict)` per decision ONLY
on a verified+saved round; `data-deal-change` frame is `{ref, verdict}` (audit-safe, no clause text). Chip lives
in `ConversationPanel` (Commercial has no register), persists across stream re-opens, decays. Live-proven
end-to-end on DeepSeek (5 frames) + deterministic Cypress light/dark (`docs/fork/evidence/c5b3/`).
**NEXT = maintainer's call: C7b (drafter/reviewer fan-out roster) / C6 (controlling playbook skills — needs ADRs
F036/F038 first). Backlog: counter-with-reply skill tuning + a Claude-judged eval re-run when the gateway has an
Anthropic key (deepseek-pro stood in as judge — Claude not reachable locally).**

C4 was built **ahead of C3** (maintainer reprioritised 2026-06-22: C4 retires the milestone's central risk +
produces the work product). The full decomposition: `docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`.
**Privacy PARKED** (`docs/fork/plans/PRIV-BACKLOG.md`). **MCP capability** is its own approved milestone.

**⚠ Gateway aliases (operational, UNCOMMITTED, LOCAL):** `smart`/`fast`/`budget` repointed
minimax/MiniMax-M3 → deepseek on the local gateway (MiniMax out of quota). **`deepseek` alias has quota** and is
the qualified live-test target. Revert when MiniMax quota returns. C9 fact: `deepseek` → `deepseek-v4-flash`;
**`deepseek-pro` → `deepseek-v4-pro`** (both wired in `gateway.yaml`, same DeepSeek account/quota) — the
stronger tier for the "is it the model?" control.

## Done this session (C7b — DRAFTER/REVIEWER FAN-OUT ROSTER + POST-FAN-OUT RECONCILIATION — branch `fork/c7b-fan-out-roster`; ADR-F034; migration `0073`; NO endpoint/dep)

**What:** the complex-deal **roster** + the **reconciliation pass**. The lead fans out `clause-drafter` (one per
material head) + consults `clause-reviewer`, then reconciles the drafts into ONE position per head before emitting
one work product. Completes C7 (C7a download + C5b-3 live signal already shipped).
- **Fan-out is deepagents-native + model-driven — C7b added NO orchestration** (see the pickup note above). The
  roster is two declarative subagent dicts; the reconciliation is a single-dispatch tool gate, NOT a guaranteed
  flow (the flow guarantee is the deferred O-series — ADR-F034 names this boundary honestly).
- **Migration `0073`** (`down_revision 0072`): `_extend_commercial_roster` — a **reconciling** never-clobber JSONB
  swap of the verbatim 0057 single-researcher config → `[document-researcher, clause-drafter, clause-reviewer]`
  (0057's `= '{}'` guard is dead now; mirror 0066/0072's `WHERE col = :old` instead) + `_bind_deal_review_skill`
  (NOT EXISTS). Both module-level for the idempotency test. New subagents: model-free (ADR-F010), no `tools`
  (inherit guarded matter tools), `skills` ⊆ area (ADR-F017).
- **`skills/deal-review/SKILL.md`** (ADR-F041 craft layer, bound in 0073): triage → fan out per head → review
  (over-reach/under-protection/inconsistency/gaps) → `reconcile_positions` → emit one work product.
- **`reconcile_positions` tool** (in `COMMERCIAL_TOOL_NAMES`) + pure `evaluate_position_consistency`
  (`schemas/commercial.py`, mirrors `evaluate_coverage`): a head where drafts diverge needs an explicit
  `resolutions[head]` or the batch is **rejected** (no-silent-divergence). On success records a SAVEPOINT-isolated
  **counts+head-names-only** matter receipt (`_record_reconciliation_receipt`) + audits **counts only**. Records
  only on success.
- **Verify:** full api suite **2708 passed / 32 skipped / 0 failed**; ruff + mypy clean; migration round-trip
  (upgrade→downgrade→upgrade) on a throwaway pgvector DB. **Live (DeepSeek, `docs/fork/evidence/c7b/`):** the real
  agent fanned out **3 `task` delegations / 43 nested steps** and called **`reconcile_positions` (2 calls → 1
  receipt)** end-to-end — fan-out + reconcile + receipt all proven live (run ends `cap_exceeded` only because
  deepseek-flash keeps exploring AFTER reconciling — an honest ADR-F015 over-exploration finding, not a mechanism
  defect; mechanics are deterministically pinned). Adversarial review: **0 blockers / 0 should-fixes / 1 nit
  folded** (a docstring overstated resolution precedence — code is correct), 4 refuted; security clean
  (audit counts-only + receipt head-labels-only verified, matter-scoped, no leaks).

## Done earlier this session (C5b-3 — NEGOTIATION LIVE VERDICT CHIPS — branch `fork/c5b3-deal-change-chips`; ADR-F032 + ADR-F024 addenda; NO migration/endpoint/dep)

**What:** the **live signal** on the round-2 loop — the C5 analogue of PRIV-9b's changed-row highlight. As the
agent responds to the counterparty, the cockpit flashes a transient **verdict chip per item** inline in the
conversation. Clones the `data-ropa-change` ledger→drain→transient-frame seam.
- **Seam generalised (the one structural call):** new `app/agents/live_changes.py` = a `LiveChange`
  (`publish(publisher)`) + `ChangeLedger` (`drain()`) **Protocol**. The runner drain is now area-agnostic
  (`for change in change_ledger.drain(): change.publish(publisher)`). `RopaChange` gained a 2-line `publish`
  (byte-identical Privacy behaviour); the new `app/agents/deal_changes.py` `DealChange`/`DealChangeLedger` is
  the 2nd implementer (composition root already anticipated a 3rd — assessments). ADR-F024 addendum.
- **Backend:** `RunStreamPublisher.deal_changed(ref, verdict)` → transient `data-deal-change` `{ref, verdict}`
  (audit-safe; no clause text). `composition.py` creates a `DealChangeLedger()` in the COMMERCIAL branch +
  passes it to `build_commercial_tools`. `respond_to_counterparty` records one `(ref, verdict)` per decision
  ONLY after `recon.ok` + persist (record-only-on-a-real-change; nothing on a rejected round).
- **Web:** `run-stream.ts` `parseDealChangePayload` (both `ref`+`verdict` load-bearing; unknown verdict → null)
  + pure `dealVerdictLabel`/`dealVerdictTone` presenters. `ConversationPanel.svelte` `case 'data-deal-change'`
  → `pushDealChip` (dedupe by ref, 6s decay, reset on run change via `dealChipRunId`); chips render inline in
  the running turn, coloured per verdict tone via `--color-status-*` tokens. **Key fix:** chips are NOT cleared
  in `clearStreamState` (the poll re-opens the stream + re-delivers the transient frames every 2s, keeping them
  lit) — reset on run change / thread switch (`startPolling`) / decay / `onDestroy`.
- **Verify:** backend `tests/agents` 489 passed/1 skipped + 8 new tests green; full api suite green (see below);
  ruff + mypy clean. Web `npm run check` 0 err, vitest **942** (+ deal-change parser/presenter tests),
  prettier clean (lone eslint error = pre-existing `catch (e)` in untouched code). **Live (DeepSeek):** the
  provider-marked `test_commercial_deal_change_frames_live` captured **5 real `data-deal-change` frames**
  end-to-end (C1 accept / C2 reject / C3 accept / C4 escalate / Com:1 leave_open). **Cypress 2/2** light+dark,
  screenshots verified (`docs/fork/evidence/c5b3/`). NO migration/endpoint/dep; NO gate/guarantee change.

## Done earlier this session (C5b-2 — NEGOTIATION-REVIEW SKILL + BINDING + CRAFT EVAL — branch `fork/c5b2-negotiation-review-skill`; ADR-F041/F032 addendum; migration `0072`; NO endpoint/dep)

**What:** the **craft layer** on the round-2 negotiation loop — *prompt quality tuned by eval, not a runtime
gate* (ADR-F041), so it adds no gate and changes no guarantee. The negotiation companion to `surgical-redline`.
- **`skills/negotiation-review/SKILL.md` (NEW curated skill):** decide-every-item + the closed taxonomy +
  materiality + counter **surgically** (term-swap, cross-refs `surgical-redline`) + **counter-with-reply over
  reject-then-orphan** (the C5b-1 nuance) + escalate-don't-concede + untrusted-input framing (ADR-F028). Bound to
  Commercial. It *teaches*; the code (`evaluate_coverage`/`evaluate_anchoring`/`evaluate_gate` + reconciliation)
  *enforces*.
- **Migration `0072` (NEW, mirrors 0067):** `_bind_negotiation_review_skill` (idempotent `NOT EXISTS`) +
  `_refresh_negotiation_doctrine` (never-clobber `REPLACE` of the stale 0066 "accept, reject, or counter"
  paragraph — it predated the C5a tools — pointing at `extract_counterparty_position`/`respond_to_counterparty` +
  the skill + the full taxonomy). down_revision `0071`. No schema/route/openapi change.
- **`api/tests/agents/scenarios/test_commercial_negotiation_eval.py` (NEW, provider-marked):** fuses the C5a
  scenario with the C9 judge pattern — a plain task drives the **bound** skill; judge grades the response `.docx`
  for mutuality-restored / floor-held / comment-engaged. RIG assertions only (ADR-F015). Agent vs judge aliases
  decoupled (`LQ_AI_SCENARIO_MODEL` / `LQ_AI_JUDGE_MODEL`).
- **Tests + simplification:** two mirrored tests in `test_practice_areas.py` (binding+doctrine API assertion +
  migration idempotency/never-clobber); factored a generic `capture_output_file` into `commercial_redline_lib.py`
  (single-sources the storage fetch; `capture_redline` delegates; C5a scenario test refactored to use it).
- **Verify:** **full api suite 2684 passed / 31 skipped / 0 failed** (dev-image, throwaway test DBs); ruff
  (CI-exact, root config) + mypy clean. **Live (DeepSeek agent, deepseek-pro judge, 3 reps,
  `docs/fork/evidence/c5b2/`):** 3/3 substantive craft pass (§3 reverted to mutual surgically, §4 below-floor
  perpetuity held, §2 benign accepted, full coverage, `respond_calls` 7/7/4 = the gate adapting). **Honest
  finding: counter-with-reply 0/3** — the model reverts §3 (orphaning Com:1) rather than counter+reply; the
  guarantee holds (comment preserved, reply never silently lost), the *ideal* isn't yet driven on deepseek-flash
  → backlog tuning item (the skill carries the coaching; the model under-follows it). Claude (Opus 4.8) read the
  artifacts directly and **concurs** with the deepseek-pro verdicts (Claude not reachable on the local gateway —
  `ANTHROPIC_API_KEY` unset / no `claude` alias). Adversarial review: **SHIP**, 0 blockers/should-fixes/nits.

## Done earlier this session (C5b-1 — COMMENT-WIPE FIX — branch `fork/c5b1-comment-wipe-fix`; ADR-F032 addendum; NO migration/endpoint/dep)

**What:** make C5a's no-silent-action guarantee hold at the **document** level for comments. Raw-OOXML
inspection of the C5a live output found a real gap: when the agent `reply`-ed to a counterparty comment **and**
accepted/rejected the change it was anchored to, Adeu deletes the whole thread — silently wiping the reply while
reporting it `applied` (count-based reconciliation missed it). Three code layers (model judges, code disposes):
- **`negotiation_service.py` (A + C):** `read_state_of_play` now captures `StateOfPlay.comment_anchors`
  (`Com:N → Cn`, from a `[Com:N]` token sharing a change's `{>>…<<}` meta block); `apply_decisions` re-reads the
  output and **proves every reply survived** (raw `parent_id` match) — a wiped reply → `Reconciliation.ok=False`
  → persist nothing. Replaces the old corruption-only re-read that deliberately didn't count threads.
- **`schemas/commercial.py` (B):** model-free `evaluate_anchoring(comment_anchors, decisions)` + `AnchorReport`
  — rejects a `reply` on a comment anchored to an `accept`/`reject`-ed change (counter/leave_open are safe),
  collect-all-errors, refs-only message telling the model to counter or leave_open instead.
- **`commercial_tools.py` (E):** gate wired as step 3.5 in `_respond_to_counterparty` (after coverage, before
  the counter gate); `_render_state_of_play` annotates anchored comments + a coupling RULE so the model
  self-corrects up front.
- **Probed on the pin (Step 0, like F045):** `[Com:N]` co-occurs with `[Chg:N]` in the meta block (the anchor
  signal); `extract_comments_data` keys by RAW unprefixed ids (`"1"`); `add_comment(author,text,parent_id)` has
  **no text-range anchor** → no pure margin comment → the gate is the guarantee (not a re-homing trick); reject
  of an anchored change with a reply wipes the whole thread (applied=3/skipped=0 yet reply gone).
- **Verify:** 48 negotiation tests + `tests/agents` 502 green; **full api suite 2680 passed / 1 failed (the
  documented `test_ready` env-flake) / 2 skipped**; ruff + mypy clean. **Live (DeepSeek, `docs/fork/evidence/c5b1/`):**
  re-ran the round-2 NDA → the counterparty comment now **survives** the round (was deleted in C5a); the agent
  adapted across **4 `respond_to_counterparty` calls** when the gate refused reply+reject; swap reverted to
  mutual, perpetuity escalated (visible). Adversarial review: SHIP, 0 blockers, NITs folded.

## Done earlier this session (C5a — PROVABLE NEGOTIATION LOOP — branch `fork/c5a-negotiation-core`; ADR-F032; NO migration/endpoint/dep)

**What:** the commercial agent's **second round**. The counterparty returns a marked-up `.docx`; the agent
reads their tracked changes + comments and responds to **every** item, with a **code-enforced guarantee it
never silently accepts/rejects** (the maintainer's hard requirement). C5 was SPLIT: **C5a = the provable
backend core**; deferred → **C5b** (skill calibration + inline live chips + multi-round eval). Plan
`docs/fork/plans/C5a-provable-negotiation-loop.md`; ADR-F032.

- **Adeu 1.12.1 reads/writes the markup natively** (no OOXML code of ours; verified live then built on):
  `extract_text_from_stream(clean_view=False/True)` (CriticMarkup + `Chg:N` ids / accept-all) +
  `engine.comments_manager.extract_comments_data()` (`Com:N`); `engine.apply_review_actions([AcceptChange|
  RejectChange|ReplyComment])` + `apply_edits([ModifyText(comment=)])` for a counter. The maintainer's prior
  art `Claude-Plugin-MCP` (MIT) gave the *concepts* (closed taxonomy, layer-don't-reject, per-id state) but
  left completeness to the prompt — the **gate is the net-new piece**.
- **`api/app/agents/negotiation_service.py` (NEW)** — `read_state_of_play(docx)→StateOfPlay` (parses the
  CriticMarkup regions into synthetic refs `C1..Cn` in doc order + comments from `extract_comments_data`) and
  `apply_decisions(docx, state, decisions)→(bytes, Reconciliation)` (replies→rejects→accepts then counters;
  re-reads to prove each landed). SDK-only.
- **`api/app/schemas/commercial.py`** — `CounterpartyDecision` (closed taxonomy), `RespondToCounterpartyInput`,
  `evaluate_coverage` + `CoverageReport` (the **upfront coverage gate**: exactly one decision per ref).
- **`api/app/agents/commercial_tools.py`** — `extract_counterparty_position` + `respond_to_counterparty`
  closures (guarded, matter-scoped via `_matter_files_query`, 404-conflated); `respond` re-extracts ground
  truth → coverage gate → counter gate (D1–D6) → `apply_decisions` → reconcile → persist a `(response).docx`
  File (`created_by_run_id`) + a matter-memory `open_point` receipt fact; audit counts/IDs only. Both names in
  `COMMERCIAL_TOOL_NAMES` (auto-granted via the existing `build_commercial_tools`).
- **`api/app/agents/redline_service.py`** — extracted `word_diff_edits` to a module function (single-sourced
  for the counter path; the instance method delegates). Redline path unchanged (10/10 regression green).
- **Verify:** unit/integration (negotiation service + tools) green; ruff + mypy clean; redline regression
  10/10. **Live (DeepSeek, `docs/fork/evidence/c5a/`):** round-2 NDA, `status=completed`, both tools called,
  full coverage in one pass, **escalated** the below-floor perpetuity demand (left as a visible tracked
  change, not conceded). No new HTTP route (no `test_endpoints`/`test_openapi` change).

## Done earlier this session (C7a — REDLINE-DOWNLOAD surface — branch `fork/c7a-redline-download`; ADR-F046; migration `0071`)

**What:** the lawyer can now **download the redlined `.docx`** the commercial agent produces — both from a cockpit
**Documents tab** (every matter, all areas) and **inline** under the completed run that made it. Closes the stranded
work-product gap (the redline was persisted + audited but never surfaced). C7 was SPLIT (3 features > one-PR
discipline): **C7a = download only**; deferred = **C7b** drafter/reviewer fan-out roster, and the accept/reject/counter
**classification + deal-context live signal → C5**. Plan `docs/fork/plans/C7a-redline-download-surface.md`; ADR-F046.

- **Reused, not rebuilt:** `GET /api/v1/files/{file_id}/content` already streams bytes (owner-scoped 404). The
  download path is unchanged; C7a only adds a way to *find* the file + the UI. **No SSE/step protocol change** —
  `AgentRunStep` has only a text summary (no structured-artifact channel), so one matter-files endpoint feeds BOTH
  surfaces instead of threading a new frame (settled-rows-decide intact).
- **`File.created_by_run_id`** (mig `0071`, nullable FK → `agent_runs.id`, `ON DELETE SET NULL`, additive/no-backfill);
  `_apply_redline` stamps it (`run_id` already in scope at `build_commercial_tools`). Honest run→file provenance → the
  inline button filters to `created_by_run_id === run.id` (precise, not a filename heuristic).
- **`GET /matters/{project_id}/files`** — new `api/app/api/matter_files.py` on the `/matters` router, owner-scoped via
  `_load_visible_project` (404 cross-user/archived). Metadata only, newest-first, membership-union scope (mirrors
  `tools._matter_files_query`). Registered in `api/__init__.py`; meta-tests updated (`test_endpoints` IMPLEMENTED_ROUTES
  + `test_openapi` EXPECTED_PATHS, count 147→148).
- **Web:** `files.ts` `downloadFile` + pure `pickDownloadFilename`; `matterFiles.ts` `listMatterFiles`; `types.ts`
  `MatterFile`. `DocumentsPanel.svelte` (new, Svelte-5 runes; load/poll/reconcile mirror MemoryPanel; pure helpers in
  `<script module>`). `ConversationHost` — `'documents'` tab whenever a matter is set; conversation region stays MOUNTED
  behind `class:hidden` via `matterPanelOpen` (no-remount invariant); reset-on-leave. `ConversationPanel` (Svelte-4) —
  inline Download under each completed run, refetched when the completed-run set changes.
- **Verify:** migration upgrade+**downgrade** round-trip on a throwaway DB (live DB untouched); full api suite **2639
  passed / 2 skipped** (lone failure = the documented env-flake `test_ready`); targeted endpoint/commercial-tools/meta
  tests green; ruff + mypy clean. Web: `npm run check` 0 errors, vitest **938 passed** (+12), prettier/eslint clean on
  touched files. **Headed Cypress 2/2** (`c7a-documents.cy.ts`) + screenshot matrix → `docs/fork/evidence/c7a/`.
  **Live (Atlas, DeepSeek):** real redline run `b588d8f8…` completed → output `…(redlined).docx` carries
  `created_by_run_id` == the run id; uploads carry `null`; nonexistent matter → 404. Full chain proven through the
  rebuilt arq-worker.

## Previous slice (REDLINE WORD-DIFF — branch `fork/redline-worddiff-adeu`; ADR-F045; NO migration / deps)

**What:** the redline TOOL now produces surgical tracked changes itself, so the model only has to preserve unchanged
wording. Root cause of the C8/C9 swallow (read from Adeu's engine source): our adapter sent ONE wholesale
`ModifyText` per edit → Adeu's `_pre_resolve_heuristic_edit` trims only common prefix/suffix → **swallows unchanged
interiors**. Plan `docs/fork/plans/redline-worddiff-via-adeu.md`; ADR-F045; headline `docs/fork/evidence/c9/SUMMARY.md`.

- **`api/app/agents/redline_service.py` (the fix):** new `_word_diff_edits(engine, edits)` — for each
  `(target,new)`, diff `full` vs `full.replace(target,new)` via `adeu.diff.generate_edits_from_text` (sub-edits carry
  full-document `_match_start_index`), rationale on the first sub-edit; `dry_run`/`apply` now call
  **`engine.apply_edits(...)` directly, NOT `process_batch`** (the canonical `adeu.sanitize.core` pattern — bypasses
  `validate_edits`' per-sub-edit uniqueness check, which would reject a short region like "the Customer"; `apply_edits`
  trusts the positional index). **Wholesale fallback** when `full.count(target)!=1` (rare whitespace mismatch; D4
  already guarantees uniqueness in the doc text) — logged counts-only. Removed dead `_counts`.
- **`skills/surgical-redline/SKILL.md` → v2.0.0:** dropped the anchor-mechanics / decompose / "split the block" /
  "fold into the boundary" coaching; teaches "quote the clause, change only the necessary words, keep the rest
  verbatim — the tool diffs it." Skill-loader guard re-run green (no `": "` silent-drop).
- **`api/app/agents/commercial_tools.py`:** tool docstrings + preview self-review text realigned to the new approach.
- **`api/app/schemas/commercial.py`:** removed dead `changed_regions()`. **Gate D1–D5 UNCHANGED** — it keys on the
  minimal token diff (renderer-agnostic) and still guards genuine over-rewording; no threshold change (unverifiable
  at n=1, ADR-F045).
- **Empirically proven before coding** (read Adeu's `engine.py`/`diff.py`/`sanitize/core.py`; scratchpad
  `worddiff_design_probe2.py`): indemnity → 3 regions verb-phrase bare, multi-edit batches don't cross-contaminate,
  genuine rewrite still ONE block (renderer doesn't fake surgery), hyphen/underscore no corruption.
- **Verify:** `test_redline_service.py` 10/10 (5 new word-diff cases) · gate/loader/tools 52 · broad non-provider
  regression **513 passed** · ruff check+format clean · mypy clean on changed files. **Live (DeepSeek flash, C9
  harness, all 7 instruments + Claude-judge via `scratchpad/c9-judge.js`): surgical-pass 3/7 → 6/7, STRONG 6/7,
  redlined 7/7, boilerplate-bare 6/7 → 7/7; Aegis NDA mutualisation STRONG·surgical (refuter held); seam-defect
  duplication eliminated (deterministic scan).** The lone ADEQUATE (Meridian) is the model *choosing* to
  wholesale-rewrite a warranty disclaimer — a genuine rewrite the renderer correctly preserves, NOT a swallow.
  Evidence: `c9/flash`, `c9/verdicts/*.md`, `c9/SUMMARY.md` (v3) + `c9/v2-wholesale-render/` (archived v2).

### Earlier (C3c-2 — cockpit matter-memory panel SHIPPED; PR #137, branch `fork/c3c2-cockpit-memory-panel`)

**What:** the **frontend half** of the matter-memory tier (ADR-F042 §C3c) — a new **"Memory" tab** in the
cockpit's matter view rendering the C3c-1 composite + a human-authenticated wiki revert. **Pure frontend over
existing endpoints: no backend change, NO migration** (head stays `0070`), **zero new deps**. **Maintainer
chose** (AskUserQuestion): **Memory tab on ALL matters, any area** + **revert behind a confirm dialog**
(disabled while a run is active). No new ADR — F044 stays the governing decision (noted in the PR).

- **`web/src/lib/lq-ai/components/matter/MemoryPanel.svelte` (NEW)** — one scrollable view, four sections
  (Working summary / Facts / Pinned corrections / Activity log). `<script module>` exports the pure helpers
  (`logKindLabel`/`isRevertable`/`shortRunId`/`logTailNote`/`canRevert`) — the codebase has **no
  @testing-library/svelte**, so logic is tested at the helper layer (pattern: `MatterCard`/`AttachKBModal`).
  Mirrors `RopaRegister` for the `loadGeneration` out-of-order guard + the `runActive` `schedulePoll`/`stopPoll`
  poll + the `reloadKey` settle-reconcile. Revert = a `wiki_snapshot` log row → confirm `Dialog` → POST →
  refetch; **disabled while `runActive`** (don't race the agent). **Every** model-authored body
  (`content_md`/`body_md`/`body_preview`) renders through `renderModelMarkdown` (DOMPurify, media-forbid) —
  the only `{@html}`, never raw.
- **`web/src/lib/lq-ai/api/matterMemory.ts` (NEW)** — `readMatterMemory(id)` (GET) + `revertWiki(id, snap)`
  (POST `{snapshot_id}`) over `apiRequest` (base already `/api/v1`); barrel-exported as `matterMemoryApi`.
- **`web/src/lib/lq-ai/types.ts`** — hand-written interfaces mirroring the C3c-1 Pydantic models exactly
  (datetimes = ISO strings); **no frontend OpenAPI contract test exists** (verified) so nothing else to update.
- **`web/src/lib/lq-ai/cockpit/ConversationHost.svelte`** — widened `matterTab` to add `'memory'`; derived
  `matterTabs` (conversation always; `register` only narrow-Privacy; `memory` whenever a matter is set; **none
  for the unfiled bucket**). The conversation/register region stays **MOUNTED** under `class:hidden` so the
  live SSE stream + `runActive` never drop on a tab switch; `MemoryPanel` is a sibling `{#if}`. **No-remount
  invariant preserved** (verified by the reviewer).
- **Adversarial review (fresh-context, 8 lenses → per-finding refutation): SHIP — 0 blockers, 0 should-fixes,
  2 NITs, both folded:** (1) reset `matterTab`→`conversation` when the active tab leaves the strip (Privacy
  widen retires the register tab → nothing highlighted); (2) clear the revert dialog's target/error on close.
- **Verify:** `npm run check` 0 errors (5 pre-existing warnings); vitest **915 passed** (+11 new); eslint +
  prettier clean on all touched files. **Real-stack smoke** (rebuilt `api`): `GET /matters/{id}/memory` → 200
  with the exact composite shape. **Headed Cypress** (`c3c2-matter-memory.cy.ts`, rebuilt `web`): **2/2** —
  render-the-four-sections + revert round-trip (confirm dialog → POST `{snapshot_id}` → refetch) + the
  screenshot matrix → `docs/fork/evidence/c3c2/` (light/dark × wide/narrow, all visually verified clean; the
  Privacy capture shows Memory **beside** the ROPA register, proving the all-areas placement).

### Previous slice (C3c-1 — matter-memory READ backend; merged #136, ADR-F044, branch `fork/c3c1-matter-read-revert`)

The read/manage **backend** (this slice's dependency): two guarded agent read tools — `search_matter_memory`
(Python keyword match over the **LIVE** corpus, no SQL from the model, superseded facts never resurface) +
`matter_facts_as_of` (bi-temporal as-of; the date is reject-not-crash hardened via a `mode='before'`
`_require_iso_date_string` + `_utc_aware`) — granted to every matter-bound run, all areas, disjoint grant. A
composite `GET /matters/{id}/memory` (wiki + live facts + live corrections via the new uncapped
`live_corrections` + capped/counted log) and a human-authenticated `POST .../memory/wiki/revert {snapshot_id}`
(restore a chosen `wiki_snapshot`, snapshot-current-first → reversible, append-only; triple-scoped lookup →
404; **no agent revert tool**). **No migration; no model calls.** Full detail: memory `c3c1-matter-read-revert-shipped`.

### Previous slice (C3b-2 — gateway-routed consolidation/Lint SHIPPED; merged #135; branch `fork/c3b2-gateway-consolidation`)

(C3a — PR #133; C3b-1 — PR #134 [[matter-facts-c3b1-shipped]]: the typed bi-temporal fact ledger, ZERO model
calls. C3b-2 builds the automated hygiene on top.)

**What:** the matter agent can now **consolidate its own memory** in one tool call — the **first matter-memory
code that calls a model**, so the **ADR-F010 egress obligation lands here**. `consolidate_matter_memory` loads
the matter's live fact set whole + the wiki + the pinned corrections, routes **ONE** gateway chat completion
(mem0 extract→judge + Lint) under a new `lq_ai_purpose`, then applies the proposal **supersede-only** (retire /
replace — never delete, never edit a body in place) and **rewrites the wiki**. **Maintainer chose** (AskUserQuestion):
**facts + wiki**, **supersede-only**, **match the R4-no-op cost posture + gateway audit**. **No migration** (reuses
`0070` + `context_md`); **zero new deps**. Plan `docs/fork/plans/C3b-2-gateway-consolidation.md`; **ADR-F043** (proposed).

- **`app/agents/matter_consolidation.py` (NEW)** — `MATTER_CONSOLIDATION_TOOL_NAMES` (disjoint),
  `build_matter_consolidation_tools(session_factory, *, run_id, binding, gateway_factory=get_gateway_client)`
  (the **gateway DI seam** tests override), the zero-arg guarded `consolidate_matter_memory()`, and
  `_consolidate_matter_memory` = load → ONE `gateway.chat_completion` (`max_tokens` cap, `anonymize=False`,
  `lq_ai_purpose="consolidate_matter_memory"`) → lenient JSON parse → **pure validation pass** (every op id a
  LIVE `kind='fact'` row of THIS matter; no double-ref; temporal coherence for retire AND replace) → **all-or-nothing
  supersede-only apply** + `snapshot_and_rewrite_wiki`. A gateway error / truncation / malformed output / bad id
  → **reject-and-retry string, never a crash, zero writes**.
- **`schemas/matter_memory.py`** — `RetireConsolidationOp`/`ReplaceConsolidationOp` (discriminated on `op`) +
  `ConsolidationResult` (`extra='forbid'`, `new_wiki` ≤ wiki budget); extracted shared `_utc_aware` /
  `_absent_if_blank` helpers (C3b-1's `RecordMatterFactInput` now reuses them — single-sources the tz fix).
- **`app/agents/matter_memory_tools.py`** — extracted `snapshot_and_rewrite_wiki(...)` from `_update_matter_memory`
  (single-sources the snapshot+overwrite for C3a + C3b-2).
- **`app/agents/composition.py`** — grants `build_matter_consolidation_tools(...)` to **every** matter-bound run
  (all areas), beside the memory + fact grants; disjoint.
- **Gateway** — `consolidate_matter_memory` added to `_KNOWN_PURPOSES` (`gateway/app/api/inference.py`) +
  documented (`openai_schema.py`) + the propagation test (`test_inference_b4.py`). **⚠ frozenset at module load
  → the gateway must be RESTARTED to recognise the purpose** (unknown purposes fall back to `chat`, so the call
  still succeeds — only the routing-log tag differs until restart).
- **B2 carries over (structural):** corrections are read-only prompt input; the apply only touches live
  `kind='fact'` rows (a correction/cross-matter/superseded/invented id is unreachable) — no-fabrication +
  no-overwrite hold without prose. The tool's only model access is the injected `GatewayClient` (asserted by a
  unit test + an AST-parse egress guard — no provider SDK).
- **Adversarial review (workflow, 5 lenses → per-finding refutation): 0 blockers, 1 should-fix + 6 nits; 2 refuted.**
  Folded: **should-fix** = a `retire` of a *future-dated* fact set `invalid_at=now < valid_at` → DB CHECK crash
  (now rejected in validation, + regression test); nits = bound the echoed parse-error text, detect
  `finish_reason='length'` truncation → diagnosable reject, single-source the resolved `valid_at`
  (validation→apply), drop the dead `model_alias` builder kwarg, distinct `MAX_SUPERSEDES` constant. **Deferred**
  (documented): the DB connection held across the gateway await (consistent with every guarded tool; no lock).
- **Verify:** ruff (CI-exact 0.15.18) + format + mypy `app` clean; gateway mypy `--strict` + ruff clean;
  gateway suite **595 passed** (purpose test 3/3; lone `test_model_discovery` failure is pre-existing env-sensitive,
  reproduces in isolation, CI-green on main); **full api suite 2585 passed / 2 skipped** (lone failure = the
  documented env-sensitive `test_ready`).
- **Live (DeepSeek, `docs/fork/evidence/c3b2/live-matter-consolidation.json`):** seeded a duplicate party fact +
  a stale draft cap; the agent called `consolidate_matter_memory` → **`deepseek-pro` retired the duplicate**
  (`superseded_count=1`, `live_fact_count` 3→2, `total_fact_rows` stays 3 — **supersede-only, history preserved**)
  + rewrote the wiki; `status=completed`, no crash. **Craft finding (ADR-F015):** flash returned an all-NOOP (didn't
  dedupe); pro's first attempt set a `valid_from` ≤ the prior's `valid_at` → the temporal check **correctly
  rejected it** (no crash, agent surfaced "consolidation failed") — proving the validation works; a **prompt fix**
  (dedupe = RETIRE the redundant copy; `valid_from` only for a genuine LATER value change) then made pro
  consolidate cleanly. The supersede/wiki mechanics are deterministically covered by 19 unit tests.

### Previous slice (cockpit chat-UX render polish — merged #132, on main): dark-mode markdown parity
(`dark:prose-invert` on the agent-surface prose containers — the GFM-parser theory was a red herring) +
quieter tool calls. `vitest` 904/904. Redline download deferred to C7.

## Previous slice (C9 — Claude-judged manual redline tests; merged #131; no migration; no new ADR)

**What:** upgraded C8's craft signal from DeepSeek-judging-itself to **Claude (Opus 4.8) judging DeepSeek**
over a corpus spanning contract types **and** complexity, with the produced `.docx` surfaced for the
maintainer. Reuses C4/C8 (`apply_redline`/`preview_redline`, `seed_doc_matter`/`capture_redline`,
reconstruction). Plan `docs/fork/plans/C9-claude-judged-redline-tests.md`.

- **7 corpus instruments** (single-source `.docx`==normalized text): *moderate* — `securescan_msa`,
  `databridge_license`, NEW `aegis_mutual_nda`, `northwind_dpa`, `meridian_services_sow`; *complex*
  (dense multi-limb, added mid-slice on the maintainer's "the real test is long clauses where most language
  must be LEFT ALONE") — NEW `helios_master_agreement`, `orion_dev_licence`.
- **`tests/agents/scenarios/test_commercial_redline_manual.py`** (NEW, provider-marked) — purposive
  per-instrument prompts (names the one-sided heads, leaves surgical technique to the bound skill); runs the
  chosen model with the skill registry active; writes `c9/<id>/` (`original-*.docx`, `* (redlined).docx`,
  `reconstruction.txt`, `accepted-clean.txt`) + a merge-safe `manifest.json`; `LQ_AI_C9_ONLY` runs a subset;
  `LQ_AI_SCENARIO_MODEL` selects `deepseek` (flash) vs `deepseek-pro`. `complexity` field added to
  `RedlineScenarioDoc`.
- **Substrate bugfix `api/app/agents/skill_backend.py`** — `RegistrySkillBackend.grep`/`glob` now return a
  graceful unsupported `GrepResult`/`GlobResult` instead of inheriting the protocol's `raise
  NotImplementedError`. deepagents' `agrep`/`aglob` do NOT catch that, so **any run where the model called the
  builtin grep/glob hard-failed** (observed live: the NDA crashed mid-redline). Fixes every area agent
  (Privacy too). Test in `tests/agents/test_skill_backend.py`.
- **Judge deliverables (Claude):** `docs/fork/evidence/c9/SUMMARY.md` + `verdicts/<id>.md` + `flash/` & `pro/`
  `.docx`. **Finding:** flash surgical-craft **5/7** by the strong judge (vs C8's self-judged 2/6); the
  **complex** docs scored *among the best on both models* — complexity is NOT the craft predictor. The one
  consistent weakness is **pervasive mutualisation** (one-directional-throughout clauses → whole-clause
  rewrite). Pro re-run of the flash failures: fixed the SOW *robustness* (flash produced no redline) but did
  **worse** on the NDA (looped to `cap_exceeded`) — so the stronger tier does NOT reliably fix craft; the
  lever is **method** (a mutualisation worked-example in `surgical-redline` + a redline step-budget tier).
- **Live cockpit UAT (maintainer, end of C9):** drove the agent in the real UI on a "Project Atlas" deal
  suite (`/home/sarturko/atlas-deal-suite/`: an `.eml` with a **nested** term-sheet PDF, the Cirrus MSA
  `.docx`, a processor DPA PDF; org profile seeded as Northwind). The agent read all four (incl. the nested
  attachment), used **company memory**, produced a correct gap analysis + a successful tracked-changes
  redline. **Real fix committed:** the **arq-worker had no S3/MinIO env** (api/ingest did) → storage-backed
  agent tools failed in the worker; added the S3 block to `docker-compose.yml`. Dev-only/local (NOT
  committed): `LQ_AI_DOCLING_ENABLED=false` (Docling hung PDFs to its 300s timeout) and the seeded org
  profile. Full findings: memory `commercial-agent-live-uat-findings`.

## ▶ PICK UP — REDLINE WORD-DIFF SHIPPED (ADR-F045); next = maintainer's call (C7 / C5 / C6)

**C3-UM (the human "update memory" UX) is DONE** on branch `fork/c3-update-memory-ux` (squash-merged; the whole
matter-memory track is now complete). What shipped — three human gestures on `MemoryPanel.svelte`, all
overlay/append-only per ADR-F042, disabled while a run is active:
1. **Pin a correction** — `+ Pin a correction` composer (textarea + char cap) → `POST .../memory/corrections`
   (the existing C3a human-authenticated pin, `trust='human-pinned'`). Pin VISUAL = F013 brand-left-accent.
2. **Correct a fact** — a quiet `Correct` on each Fact row pre-fills the composer with a `Re: "…" →` stub
   (free-text, **no DB link** — maintainer chose free-text over an anchor column → NO migration). Still a
   plain correction (B2 no-overwrite).
3. **Retire** — quiet `Retire` on a correction (soft `superseded_at`) AND on a fact (close `invalid_at`),
   shared confirm dialog. **Maintainer chose corrections + facts.** NO free-edit of the working summary (it's
   agent-regenerated; levers stay pin + revert).

**Backend (NO migration, head stays `0070`):** two new endpoints in `api/app/api/matter_memory.py` —
`POST .../memory/corrections/{entry_id}/retire` (idempotent soft-retire) + `POST .../memory/facts/{entry_id}/retire`
(close window; **future-dated fact `valid_at >= now` → 409 Conflict**, never the `invalid_at > valid_at` CHECK 500;
the C3b-2 trap). Both owner-scoped 404 + kind-scoped, audit IDs-only, tz-aware `datetime.now(UTC)`. Frontend:
`api/matterMemory.ts` (`pinCorrection`/`retireCorrection`/`retireFact`) + `types.ts` + the `MemoryPanel.svelte`
gestures (`canWrite` aliases `canRevert`; one shared retire dialog). **Traps hit:** new endpoints must be
registered in BOTH `tests/test_endpoints.py` `IMPLEMENTED_ROUTES` AND `tests/test_openapi.py` `EXPECTED_PATHS`
(+ bump the hardcoded `len(actual) == N` path count) or the meta-tests fail; new path params need a value in
`test_endpoints.py` `_PARAM_VALUES` (`entry_id`).
**Verify:** api 2627 passed (lone failure = the documented env-flake `test_ready` — expects 503 but the dev-image
runs on the live network so deps are reachable → 200; CI-green in a clean env). web 926 vitest + `npm run check`
0 err + Cypress 2/2 + live Atlas smoke (pin→retire-correction→retire-fact, idempotent, cross-kind 404). Evidence
`docs/fork/evidence/c3-um/`. No new ADR (F042/F044 govern).

**Disk-cleanup folded into the same PR** (Crostini hit 100% full, 2026-06-24): root cause = btrfs storage-driver
subvolume leak (690+ orphaned layers from frequent ~6 GB rebuilds). Reclaimed ~100 GB (3.9 GB → 82 GB free; rebuild
brought it to ~74 GB). Prevention = CLAUDE.md rebuild-time rule (`docker image prune -f` after every build,
dangling-only) + `scripts/docker-prune.sh` (dangling + stopped containers + leftover `lq_ai_test_*`), no cron.
**Recovery playbook if it recurs:** `docker system prune -af` (keeps running-stack images + volumes); if orphaned
btrfs subvolumes persist, `apt-get install btrfs-progs`, stop docker, delete `/var/lib/docker/btrfs/subvolumes/*`
(safe when `docker images` is empty), then `rm -rf /var/lib/docker/{image,buildkit,btrfs,containers}` (KEEP
`volumes`+`network`), restart docker, `compose up -d --build`. The btrfs cleaner reclaims on the first commit
(starting docker triggers it). See [[redline-viewing-direction]] memory for the new redline-viewer roadmap input.

**Test vehicle on the dev stack:** the **Atlas** Commercial matter (`905720d1-5d17-43cd-a8f0-3a76d095de34`, owner
admin) seeded with a wiki + 2 wiki snapshots + 5 live facts + 1 superseded fact + 1 human-pinned correction.
Deep-link `/lq-ai?area=commercial&matter=905720d1-5d17-43cd-a8f0-3a76d095de34` → **Memory** tab.

**▶▶ PICK UP HERE — C5b-1 COMMENT-WIPE FIX SHIPPED; next slice = maintainer's call.** C5a's negotiation loop is
now document-level-honest for comments (a reply can no longer be silently wiped — anchor map + `evaluate_anchoring`
gate + reply-survival reconciliation, ADR-F032 addendum; live-re-verified at the OOXML level). C5 split into
C5a (core) + C5b-1 (this fix) + C5b-2/C5b-3 (below). **Remaining open commercial slices (maintainer picks):**
- **C5b-2** — the negotiation craft layer: a `negotiation-review` SKILL.md (materiality / authority zones /
  worked examples — incl. *prefer counter-with-reply over reject-then-leave-open when there's a comment to
  engage*, so the comment stays anchored + visibly answered; this is the C5b-1 craft follow-up) + skill-binding
  migration `0072` (mirror `0067`, down_revision `0071`); a multi-round Claude-judged eval (like C9).
- **C5b-3** — the **inline live verdict chips**: clone the `data-ropa-change` ledger→drain→transient-frame seam
  to a `data-deal-change` frame rendered as a transient chip **in the conversation** (NOT a register-row wash —
  there is no deal-terms panel; chip keyed by ref/verdict). Full clone recipe mapped (ropa_changes.py →
  deal_changes.py, composition COMMERCIAL_AREA_KEY branch, runner drain on tool_result, stream.deal_changed,
  run-stream.ts parseDealChangePayload, ConversationPanel dispatch).
- **C7b** — drafter/reviewer **fan-out roster** + post-fan-out reconciliation. The fan-out *infrastructure*
  already works (subagent steps nest via `parent_step_id`, mirrored to SSE + parsed by the web, tested in
  `test_agent_composition.py`); **blocker #6 (`work_product_attributions`) is a legacy-chat concern, NOT on the
  agent path** — so C7b is "define drafter/reviewer subagents (mig reconciling `0057`) + a reconciliation pass."
- **C6** — controlling playbook skills (blocked by ADRs **F036 + F038** — canonical severity scale + the
  controlling-skill plane — which must be decided first). C5a deliberately uses **prose** house positions, not
  the `PlaybookPosition` mechanism, to stay unblocked.
**C5a backlog (Adeu gaps, recorded):** no public pure-margin-comment (comment with no edit) — C5a anchors a
comment to a change/counter, and accept/reject carry their reason in the receipt not a Word comment;
per-revision dates not surfaced. **Carried cross-cutting:** in-app redline *viewer/accept*
([[redline-viewing-direction]], MCP-gated / AGPL caveat); marker-fence hardening (C3a nit); embedding/FTS
search UI (gateway `/v1/embeddings` 501 until B6); log pagination.

## Gotchas / durable traps (C8 + C4 + carried)

- **C5a — Adeu `Chg:N`/`Com:N` ids are internal and RENUMBER after accept/reject; a *modify* is a del+ins
  PAIR.** So (1) the model must reference the ids from the **extract** step (C5a hands it synthetic `C1..Cn`
  refs that decouple it from Adeu's numbering — `negotiation_service` re-derives the map on respond from the
  same unchanged doc); (2) accept/reject of one logical change acts on **both** Adeu ids; (3) reconciliation
  must NOT re-diff ids across the apply — trust Adeu's `(applied, skipped)` + `skipped_details`. **Accepting a
  change deletes the comment thread anchored to it** (correct — the acceptance resolves their comment), so
  apply **replies before accepts** and do NOT post-count threads (it false-fails). `apply_review_actions`
  takes ONLY `AcceptChange`/`RejectChange`/`ReplyComment` — no public resolve / no pure-margin comment.
- **C5a — the coverage gate must re-extract the StateOfPlay as GROUND TRUTH, not trust the model's view.**
  `respond_to_counterparty` re-reads the doc and runs `evaluate_coverage(state.change_refs,
  state.open_comment_refs, decisions)` — exactly one decision per ref. A silent omission → reject; the
  reconciliation then proves each decision landed (skipped/under-applied counter → reject, persist nothing).
  This is the no-silent-action guarantee; keep it prompt-independent.
- **C5b-1 — accepting OR rejecting a change DELETES the comment thread anchored to it (incl. a reply we made),
  and Adeu reports it `applied` — so a reply could silently vanish.** Three things close it and must stay
  together: (1) `read_state_of_play` builds `StateOfPlay.comment_anchors` (`Com:N → Cn`) from a `[Com:N]` token
  sharing a change's `{>>…<<}` meta block; (2) `schemas.commercial.evaluate_anchoring` rejects a `reply` on an
  `accept`/`reject`-ed anchored change BEFORE any write (counter/leave_open are safe — a counter layers a new
  edit and keeps the original change + thread); (3) `apply_decisions` re-reads the output and proves each reply
  survived. **`extract_comments_data` keys comments by RAW unprefixed ids** (`"1"`, not `"Com:1"`) for both the
  id and `parent_id` — the survival match normalizes `Com:N → N` (`split(":")[-1]`). **There is NO public
  margin-comment API** (`add_comment` has no text-range anchor), so the gate is the guarantee, not a re-homing
  trick. Rejecting a commented change *orphans* the counterparty comment (text preserved, anchor gone — may not
  render in Word) — not a silent loss, but the *ideal* is to **counter** (keeps it anchored) + reply; that
  coaching is C5b-2. **Always re-verify redline/comment output at the OOXML level (`word/comments*.xml`), not the
  reconstruction text — the reconstruction masked this bug.**
- **C7a — `api`, `arq-worker`, `ingest-worker` are SEPARATE per-service images** (`lq-ai-api` /
  `lq-ai-arq-worker` / `lq-ai-ingest-worker`), all built from `./api`. `docker compose build api` rebuilds ONLY
  `lq-ai-api` — the workers keep their old image. After a code/migration change you must
  `docker compose build api arq-worker ingest-worker` (then `up -d --force-recreate` them) or the **agent loop
  runs stale worker code** (the agent run executes in arq-worker — confirmed by the C9 UAT S3-env finding). Verify
  with `docker inspect --format '{{.Image}}' lq-ai-<svc>-1` after a rebuild. The CLAUDE.md "rebuild all three
  together" rule means three SEPARATE builds, not one.
- **C7a — Postgres `now()` is CONSTANT within a transaction.** Two rows inserted in the same test transaction
  share `created_at`, so a "newest-first" ordering assertion falls back to the id tiebreaker and flaps. Set an
  explicit `created_at` per row in ordering tests (in production each file is its own transaction, so it's fine).
- **C7a — a new FK column means a unit test that INSERTS the row must satisfy it.** `_apply_redline`'s
  `created_by_run_id` FK → `agent_runs.id` forced the happy-path test to seed a real thread+run; the
  reject/scope tests never persist a File so a bare `uuid` passes. And **Svelte merges `<script module>` +
  `<script>` into one module** — importing a type in both blocks is a "Duplicate identifier" (import once).
- **C3c-2 — the `web` container serves a PRE-BUILT bundle; rebuild it before any UI/Cypress verification**
  (`docker compose up -d --build web`) or you test stale code (a CLAUDE.md hard rule — bit the cockpit
  screenshot workflow). Headed Cypress needs `DISPLAY=:0` (`X0`/`X1` sockets present on this box).
- **C3c-2 — no `@testing-library/svelte` in `web/`.** Test Svelte component LOGIC by exporting pure functions
  from `<script module>` and unit-testing those (pattern: `MatterCard`/`AttachKBModal`); cover DOM + interaction
  via Cypress. Don't add the library (CLAUDE.md: justify every dep).
- **C3c-2 — cockpit Cypress nav:** deep-link `/lq-ai?area=<key>&matter=<id>` and wait for
  `[data-testid="lq-cockpit-conversation"]`. At narrow/stacked width a fresh deep-link (no `&thread=`) shows the
  thread LIST, not the panel where the matter tab strip lives — click `lq-cockpit-new-conversation` to enter the
  panel first, THEN the `lq-cockpit-matter-tab-{id}` tabs (incl. `…-memory`) are reachable.
- **C3c-2 — adding a cockpit tab must NOT remount the conversation pane.** Keep the conversation/register region
  MOUNTED behind `class:hidden={matterTab === '…'}` and render the new view as a SIBLING `{#if}`; moving
  `{@render conversationPane()}` to a new DOM position remounts `ConversationPanel` → drops the live SSE stream
  and resets the bound `runActive`. Also reset `matterTab` to a tab that's always present when the active tab can
  leave the derived strip (e.g. a Privacy matter widening past the split budget retires the `register` tab).
- **C3c-2 — any `{@html}` of model output needs `renderModelMarkdown` + an `eslint-disable-next-line
  svelte/no-at-html-tags` comment** (the shared sanitizer is DOMPurify media-forbid; raw `{@html}` fails lint
  and is an XSS sink). Every matter-memory body (`content_md`/`body_md`/`body_preview`) is untrusted model text.

- **F045 — the redline renderer uses Adeu's NATIVE word-diff applied via `engine.apply_edits`, NOT
  `process_batch`.** `redline_service._word_diff_edits` diffs `full` vs `full.replace(target,new)` with
  `adeu.diff.generate_edits_from_text` (sub-edits carry full-document `_match_start_index`), then
  `engine.apply_edits(subs)` applies them positionally. **Do NOT switch back to `process_batch`** — it runs
  `validate_edits`, which re-checks each sub-edit's `target_text` for uniqueness and REJECTS a short region
  ("the Customer" recurs) with `BatchValidationError: Ambiguous match`. `apply_edits` trusts the index and
  skips that check (the canonical `adeu.sanitize.core` pattern). The fragment-relative trap: diff the FULL doc
  text, never the bare clause, or `_match_start_index` is relative to the fragment and misplaces. Fallback to a
  wholesale `ModifyText` only when `full.count(target)!=1`. Proof scripts: `scratchpad/worddiff_design_probe2.py`.
- **F045 — a genuine rewrite (every word changed) correctly renders as ONE block; the renderer does not fake
  surgery.** So the surgical signal still depends on the model preserving unchanged wording (the skill teaches
  it) and the gate (D1–D5, minimal-diff) still guards genuine over-rewording. A carve-out APPEND now renders as
  a clean insertion via the word-diff (no more zero-width-insertion crash to dodge) — the skill no longer needs
  the "fold into the boundary" mechanic, though `_EDITOR_ERROR_MSG` remains as a defensive catch.
- **C8 — the surgical-craft eval is provider-marked** (`test_commercial_redline_eval.py`): run live with
  `LQ_AI_SCENARIO_MODEL=deepseek LQ_AI_REDLINE_EVAL_REPS=N UX_B1_EVIDENCE_DIR=<repo>/docs/fork/evidence/c8`.
  It regenerates ALL eval files in one run — if a (doc,rep) yields no redline, no per-rep file is written, so
  reconcile the dir against `eval-report.json` before committing (delete stale files from a prior run).
- **C9 — builtin `grep`/`glob` crash a run if the backend doesn't implement them.** deepagents exposes
  `grep`/`glob` filesystem tools; `BackendProtocol`'s default `grep`/`glob` `raise NotImplementedError`, and
  the async wrappers (`agrep`/`aglob`) do NOT catch it → the exception leaves the tools node and fails the
  whole run. Any custom backend MUST override `grep`/`glob` to return a `GrepResult`/`GlobResult` (even just
  an `error=`), never inherit the raise. Fixed for `RegistrySkillBackend` (C9); watch for it in any future
  backend. **C9 manual harness** (`test_commercial_redline_manual.py`, provider-marked) writes per-MODEL dirs
  (`c9/flash`, `c9/pro`) with a merge-safe `manifest.json`; `LQ_AI_C9_ONLY` runs a subset. The one open craft
  weakness it found is **pervasive mutualisation** (see pickup) — flash rip-and-replaces, pro can `cap_exceeded`.

- **C8/C9 re-run — a bound skill's BODY reaches the model ONLY on-demand (ADR-F016 progressive disclosure).**
  deepagents' SkillsMiddleware auto-injects only the skill **index** (name + `description:`) into the system
  prompt; the full SKILL.md body is fetched by the model calling the builtin **`read_file`** on
  `/skills/<name>/SKILL.md`. So "skill loaded + bound" (the premise gate) ≠ "the worked examples are in context"
  — the model must choose to read them. So (1) make the `description:` itself carry the core directive (always
  present); (2) to confirm the body was consulted, look for `read_file` in the manifest `tools_called` (distinct
  from `read_document`, the matter-doc reader) and/or the redline reproducing the skill's worked examples.
- **C8/C9 re-run — redline craft at n=1 is NOISE; the `surgical` boolean is judge-borderline.** C9 is one run per
  (instrument, model); the surgical-pass *count* swings on borderline "is a bare-grant-clause wholesale rewrite
  surgical?" calls — even the *same* Claude panel split on it across two runs. Read deterministic signals
  (manifest `redlined`/`boilerplate_bare`) + direct text inspection as primary; treat verdict counts as
  qualitative. A real craft-rate change needs **multi-rep × strong-judge** → **don't ship a craft tweak you can't
  measure**. To compare two runs fairly, re-judge BOTH with the *identical* panel (removes judge drift).
- **C8/C9 re-run — a judge agent given a path to a MISSING `reconstruction.txt` (a no-redline run) will hunt and
  read a DIFFERENT run's file → a verdict for the wrong artifact.** Bit the v1 Meridian + pro DataBridge/Northwind
  cells. **Gate trust on file-existence**: a verdict is valid only if its `reconstruction.txt` exists on disk;
  otherwise use the manifest ground-truth (no-redline).

- **Adeu is installed `--no-deps`** (4 places: api/Dockerfile, api/Dockerfile.dev, ci.yml, + any dev-image test
  command). Its `fastmcp[apps]` dep bumps starlette 0.48/pydantic 2.13/mcp → breaks `APIRouter`. The SDK
  (`RedlineEngine`/`ModifyText`/`process_batch`) needs only `diff-match-patch` + `structlog` (+ lxml/python-docx
  /rapidfuzz/pydantic already in-tree). **Dev-image test commands MUST `pip install diff-match-patch structlog`
  + `pip install --no-deps adeu==1.12.1`** or `from adeu import …` fails `ModuleNotFoundError: structlog`.
- **`apply_redline` redlines the named doc FRESH each call (no stacking)** — the agent must pass ALL edits in
  ONE batched call (the tool docstring says so). Multiple calls each re-redline the ORIGINAL → only the last
  call's edits survive in its output File. For long docs needing >50 edits/call → chain on the prior output or
  fan out (C7). A redline run is step-intensive; ADR-F026 budget is 100 steps/900s (fine for one batched
  single-doc redline; **50-page docs need C7 fan-out + a redline budget tier** — recorded as a finding).
- **`max_steps` is API-capped at `le=100`** (`schemas/agent_runs.py`); the harness sets it directly on the
  AgentRun row (bypasses the schema), so live scenarios can exceed 100 if needed — but production is 100.
- **Killed-container test-DB contamination:** killing a `docker compose run` suite container mid-run leaves the
  reused test DB dirty (leftover admin/session rows) → spurious CLI/audit/last-admin failures on the next run.
  Re-run the suspect files in a FRESH container to confirm. The `test_ready_reports_per_dependency_status`
  health test is separately env-sensitive (passes isolated; "fails" on the live network).
- **Provider tests need the gateway key UNSET to skip:** `docker compose run api` inherits `LQ_AI_GATEWAY_KEY`
  from the api service env, so the full suite would RUN the provider tests (slow/hangs on real gateway calls).
  Run the regression suite with `-e LQ_AI_GATEWAY_KEY= -m 'not provider and not e2e'`.
- **Live redline scenario:** `tests/agents/scenarios/test_commercial_redline_scenario.py` (provider-marked) seeds
  the real `securescan_msa.build_msa_docx()` into MinIO + runs DeepSeek + writes `.docx`/reconstruction/
  accept-clean/judge to `UX_B1_EVIDENCE_DIR`. The judge's input was truncated at first (false WEAK); caps are
  now generous (must fit the full redline). Run via the dev image on `lq-ai_default` with the api gateway env +
  `UX_B1_EVIDENCE_DIR` mounted; `chown` the root-owned evidence before `git add`.
- **Migration head is `0070`** (`0070_matter_memory_typed_facts.py`, C3b-1 — additive-nullable typed-fact
  columns on `matter_memory_entries`; `0068` is the store, `0069` the skill binding; **C3b-2 added NO
  migration** — it reuses `0070` + `context_md`). Re-check the head before writing in case anything lands first. Fresh-head check before any migration; rebuild api+arq-worker+
  ingest-worker after one; never host-side `alembic upgrade` on the dev DB; never `compose down -v`.
  (**C3c-1 added NO migration** — pure read + revert over existing rows/columns; head stays `0070`.)
- **C3b-1 — a Pydantic `datetime` field accepts a tz-NAIVE value from a bare ISO date** ("2026-01-01" parses
  with `tzinfo=None`). Comparing it against a tz-aware `DateTime(timezone=True)` column raises `TypeError`,
  which escapes a guarded tool as a CRASH (audited error + re-raised), not a reject-and-retry. Any datetime the
  model supplies must be normalised to UTC-aware at the schema boundary (now the shared `_utc_aware` helper in
  `schemas/matter_memory.py`, used by `RecordMatterFactInput` + the C3b-2 `ReplaceConsolidationOp`). Tests using
  only `+00:00` offsets mask it — add a bare-date case.
- **C3c-1 — a Pydantic `datetime` field reads a BARE NUMERIC string as a Unix timestamp, not a year.** `"2026"`
  becomes `1970-01-01`, `"1700000000"` becomes 2023 — silently, no reject. On a load-bearing arg (the
  `matter_facts_as_of` date) that is a confidently-wrong recall, not a crash, so `_utc_aware` (a `mode='after'`
  validator) can't catch it. Reject an all-digit string at the boundary with a `mode='before'` validator (the
  shared `_require_iso_date_string` in `schemas/matter_memory.py`, on `as_of` + both `valid_from`s). A `"2026-05"`/
  `"last Tuesday"` is already rejected by Pydantic; only the all-numeric case slips through. Add a `"2026"` test.
- **C3c-1 — `load_pinned_corrections` is the per-run prompt-INJECT slice (newest 30, capped), NOT the search/read
  corpus.** It exists to bound prompt size; reusing it for a read surface silently hides older live corrections.
  The read surface (search + the GET) uses the UNCAPPED `live_corrections(db, project_id)` (oldest-first rows) in
  `matter_fact_tools.py`. Keep the two distinct: capped-bodies-newest-first for injection, uncapped-rows-oldest
  for read.
- **C3b-2 — closing a bi-temporal window must respect the `invalid_at > valid_at` CHECK or the flush CRASHES.**
  Setting `invalid_at` to a time **at or before** a fact's `valid_at` (e.g. retiring a *future-dated* fact at
  `now`) violates `chk_matter_memory_entries_valid_window` → `IntegrityError` on flush → escapes the guarded
  tool as a crash, not a reject. The consolidation validation pass guards BOTH op kinds (`retire`: `now > valid_at`;
  `replace`: `new_valid_at > prior.valid_at`) BEFORE any write. Any future window-closing code must do the same
  pre-flush check. `record_matter_fact`'s supersede already enforces this for its one path; a *retire* (no
  replacement) was the new gap.
- **C3b-2 — a new `lq_ai_purpose` only takes effect after a GATEWAY RESTART** (`_KNOWN_PURPOSES` is a
  module-load frozenset in `gateway/app/api/inference.py`). An unknown purpose falls back to `chat` (the call
  still succeeds), so a live agent run works against an un-rebuilt gateway — only the routing-log tag is wrong
  until the gateway is rebuilt. Rebuild `gateway` when adding a purpose. **Egress-guard test pattern:** assert a
  module's only model access is the injected `GatewayClient` by AST-parsing its imports (forbid
  openai/anthropic/httpx/requests roots) — grepping the source text is fooled by a docstring that *names*
  `api.openai.com` (`test_module_has_no_direct_provider_egress`).
- **🔴 SKILL.md frontmatter must not contain an unquoted `": "` (colon-space) in any value (`description:` is
  the usual culprit).** The loader does `yaml.safe_load`; an unquoted plain scalar with `": "` parses as a
  mapping → `frontmatter YAML is invalid: mapping values are not allowed here` → the loader logs a WARNING and
  **silently skips the skill** (it vanishes from the registry; bound skills are filtered to known names, so the
  binding is silently dropped). This bit C8's `surgical-redline` (never loaded until C3a fixed it) and C3a's
  `matter-memory`. Use " — " / "," / "(…)", or quote the value. Guarded now by
  `test_every_real_skill_loads_no_silent_drops` (`tests/test_skill_loader.py`) — run it after adding/editing any SKILL.md.
- **The per-area grant seam** is `composition.py` (`area_key == PRIVACY_AREA_KEY` / now `== COMMERCIAL_AREA_KEY`).
  `COMMERCIAL_AREA_KEY = "commercial"` lives in `commercial_tools.py` (mirrors `PRIVACY_AREA_KEY` in ropa_tools).
- **Dev-image suite/lint recipe:** `docker compose run --rm --no-deps --entrypoint bash -v "$PWD/api:/app"
  -v "$PWD/skills:/skills" -v "$PWD/ruff.toml:/ruff.toml" -e LQ_AI_SKILLS_DIR=/skills api -c "pip install -q
  pytest pytest-asyncio respx mypy types-PyYAML 'ruff>=0.6' diff-match-patch structlog && pip install --no-deps
  adeu==1.12.1 && <cmds>"`; `chown -R $(id -u):$(id -g) app tests` after. CI ruff = `ruff>=0.6`; format with it
  before pushing (version drift). `mypy app` via unpinned mypy false-flags `ropa_export.py`/`tabular.py` — ignore.
- Dev login `admin@lq.ai` (password in local `.env`, not committed); api :8000, web :3000, gateway :8001.
  Privacy area id `71bb11f9-e5e6-403d-ae91-e4401a644927`. Adeu SDK-only — never `adeu.server`/`adeu.mcp_components`.

## Merge policy (ADR-F005, agent-merged)

Squash-merge when the FULL gate passes: CI green + containerized suites (counts quoted) + fresh-context
adversarial+security+simplification review + live verification (DeepSeek) when behaviour changes + HANDOFF
updated. `gh` always `--repo sarturko-maker/lq-ai-fork --head <branch>`. Branch off `main` first.
