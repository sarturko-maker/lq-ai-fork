# Plan — WORKSPACE awareness: duplicate detection + per-document summaries

**Status:** drafted 2026-07-11 · maintainer decisions captured (see § Decisions).
**WS-1 (backend) LANDED 2026-07-11** — code + 12 tests green (also 143 impacted + mypy clean); ADR-F082
drafted; migration 0096. Note surfaced: `summary_run_id` FK requires a live run (provenance; tests seed
one).
**WS-2 (prompt injection) LANDED 2026-07-12** — `MATTER_DOCUMENTS_PROMPT` data-only fence, 6th tier in
`render_memory_tiers` (last of the matter tiers), `load_matter_documents_block` bounded 30 lines/8000
chars with a visible `+K more` tail; 15/15 suite green. Trap surfaced: do NOT edit api/ files while a
containerized pytest run is collecting off the live mount (raced once → phantom fixture errors; clean
re-run authoritative).
**WS-3 (backend read-model) LANDED 2026-07-12** — `MatterFileRead` gains `summary` + `duplicate_of`
(computed via the same `duplicate_of_map` rule the agent sees). Web half (badge + tooltip + vitest)
delegated; verification pending.
**Milestone:** WORKSPACE (new). Slices WS-1 (backend) → WS-2 (prompt injection) → WS-3 (UI badge).
**Linked ADRs:** F042 (auto-write-then-correct), F049 (tier middleware / Store), F010 (gateway sole egress).
New ADR: **F082** (workspace awareness) — drafted in WS-1.

## Why

Lawyers are not used to this tooling. They upload the same contract twice ("contract.docx",
"contract (2).docx"), and they refer to files sometimes by name, sometimes by content. Today the
agent sees a bare per-file inventory (name, pages, ~tokens) and has **no** signal that two files are
the same bytes, and **no** memory of what a document *is* once it has read it. So it can treat two
copies as two contracts, or re-read a doc it already understood. We fix both.

## What the research established (grounded)

- Every uploaded file already carries a content hash: `files.hash_sha256` (NOT NULL) with a
  **non-unique** index `idx_files_hash` (mig `0003:129`). So **exact-duplicate detection is free** —
  a scoped `GROUP BY hash` lookup, computed at read time, always correct, never stale.
- There is **no** per-file summary anywhere: `File` has no summary column, `Document` has no summary
  column (`api/app/models/file.py`, `api/app/models/document.py`). This is the only new storage.
- The agent's document listing is `tools._inventory` (`api/app/agents/tools.py:739`) — one line per
  file. This is the natural on-demand home for "— <summary> — (duplicate of X)".
- Read-only DATA tiers are injected into the system prompt by `TierMemoryMiddleware`
  (`tier_middleware.py:51`) from text pre-rendered at composition (`render_memory_tiers`,
  `composition.py:454`). A bounded "Documents in this matter" block would be a 5th block rendered
  here — but a matter can hold ~1000 files, so it MUST be capped (corrections precedent:
  30 rows / 8000 chars, `matter_memory_tools.py:54`).

## Decisions (maintainer, 2026-07-11)

- **Duplicates → agent-aware AND a UI badge.** The agent recognises duplicates and factors them in
  (won't treat two copies as two contracts; says so in chat); the Documents panel also shows a
  "⚠ duplicate of contract.docx" badge so the lawyer sees it without asking.
- **Summary timing → written when the agent reads a doc** (matches "after it has read it"). No
  eager/at-ingest summarizer — free, no extra model call, produced as a byproduct of the agent's own
  gatewayed read. Consequence accepted: a doc nobody has opened has no summary yet (still fully
  exact-dup-detectable by hash).

## Non-goals

- **Near-duplicate ("same contract, lightly edited") clustering** — deferred. The embedding substrate
  exists (`store.py:69` semantic index; matter hybrid retriever), so it is a later slice, not now.
  WS ships EXACT dup only. Any near-dup hint the agent offers is untrusted prose, fenced, never a code
  assertion.
- **Eager / background summarization** at upload/ingest (decided against; would need the ingest
  worker wired to a gateway LLM it does not have today).
- **Blocking or de-duplicating uploads** — we surface, we don't prevent (the lawyer may want two
  copies). Cross-matter dedup is out (existence-leak surface; stay project-scoped).

## Slices

### WS-1 — backend: dedup signal + agent summary (one migration)
- **Migration `0096`**: add to the per-file record — `summary TEXT NULL`, `summary_updated_at
  TIMESTAMPTZ NULL`, `summary_run_id UUID NULL` (FK agent_runs, SET NULL). *Verify File↔Document
  cardinality first; put the column on the entity that is 1:1 with the uploaded blob — expected
  `files`, because filename + hash + lifecycle (`deleted_at`) already live there and `_inventory`
  lists files.*
- **Exact-dup helper** (code, not agent): `duplicate_groups(project_id, owner_id)` → for the matter's
  live files (`deleted_at IS NULL`), group by `hash_sha256`, return the canonical (earliest
  `created_at`) file per hash and its copies. **Scope to project_id AND assert owner** — never a bare
  hash lookup (existence leak → 404 discipline). Canonical = oldest; copies point at it.
- **Agent tool** `record_document_summary(file_id, summary)` — guarded (`guarded_dispatch`),
  matter-scoped, auto-write-then-correct (author = agent; the human owns it afterwards via the same
  correct/undo affordances as the Matter File). Caps: summary ≤ ~600 chars. Writes
  `summary`/`summary_updated_at`/`summary_run_id`. Audit receipt = counts/ids only, never the summary
  text or document content.
- **Enrich `_inventory`**: each line gains `— <summary>` when present and `— (duplicate of
  <canonical filename>)` when the file is a non-canonical copy. Duplicate marker computed from the
  helper, not from any stored/agent field.
- **Doctrine nudge** (Commercial + Privacy composition/skill prose): "before treating two files as
  distinct, check the inventory's duplicate marker; after you read a document, record a one-line
  summary against it so you and the lawyer can find it by content later." Keep it short.
- Tests: dedup helper (exact group, owner/project scoping, deleted_at excluded, no cross-tenant
  leak); `record_document_summary` guarded + auto-write + cap + audit counts-only; `_inventory`
  renders summary + dup marker; 404/authz on foreign file_id.

### WS-2 — inject a bounded "Documents in this matter" block
- Add a 5th read-only block to `render_memory_tiers` → `TierMemoryMiddleware`: for the matter's live
  files, "<filename> — <summary or 'not yet read'> — <dup marker>", **hard-capped** (reuse the
  corrections bound: ~30 lines / 8000 chars; if over, show the most-recently-touched N + a
  "+K more — list documents to see all" tail so truncation is never silent).
- Behind the **data-only fence** (copy `MATTER_MEMORY_PROMPT` posture, `composition.py:390`) — a
  summary distilled from a counterparty doc is untrusted-origin: DATA, never instructions.
- Loaded at composition (middleware does no DB reads), same path as corrections/roster.
- Tests: block rendered + fenced + capped + truncation tail; zero files → block absent (byte-identical
  prompt); the cap never blows the budget.

### WS-3 — UI: duplicate badge in the Documents panel
- Expose a computed `duplicate_of: {id, filename} | null` (and optionally `summary`) on
  `MatterFileRead` (`api/app/api/matter_files.py`), derived server-side from the WS-1 helper —
  owner-scoped, never a raw hash.
- `DocumentsPanel.svelte`: render "⚠ duplicate of <filename>" on non-canonical copies; a subtle
  tooltip showing the summary if present. Match the existing panel design language.
- Web tests (vitest, `CI=true npx vitest run`): badge shows on a copy, absent on canonical/unique;
  summary tooltip present when set.

## Traps (do not skip)

- **Dedup is forgeable if agent-asserted** — a hostile document could claim "this supersedes the real
  contract". Exact dup is computed in code from `hash_sha256`; the agent NEVER writes the dup edge.
- **Existence leak** — scope every dup lookup to `project_id`, assert `owner_id`, filter
  `deleted_at IS NULL`; cross-user/foreign file → 404, never 403, never "identical bytes exist
  elsewhere".
- **Untrusted summary origin** — the injected block and inventory carry the data-only fence.
- **~1000 files/matter** — the injected block is capped with a visible truncation tail; full list is
  on-demand via `_inventory`. Never full-inject.
- **Write discipline** — matter-tier auto-write-then-correct (author=agent, trust=normal). Must NOT
  land in company/practice read-only tiers; can never mint a human-pinned correction.
- **Gateway egress** — the only "LLM" here is the agent writing its own summary inside its already
  gatewayed run; no new egress, no background provider call.
- **File↔Document cardinality** — verify before choosing the column's table; lean `files`.

## Verification / DoD (ADR-F005 gate)
- Container suites (repo root mounted for root `ruff.toml`): API `tests/` + `tests/agents/` counts
  quoted; web vitest count quoted. mypy `app` in-container.
- Rebuild api + arq-worker + ingest-worker together for mig `0096`; `docker image prune -f` (dangling).
- Live: upload a doc twice on a throwaway matter → agent's inventory shows the dup marker + the panel
  shows the badge; agent reads a doc → summary recorded + visible on next inventory. Evidence under
  `docs/fork/evidence/workspace-awareness/`.
- Fresh-context adversarial review incl. security + simplification pass (dedup scoping / injection
  fence / no stray files / dead code). ADR-F082 drafted. HANDOFF + memory updated.
