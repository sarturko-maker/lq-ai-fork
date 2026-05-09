# Session Handoff — 2026-05-08 → 2026-05-09

> **Purpose.** Resume this session in a fresh context window. Pair with `docs/M1-PROGRESS.md` (the canonical living ledger).

---

## State at handoff

- **Branch:** `main`, origin in sync.
- **Last commit:** `fd08354` *fix(web): admin alias form uses live model discovery*.
- **Stack:** `docker compose up -d` (default profile + `--profile local` for Ollama) — all 8 services healthy as of last check.
- **Auth:** `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!` (rotate when convenient).
- **Migrations applied:** `0001` → `0008`.
- **ADRs in tree:** `0001` (OpenWebUI fork pin), `0002` (backend-owned auth), `0003` (error handling), `0004` (skill-loader locus), `0005` (file-storage soft-delete + key scheme), `0006` (document pipeline), `0007` (skill prompt assembly), `0008` (embedding model + OpenAI adapter), `0009` (LQ.AI web shell coexistence), `0010` (gateway config hot-reload).

---

## What's done

| Phase | Status |
|---|---|
| **A** scaffolding | ✅ all 5 (A5's deferred branding + delegated-auth wiring closed under LQ.AI shell at `/lq-ai` per ADR 0009) |
| **B** auth + routing | ✅ B1–B5; **B6 partial** (Ollama adapter only — OpenAI/Vertex/Bedrock chat completions still deferred) |
| **C** capability layer | ✅ all 8 |
| **D0** model availability + picker | ✅ done — gateway `/v1/models` merges aliases + Ollama `/api/tags` + Anthropic catalog; raw `provider/model` passthrough; LQ.AI shell composer picker |
| **D0.5** admin alias UI | ✅ done — `/lq-ai/admin/models` page, atomic-swap config holder, hot-reload, RW gateway-config volume, alias-tier surfaced on `/v1/models` |

## What's NOT done

- **D-phase wave-1**: D1 (tier-floor refusals), D5 (MFA), D6 (GDPR export/delete). All unblocked. Recommended to spawn in parallel.
- **D-phase wave-2**: D2 (tier UI deeper than C8 badge), D3 (audit log privilege fields), D4 (Organization Profile), D7 (Saved Prompts).
- **B6 remainder**: OpenAI / Vertex / Bedrock chat completions adapters.
- **Phase E**: compliance pack mappings, release packaging.

---

## Smoke-test session — 8 real bugs caught and fixed inline

1. `skills/` not mounted into api container — added `./skills:/skills:ro` volume.
2. All ports bound to `0.0.0.0` (DigitalOcean IP scanned 8000) — `*_BIND_ADDR` defaults to `127.0.0.1`.
3. C3 FK ordering race against B4 routing-log writes — migration `0008` drops the FKs.
4. C4 `LogRecord.filename` collision via `extra={"filename": ...}` — renamed to `upload_filename`.
5. Docling first-run model download blocked uploads — `ingest-hf-cache` and `ingest-easyocr-cache` named volumes persist across restarts.
6. No CORS on api/ for cross-origin browser dev — env-driven `LQ_AI_CORS_ORIGINS`.
7. C8 client relative `/api/v1` broke cross-origin dev — switched to `import { PUBLIC_LQ_AI_API_BASE_URL } from '$env/static/public'` with the value baked into `.env` at Docker build via `RUN printf > .env`.
8. Stale Docker images blocked C-phase migrations / C8 routes — rebuild any service whose code changed.

End-to-end inference verified: Anthropic (Tier 4) + Ollama (Tier 1) round-tripped through backend chat → gateway router → adapter → audit log → SSE streaming → LQ.AI UI. Receipts in `inference_routing_log` and `messages` tables.

---

## Open question for next session — model picker UX

User flagged that the **D0.5 admin alias form's model dropdown shows only the in-Compose Ollama's pulled models** (one model: `llama3.1:8b`). Two distinct issues nested here:

- **Compose vs host Ollama.** `OLLAMA_BASE_URL=http://ollama:11434` points the gateway at the in-Compose service, which has only what we explicitly `ollama pull`'d. The user's host machine has more models. Quick fix (operator-side): set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env` and restart gateway.
- **Picker UX still feels like a hardcoded list.** User offered to share an example code pattern they'd prefer; **defer the rebuild until they do**. Don't try to redesign without their pattern in hand. The current implementation pulls dynamically from D0's `/v1/models`, but the user's reaction was UX-grounded (the affordance feels static); listen for their pattern before making changes.

---

## How to resume next session

1. `cd /Users/kevinkeller/Desktop/LegalQuants/inhouse-ai`
2. `git pull origin main` and verify HEAD is `bb41f8f` or later.
3. `docker compose ps` — if not all-healthy, `docker compose up -d`.
4. Read `docs/M1-PROGRESS.md` and this handoff doc.

### Note for next session — D1 agent already in flight

The previous session accidentally spawned a D1 agent (worktree `worktree-agent-a3cec7b630131a9e6`) before the user redirected to "let next session run D." Two scenarios:

**(a) The D1 agent finished while no session was open.** Check for the worktree on disk: `git worktree list | grep a3cec7b6`. If it's there with commits ahead of main, treat it like any other completed agent worktree — verify, ff-merge or rebase, run static checks + tests, push.

**(b) The D1 agent is still running.** Background tasks may not survive cleanly across session boundaries; if no completion notification arrived, check `docker compose logs` and the agent's output file at `/private/tmp/claude-501/-Users-kevinkeller-Desktop-LegalQuants-inhouse-ai/.../a3cec7b630131a9e6.output`. If incomplete, ABORT and re-spawn freshly.

Either way: do NOT spawn D5 + D6 until D1's state is resolved.

5. **Wait for the user's example code** for the model-picker UX pattern before touching `web/src/routes/lq-ai/admin/models/+page.svelte` or `web/src/lib/lq-ai/components/AliasForm.svelte`. The picker UX is deferred per the user's explicit "model picker can wait until D is done" decision.
6. **Then** spawn D-phase wave-1 remainder (D5 + D6) in parallel worktrees, after D1 is merged. Surfaces don't overlap.

---

## D-phase wave-1 brief (already drafted in conversation; condensed here)

- **D1** — Tier-floor enforcement. Gateway refuses requests below `minimum_inference_tier` (skill frontmatter / project setting / request override) with 403 `tier_below_minimum`. Logs `refused: true`. Backend translates. ~3–4h.
- **D5** — MFA TOTP. `/auth/mfa/setup`, `/auth/mfa/verify`, recovery codes, login flow detects `mfa_enabled` and returns 423. ~6–8h.
- **D6** — GDPR. `/users/me/export` ZIPs all user data; `/users/me/delete` schedules deletion with grace period (default 30d, configurable for testing). ~6–8h.

Surfaces don't overlap: D1 = gateway + api/chats.py, D5 = api/auth.py + user model migration, D6 = api/users.py + delete worker. Each has its own migration if needed (next available is `0009`).

---

## Things that should NOT regress

- Anthropic key in `.env` is real — DO NOT overwrite it when generating a fresh `.env`.
- `POSTGRES_HOST_PORT=5433` (documented default — host postgres collision was tidepool, currently down).
- `LQ_AI_CORS_ORIGINS=http://localhost:3000` (local dev only; production: leave unset).
- `PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1` (local dev; production: relative `/api/v1`).
- Gateway-config writable named volume `gateway-config` mounted at `/etc/lq-ai` — first-boot init copies from `gateway.yaml.example`; admin edits via UI persist there.
- 4 pre-existing `B017 pytest.raises(Exception)` ruff warnings in `test_migrations.py` — pre-date M1; leave alone unless a contributor wants to narrow them.
