# Session Handoff — 2026-05-10d (D8 API slice + encrypted-keys doc)

> **Purpose.** Resume in a fresh context window. Pair with `docs/M1-PROGRESS.md`. Fourth handoff for 2026-05-10. The morning (SESSION-HANDOFF-2026-05-10.md) covered D7; the afternoon (-10b.md) covered Wave-3 transparency; the evening (-10c.md) covered Option A + D3-coverage. This one covers **D** (encrypted-keys ops doc) + the **D8 API slice** (DB-backed user skills per the new ADR 0012). The remaining D8 work is the **Skill Creator UI**; team-scope CRUD is deferred to **D8.1**.

---

## State at handoff

- **Branch:** `main`. Pushed through `674933a` (D8 progress-doc update).
- **Commits landed this session (all pushed):**
  ```
  674933a docs(progress): D8 API slice landed (ADR 0012)
  53b0b1d feat(api): user-skills CRUD + skills merge/shadow/fork (D8 per ADR 0012)
  251a674 feat(db): migration 0013 + UserSkill ORM (ADR 0012)
  c371c53 docs(adr): 0012 — DB-backed user skills (amends ADR 0004)
  30b4a65 docs(security): encrypted-keys operator workflow (ADR 0011)
  ```
- **Stack:** all 7 services healthy; api rebuilt this session (migration 0013 + new code). Web container is **stale on D8** — it still doesn't know about /user-skills; rebuild before the D8 UI session.
- **Auth:** `admin@lq.ai` / `LQ-AI-smoke-test-Pw1!`.
- **Migrations:** `0001` → `0013` (0013 adds `user_skills`).
- **Test counts:** +25 in `api/tests/test_user_skills.py`; pre-existing failures unchanged (admin/tier-policy stubs from D1; FK-set-null check on `inference_routing_log`; `test_skill_loader` 2; `test_chats_endpoints` 1; `test_pipeline_ingest` 1 — all carried forward from prior handoffs).

---

## What landed this session

### D — Encrypted-keys ops doc (~30 min, 1 commit)

`docs/security/encrypted-keys.md` (~230 lines). Operator workflow for the encrypted-at-rest path that landed code-side in wave-3 (ADR 0011 §"Encrypted-at-rest provider keys"). Sections:

* Why it exists; threat-model framing (plaintext-in-`gateway.yaml` was the gap).
* One-time bootstrap (`generate-master-key` → vault → `LQ_AI_GATEWAY_MASTER_KEY` env), with a deployment-target binding table (compose / k8s / systemd / host).
* Per-provider `encrypt-key` (interactive vs piped vs `--plaintext` — explicit warning against the last because shell history).
* Before/after `gateway.yaml` snippet showing `api_key_env` → `api_key_encrypted` swap.
* Full rotation procedure: generate fresh master key → re-encrypt every provider key under it → swap yaml → swap env → restart → verify via `/admin/v1/providers/health` → revoke old.
* Lost-master-key story: no recovery, re-issue every upstream provider key.
* Verification smokes (round-trip canary; adapter health; end-to-end dispatch).
* "What this doesn't do": encrypted at rest ≠ encrypted in use; master key is still a secret; per-user keys out of scope; no HSM/KMS in M1.

Cross-linked from `docs/security/README.md`'s artifact table.

### ADR 0012 — DB-backed user skills (1 commit, north star before code)

`docs/adr/0012-db-backed-user-skills.md` (~170 lines). Amends ADR 0004 (skill-loader locus). Settles five decisions before the migration shape was inked:

1. **Storage:** new `user_skills` table; single row per `(scope, owner, slug)`; team-scope columns ship from the start so D8.1 is purely additive.
2. **Resolution: user shadows built-in.** A user's row at slug `nda-review` wins for their chats; the built-in stays canonical for everyone else. Forking-by-shadowing per PRD §1.3 transparency framing.
3. **Registry merge: lookup-time join, not registry rebuild.** The in-memory `SkillRegistry` stays built-in-only; `/internal/skills/{slug}?user_id=...` does an O(1) DB lookup per resolution.
4. **API surface:** management CRUD at `/api/v1/user-skills`; read merge + fork at `/api/v1/skills` (preserves OpenAPI sketch's path shapes).
5. **Versioning: single-row + user-set semver string.** No history table; `archived_at` soft-delete; audit log records `version_before` / `version_after` so edits are forensically traceable.

ADR 0004 was banner-updated with a forward reference so downstream readers arrive at 0012 without bouncing through git log.

### D8 API slice (3 commits: db, api+tests, progress)

#### Migration 0013 (`251a674`)

`api/alembic/versions/0013_create_user_skills.py` + ORM at `api/app/models/user_skill.py`.

Columns: `id`, `scope`, `owner_user_id` (FK→users CASCADE), `owner_team_id` (FK target deferred to D8.1), `slug`, `display_name`, `description`, `version` (default `'1.0.0'`), `tags` (TEXT[]), `frontmatter_extra` (JSONB), `body`, `archived_at`, `created_at`, `updated_at`.

Constraints:
* CHECK `scope IN ('user', 'team')`.
* CHECK scope/owner consistency — user rows must have owner_user_id and NULL owner_team_id; same shape for team.
* Two partial UNIQUE indexes — `ux_user_skills_{user,team}_slug` on `(owner_*_id, slug) WHERE scope = '<x>' AND archived_at IS NULL`. Archiving frees the slug for re-creation; that's the deliberate soft-delete-and-reuse pattern.
* Two partial listing indexes — `idx_user_skills_owner_{user,team}` on `(owner_*_id, updated_at DESC)` partial on the live branch.
* `set_updated_at()` trigger (canonical across all entity tables per A2).

`db-schema.md` carries the canonical DDL.

#### API + tests (`53b0b1d`)

| Endpoint | Behavior |
|---|---|
| `POST /api/v1/user-skills` | Create user-scope row. Slug collision with **own non-archived rows** → 409; collision with a **built-in** is allowed (shadow case). Audit: `user_skill.created`. |
| `GET /api/v1/user-skills` | List caller's non-archived rows; newest-first. Rich `UserSkill` response (body + frontmatter_extra). |
| `GET /api/v1/user-skills/{id}` | Owner-only fetch; 404 for non-owner (id-probing safe). |
| `PATCH /api/v1/user-skills/{id}` | Partial update. No-op PATCH returns the row without writing audit; version bump records `version_before` / `version_after` in `details`. Audit: `user_skill.updated`. |
| `DELETE /api/v1/user-skills/{id}` | Soft-delete (sets `archived_at`). 204 first time; 410 on already-archived. Audit: `user_skill.deleted`. |
| `GET /api/v1/skills` (extended) | Merges built-ins + caller's user-scope rows; user rows first; built-ins dedup on slug match. `scope=user/builtin/team` filters apply independently. |
| `GET /api/v1/skills/{slug}` (extended) | Shadow first, registry fallback, 404 if neither. |
| `POST /api/v1/skills/{slug}/fork` (real) | Replaces C1-era 501 stub. Copies built-in's resolved frontmatter + body into a new user-scope row. `scope=team` → 400 (deferred to D8.1). `new_name` defaults to source slug (the "same-slug shadow" case). Audit: `user_skill.created` with `details.forked_from`. |

Audit failure-path commit-before-raise convention from 2026-05-10c is respected — IntegrityError on slug collision rolls back cleanly without leaving stale audit rows.

OpenAPI sketch (`docs/api/backend-openapi.yaml`) updated: new paths, new component schemas (`UserSkill`, `UserSkillCreate`, `UserSkillUpdate`), new `user-skills` tag. `test_openapi` counter bumped 46 → 48.

`test_user_skills.py` covers 25 scenarios: CRUD round-trip, cross-user 404 isolation, collision with own slug (409) + built-in (201 OK), PATCH partial + version-bump + no-op, soft-delete + 410 + re-create-after-archive, merged listing + shadow dedup, per-user shadow isolation, fork (happy path + team→400 + missing→404 + default-slug shadow), migration 0013 CHECK + partial UNIQUE invariants.

#### Progress doc (`674933a`)

Snapshot row marks D8 API slice complete; D8 UI is the open piece; D8.1 lands the team-scope columns' API surface.

### Live verification done in-session

```bash
# All confirmed via curl against the running stack, with admin user:
- POST /user-skills create → 201, persists, returns rich response
- GET /user-skills → owner-only list
- GET /skills (merged) → user-scope first, then 10 built-ins; shadow dedupes
- GET /skills/my-custom-nda → shadow content_md = "shadowed body" (not built-in)
- POST /skills/nda-review/fork {new_name: "nda-review-kev"} → 201; audit has forked_from
- POST /user-skills (dup) → 409
- PATCH with version bump → audit details.version_before/version_after
- DELETE → 204; DELETE again → 410; recreate at same slug → 201
```

---

## What's NOT done in D8 (queued for next session)

### D8 — Skill Creator UI (the remaining D8 piece)

Per ADR 0012 §Consequences ("UI must surface shadowing"). The implementation obligations:

* **`web/src/routes/lq-ai/skills/new/+page.svelte`** — form fields mirroring `UserSkillCreate`: slug, display_name, description, version, tags, body, optional frontmatter_extra (advanced disclosure?).
* **Shadow warning UX.** When a user types a slug matching a filesystem built-in, the form must prominently surface that the new skill will *shadow* the built-in for their chats — without rejecting the create. Suggested copy: "This shadows the built-in `nda-review` skill for your chats; other users still see the built-in." Probably a yellow inline note next to the slug field.
* **`web/src/routes/lq-ai/skills/+page.svelte`** — list page showing the caller's user-scope skills with edit / archive affordances. Fetches `GET /api/v1/user-skills`.
* **`web/src/routes/lq-ai/skills/[id]/edit/+page.svelte`** — edit form. Fetches `GET /api/v1/user-skills/{id}`; submits `PATCH`.
* **Rewire D7 "Promote to Skill."** Currently downloads SKILL.md; the new path POSTs to `/api/v1/user-skills` with the saved-prompt's body becoming `body` and the user picking a slug + display_name. The download path can stay as an "Export" option for advanced users who want to PR a built-in.
* **Web API client.** Add `web/src/lib/lq-ai/api/user-skills.ts` mirroring the existing saved-prompts client shape. Round-trip vitest a la D3-coverage's audit-log client.

Rough sizing: ~3-5h for a clean UI pass. The API is stable so this is straight Svelte work.

### D8 — Gateway internal endpoint extension (smaller piece)

`/internal/skills/{skill_name}` (in `api/app/api/internal.py`) currently only knows about filesystem skills. Per ADR 0012 §3, it should accept an optional `user_id` query param and check `user_skills` first before falling through to the registry. Without this extension the **shadow doesn't actually shape prompts during inference** — the merged list shows the shadow, the read endpoint returns it, but the gateway-side prompt-assembly path (C2) still sees the built-in.

Touch points:
* Extend `get_skill_internal` to accept `user_id: uuid.UUID | None = Query(default=None)`.
* Lookup user shadow if `user_id` provided; synthesize Skill payload from `user_skills` row.
* `gateway/app/skills_client.py` (or wherever C2 calls this): thread the requesting user's UUID into the call.
* Integration smoke: chat as the admin against a user-scope shadow → verify the shadow body actually lands in the system prompt (look at the inference_routing_log row's `prompt_skills` or equivalent).

Rough sizing: ~1h. This and the UI work could land in either order; the UI without the internal hop renders the shadow correctly but it doesn't *do* anything during inference yet — worth landing the internal hop first if you want end-to-end shadow behavior.

### D8.1 — Team-scope CRUD (deferred per ADR 0012)

* New `teams` + `team_members` migration.
* FK constraint linking `user_skills.owner_team_id` → `teams.id`.
* Team-scope branches in `/api/v1/user-skills` (POST/PATCH/DELETE) with team-admin permission checks.
* Resolution-order middle slot in `_load_user_shadow` (user > team > built-in).
* Gateway internal endpoint extended again to look up team membership.

Schema is ready; this is the "next D-task after D8 UI" item.

---

## How to resume

1. `cd /Users/kevinkeller/Desktop/LegalQuants/inhouse-ai`
2. `git status` clean; `git log --oneline -1` shows `674933a`.
3. `docker compose ps` — all 7 services healthy. **Rebuild web before UI work** (api was rebuilt this session; web wasn't).
4. **Pick the next move:**
   - **Recommended path:** internal-endpoint extension first (~1h; closes the shadow-actually-shapes-prompts loop), then UI (~3-5h). UI tests against a real shadow behavior.
   - **Alternative:** UI first, ship the management surface, internal hop as a follow-on.
5. Read ADR 0012 §3 ("Registry merge: lookup-time join, not registry rebuild") before touching the internal endpoint.

---

## Things that should NOT regress

(Carry-forward from prior handoffs + new for D8.)

- `OLLAMA_BASE_URL` should point at host Ollama unless `--profile local` is intentionally active.
- Anthropic key in `.env` is real — DO NOT overwrite when generating a fresh `.env`.
- `POSTGRES_HOST_PORT=5433` (host postgres collision).
- `LQ_AI_CORS_ORIGINS=http://localhost:3000` (local dev only; production: leave unset).
- `PUBLIC_LQ_AI_API_BASE_URL=http://localhost:8000/api/v1` (local dev; production: relative `/api/v1`).
- Gateway-config writable named volume `gateway-config` mounted at `/etc/lq-ai`.
- **New for D8**: when the Skill Creator UI lands, do NOT remove the shadow-warning UX without surfacing it elsewhere — the silent-shadowing behavior is by design but the user MUST know about it (ADR 0012 §Consequences).
- **New for D8**: do NOT add a `user_skill_versions` history table without filing a DE and reading ADR 0012 §5. The single-row+audit-log decision is deliberate.
- Pre-existing test failures still on `main` HEAD (predate D8):
  - 2 in test_endpoints.py (D1 deferred tier-policy surface).
  - 2 in test_migrations.py (FK-set-null check on inference_routing_log).
  - 2 in test_skill_loader.py.
  - 1 in test_chats_endpoints.py.
  - 1 in test_pipeline_ingest.py.
  - Confirmed against clean main; not regressions from this session.
  - web `npm run check` shows ~9k pre-existing OpenWebUI fork errors (i18n typing, unrelated routes) — unchanged.

---

## Verification commands (D8 surface)

```bash
# 0) Login
TOKEN=$(curl -sX POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@lq.ai","password":"LQ-AI-smoke-test-Pw1!"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 1) Create a user-scope skill
curl -sX POST http://localhost:8000/api/v1/user-skills \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"slug":"my-nda","display_name":"My NDA","description":"My workflow","body":"Be thorough on noncompetes."}' \
  | python3 -m json.tool

# 2) Merged listing — user-scope first, then built-ins
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/skills \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(f'total={len(d)}');[print(' ',s['scope'],s['name'],'v'+s['version']) for s in d[:12]]"

# 3) Fork a built-in into user scope
curl -sX POST http://localhost:8000/api/v1/skills/nda-review/fork \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"new_name":"my-nda-review","scope":"user"}' \
  | python3 -m json.tool | head -10

# 4) Shadow read — create at same slug as a built-in, then GET /skills/{slug}
curl -sX POST http://localhost:8000/api/v1/user-skills \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"slug":"contract-qa","display_name":"My CQA","description":"shadow","body":"shadowed"}'
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/skills/contract-qa \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('scope:',d['scope']);print('body[:40]:',d['content_md'][:40])"
# Expect: scope=user, body=shadowed

# 5) Audit-log readback
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/audit-log?action=user_skill.created&limit=5" \
  | python3 -m json.tool | head -40
```

---

## Files touched this session

```
A  api/alembic/versions/0013_create_user_skills.py
A  api/app/api/user_skills.py
A  api/app/models/user_skill.py
A  api/tests/test_user_skills.py
A  docs/adr/0012-db-backed-user-skills.md
A  docs/security/encrypted-keys.md
M  api/app/api/__init__.py
M  api/app/api/skills.py
M  api/app/models/__init__.py
M  api/tests/test_endpoints.py
M  api/tests/test_openapi.py
M  docs/M1-PROGRESS.md
M  docs/adr/0004-skill-loader-locus.md  (banner reference to 0012)
M  docs/api/backend-openapi.yaml         (new endpoints + schemas)
M  docs/db-schema.md                     (user_skills DDL)
M  docs/security/README.md               (encrypted-keys row in artifact table)
```

Untracked (carried from prior session; not in git): `docs/MODEL_PICKER_ARCHITECTURE.md`.
