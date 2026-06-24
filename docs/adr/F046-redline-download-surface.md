# F046 — Redline work-product download surface + run provenance

- Status: proposed
- Date: 2026-06-24
- Deciders: maintainer (Arturs), agent
- Slice: C7a (first sub-slice of the commercial milestone's C7)

## Context

The commercial agent's primary work product is a **redlined `.docx`** with native tracked
changes (C4/C8/C9, ADR-F031/F041/F045). `apply_redline` already persists it as a matter-scoped
`File` (owner + `project_id`, bytes in MinIO) and audits the creation — but the resulting
`file_id` **never reached the UI**. It lived only in the audit row, so the lawyer could not
download the document they asked the agent to produce. The work product was stranded; this was
repeatedly the most-requested gap.

C7 as decomposed (`docs/fork/plans/COMM-commercial-deep-agent-decomposition.md`) bundled three
features — a drafter/reviewer **fan-out roster**, a **deal-context live signal**, and the
**redline-download UI** — into one ~3-day slice, past the fork's ≤2–3-day one-PR discipline. The
maintainer chose to ship the download surface first as **C7a** and defer the fan-out roster
(→ C7b) and the accept/reject/counter classification + live signal (→ C5, where the classification
concept lives).

Two facts shaped the design, found by mapping the subsystems first:
1. `GET /api/v1/files/{file_id}/content` **already** streams a file's bytes, owner-scoped (404 on
   cross-user, never 403), with an `attachment` `Content-Disposition`. The actual download needs
   no new bytes path — only a way to *find* the file and a UI affordance.
2. `AgentRunStep` carries only a bounded text `summary` — there is **no structured-output channel**
   on a step or in the SSE protocol. Surfacing the created `file_id` inline by threading a new
   structured-artifact frame through step row → SSE → web parser would be a protocol change well
   beyond a download button.

Blocker #6 in CLAUDE.md ("`work_product_attributions` assumes one inference per message — breaks
under fan-out") is a **legacy-chat** concern: agent runs do not write `work_product_attributions`;
they use the `agent_run_steps` tree (which nests correctly via `parent_step_id`). It does not block
this slice and is left to the fan-out slice (C7b) if it ever needs the attribution table at all.

## Considered options

1. **One matter-files listing endpoint + a `created_by_run_id` provenance column, feeding both the
   Documents tab and the inline button.** A nullable `File.created_by_run_id` FK ties an output to
   the run that made it; one read endpoint returns the matter's files; the tab lists all of them and
   the inline button filters the same data to the current run's outputs.
2. **Structured-artifact channel on steps + SSE.** Add an `artifacts`/`files_created` field to the
   step row, serialize a new `data-*` frame, parse it in `run-stream.ts`, render inline. Precise and
   "in-the-moment", but a protocol change that touches the settled-rows-decide contract (ADR-F004)
   and the SSE surface (CLAUDE.md blocker #4) for what is fundamentally a download link.
3. **Filename/recency heuristic, no schema change.** Inline shows "the matter's newest `(redlined)`
   file". Migration-free, but the inline button can't be tied to a *specific* run (wrong after a
   second redline, or with concurrent runs) — not an honest receipt.

## Decision outcome

**Chosen: option 1.**

- **`File.created_by_run_id`** — additive-nullable FK → `agent_runs.id`, `ON DELETE SET NULL`
  (migration `0071`, no backfill). NULL for human uploads; set when `apply_redline` persists its
  output (`run_id` is already in scope at the tool-build site). Honest work-product → run
  provenance; the inline button is precise, not heuristic.
- **`GET /api/v1/matters/{project_id}/files`** — a new read-only listing on the owner-scoped
  `/matters` router (mirrors `matter_memory.py`; `_load_visible_project` → 404 on
  cross-user/archived). Returns file **metadata only** (id, filename, mime, size, status,
  `created_at`, `created_by_run_id`), newest-first, scoped to the matter (membership union + owner
  re-assertion + not soft-deleted — the same set the agent reads). No bytes, no document content.
- **Download reuses the existing `GET /files/{id}/content`** (no new bytes path). The web client
  gains a `downloadFile` helper (blob → object URL → `<a download>`) and `listMatterFiles`.
- **Both surfaces from the one endpoint:** a cockpit **Documents** tab lists every matter file with
  a Download button; the conversation timeline shows an inline Download under each completed run,
  filtered to that run's outputs (`created_by_run_id === run.id`).
- **The SSE protocol and the settled-rows-decide contract are untouched.** No new step field, no new
  frame type.

## Consequences

- The lawyer can download the redline work product from a persistent tab and inline after a run —
  the stranded-output gap is closed without a protocol change.
- One small migration (one nullable column) requires the usual rebuild of `api` + `arq-worker` +
  `ingest-worker`; the column is purely additive and reads NULL for every existing row.
- `created_by_run_id` is generic provenance ("which run produced this file"), reusable beyond
  redlines (any future agent file output).
- The Documents tab is **read + download only** — no upload/delete/rename here (those live on the
  existing files/projects surfaces). Redline outputs are **not** re-ingested or indexed (work
  product, not a search source) — unchanged from C4.
- This ADR folds the decomposition's stale **F034** reservation ("redline-download surface"); the
  actual fork ADRs ran F042–F045, so the download surface takes the next free number, F046. The
  fan-out roster (C7b) and the classification/live-signal (C5) remain unbuilt and will get their own
  ADRs if they make architectural calls.
