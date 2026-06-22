# C2 — Email-chain + `.msg` + one-level attachment recursion (plan)

**Slice:** C2 (COMMERCIAL ladder). **Depends:** C1 ✓ (the reader registry). **ADR:** F029 (extended).
**Status:** plan — awaiting maintainer edits before implementation (CLAUDE.md: explore → plan → human edits →
implement). Explored against the *actual* C1 code (`api/app/pipeline/readers/`, `ingest.py`, `chunker.py`,
`models/document.py`, `agents/tools.py`), not the decomposition prose.

## Goal

A deal starts as an email; complex ones are the whole chain + attachments. Today a `.eml` ingests as **one**
message (headers + inline body, no recursion) and `.msg` doesn't ingest at all. C2 makes an uploaded email a
**fully searchable matter document**: every message in the chain **and** the text of its recursable attachments
become grounded, citable passages under the one file's `Document`.

## Non-goals (held)

- No quoted-history splitting library (we keep the body verbatim; reply quoting stays as-is unless proven
  needed). No counterparty/deal **entity** (matter memory = C3). **No recursion deeper than one level.** No
  redline/extraction (C4/C5). No new SSE frames.

## The core design — one File → one `ParsedDocument`, untouched downstream

A `.eml`/`.msg` is **one** uploaded `File`. C1's pipeline is `File → ParsedDocument → Document → chunks`, and
the Citation invariant `normalized_content[start:end] == chunk.content` holds because the chunker slices
`canonical_text`. C2 keeps that exactly: the email reader emits **one `ParsedDocument`** whose `canonical_text`
is the ordered concatenation of **units** —

```
unit 1  = message 1   ("From: …\nTo: …\nDate: …\nSubject: …\n\n<body>")
unit 2  = message 2   (nested forwarded/replied message/rfc822 or .msg, one level)
…
unit k  = attachment 1 ("[Attached file: SecureScan-OrderForm.docx (…docx)]\n\n<extracted text>")
unit k+1= attachment 2 …
```

- **Offsets:** `join_units` (the existing single offset-truth helper) — **unchanged**. Each unit = one
  `PageSpan` (`page_number` = unit ordinal). The chunker maps chunk→unit by offset for free; `search_documents`
  already shows `[filename — page N]`, so the unit ordinal is a free coarse provenance signal.
- **Provenance that the agent can actually use is INLINE.** `search_documents` returns chunk **content
  verbatim** (it does *not* read `structured_content`/`metadata_json`). So each unit's text carries its own
  human-readable label — the message header block (as EML already does) and a synthetic `[Attached file: …]`
  line per attachment. This is what lets the agent answer *"per the order form attached to Jason's email…"*.
- **Machine-readable map → `Document.structured_content`** (already a JSONB column → **NO migration**). The
  reader writes a thread/attachment map: per message `{ordinal, from, to, date, subject, message_id,
  in_reply_to, references, depth}`; per attachment `{ordinal, filename, mime, parser, bytes, parent_message_id,
  status}`. Not consumed by search today; it is the transparency/audit record and the substrate C5/C7 build on.
- **Untouched:** chunker, `Document`/`DocumentChunk` models, persist path, `search_documents`. Zero migration
  (head stays `0066`).

## Components

> **⚠ Superseded by the Build-prep resolutions below + the shipped code (ADR-F029 C2 section is the
> authoritative record).** This section sketched an early design that did NOT ship. What actually shipped:
> a **single** `NormalizedMessage(headers, body, attachments)` (no `nested` field) and
> `assemble_email(message, *, recurser, parser_label, parser_version)` taking **one** message — a nested
> `message/rfc822`/`.msg` is just another **attachment** handled by the recurser (one level), not a separate
> message in a tree. The recurser is `AttachmentRecurser(registry, depth_remaining)` (per-call depth, not
> `max_depth`), wired via a `set_recurser_factory` seam at the composition root. Caps are module constants
> (`MAX_EMAIL_ATTACHMENTS`, `MAX_RECURSED_TEXT_CHARS` — extracted-text-based, see Build-prep), not env vars,
> and there is no separate "nested-messages" cap. The original sketch is kept below for history.

1. **Shared message assembler (`_base` or a new `_message.py`).** A normalized intermediate
   `_NormalizedMessage(headers: dict, body: str, attachments: list[_Attachment], nested: list[_NormalizedMessage])`
   and `assemble_email(messages, *, recurse, parser_label, parser_version) -> ParsedDocument` that walks
   messages depth-first (one level), builds the unit list + inline labels + `structured_content`, and applies
   the security caps. Both readers normalize their format into `_NormalizedMessage`, then call the assembler —
   so threading/recursion/provenance logic lives in **one** place.
2. **`eml.py` upgraded (stdlib `email`).** Parse the top message; collect nested `message/rfc822` parts as
   `nested` messages (forwarded/attached emails); collect non-message attachments. Reuse the existing
   `_HtmlTextExtractor`/`_strip_html` + `_HEADER_ORDER`. Order messages: top first, then nested by `Date`
   (linked via `In-Reply-To`/`References`/`Message-ID` recorded in the map; **ordering only**, no tree build).
3. **`msg.py` new (`python-oxmsg`, MIT).** `sniff` = OLE magic `D0 CF 11 E0 A1 B1 1A E1` (a *real* spoof check,
   unlike `.eml`). Normalize sender/recipients/subject/body(+html)/attachments → `_NormalizedMessage`; nested
   `.msg` attachments become `nested` (one level). MIME `application/vnd.ms-outlook` (+ register the common
   `application/x-msg` alias) added to the registry.
4. **Attachment recursion via an injected recurser.** `AttachmentRecurser(registry, max_depth=1)`:
   `(mime, data) -> ParsedDocument | None` — look up a reader, run `sniff`, `read`; returns `None` (not text)
   when no reader, sniff fails, depth exhausted, or the reader raises (fail-soft per-attachment: a bad
   attachment is recorded `status="parse_failed"` in the map, never sinks the whole email). Office docs recurse
   through the **existing** OOXML readers → `guard_ooxml` (zip-bomb/XXE) applies automatically. Wired in
   `build_default_registry`: build readers → build registry → construct recurser → assign to `eml`/`msg`
   (two-phase wiring at the composition root; tests inject a fake recurser through the constructor seam).

## Security (untrusted input — the slice's main surface)

- **Depth = 1** (recurser); a nested email is read **without** further recursion (its attachments are listed,
  not extracted) → no unbounded `.eml`-in-`.eml`.
- **Caps:** max attachments per email (`C2_MAX_ATTACHMENTS`, ~50), max **cumulative recursed bytes**
  (`C2_MAX_RECURSED_BYTES`, e.g. 100 MB — independent of the per-file upload cap), max nested messages. Over a
  cap → record `status="skipped_cap"` in the map + an inline note, don't fail the email.
- **No remote fetch.** `cid:`/`http(s)`/external DTD never dereferenced (stdlib + `_strip_html` already inert;
  `oxmsg` is local OLE parsing). **HTML sanitized** via the existing stripper. **OOXML** recursion inherits
  `guard_ooxml`. **`.msg`/OLE**: cap sizes; `oxmsg`/`olefile` do no eval.
- **fitz import-guard extended** to `msg.py` + the assembler (the C1 AST test asserts no reader imports `fitz`).
- **Audit/Citation:** no raw clause text in logs; offsets via `join_units` fail-closed on drift.

## Dependencies

- **`python-oxmsg`** (MIT) + transitive **`olefile`** (BSD-2-Clause). **Verify first** in a throwaway py3.12
  container (mirror C-R0/C1): load API shape, full transitive license scan (no NEW copyleft), no egress.
  *Reject `extract-msg` — GPLv3 (copyleft, rule B).* Add to `api/pyproject.toml` + mypy override + `NOTICES.md`.
- New deps run in the **ingest-worker** → rebuild `api` + `arq-worker` + `ingest-worker` before live tests.

## Files

`readers/_message.py` (new, shared assembler) · `readers/eml.py` (upgrade) · `readers/msg.py` (new) ·
`readers/__init__.py` (register `.msg`, wire recurser) · `readers/_base.py` (recurser type + caps consts; maybe
the `_Attachment`/`_NormalizedMessage` types) · `api/pyproject.toml` · `NOTICES.md` ·
`docs/adr/F029-mime-reader-registry.md` (extend) · `tests/test_readers.py` + `tests/test_pipeline_ingest.py`.

## Verification

- **CI:** multi-message `.eml` → ordered per-message units with sender/date inline + map in
  `structured_content`; `.msg` → sender/recipients/subject/body + attachment bytes; an attached office doc is
  recursed + chunked + fidelity-verified (`content == normalized_content[start:end]`); `.msg` OLE-magic
  sniff/spoof; depth/count/byte caps; a malformed attachment fails soft (email still `ready`); no-remote-fetch;
  fitz-guard covers the new modules. ruff (CI 0.15.18) + targeted mypy clean; full api suite count quoted.
- **Live (DeepSeek):** ingest a real multi-attachment deal email; agent answers grounded in a **buried
  attachment** (the C2 acceptance signal). First vehicle = **Scenario A** (`scenarios/scenario-a-securescan.md`).
- **Review:** fresh-context adversarial + security + simplification pass. Merge per ADR-F005.

## Open choices for sign-off

1. **`.msg` dep = `python-oxmsg`** (MIT). Confirm direction (vs. deferring `.msg` to a later slice and shipping
   only the chain + attachment recursion now). *Recommend: include it — Scenario B needs `.msg`, and it's MIT.*
2. **Provenance home:** inline labels (load-bearing, agent-usable today) **+** `structured_content` map (future
   C5/C7). *Recommend as written — no migration, no chunker/search change.*
3. **Non-text attachments** (images/PDF-scans/zips): record in the map + an inline `[Attachment: name (mime) —
   not text-extracted]` marker so the agent knows it exists, but no body text. *Recommend yes.*
4. **Caps:** `C2_MAX_ATTACHMENTS≈50`, `C2_MAX_RECURSED_BYTES≈100 MB`, depth 1. Confirm values (defensive, not
   tuning).

## Build-prep resolutions (2026-06-22 — signed off "go", structured_content built now)

- **`structured_content` map ships in C2** (not deferred). It's near-free (the metadata is already extracted to
  build the inline labels + drive recursion), needs **no migration** (column exists, already persisted), gives
  an **auditable** thread/attachment record today (receipts rule), and matches the codebase precedent (the PDF
  path stashes Docling `structured_content` ahead of consumers). Schema kept flat/obvious; **inline labels stay
  the load-bearing agent path** (the map is not agent-visible yet — honest).
- **`python-oxmsg==0.0.2`** verified in a throwaway py3.12 container: **MIT**; transitive tree all permissive
  (`olefile` BSD, `click` BSD-3) — **no copyleft** (rule B ✓); `Message.load(str|IO|bytes) -> Message` exposing
  `sender / recipients[.email_address,.name] / subject / body / html_body / sent_date / message_headers /
  message_class / attachments[.file_name,.mime_type,.file_bytes,.size]`. `socket`/`urllib` appear in
  `sys.modules` only as stdlib-transitive imports (email.utils / click), not network calls — the parse is local
  OLE via olefile; proven offline under `--network=none` at verify time. **0.0.2 is the latest** (young package
  → exact pin + the egress/offline proof + ADR note). Read-only: there is **no `.msg` writer**.
- **Recurser is per-call depth-safe** (concurrency): `AttachmentRecurser(registry, depth_remaining)` is
  immutable; recursing constructs a `depth-1` child and passes it as an **argument** to email readers
  (`read(data, recurser=...)`, marked `accepts_recurser=True`) — never mutates shared reader state. Top-level
  `ingest_file` calls `reader.read(bytes)`; the email reader mints a fresh `depth=1` recurser from a registry
  factory set at wiring. A nested email is read with a `depth-0` recurser → its attachments are listed, not
  extracted (the one-level guarantee).
- **`.msg` fixture strategy** (oxmsg can't write): C2's **live vehicle is a multi-attachment `.eml`**
  (stdlib-buildable, realistic for the internal Scenario-A email). `.msg` is covered by (a) **normalization**
  unit tests via an injected parse-boundary stub, (b) **OLE-magic sniff** tests (`D0CF11E0A1B11AE1`), and (c) a
  **patched-load end-to-end** test (`oxmsg.Message.load` monkeypatched to a stub → exercises `read()` →
  `_normalize` → `assemble_email`). The oxmsg byte-parse itself is empirically API-verified (C2 container
  check) + is oxmsg's own responsibility; the first **real** `.msg` byte-parse lands at Scenario B. A
  hand-built CFB fixture was judged not worth the risk (no *our*-logic test depends on one).
- **Recursed-text cap corrected (post adversarial-review, 2026-06-22).** The cap now bounds the cumulative
  **extracted text** spliced into `canonical_text` (`MAX_RECURSED_TEXT_CHARS`, accounted in
  `_recurse_attachment` after parsing), **not** the compressed input bytes. A compressed-bytes cap was inert
  (each attachment is already a subset of the upload, capped by `LQ_AI_MAX_UPLOAD_SIZE_MB`), so it never bit;
  the real decompression-amplification vector (≤50 attachments × guard_ooxml's ~500 MB uncompressed) needed an
  extracted-text bound. Covered by `test_assemble_email_caps_on_extracted_text_not_input_bytes`.
