# Plan — LibreOffice editor **Slice 2**: the WOPI host in `api` (CheckFileInfo · GetFile · Lock family · file-scoped token)

## Context

Slice 1 stood up the isolated `collabora` (CODE) service behind the same-origin `/collabora/` proxy
(ADR-F047). Slice 2 makes `api` a **WOPI host** so Collabora can open a matter's `.docx` over the WOPI
protocol. Per the milestone sequence (**WOPI read → save-back → cockpit editor/reskin → hand-back**),
Slice 2 is the **read** half: the lawyer can SEE the agent's redline in the in-app engine. Editing +
byte-save-back (PutFile) is Slice 3; the cockpit launch UI + reskin is Slice 4.

WOPI protocol spec used (authoritative, agent-researched against MS WOPI REST docs + Collabora SDK +
this repo's `docs/fork/research/libreoffice-editor.md` + the maintainer's VibeLegalStudio prior art).

## Decisions (this slice's architectural calls — recorded as an **F047 addendum**, no new ADR)

1. **Read-only viewer this slice.** CheckFileInfo advertises `UserCanWrite=false`, `ReadOnly=true`,
   `SupportsUpdate` omitted (→ false). The doc opens faithfully (tracked changes/comments render) but
   no save path exists yet → **no data-loss window**. Slice 3 flips to editable + adds PutFile atomically.
2. **File-scoped editor token = a stateless signed JWT** (mirrors `create_mfa_token`): HS256 on the
   existing `settings.jwt_secret`, `typ="wopi"`, claims `sub` (user id), `fid` (file id), `name`
   (display name → WOPI `UserFriendlyName`), `iat`, `exp`. No DB row. Three-layer authz: mint gated by
   `ActiveUser` + `_load_visible_file` (cross-user → 404); the `fid` claim must equal the URL `{file_id}`
   (no cross-file replay); every WOPI handler re-runs `_load_visible_file(db, fid, claims.user_id)` →
   404. Bad/expired/wrong-typ/`fid`-mismatch token → **401**; file not visible → **404**.
3. **Locks = a small `editor_locks` DB table** (migration `0074`), keyed by `file_id` (PK, FK→files
   `ON DELETE CASCADE`), `lock_value TEXT` (≤1024, `SupportsExtendedLockLength=true`), `expires_at`
   (30-min TTL; expired → treated as unlocked). The WOPI lock **state machine is a pure function**
   (`app/schemas/wopi.py`) the handler wires DB read/write around — fully unit-testable. Locks are
   implemented + tested this slice (HANDOFF-recorded Slice-2 scope, de-risks Slice 3); a read-only
   Collabora session won't call them live, so they're proven by unit tests + a curl smoke replicating
   Collabora's exact LOCK→GET_LOCK→REFRESH_LOCK→UNLOCK→UNLOCK_AND_RELOCK sequence.
4. **`Version` / `X-WOPI-ItemVersion` = `File.hash_sha256`** (content-addressed → changes on save-back).
   `OwnerId`/`UserId` = `uuid.hex` (WOPI requires **alphanumeric**; the hyphenated form is invalid).
5. **No model calls anywhere in Slice 2** → ADR-F010 egress invariant trivially intact; the WOPI host
   never touches the gateway. Proof-key (`X-WOPI-Proof`) validation stays **deferred** (optional;
   threat model = file-scoped short-TTL token + private compose network + `aliasgroup1` allow-list).

## Files & changes (api only — no web, no nginx; WOPI callbacks are server-to-server on the compose net)

1. **`app/config.py`** — `collabora_wopi_host` (default `http://api:8000`, the in-network address
   Collabora reaches = matches Slice-1 `aliasgroup1`), `wopi_token_ttl_seconds` (default `36000` = 10h),
   `collabora_post_message_origin` (default `http://localhost:3000`; consumed by the Slice-4 reskin).
2. **`app/security/jwt.py`** (+ `__init__.py` exports) — `WopiTokenClaims`, `create_wopi_token`,
   `decode_wopi_token` mirroring the MFA-token pattern (`_TYPE_WOPI`).
3. **`app/models/editor_lock.py`** (+ register in models package) — `EditorLock`.
4. **`alembic/versions/0074_editor_locks.py`** (down_revision `0073`) — `create_table editor_locks`
   (+ `drop_table` on downgrade). Round-tripped on a throwaway pgvector DB; live DB rebuilt, never
   host-side `alembic upgrade`.
5. **`app/schemas/wopi.py`** — `CheckFileInfoResponse` (Pydantic, the read-only capability set) +
   pure lock state-machine (`decide_lock(...) -> LockOutcome`) + `EditorSessionResponse`
   (`access_token`, `access_token_ttl` epoch-ms, `wopi_src`).
6. **`app/api/wopi.py`** (NEW bare router, prefix `/wopi`, mounted WITHOUT `_active`) —
   `GET /wopi/files/{file_id}` (CheckFileInfo), `GET /wopi/files/{file_id}/contents` (GetFile,
   `StreamingResponse` via `stream_download` + `X-WOPI-ItemVersion`, 25 MiB cap),
   `POST /wopi/files/{file_id}` (Lock dispatch on `X-WOPI-Override`; `LOCK`+`X-WOPI-OldLock`→
   UnlockAndRelock; 409+`X-WOPI-Lock` echo on mismatch; `PutRelativeFile`→501). Shared
   `_authorize_wopi(...)` helper (token from `?access_token` or `Authorization: Bearer`, prefer query).
7. **`app/api/files.py`** — `POST /{file_id}/editor-session` (under existing `_active` `files.router`,
   owner-scoped `_load_visible_file`) → mints the token + returns `EditorSessionResponse`
   (`wopi_src = {collabora_wopi_host}/api/v1/wopi/files/{file_id}`, no trailing slash → avoids the
   VibeLegalStudio `//contents` quirk by construction).
8. **`app/api/__init__.py`** — mount `wopi.router` bare (precedent: `word_addin.public_router`).
9. **Tests** — `tests/test_wopi.py` (token round-trip + wrong-typ/expired/`fid`-mismatch; CheckFileInfo
   shape + cross-user 404 + bad-token 401; GetFile bytes + `X-WOPI-ItemVersion` + 401; full Lock family
   incl. expired-lock-as-unlocked, 409 echo, `PutRelativeFile`→501) + mint coverage in `tests/test_files.py`
   (200 shape, cross-user/missing → 404). **Meta-tests:** `test_endpoints.py` `IMPLEMENTED_ROUTES` +4;
   `test_openapi.py` `EXPECTED_PATHS` +3 + count **148 → 151**.
10. **`.env.example`** — `COLLABORA_WOPI_HOST` + `WOPI_TOKEN_TTL_SECONDS` (+ post-message origin) in the
    Slice-1 Collabora block. **`docker-compose.yml` needs no change** (defaults are correct in-compose).
11. **Docs** — F047 addendum (decisions above); `MILESTONES.md` S2 ✓; `HANDOFF.md` → pick up Slice 3;
    this plan committed. NOTICES unchanged (no new dependency).

## Non-goals (later slices)
- PutFile / save-back / new `File` version / the 409+`COOLStatusCode 1010` save-race (Slice 3).
- Cockpit editor panel, discovery-XML→`urlsrc` parsing, the hidden-form launch POST, reskin/postMessage,
  the sub-path asset-URL fix (Slice 4). Hand-back → agent resume (Slice 5).
- Proof-key signing; a full script-src/style-src CSP (deferred hardening).

## Verification (DoD — shown, not asserted)
1. Rebuild `api` + `arq-worker` together (migration), `docker image prune -f` (dangling); show
   migration `0074` upgrade→downgrade→upgrade on a throwaway pgvector DB (live DB untouched).
2. Full api suite (dev image, throwaway test DBs) + `test_wopi` + meta-tests green — counts quoted.
   `ruff format && ruff check` (CI-exact, repo-root config) + `mypy app` clean.
3. **Live (dev stack):** mint a token for an owned Atlas file → curl the WOPI host replicating
   Collabora's calls: `GET /api/v1/wopi/files/{id}?access_token=…` → CheckFileInfo JSON (right fields);
   `…/contents` → the `.docx` bytes + `X-WOPI-ItemVersion`; `POST` LOCK/GET_LOCK/REFRESH_LOCK/UNLOCK →
   documented 200/409 + `X-WOPI-Lock`; cross-user token → 404; bad token → 401. Confirm `collabora`→`api`
   reachability on the compose net. (The visual in-iframe open is Slice 4.) Evidence → `docs/fork/evidence/libreoffice-slice2/`.
4. Fresh-context adversarial + security + simplification pass (every slice): token unguessability +
   file/user scoping + cross-file replay + the 404/401 split; lock state-machine correctness; no secrets;
   no gateway reachability; the WOPI surface adds no unauthenticated data leak. Update HANDOFF; squash-merge
   under the ADR-F005 gate.

## Recommended order
config → token (+exports) → model + migration (round-trip on throwaway DB) → schemas (CheckFileInfo +
pure lock SM + session) → wopi.py router → mint endpoint → mount → tests (unit-first on the pure SM) →
meta-tests → .env.example → run full suite + ruff + mypy → live curl smoke → F047 addendum + docs → review → merge.
