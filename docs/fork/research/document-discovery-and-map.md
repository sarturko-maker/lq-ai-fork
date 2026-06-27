# Research — How a Deep Agent knows what documents exist in a matter, and picks the right one

**For:** the maintainer's question — document discovery/selection for matter-bound Deep Agents; the
single-upload "work on this" case must be airtight; for long-running deals we want a maintained
**documents map**; evaluate **PageIndex**; and respect the **CRUCIAL BALANCE** — if tokens are cheap
or reading the whole document makes sense, prefer putting it in context over building machinery.

**Method:** codebase discovery (LQ.AI fork, branch `fork/c3-update-memory-ux`, head `1f8fc87`) +
web research + two adversarially-verified verdicts on the load-bearing PageIndex claims. Code claims
below were re-verified by reading the cited files. **Date:** 2026-06-27.

**Posture reminders baked into every recommendation:** all LLM calls route through the in-house
gateway (no direct provider egress, ADR-F010); unit-of-work memory is **auto-write-then-correct**
(ADR-F042 — agent maintains it, human owns it after the write, human-pinned corrections win);
Apache-2.0 posture, AGPL is a hard server-side-only boundary; new dependencies are SBOM/supply-chain
surface and must be justified.

---

## 1. Executive summary

- **The single-upload case is already close to airtight, and cheaply made fully airtight.** A
  matter-bound agent discovers documents by calling `search_documents("")`, which lists every attached
  file by name + page count + ingestion status (`api/app/agents/tools.py:499-516`); it reads one by
  exact (case-insensitive) filename via `read_document(name)` (`tools.py:199-256`). With one document
  the only failure modes are (a) the doc isn't ingested yet (handled with an honest "try again
  shortly" message, `tools.py:241-245`) and (b) the agent never lists at all and answers blind. The
  fix for (b) is prompt/skill discipline, not machinery (see §3).

- **The hard case is the long deal: many documents, many turns, similar names.** Today there is **no
  per-document description anywhere** — neither `File` nor `Document` has a title/summary/role field
  (`api/app/models/document.py:51-132`, `api/app/models/file.py:33-105`). The inventory is just
  `filename (N pages)`. With 20+ documents named `NDA_v3_FINAL_clean.docx`, the agent picks by
  filename guesswork + FTS snippets. **This is the real gap**, and it is a *description* gap, not a
  retrieval gap.

- **Recommended primitive: a maintained DOCUMENTS MAP — `{document → one-line description + role/side
  + status + key facts}` — built on the existing auto-write-then-correct machinery, not a new
  subsystem.** The map is the inventory the agent already gets, *annotated*. Best home: the typed fact
  ledger (`MatterMemoryEntry`, ADR-F042/F043) with a new `fact_type="document"` (an additive
  one-line enum + migration), keyed to the file. It inherits bi-temporal supersede, provenance,
  human-pinned corrections, undo, and the existing consolidation pass for free.

- **The map and the authorship roster (ADR-F048) are siblings, not the same thing.** The roster
  answers *who* (people → side); the map answers *what* (documents → role/status). They cross-reference
  (a document's role is "the counterparty's markup, authored by Jane (counterparty)") but stay
  distinct: one is `MatterParticipant`, the other a `fact_type="document"` ledger entry. Don't fold
  documents into the roster.

- **PageIndex: a clean piece of engineering, wrong tool for this problem *right now*.** It is MIT
  (verdict: confirmed — vendorable under Apache-2.0) and — crucially — it does **not** call providers
  directly: every LLM call goes through LiteLLM (verdict: refuted that it needs adapter work), so it
  *could* be pointed at our gateway. But it is a *within-document* retrieval engine (tree-of-contents
  over one big doc), which solves a problem we don't yet have: we have no documents large enough to
  need it, FTS over chunks already exists, and tree-building costs ~137 gateway calls per document.
  **Verdict: skip now, revisit only if/when single documents routinely exceed our 40k-char read cap
  AND FTS proves insufficient** (see §5).

- **The balance rule (the heart of the question), stated crisply:**
  - **Just read the whole document** when a single doc is **≲ 40k characters (~10k tokens)** — i.e. it
    fits under the existing `read_document` cap (`tools.py:65`). This is the **common case** (a typical
    NDA/contract is 4k–13k tokens) and needs **zero new machinery**.
  - **Use the map (annotated inventory)** when there are **roughly 5+ documents** in the matter, so the
    agent picks by *description* not by filename guess. The map is metadata (descriptions), not full
    text — it costs a few hundred tokens and prevents the wrong-document failure.
  - **Use FTS (already built) to pull passages** when a doc is too big to inline or when the question
    targets a specific clause across several docs.
  - **Only consider a tree-index (PageIndex-style)** when a *single* document is so large that even
    chunked FTS can't reliably locate the right section — a threshold we do not hit today.

- **Confusion-avoidance is mostly prompt + a tiny bit of state, not retrieval tech.** Three cheap
  levers, in priority order: (1) **descriptions read first** (the map) so selection is by meaning;
  (2) **active-document stickiness** — there is *no* stickiness today (`grep` for it returns nothing),
  so an agent can drift between similarly-named files mid-thread; the matter wiki should name the
  "document in play"; (3) **ask, don't guess** on ambiguous names — the read path already *notifies*
  on duplicate names (`tools.py:234-239`) but still auto-picks; for genuinely ambiguous *selection*
  the agent should surface the choice.

- **Decomposition: two cheap wins now, the index deferred.** (1) Add `fact_type="document"` + a
  `record_document_note` write tool + render the map into the inventory and a prompt block (one slice,
  needs a short ADR — it's the documents-map decision). (2) Active-document stickiness via the wiki +
  a "documents in play" convention (prompt/skill only, no schema). PageIndex and any vector/tree index
  stay in the backlog behind an explicit "we measured a doc too big for FTS" trigger.

---

## 2. Current state (codebase-grounded)

### How documents are stored

Documents are **dual-tracked**:

- **`File`** — the original bytes' metadata: `filename`, `mime_type`, `size_bytes`, SHA256,
  `storage_path` (MinIO key), `ingestion_status` (`pending`→`processing`→`ready`/`failed`),
  soft-delete via `deleted_at`, optional `project_id` (matter scope), `created_by_run_id`
  (work-product provenance). Bytes live in MinIO; metadata in Postgres.
  `api/app/models/file.py:33-105`.
- **`Document`** — one row per successfully-ingested file (unique FK): `parser`/`parser_version`,
  `page_count`, `character_count`, `structured_content` (JSONB — e.g. email headers),
  `normalized_content` (the canonical text used for citation verification), `was_ocrd`,
  `ingest_status`. `api/app/models/document.py:51-132`.
- **`DocumentChunk`** — character-precise chunks upholding the citation invariant
  `canonical_text[char_offset_start:char_offset_end] == chunk.content`; `content_tsv` is an
  auto-generated TSVECTOR for FTS; `embedding` is `pgvector(1536)` but **NULL in M1**
  (vector search deferred to C6). `api/app/models/document.py:135-228`, embedding comment
  `:207-211`.

### What description/metadata fields already exist

**There is no per-document description, summary, title, or role field anywhere.** Verified by reading
both models: `Document` carries only parser metadata + raw `structured_content` + canonical text;
`File` carries only filename/mime/size/hash/status (`document.py:51-132`, `file.py:33-105`). The only
free-text "description" fields in the schema sit at *collection* level, not per-document:
`Project.context_md` (the matter wiki, `api/app/models/project.py`) and `KnowledgeBase.description`
(`api/app/models/knowledge.py:47-142`, and KBs aren't agent-visible). So the agent's entire picture of
"what is this document" is: **the filename, its page count, and whatever FTS snippets it can pull.**

### How documents are discovered and selected (agent-facing)

A matter-bound run gets exactly three document tools, granted as a frozenset
(`MATTER_TOOL_NAMES = {search_documents, read_document, get_document_metadata}`, `tools.py:67`), built
into closures that capture the matter+owner scope so `user_id`/`project_id` are never model-visible
(`build_matter_tools`, `tools.py:100-158`):

- **Discovery — `search_documents("")`** → `_inventory()` lists every attached file as
  `- {filename} ({N} pages)` (or `(not ingested yet — status: …)`), one line each
  (`tools.py:163-164`, `:499-516`). This is the primary "what exists" mechanism.
- **Content discovery — `search_documents(query)`** → lexical FTS via
  `websearch_to_tsquery('english', query)` over `document_chunks.content_tsv`, top-8 passages by
  `ts_rank_cd`, each labelled with filename + page range (`_FTS_SQL`, `tools.py:70-83`;
  `_search`, `:161-196`). **No vector search** (embeddings NULL in M1; FTS only — `tools.py:6-10`).
- **Selection — `read_document(name)`** → exact filename match, case-insensitive
  (`func.lower(File.filename) == wanted.lower()`, `tools.py:217`). Returns
  `Document.normalized_content` capped at `_READ_LIMIT = 40_000` chars (~10k tokens, `tools.py:65`),
  truncating with an honest notice that steers back to `search_documents` (`tools.py:249-255`).
- **Authorship — `get_document_metadata(name)`** → email From/To/Cc/Date/Subject from
  `structured_content`, or `.docx` core-properties author/last-modified-by; explicitly marked as
  **untrusted, forgeable** model input (ADR-F048, `tools.py:143-156`, `:270-317`).

**Matter membership** is a union of two attachment paths — the `project_files` join OR
`File.project_id` set at upload — re-asserting `owner_id` and `deleted_at IS NULL` on every query
(`_matter_files_query`; module docstring `tools.py:1-35`; mirrored in the REST endpoint
`api/app/api/matter_files.py:78-89`). Cross-user access is **404-conflated** (ADR-F035): a doc in
someone else's matter returns the same "No document named X in this matter" as a non-existent one.

**Duplicate-name handling** (the same name on multiple files): the read path fetches *all* matches,
orders them **readable-first** (`Document.id.is_(None)`) then **newest-first**
(`coalesce(ProjectFile.attached_at, File.created_at).desc()`), reads `rows[0]`, and **prepends a note**
to the result: *"Note: N files in this matter share this name; reading the most recently added readable
copy."* (`tools.py:222-239`). So duplicates are *announced* but still auto-resolved — there is no
*selection* hand-off to the user.

There is also a **REST discovery endpoint** for the cockpit UI, `GET /matters/{id}/files` (C7a,
ADR-F046), returning the same metadata (id, filename, mime, size, status, `created_at`,
`created_by_run_id`) with the same scope, newest-first, metadata-only
(`api/app/api/matter_files.py:63-107`).

### What's injected at run start

The system prompt is composed in a deliberate, fenced order (`system_prompt_for`,
`composition.py:218-254`): base identity → `MATTER_PROMPT` ("ground your answer in the matter's
documents", `:95-102`) → `MATTER_REVIEW_DOCTRINE` + `MATTER_ROSTER_DOCTRINE` (`:109-139`) →
`CLIENT_CONTEXT_PROMPT` (operator org profile, read-only, ADR-F030, `:149-162`) →
`MATTER_MEMORY_PROMPT` (the matter wiki, `:175-186`) → `MATTER_CORRECTIONS_PROMPT` (human-pinned
corrections, `:192-200`) → `MATTER_ROSTER_PROMPT` (authorship roster, `:207-215`) → the area's
controlling-method suffix (last, so it governs). Every block is wrapped in `BEGIN/END` markers so
embedded text can't change the model's role, and every layer degrades to silence when empty.

**Crucially, no document inventory or manifest is injected at run start.** The agent learns what
documents exist *only* by calling `search_documents("")` during the turn. The discovery findings
confirm this ("No Per-Document Snapshot Injection; Agent Uses Live Inventory") and it is borne out by
`system_prompt_for` having no document parameter. Token-budget note: the operating point is
`DEFAULT_MAX_INPUT_TOKENS = 200_000` (`factory.py:33`), deepagents compacts at ~0.85× (~170k); a
20-doc inventory is a few hundred tokens, so re-listing each turn is cheap.

### Multi-turn behaviour

Conversation state persists via a langgraph `AsyncPostgresSaver` checkpointer keyed by `thread_id`
(`api/app/agents/checkpointer.py`; follow-ups detected by querying prior `AgentRun` rows for the
thread, `composition.py:327-333`; a follow-up with no checkpointer is honestly refused). Durable
matter recall comes from the **matter wiki** (`Project.context_md`, rewritten in place, max 16k chars —
`MATTER_WIKI_MAX_CHARS`, `api/app/schemas/matter_memory.py:29`) and the **typed fact ledger**
(`MatterMemoryEntry`, bi-temporal `valid_at`/`invalid_at`/`superseded_by`, `fact_type` ∈
{party, term, date, decision, open_point, fact} — `matter_memory.py:124-138`; max 4k chars/fact,
`:33`). Both inject read-only each run. **But document discovery itself is re-run fresh every turn —
there is no remembered "the document we're working on".** That absence is the seed of cross-turn
confusion (§7).

---

## 3. The gap

### The single-upload "work on this" case — is it actually airtight?

**Almost, and the residual is cheap.** With exactly one document attached:

- Discovery is trivial — `search_documents("")` returns the one file.
- Selection can't pick wrong — there's one name to match.
- The honest-failure paths are covered: not-yet-ingested returns *"…has no extractable text yet
  (ingestion pending or failed). Try again shortly…"* (`tools.py:241-245`); a too-long doc truncates
  with a notice (`:249-255`).

The **one** real failure mode is behavioural, not structural: **the agent answers without ever
listing/reading**, because nothing *forces* discovery — `MATTER_PROMPT` *encourages* grounding
(`composition.py:95-102`) but the model can ignore it. This is a prompt/skill-discipline fix (a strong
"on a single-document matter, read it before answering" instruction), **not** a machinery fix. Verdict:
the single-upload case is airtight on the *plumbing*; tighten the *instruction* and add a test that a
single-doc matter is read before answering.

### The hard cases

**(a) Long deal, many documents, many turns.** The inventory is `filename (N pages)` with **no
descriptions** (§2). At 15–30 documents — drafts, redline rounds, side letters, emails, schedules — the
agent must infer role and relevance from filenames + FTS snippets alone. Failure modes:
- Picks a stale draft (`MSA_v2.docx`) when `MSA_v4_clean.docx` is current — filenames don't encode
  "current".
- Can't tell *our* draft from the *counterparty's* markup from filename alone (the roster knows
  *people*, not which *file* is whose).
- Burns turns re-deriving the lay of the land each session because discovery is stateless and
  un-annotated.

**(b) Similarly-named documents.** The read path *announces* duplicates and auto-picks readable+newest
(`tools.py:234-239`), which is a sensible default for true duplicates (re-uploads). But for
*semantically distinct* files that happen to collide on name (two parties' versions both saved as
`NDA_FINAL.docx`), "newest readable copy" is a **silent wrong pick dressed as a notice** — the agent is
told it picked one of several but isn't asked which. There is no disambiguation hand-off.

**(c) No active-document memory across turns.** Confirmed by code search: there is **no** stickiness /
active-document / current-document field anywhere in `api/app/agents/` (grep returns nothing). Turn 5
of a negotiation has no structural memory that turns 1–4 were working on `Cirrus_MSA_v4.docx`; it
re-discovers from scratch. Combined with (b), the agent can *drift* between similarly-named files
mid-thread without anyone noticing.

**(d) Discovery is content-blind beyond FTS.** FTS finds *passages by keyword*; it doesn't summarize
*what a document is for*. "Which document is the escrow agreement?" only works if "escrow" appears in
the text and ranks; it can't answer "which of these 12 is the one we're actively redlining?"

**Bottom line:** the gap is a **description + selection-stickiness gap**, not a retrieval-power gap.
FTS retrieval is adequate at our scale; what's missing is *annotated inventory* and *cross-turn
focus*.

---

## 4. The documents map

**Proposal:** a maintained **documents map** — for each matter document, a short record:
`{filename → one-line description · role · side · status · 1–3 key facts}`. Example entries:

- `Cirrus_MSA_v4_clean.docx` — *Master Services Agreement, our current draft (v4), incorporates
  counterparty round-2 markup; liability cap at 12 months' fees; **active**.* (role: primary contract;
  side: ours; status: current)
- `Cirrus_MSA_v3_counterparty.docx` — *Counterparty's round-2 redline of the MSA; superseded by v4.*
  (role: counterparty markup; side: counterparty; status: superseded)
- `escrow_sideletter.eml` — *Side letter proposing source-code escrow; from opposing counsel
  2026-05-02.* (role: side letter; side: counterparty; status: open point)

This is **the inventory the agent already sees, annotated** — `filename (N pages)` becomes
`filename (N pages) — <description> [role/side/status]`. It is *metadata*, not full text: a few
hundred tokens for a whole matter.

### Where it should live — three options

**Option A — new `fact_type="document"` in the existing typed fact ledger (RECOMMENDED).**
Add one member to `MatterFactType` (`api/app/schemas/matter_memory.py:124-138`) — additive, a one-line
enum + a one-line ORM CHECK tuple update (`app.models.project._MATTER_FACT_TYPES`) + a one-line
migration DDL (the pattern is documented as the extension path right in the enum docstring, `:128-130`).
A document entry is a fact like any other: `body_md` = the description, plus a structured handle to the
`file_id`/filename. It inherits, for free:
- **Auto-write-then-correct** (ADR-F042): the agent records/updates entries via a guarded write tool;
  the human corrects via the authenticated correction path; human-pinned wins.
- **Bi-temporal supersede** (ADR-F043): "v3 superseded by v4" is `invalid_at`/`superseded_by` — never a
  destructive edit; "what was current when" is queryable (`matter_facts_as_of`, ADR-F044).
- **Provenance** (`run_id`, `author='agent'`, source citation) and the existing **consolidation/Lint**
  pass (`consolidate_matter_memory`) which already loads live facts and can prune stale doc entries.
- **The injection pattern** — render the live document facts into the inventory output and (optionally)
  a small fenced prompt block, exactly like the wiki/roster.

  *Trade-off:* the fact ledger is "short statements," and a doc entry wants a couple of structured
  fields (role/side/status, `file_id`). Either overload `body_md` with a light convention, or add 2–3
  nullable typed columns to `MatterMemoryEntry` scoped to doc-kind rows. A small column add is honest
  and keeps the map queryable; this is the only real cost.

**Option B — keep it in the matter wiki prose (`Project.context_md`).** The wiki *already* invites
"the documents in play" (`update_matter_memory` docstring, `matter_memory_tools.py:84`). Zero schema
change: the agent just maintains a "## Documents" section. *Trade-off:* no structure — can't render an
annotated inventory programmatically, can't supersede a single doc entry cleanly (it's a 16k-char
rewrite each time), no per-document undo, and it competes with the wiki's 16k budget. **Good enough as
a stop-gap / the cheap first slice; not the durable home.**

**Option C — a dedicated `matter_document_notes` table (or columns on `File`/`Document`).** A purpose-built
structure keyed to `file_id` with description/role/side/status. *Trade-off:* a whole new auto-write
surface (validation, guard tool, correction endpoint, undo, injection, tests) — it duplicates
everything the fact ledger already provides. Only justified if document metadata grows far beyond a
description (custom fields, per-clause tags). **Over-engineering for the stated need.** Note: putting
descriptions directly on `File`/`Document` (an extension column) is tempting but *wrong under
ADR-F042* — those are model-free ingest artifacts, and a description is agent-written content that
needs the supersede/correct/undo machinery, which the ledger has and the bare columns don't.

### Recommendation

**Start with B (wiki "## Documents" section, prompt/skill only — zero schema) to prove the behaviour,
then graduate to A (`fact_type="document"` + a light structured handle) as the durable home.** A reuses
the entire ADR-F042/F043/F044 spine — write tool, supersede, provenance, correction, undo,
consolidation, injection — so the marginal build is small and the design is consistent with everything
already shipped. Avoid C unless the metadata genuinely outgrows a description.

### How it's maintained (auto-write-then-correct)

The agent updates a document's entry **as it learns** — on first read ("this is the MSA, our draft"),
on a new version arriving ("v4 supersedes v3"), on a status change ("escrow point resolved"). Same
discipline as the wiki/ledger: code-validated write (reject-not-truncate), supersede-not-overwrite,
human-pinned corrections immutable to the agent (B2). The lawyer corrects a wrong description /
re-labels a side via the authenticated correction path, and that correction wins — exactly the
ADR-F042 contract, no new governance.

### How it's injected / discovered

Render live document facts **into the existing inventory** so `search_documents("")` returns annotated
lines (the agent already calls this — no new tool needed for discovery). Optionally also a small fenced
"## Documents in this matter" prompt block for the most-relevant handful, same posture as the
roster/wiki. **Do not** inject all document *contents* — the map is descriptions; contents come on
demand via `read_document`/`search_documents`.

### Staleness

The map is annotated *live state* (the same philosophy the matter-memory research landed on:
"the live state is the source, not a stale snapshot"). Three guards: (1) the bi-temporal ledger makes
"superseded" explicit rather than deleting; (2) the consolidation/Lint pass already prunes stale facts
and would prune stale doc entries; (3) the inventory is generated from live `File` rows, so an
attach/detach is visible immediately — a doc-fact whose `file_id` no longer resolves is a Lint target.

### Relationship to the authorship roster (ADR-F048)

**Siblings, kept separate.** The roster (`MatterParticipant`: display_name, side ∈
{ours, counterparty, other, unknown}, trust ∈ {inferred, confirmed}, `composition.py:362-384`) answers
*who*; the documents map answers *what*. They **cross-reference**: a document entry's `side` should be
derived from / consistent with its author's roster `side` (the counterparty's markup is authored by a
`counterparty` participant). The hand-back doctrine already buckets edits by author-side
(`MATTER_REVIEW_DOCTRINE`, `composition.py:109-117`); the map extends that from *edits* to *whole
documents*. **Do not** fold documents into `MatterParticipant` — different cardinality, different
lifecycle (a person persists; a document gets superseded), different correction semantics.

---

## 5. PageIndex assessment

### What it is / how it works

PageIndex (VectifyAI, github.com/VectifyAI/PageIndex, ~33.5k stars) is a **vectorless,
reasoning-based RAG** framework. Two phases: **(1) tree-building** — an LLM reads a document once and
produces a hierarchical "table-of-contents" tree (chapters → sections → paragraphs) with a generated
summary per node; **(2) retrieval** — an LLM agent is shown only node titles/summaries and *reasons*
which branch holds the answer, navigating down and extracting full text from the chosen nodes (no
cosine similarity, no vector DB). It targets structured/long documents (SEC filings, contracts,
manuals) and reports **98.7% on FinanceBench** with full path-level explainability — every answer
traces to specific sections.
(Sources: medium.com/@visrow/how-pageindex-works…; github.com/VectifyAI/PageIndex;
venturebeat.com/infrastructure/this-tree-search-framework-hits-98-7…)

### OSS vs cloud

OSS repo = tree-build + agentic-retrieval scripts you run locally (PDF parsing via PyMuPDF/PyPDF2).
Cloud (dash.pageindex.ai) adds managed OCR, an optimized tree-build pipeline, REST/MCP endpoints, SLAs,
enterprise (VPC/on-prem). The OSS version carries **zero restrictions**; cloud terms are separate and
don't bind the OSS code. (github.com/VectifyAI/PageIndex README; docs.pageindex.ai)

### Gateway-egress implication — the load-bearing question, **verified**

**Verdict: REFUTED that vendoring would require adapter work to satisfy our no-direct-egress rule.**
The adversarial check found `requirements.txt` pins `litellm==1.83.7` with **no** direct
`openai`/`anthropic`/`google` SDK; `pageindex/utils.py` calls `litellm.completion(...)` /
`litellm.acompletion(...)` only; a GitHub code search for `import openai` / `from anthropic` returned
**no results**. LiteLLM is a pluggable abstraction that can be pointed at a custom endpoint via env
config. **So PageIndex already routes through a configurable client and could be aimed at our gateway**
(configure LiteLLM's base URL/key to the gateway's OpenAI-compatible surface) — *provided* the gateway
exposes a LiteLLM-compatible endpoint and we treat that wiring as the egress seam (ADR-F010). This is a
config exercise, not a fork-the-library exercise. **Caveat:** it still introduces LiteLLM as a *new
egress-capable dependency in `api/`* — the discipline of "only the gateway holds keys / only the
gateway egresses" means we'd be adding a second HTTP-LLM client into the API image and trusting its
routing config; that is a real surface to weigh even though no *code* change is needed.

### License / SBOM verdict

**Verdict: CONFIRMED — MIT (Copyright 2025 Vectify AI).** Fully compatible with Apache-2.0 posture;
not AGPL, not source-available, not non-commercial. (github.com/VectifyAI/PageIndex/blob/main/LICENSE)

### Dependencies

Five direct: `litellm`, `pymupdf`, `PyPDF2`, `python-dotenv`, `pyyaml` — no torch/tensorflow, no
vector-DB client, no browser engine. We **already** depend on PyMuPDF (the ingest pipeline's PDF
canonical-text reader). The genuinely new surface is **LiteLLM** (and its transitive OpenAI SDK) —
which the fork does *not* use today and which is, by design, an egress-capable client. That is the
SBOM/supply-chain line item to justify, and it cuts against adding it lightly.

### Legal-doc fit

Strong *on paper* for big structured documents (the explainability + section-path tracing is genuinely
attractive for audit). **But** the FinanceBench result is on SEC filings; the open question
"does it transfer to contracts/regulatory docs" is unverified for our exact workload.

### Clear verdict: **SKIP NOW** (revisit later behind a measured trigger)

Reasoning:
- **It solves a problem we don't have yet.** PageIndex is a *within-a-large-document* retriever. Our
  documents are contracts/emails that overwhelmingly fit under the 40k-char read cap (a typical NDA is
  4k–13k tokens). The maintainer's actual pain is *picking the right document among many* — a
  *cross-document* description problem the documents map solves directly, and which PageIndex does not
  address.
- **We already have cross-chunk retrieval (FTS) and a citation engine.** Adding tree-RAG duplicates the
  "find the passage" job FTS does, while the precise-offset citation invariant
  (`document.py`/`api/app/citation/__init__.py`) is already our explainability story.
- **Cost + complexity.** ~137 gateway calls to tree-build *each* document is real spend and latency on
  our gateway, plus a new egress-capable dependency (LiteLLM) — against the maintainer's explicit "if
  reading the whole document makes sense, just put it in context" preference.
- **The build-our-own-lighter option dominates** for the rare oversized doc: our chunks already carry
  `page_start`/`page_end` and headings-capable structure; a cheap "section map from chunk
  headings/pages" gives PageIndex-style navigation hints with **zero** new dependency and **zero** extra
  gateway calls. Prefer that if the need ever materializes.

**Trigger to revisit (adopt-later):** if we observe real matters where a *single* document exceeds the
read cap *and* FTS demonstrably fails to surface the right section (measured, not assumed). At that
point evaluate (a) our own chunk-derived section map first, then (b) PageIndex-via-gateway if the
section map is insufficient — and pay the LiteLLM SBOM cost deliberately.

---

## 6. The balance: inline vs map vs index

This is the core of the question. The decision is keyed on **single-document size**, **document
count**, and the **token budget of the chosen model** — grounded in the verified token math (1 token ≈
4 chars ≈ 0.75 words; a typical NDA = 4k–13k tokens; legal text tokenizes slightly denser) and the
"lost in the middle" finding (models effectively use far less than their advertised window; relevant
content buried mid-context loses ~30% retrieval accuracy).

Our concrete constants: `read_document` cap = **40,000 chars (~10k tokens)** (`tools.py:65`); operating
budget = **200k input tokens**, compaction at ~170k (`factory.py:33`). The model is **injected and
replaceable** through the gateway — so the rule is stated relative to the *active* model's effective
window, not a single vendor.

### The decision rule

**1. JUST READ THE WHOLE DOCUMENT — the common case, no machinery.**
When a single document is **≲ 40k chars (~10k tokens)** *and* the task needs that document, call
`read_document` (or paste it into context) and reason over the full text.
- Covers the overwhelming majority of contracts/NDAs/letters.
- Preserves cross-clause relationships (definitions ↔ liability cap ↔ governing law) that chunking
  fragments.
- Costs nothing to build; it's already implemented.
- **This is the maintainer's default and it should stay the default.** Tokens are cheap enough that for
  one ordinary contract, inlining beats any retrieval machinery on both accuracy and simplicity.

**2. ADD THE MAP (annotated inventory) — when there are roughly 5+ documents.**
The map is *descriptions*, not contents. It changes *selection*, not *reading*: the agent picks the
right document by meaning, then still inlines that one document per rule 1.
- Cost: a few hundred tokens for the whole matter — trivially affordable.
- This is where the documents map (§4) earns its keep: it's the cheap layer that prevents the
  wrong-document failure without touching how documents are *read*.
- Rule of thumb from the research: **< 5 docs and each < ~15–20k tokens → inline with good ordering;
  ≥ 5 docs → maintain a lightweight description layer and select before reading.**

**3. USE FTS FOR PASSAGES — when a doc is too big to inline, or the question is clause-targeted across
several docs.**
Already built (`search_documents(query)`). Pull the top passages with page anchors, cite precisely.
This is the existing answer for "the doc is 200 pages, find the indemnity clause," and it needs no new
work.

**4. CONSIDER A TREE-INDEX — only when a *single* document is so large that even chunked FTS can't
reliably locate the right section.**
A threshold we **do not hit today**. If we ever do: build the lighter chunk-derived section map first
(§5), and only reach for PageIndex-via-gateway if that proves insufficient. Indexing has an
infrastructure/cost tax (tree-build calls, a new dependency) that must be paid for with measured
evidence, not anticipation.

### Why "just read it" wins so often (the honest economics)

The research's "context window illusion" cuts *both* ways: it argues against *stuffing many large
documents* into one prompt (mid-context content degrades ~30%), but it argues *for* inlining a *single*
in-scope document — one 10k-token contract sits comfortably in the high-attention region, with full
fidelity, no retrieval indirection, and no machinery. The failure the research warns about is dumping
*10 documents* into context and hoping; the documents map prevents exactly that by ensuring the agent
inlines the *one right* document instead of many wrong ones.

### One nuance for the multi-doc inline case

If the agent ever does inline several documents at once (rare — prefer selecting one), apply
**strategic ordering**: most-relevant documents at the **beginning and end**, lower-relevance in the
middle, to dodge the U-shaped attention curve. But the better move is almost always: **use the map to
pick one, inline that one.**

---

## 7. Confusion-avoidance

How to keep the agent picking the right document across turns — in priority order, cheapest first:

1. **Descriptions read first (the documents map, §4).** The single highest-leverage fix: when the
   inventory says `Cirrus_MSA_v4_clean.docx — our current MSA draft, v4 [ours · current]` instead of
   just `Cirrus_MSA_v4_clean.docx (38 pages)`, the agent selects by *meaning*, and "current" vs
   "superseded" is explicit. This directly kills the stale-draft and whose-file-is-this failures.

2. **Active-document stickiness — currently MISSING.** There is **no** active/current-document state in
   the codebase (verified: grep finds nothing). The agent re-discovers each turn, so it can drift
   between similarly-named files. Cheap fix with **no schema change**: a convention that the matter wiki
   names the "document(s) in play" (the wiki already invites this), reinforced by a prompt line — "when
   the user says 'the contract' without naming a file, it means the active document recorded in matter
   memory; confirm if ambiguous." This gives cross-turn focus using machinery that already exists.

3. **Disambiguate / ask, don't guess.** The read path *announces* duplicate names but still auto-picks
   readable+newest (`tools.py:234-239`) — fine for re-uploads, risky for semantically distinct
   collisions. For genuine *selection* ambiguity (the user's request maps to several plausible
   documents), the agent should **surface the choice** rather than silently pick. Cheap: a skill/prompt
   rule "if more than one document plausibly matches the request and they differ in substance, list
   them and ask." (The plumbing already returns enough info to do this.)

4. **Naming hygiene.** Encourage (via the documents map description, not by renaming files) that each
   document carries a human-readable role in its *description* — the agent shouldn't rely on filenames
   to encode "current/our-side/round-2," because filenames lie (`NDA_FINAL_v3_clean(2).docx`). The map
   is where role/status lives authoritatively.

5. **Lost-in-the-middle mitigation.** Keep the high-value, frequently-referenced material near the
   prompt's edges. In practice for us that means: inject the *map* (small, high-value) in the fenced
   region; don't bury the active document's content in the middle of a stuffed context — inline it as
   the focused working document. Strategic ordering only matters when multiple docs are inlined (rare;
   §6).

**What Claude Code itself does, and what transfers.** Claude Code does **agentic search, not RAG**:
`Glob` (filenames) + `Grep` (content) + `Read` (known paths), iterating — query → result → "not quite"
→ refine — keeping a lightweight mental map and reading on demand, with **no vector index** ("no
indexing tax"). **What transfers and is already true for us:** our model *is* this — `search_documents`
(≈ glob via empty-query inventory + grep via FTS) + `read_document` (≈ read), model-driven, no index.
The fork is already on the right architecture. **What transfers and is missing:** Claude Code's files
*self-describe* (a path like `src/auth/login.ts` and the code inside tell you what it is); our
documents *don't* (a filename + page count tells you almost nothing). The documents map is precisely
the "make documents self-describing" layer that lets the agentic-search loop pick correctly — it's the
adaptation of Claude Code's approach to opaque legal blobs.

---

## 8. Recommended decomposition

Vertical slices, dependency-ordered, ≤2–3 days each, one PR each. **The next fork ADR number is F049**
(highest accepted is F048).

### Cheap wins now

- **Slice 1 — Single-upload airtightness (no schema, no ADR).** Strengthen `MATTER_PROMPT` / the
  matter skill so a single-document matter is *read before answering*; add a test asserting the agent
  lists/reads on a one-doc matter before responding. Tightens the one residual single-upload failure
  mode (§3). *Diff describable in a sentence — skips the plan; folds the standard security +
  simplification pass.*

- **Slice 2 — Documents map, prose stop-gap (no schema; ADR-F049 drafted here).** Teach the agent (via
  the matter-memory skill + a prompt line) to maintain a "## Documents" section in the matter wiki —
  `{filename → one-line description · role · side · status}` — and to read it first when selecting. Plus
  the active-document convention (§7.2): name the document(s) in play. This proves the behaviour using
  only existing machinery (Option B, §4) and validates the map's *shape* before committing schema.
  **Needs ADR-F049 ("documents map")** because it makes the architectural call (auto-write-then-correct
  applies to a per-document description layer; map vs index; relationship to roster) — draft it in this
  slice's PR even though the *implementation* is prompt-only, so the typed slice (4) builds on an
  accepted decision.

- **Slice 3 — Annotate the inventory + disambiguation hand-off (small code, no schema).** Make
  `_inventory()` render any description it has (initially from the wiki section / later from the typed
  store) so `search_documents("")` returns annotated lines; add the "ask when selection is genuinely
  ambiguous" skill/prompt rule (§7.3). Low-risk, high-leverage.

### Only-if-needed later

- **Slice 4 — Typed documents map (`fact_type="document"`).** Promote the map to the typed fact ledger
  (Option A, §4): additive `MatterFactType` member + ORM CHECK tuple + one migration; a guarded
  `record_document_note` write tool (code-validated, reject-not-truncate); optional 2–3 nullable
  structured columns (role/side/status/`file_id`) on `MatterMemoryEntry` for doc-kind rows; render into
  inventory + a fenced block; wire into the existing consolidation/Lint pass; correction via the
  existing authenticated path. Reuses the whole ADR-F042/F043/F044 spine — marginal build is small.
  *Builds on accepted ADR-F049; a thin addendum if columns are added.* Do this **only after** Slice 2
  shows the prose map is too lossy to maintain at scale.

- **Slice 5 — Cross-link map ↔ roster.** Derive a document entry's `side` from its author's roster
  `side` (consistency check / auto-suggest), extending the hand-back author-bucketing from edits to
  whole documents (§4). Depends on Slice 4.

- **Backlog (no slice until triggered) — oversized-document navigation.** If and only if we *measure* a
  single document exceeding the read cap where FTS fails to locate the right section: first a
  chunk-derived section map (zero new dependency, zero extra gateway calls), then evaluate
  PageIndex-via-gateway with the LiteLLM SBOM cost paid deliberately. Would need its own ADR if a
  dependency is added.

---

## 9. Open questions for the maintainer

1. **Map home — prove-then-promote, or go typed straight away?** Recommendation is Slice 2 (prose
   stop-gap) → Slice 4 (typed `fact_type="document"`). Are you happy to validate the *shape* in prose
   first, or do you want the typed store from the outset (skip Slice 2, accept more up-front build)?

2. **Structured columns on `MatterMemoryEntry`, or convention in `body_md`?** A small column add
   (role/side/status/`file_id`) makes the map cleanly queryable and renderable; the convention-only
   route avoids a migration but loses structure. Which side of that trade do you want?

3. **Disambiguation aggressiveness.** When several documents plausibly match a request, should the agent
   *always* ask, or auto-pick the best and *announce* (as the read path does today for duplicate names)?
   This is a UX-friction vs safety call only you can set — and it differs for true duplicates
   (auto-pick fine) vs semantically distinct collisions (ask).

4. **Active-document stickiness — convention vs state.** §7.2 proposes a wiki/prompt convention (no
   schema). Is that sufficient, or do you want a first-class "active document" the cockpit can show and
   the lawyer can set/override (more build, clearer UX)?

5. **PageIndex trigger threshold.** Do you accept "skip now, revisit only when a measured single
   document exceeds the read cap *and* FTS fails," or do you want a spike on a real large legal document
   (e.g. a long credit agreement) *now* to de-risk the eventual decision? Either is defensible; the
   former matches your "don't build machinery if reading works" preference.

6. **LiteLLM as a second egress-capable client in `api/`.** Even pointed at the gateway, adopting
   PageIndex means LiteLLM (+ transitive OpenAI SDK) lives in the API image. Is that acceptable
   supply-chain/egress surface if/when the time comes, or is "build-our-own-lighter section map" the
   only acceptable path to keep the gateway the sole LLM client?

7. **Read cap (40k chars / ~10k tokens).** The whole balance rule pivots on this constant
   (`tools.py:65`). With a 200k operating budget and replaceable models, is 40k still the right
   "inline the whole doc" ceiling, or should it rise (fewer truncations, more inlining) now that the
   common case is "just read it"?

---

### Honest limits of this dossier

- **The single-upload case** is verified airtight on plumbing; the residual is behavioural and rests on
  prompt discipline — there is no test today proving a single-doc matter is read before answering
  (Slice 1 adds one).
- **PageIndex's legal-document accuracy is unverified for our workload** — the 98.7% is FinanceBench
  (SEC filings); transfer to contracts/regulatory text is an open question the research flagged and we
  did not close.
- **The "5+ documents" and "40k-char inline" thresholds are defensible rules of thumb**, grounded in
  the verified token math, not measured against our own corpus — treat them as starting points to
  calibrate, not laws.
- **No production telemetry** on how often agents actually re-list vs read, or how often the
  wrong-document failure occurs today — so the gap in §3 is reasoned from the code's shape (no
  descriptions, no stickiness), not from incident data.
