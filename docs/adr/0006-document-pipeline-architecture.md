# ADR 0006 — Document pipeline architecture

**Status:** Accepted
**Date:** 2026-05-08
**Owners:** Kevin Keller (LegalQuants)
**Context:** Task C5 — Document pipeline (basic)

---

## Context

Task C5 lands the asynchronous document pipeline that processes uploaded
files. C4 leaves rows in `files` with `ingestion_status='pending'`; C5
picks them up, parses the bytes, produces chunks with character-precise
offsets against the original document text, and flips
`ingestion_status` to `ready` (or `failed`).

Three architectural decisions had to be made before C5 could land:

1. **Parser choice.** Docling (IBM) is the PRD's structure-aware parser
   of choice; PyMuPDF (Artifex) is the byte-precise companion. Both are
   listed in [PRD §3, §1519, §7.2](../PRD.md). The implementation
   question: which is primary, which is fallback, and how do we
   reconcile their outputs to satisfy the load-bearing offset-fidelity
   contract that the M2 Citation Engine consumes?
2. **Worker mechanism.** The pipeline is async. The
   M1-IMPLEMENTATION-ORDER C5 brief calls for a Redis-backed worker
   queue. The candidates are `arq`, `rq`, or rolling our own pub-sub.
3. **Embedding generation.** The C5 brief lists "embeddings generated"
   in scope. The PRD lists embeddings as part of the chunk metadata.
   But the gateway's `/v1/embeddings` is still a 501 stub (B5 left
   it stubbed; B6 is optional and embeddings adapter work isn't
   sequenced). Writing embeddings now means picking *somewhere* to
   call — gateway-locally (501), a separate sentence-transformers
   stack (torch in the SBOM), or directly to OpenAI (architecture
   violation per CLAUDE.md — backend cannot hold provider keys).

Per CLAUDE.md, "if a decision isn't anchored in existing docs, document
the call rather than make it implicitly." This ADR records the three
calls.

## Decision

### 1. Docling primary, PyMuPDF for byte-precise offset reconciliation.

The pipeline runs **both parsers**:

* **PyMuPDF** (`fitz`) extracts the **character stream** of the
  original document — every character with its source page and byte
  offset. PyMuPDF's `page.get_text("dict")` produces this directly.
  This is the **canonical original-text representation** against which
  offsets are measured.
* **Docling** produces a structure-aware view (titles, paragraphs,
  tables) that *would* be useful for chunk-boundary heuristics in
  later passes — but its output is NOT character-precise against the
  original PDF byte stream. For M1 we run Docling for forward
  compatibility but **drive the chunker off the PyMuPDF character
  stream**. Docling's structured representation is stashed in
  `documents.structured_content` (JSONB) for M2 to consume.

If Docling crashes (the library is young; we accept some flakiness),
the pipeline falls through to **PyMuPDF only**, marks the row's
`parser` column as `pymupdf` (rather than `docling+pymupdf`), and
proceeds with the PyMuPDF-driven chunker. The pipeline never refuses
work because Docling failed; it refuses only when PyMuPDF fails too.

If PyMuPDF *also* fails (genuinely corrupt PDF, encrypted file, etc.)
the row is set to `ingestion_status='failed'` with a populated
`ingestion_error` and the worker moves on. The worker never crashes
on a bad input.

#### Why PyMuPDF for offsets

PyMuPDF returns each character's exact position in the original PDF's
text-extraction stream. Slicing the concatenated character stream by
`[char_offset_start:char_offset_end]` yields byte-equal source text.
This is the only library in our SBOM tier that gives us this.

#### Why Docling primary for structure (when it works)

Docling understands document structure (headings, lists, tables). The
chunker can use this for sentence-boundary respect. But because
Docling's output is not character-precise, we can't use its offsets
directly — we use its *boundaries* and reconcile by searching the
PyMuPDF stream. For M1 we keep this simple: the chunker is
sliding-window over the PyMuPDF stream, sentence-aware via a regex.
M2's Citation Engine work may upgrade this to use Docling's structure
for finer-grained chunk boundaries; the offset contract doesn't
change.

#### License posture

PyMuPDF is AGPL-3.0; the LQ.AI codebase is Apache-2.0. PRD §7.2 and
§1519 explicitly document the position: PyMuPDF is **server-side
only**, used as a library *in our deployed service*, and not
redistributed as a library bundled into a downstream consumer's
binary. The HTTP API surface is the AGPL boundary. Operators who
deploy LQ.AI run a service that incorporates PyMuPDF; that's
covered by AGPL's "use over a network" clause in §13. We do not
redistribute PyMuPDF source or binaries to downstream consumers as a
library; we redistribute it as part of our deployed service per the
AGPL's intent. Documented in:

* `docs/PRD.md` §7.2 (license rationale)
* `docs/PRD.md` §1519 (PyMuPDF boundary statement)
* `docs/PRD.md` §2640 (PyMuPDF-free build configuration as future
  fallback if AGPL interpretation tightens)

### 2. Worker mechanism: `arq`.

`arq` is the Redis-native async job queue we'll use for the document
pipeline (and for any future async backend work).

#### Why arq over rq

* **Async-native.** `rq` is sync; using it from our async codebase
  would require thread-pool gymnastics or a sync sub-process. `arq`
  is `asyncio` end-to-end, the same stack the rest of `api/` runs on.
* **Pydantic-friendly.** `arq` jobs are functions taking explicit
  arguments; signatures map cleanly to typed handlers.
* **Small dep footprint.** `arq` pulls only `redis-py` (which we
  already have) and `click` (small). No new SBOM family.
* **Healthcheck-able.** `arq` workers expose a status that can be
  scraped by docker-compose's healthcheck.

#### Why not Celery

Celery is the right choice at scale and for cross-language workers,
but for M1 it's overkill: configuration complexity, additional
result-backend, broker abstraction layer. We don't need any of that
yet.

#### Why not roll our own pub-sub

Tempting but premature. Reliability features `arq` provides (retry,
visibility timeout, dead-letter handling, scheduled jobs) we'd
re-implement and get wrong. Adopt the small library; revisit if it
ever becomes a constraint.

### 3. Embeddings deferred to C6.

For M1, the C5 pipeline writes `document_chunks.embedding = NULL` for
every chunk it produces. C6 (knowledge-base hybrid retrieval) is the
natural place to wire embeddings:

1. C6 already needs the gateway's `/v1/embeddings` endpoint to
   actually work (it's the retrieval-side call).
2. C6 owns the embedding-model selection decision (model name,
   dimension, default vs operator override).
3. C6 will backfill embeddings for any chunks where `embedding IS
   NULL`, which is a one-pass batch operation against ready
   documents.

The chunks themselves are stored with character-precise offsets; the
M2 Citation Engine's deterministic substring verification depends on
the offsets being right, **not** on the embedding being populated.
Citations work in M2 with or without embeddings — embeddings are for
*retrieval*, not for *verification*.

The **C5 pipeline updates `files.ingestion_status` to `ready`** as
soon as chunks are written. The chunks are queryable, ordered, and
sliceable from the moment ingestion completes. This satisfies the
C5 brief's verification step ("query `document_chunks` and confirm
content is present, offsets are character-precise") even though the
"embeddings generated" sub-clause is deferred. Documented in
`docs/M1-PROGRESS.md` and the C6 spec is updated to absorb the
embedding-generation work.

#### Why not call OpenAI directly from the worker

This would give us embeddings today, but it bypasses the Inference
Gateway boundary. CLAUDE.md is explicit: "The Inference Gateway is
the security boundary — the only component holding privileged
provider API keys." Direct OpenAI calls from the worker would
introduce a parallel auth path, a parallel cost-tracking path, and
a parallel anonymization path — every reason the gateway exists in
the first place.

#### Why not a local sentence-transformers stack

`sentence-transformers` pulls `torch` (multi-gigabyte SBOM entry).
PRD §1519 already documents the AGPL footprint we accept; adding a
multi-GB ML dep is a strictly bigger swallowing-of-the-camel that
wants its own ADR. C6 may decide to take this on, may decide to wire
through the gateway, or may decide on a hybrid; the right place for
that decision is C6.

### 4. Idempotency: replace-on-conflict.

The worker must be re-runnable: an operator triggers a re-ingest
(e.g., after a Docling version upgrade, or after a manual
`UPDATE files SET ingestion_status='pending' WHERE ...`), and the
pipeline must not produce duplicate chunks.

Approach: the worker, before writing chunks, deletes every existing
`document_chunks` row for the file's `document_id` (CASCADE-delete
via the FK from `documents` to `document_chunks` does NOT help here
because we're keeping the `documents` row and only re-writing
chunks). The delete + insert run in a single transaction, so a
mid-run failure leaves the prior chunks intact.

The `(document_id, chunk_index)` UNIQUE constraint enforces this at
the storage layer; the worker enforces it at the application layer
by transactional replace.

### 5. Wire-up: C4 enqueues; the worker is a separate Compose service.

The C4 upload handler is updated to **enqueue** an ingest job after
the row is committed. A new docker-compose service `ingest-worker`
runs the `arq` worker. Both share the same `app/` source tree
(the worker imports `app.workers.document_pipeline`).

Enqueue is best-effort: if Redis is briefly unreachable when the
upload completes, we log a WARNING and the row stays in
`pending`; an operator-initiated batch re-enqueue (or the worker's
own pickup-on-startup sweep) will catch up. The upload itself
**succeeds** even when enqueue fails — the user has a file, just
ingestion is delayed.

The worker also runs a **startup sweep** that picks up any rows in
`pending` or `processing` status (possibly orphaned by a worker
crash mid-job) and enqueues them. This makes the worker
self-healing across restarts.

## Consequences

### Positive

* The offset-fidelity contract holds: every chunk slices back to its
  content byte-for-byte, against the canonical PyMuPDF character
  stream.
* Docling failures degrade gracefully (PyMuPDF-only fallback), not
  catastrophically.
* `arq` gives us retry/visibility/dead-letter at small dep cost.
* Re-ingestion is safe (idempotent replace).
* Worker is self-healing across restarts (startup sweep).
* The decision to defer embeddings is explicit and reversible: the
  schema accepts `NULL` embeddings; C6 backfills.

### Negative

* PyMuPDF AGPL. Mitigated by PRD §7.2's documented boundary; if a
  downstream consumer ever needs a truly PyMuPDF-free build, PRD
  §2640 documents the fallback (Docling-only, accepting reduced
  precision).
* Two parsers means two failure surfaces; mitigated by the fallback
  cascade.
* Embeddings deferral means M1's KB retrieval (C6) cannot do vector
  search until embeddings are generated. C6 is sequenced after C5,
  so this is a question for C6 not C5.

### Neutral

* The `documents.structured_content` JSONB field stores Docling's
  structured representation. M1 doesn't read it back; M2's Citation
  Engine work (or M2's RAG retrieval) may use it. Storing it now
  means we don't have to re-run Docling later.

## Companion artifacts

* `api/alembic/versions/0004_create_documents_and_chunks.py` —
  migration that adds `documents`, `document_chunks`, and the
  pgvector extension.
* `api/app/models/document.py` — ORM models.
* `api/app/pipeline/parsers.py` — PyMuPDF and Docling adapters.
* `api/app/pipeline/chunker.py` — character-precise sliding-window
  chunker.
* `api/app/pipeline/ingest.py` — orchestration: pull bytes, parse,
  chunk, persist, flip status.
* `api/app/workers/document_pipeline.py` — `arq` worker entrypoint.
* `api/app/workers/queue.py` — enqueue helper used by the upload
  handler.
* `docker-compose.yml` — new `ingest-worker` service.
* `docs/db-schema.md` — already documents `documents` and
  `document_chunks`; this ADR is the rationale for how C5
  populates them.
* `docs/M1-PROGRESS.md` — embeddings-deferral entry that
  reassigns scope to C6.

## Alternatives considered

### Docling-only pipeline

Considered for "one parser is simpler than two." Rejected because
Docling does not give character-precise offsets and the M2 Citation
Engine *requires* them. Building a reconciliation layer to map
Docling output back to original-PDF byte offsets is more work than
running PyMuPDF in parallel.

### Celery for the worker

Considered because Celery is the industry default. Rejected for M1's
scale: configuration complexity exceeds the value. We can revisit if
we ever need cross-language workers, complex DAG-style workflows, or
a result-backend-as-a-service.

### Local sentence-transformers for embeddings now

Considered for "embeddings work end-to-end at M1." Rejected because
the multi-GB torch dependency is bigger than this task's scope wants
to absorb without its own ADR; C6 owns this decision.

### Generate embeddings via the gateway's still-501 endpoint

Considered for "no new architectural pieces." Rejected because the
endpoint is genuinely unimplemented and landing it as part of C5
would expand C5's scope by 30-50%. The right place is C6.

### Hard-fail on Docling crashes

Considered for "fail loud, fix bugs." Rejected because Docling is a
young library and our pipeline must be robust to its flakiness. We
log Docling failures at WARNING and proceed via PyMuPDF; the operator
sees the warning and can decide whether to file a Docling issue.
