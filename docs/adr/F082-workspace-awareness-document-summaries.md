# F082 — Workspace awareness: exact-duplicate detection + per-document summaries

Status: proposed (drafted 2026-07-11, maintainer request same day — WORKSPACE-1)

## Context

Lawyers are not used to this tooling. Two concrete failure modes the maintainer flagged: they upload
the same document twice (`contract.docx`, `contract (2).docx`), and they refer to documents
sometimes by name and sometimes by content. Today the agent's document inventory
(`app.agents.tools._inventory`) shows only name / pages / read-cost, so the agent can (a) treat two
identical uploads as two distinct documents, and (b) has no memory of what a document *is* once it
has read it — it must re-read to re-learn.

Two capabilities close this: **exact-duplicate awareness** and a **per-document summary** the agent
records after reading. The substrate already carries the hard part: every uploaded file stores a
content hash (`files.hash_sha256`, non-unique index since migration 0003), so exact duplicates are a
scoped group-by, not new state. No per-file summary column exists anywhere.

## Considered options

1. **Store a summary as a Matter Fact** (`matter_memory_entries`, kind extended) — rejected: the
   bi-temporal fact ledger is world-time ("what did we believe at signing"), has no `file_id`, and
   is never injected; a per-file description is a category mismatch.
2. **Fold per-file summaries into the Matter File wiki** (`projects.context_md`) — rejected: a single
   16k matter-level blob does not scale to a matter's many files and has no structured dup edge.
3. **A file-keyed summary + code-computed exact dedup** — chosen. `summary` lives on `files` (where
   filename, hash, and lifecycle already live, and which the inventory lists); duplicates are
   computed at read time from `hash_sha256`, never stored and never agent-asserted.

## Decision outcome

**Summary storage — on `files` (migration 0096).** Three additive nullable columns: `summary`
(TEXT, bounded at the write boundary — reject-not-truncate, not a DB CHECK), `summary_updated_at`,
and `summary_run_id` (FK `agent_runs` **`ON DELETE SET NULL`**, mirroring `created_by_run_id` — the
summary outlives the run that wrote it, but carries honest provenance). One agent tool,
`record_document_summary`, area-agnostic and granted to every matter-bound run, guarded through
`guarded_dispatch` (R4/R5/R6), auto-write-then-correct (ADR-F042): the agent maintains it, the human
owns it after; re-recording overwrites; there is **no domain audit row** (the guard envelope is the
only receipt, so no summary or document text leaks to audit).

**Duplicate detection — computed, scoped, never forged.** `duplicate_of_map` groups the matter's
live files by `hash_sha256` (owner-re-asserted, `deleted_at IS NULL`, matter-scoped via
`_matter_files_query`); the earliest-created file of a set is canonical, every other maps to it. The
agent **never** asserts a duplicate — a hostile document could forge that claim — so the edge is
derived from bytes in code. Cross-matter / cross-owner identical bytes are never revealed (no
existence leak; the 404 discipline).

**Surfacing.** The agent's on-demand inventory gains `— (duplicate of X)` and `— <summary>` markers
(WS-1). A bounded, data-only-fenced "Documents in this matter" prompt block (WS-2) and a Documents-
panel duplicate badge (WS-3) follow as their own slices.

**Summary timing — only when the agent reads a document** (maintainer decision): free, no extra
model call, a byproduct of the agent's own gatewayed read. A document nobody has opened stays
unsummarised but remains fully exact-dup-detectable by hash. No eager/at-ingest summariser (the
ingest workers carry no gateway LLM).

## Review hardening (adversarial review of PR #271, 2026-07-12 — 18 confirmed findings, all
addressed)

- **Resolver parity:** `resolve_matter_file_by_name` now uses the READ path's exact rule
  (case-insensitive, readable-copy-first, `coalesce(attached_at, created_at)` recency) so a summary
  can never bind to a same-named file the agent didn't read.
- **Forgery rejection at the boundary:** a summary may not contain newlines/control characters
  (line/fence forging) or the literal `"(duplicate of"` (spoofing the code-derived byte-identity
  marker) — rejected with fix-and-retry, applied to BOTH the agent tool and the human endpoint.
  Residual (accepted, pre-existing class): file NAMES are user-supplied and can carry misleading
  words — the fence now says so explicitly and scopes the marker claim to its rendered position.
- **The human half now exists:** `summary_author` (`'agent'`/`'human'`, CHECK) + `PUT
  /matters/{project_id}/files/{file_id}/summary` (MutatingUser — viewer excluded, owner-scoped 404,
  null clears). A human-set summary is a pin: the agent tool refuses to overwrite it. The Documents-
  panel *edit affordance* is backlogged (the API control exists; MILESTONES § Backlog).
- **Honesty:** stale summaries (bytes mutated after the summary — editor save/redline convergence)
  carry an explicit "may be stale" suffix everywhere (`summary_stale` on the API); the injected tier
  renders F066 provenance for work products/snapshots instead of "not yet read"; the fence states
  the check is byte-identity ONLY (absence of a marker proves nothing about near-identical
  revisions); every rendered line is clamped (unbounded filenames).
- **One query per surface:** dup grouping is a pure function over rows the surface already holds.

## Consequences

- Exact-duplicate awareness is deterministic and cheap; **near-duplicate** ("same contract, lightly
  edited") clustering is deferred — the embedding substrate exists but is a later slice, and any
  agent near-dup hint is untrusted prose, fenced, never a code assertion.
- A summary distilled from an untrusted counterparty document is itself untrusted-origin: every
  surface that shows it carries the matter-memory data-only fence and a size cap (~1000 files/matter
  would otherwise blow the prompt — the injected block is bounded with a visible truncation tail).
- The `summary_run_id` FK means the write requires a live run; production tool calls always run
  inside one. Tests must seed a real `agent_runs` row (surfaced in WS-1).
- Grant confinement holds: `DOCUMENT_SUMMARY_TOOL_NAMES` is disjoint from every other matter/domain
  grant, and `record_document_summary` is added to `hitl_eligible_tool_names()` (an admin *could*
  gate it, though pausing before a description is rarely wanted).
- `files` gains write traffic on the summary columns only; the redline/WOPI in-place mutators are
  untouched (they write bytes/hash/`updated_at`, a disjoint column set).
