# Session Handoff — 2026-05-09 (afternoon → next session)

> **Purpose.** Resume in a fresh context window. Pair with `docs/M1-PROGRESS.md` (the canonical living ledger). This is the second handoff for 2026-05-09 — the morning handoff (`SESSION-HANDOFF-2026-05-09.md`) covered D5/D6/D3-core/D4-backend; this one covers D4-coverage.

---

## State at handoff

- **Branch:** `main`, ahead of origin until pushed (see "Push status" below).
- **Last commit before this session's work:** `cef4560` *docs: handoff updated for D4 backend landing + D4-coverage scope*.
- **D4-backend (4 commits):** ✅ committed locally last session, **not yet pushed**.
- **D3-core (5 commits):** ✅ pushed mid-morning session.
- **D4-coverage:** ✅ implemented and verified end-to-end this session, **not yet committed** at handoff time (decide before next session whether to bundle or split).
- **Stack:** `docker compose up -d` — all services healthy. Both `api` and `gateway` containers were rebuilt this session with the D4-coverage code; the live `api` container at `lq-ai-api-1` and `lq-ai-gateway-1` are serving the new endpoints.
- **Auth:** `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!`.
- **Migrations applied (live DB):** `0001` → `0010`. Migration `0010` (organization_profile) was applied this session — the prior handoff's claim of "0001 → 0009 applied" was off by one.
- **ADRs in tree:** unchanged.
- **Live Profile state:** the smoke-test Profile is set on the live deployment ("## Org Profile (smoke test) — We always recommend Delaware as choice of law."). Clear with `PUT {"content_md":""}` if you want a fresh-deployment posture.

---

## What landed in this session

| Phase | Status | Surface |
|---|---|---|
| **D4-coverage** Wave-2: gateway-side prompt-assembly hook | ✅ implemented + verified end-to-end | api + gateway + tests + docs |

**The one big thing.** D4 verification step now passes. The full path is wired: admin PUTs the Profile → backend stores in `organization_profile` table → gateway fetches via `/internal/organization-profile` → prompt assembler prepends Profile body to skill sections (unless skill opts out via `lq_ai.use_organization_profile: false`) → upstream LLM receives Profile content as part of the system prompt. Live token-count differential confirms: same chat with vs. without Profile, prompt_tokens grows by exactly the Profile's token count.

**Files touched (D4-coverage).**

* `api/app/api/internal.py` — new `GET /api/v1/internal/organization-profile` handler.
* `gateway/app/clients/backend.py` — `BackendClient.get_organization_profile()` + `ORGANIZATION_PROFILE_CACHE_KEY` sentinel.
* `gateway/app/skills/assembler.py` — `consumes_organization_profile()` helper + Profile-aware `assemble_skill_prompt`.
* `gateway/app/skills/__init__.py` — export the new helper.
* `gateway/app/api/inference.py` — Profile fetch added to `_apply_skill_prompt_assembly`.
* `docs/api/backend-openapi.yaml` — `/api/v1/internal/organization-profile` path documented.
* `docs/M1-PROGRESS.md` — D4 marked fully complete.
* Tests: `gateway/tests/test_skill_assembler.py` (+9), `gateway/tests/test_backend_client.py` (+7), `gateway/tests/test_inference_skill_assembly.py` (+3 + helper refactor), `gateway/tests/test_inference_tier_floor.py` (default 404 stub for backward compatibility), `api/tests/test_internal_skills.py` (+6), `api/tests/test_endpoints.py` (route promoted to `IMPLEMENTED_ROUTES`), `api/tests/test_openapi.py` (path-count 45 → 46 + new entry in `EXPECTED_PATHS`).

**Test posture at end-of-session.**
- Gateway: 343 passed, 1 skipped (excluding `test_routing_log_db.py` which needs Postgres).
- API: 36 passed across the 4 touched files; 2 pre-existing `admin/tier-policy` failures remain (D1 deferred surface, predate D4-coverage).

**Architectural decisions worth surfacing.**

1. **404 + empty content treated identically.** The internal endpoint returns 404 both when the row doesn't exist and when its body is whitespace-only. The gateway only branches on "Profile present vs absent"; there's no value in distinguishing "never set" from "explicitly cleared" at the prompt-assembly layer.
2. **Profile rendered once at top, not per-section.** PRD §3.12 / morning handoff loosely described "prepend to each attached skill's section." We landed on once-at-top because the upstream LLM sees a single concatenated system prompt — toggling Profile presence per skill section isn't meaningful at the API level, and per-section repetition would multiply the Profile's token cost. All-opt-out still correctly omits the Profile entirely. The contract is pinned by `test_assemble_includes_profile_when_at_least_one_skill_opts_in`.
3. **404 path NOT cached.** Skill-cache hits on the Profile sentinel only when the body fetch returned 200. An operator's first PUT lands in the next chat (no waiting for cache TTL on the absence path). The trade-off: an extra HTTP round-trip per chat during the no-Profile-yet phase of a deployment, which is fine — intra-cluster, ms-scale.
4. **Default opt-in.** `consumes_organization_profile(skill)` returns `True` when the skill's frontmatter doesn't mention `use_organization_profile`. PRD §3.12 says the Profile is automatic; opting out should be the explicit signal, not the default.
5. **Helper test-file ergonomics.** `_mock_backend_skill` in `test_inference_skill_assembly.py` was extended to auto-register a default 404 stub for the Profile endpoint (so existing tests that don't care about the Profile see "no Profile set" and behave identically). Tests that want a present Profile call `_mock_backend_org_profile` *after* `_mock_backend_skill` — respx's "last route registration wins" semantics applied. The `test_inference_tier_floor.py` `_mock_skill` helper was updated identically.

---

## What's NOT done

### Wave-2 remaining

- **D7** (Saved Prompts per Issue 04) — `/api/v1/saved-prompts` CRUD + sidebar UI + Promote-to-Skill affordance. **Dependencies:** C8 ✅. **Effort:** 4–6h.
- **D2** (Inference Tier Awareness UI) — web/ work; tier badge in chat header showing routed tier (1–5), click for details panel. **Dependencies:** D1 ✅ + C8 ✅. **Effort:** 4–6h.
- **D3-coverage** — auth/MFA/projects/files/KBs audit writes + retroactive backfill + admin filtering UI. **Effort:** ~6–10h. Scope unchanged from prior handoff.

### B6 remainder + Phase E

Unchanged: OpenAI / Vertex / Bedrock chat completions adapters; Phase E compliance pack mappings + release packaging.

### Push status

- **D4-backend (4 commits)** + **D4-coverage (this session's work, not yet committed)** are the next push.
- **Recommendation:** commit D4-coverage as 4–5 atomic commits (backend internal endpoint, gateway client, assembler helper, prompt-assembly hook, tests/docs), then push the whole D4 stack together. The verification step passes end-to-end; pushing as one coherent surface is honest about the state.
- The D4-backend commits already include test files + handoff updates that reference D4-coverage as in-flight; pushing D4-backend without D4-coverage would briefly leave `M1-PROGRESS.md` saying "verification step doesn't pass" while the live code makes it pass. Better to push the whole stack.

---

## How to resume next session

1. `cd /Users/kevinkeller/Desktop/LegalQuants/inhouse-ai`
2. **Decide on commit/push strategy first** (see "Push status" above), then commit + push the D4-coverage work.
3. `docker compose ps` — all services should still be healthy (no rebuild needed; the in-flight image already has D4-coverage code).
4. Read `docs/M1-PROGRESS.md` D4 section (now reflects the full picture) and this handoff.
5. **Pick the next move:**
   - **D7 Saved Prompts** (~4–6h) — backend CRUD + sidebar UI + Promote-to-Skill. Tied to a specific tracked issue (Issue 04).
   - **D3-coverage** (~6–10h) — extends audit-log writes across auth/projects/files/KBs/MFA. Biggest scope but distributed (easy to commit incrementally).
   - **D2 Tier UI** (~4–6h) — pure web/ work; different mode entirely.

---

## Things that should NOT regress

(Carry-forward from prior handoff; D4-coverage didn't introduce new risks.)

- `OLLAMA_BASE_URL` should point at host Ollama unless `--profile local` is intentionally active.
- Anthropic key in `.env` is real — DO NOT overwrite it when generating a fresh `.env`.
- `POSTGRES_HOST_PORT=5433` (the host postgres collision was tidepool, currently down).
- `LQ_AI_CORS_ORIGINS=http://localhost:3000` (local dev only; production: leave unset).
- `PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1` (local dev; production: relative `/api/v1`).
- Gateway-config writable named volume `gateway-config` mounted at `/etc/lq-ai`.
- 4 pre-existing `B017 pytest.raises(Exception)` ruff warnings in `test_migrations.py` — pre-date M1; leave alone.
- Pre-existing test failures on main HEAD (predate D4-coverage):
  - `tests/test_endpoints.py::test_endpoint_returns_canonical_501_body[GET /api/v1/admin/tier-policy]`
  - `tests/test_endpoints.py::test_endpoint_returns_canonical_501_body[PATCH /api/v1/admin/tier-policy]`
  - These are the D1 deferred admin endpoints; clear when D1 follow-on lands.
  - 13+ chats_skills_forwarding / pipeline_ingest / skill_loader / migrations / health failures — environmental / fixture drift, predate D3-core. Don't add to that pile.

---

## Disk-pressure incident (one-time, resolved)

Mid-session, the Docker Desktop VM disk filled up enough that minio crashed with "Storage reached its minimum free drive threshold" and api couldn't start (minio dependency-failed). Root cause: 64GB of dangling/unused Docker images accumulated across several projects on this machine.

**Resolution:**
1. `docker image prune -f` reclaimed only 600MB (only truly `<none>` dangling images count).
2. `docker rmi inhouse-ai-web inhouse-ai-api inhouse-ai-gateway` — 6.5GB of stale tags from before the project rename to `lq-ai`. Layer-shared so the actual disk freed was small (~600MB), but enough to clear minio's threshold after a hard restart.
3. `docker compose stop minio && docker compose rm -f minio && docker compose up -d minio` — minio came back healthy; api could then start cleanly.

**For next session.** The Docker VM is currently at ~62% used (45GB free) but image count is still high. A future cleanup of the other-project images (`tidepool-*`, `livingworlds-*` / `living_worlds-*` underscore duplicates, `seldonsandbox-*`, `cognitive-partner-*`, etc.) would reclaim much more — probably ~50GB. **Defer until you have time to inspect each project's current relevance**; this session preserved Kevin's standing rule of "don't run destructive cleanups without authorization."
