# C3b — Typed bi-temporal matter facts + gateway-routed consolidation (split into C3b-1 / C3b-2)

**Status:** APPROVED scope (maintainer chose *split* + *in-run guarded tool*, 2026-06-23). Builds on
**C3a** ([[matter-memory-c3a-shipped]], PR #133) and **ADR-F042** (auto-write-then-correct). Supersedes the
single-slice C3b framing in `C3-matter-memory-track.md` §C3b. **Depends:** C3a ✓, ADR-F042 ✓.
**Research:** `matter-memory-patterns.md` + `matter-memory-reuse.md`.

## Why split

C3b-as-written bundles a **zero-model-call store layer** (typed columns + write + supersede + as-of query)
with a **security-sensitive gateway-egress layer** (the consolidation/Lint pass — the first matter-memory
code that calls a model). Per the iteration discipline (≤2–3d, one PR each) and to keep the egress security
review *isolated*, the maintainer split it:

```
C3a ✓ ─► C3b-1  typed bi-temporal fact store + guarded write tool + supersede + as-of query   (ZERO egress)
              └─► C3b-2  gateway-routed consolidation/Lint pass (the ADR-F010 egress slice)     (in-run tool)
                      └─► C3c  matter-scoped retrieval (memory_search/get) + cockpit panel + undo endpoint
```

## Resolved design decisions (within ADR-F042; recorded here, not a new ADR for C3b-1)

1. **Typed facts are new `kind='fact'` rows in the existing `matter_memory_entries` table** (the `0068`
   additive-nullable contract), not a new table. Correction/snapshot rows keep `body_md` + leave the new
   columns NULL; fact rows populate them. One temporal spine for the whole matter → one undo/audit/log path.
2. **A fact's statement reuses `body_md`** — no separate `value` column. This inherits the existing
   body-length CHECK and the no-leak audit envelope unchanged. The ported Graphiti fields become **nullable
   columns**: `author`, `source_citation`, `valid_at`, `invalid_at`, `superseded_by`, `fact_type`.
3. **`superseded_by` is a plain nullable UUID** (the explicit forward link), mirroring the existing
   `run_id` column — not a self-FK (avoids self-referential CASCADE subtlety; referential integrity here is
   not load-bearing, the temporal window is).
4. **Facts are agent-authored only** (`author='agent'`, `trust='normal'`). No agent path mints
   `trust='human-pinned'` (that stays the human pin endpoint — B2 no-fabrication carries over) and
   `record_matter_fact` touches only `kind='fact'` rows, never a `correction` (no-overwrite carries over).
5. **`source_citation` is the agent-supplied *prose* source** (e.g. `"Cirrus MSA §9"`), capped + nullable.
   The structured Citation-Engine tuple `{file_id, offsets}` is **impossible for the agent to supply
   honestly** — its document tools expose only filename + page + snippet, never `document_id`/offsets.
   A structured-ref upgrade needs Citation-Engine ids plumbed into the agent's document tools → deferred.
6. **No embeddings.** The gateway `/v1/embeddings` endpoint is **501 until B6**. A matter has tens of facts;
   they fit in a prompt whole. The C3b-2 consolidation "retrieve" step loads the small fact set whole and
   lets the model judge (no vector retrieval). FTS exists if ever needed (C3c retrieval).
7. **The read/retrieval surface (agent tools, REST, cockpit panel) is C3c.** C3b-1 ships the *store + write +
   the as-of query as tested pure helpers* (`facts_valid_at` / `live_facts` / `memory_log`). The bi-temporal
   correctness is proven by unit tests + a live write; C3c surfaces it.

## C3b-1 — typed bi-temporal fact store + guarded write + as-of query *(this slice; ZERO model calls)*

**Goal.** The matter keeps a **dated, supersede-able fact ledger** beside the prose wiki: the agent records a
durable fact (with its source + when it became true); superseding a fact sets the old one's `invalid_at` and
a forward link, never deletes — so we can answer *"what did we believe at signing"*. End to end, all areas.

### Build
1. **Migration `0070_matter_memory_typed_facts.py`** (`down_revision="0069"`) — additive-nullable columns
   `author`, `source_citation`, `fact_type`, `valid_at`, `invalid_at`, `superseded_by` on
   `matter_memory_entries`; extend the `kind` CHECK to add `'fact'`; new nullable-enum CHECKs (`author`,
   `fact_type`), a temporal CHECK (`invalid_at IS NULL OR valid_at IS NULL OR invalid_at > valid_at`), and a
   `source_citation` length CHECK. No backfill. Downgrade deletes `kind='fact'` rows then reverses.
2. **ORM** — extend `MatterMemoryEntry` (`models/project.py`): the 6 nullable columns + module enum tuples
   (`_MATTER_MEMORY_AUTHORS`, `_MATTER_FACT_TYPES`, extend `_MATTER_MEMORY_KINDS` with `'fact'`) + an
   `_opt_in_set` helper, CHECKs mirroring the migration (single source of truth, like `assessment.py`).
3. **Schema** — `RecordMatterFactInput` + `MatterFactType(StrEnum)` in `schemas/matter_memory.py`
   (`extra='forbid'`, reject-not-truncate; fields `fact`, `fact_type`, `source`, `valid_from`, `supersedes`).
4. **Tool** — `matter_fact_tools.py` (new, mirrors `matter_memory_tools.py`): own grant set
   `MATTER_FACT_TOOL_NAMES = {"record_matter_fact"}` (disjoint), `build_matter_fact_tools(...)`; the guarded
   `record_matter_fact(fact, fact_type, source=None, valid_from=None, supersedes=None)` — validate → reload
   project (owner+active) → if `supersedes`: load the live prior fact (same matter, `kind='fact'`,
   `invalid_at IS NULL`) else reject → insert the new fact (`author='agent'`, `trust='normal'`,
   `kind='fact'`) → set the prior's `invalid_at`+`superseded_by` → flush. Guard-only audit (no body leak).
   + pure read helpers `facts_valid_at(db, project_id, at)` (the as-of query `valid_at ≤ T < invalid_at`),
   `live_facts(db, project_id)`, `memory_log(db, project_id)`.
5. **Composition** — grant `build_matter_fact_tools(...)` for **every** matter-bound run (all areas),
   beside the matter-memory grant; disjoint from ROPA/assessment/commercial.
6. **Skill** — extend `skills/matter-memory/SKILL.md` with a short *fact-ledger* section (when to record a
   fact vs update the wiki; supersede a changed term with `supersedes=<id>`; attach a source). **No unquoted
   `": "` in the description** (the C3a trap; CI guard `test_every_real_skill_loads_no_silent_drops`).

### Verify (4-discipline DoD)
- `ruff format && ruff check` (CI ruff), `mypy app`, full `pytest` (dev-image recipe; counts quoted).
- **Tests:** `test_matter_fact_tools.py` — grant set + disjointness; record a fact (columns set, author/trust
  fixed); supersede (prior `invalid_at`/`superseded_by` set, new live); supersede-not-found rejected; oversize
  source / blank fact rejected (reject-not-truncate); a fact write does NOT touch a `correction`/snapshot row
  (no-overwrite carries over); `facts_valid_at` returns the right as-of view across a supersede boundary;
  `memory_log` append-only order; guard audit carries no body. + `test_agent_composition.py` — the fact tool
  is granted to a matter-bound run (Commercial **and** Privacy), grant-set disjoint.
- **Migration** up/down/up on a throwaway pgvector container; rebuild api+arq-worker+ingest-worker.
- **Live (DeepSeek):** the agent records two facts on a matter (one superseding the other via `supersedes`);
  assert `facts_valid_at(before)` vs `facts_valid_at(after)` returns the historical vs current truth.
  Evidence → `docs/fork/evidence/c3b1/`.
- Fresh-context adversarial + security + simplification pass (injection: a fact body is data; the agent
  cannot mint a pin or alter a correction; audit counts/IDs only; reject-don't-truncate + DB CHECK;
  confinement from ROPA/assessment). HANDOFF.

### C3b-1 non-goals (→ C3b-2 / C3c)
Zero gateway/model calls (the ADR-F010 egress obligation is **C3b-2**). No automated consolidation/Lint
(the agent supersedes manually via the tool). No retrieval tool / REST / cockpit panel (C3c). No structured
Citation-Engine reference (prose source only). No FTS/vector search over facts (C3c).

## C3b-2 — gateway-routed consolidation/Lint pass *(next; the egress slice)* — outline, ADR to draft

The **in-run guarded tool** `consolidate_matter_memory` (maintainer's choice): the agent calls it during a
run; it loads the matter's live fact set whole + the wiki, routes a **gateway** call (the mem0
extract→judge ADD/UPDATE/DELETE/NOOP loop + Karpathy/OpenClaw Lint for contradictions/stale/orphans) through
`GatewayClient.chat_completion` (precedent: `playbooks/easy/extractor.py`, `autonomous/guard.py`) under a
**new `lq_ai_purpose`** (register in `gateway/app/api/inference.py` `_KNOWN_PURPOSES`), then supersedes stale
facts (sets `invalid_at`/`superseded_by`) and rewrites the wiki — **pinned corrections stay immutable to the
loop**. Guarded + cost-metered via `guarded_dispatch`; **ADR-F010 no-`api.openai.com`/no-direct-provider
assertion** on the path. **Draft ADR-F043** (egress lands here + the new purpose + the model-calling tool).
Background-cron autonomy is the deferred upgrade (backlog).

## Risks / traps (carried)
- **Migration head is `0069`** → C3b-1 is `0070` (re-check before writing). Throwaway-container verify;
  rebuild the 3 workers; never host `alembic upgrade`; never `compose down -v`.
- **CHECK literals must match in 3 places** (migration DDL · ORM `_in_set`/`_opt_in_set` · Pydantic enum) —
  keep the authoritative tuple module-level and generate from it.
- **No new public endpoint in C3b-1** (read surface is C3c) → no `test_endpoints`/`test_openapi` contract
  churn (the C3a CI round-trip lesson).
- **SKILL.md frontmatter:** never an unquoted `": "` in any value.
