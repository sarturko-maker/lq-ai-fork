# Session Handoff — 2026-05-09 → next session

> **Purpose.** Resume in a fresh context window. Pair with `docs/M1-PROGRESS.md` (the canonical living ledger).

---

## State at handoff

- **Branch:** `main`, **5 commits ahead of origin/main** (D3-core not yet pushed; see "Push status" below).
- **Last commit:** `45b94f3` *docs: mark D3 core complete (D3)*.
- **Wave-1 (D5 + D6):** ✅ pushed to origin (`c00c5cb..b57cf4f`, 12 commits). Verified.
- **Wave-2 D3-core:** ✅ committed locally (`b57cf4f..45b94f3`, 5 commits). Not pushed.
- **Stack:** `docker compose up -d` — all services healthy as of close. Postgres recovered after the ollama-volume incident (see "Ollama volume incident" below).
- **Auth:** `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!` (rotate when convenient).
- **Migrations applied:** `0001` → `0009`.
- **ADRs in tree:** unchanged from prior handoff.

---

## What landed in this session

| Phase | Status | Commits |
|---|---|---|
| **D5** Wave-1: MFA enrollment + verification | ✅ pushed | `9716519..6dca723` + merge `9738240` |
| **D6** Wave-1: GDPR Article 17 + 20 | ✅ pushed | `3980c5b..b754449` + merge `b57cf4f` |
| **D3** Wave-2 core: audit-log helper + chat keystone + admin read endpoint | ✅ local | `5aba280..45b94f3` |

**Wave-2 D3-core:**
- `5aba280` audit-log helper module + migrate D6 callsites
- `40f798f` chat-message audit row with privilege + routed tier
- `961c80d` /admin/audit-log read endpoint with filtering + pagination
- `10489cc` D3 audit-log critical path coverage (10 tests)
- `45b94f3` docs: mark D3 core complete

**D3 verification step passes:** create privileged project → send chat → query `/admin/audit-log?privilege_marked=true` → row appears with `routed_inference_tier` populated.

---

## What's NOT done

### Wave-2 remaining

- **D3-coverage** (the rest of D3, filed as separate scope per the user's "wide D3" decision but split off into a follow-on session for context-budget reasons). See "D3-coverage scope" below.
- **D2** (Inference Tier Awareness UI) — web/ work; tier badge in chat header showing routed tier (1–5), click for details panel. **Dependencies:** D1 ✅ + C8 ✅. **Effort:** 4–6h.
- **D4** (Organization Profile singleton) — `/api/v1/organization-profile` GET/PUT, partial unique index, prepend to skill prompts unless `use_organization_profile: false`. **Dependencies:** C2 ✅. **Effort:** 4–6h.
- **D7** (Saved Prompts per Issue 04) — `/api/v1/saved-prompts` CRUD + sidebar UI + Promote-to-Skill affordance. **Dependencies:** C8 ✅. **Effort:** 4–6h.

### B6 remainder + Phase E

Unchanged from the prior handoff: OpenAI / Vertex / Bedrock chat completions adapters; Phase E compliance pack mappings + release packaging.

### Push status

The 5 D3-core commits are local on `main` only. Decide before next session whether to push them as-is (pre-D3-coverage) or hold until D3-coverage lands too. Argument for push-now: D3-core is verification-passing on its own; another contributor or CI can pick it up. Argument for hold: D3 looks "complete" in `git log` while broader audit coverage is still missing, which could mislead a contributor into thinking the audit surface is wired across the codebase.

**Recommended:** push now with D3-core marked clearly in M1-PROGRESS as "core complete; coverage continuing." That's the honest state and aligns with the project's transparency principle.

---

## D3-coverage scope (next session)

The D3-core verification path passes, but the full PRD §5.3 commitment ("Every state-changing API call writes to an `audit_log` table") is partial. D3-coverage extends the audit-write surface using the existing `app.audit.audit_action` helper.

### Endpoints needing audit instrumentation

All use the same pattern: `await audit_action(db, user_id=..., action="...", resource_type="...", resource_id=str(resource.id), project=project_or_none, request=request, details={...})` followed by a `db.commit()` (or call inside the existing commit boundary).

**Auth events** (`api/app/api/auth.py`):
- `user.login` (on 200 from `/auth/login`) — no project context, but useful for "who logged in when from where" audit.
- `user.logout` (on 204 from `/auth/logout`).
- `user.password_changed` (on 204 from `/auth/change-password`).
- `user.session_refreshed` (on 200 from `/auth/refresh`) — possibly skip; high cardinality, low audit value.

**MFA events** (`api/app/api/auth.py`):
- `user.mfa_setup` (on 200 from `/auth/mfa/setup`).
- `user.mfa_enabled` (on 204 from `/auth/mfa/enable`).
- `user.mfa_disabled` (on 204 from `/auth/mfa/disable`) — D5 explicitly deferred this to D3.
- `user.mfa_recovery_code_used` (on 200 from `/auth/mfa/verify` when the success path used a recovery code, not a TOTP code).

**Project CRUD** (`api/app/api/projects.py`):
- `project.create`, `project.update`, `project.archive` (DELETE = soft-archive).
- `project.skill_attached`, `project.skill_detached`.
- `project.file_attached`, `project.file_detached`.
- For all of these, the `project` argument to `audit_action` resolves privilege automatically.

**File CRUD** (`api/app/api/files.py`):
- `file.uploaded`, `file.deleted` (soft-delete via DELETE).
- For files inside a project, pass `project_id=file.project_id` so privilege resolves.

**Knowledge base CRUD** (`api/app/api/knowledge_bases.py`):
- `knowledge_base.create`, `knowledge_base.update`, `knowledge_base.archive`.
- `knowledge_base.file_attached`, `knowledge_base.file_detached`.
- `knowledge_base.queried` — possibly; high cardinality, but useful for "who asked what about a privileged matter" audit.

**Hard-delete worker** (`api/app/workers/user_deletion.py`):
- D6 known-limitation: the worker doesn't audit-log the actual hard delete. Add a `user.hard_deleted` row with `user_id=NULL` (the user is gone) and `details={user_id_was: ..., email_hash: ...}`. The pre-deletion `details` capture lets operators correlate the cancel/scheduled events with the eventual delete.

### Retroactive backfill

Today's audit_log table is essentially empty (all rows are from D3-core's chat tests + D6 endpoint tests). A backfill pass for the existing data is approximately a no-op against current state, but the pattern should be documented for production deployments where the audit table has accumulated rows from the M1-pre-D3 codebase.

Recommended: add a `python -m app.cli backfill-audit-privilege` command that walks existing `audit_log` rows whose `privilege_marked` is null/false and re-resolves privilege from `details.chat_id` (or `details.project_id`). Skip if `details` doesn't carry the resolution key.

### Admin filtering UI

`web/src/routes/lq-ai/admin/audit-log/+page.svelte` — Svelte page that calls `GET /api/v1/admin/audit-log` with the existing query parameters. Layout suggestion:

- Filters bar: `privilege_marked` toggle, `routed_inference_tier` dropdown (1-5 + "all"), `action` text input, date range pickers.
- Results table: columns for timestamp, action, user (resolved from `user_id`), resource (`<resource_type>:<resource_id>`), privilege badge, tier.
- Detail drawer: clicking a row shows the full `details` JSON payload + IP / user-agent / request-id.
- Pagination: "Load more" button passes `next_cursor`.

Match the LQ.AI shell conventions (the D0.5 admin alias UI at `web/src/routes/lq-ai/admin/models/+page.svelte` is the closest analog).

### Tests

Each instrumented endpoint should add a single integration test that confirms the audit row is written with the right action + privilege fields. The existing `test_audit_log.py` covers the helper + endpoint; subsystem tests should focus on "this endpoint emits its expected audit row" rather than re-testing the helper.

---

## How to resume next session

1. `cd /Users/kevinkeller/Desktop/LegalQuants/inhouse-ai`
2. `git pull origin main` and verify HEAD matches local (or push the D3-core commits first if you want them on origin).
3. `docker compose ps` — all services healthy.
4. Read `docs/M1-PROGRESS.md` (D3 section is at the bottom of the wave-2 stack) and this handoff.
5. **Pick the next move:**
   - If finishing D3-coverage feels right: walk the auth → projects → files → KBs → MFA → hard-delete-worker subsystems, one atomic commit per subsystem, using `audit_action` everywhere. ~6–10 commits, ~6–10h.
   - If you want a different task next: D2 (web/, ~4-6h), D4 (api/, ~4-6h), D7 (api/ + web/, ~4-6h). All independent of D3-coverage; pick whichever has the most user-facing value.

---

## Ollama volume incident (one-time, resolved)

Mid-session, `lq-ai-postgres-1` OOM-killed because the Docker VM disk filled up. Root cause: another CC instance (working in a different project, "SmarterClaw") was pulling models against `localhost:11434`, which our `--profile local` `lq-ai-ollama-1` container had captured (the LQ.AI compose's `ollama` service uses the `lq-ai_ollamadata` volume). That volume hit 126 GB, exhausting Docker Desktop's VM disk and crashing postgres.

**Resolution:** stopped + removed `lq-ai-ollama-1`, `docker volume rm lq-ai_ollamadata`. Local Volumes dropped 201 GB → 2 GB. Postgres came back healthy.

**For next session:**
- The LQ.AI `ollama` service stays in the compose under `profiles: ["local"]`; only runs with `docker compose --profile local up -d`. Don't accidentally bring it up when host Ollama is the intended path.
- The user prefers host Ollama. Operator-side: set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env` for the gateway.
- A `feedback_ollama.md` memory entry was added: never run `ollama rm` / `ollama prune` without per-model authorization. Read-only commands (`ollama list`, `ollama show`, `ollama pull`) are fine.

---

## Things that should NOT regress

- `OLLAMA_BASE_URL` should point at host Ollama unless `--profile local` is intentionally active.
- Anthropic key in `.env` is real — DO NOT overwrite it when generating a fresh `.env`.
- `POSTGRES_HOST_PORT=5433` (the host postgres collision was tidepool, currently down).
- `LQ_AI_CORS_ORIGINS=http://localhost:3000` (local dev only; production: leave unset).
- `PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1` (local dev; production: relative `/api/v1`).
- Gateway-config writable named volume `gateway-config` mounted at `/etc/lq-ai`.
- 4 pre-existing `B017 pytest.raises(Exception)` ruff warnings in `test_migrations.py` — pre-date M1; leave alone.
- Pre-existing test failures on main HEAD (predate D3-core):
  - `tests/test_endpoints.py::test_endpoint_returns_canonical_501_body[GET /api/v1/admin/tier-policy]`
  - `tests/test_endpoints.py::test_endpoint_returns_canonical_501_body[PATCH /api/v1/admin/tier-policy]`
  - These are the D1 deferred admin endpoints; clear when D1 follow-on lands or when the test file is updated to acknowledge them as not-yet-implemented.
- Note: the prior handoff mentioned 17 pre-existing failures. Most of those (chats_skills_forwarding, pipeline_ingest, skill_loader, migrations) are environmental / fixture drift and may be flaky. Don't add to that pile; do leave them be unless a contributor takes them on as cleanup.
