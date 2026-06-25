# Plan — LibreOffice editor **Slice 3**: PutFile save-back (the editable half)

> Status: **SHIPPED (2026-06-25), branch `fork/libreoffice-editor-slice3`.** Decisions recorded as the
> **ADR-F047 Slice-3 addendum**. The version-model decision flagged below was resolved by the maintainer at
> kickoff (AskUserQuestion): **(B) snapshot-then-mutate.** Two plan corrections found during build, both
> applied: (1) `guard_ooxml` **already exists** (`app/pipeline/readers/_base.py`) — REUSED, no new helper;
> (2) WOPI coherence is about the **row id** (in the `WOPISrc` URL), not the storage key, so the ADR-0005
> `key == id` convention is kept for BOTH rows (snapshot via a server-side `copy_object`, live overwrite in
> place) and a nullable **`files.updated_at`** (migration `0075`) was added so `LastModifiedTime` is honest
> after an in-place save and the `1010` save-race check is meaningful.

## Context

Slice 2 made `api` a WOPI host for the **read** half (CheckFileInfo / GetFile / Lock family) and opened the
doc **read-only** (`UserCanWrite=false`). Slice 3 is the **write** half: the lawyer edits in Collabora and
the changes **save back** through `PutFile`, under the lock the session holds. After Slice 3 the doc is
genuinely editable (no data-loss window — read + write now both exist).

The agent-resume loop (Slice 5) and the cockpit UI (Slice 4) still come after; Slice 3 is backend only.

## Scope (one PR, backend only)

1. **PutFile** — `POST /wopi/files/{file_id}/contents` with header `X-WOPI-Override: PUT`, body = the full new
   `.docx`. (Same path string as GetFile — this adds the **POST** method to the existing `/contents` route.)
   - **Lock enforcement:** if the file is locked, the request's `X-WOPI-Lock` must match the held lock, else
     **409 + `X-WOPI-Lock`** (current lock echoed) — reuse/extend the Slice-2 lock-resolution + a small pure
     check (mirrors `decide_lock`). An unlocked file: WOPI permits PutFile (Collabora locks first in practice).
   - **OOXML guard + size cap:** validate the body is a real OOXML zip (`zipfile` opens it + has
     `[Content_Types].xml`) and ≤ `lq_ai_max_upload_size_mb`; reject (400/413) otherwise. (No `guard_ooxml`
     exists yet — add a small `app/...` helper; do NOT trust the bytes — they came from the browser.)
   - **Version bump:** the new content hash becomes the file's `Version` / `X-WOPI-ItemVersion` (returned).
2. **Flip CheckFileInfo to editable** — `UserCanWrite=true`, `SupportsUpdate=true`, drop `ReadOnly`. (A
   `view`/`edit` toggle can come from the mint endpoint later; Slice 3 makes the session writable.)
3. **Save-race backstop (VibeLegalStudio prior art):** honor `X-COOL-WOPI-Timestamp` — if the stored file
   changed since the editor loaded it (e.g. the agent re-wrote it), return **409 + `{"COOLStatusCode": 1010}`**
   ("document changed in storage") so the editor warns rather than clobbers. Put a JSON `LastModifiedTime` in
   the PutFile response (the documented Collabora quirk).
4. Counts-only audit on the save (`editor.file_saved`, IDs only).

## Decision to resolve at kickoff — the **version model** (needs maintainer call + ADR-F047 addendum)

WOPI expects `file_id` to keep serving the **latest** content (the editor holds one `WOPISrc` for its whole
session). That tensions with the fork's **immutable-File** convention (ADR-0005: object key = `str(file_id)`,
soft-delete only). Options:

- **(A) Mutate in place (WOPI-canonical, recommended for coherence).** PutFile overwrites the File's MinIO
  object (key stays `str(file_id)`), updates `hash_sha256` (new `Version`) + `size_bytes`. The editor stays
  coherent across reloads. **Cost:** the pre-edit redline bytes are overwritten unless snapshotted.
- **(B) Snapshot-then-mutate (recommended if history matters).** Before overwriting, copy the current bytes to
  a NEW `File` row (the preserved prior version, surfaces in the C7a Documents tab), then mutate the live row
  as in (A). Keeps `file_id` stable AND preserves history. Mirrors the matter-memory `wiki_snapshot` pattern.
  **Cost:** a little more plumbing + a storage copy per save.
- **(C) New row only.** Rejected — leaves the editor's `file_id` serving stale bytes on reload (incoherent).

Provenance question (couples to the above): the File started as the agent's redline (`created_by_run_id=run`).
After the first human save it is human-touched — null it, keep it, or record an `edited_by_user` audit trail?
**Recommendation:** **(B)** — snapshot the agent's redline as the immutable prior version (provenance intact),
mutate the live row for the editable doc, and leave `created_by_run_id` on the live row but rely on the audit
row for the human-edit trail. Confirm at kickoff.

## Files (anticipated)
- `app/api/wopi.py` — the `PUT` branch in `wopi_file_operation` dispatch (it already 501s `PUT` today) → real
  PutFile handler; lock check; OOXML guard; Version bump; 1010 backstop. Flip `CheckFileInfoResponse` caps.
- `app/schemas/wopi.py` — editable capability set; a pure PutFile lock-precondition check; the 1010 response shape.
- `app/storage.py` — reuse `upload_bytes` (overwrite the key) [+ a `copy_object` helper if (B)].
- A small OOXML-sniff guard (zip + `[Content_Types].xml`).
- (B) a snapshot `File` row writer.
- Tests: `tests/test_wopi.py` — PutFile happy path (bytes persist, Version bumps, GetFile returns the new
  bytes), lock-mismatch 409, unlocked-allowed, non-OOXML 400, oversize 413, the 1010 timestamp backstop, the
  editable-caps flip; meta-test: **IMPLEMENTED_ROUTES += ("POST", "/api/v1/wopi/files/{file_id}/contents")**
  (the path already exists in `EXPECTED_PATHS` → **no count bump**).
- Migration: only if (B) needs a new column (it doesn't — a snapshot is a plain `File` row); likely **no
  migration**. Confirm at kickoff.

## Verification (DoD)
Migration round-trip if any; full non-provider api suite + `test_wopi` + meta-tests; `ruff` + `mypy` clean;
**live** (rebuilt api): mint editable session → PutFile a modified `.docx` (lock held) → GetFile returns the
new bytes + bumped `X-WOPI-ItemVersion`; lock-mismatch 409; non-OOXML rejected; the saved version visible in
the C7a Documents tab. Fresh-context adversarial + security pass (untrusted upload bytes are the new surface —
OOXML guard, size cap, lock enforcement, no path traversal, no overwrite of another user's file). The real
in-Collabora visual (a human editing + Ctrl-S round-trip) lands with the **Slice-4** cockpit editor.

## Non-goals
Cockpit editor UI + reskin + the browser-facing proxy/asset-URL fix (Slice 4). Agent hand-back/resume (Slice 5).
PutRelativeFile / RenameFile (stay 501).
