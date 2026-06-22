# C2 verification — email-chain + `.msg` + one-level attachment recursion (ADR-F029 extended)

Slice **C2** makes an uploaded email (`.eml` / Outlook `.msg`) a fully searchable matter document: the message
plus the **text of its recursable attachments** become grounded, citable passages under the one file's
`Document`, on the **same** `File → ParsedDocument → Document → chunks` contract (no migration; chunker /
models / persist / `search_documents` untouched). Provenance is **inline** in `canonical_text` (header block +
`[Attached file: …]` labels — the only thing `search_documents` surfaces); the machine-readable thread/
attachment map is the audit record in `Document.structured_content`.

## Automated (CI-parity, containerized api image)

- **ruff** (CI 0.15.18): `format --check` + `check` clean on `app/pipeline/readers` + `tests/test_readers.py`.
- **mypy**: `app/pipeline/readers` clean (9 files); `mypy app` clean.
- **Reader unit tests** (`tests/test_readers.py`): **38 passed** — chain assembly + offset/fidelity tiling per
  format; wired one-level recursion (docx attachment extracted) + the depth-1/depth-0 bound (nested email body
  extracted, its own attachment only listed); **fail-soft + sniff-gating** of `AttachmentRecurser` (unknown
  mime / spoof / malformed-but-sniff-passing / depth-exhausted → `None`, email still parses); the
  **extracted-text cap** (tiny input, larger extracted → `skipped (size cap)`); attachment-count cap;
  `_guess_mime` extension fallback; fully-empty-message degrade; `.msg` OLE-magic sniff + spoof; `.msg`
  normalization (oxmsg field mapping, plain>html, threading headers) via stub; `.msg` `read()` end-to-end via
  patched `Message.load`; the **fitz import-guard** auto-covers the new modules (`readers/*.py` glob).
- **Ingest e2e** (`tests/test_pipeline_ingest.py`, real postgres): a `.eml` with a `.docx` attachment ingests
  through the **wired** registry → persisted `normalized_content` grounds both the email body and the
  **recursed attachment text**, the inline label is present, every chunk slices back byte-for-byte, and the
  `structured_content` map records `extracted via …`.
- **Full api suite (containerized):** **2494 passed / 2 skipped**; the single non-pass is
  `test_health.py::test_ready_reports_per_dependency_status`, the documented environment-sensitive test that
  asserts services are *unreachable* and flips when the suite runs on the live `lq-ai_default` compose network
  (passes isolated in CI — same non-regression as C1). `mypy app` clean (182 files). Readers + ingest e2e
  re-run on the final post-fix code: **53 passed** on real postgres. CI (isolated) is the authoritative gate.

## Live (rebuilt image: baked code + `python-oxmsg==0.0.2`)

Ran the wired registry against a multi-attachment deal `.eml` (a `.docx` order form + a `.png`) on the real
rebuilt image (`docs/fork/evidence/c2/c2_live_recursion.py`):

```
python-oxmsg installed in image: 0.0.2
parser: eml | units: 3
  email body grounded : True
  docx text grounded  : True
  cap clause grounded : True
  docx label present  : True
  png listed, no bytes: True
  sc format: email | attachments: [('SecureScan-OrderForm.docx', 'extracted via python-docx'), ('logo.png', 'not text-extracted')]
  chunk fidelity OK   : True | chunks: 4
  .msg OLE sniff      : True | non-msg: False
```

Workers recreated on the C2 image: api + ingest-worker healthy. `arq-worker` hit the **documented C1**
docker network-endpoint glitch (`endpoint … already exists`) — non-blocking (cron-only; ingest flows through
ingest-worker; daemon restart clears it).

## Dependency posture

`python-oxmsg==0.0.2` — **MIT**, read-only OLE parsing (no network/eval; egress proven offline at C-R0-style
verification). Transitives `olefile` BSD-2, `click` BSD-3 — **no new copyleft** (rule B). NOT GPLv3
`extract-msg`. Recorded in `pyproject.toml` (+ mypy override) and `NOTICES.md`.

## Review

A 5-dimension fresh-context adversarial review (security / correctness / simplicity / tests / docs — 19 agents,
each finding independently re-verified against the code) returned **SHIP**, **0 blockers**, 4 should-fix, 9
nits. **All four should-fixes were applied before merge:**

1. **Security — inert recursion cap (real).** The cumulative cap measured **compressed** input (`att.data`),
   which is already a subset of the upload limit, so it never bit — while up to ~50 × guard_ooxml's 500 MB of
   **extracted** text could be spliced into one `canonical_text` (OOM vector). Fixed: the cap
   (`MAX_RECURSED_TEXT_CHARS`) now bounds the **extracted text** length, accounted in `_recurse_attachment`
   after parsing. New test `test_assemble_email_caps_on_extracted_text_not_input_bytes`.
2. **Tests — fail-soft/sniff-gating of the wired recurser was unexercised.** Added a wired spoofed-attachment
   test (email still `ready`, attachment `not text-extracted`, bytes never extracted) + a direct
   `AttachmentRecurser` test covering unknown-mime / spoof-sniff / malformed-parse / depth-exhausted.
3. **Docs — stale plan data model.** The plan's Components section still described the abandoned `nested`-tree
   design; added a **superseded banner** pointing to the shipped single-`NormalizedMessage` design + ADR.
4. **Docs — overstated "per-message".** Tightened ADR-F029 (and the plan) to "**one** message unit (top
   message) + one unit per attachment; a forwarded email is an attachment unit; `message_count` is always 1;
   inline-quoted history kept verbatim."

Nits folded: DRY'd the recurser plumbing into a shared `RecursingReader` mixin (removed the triplicated
`set_recurser_factory`/`_mint_recurser`/`accepts_recurser`); added the `_guess_mime`-fallback, fully-empty,
and patched-load-fidelity tests; removed a tautological assertion. The header-key extraction constants
(eml/msg) vs the display-mapping (assembler) were left distinct on purpose (extraction ≠ display).
