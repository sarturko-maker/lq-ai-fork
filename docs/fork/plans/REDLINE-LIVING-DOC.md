# REDLINE-LIVING-DOC — further redlines converge on one living document (ADR-F081)

Status: **IMPLEMENTED in this slice's PR.** Maintainer bug report 2026-07-11: *"if the user asks to
further redline, the agent creates a NEW document … the agent should redline continuously over the
same redline, because the user may ask to change and improve things a hundred times before taking
the document."*

## Diagnosis

Input continuity already exists (R-1, ADR-F066): `resolve_working_docx` walks `parent_file_id`
lineage to the newest non-snapshot leaf, so a follow-up `apply_redline` builds ON the previous
redline's bytes. But the **output never converges**: `_apply_redline` always mints a NEW `File` row
(`contract (redlined).docx` → `(redlined v2)` → …), so every round lands a new document in the
Documents tab and the web opens a new Collabora editor. The in-repo precedent for the right shape is
WOPI PutFile (ADR-F047 Slice 3): **snapshot-then-mutate** — the live row keeps its id, bytes update
in place, an immutable snapshot preserves the prior version at the authorship boundary.

## Goals

1. A follow-up `apply_redline` (default, `start_fresh=False`) whose resolved working head is a
   **derived work product** updates that row **in place** — same file id, same filename, same
   storage key — so the matter keeps ONE living redlined document.
2. Symmetric data safety: when the head's bytes are **human-authored** (the lawyer edited in
   Collabora since the agent's last write: `created_by_run_id IS NULL`), the prior bytes are
   preserved first as an immutable `is_snapshot` row — the exact mirror of WOPI PutFile's
   snapshot-on-first-human-save.
3. Round-2+ web UX keeps working: the redline auto-open/announce (today keyed on *new file id*,
   which an in-place update never produces) re-fires on content change; an open editor refreshes
   (auto when pristine, banner when dirty).
4. Original uploads are NEVER mutated; `start_fresh=true` still branches a NEW redline document
   from the original (now with a matter-unique name — fixes the pre-existing duplicate-name wart).

## Non-goals

- `respond_to_counterparty` stays new-row-per-round (deliberate: each response is the per-round
  OUTBOUND artifact — a record of what was dispatched, arguably immutable; and its resolution path
  has no lineage walk, so convergence there is a different predicate). Follow-up recorded for its
  duplicate-name quirk.
- No refusal when a Collabora editor lock is held — the lock is held during the *primary* UX
  (chat beside the open viewer), so refusing would break the exact flow being fixed; the WOPI
  `X-COOL-WOPI-Timestamp` backstop (409/1010) keeps concurrent saves warn-not-clobber, and
  snapshots at authorship boundaries keep byte history recoverable.
- No SSE work-product frame (the poll-driven surfacing stays); no per-run file link table; no
  org-wide document-versioning entity (MILESTONES backlog; ADR-F066's option-4 escape hatch).

## Design (ADR-F081 — amends ADR-F066 in part)

**Persist decision in `_apply_redline`** (after render): re-fetch the resolved head as a locked ORM
row (`SELECT … FOR UPDATE` — the render projection lacks lineage/provenance columns, and the lock
closes the resolve→persist TOCTOU window), then:

- head is derived (`parent_file_id IS NOT NULL AND NOT is_snapshot`) and not `start_fresh`
  → **update in place**, guarded by a hash CAS: if the head's `hash_sha256` no longer equals the
  hash of the bytes the redline was rendered over, reject with fix-and-retry (never clobber a
  concurrent write).
- otherwise (root upload, explicitly named snapshot, or `start_fresh`) → **create a new derived
  row** exactly as today, with a matter-unique `(redlined)`/`(redlined vN)` name.

**Two durable steps** (mirrors wopi.py / ADR-F047 §data-safety ordering):

1. *(only when the head is human-authored)* `copy_object` the live bytes to a snapshot key → insert
   the `is_snapshot=True` row (name `<stem> (lawyer draft).docx`, `created_by_run_id=None` — the
   preserved bytes are the lawyer's) → flip the head's `created_by_run_id = run_id` → **commit**;
   on failure, delete the orphan snapshot object and raise. Flipping provenance in step 1 means a
   retry after a step-2 failure can never re-snapshot overwritten bytes (same rationale as WOPI).
2. Overwrite the live object at the head's own `storage_path` (key reuse is load-bearing — no GC
   exists; a new key would leak the old object) → bump `hash_sha256`/`size_bytes`/`updated_at`
   (the `updated_at` bump is load-bearing twice: the lineage resolver's
   `coalesce(updated_at, created_at)` leaf pick, and WOPI's save-race backstop) → set
   `created_by_run_id = run_id` → audit `commercial.redline_applied`
   (details += `updated_in_place`, `redlined_sha256`, `snapshot_file_id`) → **commit in the tool
   body** (not guard-deferred: the guard's failed-audit rollback path must not be able to discard
   the row bump after the object is already overwritten).

**Provenance semantics change (documented in F081):** `created_by_run_id` becomes "the run that
last wrote the bytes" (was "the run that created the row"). The run timeline chip follows the
living document to the latest run; earlier runs keep their audit rows (which now carry the
per-apply result hash). WOPI's snapshot-on-human-save keys on the same flag and re-arms correctly.

**Web companion (required, else round-2+ auto-open silently dies):**
- `MatterFileRead` grows `updated_at`; announce/dedupe key becomes `id:updated_at` so an in-place
  update re-fires `redlineready`; `isRedlineOutput` regex accepts `(redlined vN)`.
- `ConversationHost`/`DocumentEditorPanel`: a `redlineready` for the *currently open* file reloads
  the editor (re-mint session) when pristine; shows a "the agent updated this document — reload"
  banner when the editor is dirty.
- Documents tab renders `updated_at ?? created_at`.

**Adjacent hazard fixed:** `GET /files/{id}/content` pinned `Content-Length` from the row while
streaming from storage — already documented as unsafe under in-place mutation by WOPI GetFile;
now that a second in-place mutator exists, drop the pinned header the same way.

## Files

- `api/app/agents/commercial_tools.py` — persist branch, `_unique_redlined_filename`,
  `_lawyer_draft_filename`, CAS, messages/docstrings.
- `api/app/agents/tools.py` — `_DOCX_COLUMNS` += `parent_file_id`, `is_snapshot` (note wording).
- `api/app/api/matter_files.py` (+`updated_at`), `api/app/api/files.py` (Content-Length),
  `api/app/models/file.py` (comment).
- `web/src/lib/lq-ai/`: `types.ts`, `api/editor.ts`, `components/agents/ConversationPanel.svelte`,
  `cockpit/ConversationHost.svelte`, `components/matter/DocumentEditorPanel.svelte`,
  `components/matter/DocumentsPanel.svelte`.
- `skills/surgical-redline/SKILL.md`, `api/app/agents/composition.py` doctrine sentence.
- `docs/adr/F081-living-redline-document.md` (new), F066 status pointer, F047 addendum,
  `docs/fork/plans/PIVOT-modular-azure.md` §R note.
- Tests: `api/tests/agents/test_commercial_tools.py` (rewrites + new branch matrix),
  `api/tests/test_matter_files_api.py`, `api/tests/test_files_endpoints.py`, web vitest.

## Verification

- Containerized api + web suites (counts quoted; repo-root mount; run ALONE on this box).
- Live: fresh matter → upload → redline → "further redline" → Documents tab shows ONE living
  `(redlined)` doc with accumulated tracked changes; screenshot evidence.
- Fresh-context adversarial review incl. security pass (two-durable-steps ordering, CAS, no
  cross-matter leak via the PK re-fetch, no secrets) + simplification pass.
