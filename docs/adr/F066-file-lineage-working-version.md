# F066 — File lineage + working-version resolution (redline continuity)

Status: accepted (maintainer approved the spec 2026-07-07)
Date: 2026-07-07
Deciders: maintainer + agent lead
Slice: R-1
Plan of record: `docs/fork/plans/PIVOT-modular-azure.md` § Workstream R (maintainer-approved
2026-07-07).

## Context

Live, maintainer-reported bug: the Commercial agent redlines a contract via its Adeu-SDK tools and
saves the redlined `.docx`; on a follow-up instruction ("further redline the document") it redlines
the ORIGINAL upload again instead of continuing from its own redlined output. Root cause is
structural, not model behaviour — four reinforcing gaps:

1. **Filename resolution.** Every redline tool resolves its source by exact case-insensitive
   filename (`fetch_matter_docx`, `api/app/agents/tools.py`; its `order_by` only tie-breaks among
   same-named rows). Redline output is a NEW `File` row under a DIFFERENT name
   (`_redlined_filename`: "contract.docx" → "contract (redlined).docx";
   `respond_to_counterparty` likewise via `_response_filename`), so "the document" the lawyer
   names always resolves back to the original.
2. **No lineage.** `File` (`api/app/models/file.py`) had no parent/derivation column — only
   `created_by_run_id` (run → file) and `updated_at`. Nothing records that the redlined row was
   derived FROM the original.
3. **Doctrine reinforcing the bug.** The `apply_redline` docstring and
   `skills/surgical-redline/SKILL.md` actively SAID each call re-redlines the original afresh; and
   the matter inventory rendered the un-ingested work product as "(not ingested yet — status:
   ready)" — it read as a pending upload, not as the agent's latest draft.
4. **WOPI in-place mutation.** The in-app editor's FIRST human save
   (`api/app/api/wopi.py::put_file_contents`) overwrites the redlined row's bytes IN PLACE
   (`created_by_run_id` flipped to NULL) and creates a NEW snapshot row "... (agent draft).docx"
   preserving the prior bytes — so even a heuristic over `created_by_run_id` or names breaks the
   moment a human touches the document.

Desired: a follow-up redline defaults to continuing from the agent's own latest working version;
the original is the starting point only when the lawyer explicitly asks for it.

## Considered Options

1. **Doctrine-only** — teach the agent (skill + system prompt) to target its own output by name.
   Advisory only: the resolver still returns the original for the name the lawyer uses, the model
   must remember and spell the derived filename exactly, and the WOPI rename/snapshot churn breaks
   it. No enforcement anywhere.
2. **Filename-suffix heuristic** — resolve "contract.docx" to the newest row whose name extends it
   ("contract (redlined).docx", …). Brittle: collides with "(response)" outputs whose subject is a
   DIFFERENT source document, breaks when the editor mutates rows and mints "(agent draft)"
   snapshots, and becomes ambiguous after multiple generations. Encodes semantics in display
   strings.
3. **`parent_file_id` lineage + `is_snapshot` + a working-version resolver + explicit
   `start_fresh`** — record derivation as data; resolve "the document" by walking the chain.
4. **Full document-version table** — first-class versions with numbering, authorship and
   diff-ancestry. The right long-term shape for org-wide versioning, but far more surface than
   this bug needs; nothing else consumes versions yet.

## Decision Outcome

**Option 3.** Lineage becomes two additive columns; continuation becomes resolution, not memory.

- **Migration 0089** adds to `files`: `parent_file_id` (nullable, FK `files.id`
  `ON DELETE SET NULL`, indexed, same type as `files.id`) and `is_snapshot`
  (`BOOLEAN NOT NULL` server-default `false`).
- **Write-side lineage:** redline and response outputs set `parent_file_id` = their source row's
  id; the WOPI first-save snapshot row sets `parent_file_id` = the live (overwritten) file's id
  AND `is_snapshot = True`. The WOPI live row keeps its id across human saves, so the chain leaf
  stays stable while the editor mutates bytes in place.
- **Working-version resolver** (`resolve_working_docx`, `api/app/agents/tools.py`): from the
  document the lawyer names, walk the lineage chain to the NEWEST non-snapshot leaf — newest
  compared across the whole descendant tree, so a diverged lineage (`start_fresh`, or an
  explicitly named branch) resolves to wherever the latest work happened, not to the newest
  immediate child's branch. That leaf is "the document" for redlining purposes. Snapshots are
  immutable prior-version copies and are never a working version.
- **Tool defaults:** `apply_redline` / `preview_redline` grow `start_fresh: bool = False` and use
  the resolver by default; `start_fresh=True` is the explicit "start over from the named original"
  escape hatch. `extract_counterparty_position` and `respond_to_counterparty` KEEP exact-name
  semantics — their subject is the counterparty's named document, not our working draft.
- **Version-aware naming** keeps chains readable: "contract (redlined).docx" →
  "contract (redlined v2).docx" → v3 ….
- **Honest surfaces:** the matter inventory renders derivation/provenance instead of "not ingested
  yet"; tool results state which version they continued from; docstrings, the surgical-redline
  skill and one sentence of matter doctrine (`MATTER_REVIEW_DOCTRINE`,
  `api/app/agents/composition.py`) describe the new default without contradicting the
  editor-handback doctrine (an editor-edited hand-back still goes through
  `review_edited_document`, ADR-F047).

## Consequences

- **Good:** follow-up instructions build on prior work by default — the failure mode silently
  discarding the agent's own redline is closed at the resolver, not by prompt discipline; the
  lawyer keeps naming the document naturally; an explicit restart stays one parameter away;
  snapshots are excluded from working chains so editor history can't shadow the live draft.
- **Bad / cost:** a migration (0089); legacy rows (pre-0089) have no lineage and resolve to
  themselves — a pre-migration redline is NOT found as its original's working version (matches the
  old behaviour, so no regression, but no retroactive continuity either). `ON DELETE SET NULL`
  means deleting a mid-chain row splits the chain: the derivative survives as its own root.
- **Kept as-is:** exact-name semantics for the counterparty-subject tools; the WOPI
  overwrite-in-place + snapshot design (this ADR layers lineage onto it, it does not change it);
  `guarded_tool_call`, audit (counts/types/IDs) and the gateway are untouched.
- A future org-wide document-versioning ADR (option 4 territory) may supersede this lineage
  scheme; until then these two columns are the only versioning truth.
