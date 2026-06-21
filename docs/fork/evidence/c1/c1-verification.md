# C1 verification — document-reader registry (ADR-F029)

Slice **C1** replaces the single PDF MIME gate with an injected `MIME→reader` registry so a matter ingests the
formats a deal arrives in (DOCX/XLSX/PPTX/EML), each returning the existing `ParsedDocument`. The chunker,
`Document`/`DocumentChunk` models, and the persist path are untouched, so the Citation-Engine invariant
`normalized_content[start:end] == chunk.content` holds for every reader by construction.

## Automated (CI-parity, containerized api image)

- **ruff** (CI version 0.15.18): `format --check` + `check` clean on the readers pkg, `ingest.py`, `parsers.py`,
  and both test files.
- **mypy** (targeted, readers + ingest): `Success: no issues found in 8 source files`.
- **Full api suite:** `2476 passed, 2 skipped`. The single non-pass is
  `test_health.py::test_ready_reports_per_dependency_status`, which asserts a **503 / not_ready** because it
  assumes DB/Redis/MinIO/gateway are *unreachable* (unit mode); the run was inside the live `lq-ai_default`
  compose network so `/ready` was healthy → the assertion flips. It is unrelated to the ingest path and passes
  in CI's isolated mode.
- **New reader tests** (`tests/test_readers.py`): per-format offset invariant + tiling unit-spans, registry
  dispatch (case/param), per-reader `sniff` spoof-rejection, `guard_ooxml` DOCTYPE/ENTITY + zip-bomb across all
  OOXML, the **fitz import-guard** (no reader imports `fitz`), EML non-recursion / HTML-strip / plain>html,
  **malformed-OOXML-fails-closed**, and empty-document degradation. Plus 5 per-format ingest e2e in
  `tests/test_pipeline_ingest.py` asserting fidelity against the persisted `normalized_content`.

## Live (real rebuilt image + real MinIO + real DB)

Ran `ingest_file` against real MinIO-backed storage and the real DB, through the deployed image's readers
(confirming `python-docx`/`python-pptx` are installed in the worker image), for one fixture of each format,
then cleaned up:

```
  live.docx  status=ready   parser=python-docx   chunks= 1 fidelity=OK
  live.xlsx  status=ready   parser=openpyxl      chunks= 1 fidelity=OK
  live.pptx  status=ready   parser=python-pptx   chunks= 1 fidelity=OK
  live.eml   status=ready   parser=eml           chunks= 1 fidelity=OK
  cleanup: done
```

`fidelity=OK` = every persisted chunk slices back byte-for-byte from `normalized_content`.

## Review

A 28-agent fresh-context adversarial review (security / correctness / simplification / tests / docs, each
finding independently verified) returned **SHIP** with zero blockers. Two should-fixes were applied before
merge: (1) the three OOXML readers now **fail closed** — they wrap library errors as `ParserError` so a
malformed-but-sniff-passing file becomes `parse_failed` rather than a retriable worker error (matching the
PDF path + the documented worker contract); (2) added an EML plain-vs-HTML preference test. Nits folded
(shared `build_parsed_document` helper, DOCTYPE tests across all OOXML, empty-doc cases, multi-sheet span
assert, format-agnostic `ParsedDocument` docstring). 12 findings were dropped as not-real or out-of-scope.
