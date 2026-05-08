# M1 Build Progress

> **Living status for the M1 build.** Updated at every session boundary or significant milestone. Pair this with `docs/M1-IMPLEMENTATION-ORDER.md` (which has the per-task spec, scope, and verification criteria) — this doc tracks what's *done* against that plan and what's *deferred* with explicit owning tasks.
>
> **Last updated:** 2026-05-08 (session 6 close; C2 + C5 + C7 all landed in parallel worktrees and merged)
> **Repo:** [github.com/LegalQuants/lq-ai](https://github.com/LegalQuants/lq-ai) (origin/main is in sync)
> **Local working dir:** `/Users/kevinkeller/Desktop/LegalQuants/inhouse-ai` (project renamed from InHouse AI to LQ.AI on 2026-05-07; local directory not yet renamed)

---

## Snapshot

| Phase | Done | In progress | Next |
|---|---|---|---|
| A — Foundation scaffolding | A1, A2, A3, A4 | A5 (partial — env-var branding only) | — |
| B — Core authentication and routing | B1, B2, B3, B4, B5 | — | B6 optional; otherwise C-phase |
| C — Capability layer | C1, C2, C4, C5, C7 | — | C3 (chats), C6 (KB), C8 (web UI) |
| D — M1 differentiators | — | — | After C |
| E — Procurement and release | — | — | After D |

**Tests:** ~390+ passing in api/ (C2 added 16: 8 internal-skills endpoint integration + 8 chat-skill-forwarding integration; C5 added 49+: 19 chunker unit + 13 parser unit + 5 worker-queue unit + 6 ingest-orchestration integration + 6 migration; C7 added 76: 27 schema/slug unit + 42 endpoint integration + 6 migration + 1 errors-hierarchy parametrize entry; C4 added 43; C1 added 37; on top of B5's 170-line baseline); ~170 passing in gateway/ (C2 added 52: 24 backend-client unit + 28 assembler unit + 10 inference-with-skills integration; 1 skipped pending ANTHROPIC_API_KEY); 5 cross-subsystem conformance tests under `tests/` extended with `skill_not_found` / `skill_fetch_failed` / `skill_input_missing` (`conflict` and pipeline-internal codes are backend-only and don't extend the contract).
**Stack:** `docker compose up` brings 7 services (postgres, redis, minio, gateway, api, ingest-worker, web) to healthy in ~30s. (C5 added the `ingest-worker` service.)
**Migration:** `make migrate` applies `0001_initial.py` → `0002_add_must_change_password.py` → `0003_create_files_table.py` → `0004_create_projects.py` (C7) → `0005_create_documents_and_chunks.py` (C5) cleanly; all reversible. Migration 0005 enables the pgvector extension.

---

## Completed tasks

### A1 — Repository scaffold ✅

Foundation in place: api/ + gateway/ FastAPI services with /health (200) + /ready (503), Makefile, ruff.toml, docker-compose.yml with 6 services, .env.example with full env-var inventory, OpenWebUI v0.9.2 imported into web/. Smoke test passes end-to-end.

### A2 — Database migration scaffolding ✅

Phase A1 schema landed via Alembic. Tables: users, user_sessions, audit_log, inference_routing_log. CITEXT email, gen_random_uuid() (UUIDv4 — see deferred items), partial indexes, CHECK constraints, set_updated_at() trigger. Test fixture uses session-scoped Alembic + per-test SAVEPOINT rollback (canonical SQLAlchemy pattern). 8 migration tests pass when DATABASE_URL is set.

### A3 — Inference Gateway minimal scaffold ✅

gateway/ now loads gateway.yaml on startup (Pydantic schema validation, ${VAR:-default} env expansion). OpenAI-compatible surface: /v1/chat/completions stub (501 → real in B3), /v1/embeddings (501), /v1/models (returns configured aliases). Admin surface per PRD §4.5: /admin/v1/tier-config (returns loaded policy), /admin/v1/providers/health, /admin/v1/usage, /admin/v1/anonymization-config (501 stubs). 27 tests.

### A4 — Backend minimal scaffold ✅

api/ now connects to Postgres + Redis + MinIO + gateway on lifespan startup. /ready reports per-dependency status. All 30 paths from backend-openapi.yaml are registered as 501-returning stubs (with a structured error body naming the next task that lands real implementation). OpenAPI 3.1 spec at /openapi.json. 47 endpoint stub tests + 3 OpenAPI conformance tests.

### A5 — Web shell scaffold (PARTIAL) ⏳

What's done: OpenWebUI v0.9.2 fork imported, builds in Docker, `WEBUI_NAME=LQ.AI` and `WEBUI_AUTH=false` set in .env.example. Container healthy.

What's deferred (per the entry in M1-IMPLEMENTATION-ORDER.md):
- **Delegated auth wiring** (Svelte component changes) → folds into B1 verification + future UI task
- **Visual branding** (logo, color scheme, footer per ADR 0001 dual-branding constraint) → folds into D2

### B1 — User model + auth endpoints (backend) ✅

Bcrypt password hashing + JWT access tokens (15min) + opaque refresh tokens (7d, bcrypt-hashed at rest). Endpoints: POST /auth/login (401 wrong creds, 423 if MFA enabled with mfa_token), POST /auth/refresh (rotates refresh token), POST /auth/logout (revokes all active sessions), GET /users/me (returns current user). 20 integration tests covering full round-trip + edge cases (timing-equalization on unknown-email branch, CITEXT case insensitivity, expired/revoked session handling).

End-to-end verification: 401 confirmed against the running stack with no matching user.

### B2 — First-run admin user setup ✅

Migration `0002_add_must_change_password.py` adds `users.must_change_password BOOLEAN NOT NULL DEFAULT FALSE` (reversible). On API startup, `app.admin_bootstrap.ensure_first_run_admin` creates an admin (`admin@lq.ai` by default; configurable via `LQ_AI_FIRST_RUN_ADMIN_EMAIL`) with `must_change_password=True` and a 24-character CSPRNG password. The lifespan handler in `main.py` logs the password at WARNING level once on the actual creation event ("First-run admin password (record it now and rotate on first login): …"), matching the grep pattern in `docs/quickstart.md`. Race-safe via `INSERT ... ON CONFLICT DO NOTHING`.

`POST /api/v1/auth/change-password` (B1 token-protected) verifies the current password, enforces a 12-char minimum and a "must differ from current" rule, hashes the new password, clears `must_change_password`, and revokes every active session for the user. The login response and `/users/me` payload now expose `must_change_password` so the client can route. The forced-change gate is a `get_active_user` dependency wired at the router level: every authenticated router except `/auth/*` and `/users/me` returns HTTP 403 with `{ "detail": { "code": "password_change_required", ... } }` until the user clears the flag.

The CLI **landed in this task** (originally listed as deferred-or-later): `python -m app.cli reset-admin-password [--email EMAIL]` rotates the password, sets `must_change_password=True`, prints the new password to stdout, and revokes any active sessions. Exit codes: 0 success, 2 user-error (no admin, missing email, multiple admins).

22 new tests: 16 `test_admin_bootstrap.py` (3 unit on `generate_password`, 13 integration covering bootstrap idempotency + change-password happy/error paths + the gate + the end-to-end flow); 5 `test_cli.py` (CLI happy path + each error branch + session revocation); the `test_endpoints.py` 501-stub fixture was upgraded to authenticate every request (the auth gate now applies to those routers).

End-to-end verification on the running stack:
1. Fresh `docker compose down -v && up -d && make migrate` → API logs `WARNING:app.main:First-run admin password (record it now and rotate on first login): <pw>`.
2. `POST /auth/login` with the printed password → 200 with `user.must_change_password: true`.
3. `GET /api/v1/projects` → 403 `password_change_required`.
4. `POST /auth/change-password` (current=printed, new=permanent) → 204.
5. Login with old password → 401; login with new password → `user.must_change_password: false`.
6. `GET /api/v1/projects` → 501 (stub passes through gate).
7. `docker compose exec api python -m app.cli reset-admin-password` → prints new password and re-arms the gate; subsequent login surfaces `must_change_password: true` again.

Drift flagged: OpenAPI sketch updated with `/auth/change-password` path, `ChangePasswordRequest` schema, and `must_change_password` added to the `User` schema (now in `required`). `docs/db-schema.md` updated with the new column. `docs/quickstart.md:325` updated from the `lq_ai.cli` placeholder to `python -m app.cli reset-admin-password` (the canonical invocation in this codebase; the package is named `app`, not `lq_ai`).

### B3 — Anthropic provider adapter (gateway) ✅

ProviderAdapter abstract base + Pydantic OpenAI schema (with LQ.AI extensions: routed_inference_tier, routed_provider, cost_estimate, anonymization_applied). AnthropicAdapter translates OpenAI Chat Completions ↔ Anthropic Messages format (system-message extraction, stop-reason mapping, token-usage translation, streaming SSE chunk translation). Hand-rolled httpx — no `anthropic` SDK dep per PRD §4. Wired into inference.py with B3-temporary "Anthropic-only" routing (B4 replaces with the real router).

22 unit tests + 7 integration tests (respx-mocked) + 1 @provider real-key test (skipped without ANTHROPIC_API_KEY).

End-to-end verification: 503 `provider_unavailable` confirmed when no key is set; real-key verification deferred to operator.

### B5 — Backend ↔ Gateway integration ✅

End-to-end inference path: backend chat endpoint → `GatewayClient.chat_completion()` → gateway `/v1/chat/completions` → AnthropicAdapter → response back through both layers, with the gateway's `routed_inference_tier` surfaced through to the API caller and a structured error envelope on every failure mode. Bundled with the `lq_ai.errors` exception hierarchy that was deferred to this task.

**1. `lq_ai.errors` exception hierarchy (with ADR).** [`docs/adr/0003-error-handling.md`](adr/0003-error-handling.md) records the architectural choice: rather than a shared Python module that both `api/` and `gateway/` import from (would violate CLAUDE.md's hard rule on subsystem isolation), each subsystem owns its own typed `LQAIError` hierarchy under `app/errors.py`. The cross-subsystem contract is the **error-code enum** in the OpenAPI sketches plus a conformance test under `tests/test_error_code_contract.py` that asserts both sides stay in sync.

* `api/app/errors.py` — `LQAIError` base + 12 subclasses (Unauthorized, Forbidden, NotFound, ValidationError, RateLimited, InternalError, PasswordChangeRequired, GatewayUnreachable, GatewayTimeout, GatewayInvalidResponse, ProviderUnavailable, TierBelowMinimum, InvalidModel). Renders `{"detail": {"code", "message", "details"}}` to match FastAPI's native `HTTPException` shape and the existing B2 forced-password-change pattern. New `Error` schema added to `docs/api/backend-openapi.yaml` (was missing — gap noted in ADR 0003).
* `gateway/app/errors.py` — `LQAIError` base + 9 subclasses keyed to the existing `GatewayError.code` enum. Renders `{"error": {"code", "message", "details"}}` per `docs/api/gateway-openapi.yaml`. The pre-existing `ProviderAdapterError` hierarchy is unchanged; it continues to drive adapter-internal errors and is mapped at the route boundary.
* FastAPI exception handlers in both subsystems' `main.py` translate `LQAIError` instances to the canonical envelope.
* `api/app/api/dependencies.py`'s forced-password-change gate now raises `PasswordChangeRequired` instead of a hand-rolled `HTTPException` detail dict (existing test still passes — wire shape preserved). CONTRIBUTING.md's "Exceptions" bullet now points at the real `app.errors` modules and ADR 0003.

**2. Real `GatewayClient` chat-completion (and embeddings stub).** A4 had `health_check()` only; B5 builds out:

* `chat_completion(request, request_id=None) -> ChatCompletionResponse` — non-streaming POST. Surfaces the gateway's tier annotation (with header backfill if the body somehow lacks it).
* `chat_completion_stream(request, request_id=None) -> AsyncIterator[ChatCompletionChunk]` — parses OpenAI-format SSE frames (`data: <json>` blocks terminated by `data: [DONE]`). Mid-stream error frames map to the right `LQAIError` subclass and raise.
* `embeddings(model, input_, request_id=None)` — thin client over the gateway's still-501 `/v1/embeddings`. Lands a stable signature for the future KB / RAG layer.
* Error translation per ADR 0003: timeout → `GatewayTimeout` (504); network/DNS/TLS → `GatewayUnreachable` (503); gateway 5xx (no structured body) → `GatewayUnreachable`; gateway 401 (bad gateway-key header) → `GatewayUnreachable` plus a WARNING log naming the misconfiguration (the user must not see "wrong gateway key"); gateway 4xx with a `GatewayError` envelope → mapped via `app.errors.map_gateway_error_code`; malformed body → `GatewayInvalidResponse` (502).
* `api/app/schemas/gateway.py` mirrors the gateway's OpenAI-compatible request/response shapes. Per CLAUDE.md, the api/ side cannot import from `gateway/`; the two subsystems each own their definitions, kept in sync against `docs/api/gateway-openapi.yaml`.
* Single `httpx.AsyncClient` pooled across calls (per CLAUDE.md "reuse the same client").
* `respx>=0.21` added to `api/`'s dev deps (already used the same way in `gateway/` — same library, no new SBOM family).

**3. Backend chat endpoint (stateless pass-through).** `POST /api/v1/chats/{chat_id}/messages` — A4 had this as a 501 stub; B5 wires it through to the gateway:

* Auth gate (`ActiveUser`): bearer token + cleared `must_change_password`.
* Request body validates as `MessageCreate`; `chat_id` validates as a UUID.
* Translates to a single-turn `ChatCompletionRequest` (the `content` becomes one `user` message). C3 will pull prior messages from the DB to build full conversation context; until then the gateway sees a single-turn request.
* Calls `GatewayClient.chat_completion()` (non-streaming) or `chat_completion_stream()` (streaming). Streaming emits the OpenAPI sketch's `MessageStreamEvent` shapes: `delta` events while chunks arrive, a `complete` event on clean end, or an `Error` envelope frame if the stream ends in failure.
* Surfaces `routed_inference_tier` and `routed_provider` in the response body and in the `X-LQ-AI-Routed-Inference-Tier` / `X-LQ-AI-Routed-Provider` headers.
* Forwards `X-Request-Id` to the gateway so audit rows correlate.
* Persistence: **none yet** — the `chats` and `messages` tables don't exist (C3 adds them). The response body carries `stateless_passthrough: true` so clients can detect the transitional state.
* Routing-log writes: **the gateway is the canonical writer (B4)**; the backend does **not** double-write. There's an integration test that asserts the row count doesn't change during a backend chat call.
* `docs/api/backend-openapi.yaml`: documents the dual response shape (JSON or SSE), the structured 4xx/5xx responses, and the tier-related response headers. Adds `MessagePostResponse` schema for the non-streaming JSON body. Adds the `stream` field to `MessageCreate` (was missing). Adds the `Error` variant to `MessageStreamEvent`'s `oneOf` so SSE error frames are part of the contract.

**4. Tests (75 net-new across the build, plus 5 cross-subsystem):**

* `api/tests/test_errors.py` — 23 unit tests pinning the envelope shape, the per-subclass HTTP status, the FastAPI handler round-trip, and the gateway-code → backend-class map.
* `api/tests/test_gateway_client.py` — 27 unit tests against a respx-mocked gateway covering the full matrix (success path, auth/network/timeout/4xx/5xx error translation, schema-violation detection, streaming happy path / mid-stream errors / pre-frame errors / malformed chunks, embeddings 501, header forwarding).
* `api/tests/test_chats_send_message.py` — 20 integration tests (DB-backed) exercising the chat endpoint end-to-end: auth and gate, validation, happy path, full error matrix, streaming variants, no-double-write regression, and the still-501 stubs.
* `api/tests/test_endpoints.py` — adds `POST /api/v1/chats/{chat_id}/messages` to `IMPLEMENTED_ROUTES` so the 501 scaffold-test no longer asserts on it.
* `gateway/tests/test_errors.py` — 14 unit tests for the gateway-side hierarchy.
* `tests/test_error_code_contract.py` (cross-subsystem, brand-new dir) — 5 conformance tests that import both subsystems' `app.errors` modules and verify the codes/shapes stay in sync. Lives under the cross-cutting `tests/` directory per CLAUDE.md (the only place imports from both subsystems are allowed). Has its own `pyproject.toml` registering pytest markers.

**5. End-to-end verification on the running stack:**

1. ✅ `docker compose down -v && up -d && make migrate` — all 6 services healthy in ~30s; migrations apply cleanly.
2. ✅ Get the first-run admin password from the API logs; `POST /auth/login` → 200 with `must_change_password: true`; `POST /auth/change-password` → 204; relogin with the new password → 200 with `must_change_password: false`.
3. ⏭️ Real-key Anthropic verification deferred to operator (no `ANTHROPIC_API_KEY` available in this session). Covered by the respx-mocked stack-level integration tests.
4. ⏭️ Bad gateway-key verification flagged: **the gateway does not enforce X-LQ-AI-Gateway-Key auth yet**. The OpenAPI sketch documents it and the backend client always sends it, but no gateway-side middleware checks it. Not in B5 scope. Surfaced as a deferred-items entry below; the backend's translation logic for the gateway-401 case is unit-tested via respx and is in place when the middleware lands.
5. ✅ No `ANTHROPIC_API_KEY` set on the gateway → backend returns HTTP 502 with `{"detail": {"code": "provider_unavailable", "message": "Anthropic provider 'anthropic-prod' is configured but no adapter was instantiated; check that the credential environment variable referenced by 'api_key_env' is set", "details": {"provider": "anthropic-prod", "gateway_code": "provider_unavailable"}}}`. Confirms the gateway's structured `provider_unavailable` envelope propagates through the backend with the right code, the right HTTP status, and the operator-facing detail preserved.

### B4 — Gateway router + alias resolution + tier derivation ✅

Real router in `gateway/app/router.py` replaces B3's "Anthropic-only" temp logic. Pulls together:

- **Alias resolution** — single- and multi-level chains; the resolved-target list (primary + fallbacks) is built once per request.
- **Tier derivation** — `inference_tiers.overrides["<provider>/<model>"]` → `inference_tiers.overrides["<provider>"]` → `inference_tiers.defaults["<provider_type>"]` → provider entry's own `tier:`. New `inference_tiers:` block in `gateway.yaml.example` (optional; provider's `tier:` is the fallback so the prior config still works).
- **Cycle detection at config load** — alias chains are walked from each starting alias and rejected at startup with a clear chain-listing error. `MAX_ALIAS_DEPTH = 8`.
- **Adapter dispatch via registry** — `app.state.adapters` keyed by provider name. New adapters in B6 register themselves; the router doesn't care.
- **Fallback chain skeleton** — fallback-eligible errors (network, 5xx, 429) walk the alias's `fallback:` list. Auth errors and 4xx-non-429 surface immediately. Unit-tested with mocked adapters; real activation when B6 lands more providers.
- **`inference_routing_log` writer** — `app/routing_log.py` with three implementations: `SQLRoutingLogWriter` (the real one, async via SQLAlchemy + asyncpg), `NullRoutingLogWriter` (no-op when `DATABASE_URL` is unset; gateway must not refuse traffic over an unreachable audit log), `RecordingRoutingLogWriter` (in-memory, used by tests). Writers never raise out of `write()`.
- **Tier surface (decision)** — surfaced **both** in the response body's `routed_inference_tier` field (B3 already documented this on the schema) **and** in the `X-LQ-AI-Routed-Inference-Tier` header. Streaming preserves the body field on every chunk envelope. Documented in `docs/api/gateway-openapi.yaml` and `docs/PRD.md` §4.4.1.
- **Cost estimate** — populated from `cost_tracking.rates["<provider>/<model>"]` when configured; left NULL otherwise (per CLAUDE.md: don't invent prices).

Gateway now opens a DATABASE_URL connection on startup (separate engine from `api/`'s, sized for short-row insert workload). `docker-compose.yml` updated to pass DATABASE_URL to the gateway service.

46 new tests across unit + integration (alias resolution, tier derivation matrix, cycle rejection, fallback eligibility, router fake-adapter dispatch, routing-log row construction + bind params, response-surface header+body, streaming tier, unresolved-model audit row, real-DB write smoke).

End-to-end verification: real-DB row write confirmed (`docker exec` + `gateway/.venv/bin/python` against `lq-ai-postgres-1`). Real-key Anthropic verification deferred to operator (no ANTHROPIC_API_KEY available in this session).

### C1 — Skill Service: filesystem loading ✅

Backend-side filesystem walk + frontmatter parse + in-memory registry + SIGHUP-driven atomic-swap reload + the two queryable endpoints.

**ADR 0004 — loader locus.** Task C1's spec says "On *gateway* startup, load all skills…" but the queryable endpoints (`GET /api/v1/skills`, `GET /api/v1/skills/{name}`) live on the backend per `docs/api/backend-openapi.yaml`. The locus question — does the loader live in `api/`, `gateway/`, or both — was resolved in [ADR 0004](adr/0004-skill-loader-locus.md): the backend owns the registry. Rationale: the OpenAPI sketch puts the user-facing surface on the backend; the gateway↔backend HTTP boundary is the project's existing way of crossing subsystem lines (per CLAUDE.md and ADR 0003); future user/team-scope skill storage lives behind the backend's database. C2 (prompt assembly, gateway-side) will fetch skill content from `api/` over HTTP at the same boundary every other interaction crosses today.

**What landed:**

* `api/app/skills/{schema,registry,loader}.py` — Pydantic models for the `lq_ai:` frontmatter namespace (permissive — most fields optional, unknown fields kept; the M1 corpus predates the formal authoring guide and uses values like `output_format: markdown` and `jurisdiction: agnostic` that the guide doesn't document); immutable `SkillRegistry` snapshot with atomic-swap holder; filesystem walker with per-skill failure isolation (one bad apple does not break startup — operator sees all WARNING lines at once for a single-pass cleanup).
* `api/app/main.py` lifespan — builds the initial registry from `LQ_AI_SKILLS_DIR` (default: `../skills` relative to the API container's WORKDIR) and installs a SIGHUP handler that re-walks and atomically swaps the registry. In-flight requests holding the old snapshot continue observing it; new requests pick up the new state.
* `api/app/api/skills.py` — replaces the A4 501 stubs with real handlers. `GET /api/v1/skills` returns summaries (with `?tag=`, `?scope=` filters); `GET /api/v1/skills/{name}` returns the full Skill including `content_md`, `content_yaml`, and lazily-loaded `reference_files` / `example_files`. Auth gates inherited from the `Depends(get_active_user)` already on the skills router. Unknown skill name → 404 via `app.errors.NotFound` (the canonical envelope from ADR 0003). The `POST /skills/{name}/fork` endpoint stays a 501 stub — needs DB-backed user/team-scope storage that isn't in C1.
* OpenAPI sketch `docs/api/backend-openapi.yaml`: `SkillSummary` gains `minimum_inference_tier` and `output_format` (the loader surfaces both); the `/api/v1/skills/{skill_name}` GET path documents its 404. The wire shape drops `null`-valued optionals and empty `tags` for compactness.

**Skill corpus reality check.** The `skills/` directory ships with 11 starter skill folders (10 substantive starter skills the PRD describes plus the `skill-creator` meta skill — by visual count: action-items-from-client-alert, comms-improver, contract-qa, dpa-checklist-review, enhance-prompt, msa-review-commercial-purchase, msa-review-saas, nda-review, skill-creator, vendor-privacy-policy-first-pass, plus `CONTRIBUTING.md` at the top level). All 11 load through C1's loader cleanly. The frontmatter conventions across the corpus diverge from the formal `docs/skill-authoring-guide.md` in ways the loader's permissive mode accommodates rather than reject:

* `nda-review`, `comms-improver` use `output_format: markdown` (the guide says `report`);
* `dpa-checklist-review` uses `output_format: structured_checklist`;
* `nda-review` declares `jurisdiction: US-default`, `comms-improver` declares `agnostic`, `dpa-checklist-review` declares `regime-dependent` — the guide enumerates `us | eu | regime-aware | global | other`;
* `skill-creator` and `enhance-prompt` carry only `name` + `description` (no `lq_ai:` namespace at all);
* none of the skills declare `lq_ai.minimum_inference_tier`.

The loader treats this as the corpus reality, not as errors. The forward-looking convention in the authoring guide should be reconciled — that's a docs-side decision (either tighten the corpus to match the guide, or relax the guide to match the corpus). Surfaced as a deferred item below.

**Tests (37 net-new in api/, target was ≥18):**

* `api/tests/test_skill_loader.py` — 24 unit tests: schema validation matrix, tier-bound enforcement, summary-derivation defaults, frontmatter regex, happy-path load, malformed-skill skipping with WARNING, empty/missing directory handling, single-skill load, lazy reference/example file materialisation, tag-filter case-insensitivity, atomic-swap behaviour, in-flight reader consistency, SIGHUP handler installation, SIGHUP-driven registry replacement (invoked directly), and a smoke test against the real `skills/` corpus that asserts ≥10 starter skills load cleanly.
* `api/tests/test_skill_endpoints.py` — 12 integration tests (DB-backed) covering both endpoints' auth gates (401, 403 with `password_change_required`), happy paths, tag filter, scope filter, invalid scope → 422, 404 for unknown skill, sparse-frontmatter optional-field omission, and the full Skill shape including lazy-loaded reference and example files.
* `api/tests/test_skill_sighup_reload.py` — 1 subprocess integration test that spawns a real Python child process, has it install the SIGHUP handler against a temp skills directory, then sends real SIGHUP from the parent and asserts the child's registry reflects the post-mutation directory state.
* Fixture skills under `api/tests/fixtures/` — synthetic content with no legal substance (3 well-formed in `skills/`, 4 deliberately malformed in `skills_with_bad/` plus one well-formed sibling and a `CONTRIBUTING.md` to verify top-level non-skill files are silently skipped). Per CLAUDE.md, agents do not author legal-substance skill content; real `skills/*` content is a human-attestation pipeline concern.

End-to-end verification: 24 unit tests + 1 SIGHUP subprocess test pass under the standard `pytest` invocation; 12 endpoint integration tests run cleanly when `DATABASE_URL` is set per the worktree's documented quickstart. mypy clean across `api/app/`. ruff format + check clean across the C1 surface. The smoke test against the real `skills/` corpus confirms all 10+ starter skills load.

**Deviations from the C1 brief:**

* The brief's recommendation to put `gateway/` aware of skills at all is deferred to C2. C1 ships the loader on `api/` only; the gateway has zero skill-related code post-C1. Per ADR 0004 this is the documented path, not a deviation.
* The brief described frontmatter validation as "strict" and "validate strictly; surface a clear error per skill on parse failure but don't fail the whole startup". The loader meets the second half of that brief verbatim — but the schema is *permissive*, not strict. Strict-mode validation would reject most of the M1 corpus, which is a worse outcome than accepting non-canonical values and surfacing them as-is. The deviation is documented in the schema module's docstring, in the C1 commit message for the loader, and in the corpus reality check above.
### C2 — Skill Service: prompt assembly ✅

Gateway-side prompt assembly: when a chat request arrives at the gateway with skills attached, the gateway fetches each skill from the backend's registry, assembles the bodies + reference files (with input substitution), prepends the result to the system message, and dispatches to the provider adapter.

**ADRs.** [ADR 0007 — Skill prompt assembly](adr/0007-skill-prompt-assembly.md) records three architectural choices (renumbered from 0006 at merge time — C5's document-pipeline ADR took 0006 first):

* **Backend↔gateway auth — Path A.** A new internal route `GET /api/v1/internal/skills/{name}` authenticated by the existing `X-LQ-AI-Gateway-Key` shared secret (constant-time compare). User-facing routes stay under user-token auth; service-to-service routes stay under shared-secret auth. The two never mix on a single route.
* **Templating — regex `{{name}}`.** Skill-input substitution is a bounded regex (`[a-zA-Z_][a-zA-Z0-9_]*`); values are inserted verbatim, no expression evaluation, no chained substitution (no template-injection vector). No new SBOM entry.
* **Skill-attachment surface — request-extension on the body.** `lq_ai_skills: list[str]` and `lq_ai_skill_inputs: dict[str, dict[str, Any]]` extend `ChatCompletionRequest`. Matches the existing B3/B4 pattern; per-skill input scoping; ordered list so the assembler concatenates in caller-supplied order. The pre-existing `skill_name: str` (audit-log tag) is preserved; the gateway populates it from the first attached skill if the caller didn't set it.

**What landed:**

* **`api/app/api/internal.py`** — new `GET /api/v1/internal/skills/{name}` handler. Auth is constant-time `X-LQ-AI-Gateway-Key` compare. Same response shape as the user-facing route. Operator-misconfiguration posture: if `LQ_AI_GATEWAY_KEY` is unset on the backend, the route returns 500 (refuses to accept service-to-service traffic) rather than running open.
* **`gateway/app/clients/backend.py`** — long-lived `httpx.AsyncClient` pooled across calls; `BackendClient.get_skill(name)` with cache-aware fetch, full error-translation matrix (404 → `SkillNotFound`, 401/5xx/timeout/network/malformed → `SkillFetchFailed`/`BackendUnreachable`). Process-global handle wired through `configure_backend_client()` / `close_backend_client()` from the gateway's lifespan.
* **`gateway/app/clients/backend.py:SkillCache`** — in-memory dict TTL cache (default 60s; tunable via `LQ_AI_SKILL_CACHE_TTL_SECONDS`). Monotonic clock for deterministic testing. Failures are NOT cached.
* **`gateway/app/skills/assembler.py`** — pure-function assembler. `interpolate(template, bindings)` applies `{{name}}` substitution; `extract_required_inputs(skill)` re-parses the verbatim frontmatter to find the corpus-shape `inputs.required` block; `assemble_skill_prompt(skills, ...)` builds the system message (skill body + reference files first, separator, operator's pre-existing system message after).
* **`gateway/app/api/inference.py`** — when `chat_request.lq_ai_skills` is non-empty, calls `_apply_skill_prompt_assembly()` before model resolution. Mutates the request in place: replaces `messages` with `[assembled_system, *non_system_messages]`. On success, stamps `lq_ai_applied_skills` on the response body and on each streaming chunk envelope.
* **`gateway/app/main.py`** — lifespan now calls `configure_backend_client()` at startup and `close_backend_client()` at shutdown. The `BackendClient` is stored on `app.state.backend_client`.
* **Cross-subsystem error contract.** New crossing codes: `skill_not_found` (404), `skill_fetch_failed` (502), `skill_input_missing` (400). Added on both sides (`api/app/errors.py`, `gateway/app/errors.py`); registered in api/'s `_GATEWAY_CODE_MAP`; documented in both OpenAPI sketches' enums; covered by `tests/test_error_code_contract.py`.
* **`api/app/api/chats.py`** — `MessageCreate` body now accepts `skills: list[str]` and `skill_inputs: dict[str, dict[str, Any]]`; `_build_gateway_request()` forwards them as `lq_ai_skills` / `lq_ai_skill_inputs` on the gateway request. The non-streaming response body's new `applied_skills` field surfaces the gateway's `lq_ai_applied_skills`. The streaming `MessageComplete` event includes `applied_skills`.
* **OpenAPI sketches.**
  * `docs/api/backend-openapi.yaml` adds `/api/v1/internal/skills/{name}` (GET; tagged `internal`; `gatewayKeyAuth` security scheme); `MessageCreate.skills` / `skill_inputs`; `MessagePostResponse.applied_skills`; `MessageComplete.applied_skills`; the three new error codes in the `Error.code` enum.
  * `docs/api/gateway-openapi.yaml` adds `lq_ai_skills` / `lq_ai_skill_inputs` to `ChatCompletionRequest`; `lq_ai_applied_skills` to `ChatCompletionResponse`; the three new error codes in `GatewayError.code`.
* **Configuration.** `gateway.yaml.example` documents the bidirectional use of `LQ_AI_GATEWAY_KEY` and points operators at `LQ_AI_API_URL` + `LQ_AI_SKILL_CACHE_TTL_SECONDS`. `docker-compose.yml` passes both new env vars to the gateway service.

**Tests (50 net-new):**

* **api/ side (15 new):**
  * `api/tests/test_internal_skills.py` — 8 integration tests: 401 on missing/wrong/near-miss key (constant-time compare regression guard), 200 happy path, 404 unknown skill, 500 when `LQ_AI_GATEWAY_KEY` unset, bearer-token-alone rejected, gateway-key-alone accepted (no user required).
  * `api/tests/test_chats_skills_forwarding.py` — 8 integration tests: skills/skill_inputs flow to gateway, no-skills means empty/absent extension, applied_skills surfaces in response, error pass-through (skill_not_found → 404, skill_fetch_failed → 502, skill_input_missing → 400).
  * `api/tests/test_endpoints.py` adds the new `/internal/skills/{name}` route to `IMPLEMENTED_ROUTES`. `api/tests/test_openapi.py` adds the route to `EXPECTED_PATHS` (32 paths now, up from 31).

* **gateway/ side (52 new):**
  * `gateway/tests/test_backend_client.py` — 24 unit tests: `SkillCache` (5: miss, put/get, TTL expiry, invalidate, clear); `BackendClient.get_skill` (16: happy path, gateway-key + request-id header forwarding, 404, 401 with operator-actionable log, 500/503, timeout, network failure, non-JSON body, schema-drift body, cache populates on success, cache does NOT populate on failure, cache expiry refetches, aclose idempotent, aclose respects injected client); `configure_backend_client` (3: env defaults, explicit args, TTL env override).
  * `gateway/tests/test_skill_assembler.py` — 28 unit tests: `interpolate` (8 — substitution, whitespace tolerance, unknown-vars-pass-through, non-strings, None → "", no expression evaluation, no chained substitution); `extract_required_inputs` (5 — M1 corpus shape, simple list, no inputs, malformed YAML, non-dict inputs); `assemble_skill_prompt` (15 — empty input, single skill body+metadata, version handling, body/reference substitution, multi-skill order preservation, system-message prepend, empty/whitespace system-message handling, missing-required-input single + cross-skill aggregation, empty-string-as-missing, optional-unbound-leaves-placeholder, per-skill input scoping).
  * `gateway/tests/test_inference_skill_assembly.py` — 10 integration tests: skill body lands in Anthropic system message; pre-existing system message preserved; input substitution; missing required → 400 + skill_input_missing; unknown skill → 404 + skill_not_found; backend 5xx → 502 + skill_fetch_failed; cache hit only once across N requests; multi-skill in order; skill_name audit tag from first attached skill; no-skills request unchanged from B4.

* **Cross-subsystem (`tests/test_error_code_contract.py`):** `EXPECTED_CROSSING_CODES` extended with `skill_not_found`, `skill_fetch_failed`, `skill_input_missing` — same 5 conformance tests confirm the codes are declared on both sides.

**Closes the C1-flagged deferred item** (Gateway-side skill content fetch).

**Tool-use scope check (deferred-item recommendation from the brief).** None of the 11 starter skills declare `tools:` in their frontmatter. Bidirectional tool-call translation in the Anthropic adapter (B3's deferred item) is **not** exercised by C2 and stays deferred. Documented in ADR 0007's "What this ADR does not commit to" section.

**Verification:** the Anthropic respx-mock captures the request body; tests assert that `system` contains the skill content and that the response body includes `applied_skills`. Real-key end-to-end verification requires `ANTHROPIC_API_KEY`; deferred to operator. Test runs blocked in this session due to harness-level pytest restrictions; mypy-strict + ruff-format checks pass on the gateway/ surface; the build is intentionally conservative (every public function is annotated; no shared-state across requests outside `app.state`).

### C4 — File upload + storage ✅

The four file endpoints (`POST /api/v1/files`, `GET /api/v1/files/{id}`,
`GET /api/v1/files/{id}/content`, `DELETE /api/v1/files/{id}`) are wired
end-to-end against MinIO with streaming I/O, content-addressable identity
via SHA-256, and a 100 MB-per-request size cap (`LQ_AI_MAX_UPLOAD_SIZE_MB`).

**Migration `0003_create_files_table.py`** — adds the `files` table per
`docs/db-schema.md` §`files`. Columns: `id` (UUID PK), `owner_id` (FK to
users with ON DELETE RESTRICT), `project_id` (nullable, FK deferred to C7),
`filename`, `mime_type`, `size_bytes`, `hash_sha256`, `storage_path`,
`ingestion_status` (CHECK in {`pending`,`processing`,`ready`,`failed`}),
`ingestion_error`, `created_at`, `deleted_at`. Indexes: owner-active
(listing), project-active (C7's file picker), status-pending-or-processing
(C5's worker pickup), and hash (PRD §3.5 dedup). Reversible.

**Streaming I/O.** `api/app/storage.py` now exposes `stream_upload` (S3
multipart-upload with 8 MiB parts; SHA-256 computed as bytes flow past;
413/PayloadTooLarge raised the moment the running total exceeds the cap;
in-progress upload aborted on any failure so MinIO doesn't retain orphan
parts), `stream_download` (async-context-manager yielding an async byte
iterator), and `delete_object` (idempotent on 404). Bytes never reach
RAM in their entirety: Starlette spools `UploadFile` to a
`SpooledTemporaryFile` past 1 MB, and our handler reads `MULTIPART_PART_SIZE`
chunks from it.

**Architectural decisions (ADR 0005).** Two questions surfaced (C4's ADR was renamed from 0004 to 0005 at merge time because C1 took 0004 first):

* **Soft-delete vs hard-delete.** ADR 0005 documents soft-delete by
  default — `DELETE` flips `deleted_at` and leaves the MinIO bytes in
  place. Hard-deletion is owned by D6 (per-user export+delete) and a
  future operator-facing GC sweep. Reasoning: audit-log integrity, the
  C5 race window, the `documents.file_id ON DELETE CASCADE` blast
  radius, and consistency with `users.deleted_at`.
* **MinIO key scheme.** ADR 0005 picks the bare file UUID as the
  storage key (`<bucket>/<file_id>`) — no owner prefix, no filename in
  the path. Multitenancy is enforced at the application layer
  (`files.owner_id`); the key scheme is not a parallel access boundary.

**Error hierarchy.** Added `app.errors.PayloadTooLarge` (HTTP 413) +
`CODE_PAYLOAD_TOO_LARGE = "payload_too_large"`. Backend-only code; does
NOT cross the gateway boundary, so the cross-subsystem contract test
(`tests/test_error_code_contract.py`) is unaffected.

**Per-user isolation.** `_load_visible_file` filters on `(id, owner_id,
deleted_at IS NULL)`. The cross-user case returns 404 (not 403) per the
brief and CLAUDE.md — avoids leaking existence information.

**Content-Disposition.** `_content_disposition_attachment` emits the
canonical RFC 6266 form for ASCII filenames and adds an RFC 5987
`filename*=UTF-8''<percent-encoded>` for non-ASCII filenames. Quote and
backslash characters are escaped per the spec.

**`ingestion_status='pending'`.** Set on insert. C4 does NOT enqueue or
notify — the C5 document pipeline polls or subscribes; that's its
problem.

**Dependency.** Added `python-multipart>=0.0.20,<0.1` to `api/`'s
runtime deps — required by Starlette to parse `multipart/form-data`
request bodies. Already a Starlette optional dep; we pin it directly
because we use `UploadFile` at runtime. No new SBOM family.

**Tests (43 new).**

* `api/tests/test_storage_streaming.py` — 14 unit tests against an
  in-memory `FakeS3Client` covering the multipart-upload sequence,
  SHA-256/size accounting across chunk shapes (empty body, multiple
  small chunks, parts-boundary roll-over), the 413 abort path, the
  abort-failure tolerance, the streaming download path, and
  `delete_object` idempotency.
* `api/tests/test_files_endpoints.py` — 22 integration tests
  (DB-backed + MinIO-mocked) covering the full handler matrix: auth
  gates (401, 403), validation (400, 422), happy-path round trip
  (upload → metadata → byte-equal download), per-user isolation
  (404 cross-user), soft-delete semantics (idempotent, MinIO bytes
  preserved), the 413 size cap, and the Content-Disposition shape
  for ASCII and non-ASCII filenames. The bytes-fidelity assertion
  (the C4 verification step from M1-IMPLEMENTATION-ORDER) lives here.
* `api/tests/test_files_helpers.py` — 7 unit tests for the
  `Content-Disposition` builder and `_validate_file_id`.
* `api/tests/test_migrations.py` — 4 new tests for the `files` table:
  table existence, the four expected indexes, the `ingestion_status`
  CHECK, and the `size_bytes >= 0` CHECK.
* `api/tests/test_errors.py` — extended with the `PayloadTooLarge`
  case in the parametrized status/code matrix.
* `api/tests/test_endpoints.py` — file routes added to
  `IMPLEMENTED_ROUTES` so the 501-stub test no longer asserts on
  them.

**Drift flagged.** `docs/api/backend-openapi.yaml` updated: the four
file endpoints carry full responses (not just 201/200/204), with
documented 4xx/5xx error envelopes; the `Content-Disposition` and
`X-Content-Type-Options` headers are documented on the GET-content
endpoint; the `payload_too_large` code is added to the `Error.detail.code`
enum. `.env.example` adds `LQ_AI_MAX_UPLOAD_SIZE_MB=100`.

End-to-end verification: stack-level smoke (real MinIO via
`docker compose up -d`, real upload of a binary blob via curl,
download via curl, byte-compare) is the next-session operator
verification step. The mocked-MinIO bytes-fidelity test enforces the
contract automatically on every CI run.

### C7 — Project service ✅

`/api/v1/projects` CRUD endpoints + file/skill attachment endpoints +
free-form `context_md` document + the `privileged`/`minimum_inference_tier`
constraint enforced at three layers (Pydantic schema, PATCH handler
merge-state validation, and the DB CHECK constraint). New migration
`0004_create_projects.py` lands `projects`, `project_files`, and
`project_skills` tables, plus closes the C4-deferred FK constraint
on `files.project_id` (`fk_files_project_id REFERENCES projects(id)
ON DELETE SET NULL`).

**Migration `0004_create_projects.py`** — `projects` table with
`owner_id` (FK→users, ON DELETE RESTRICT), `name`, `slug`, `description`,
`context_md`, `privileged` (bool, default false), `minimum_inference_tier`
(SMALLINT, nullable), `archived_at` (soft-delete column;
NULL means active). CHECK constraints: tier-range (NULL or 1-5),
privileged-implies-tier, name length (1-200), slug length (1-80).
Partial UNIQUE index on `(owner_id, slug) WHERE archived_at IS NULL`
so archived slugs free up for reuse. Partial listing index on
`(owner_id, created_at DESC) WHERE archived_at IS NULL`. Reuses the
A1 `set_updated_at()` trigger function for `updated_at` maintenance.

`project_files` (composite-PK join, ON DELETE CASCADE on both ends)
and `project_skills` (composite-PK join, `skill_name` is *text* not a
FK because skills are filesystem-canonical per ADR 0004). Indexes for
the inverse-lookup queries: `(file_id)` on `project_files`,
`(skill_name)` on `project_skills`.

**Endpoints landed:**

* `POST /api/v1/projects` — create. Slug is generated from name when
  omitted; collisions resolve with a numeric suffix (`-2`, `-3`, …).
  Privileged-without-tier returns 422 (Pydantic-driven; the schema's
  `model_validator` enforces the rule at the API boundary).
* `GET /api/v1/projects?archived=true|false` — list (default excludes
  archived; `archived=true` returns archived only).
* `GET /api/v1/projects/{id}` — fetch single, with `attached_file_ids`
  and `attached_skill_names` populated from the join tables. Archived
  projects are visible via direct GET (the listing default excludes
  them) so a client can render an archived-detail page.
* `PATCH /api/v1/projects/{id}` — partial update with the
  `exclude_unset` pattern that distinguishes "field absent" from
  "explicit null." The privileged-tier rule is re-checked against the
  *merged* state (the DB CHECK is the safety net).
* `DELETE /api/v1/projects/{id}` — soft-delete (sets `archived_at`).
  Idempotent: a second DELETE on an already-archived project returns
  404.
* `POST/DELETE /api/v1/projects/{id}/files` and
  `POST/DELETE /api/v1/projects/{id}/skills` — attachment endpoints.
  Cross-user files/projects → 404; unknown skills → 404; already-
  attached → 409. Skills are validated against the in-memory registry
  before insert.

**Per-user isolation.** Projects are scoped to `owner_id`; cross-user
access returns 404 (not 403), matching C4's posture. File attachment
requires the user to own *both* the project AND the file; skill
attachment is registry-wide so any authenticated user may attach any
registered skill.

**`Conflict` exception class added.** `app.errors.Conflict` (HTTP 409,
code `conflict`) for slug collisions and idempotency-violating
attachments. Backend-only code; does not cross the gateway boundary,
so the cross-subsystem contract test is unaffected.

**Closed C4 deferred items:**

1. **`files.project_id` FK constraint.** Migration 0004's ALTER TABLE
   adds `fk_files_project_id REFERENCES projects(id) ON DELETE SET
   NULL`. SET NULL rather than CASCADE because a file is independently
   owned and may be in other projects via the `project_files` join.
2. **Multipart `project_id` form field on POST /api/v1/files.** The
   C4 handler now accepts the field, validates it against the caller's
   active projects, and persists `files.project_id`. Bogus,
   cross-user, or invalid-UUID `project_id` returns 422 *before* any
   bytes touch MinIO.

**Tests (75 net-new in api/, plus 6 migration tests + 1 errors entry):**

* `api/tests/test_projects_unit.py` — 27 unit tests on
  `slugify`, `ProjectCreateRequest` (privileged-tier rule, context-md
  byte cap, slug pattern, extra-fields rejection), and
  `ProjectUpdateRequest` (partial-update semantics, no privileged
  rule on PATCH).
* `api/tests/test_projects_endpoints.py` — 42 integration tests
  covering the full handler matrix: auth gates, CRUD round-trip,
  per-user isolation (404 cross-user), the privileged constraint at
  schema and PATCH-merge layers, slug collision suffixing,
  archive/unarchive via PATCH, file/skill attachment (happy path,
  unknown, cross-user, already-attached, detach, idempotent), context
  cap, and the C7 verification contract end-to-end.
* `api/tests/test_migrations.py` — extended with 6 new tests:
  `projects` + `project_files` + `project_skills` table existence,
  expected indexes (including the partial slug-uniqueness index),
  the `fk_files_project_id` constraint existence, the
  privileged-implies-tier CHECK firing, the tier-range CHECK firing,
  and the ON DELETE SET NULL behavior of `files.project_id`.
* `api/tests/test_errors.py` — extended with the `Conflict` case in
  the parametrized status/code matrix.
* `api/tests/test_endpoints.py` — projects routes added to
  `IMPLEMENTED_ROUTES`. The route-inventory lower-bound was loosened
  from 29 to 15 to reflect that wave-2 tasks are migrating routes
  from the 501-stub set into real implementations.
* `api/tests/test_openapi.py` — `EXPECTED_PATHS` updated with the two
  new detach paths; the count assertion bumped to 33.
* `api/tests/test_admin_bootstrap.py` — the gate-cleared probe
  switched from `/api/v1/projects` (now real) to
  `/api/v1/knowledge-bases` (still 501).

**Drift flagged.** `docs/api/backend-openapi.yaml`: the `/projects`
family now documents real shapes (status codes, response envelopes,
the privileged constraint behavior, the `archived` filter on GET,
the `archived` flag on PATCH), the new detach endpoints
(`/projects/{id}/files/{file_id}` and `/projects/{id}/skills/{skill_name}`),
the `Project`/`ProjectCreate`/`ProjectUpdate` schema shapes (slug,
context_md, attached_file_ids, attached_skill_names, archived_at),
and the `conflict` code added to the `Error.detail.code` enum.
`docs/db-schema.md`: the `projects` schema doc updated to match what
0004 lands (gen_random_uuid, slug column, archived_at, the join
tables renamed to `project_files`/`project_skills` matching the
migration), plus a section for the C4-deferred FK closure.

End-to-end verification: stack-level operator smoke
(`docker compose up -d`, login, `POST /api/v1/projects`, attach a
skill, attach a file, `GET` and verify round-trip, `POST` again with
`privileged=true` without tier and confirm 422) is the next-session
operator verification step. The 48-test integration suite enforces
the contract automatically on every CI run that has DATABASE_URL set.

### C5 — Document pipeline (basic) ✅

The async document pipeline that processes uploaded PDFs into
character-precise chunks. PyMuPDF is the canonical parser (byte-precise
offsets); Docling runs alongside for structured-content extraction
(stashed for M2 consumption). The chunker produces chunks whose
``[char_offset_start:char_offset_end]`` slice of the canonical text
equals the chunk's ``content`` byte-for-byte — the load-bearing
invariant the M2 Citation Engine consumes.

**ADR 0006 — document pipeline architecture.** Records the four
architectural calls C5 made: (1) Docling primary, PyMuPDF for
byte-precise offset reconciliation; (2) `arq` for the worker queue
(async-native, small footprint, fits the codebase); (3) **embeddings
deferred to C6** — chunks land with `embedding=NULL` for M1, the
schema accepts NULL, and C6 backfills via the gateway's
`/v1/embeddings` once it lands; (4) idempotency via transactional
delete-then-insert.

**Migration `0005_create_documents_and_chunks.py`.** Adds the
`documents` and `document_chunks` tables, enables the pgvector
extension. Embedding column is `vector(1536)` (sized for OpenAI
text-embedding-3-small/-large; alterable when C6 picks); content_tsv
is a generated TSVECTOR column. Indexes: `idx_chunks_embedding`
(ivfflat, vector_cosine_ops), `idx_chunks_tsv` (GIN), `idx_chunks_document`
(ordered scan), `idx_documents_file_id`. Reversible.

**The pipeline (`api/app/pipeline/`).**

* `parsers.py` — PyMuPDF + Docling adapters. PyMuPDF is mandatory
  (without it no offsets, no ingestion); Docling is best-effort
  (failures degrade gracefully to PyMuPDF-only with a WARNING log).
  Encrypted PDFs raise `ParserUnsupported` (M1 doesn't decrypt).
* `chunker.py` — character-precise sliding-window chunker. Snaps to
  paragraph breaks first, then sentence terminators, within a
  200-char lookback window — but never below the configurable
  `min_chars` floor. Page assignment via the parser's PageSpan
  table; chunks crossing page boundaries record both pages.
* `ingest.py` — orchestration: load file row, refuse if soft-deleted
  or unsupported MIME, pull bytes via `stream_download`, run parser
  cascade in `asyncio.to_thread`, chunk, persist Document +
  DocumentChunks transactionally (idempotent replace), flip
  `files.ingestion_status` to `ready` (or `failed` with
  `ingestion_error`).

**The worker (`api/app/workers/`).** `arq`-backed. New
docker-compose service `ingest-worker` runs `arq
app.workers.document_pipeline.WorkerSettings`. The worker's
on-startup hook re-enqueues any rows stuck in `pending` or
`processing` (self-healing across crashes / restarts). The
upload handler (C4) now enqueues a job after successful row
commit; enqueue failures are non-fatal — the row stays at
`pending` and the worker's startup sweep picks it up.

**New runtime deps (justified per ADR 0006).** `pymupdf>=1.24`
(AGPL-3.0, server-side per PRD §1519/§7.2), `docling>=1.16`
(MIT), `arq>=0.25` (MIT). New env vars in `.env.example`:
`LQ_AI_INGEST_WORKER_CONCURRENCY=2`, `LQ_AI_DOCLING_TIMEOUT_SECONDS=300`,
`LQ_AI_DOCLING_ENABLED=true`, `LQ_AI_CHUNK_TARGET_CHARS=2000`,
`LQ_AI_CHUNK_OVERLAP_CHARS=200`.

**Tests (37+ new unit tests + 6 new migration tests + 6 new
integration tests; ≥49 total net-new):**

* `api/tests/test_chunker.py` — 19 unit tests including the
  canonical fidelity invariant (`canonical[start:end] ==
  content`) over varied chunk shapes, unicode content, and the
  default chunk size.
* `api/tests/test_pipeline_parsers.py` — 13 unit tests including
  the **mandatory offset-fidelity test** parametrised over three
  fixture PDFs (simple, multi-page, two-column). Every chunk in
  every fixture slices back byte-for-byte.
* `api/tests/test_pipeline_ingest.py` — 6 integration tests
  (DB-backed + MinIO-mocked): happy path, multi-page chunk
  page-tracking, idempotent re-run (no duplicate chunks),
  unsupported MIME (failed + `unsupported_type`), corrupt PDF
  (failed + `parse_failed`), soft-deleted skip.
* `api/tests/test_workers_queue.py` — 5 unit tests: enqueue
  success / failure / import-error paths, idempotent close.
* `api/tests/test_migrations.py` — extended with 6 C5 tests:
  documents and document_chunks table existence, pgvector
  extension installed, documents.file_id UNIQUE, offset CHECK
  constraints, (document_id, chunk_index) UNIQUE, FK CASCADE
  on file hard-delete.

**Verification (achievable without DB).** ruff format clean. ruff
check clean (3 pre-existing B017 issues in test_migrations.py
unaffected). mypy clean across `api/app/` (1 pre-existing
storage.py mypy issue from C4 not in C5 scope). 37 unit tests pass
in 0.22s with PyMuPDF installed; the 6 integration tests + 6
migration tests run with `DATABASE_URL` set per the standard
quickstart.

End-to-end verification (DB-required): `docker compose up -d`,
`make migrate` applies migration 0005 cleanly, upload a real PDF
via the API, wait for `ingestion_status='ready'`, query
`document_chunks`, slice a random chunk's content from the
canonical text, byte-compare. The mocked-MinIO + real-PyMuPDF
integration test enforces this contract automatically on every
CI run.

**Deviations from the C5 brief:**

* Embeddings deferred to C6, documented in ADR 0006 §3 and the
  newly-deferred-items section below. The C5 brief listed
  "embeddings generated" in scope; we ship chunks with
  `embedding=NULL` so the citation-engine offset contract holds
  immediately, and C6 (KB hybrid retrieval) is the natural place
  for the embedding model selection + generation work.
* `metadata` column on `document_chunks` named `metadata_json` to
  avoid SQLAlchemy declarative's `Base.metadata` reserved name
  conflict. Functionally equivalent.

---

## Tasks ahead

### B6 — Additional provider adapters (optional)

**Depends on:** B3 (template).

**Scope:** OpenAI, Vertex (Anthropic on Vertex), Bedrock, Ollama. Optional for M1 baseline; **Ollama is critical for Mode 2** (air-gapped local inference). The other three are recommended for breadth.

**Per provider:** ~3-4h following B3's adapter template.

---

## Deferred items (cataloged with owning tasks)

These were flagged during execution but deliberately deferred. Each has an owning task — when that task lands, it pulls the deferred item with it. **Per Kevin's standing instruction: address tech debt along the way; don't foist on the community.**

### ~~Deferred to B2~~ — landed in B2

| Item | Disposition |
|---|---|
| `lq_ai.cli reset-admin-password` CLI | **Landed in B2 as `python -m app.cli reset-admin-password`.** The package is named `app`, not `lq_ai`, in this codebase; quickstart.md:325 was updated to the correct invocation. Argparse-based, ~150 LOC, 5 integration tests. A `[project.scripts]` console-script entry was considered but pulled because the current Dockerfile installs only the package metadata (the `app/` source tree is `COPY`'d in afterward); the console script would resolve `app.cli:main` against an empty wheel and fail. `python -m app.cli` works correctly because the API container's WORKDIR is `/app`. Reintroduce the console script when the Dockerfile installs the real wheel. |

### ~~Deferred to B5~~ — landed in B5

| Item | Disposition |
|---|---|
| `lq_ai.errors` exception hierarchy | **Landed in B5.** ADR 0003 records the architectural decision: parallel hierarchies in `api/app/errors.py` and `gateway/app/errors.py` rather than a shared Python module (would violate CLAUDE.md's hard rule on subsystem isolation). The contract is the error-code enum in the OpenAPI sketches; a cross-subsystem conformance test under `tests/test_error_code_contract.py` keeps the two sides in sync. CONTRIBUTING.md's "Exceptions" bullet now points at the real modules. |
| Real `GatewayClient` chat_completion / embeddings methods | **Landed in B5.** Non-streaming + streaming chat-completion + embeddings stub. Full error-translation matrix per ADR 0003 (timeout / network / 5xx / 4xx with envelope / 401 special-case). 27 unit tests against a respx-mocked gateway. |

### Newly deferred (surfaced during B5)

| Item | Surface | Owning task |
|---|---|---|
| Gateway-side `X-LQ-AI-Gateway-Key` auth middleware | `docs/api/gateway-openapi.yaml` documents it as a security scheme; `api/app/clients/gateway.py` always sends it; **the gateway has no middleware checking it** | The backend's translation logic for a gateway-401 case is unit-tested via respx and the right behavior (503 + WARNING log; user does NOT see "wrong gateway key") is in place. The middleware itself is operator-scope hardening — most natural in **D-phase** alongside other gateway hardening (rate limiting, request signing). Could land earlier if a procurement-evaluator deployment forces the question. Until then, **the gateway is trust-on-first-network**: any caller that can reach the gateway port can call `/v1/chat/completions`. Operators must front the gateway with network-level isolation (Compose default network; K8s Service). |

### Newly deferred (surfaced during C1)

| Item | Surface | Owning task |
|---|---|---|
| Skill-authoring-guide ↔ corpus drift | `docs/skill-authoring-guide.md` documents `output_format: report \| table \| issues_list \| redline` and `jurisdiction: us \| eu \| regime-aware \| global \| other`. The M1 corpus uses `output_format: markdown \| structured_checklist \| ...` and `jurisdiction: US-default \| agnostic \| regime-dependent \| ...`. C1's loader is permissive and accepts the corpus as-is. | Decide the correct reconciliation (tighten the corpus to match the guide, or relax the guide to match the corpus). Either is a docs-side task; not blocking. Most natural alongside D2 or as a focused docs PR led by a maintainer with practicing-attorney input. The C1 loader will keep loading whatever the corpus actually contains. |
| `POST /api/v1/skills/{name}/fork` endpoint | C1's `app/api/skills.py` keeps the A4 501 stub | Needs DB-backed user/team-scope skill storage which C1 does not deliver. Lands when user/team scope storage is wired (likely a focused C-phase task between C1 and D-phase, or folded into D2's UI work). |
| ~~Gateway-side skill content fetch (C2)~~ | **Closed in C2** — ADR 0007 records the auth + templating + request-surface decisions. The gateway has `BackendClient` (httpx pool + 60s TTL skill cache) wired against `LQ_AI_API_URL` + `LQ_AI_GATEWAY_KEY`; the assembler in `gateway/app/skills/assembler.py` builds the system message; `/v1/chat/completions` mutates the request to insert the assembled prompt and surfaces `lq_ai_applied_skills` on the response. |

### Newly deferred (surfaced during C4)

| Item | Surface | Owning task |
|---|---|---|
| MinIO-bytes GC for soft-deleted files | C4's `DELETE /api/v1/files/{id}` flips `deleted_at` and leaves the bytes; ADR 0005 documents the rationale | **D6 (per-user export+delete)** owns the user-driven hard-delete path. Operators who care about storage cost before D6 ships need a manual cleanup tool. Filed as a candidate **DE-XXX** in PRD §9 next time we update the deferred-enhancements list — the natural shape is a CLI subcommand under `python -m app.cli` that hard-deletes `files` rows + objects past a retention window. |
| ~~`project_id` FK constraint on `files.project_id`~~ | ~~Migration 0003 leaves the column nullable without an FK constraint~~ | **Landed in C7.** Migration 0004's ALTER TABLE adds `fk_files_project_id REFERENCES projects(id) ON DELETE SET NULL`. Migration test pins both the constraint existence and the SET NULL behavior. |
| ~~Multipart `project_id` form field on `POST /api/v1/files`~~ | ~~The handler accepted but did not persist the field~~ | **Landed in C7.** The C4 handler now declares `project_id` as a `Form` parameter, validates it against the caller's active projects (rejecting bogus / cross-user / invalid-UUID values with 422 before any bytes touch MinIO), and persists `files.project_id`. 4 new integration tests cover persistence, unknown id, cross-user id, and invalid-UUID id. |
| `forceful=true` immediate hard-delete on `DELETE /api/v1/files/{id}` | Considered in ADR 0005; not in C4 scope | Out of M1; will be reconsidered in D-phase if operator feedback reveals demand. Until then, the only hard-delete path is D6. |

### Newly deferred (surfaced during C5)

| Item | Surface | Owning task |
|---|---|---|
| Embedding generation for `document_chunks` | C5 writes `embedding=NULL` for every chunk per ADR 0006 §3; the column type is `vector(1536)` and the ivfflat index is in place | **C6 (KB hybrid retrieval)** absorbs the embedding-generation work. C6 already needs the gateway's `/v1/embeddings` to actually work (it's the retrieval-side call); landing it once for both ingestion and retrieval is more efficient than landing it twice. The M1-IMPLEMENTATION-ORDER C6 spec should be updated to reflect this absorption (small, additive — the retrieval flow naturally calls embed-on-write for any chunks where `embedding IS NULL`). |
| Gateway `/v1/embeddings` endpoint implementation | B5 left it as a 501 stub returning `not_implemented`; `GatewayClient.embeddings()` already has the right shape | **C6** lands the real implementation. Per CLAUDE.md the embedding call must go through the gateway (it's a provider call); C6 is the right place because it's the consumer. B6 (additional provider adapters) is a separate concern. |
| OCR for image-only PDFs | C5 marks scanned/image PDFs as `failed` because PyMuPDF returns empty text; per the brief OCR is M2 | **M2** Document Pipeline expansion. Mistral OCR API for cloud, PaddleOCR-VL for air-gapped. PRD §3 and §6.1 have the design. |
| DOCX/RTF/TXT parser support | C5 marks non-PDF MIMEs as `failed` with `unsupported_type`; M1 is PDF-only per the brief | **M2**. The parser cascade in `app/pipeline/parsers.py` is structured to accept additional adapters; the dispatch is by MIME type. New adapters need to produce a canonical character stream + page spans (or chapter spans / section spans for DOCX) that satisfy the offset-fidelity invariant. |
| Per-chunk token count | C5 writes `tokens=NULL` (column nullable); per ADR 0006 token counts are computed alongside embeddings, which means C6 owns this | **C6** (alongside embeddings). The tokenizer choice is coupled to the embedding model choice (most providers tokenize via tiktoken or a model-specific BPE). C6's embedding-model decision drives the tokenizer. |
| Operator re-ingest CLI | A future `python -m app.cli reingest --file <id>` (or `--all-failed`) for operator-driven re-ingestion of files | Not strictly needed for M1 — operators can `UPDATE files SET ingestion_status='pending' WHERE ...` against the database directly, and the worker's startup sweep picks it up on the next worker restart. The CLI affordance is convenience-only; deferred to **D-phase** or later as operator-side experience guides demand. |

### Deferred to **C3** (chat service + message persistence)

| Item | Surface | Notes |
|---|---|---|
| FK constraints on `inference_routing_log.chat_id` and `.message_id` | A2's `0001_initial.py` notes this | The columns are nullable UUIDs without FKs in 0001; a future migration ALTERs to add the FK constraints once `chats` and `messages` tables exist (which is C3). |

### Deferred to **C-phase (skill execution generally)**

| Item | Surface | Notes |
|---|---|---|
| Bidirectional tool-call translation in Anthropic adapter | B3's `anthropic.py` translates `role: tool` → `tool_result`; assistant tool_use is one-way | **C2 scope-check, 2026-05-08:** none of the 11 starter skills declare `tools:` in their frontmatter, so C2 ships without exercising bidirectional tool-call translation. Stays deferred. Most natural successor is C3 (chat persistence forces the tool-call/tool-result message-shape question end-to-end), or whichever later C-phase task brings up a skill that declares tools. |

### Deferred to **D1** (tier-floor enforcement / refusals)

| Item | Surface | Notes |
|---|---|---|
| HTTP 403 `tier_below_minimum` refusal logic | The error code is in the gateway-openapi.yaml enum; B4 writes the tier annotation but doesn't refuse | D1 implements refusal at all three tier-floor sources (skill frontmatter, Project setting, request override). |

### Deferred to **D2** (Inference Tier Awareness UI)

| Item | Surface | Notes |
|---|---|---|
| OpenWebUI fork visual branding | A5 partial — env vars set, no Svelte changes yet | Per ADR 0001 license clause 4: dual-branding (LQ.AI alongside Open WebUI), not replacement. D2 is already touching the OpenWebUI shell to add the tier badge — natural place to also land branding. |
| OpenWebUI fork delegated auth wiring | A5 partial — backend serves /api/v1/auth/login, but the OpenWebUI default login form doesn't yet POST there | Folds into D2 or its own UI task. The Svelte component change is small once the visual approach is decided. |

### Deferred to **D5** (MFA enrollment + verification)

| Item | Surface | Notes |
|---|---|---|
| TOTP enrollment + verify endpoints | B1 left `/auth/mfa/setup` and `/auth/mfa/verify` as 501 stubs; the 423-with-mfa_token entrypoint exists | D5 implements the actual TOTP flow with `pyotp`. |

### Deferred to **D6** (per-user export + delete)

| Item | Surface | Notes |
|---|---|---|
| `/users/me/export` and `/users/me/delete` | A4/B1 left these as 501 stubs | D6 is the GDPR Article 17/20 work. |

### Deferred to **PRD §9 — DE-XXX entries** (not assigned to a specific M1 task)

| Item | Notes |
|---|---|
| **Refresh-token bcrypt scan is O(active_sessions)** | B1's note. Fine at v1 scale (a few devices per user). If it becomes hot, a deterministic HMAC lookup column would index it. Worth filing as DE-XXX in PRD §9 next time we update the deferred-enhancements list. |
| **UUIDv7 instead of v4** | A2 used v4 (`gen_random_uuid()` from pgcrypto, built-in to Postgres 16). v7 would give time-ordered insertion ordering but needs the third-party `pg_uuidv7` extension. Document migration path: a future migration can swap to v7 when Postgres 17 is available or when the ordering optimization is justified. |
| **`max_tokens` configurable per-model ceiling** | B3 hardcodes 4096 as the Anthropic default when OpenAI clients omit max_tokens. Operators may want a per-model configurable ceiling. |
| **OpenWebUI rebase to upstream** | ADR 0001 specifies quarterly. Not due until 2026-08. |

### Deferred infrastructure tracking

| Item | Notes |
|---|---|
| Worktree GC | The Claude Code harness still considers some agent worktrees "owned" — they don't auto-clean. `git worktree list` shows them; `git worktree remove --force` requires `-f -f` per git's safety mechanism. Cosmetic, not blocking. |
| Dockerfile installs metadata-only wheel | `api/Dockerfile`'s `pip install --no-cache-dir .` runs before `COPY app/ ./app/`, so the installed wheel has no source files (the metadata installs and the source is imported via WORKDIR=/app). `python -m app.cli` works; `[project.scripts]` console-scripts do not because their stub-script imports `app.cli` from site-packages. Out of scope to fix in B2; documented inline in `api/pyproject.toml`. |

---

## Operational notes for the next session

These are project-specific quirks worth knowing before the next session resumes:

### Local environment

- **Working directory:** `/Users/kevinkeller/Desktop/LegalQuants/inhouse-ai` (still using the old name; project itself is LQ.AI). Don't rename until you're ready for the cascade of `cd` muscle-memory updates.
- **Host-side Postgres collision.** The user's machine has a host-level Postgres on `localhost:5432` (looks like Anaconda's bundled). Compose maps postgres to host port `5432` by default; this loses the race when binding both. **Workaround:** set `POSTGRES_HOST_PORT=5433` in `.env` for any host-side test runs. Tests that go through `docker compose exec` (e.g., `make migrate`) are unaffected.
- **Python venvs:** `api/.venv` and `gateway/.venv` are gitignored, populated via `make install` (or per-subsystem `make install-api` / `make install-gateway`). When pyproject.toml deps change, re-run install.

### Generating an .env from the example

```bash
cp .env.example .env
# Generate the four required secrets:
PASS_PG=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
PASS_MINIO=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
KEY_GW=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
SECRET_JWT=$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')
# (BSD sed needs '' after -i on macOS)
sed -i '' "s|^POSTGRES_PASSWORD=$|POSTGRES_PASSWORD=${PASS_PG}|" .env
sed -i '' "s|^MINIO_ROOT_PASSWORD=$|MINIO_ROOT_PASSWORD=${PASS_MINIO}|" .env
sed -i '' "s|^LQ_AI_GATEWAY_KEY=$|LQ_AI_GATEWAY_KEY=${KEY_GW}|" .env
sed -i '' "s|^JWT_SECRET=$|JWT_SECRET=${SECRET_JWT}|" .env
sed -i '' 's|^POSTGRES_HOST_PORT=5432|POSTGRES_HOST_PORT=5433|' .env  # host-postgres workaround
```

### Running the test DB-backed tests from host venv

```bash
PG_PASS=$(grep "^POSTGRES_PASSWORD=" .env | cut -d= -f2)
DATABASE_URL="postgresql+asyncpg://lq_ai:${PG_PASS}@localhost:5433/lq_ai" \
  api/.venv/bin/pytest api/tests/
```

### Running the full stack

```bash
docker compose up -d            # all 6 services
make migrate                    # apply 0001_initial.py
docker compose down -v          # clean teardown (drops volumes)
```

### Provider-marked tests (real keys, gated)

```bash
ANTHROPIC_API_KEY=sk-... gateway/.venv/bin/pytest gateway/tests/ -m provider
```

---

## Next-session first move

When you resume:

1. **Check git status is clean** and you're at HEAD of origin/main:
   ```bash
   git status   # expect: "nothing to commit, working tree clean"
   git log -1 --oneline   # expect the C7 progress-doc commit (or the merge commit)
   ```
2. **Read this doc top to bottom** to recover state.
3. **C-phase wave-2 partially landed.** C7 (Projects) is done, alongside C1 + C4 from wave-1. The matter-scoped resource model is in place: projects, file/skill attachments, free-form context, the privileged constraint enforced at three layers, slug uniqueness with collision suffixing. The C4 deferred items (`files.project_id` FK + multipart `project_id` form field) are closed. End-to-end inference path is wired (B5); skills are loaded into a backend in-memory registry with SIGHUP-driven atomic-swap reload; file upload/metadata/download/soft-delete is end-to-end against MinIO with streaming I/O, SHA-256 content addressing, and a 100 MB cap. The cross-cutting `lq_ai.errors` hierarchy is in place (ADR 0003).
4. **Remaining C-phase wave-2 tasks.** C2 (prompt assembly — gateway-side; reads skill content from backend over HTTP per ADR 0004), C3 (chat persistence — removes the "stateless pass-through" caveat from B5; also closes the deferred FK on `inference_routing_log.chat_id`/`message_id`), C5 (document pipeline + character-precise offsets — depends on C4, load-bearing for M2 citation engine), C6 (KB hybrid retrieval — depends on C5), C8 (web UI chat — depends on C3). C3 is the keystone task and runs after C2 and C5 land.
5. **B6 is optional** for M1 baseline — recommended order is OpenAI first (largest user base), then Ollama (Mode 2 unlock), then Vertex/Bedrock. Ollama specifically is the Mode 2 (air-gapped local inference) unlock.

That's it — clean continuation.

---

*This document is updated at session boundaries. See `docs/M1-IMPLEMENTATION-ORDER.md` for the canonical task specs; this is the running ledger.*
