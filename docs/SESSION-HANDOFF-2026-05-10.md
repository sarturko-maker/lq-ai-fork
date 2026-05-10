# Session Handoff — 2026-05-10 (D7 Saved Prompts)

> **Purpose.** Resume in a fresh context window. Pair with `docs/M1-PROGRESS.md` (the canonical living ledger). This handoff covers the D7 Saved Prompts wave; prior handoff is `SESSION-HANDOFF-2026-05-09b.md` (D4-coverage).

---

## State at handoff

- **Branch:** `main`. D7 commits are local; **not yet pushed** (decide push timing — see below).
- **Last commit before this session:** `22f5999` *test(d4): D4-coverage tests, OpenAPI sketch, progress + handoff*.
- **D7 stack (commits below):** ✅ implemented + tested + live-verified end-to-end on backend; web UI typecheck-clean and unit-tested but **not browser click-tested** this session.
- **Stack:** `docker compose up -d` — all services healthy. The `api` container was rebuilt this session with the D7 code; the live container at `lq-ai-api-1` is serving the new endpoints.
- **Migrations applied (live DB):** `0001` → `0011`. Migration `0011` (saved_prompts) was applied via `docker cp 0011*.py … && alembic upgrade head` before the container rebuild, then survived the rebuild.
- **Auth (smoke-test admin):** `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!`.
- **ADRs in tree:** unchanged.

---

## What landed in this session

| Phase | Status | Surface |
|---|---|---|
| **D7** Saved Prompts CRUD | ✅ implemented + verified end-to-end (backend) | api + web client + sidebar UI + tests + docs |

**The one big thing.** D7 saved-prompts CRUD is a real surface. `POST /auth/login` → `POST /saved-prompts {…}` → `LIST` → `GET /{id}` → `PATCH` → `DELETE` → `LIST` empty all green against the live container with migration 0011 applied. The web SavedPromptsPanel sits in the chat shell between SkillPicker and the composer textarea, with quick-Insert (appends to composer rather than replacing — supports stacking on an in-progress message), edit/delete, and "Save as skill" (downloads a SKILL.md draft).

**Files touched (D7).**

* `api/alembic/versions/0011_create_saved_prompts.py` (new) — table per `docs/db-schema.md`; `(user_id, updated_at DESC)` btree + gin on `tags`; reuses `set_updated_at()` trigger from migration 0001.
* `api/app/models/saved_prompt.py` (new), `api/app/models/__init__.py` updated.
* `api/app/api/saved_prompts.py` — replaces A4 501 stubs with full CRUD. List uses `(updated_at DESC, id DESC)` for deterministic ordering under `now()`-aliasing.
* `api/tests/test_saved_prompts.py` (new) — 20 integration tests.
* `api/tests/test_endpoints.py` — five routes promoted to `IMPLEMENTED_ROUTES`; route-inventory bound `>= 5` → `>= 1` (D7 was the last wave-2 stub-eater).
* `api/tests/test_admin_bootstrap.py` — gate-clear assertion `501` → `200 + []`.
* `web/src/lib/lq-ai/api/savedPrompts.ts` (new), `web/src/lib/lq-ai/api/index.ts` updated, `web/src/lib/lq-ai/types.ts` updated (+`SavedPrompt`, `SavedPromptCreate`, `SavedPromptUpdate`).
* `web/src/lib/lq-ai/components/SavedPromptsPanel.svelte` (new), `web/src/routes/lq-ai/+page.svelte` mounts the panel.
* `web/src/lib/lq-ai/__tests__/saved-prompts-api.test.ts` (new) — 8 vitest cases.
* `docs/M1-PROGRESS.md` — new D7 section + D8 entry under "Tasks ahead"; snapshot table updated; "Last updated" line refreshed.
* `docs/M1-IMPLEMENTATION-ORDER.md` — D7 spec amended (Promote-to-Skill posture); new D8 spec (DB-backed user/team skills + Skill Creator).

**Test posture at end-of-session.**
- API: 20/20 saved-prompts integration tests + 17 admin-bootstrap. Pre-existing `admin/tier-policy` 403/501 mismatches (D1 deferred) reproduce on `main` HEAD and predate D7.
- Web: 8/8 saved-prompts API client vitest cases. `npm run check` shows no D7-related typecheck errors (the 9k+ pre-existing OpenWebUI fork errors — i18n typing, etc. — are unchanged).

**Architectural decisions worth surfacing.**

1. **Promote-to-Skill posture (the big one).** PRD §9 DE-013 / Issue 04 calls for "save as skill," but ADR 0004 keeps skills filesystem-canonical for M1. There's no `POST /api/v1/skills`, no DB-backed user-scope storage, and `POST /skills/{name}/fork` is still 501-stubbed. Wiring Promote to OpenWebUI's `/workspace/skills/create` would land a skill in OpenWebUI's database — not in LQ.AI's filesystem skills — and those skills wouldn't appear in the LQ.AI chat-shell SkillPicker. To keep the affordance honest, "Save as skill" generates a SKILL.md draft (frontmatter scaffold + prompt body) and triggers a browser download; the user submits via PR or drops into their `skills/` folder. **The full LQ.AI Skill Creator surface is filed as new phase D8** (ADR amendment to 0004, migration 0012, POST/PATCH/DELETE skills, registry merge, Creator page) — multi-day work, deliberately split out so D7 ships coherently.
2. **No-op PATCH skips audit.** UI auto-save patterns can fire a PATCH per keystroke pause; auditing every "no actual change" call would flood the log without information value. The handler diffs each supplied field against current state and only writes an audit row when something changed. Real changes write `saved_prompt.update` with `changed_fields` in `details`.
3. **404 conflates "doesn't exist" with "owned by someone else".** Distinguishing them would leak the existence of other users' prompts via id-probing. Same pattern as chats and projects routers.
4. **`(updated_at DESC, id DESC)` tiebreaker.** PostgreSQL's transaction-start `now()` makes timestamp aliasing easy to hit (batch imports, fast UI flows, the test suite's SAVEPOINT-bound transactions). The `id DESC` tiebreaker keeps UI stable-key rendering deterministic without forcing `clock_timestamp()` into the trigger.
5. **Tag dedup preserves first-seen order.** Set semantics would lose ordering; full-curation would invalidate the API's normalize-on-write behavior. Preserving first-seen lets users curate display order while the backend guarantees no duplicates.

---

## What's NOT done

### D7 follow-ons / known limitations

- **Browser click-through verification of the SavedPromptsPanel.** Typecheck + vitest + live API verification all pass; the panel itself was not exercised in a browser this session. Recommend a quick smoke test in the next session before declaring the UI fully validated. The Insert / Edit / Delete / Save-as-skill / Tag input flows are the main paths to exercise.
- **Tag-filter UI / endpoint.** The DB index supports it; the API doesn't expose `?tag=` filtering yet. Cheap to add when a UI need surfaces.
- **Toast-based delete-confirm / error display.** SavedPromptsPanel currently uses `confirm()` and `alert()` to match the existing OpenWebUI fork's interaction style; a polished toast would live in the broader UI consistency pass.
- **Optimistic UI for create/update/delete.** All mutations currently re-list after success; for a tight UI feel an optimistic update could elide the round-trip. Not critical at M1 scale.

### Wave-2 remaining

- **D2** (Inference Tier Awareness UI) — web/ work; tier badge in chat header, click for details panel. **Dependencies:** D1 ✅ + C8 ✅. **Effort:** 4–6h.
- **D3-coverage** — auth/MFA/projects/files/KBs audit writes + retroactive backfill + admin filtering UI. **Effort:** ~6–10h. Scope unchanged from prior handoff.
- **D8** (NEW) — DB-backed user/team skill storage + LQ.AI Skill Creator surface. ADR amendment to 0004, migration 0012, `POST/PATCH/DELETE /api/v1/skills`, Skill Service registry merge, gateway internal-skills user-scope path, Creator page, rewire D7's Promote-to-Skill. **Effort:** 1–2 days.

### B6 remainder + Phase E

Unchanged: OpenAI / Vertex / Bedrock chat completions adapters; Phase E compliance pack mappings + release packaging.

### Push status

- **D7 stack** is the next push. Suggested split (atomic per layer):
  1. `feat(api): migration 0011 — saved_prompts table + ORM model`
  2. `feat(api): /api/v1/saved-prompts CRUD (D7)`
  3. `test(api): D7 saved-prompts integration tests + scaffold updates`
  4. `feat(web): saved-prompts API client + types (D7)`
  5. `feat(web): SavedPromptsPanel with quick-insert + Save-as-SKILL.md (D7)`
  6. `test(web): saved-prompts API client vitest`
  7. `docs(d7): M1-PROGRESS + M1-IMPLEMENTATION-ORDER + D8 phase entry`
- Push the whole stack together once committed — the verification step passes end-to-end and the docs reflect the live state.

---

## How to resume next session

1. `cd /Users/kevinkeller/Desktop/LegalQuants/inhouse-ai`
2. **Push the D7 stack** if not yet pushed.
3. `docker compose ps` — all services should still be healthy (no rebuild needed; the in-flight image already has D7 code).
4. **Browser smoke test the SavedPromptsPanel** — open `http://localhost:3000/lq-ai`, create a chat, exercise Insert / Edit / Delete / Save-as-skill / Tag input. (10 minutes.)
5. **Pick the next move:**
   - **D2 Tier UI** (~4–6h) — pure web/ work; nicely scoped.
   - **D3-coverage** (~6–10h) — distributed audit-write expansion.
   - **D8** (~1–2 days, multi-phase) — the surface that closes Issue 04 fully. ADR amendment first, then migration, then endpoints, then web Creator.

---

## Things that should NOT regress

(Carry-forward from prior handoff; D7 didn't introduce new infra.)

- `OLLAMA_BASE_URL` should point at host Ollama unless `--profile local` is intentionally active.
- Anthropic key in `.env` is real — DO NOT overwrite when generating a fresh `.env`.
- `POSTGRES_HOST_PORT=5433` (host postgres collision; tidepool currently down).
- `LQ_AI_CORS_ORIGINS=http://localhost:3000` (local dev only; production: leave unset).
- `PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1` (local dev; production: relative `/api/v1`).
- Gateway-config writable named volume `gateway-config` mounted at `/etc/lq-ai`.
- 4 pre-existing `B017 pytest.raises(Exception)` ruff warnings in `test_migrations.py` — pre-date M1; leave alone.
- Pre-existing test failures on main HEAD (predate D7):
  - `tests/test_endpoints.py::test_endpoint_returns_canonical_501_body[GET /api/v1/admin/tier-policy]`
  - `tests/test_endpoints.py::test_endpoint_returns_canonical_501_body[PATCH /api/v1/admin/tier-policy]`
  - These are the D1 deferred admin endpoints; clear when D1 follow-on lands.
  - `npm run check` shows ~9k OpenWebUI fork pre-existing errors (i18n typing, watch/+page, s/[id]/+page, auth/+page) — not D7-related; tracked separately.

---

## Live verification commands (for the next session's confidence check)

```bash
# Token from smoke-test admin
TOKEN=$(curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-smoke-test-Pw1!"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# Five-endpoint smoke
curl -sX GET http://localhost:8000/api/v1/saved-prompts \
  -H "Authorization: Bearer $TOKEN"   # → []
curl -sX POST http://localhost:8000/api/v1/saved-prompts \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Smoke","prompt_text":"body","tags":["t"]}'
# Then GET / PATCH / DELETE / GET against the returned id.
```
