# libreoffice-editor Slice 2 — WOPI host (ADR-F047) — evidence

The **read** half of the in-app Word editor: `api` is now a WOPI host so Collabora Online can open a
matter's `.docx`. Slice opens the doc **read-only** (faithful redline viewer, no save path → no
data-loss window); editable + PutFile save-back is Slice 3.

## What shipped
- `app/api/wopi.py` — bare WOPI router (no user-bearer gate): **CheckFileInfo** (`GET /wopi/files/{id}`),
  **GetFile** (`GET …/contents`), the full **Lock family** (`POST …`, dispatched on `X-WOPI-Override`).
- `app/schemas/wopi.py` — `CheckFileInfoResponse` (read-only capability set) + the **pure** `decide_lock`
  state machine + `EditorSessionResponse`.
- `app/security/jwt.py` — `create_wopi_token` / `decode_wopi_token` (`typ="wopi"`, file+user scoped).
- `editor_locks` table (migration **0074**) + the `EditorLock` model.
- `POST /files/{id}/editor-session` — owner-scoped token mint (cross-user → 404).

## Verification
- **Migration 0074 round-trip** (throwaway DB): upgrade → `editor_locks` present → downgrade 0073 →
  gone → re-upgrade → recreated. Clean.
- **Unit + integration:** `tests/test_wopi.py` **34 passed** (token round-trip + wrong-typ/expired/garbage;
  the full `decide_lock` state machine incl. 409-echo / empty-when-unlocked / UNLOCK_AND_RELOCK / 400;
  CheckFileInfo shape + BaseFileName path-stripping + 401/404 splits + Bearer-header acceptance; GetFile
  round-trip + `X-WOPI-ItemVersion`; the lock lifecycle; the **INSERT-race → 409 (not 500)** retry; the
  editor-session mint). Meta-tests `test_endpoints` / `test_openapi` green (count 148 → 151).
- **Full non-provider api suite:** see the PR (re-run on final code).
- `ruff format` + `ruff check` (repo-root config) + `mypy app` (199 files) — clean.

## Live (dev stack, rebuilt api at migration 0074) — `live-smoke.txt`
Replicated Collabora's call sequence with a minted `access_token` against the real api, on the Atlas
matter's redlined `.docx` (`13ad089a-…`, owner admin):
- mint editor-session **200**; `wopi_src = http://api:8000/api/v1/wopi/files/{id}`; `access_token_ttl` epoch ms.
- CheckFileInfo **200** — `BaseFileName` the real redline name, `OwnerId`/`UserId` = uuid **hex** (alphanumeric),
  `Size=40723`, `Version`=hash, `UserCanWrite=false`/`ReadOnly=true`, `UserFriendlyName="LQ.AI Administrator"`,
  no null properties.
- GetFile **200** — bytes match `Size` (40723); `X-WOPI-ItemVersion == Version`.
- Lock family — GET_LOCK(empty) → LOCK(200) → GET_LOCK(returns it) → LOCK-conflict(**409** + current echoed)
  → UNLOCK(200) → GET_LOCK(empty).
- PutFile (Slice 3) → **501**; cross-user token → **404**; bad token → **401**; wrong-file token → **401**.
- **Collabora → api:8000 reachability** (the WOPISrc callback path): `HTTP/1.1 401` — reachable, and the
  host correctly rejects the missing token. (The visual in-iframe open is Slice 4.)

## Adversarial review
4-dimension workflow (security / WOPI-protocol / correctness-data / conventions-simplification), each
finding independently refuted: **13 findings → 9 confirmed (1 should-fix, 8 nits), 4 refuted.** The
should-fix (lock INSERT-race → duplicate-PK 500) was fixed with a re-resolve/retry loop (loser re-decides
to a correct 409/refresh) + a deterministic test. Folded nits: dead logger removed; `BaseFileName`
basename-stripped at the seam (CVE-2025-27791 posture); module-level `get_settings`; two docstrings.
Accepted/deferred (documented): proof-key validation (ADR-F047 addendum); expired-lock sweep (bounded,
overwritten/cascade-deleted).
