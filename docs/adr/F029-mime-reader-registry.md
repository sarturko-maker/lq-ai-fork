# F029 — Multi-format ingestion via an injected MIME→reader registry

- Status: accepted (2026-06-21, with slice C1)
- Date: 2026-06-21
- Extends/supersedes: **ADR-0006** (document pipeline architecture) — inherits its offset-fidelity
  contract verbatim; supersedes only its PDF-only *scope*.
- Relates: ADR-F028 (Commercial method doctrine — the agent that consumes these documents), the
  Citation Engine offset invariant (`normalized_content[start:end] == chunk.content`, M2-A1).
- Milestone: COMMERCIAL — slice **C1**. C2 extends this ADR (email-chain / `.msg` / nested attachments).

## Context

ADR-0006 fixed a **PDF-only** pipeline: `ingest_file` hard-imports `parse_pdf`/`is_pdf_mime` from
`app.pipeline.parsers`, rejects any non-PDF MIME up front, and treats PyMuPDF's character stream as the
canonical text the chunker slices. A Commercial deal, though, arrives as **DOCX/XLSX/PPTX/EML**, not just
PDF. Two things block multi-format ingest today: (1) the single `is_pdf_mime` gate, and (2) the
hard-coded `parse_pdf` call — there is no composition root or DI seam for parsing anywhere (the worker
`on_startup` and the API lifespan wire the skill registry and the queue, but no parser registry).

Three constraints bound any fix:
- **The Citation Engine offset invariant is non-negotiable.** Every chunk must slice back to its content
  byte-for-byte against `Document.normalized_content` (= the canonical text). It must hold for *every* new
  format, not just PDF.
- **No copyleft in new dependencies** (CLAUDE.md rule B). PyMuPDF (`fitz`) is already AGPL, held under a
  documented server-side-only boundary (ADR-0006); we must not *widen* that surface.
- **Untrusted input.** Documents — and especially OOXML files (zip containers of XML) and email bodies —
  are untrusted model/parse input: XXE, entity-expansion (billion-laughs), remote-template/SSRF, zip-bomb,
  and prompt injection downstream.

## Considered Options

**1. How new formats reach the pipeline**
- A. **Widen `is_pdf_mime` and branch inside `parse_pdf`.** Rejected — grows a god-function, couples the
  AGPL `fitz` import to every format, gives no DI seam, and is hard to test.
- B. **Per-format top-level functions imported conditionally in `ingest_file`.** Rejected — still a
  hard-coded `if/elif` gate, no injection, scatters MIME knowledge across the orchestrator.
- C. **An injected `MIME→reader` registry of `DocumentReader` objects, each returning `ParsedDocument`
  (chosen).** A `ReaderRegistry` is built once by `build_default_registry(settings)` and threaded into
  `ingest_file` (defaulting to the builder, so every existing caller is unchanged); tests substitute fakes
  through the same seam. Matches the fork's DI exemplar, contains `fitz` to one reader, and leaves the
  chunker / `Document` / `DocumentChunk` / persist path untouched.

**2. XML hardening for OOXML (XXE / entity-expansion / remote template)**
- A. **`defusedxml` injected into python-docx/python-pptx's lxml parser.** Rejected — the libraries use
  lxml internally with no clean, version-stable seam to swap the parser; it would add a dependency for a
  guarantee we can get without one.
- B. **Reject `<!DOCTYPE`/`<!ENTITY` in each OOXML XML-part prolog *before* the parsing library opens the
  file, dep-free (chosen).** Valid OOXML never declares a DTD, so this is a true-positive-only reject; doing
  it before `docx.Document(...)`/`Presentation(...)` means lxml never sees an entity to expand. Combined with
  a decompressed-size + entry-count cap (zip-bomb) and a bounded prolog read (defeats a lying central
  directory). External entities/templates are never *fetched* because we never resolve external
  relationships — the DOCTYPE reject closes the entity vector.

**3. Server-side type verification**
- A. **Add the `filetype` magic-sniff library.** Rejected — all OOXML share the zip magic `PK\x03\x04`, so a
  generic magic sniff can't tell `docx` from `xlsx` from `pptx`; it would add a dependency and still need a
  deeper check.
- B. **A per-reader `sniff(bytes)` content cross-check, dep-free (chosen).** PDF checks the `%PDF` magic;
  OOXML readers read the in-zip `[Content_Types].xml` and confirm the main-part content type matches the
  declared subtype (so a `.xlsx` renamed `.docx` is caught); EML (plain text, no reliable magic) accepts the
  declared type. A declared/sniffed mismatch at the boundary is rejected as `unsupported_type`.

## Decision Outcome

Adopt **1C + 2B + 3B**. Introduce `app/pipeline/readers/` — a `DocumentReader` protocol
(`mimes`, `sniff`, `read`), a `ReaderRegistry`, and `build_default_registry(settings)` — and change
`ingest_file(..., registry: ReaderRegistry | None = None)` to look up a reader by declared MIME, content-sniff
the bytes, and dispatch. `PdfReader` wraps the existing `parse_pdf` unchanged (PDF behaviour byte-identical;
`fitz` stays lazily imported inside `parsers.py`). New readers: `XlsxReader` (openpyxl, already a dep),
`EmlReader` (stdlib `email`, no dep), `DocxReader` (python-docx), `PptxReader` (python-pptx) — all permissive.
Each reader builds `canonical_text` and tracks half-open unit spans through the shared `join_units` helper
(the single source of offset truth, mirroring `parsers._run_pymupdf`), so the offset invariant holds by
construction. OOXML containers pass `guard_ooxml` (DOCTYPE/ENTITY reject + zip-bomb caps) before any library
opens them. The `page` field is **reinterpreted per format** for paginationless documents — XLSX = worksheet,
DOCX = paragraph block, PPTX = slide, EML = whole message — and that reinterpretation is documented here.
**No DB migration:** `parser`/`parser_version` are free-text, `page_count`/`character_count` nullable,
`structured_content` stays `None` for non-PDF readers.

## Consequences

- **Multi-format matter ingest**, on the same `ParsedDocument` contract; the Citation Engine invariant is
  re-tested per reader (offset fidelity + non-overlapping unit-span coverage).
- **AGPL boundary preserved and now machine-enforced**: `fitz` lives only behind `PdfReader`, asserted by a
  **CI import-guard test** (AST walk of `app/pipeline/readers/`). Adds two MIT deps (python-docx,
  python-pptx) and no copyleft; license posture recorded in `NOTICES.md`. PyMuPDF replacement stays COMM
  open question #1 (not a C1 blocker).
- **Two fewer dependencies than first planned** (no `filetype`, no `defusedxml`) — the per-reader `sniff`
  and the pre-parse DOCTYPE reject are dep-free and version-proof.
- **`page_number` semantics are now format-dependent** (documented). A downstream consumer that assumes PDF
  page semantics for "scroll to source" should treat the field as a unit ordinal for non-PDF documents —
  flagged for citation-rendering work; out of C1 scope.
- **Known C1 limitation:** `DocxReader` extracts paragraph text only (python-docx `paragraphs` excludes
  tables); a body-order paragraph+table walk is deferred. XLSX reads cached values only
  (`data_only=True`) — a workbook saved without cached formula values yields empty cells for those formulas.
- **Explicitly deferred to C2:** `.msg`, email-chain threading, and nested-attachment recursion. `EmlReader`
  reads a single message's inline body and never recurses into attachments.
- **Operational:** new readers run in the worker, so a deps change requires rebuilding **api + arq-worker +
  ingest-worker together**.
