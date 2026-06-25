# libreoffice-editor Slice 3 — PutFile save-back (ADR-F047) — evidence

The **write** half of the in-app Word editor: `api` now accepts the lawyer's edited `.docx` back over
WOPI `PutFile`, so the document is genuinely editable (read + write both exist). The session is editable
(`UserCanWrite=true`); the cockpit launch UI + the in-iframe visual are Slice 4.

## What shipped
- `app/api/wopi.py` — **PutFile** handler (`POST /wopi/files/{id}/contents`, `X-WOPI-Override: PUT`):
  lock precondition → save-race backstop → untrusted-body validation → **snapshot-then-mutate** → 200.
- `app/schemas/wopi.py` — editable `CheckFileInfoResponse` caps (`UserCanWrite`/`SupportsUpdate`/`ReadOnly`)
  + the pure `decide_putfile_lock` precondition.
- `app/models/file.py` + migration **0075** — nullable `files.updated_at` (honest `LastModifiedTime`).
- `app/storage.py` — `copy_object` (server-side snapshot copy).

## Version model (maintainer's call) — snapshot-then-mutate
On the FIRST human save of an agent redline (`created_by_run_id` set), the agent's current bytes are
copied to a NEW immutable `File` row (`(agent draft)`, provenance carried over → visible in the C7a
Documents tab, key == row id per ADR-0005) BEFORE the live object is overwritten; the live row keeps its
WOPI id, mutates in place (new `hash`/`size`/`updated_at`), and flips to `created_by_run_id = NULL`. Later
saves mutate in place; a no-op autosave (identical hash) writes nothing. Copy-first is the data-safety
invariant — the old bytes survive at the snapshot key before the live overwrite, so no crash loses them.

## Verification
- **Migration 0075 round-trip** (throwaway DB): upgrade 0074→0075 → `files.updated_at` present → downgrade
  → gone → re-upgrade → present. Clean (see `migration-roundtrip.txt`).
- **Unit + integration:** `tests/test_wopi.py` (PutFile happy-path mutate-in-place, snapshot-on-first-save,
  second-save-no-resnapshot, lock-mismatch 409, unlocked-allowed, non-OOXML 400, non-docx 400, oversize
  413, save-race 1010, matching-timestamp proceeds, no-op identical bytes, 401/404 splits, non-PUT 501,
  pure `decide_putfile_lock`). `tests/test_storage_streaming.py` (`copy_object`/`put_object` fake). Meta:
  `test_endpoints` IMPLEMENTED_ROUTES += the PutFile method (no OpenAPI count bump — same path string).
- **Full non-provider api suite** — see `suite.txt` (counts quoted in the PR).
- `ruff format` + `ruff check` (repo-root config) + `mypy app` (199 files) — clean.

## Live (dev stack, rebuilt api at migration 0075) — `live-smoke.txt`
Replicated Collabora's PutFile against the real api on an Atlas redline `.docx`: mint editable session →
LOCK → PutFile (edited bytes, lock held) → GetFile returns the new bytes + bumped `X-WOPI-ItemVersion`;
the agent's redline preserved as a `(agent draft)` snapshot; lock-mismatch → 409; non-OOXML → 400; the
save-race timestamp → 409 `{"COOLStatusCode":1010}`. The in-iframe visual round-trip is Slice 4.

## Adversarial review
See the PR. Security focus: the PutFile body is untrusted browser input — size cap, `guard_ooxml`
(zip-bomb/XXE), `.docx` subtype enforcement, lock enforcement, owner-scoped 404, no path traversal (the
storage key is server-derived `str(id)`), no overwrite of another user's file. Data-safety: copy-first
snapshot ordering; snapshot orphan kept (not deleted) on a post-overwrite failure.
