# Plan — C7a: Redline-download surface (inline + matter Documents tab)

**Status: implemented** (branch `fork/c7a-redline-download`; ADR-F046; migration `0071`).

## Goal

A supervising lawyer can **download the redlined `.docx`** the commercial agent produces — both
**inline** in the run timeline (right after the redline) and from a persistent matter **Documents**
tab. Today the redlined file is persisted + audited but never surfaced: the agent's primary work
product is stranded.

## Scope (maintainer's decision)

C7 as decomposed bundled three features into one ~3-day slice. Shipped here = **C7a, redline-download
only**. Deferred: the drafter/reviewer **fan-out roster → C7b**; the accept/reject/counter
**classification + deal-context live signal → C5**. No subagent roster, no SSE-frame change, no
orchestration in this slice. Download UX = **both** an inline timeline button and a Documents tab
(AskUserQuestion, 2026-06-24).

## What already existed (reused, not rebuilt)

- `apply_redline` persists the redlined `.docx` as a matter-scoped `File` (`commercial_tools.py`).
- `GET /api/v1/files/{file_id}/content` streams the bytes, owner-scoped 404, `attachment` header.
- The cockpit tab pattern (Memory tab, C3c-2): `ConversationHost` derived `matterTabs` + no-remount.

## Design

**Backend**
- `File.created_by_run_id` — nullable FK → `agent_runs.id` (`ON DELETE SET NULL`), migration `0071`,
  additive/no-backfill. `_apply_redline` stamps it (run_id already in scope). Precise run→file
  provenance for the inline button (not a filename heuristic).
- `GET /matters/{project_id}/files` — new `api/app/api/matter_files.py`, owner-scoped via
  `_load_visible_project` (404 cross-user/archived). Metadata only, newest-first, membership-union
  scope (mirrors `tools._matter_files_query`).

**Web**
- `files.ts`: `downloadFile(id, filename?)` (blob → object URL → `<a download>`) + pure
  `pickDownloadFilename`. `matterFiles.ts`: `listMatterFiles(projectId)`. `types.ts`: `MatterFile`.
- `DocumentsPanel.svelte` (new) — list rows + Download buttons; loadGeneration/poll/reloadKey guards
  (mirror MemoryPanel); pure helpers in `<script module>` for vitest; empty state.
- `ConversationHost.svelte` — `'documents'` tab whenever a matter is set; conversation region stays
  MOUNTED behind `class:hidden` (no-remount invariant); sibling `{#if}` panel; reset-on-leave.
- `ConversationPanel.svelte` — inline Download under each completed run, filtered to
  `created_by_run_id === run.id` (refetched when the completed-run set changes).

## Non-goals

Fan-out roster (C7b) · classification + deal-context live signal (C5) · structured-artifact channel
on steps/SSE (protocol unchanged) · re-ingest/search of redlines · presigned URLs · general
file-manager (upload/delete/rename). Read + download only.

## ADR

ADR-F046 — download surface + run provenance; reuse `/files/{id}/content`; one endpoint feeds both
surfaces; why not a step-level artifact channel; folds the stale F034 reservation.

## Verification (ADR-F005 DoD)

- Backend: endpoint 404 cross-user/archived; registered in `test_endpoints.py` + `test_openapi.py`
  (count 147→148); migration idempotent + downgrade on a throwaway pgvector container;
  `apply_redline` sets `created_by_run_id` (unit test); containerized api suite; ruff + mypy.
- Web: vitest helpers; `npm run check` 0 errors; prettier/eslint on touched files. Rebuild `web`,
  headed Cypress (Documents render + download round-trip + inline). Screenshots → `evidence/c7a/`.
- Live: rebuild `api`+`arq-worker`+`ingest-worker`; Atlas matter — run a redline, confirm it appears
  in the tab and inline, download, open in Word. `docker image prune -f`.
- Adversarial + security + simplification pass; HANDOFF + memory updated; squash per ADR-F005.
