# Session Handoff — 2026-05-10e (D8 closed loop + D8.1a teams)

> **Purpose.** Resume in a fresh context window. Pair with `docs/M1-PROGRESS.md`. Fifth handoff for 2026-05-10. This session continued from `-10d.md` and landed: gateway internal-endpoint `?user_id=` extension (shadows during inference), Skill Creator UI + Promote-to-Skill rewire, and D8.1a teams (schema + admin CRUD). The remaining D-work is **D8.1b** (team-scope branches on `/user-skills` + the gateway middle-resolution slot) plus a browser smoke pass on the Skill Creator UI.

---

## State at handoff

- **Branch:** `main`. Pushed through `6b40ee5` (progress-doc update).
- **Commits landed this session (all pushed):**
  ```
  6b40ee5 docs(progress): D8 end-to-end + D8.1a landed
  a75a98a feat(api): admin team CRUD + member management (D8.1a)
  f79c41b feat(db): migration 0014 + Team/TeamMember ORM (D8.1a)
  9055a39 feat(web): rewire D7 Promote-to-Skill to user-skills CRUD (D8)
  bdc4ae2 feat(web): Skill Creator UI (D8 / ADR 0012)
  e9484bb feat(api+gateway): thread user_id through skill resolution (D8 / ADR 0012)
  ```
- **Stack:** all 7 services healthy; api + gateway + web all rebuilt this session.
- **Auth:** `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!`.
- **Migrations:** `0001` → `0014` (0014 adds `teams` + `team_members` + closes `user_skills.owner_team_id` FK).
- **Test counts:** +4 internal-skills user_id tests, +9 web user-skills API tests, +19 teams CRUD/migration tests. ~700 api tests + 364 gateway tests + 72 web vitests now passing.

---

## What landed this session

### 1. Gateway internal-endpoint `?user_id=` extension (`e9484bb`)

Closes the shadow-during-inference loop. Before, D8 surfaced user-scope shadows on the read endpoints but the gateway's C2 prompt-assembly path still pulled the filesystem built-in — so a user could see their shadow in the picker yet their chats still ran against the original.

* `api/app/api/internal.py`: `GET /internal/skills/{slug}` now takes an optional `?user_id=<uuid>` query param. When set, the resolver checks `user_skills` for a non-archived shadow first and synthesizes the Skill payload from the row; falls through to the registry otherwise.
* `api/app/schemas/gateway.py` + `gateway/app/providers/openai_schema.py`: `ChatCompletionRequest` carries a new `lq_ai_user_id` field.
* `api/app/api/chats.py`: backend forwards `str(user.id)` on every chat send.
* `gateway/app/clients/backend.py`: `BackendClient.get_skill` threads `user_id` to the URL as `?user_id=...`. The skill cache key encodes `(name, user_id)` via the new `_skill_cache_key` helper so user A's shadow can't bleed into user B's chats and the registry-only view gets its own cache slot.
* `gateway/app/api/inference.py`: `_apply_skills` reads `chat_request.lq_ai_user_id` and passes it on every skill fetch.

**Verified live:** shadow body of "SHADOWED-BODY-SENTINEL: …" produces prompt_tokens=162 (vs 113 with no shadow), confirming the shadow content is in the dispatched system prompt. Direct internal-endpoint smoke shows `scope: user` with the shadow's `content_md` when `user_id` is set, `scope: builtin` otherwise. Claude Sonnet 4.6 ignored a "IGNORE ALL INSTRUCTIONS" sentinel in the shadow body — that's the model's safety training, not a plumbing bug.

### 2. Skill Creator UI (`bdc4ae2`)

Three routes under `/lq-ai/skills`:

* `/lq-ai/skills` — list of caller's user-scope skills with edit / archive affordances. Rows whose slug matches a built-in carry an amber "Shadows built-in" chip so the user sees at-a-glance which of their skills are overriding canonical content.
* `/lq-ai/skills/new` — create form. Slug input watches for built-in collisions and surfaces a yellow inline note explaining shadowing semantics. Creation is never blocked.
* `/lq-ai/skills/[id]/edit` — edit form. Slug read-only (rename is out of scope for D8). PATCH sends only changed fields; idempotent re-saves write no audit row. Same shadow warning surfaces.

API client at `web/src/lib/lq-ai/api/userSkills.ts` mirrors the saved-prompts client shape. 9 new vitests cover round-trip + auth-header attachment + 409 / 404 / 410 surfaces. Header nav gains a "My skills" link.

**Browser-smoke is still TODO.** The build succeeds, route serves HTTP 200, and unit tests pass. Per "don't overclaim UI completeness": a follow-on session needs to click through to confirm the shadow warning renders on slug collision, the edit-archive flow round-trips, and the layout works at smaller widths.

### 3. D7 Promote-to-Skill rewire (`9055a39`)

`SavedPromptsPanel.svelte`: "Save as skill" (download) → "Promote to skill" (POST `/api/v1/user-skills` → goto `/lq-ai/skills/{id}/edit?created=1`). Slug-collision-with-built-in is permitted at the API level; the edit page surfaces the shadow warning. "Export as SKILL.md" stays as a secondary affordance for users who want to upstream a skill via PR.

409 (slug already in caller's scope) surfaces an inline error pointing the user at `/lq-ai/skills` to edit the existing row.

### 4. D8.1a — teams schema + admin CRUD (`f79c41b`, `a75a98a`)

Migration 0014:
* `teams` table: id, name, slug (unique), description, created_by_user_id (RESTRICT), timestamps + trigger.
* `team_members` join: composite PK on (team_id, user_id), role enum CHECK ('admin' | 'member'), added_by_user_id RESTRICT (audit-trail forensics), CASCADE on team/user delete.
* `fk_user_skills_team`: CASCADE — deleting a team archives every team-scope skill it owned.

Endpoints (operator-admin only; non-admins get 403 on /admin paths):
* `POST /admin/teams` — create + auto-add creating admin as team-admin member.
* `GET/PATCH/DELETE /admin/teams/{id}` — list/read/update/delete.
* `POST /admin/teams/{id}/members` — add user with role.
* `PATCH /admin/teams/{id}/members/{user_id}` — change role (no-op write skips audit).
* `DELETE /admin/teams/{id}/members/{user_id}` — remove.
* `GET /teams` — caller's teams (read-only).
* `GET /teams/{id}` — single team (404 if not a member; id-probing-safe).

Audit actions: `team.created`, `team.updated`, `team.deleted`, `team.member_added`, `team.member_role_changed`, `team.member_removed`. Each row's details carry slug + email + before/after role for forensics.

**Design decisions Kevin confirmed before code:**
1. Operator-admin-only team mutate (no democratic "anyone creates teams" model).
2. Multi-team-shadow conflict resolution = newest `updated_at` wins (deferred — this is D8.1b's concern).
3. D8.1 scope = schema + team CRUD only. D8.1b lands later.

---

## What's NOT done (queued)

### D8.1b — team-scope user-skills + gateway middle-slot (the big remaining piece)

* **`/api/v1/user-skills` team-scope branches.** Currently POST/PATCH/DELETE only handle `scope='user'`. D8.1b adds:
  - `POST /user-skills` with `scope='team'` + `owner_team_id` — caller must be a team-admin member of the named team.
  - PATCH/DELETE — same team-admin role check.
  - Slug uniqueness within team (the partial UNIQUE index already exists in migration 0013).
  - Audit: same actions but resource bag carries `team_id`.
* **`/internal/skills/{slug}` middle slot.** Resolution becomes user > team > built-in. When `user_id` is supplied, the resolver:
  1. Check `user_skills` for that user's non-archived shadow at `slug`.
  2. Else check `user_skills` for non-archived team-scope rows at `slug` where the user is a member; pick newest `updated_at` (the design decision).
  3. Else fall through to the filesystem registry.
* **Gateway cache key.** When the team-scope path lands, the cache key needs to extend to `(name, user_id, team_set_signature)` — OR more pragmatically, the team-scope lookup happens at the resolution layer and the cache key stays `(name, user_id)`. The latter is simpler; the former handles a team-membership change without restart. Re-decide when wiring.
* **Tests.** Migration is already there. Team-scope CRUD + ownership gates + multi-team-shadow conflict resolution + gateway-side per-user-per-team cache isolation.

Rough sizing: ~3-4h. Smaller than D8.1a because the schema work is done.

### D8 UI browser-smoke (TODO from this session)

Click-through verification of the three /lq-ai/skills pages:
* Slug-collision warning renders when typing `nda-review` into the new-skill form.
* List page shows the "Shadows built-in" chip for matching slugs.
* Edit page round-trips: change a field, save, see updated value in list.
* Archive flow: archive a skill → it disappears from the list; recreate at the same slug works.
* Promote-to-Skill from `SavedPromptsPanel` flows to the edit page with `?created=1` banner.

### Other carry-forward (unchanged)

* B6 remainder (OpenAI chat completions, Vertex, Bedrock) — optional for M1 baseline.
* Browser smoke of `/lq-ai/admin/audit-log` (carried from `-10c`) + the `requested_model` row in `TierDetailsPanel`.

---

## How to resume

1. `cd /Users/kevinkeller/Desktop/LegalQuants/inhouse-ai`
2. `git status` clean; `git log --oneline -1` shows `6b40ee5`.
3. `docker compose ps` — all 7 services healthy.
4. **Pick the next move:**
   - **Recommended:** D8 UI browser-smoke first (~30 min). Catches any visual regressions before D8.1b broadens the surface.
   - Then **D8.1b** (~3-4h). The schema is in place; this is straight handler + resolver work.
5. Read ADR 0012 §3 + this handoff's D8.1b section before touching the resolver.

---

## Things that should NOT regress

(Carry-forward from prior handoffs + new for this session.)

- `OLLAMA_BASE_URL` should point at host Ollama unless `--profile local` is intentionally active.
- Anthropic key in `.env` is real — DO NOT overwrite when generating a fresh `.env`.
- `POSTGRES_HOST_PORT=5433` (host postgres collision).
- `LQ_AI_CORS_ORIGINS=http://localhost:3000` (local dev only).
- `PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1` (local dev).
- Gateway-config writable named volume `gateway-config` mounted at `/etc/lq-ai`.
- **New for D8.1a**: when D8.1b lands the team-scope user-skills branches, the `_load_user_shadow` helper in `api/app/api/skills.py` needs a team-aware variant — don't extend the existing helper inline without surfacing the multi-team-conflict resolution rule.
- **New for D8**: do NOT remove the shadow-warning UX from `/lq-ai/skills/new` or `/lq-ai/skills/[id]/edit` without surfacing it elsewhere. The silent-shadowing behavior is by design but the user MUST know.
- Pre-existing test failures (unchanged across this session):
  - 8 in test_chats_skills_forwarding.py (non-existent chat id fixture).
  - 2 in test_endpoints.py (D1 deferred tier-policy surface).
  - 2 in test_migrations.py (FK-set-null check on inference_routing_log).
  - 2 in test_skill_loader.py.
  - 1 in test_chats_endpoints.py.
  - 1 in test_pipeline_ingest.py.

---

## Verification commands

```bash
# 0) Login
TOKEN=$(curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-smoke-test-Pw1!"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 1) Create a team and verify auto-admin membership
curl -sX POST http://localhost:8000/api/v1/admin/teams \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"slug":"contracts","name":"Contracts Team"}' \
  | python3 -m json.tool | head -20
# Expect: member_count=1; members=[{role:'admin', email:'admin@lq.ai'}]

# 2) List my teams
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/teams \
  | python3 -m json.tool

# 3) Shadow-during-inference verification (carried from -10d)
GW_KEY=$(grep "^LQ_AI_GATEWAY_KEY=" .env | cut -d= -f2)
ADMIN_ID=$(curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/users/me | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
# After creating a shadow at slug=nda-review:
curl -s -H "X-LQ-AI-Gateway-Key: $GW_KEY" \
  "http://localhost:8000/api/v1/internal/skills/nda-review?user_id=$ADMIN_ID" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('scope:',d['scope']);print('body[:60]:',d['content_md'][:60])"

# 4) Audit roll-up — every state-changing surface this session
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/audit-log?action=team.created&limit=3" \
  | python3 -m json.tool | head -20
```

Browser smoke (recommended before D8.1b):
* http://localhost:3000/lq-ai/skills — verify list renders + shadow chips appear
* http://localhost:3000/lq-ai/skills/new — type slug `nda-review`, confirm shadow warning
* Edit + archive flow on an existing user-skill

---

## Files touched this session

```
A  api/alembic/versions/0014_create_teams.py
A  api/app/api/teams.py
A  api/app/models/team.py
A  api/tests/test_teams.py
A  docs/SESSION-HANDOFF-2026-05-10e.md
A  web/src/lib/lq-ai/__tests__/user-skills-api.test.ts
A  web/src/lib/lq-ai/api/userSkills.ts
A  web/src/routes/lq-ai/skills/+page.svelte
A  web/src/routes/lq-ai/skills/[id]/edit/+page.svelte
A  web/src/routes/lq-ai/skills/new/+page.svelte
M  api/app/api/__init__.py
M  api/app/api/chats.py
M  api/app/api/internal.py
M  api/app/models/__init__.py
M  api/app/schemas/gateway.py
M  api/tests/test_endpoints.py
M  api/tests/test_internal_skills.py
M  api/tests/test_openapi.py
M  docs/M1-PROGRESS.md
M  docs/api/backend-openapi.yaml
M  docs/db-schema.md
M  gateway/app/api/inference.py
M  gateway/app/clients/backend.py
M  gateway/app/providers/openai_schema.py
M  web/src/lib/lq-ai/api/index.ts
M  web/src/lib/lq-ai/components/SavedPromptsPanel.svelte
M  web/src/lib/lq-ai/types.ts
M  web/src/routes/lq-ai/+layout.svelte
```

Untracked (carried; not in git): `docs/MODEL_PICKER_ARCHITECTURE.md`.
