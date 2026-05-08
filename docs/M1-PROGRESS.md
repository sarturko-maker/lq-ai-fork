# M1 Build Progress

> **Living status for the M1 build.** Updated at every session boundary or significant milestone. Pair this with `docs/M1-IMPLEMENTATION-ORDER.md` (which has the per-task spec, scope, and verification criteria) — this doc tracks what's *done* against that plan and what's *deferred* with explicit owning tasks.
>
> **Last updated:** 2026-05-07 (end of session 2; B1 + B3 just landed)
> **Repo:** [github.com/LegalQuants/lq-ai](https://github.com/LegalQuants/lq-ai) (origin/main is in sync)
> **Local working dir:** `/Users/kevinkeller/Desktop/LegalQuants/inhouse-ai` (project renamed from InHouse AI to LQ.AI on 2026-05-07; local directory not yet renamed)

---

## Snapshot

| Phase | Done | In progress | Next |
|---|---|---|---|
| A — Foundation scaffolding | A1, A2, A3, A4 | A5 (partial — env-var branding only) | — |
| B — Core authentication and routing | B1, B3 | — | **B2 + B4 next (parallel)** then B5; B6 optional |
| C — Capability layer | — | — | After B5 |
| D — M1 differentiators | — | — | After C |
| E — Procurement and release | — | — | After D |

**Tests:** 51 passing in api/ (28 skipped pending DATABASE_URL); 57 passing in gateway/ (1 skipped pending ANTHROPIC_API_KEY).
**Stack:** `docker compose up` brings 6 services (postgres, redis, minio, gateway, api, web) to healthy in ~30s.
**Migration:** `make migrate` applies `0001_initial.py` cleanly; reversible.

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

### B3 — Anthropic provider adapter (gateway) ✅

ProviderAdapter abstract base + Pydantic OpenAI schema (with LQ.AI extensions: routed_inference_tier, routed_provider, cost_estimate, anonymization_applied). AnthropicAdapter translates OpenAI Chat Completions ↔ Anthropic Messages format (system-message extraction, stop-reason mapping, token-usage translation, streaming SSE chunk translation). Hand-rolled httpx — no `anthropic` SDK dep per PRD §4. Wired into inference.py with B3-temporary "Anthropic-only" routing (B4 replaces with the real router).

22 unit tests + 7 integration tests (respx-mocked) + 1 @provider real-key test (skipped without ANTHROPIC_API_KEY).

End-to-end verification: 503 `provider_unavailable` confirmed when no key is set; real-key verification deferred to operator.

---

## Tasks ahead

### B2 — First-run admin user setup (next, ~2-3h)

**Depends on:** B1.

**Scope:** On first start, create admin user with a randomly generated password. Print password to API container logs (matching the quickstart's expected behavior). Force password change on first login.

**Verification:** Fresh deployment → admin password in logs → login → forced password change → permanent password works.

**Notes for the agent:**
- B1 has the `User` model and password-hashing utilities ready
- "First start" detection: check if any user exists with `is_admin=True`; if not, create one
- Print to logs (don't email) — matches quickstart and operator expectation
- Forced password change: store a flag like `must_change_password=True` on the user (likely needs a new column on `users` via a migration), or stash a one-time JWT claim
- Quickstart text references `python -m lq_ai.cli reset-admin-password` (docs/quickstart.md:325) — that CLI doesn't exist yet; flag whether to land it now or as a follow-up

### B4 — Gateway router + alias resolution + tier derivation (parallel with B2, ~5-7h)

**Depends on:** B3 (adapter template).

**Scope (per the M1-IMPLEMENTATION-ORDER amended in session 1):**
- Replace B3's "Anthropic-only" routing with the real router that resolves model aliases (`smart` → `claude-opus-4-7`) and dispatches to the right adapter
- **Tier derivation lives here, not in D1.** Annotate every routed request with `routed_inference_tier` (1-5) derived from the resolved provider/model + gateway.yaml's `inference_tiers.defaults` block. Include the tier in response metadata (header or body field) so the backend doesn't re-derive. Write to every `inference_routing_log` row.
- Per-skill / per-Project tier-floor enforcement (refusing requests below a declared minimum with HTTP 403 and `tier_below_minimum` error code) is **split out to D1** — that lives there because it's the application of the data, not the data path itself.
- Fallback chain skeleton (provider A fails → try B); not exercised until B6 lands additional providers, but the structure should be in place.

**Why tier derivation lives here, not D1:** the data path runs through this task and B5. Doing tier derivation later means backfilling through gateway → backend → DB → UI. Doing it here keeps the audit log and message rows correct from the first inference call.

### B5 — Backend ↔ Gateway integration (~4-6h)

**Depends on:** A4 (gateway client stub), B4 (real routing).

**Scope:** Backend has a gateway client that calls the gateway with the gateway API key. Backend chat endpoint stub now calls through the gateway and returns the response. End-to-end inference path: backend → gateway → Anthropic → response.

**Notes:**
- A4 already drafted `api/app/clients/gateway.py` with a `GatewayClient` skeleton + `health_check()` method. B5 fleshes out the actual call methods (chat_completion, embeddings).
- Persistence of inference_routing_log entries: B4 writes them gateway-side; B5 needs to ensure the backend doesn't double-write. Probably the gateway is the canonical writer.
- This is also where the `lq_ai.errors` package would naturally land (cross-cutting backend↔gateway error semantics) — see deferred items.

### B6 — Additional provider adapters (optional)

**Depends on:** B3 (template).

**Scope:** OpenAI, Vertex (Anthropic on Vertex), Bedrock, Ollama. Optional for M1 baseline; **Ollama is critical for Mode 2** (air-gapped local inference). The other three are recommended for breadth.

**Per provider:** ~3-4h following B3's adapter template.

---

## Deferred items (cataloged with owning tasks)

These were flagged during execution but deliberately deferred. Each has an owning task — when that task lands, it pulls the deferred item with it. **Per Kevin's standing instruction: address tech debt along the way; don't foist on the community.**

### Deferred to **B2** (first-run admin)

| Item | Surface | Notes |
|---|---|---|
| `lq_ai.cli reset-admin-password` CLI | quickstart.md:325 references it; doesn't exist yet | Decide whether to land in B2 or as a follow-up. If B2, it's a small `argparse` script that connects to the DB and resets the admin password. |

### Deferred to **B4** (gateway router + tier derivation)

| Item | Surface | Notes |
|---|---|---|
| Replace B3's Anthropic-only routing | `gateway/app/api/inference.py` has a comment marking the temp routing | B3 documented this inline. B4's first move is replacing the routing logic. |
| `inference_routing_log` writer | `gateway/app/api/inference.py` (currently doesn't write to the log) | The Tier-Derivation choke point is the right place to write. Schema is already in place from A2. |
| Fallback chain on provider failure | gateway.yaml.example has `fallback:` blocks; not yet exercised | Skeleton in B4; real activation when B6 lands more providers. |

### Deferred to **B5** (backend ↔ gateway integration)

| Item | Surface | Notes |
|---|---|---|
| `lq_ai.errors` exception hierarchy | CONTRIBUTING.md references it; doesn't exist yet | Both B1 and B3 noted it. B5 is where backend↔gateway error semantics need to align — natural landing spot. Cross-cutting; lives in a shared module that both `api/` and `gateway/` import from. |
| Real `GatewayClient` chat_completion / embeddings methods | A4's stub in `api/app/clients/gateway.py` | A4 only built health_check(); B5 builds the rest. |

### Deferred to **C3** (chat service + message persistence)

| Item | Surface | Notes |
|---|---|---|
| FK constraints on `inference_routing_log.chat_id` and `.message_id` | A2's `0001_initial.py` notes this | The columns are nullable UUIDs without FKs in 0001; a future migration ALTERs to add the FK constraints once `chats` and `messages` tables exist (which is C3). |

### Deferred to **C-phase (skill execution generally)**

| Item | Surface | Notes |
|---|---|---|
| Bidirectional tool-call translation in Anthropic adapter | B3's `anthropic.py` translates `role: tool` → `tool_result`; assistant tool_use is one-way | Lands when skills exercise tool-use (probably C2 or later). B3 documented inline. |

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
   git log -1 --oneline   # expect the M1-PROGRESS doc commit
   ```
2. **Read this doc top to bottom** to recover state.
3. **Scan `docs/M1-IMPLEMENTATION-ORDER.md`** for the B2 and B4 task specs (they have effort estimates and verification criteria).
4. **Spawn B2 + B4 in parallel** via `Agent` calls with `isolation: "worktree"` — same pattern as A3+A4 and B1+B3 in this session. The agent prompts should reference this doc + the implementation order + the relevant PRD sections + the deferred items each task should pull along (per the table above).
5. **After B2 + B4 land**, verify the integrated stack, then proceed to B5 (which ties them together end-to-end).

That's it — clean continuation.

---

*This document is updated at session boundaries. See `docs/M1-IMPLEMENTATION-ORDER.md` for the canonical task specs; this is the running ledger.*
