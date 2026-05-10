# Session Handoff — 2026-05-10c (Option A + D3-coverage)

> **Purpose.** Resume in a fresh context window. Pair with `docs/M1-PROGRESS.md`. This is the third handoff for 2026-05-10. The morning (`SESSION-HANDOFF-2026-05-10.md`) covered D7; the afternoon (`SESSION-HANDOFF-2026-05-10b.md`) covered Wave-3 transparency. This one covers **Option A** (requested_model persistence) **+ Option B** (D3-coverage audit-write expansion). Options **C** (D8 user/team skills) and **D** (encrypted-keys ops doc) are queued for the next session.

---

## State at handoff

- **Branch:** `main`. Pushed through `ae84231` (admin audit-log filter UI).
- **Commits landed this session (all pushed):**
  ```
  ae84231 feat(web): admin audit-log filter page (D3-coverage)
  f012d6b feat(api): audit_action writes for knowledge base CRUD + attach/detach (D3-coverage)
  5f69e23 feat(api): audit_action writes for file upload + delete (D3-coverage)
  8395b22 feat(api): audit_action writes for auth + MFA endpoints (D3-coverage)
  4f26478 docs(progress): note requested_model persistence in wave-3 status
  b56738d feat(web): TierDetailsPanel surfaces requested-vs-routed delta (ADR 0011)
  db7aea3 feat(api): persist requested_model alongside routed pair (ADR 0011)
  8595064 feat(db): 0012 — requested_model on messages (ADR 0011 follow-on)
  ```
- **Stack:** all 7 services healthy; api + web rebuilt this session with the new code.
- **Auth:** `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!`.
- **Migrations:** `0001` → `0012` (0012 adds `requested_model` to messages).

---

## What landed in this session

### Option A — requested_model persistence (~1h, 3 commits + 1 docs)

| Piece | Surface |
|---|---|
| Migration 0012 | nullable `requested_model TEXT` on messages |
| ORM + schema | `Message.requested_model`; `MessageResponse.requested_model` |
| Handler | `_persist_assistant_message` accepts + stores it (both streaming + non-streaming paths) |
| Web type | `Message.requested_model?: string \| null` |
| TierDetailsPanel | renders "Requested: smart" above "Routed to: anthropic-prod/claude-opus-4-7" when they differ |

**Live verified.** `POST /api/v1/chats/{id}/messages` with `model=smart` → response `requested_model:"smart"`, `routed_model:"claude-opus-4-7"`. Direct dispatch shows a useful nuance: requesting `anthropic-prod/claude-haiku-4-5` routes to `anthropic-prod/claude-haiku-4-5-20251001` (provider date-suffix) — the panel correctly surfaces this resolution. The UI Tier-4 chip on the admin's "hello" exchange has been visually confirmed by Kevin to render the model resolution chip ("Model: smart → anthropic-prod/claude-opus-4-7 (+2 fallbacks)"); click-through verification of the TierDetailsPanel's new "Requested" row in browser is **still pending**.

### Option B — D3-coverage audit-write expansion (4 commits)

D3-core covered project / chat / message audit writes. This commit set extends to:

| Surface | Endpoints | Actions |
|---|---|---|
| **auth.py** (8 endpoints) | login, refresh, logout, change_password | `user.login` (success), `user.login_failed` (user_not_found / wrong_password), `user.login_mfa_challenged`, `user.session_refreshed`, `user.session_refresh_failed`, `user.logout`, `user.password_changed`, `user.password_change_failed` |
| **auth.py — MFA** (4 endpoints) | mfa_setup, mfa_enable, mfa_verify, mfa_disable | `user.mfa_setup_initiated`, `user.mfa_enabled`, `user.mfa_enable_failed`, `user.login` (with `mfa=true`, `via=totp\|recovery_code`), `user.mfa_verify_failed`, `user.mfa_disabled`, `user.mfa_disable_failed` |
| **files.py** (2 endpoints) | upload, delete | `file.uploaded`, `file.deleted` (privilege propagates from `project_id`) |
| **knowledge_bases.py** (5 endpoints) | create, update, delete, attach, detach | `kb.created`, `kb.updated`, `kb.deleted`, `kb.file_attached`, `kb.file_detached` (privilege propagates from KB's project) |
| **Admin filter UI** | new route | `/lq-ai/admin/audit-log` — admin-gated, six filter dimensions, cursor pagination, privileged rows highlight amber |

**Key design decisions worth surfacing:**

1. **Failure rows commit before raising.** Every state-changing handler that audits on success ALSO audits on the security-relevant failure path. Each failure adds an `audit_action()` call + `db.commit()` before the subsequent `raise HTTPException(...)`. Otherwise the FastAPI session would roll back and the audit row would never land. The wire response stays generic ("Invalid credentials"); the audit row's `details.reason` carries the disambiguating cause for operators. This is the load-bearing detail that makes the audit log useful for incident response.

2. **Privilege propagates from the project_id silently.** `audit_action()` already does a one-row Project lookup when `project_id` is supplied without an ORM instance. Files and KBs use this path so the privilege flag is set transparently — handlers don't need to fetch the project themselves just to mark the audit row.

3. **Audit-log endpoint was already live (D3-core).** Just the UI didn't exist. The new page wraps the existing `GET /admin/audit-log` filters one-to-one — no backend changes needed.

4. **Query / read endpoints out of scope.** Per the D3-coverage handoff, only state-mutating endpoints are audited. KB `query`, file `get_content`, message-list reads etc. do NOT audit. Privileged-content *access* audits are a separate phase if/when the operator security model requires read-tracking.

**Tests:**
- api: +0 new tests (audit writes ride existing surface; smoke tests cover end-to-end). 40 auth + 33 files + 24 KBs all green.
- web: +4 vitest tests for the audit-log API client (query-string encoding round-trip).
- Live verified: admin login + deliberate failed-login produced two rows in `/admin/audit-log` with full IP/UA/reason metadata captured.

**What's NOT done in B:**

- **No tests for the new audit-write call sites.** The mechanical assertion would be: do a POST, then query `audit_log` and assert one matching row exists. Easy to add per surface (~5 min each); deferred to keep this session focused on coverage breadth.
- **No retroactive backfill.** Historical events (logins / file uploads / etc. from before the wave-3 deploy) have no audit rows and never will — we can't reconstruct them. This is fine; the audit log is forward-looking from the deploy moment.
- **No projects.py / admin.py audit writes.** Out of scope per the D3-coverage handoff (those are C7 / D0.5 surfaces respectively); could be picked up as a D3-coverage-extras follow-on.
- **No browser smoke of /lq-ai/admin/audit-log.** Page builds clean, API client tests pass, but I didn't click through to confirm the table renders + filters work in browser. Quick smoke: log in as admin, navigate to `/lq-ai/admin/audit-log`, confirm the recent login row from the page-load itself shows up.

---

## What's still queued (next session)

### Option C — D8 DB-backed user/team skills (~1–2 days)

**Largest remaining item.** D7's "Save as SKILL.md" is a download stand-in; this builds the real thing.

Per the wave-3 cadence: pre-write the ADR amendment first so the migration + endpoint shapes have a north star.

Touchpoints:
* `docs/adr/0004-…-amendment.md` (new) — filesystem-canonical built-ins coexist with DB user/team scopes.
* `api/alembic/versions/0013_user_skills.py` — new table; columns roughly:
  `id`, `scope (user|team)`, `owner_user_id` (when scope=user), `owner_team_id` (when scope=team — team table is itself deferred to D8.1?), `name`, `slug`, `frontmatter JSONB`, `body TEXT`, `version`, `archived_at`, `created_at`, `updated_at`. Constraints: `(scope, owner_user_id, slug) UNIQUE WHERE scope='user'`; same for team.
* `api/app/api/skills.py` — extend with `POST /api/v1/skills`, `PATCH /api/v1/skills/{id}`, `DELETE /api/v1/skills/{id}`. Existing `GET /skills` reads filesystem-canonical built-ins; the new endpoints layer user-scope on top.
* **Skill Service registry merge** in `gateway/`: when assembling skill prompts, walk filesystem built-ins first, then DB user skills (newest version wins). Per ADR 0007 the gateway is the authority on skill resolution.
* Gateway internal-skills user-scope path — fetch user skills via a new internal endpoint (`/internal/skills?user_id=...`) on the api service.
* `web/src/routes/lq-ai/skills/new/+page.svelte` — Skill Creator page. Form fields mirror SKILL.md frontmatter (name, description, version, tags, prompt_template).
* Rewire D7's "Promote to Skill" — currently downloads SKILL.md; new path POSTs to `/api/v1/skills` with `scope=user`.

Audit writes on the new endpoints: `user_skill.created`, `user_skill.updated`, `user_skill.deleted` — mirror the saved_prompts pattern. (Saved-prompts audit was wired in D7.)

### Option D — Encrypted-keys operator workflow doc (~30 min)

Tag-along. `docs/security/encrypted-keys.md`:

* generate-master-key (`python -m app.cli generate-master-key`)
* encrypt-key (stdin-fed plaintext; CLI emits Fernet token)
* paste the token into `gateway.yaml` under `providers[].api_key_encrypted`
* master-key rotation procedure: regenerate, re-encrypt every key, swap `LQ_AI_GATEWAY_MASTER_KEY` env var on next deploy
* recovery-from-lost-master-key procedure: there is no recovery; operator must re-issue every provider key and re-encrypt with a fresh master key

Per the previous handoff's recommendation D bundles with B's docs pass, but B's docs are minimal (just the M1-PROGRESS update); doing D standalone in 30 minutes is fine.

### D3-coverage extras (out-of-scope but related)

* projects.py audit writes — 7 endpoints (create / update / delete + project-files attach/detach + project-skills add/remove). C7 surface; could be picked up if the operator security review flags the gap.
* admin.py aliases audit writes — 3 endpoints (create / update / delete alias). D0.5 surface.
* chats.py CRUD audit writes — chat.create / chat.update / chat.delete. C3 surface; only message-sent is audited today.
* Tests for the new B audit-write call sites — one per surface, asserting the audit row lands.

---

## How to resume

1. `cd /Users/kevinkeller/Desktop/LegalQuants/inhouse-ai`
2. `git status` clean; `git log --oneline -1` shows `ae84231`.
3. `docker compose ps` — all 7 services healthy. api + web both rebuilt this session.
4. **Pick C or D** (or both). The recommended sequence from the prior handoff (A → C → B) shifted to (A → B → C → D) at Kevin's direction; C and D remain in that order.
5. For C, start by drafting the ADR amendment to 0004 — that's the north star for the migration + endpoint shapes.

---

## Things that should NOT regress

(Carry-forward from prior handoffs.)

- `OLLAMA_BASE_URL` should point at host Ollama unless `--profile local` is intentionally active.
- Anthropic key in `.env` is real — DO NOT overwrite when generating a fresh `.env`.
- `POSTGRES_HOST_PORT=5433` (host postgres collision; tidepool currently down).
- `LQ_AI_CORS_ORIGINS=http://localhost:3000` (local dev only; production: leave unset).
- `PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1` (local dev; production: relative `/api/v1`).
- Gateway-config writable named volume `gateway-config` mounted at `/etc/lq-ai`.
- Pre-existing test failures still on `main` HEAD (predate wave-3 + B):
  - 1 in test_endpoints.py (D1 deferred tier-policy surface).
  - 11 unrelated pre-wave-3 failures (skills forwarding fixture uses non-existent chat id; migration `inference_routing_log` FK-set-null check). Confirmed against clean main; not regressions from this session.
  - web `npm run check` shows ~9k pre-existing OpenWebUI fork errors (i18n typing, unrelated routes) — unchanged.

---

## Verification commands

```bash
# 1) requested_model persistence (Option A)
TOKEN=$(curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-smoke-test-Pw1!"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

CHAT=$(curl -sX POST http://localhost:8000/api/v1/chats \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"handoff-c smoke"}')
CID=$(echo "$CHAT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

curl -sX POST "http://localhost:8000/api/v1/chats/$CID/messages" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"ping","model":"smart"}' | python3 -m json.tool | grep -E "requested|routed_(provider|model)"

# Expect: requested_model="smart", routed_model="claude-opus-4-7"

# 2) Audit-log readback (Option B)
# After login above, you've already produced a user.login row.
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/audit-log?limit=5&action=user.login" \
  | python3 -m json.tool | head -25

# 3) Generate a failed login + read it back
curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@lq.ai","password":"wrong"}' > /dev/null
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/audit-log?limit=3&action=user.login_failed" \
  | python3 -m json.tool | head -25

# Expect: row with details={"email":"admin@lq.ai","reason":"wrong_password"}
```

Browser smoke (recommended before declaring D3-coverage fully shipped):
* http://localhost:3000/lq-ai → log in as admin
* navigate to http://localhost:3000/lq-ai/admin/audit-log
* confirm the just-now login row renders at the top
* test each filter dimension; confirm privileged rows highlight amber when present
* test "Load more" pagination
