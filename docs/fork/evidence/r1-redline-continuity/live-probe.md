# R-1 live verification — redline continuity (ADR-F066)

2026-07-08, dev stack (rebuilt api/arq/ingest images off `r1-redline-continuity`; mig 0089 auto-applied
on boot). Probe: in-container script driving the REAL `_apply_redline` (real `RedlineService`/Adeu, real
MinIO, live dev DB — no LLM) on a throwaway user+matter with a seeded two-clause .docx; cleaned up in
`finally`.

## Result — 6/6 PASS

| Check | Result |
|---|---|
| Call 1 (`apply_redline` on `r1-probe.docx`) applies to the ORIGINAL, no continuity note | PASS |
| Call 2 (same name) carries the continuity note — `Continued from your latest working version "r1-probe (redlined).docx" (derived from "r1-probe.docx"); pass start_fresh=true to redline the original instead.` — and applied to v1 (its tracked changes preserved: 3 tracked regions) | PASS |
| Lineage: `r1-probe (redlined).docx`.parent = original | PASS |
| Lineage: `r1-probe (redlined v2).docx`.parent = v1 | PASS |
| `resolve_working_docx("r1-probe.docx")` leaf = v2 | PASS |
| `start_fresh=true` redlines the original again, no continuity note | PASS |

Version-aware naming observed live: `(redlined)` → `(redlined v2)`.

## Deterministic gate (same branch)

- Full containerized api suite: **3387 passed, 47 skipped** (13m32s; repo-root + /skills mounts,
  DATABASE_URL from the running api container). Baseline was 3369 — the delta is this slice's tests.
- Migration 0089 up/down/up on a THROWAWAY pgvector container (never the live DB): head reached,
  downgrade + re-upgrade clean; `\d files` shows `parent_file_id uuid` + `fk_files_parent_file_id …
  ON DELETE SET NULL` + `ix_files_parent_file_id` + `is_snapshot boolean NOT NULL DEFAULT false`.
- ruff (repo-root config) + `mypy app` clean (223 files) — re-verified after the fix pass.
- Adversarial review (3 lenses): 3 should-fixes (greedy-walk → breadth-first newest non-snapshot LEAF;
  bounded `v(\d{1,8})` version parsing vs hostile filenames; shared `_DOCX_COLUMNS` projection) —
  ALL applied, nothing deferred; 6 nits triaged.

## Probe honesty notes

- The probe's apply calls ran inside one session whose final state was rolled back on close (only the
  pre-committed seed rows persisted), so the redlined File ROWS never reached the durable dev DB —
  cleanup verified 0 leftovers. The redline .docx OBJECTS were uploaded to dev MinIO before rollback,
  so ≤3 small orphaned objects (no DB references) remain in the dev bucket — cosmetic, dev-only.
- The craft gate (ADR-F041, D1/D2) initially REJECTED the probe's toy edits (short rationale, over-
  broad strike) — evidence the surgical gate still guards the new resolution path; the passing probe
  uses ≥15-word rationales against realistic clause text.
