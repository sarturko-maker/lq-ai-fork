# Research — Native-fit reconciliation: langgraph Store / deepagents vs our custom memory & retrieval

**For:** the maintainer's load-bearing constraint on top of the prior retrieval/memory research
(`document-discovery-and-map.md`, `document-retrieval-at-scale-and-cost.md`,
`conversations-as-retrievable-knowledge-and-upstream-awareness.md`,
`retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md`, `matter-memory-reuse.md`,
`matter-memory-patterns.md`, `deepagents-ecosystem.md`). **The constraint:** *whatever we build MUST
fit langgraph + deepagents. If the framework already solves a point natively, do NOT hand-build a
parallel solution — use the native mechanism.* This document is the honest **native-vs-build map** that
re-anchors the plan.

**Method:** wheel-source introspection inside the running `lq-ai-api-1` container (deepagents **0.6.8**,
langgraph-checkpoint-postgres, langchain 1.x — pins at `api/pyproject.toml:130-152`) for every framework
API claimed; codebase re-read at the cited `file:line` for every "what we do today" claim; the prior
docs' verified verdicts carried forward and corrected where they reinvent a native primitive. **Date:**
2026-06-27. Framework APIs are cited as **installed-package path** (authoritative for *our* pin) plus the
public doc URL; our code as `file:line`.

**Posture reminders (unchanged):** external-provider LLM calls route through the in-house gateway (sole
key-holder + only egress, ADR-F010) — **local in-process compute is permitted**; `guarded_tool_call`
R4/R5/R6 brake on every agent tool call (ADR-F002); matter memory is **auto-write-then-correct**
(ADR-F042); audit carries counts/types/IDs, never raw values; new deps are SBOM surface. Upstream is
FROZEN (ADR-F001) — not in scope here.

---

## 1. Executive summary

- **The native substrate is already in our wheels and does most of what we sketched.** langgraph ships a
  `BaseStore` with **hierarchical-namespace storage + natural-language semantic search +
  metadata-filter search**, an `AsyncPostgresStore` backend (pgvector), and an `IndexConfig` whose
  `embed` field accepts **a plain callable** — so semantic-search embeddings can route through our
  gateway with zero new dependency (verified:
  `langgraph/store/base.py` `BaseStore.search(namespace_prefix, *, query, filter, limit)` +
  `IndexConfig{dims, embed, fields}`; `langgraph/store/postgres/aio.py` `AsyncPostgresStore`).

- **deepagents gives us exactly CLAUDE.md's target memory shape out of the box.**
  `create_deep_agent(..., backend=, store=, memory=, middleware=, permissions=, subagents=)` natively
  accepts a `CompositeBackend(default=StateBackend(), routes={"/memories/": StoreBackend(...)})` whose
  `StoreBackend(store=, namespace=lambda rt: (...))` maps a `/memories/{level}/` tree onto Store
  namespaces — *literally* "one CompositeBackend → `/memories/{company,practice,user,matter}/` routed to
  StoreBackend namespaces keyed `(org_id, …)`" (verified:
  `deepagents/backends/composite.py`, `deepagents/backends/store.py`, `deepagents/graph.py`
  `create_deep_agent` signature).

- **But our fork wires NONE of it today.** The composition root passes `create_deep_agent` only a
  **checkpointer** and a **read-only skills backend** — no `store=`, no `memory=`, no `CompositeBackend`,
  no `StoreBackend`, no `MemoryMiddleware`, no `SummarizationMiddleware`
  (`api/app/agents/composition.py:583-585`; `wiring.backend` is a `RegistrySkillBackend` or `None`,
  `api/app/agents/skill_backend.py:108`; grep for `AsyncPostgresStore|StoreBackend|CompositeBackend|
  IndexConfig|MemoryMiddleware|SummarizationMiddleware` across `api/app/` returns **nothing**). **We run
  deepagents with the checkpointer leg only — the Store leg of the framework is unused.**

- **Checkpointer ≠ Store, and we only have the checkpointer.** The `AsyncPostgresSaver`
  (`api/app/agents/checkpointer.py:57-104`) persists **one thread's working state** keyed by
  `thread_id` — it is within-thread durability, *not* cross-thread long-term memory and *not* content-
  searchable (library-owned, alembic-opaque tables). Cross-thread memory is the **Store's** job, and the
  Store is exactly what's missing. The four-level memory model in CLAUDE.md is currently implemented
  **not** on the native Store at all but on a **hand-built SQLAlchemy table** (`MatterMemoryEntry`,
  `api/app/models/project.py:288-368`) injected as read-only prose at the prompt seam
  (`composition.py:355-361`).

- **Headline verdict — adopt the native Store/CompositeBackend as the substrate; keep custom ONLY two
  things, both with a proven native gap.** REPLACE-WITH-NATIVE: cross-thread/long-term memory storage &
  routing, generic memory **semantic search**, within-chat compaction **and verbatim conversation
  offload/recall**, subagent fan-out (already native — we added zero scaffolding). KEEP-CUSTOM (gap
  proven below): **(a)** the **bi-temporal typed fact ledger + enforced human-pinned corrections**
  (ADR-F042/F043/F044) — the Store has *no* `valid_at/invalid_at/superseded_by` semantics, no
  as-of query, no gate-enforced "agent may not overwrite a human pin"; **(b)** the **documents hybrid
  retriever** (`api/app/knowledge/retrieval.py`) — FTS+dense **fusion** + cross-encoder rerank +
  **citation byte-offset** verification, none of which the Store's single-vector `search` provides.

- **The prior conversation plan partly reinvents a native capability and must be corrected.** The
  proposed **conversation→chunk→embed pipeline + `source_type='conversation'` index + a net-new
  `search_matter_conversations` tool** (`conversations-as-...md` §5, §7) overlaps the native Store's
  `search(namespace=("matter", id, "conversations"), query=...)` **and** the
  `SummarizationMiddleware`'s native verbatim offload to `/conversation_history/{thread_id}.md` on the
  backend (verified `deepagents/middleware/summarization.py:9,44,316-318`). The **cross-thread "search
  conversations in a matter"** need and the **within-chat recall** need are **largely subsumed by native
  primitives** — the custom pipeline as drafted is a parallel build we should not do. What remains
  genuinely custom is *narrow* (recency weighting; cite-grade conversation provenance) and may not be
  needed at all in v1.

- **This SIMPLIFIES the plan: fewer custom slices.** The prior plan's spine (Slice A wire retriever → C
  local embeddings → conversation Slices G/H/I) collapses on the conversation side: once the Store is
  wired with an `IndexConfig`, "search matter conversations" is **a thin backend tool over
  `store.asearch`**, not a chunk/embed/index subsystem. The documents side (hybrid retriever, local
  embeddings) stays — it's the part the Store does *not* cover.

- **Two real maintainer calls remain (and only two are architecturally load-bearing):** (1) adopt the
  native Store + CompositeBackend **now** as the substrate (yes — it's our own pin, it's CLAUDE.md's
  stated target, and we're currently off-substrate); (2) for conversations, **lean on the native Store
  semantic search + native summarization-offload** instead of the custom pipeline (recommended), keeping
  the fact ledger and the documents hybrid retriever as the two proven-justified custom layers. The
  remaining questions (langmem-vs-thin-extractor, recency weighting, embedding door) are secondary tuning
  calls (§8).

---

## 2. Native capabilities (langgraph 1.x + deepagents 0.6.8) — what ships, verified

All claims verified by `inspect`/source read inside `lq-ai-api-1` against our exact pins.

### 2a. The langgraph `BaseStore` — namespaces + semantic search + Postgres/pgvector backend

- **Hierarchical namespaces + two search modes in one API.** `BaseStore.search` /
  `.asearch(namespace_prefix, /, *, query: str|None, filter: dict|None, limit=10, offset=0)`
  (`langgraph/store/base.py`). **`filter`** = metadata key/value (with `$eq/$gt/...` operators) =
  structured search; **`query`** = **natural-language semantic search** ("requires a vector store
  implementation", per the docstring). One store, namespaced by tuple (e.g.
  `("matter", matter_id, "conversations")`), gives both lexical-metadata and semantic recall.

- **Semantic index is opt-in and gateway-routable.** `IndexConfig` keys are
  `{dims: int, embed: Embeddings | EmbeddingsFunc | AEmbeddingsFunc | str, fields: list[str]|None}`
  (verified annotations). **`embed` accepts a plain (async) callable** — `ensure_embeddings` wraps an
  arbitrary function into the LangChain `Embeddings` interface
  (`langgraph/store/base.py:ensure_embeddings`). **This is the gateway hook**: the embed callable can
  POST to our gateway (or call a local in-process model — ADR-F010 Door A), so the Store's semantic
  search preserves gateway-only egress *and* the local-embedding cost play simultaneously. If no
  `index` is configured, the store degrades to **filter-only** (no vector) — exactly the
  "FTS/metadata-first, dense later" degradation the prior docs want.

- **A Postgres/pgvector backend ships in our pinned wheel.** `AsyncPostgresStore`
  (`langgraph/store/postgres/aio.py`) has `from_conn_string` + `setup()` and stores into a single
  `store` table with optional pgvector index — **same Postgres we already operate, zero new
  infra/dep**. (Per the deepagents-ecosystem doc §2 row 1, this is an **ADOPT** with zero new SBOM
  entries — it rides `langgraph-checkpoint-postgres`, already pinned `>=3.0,<4`,
  `api/pyproject.toml:152`.)

### 2b. Checkpointer vs Store — different jobs (we conflate them at our peril)

| | **Checkpointer** (`AsyncPostgresSaver`) | **Store** (`AsyncPostgresStore` / `BaseStore`) |
|---|---|---|
| Scope | **One thread** (keyed `thread_id`) | **Cross-thread**, namespaced (`(org, level, …)`) |
| Holds | Working state: messages, todos, workspace files for the *current* conversation | Long-term memory: durable facts/notes/files across all conversations |
| Query | `aget_tuple(thread_config)` — by thread only | `search(namespace, query=, filter=)` — by content/metadata/semantic |
| Lifecycle | Replayed on resume; grows per step; library-owned tables | Curated; survives thread deletion; one `store` table |
| Our status | **WIRED** (`checkpointer.py`) | **NOT WIRED** (absent everywhere) |

The checkpointer is **within-thread durability** (ADR-F008, F1-S1). The Store is **the memory tier**.
They are orthogonal and both pass to `create_deep_agent` (`checkpointer=`, `store=`). We have the first
and not the second.

### 2c. deepagents `CompositeBackend` / `StoreBackend` — CLAUDE.md's target, verbatim

- `create_deep_agent(model, tools, system_prompt, *, middleware=(), subagents=None, skills=None,
  memory=None, permissions=None, backend=None, interrupt_on=None, store=None, checkpointer=None, …)`
  (verified signature, `deepagents/graph.py`). It natively threads a **backend**, a **store**, **memory
  sources**, **permissions**, and **subagents**.
- `CompositeBackend(default, routes, *, artifacts_root="/")` — **longest-prefix path routing**;
  docstring example is literally `routes={"/memories/": StoreBackend(), "/cache/": StoreBackend()}`
  (`deepagents/backends/composite.py`). ls/glob/grep remap prefixes (the prior prefix bugs are fixed at
  ≥0.6.8 per deepagents-ecosystem §2 row 2).
- `StoreBackend(runtime=None, *, store: BaseStore|None, namespace: Callable[[Runtime], tuple]|None,
  file_format="v2")` — files live in the Store under a **per-run-computed namespace**
  (`deepagents/backends/store.py`). New-style `namespace=lambda rt: (...)` factory is the forward-
  compatible form (old ctx-style removed in 0.7 — deepagents-ecosystem §1.1).
- **This is exactly CLAUDE.md's "one deepagents `CompositeBackend` — `/memories/{company,practice,user,
  matter}/` routed to StoreBackend namespaces keyed `(org_id, …)`".** The framework provides the whole
  shape; we have not instantiated it.

### 2d. Subagents / `task` fan-out — already native, already adopted

deepagents' `task` tool spawns subagents declared as plain dicts (`subagents=[{...}]`); fan-out is
**model-driven**, not Python-orchestrated. Our fork already uses this end-to-end (C7b roster:
"deepagents-native + model-driven — added ZERO orchestration scaffolding"; the ADR-F010 gate in
`build_deep_agent` is the *only* wrapper, `factory.py:126-152`). **No build here; it's done and native.**
Caveat (deepagents-ecosystem §3 #12): subagent `permissions` **REPLACE** the parent's — must be
re-declared per subagent (matters for the read-only company/practice memory routes, §5).

### 2e. Within-chat context management — native compaction **and** verbatim offload/recall

- `SummarizationMiddleware(*, backend, trigger=("fraction",0.85), keep=…, …)` summarizes the working
  window **and offloads the evicted verbatim history to the backend at
  `/conversation_history/{thread_id}.md`** (verified `deepagents/middleware/summarization.py:9,44,
  316-318`). If that backend route points at a `StoreBackend`, the **full verbatim within-thread
  transcript becomes a persistent, retrievable artifact for free** — the prior doc's "need 3b: recall
  within a chat" substrate, native.
- `SummarizationToolMiddleware` adds an on-demand `compact_conversation` tool. Defaults fall back to a
  **170k-token** trigger for unprofiled models — our `factory.py` already sets
  `profile["max_input_tokens"]` to fix exactly this (`factory.py:33,109-111`).
- `MemoryMiddleware(*, backend, sources=[...])` injects always-loaded AGENTS.md-style files into the
  system prompt wrapped in `<agent_memory>` **with built-in untrusted-data guidelines** (verified
  docstring — aligns with our prompt-injection rule). This is the native way to do "always-inject the
  level digests."

### 2f. langmem — the optional extraction/consolidation layer (rejected as a dep)

langmem (0.0.30) offers `create_memory_store_manager` / extraction prompts over a Store. The
deepagents-ecosystem doc §4 **REJECTED it as a dependency** (7.5 months stale, pre-1.0, drags
langchain-anthropic/openai/trustcall into the SBOM, no approval seam, Platform-only durable executor) —
**mine its prompts only**. Consolidation/extraction is **BUILD-thin on our arq job** (deepagents-
ecosystem §2 rows 5-6), which we already do for the matter wiki (ADR-F043).

---

## 3. What our fork uses today — the gap between the target and reality

**The CLAUDE.md target memory model is not implemented on the native substrate at all.** Verified state:

- **No Store, anywhere.** `create_deep_agent` is called with `backend=wiring.backend` and
  `checkpointer=checkpointer` and **nothing else memory-related** (`composition.py:583-585`).
  `wiring.backend` is a `RegistrySkillBackend` (read-only skills library, `skill_backend.py:108-165`) or
  `None` (`composition.py:557`). Grep across `api/app/` for `AsyncPostgresStore`, `InMemoryStore`,
  `IndexConfig`, `BaseStore`, `StoreBackend`, `CompositeBackend`, `MemoryMiddleware`,
  `SummarizationMiddleware`, `.asearch(` → **zero non-test hits**. We run deepagents with the
  **checkpointer leg only**.

- **The four memory levels are hand-built and prompt-injected, not Store-routed.** All four CLAUDE.md
  tiers are assembled as **read-only prose blocks concatenated into the system prompt** at composition
  time:
  - **Company/client** — `organization_profile` / client `context_md` injected read-only
    (`composition.py:142,257-276,305-326`).
  - **Practice area** — area `profile_md` injected read-only (composition seam, ADR-F030).
  - **User** — `autonomous_memory` (still write-only; CLAUDE.md blocker #7).
  - **Matter (unit of work)** — `projects.context_md` (the wiki) + `load_pinned_corrections` +
    authorship roster, all injected read-only (`composition.py:355-361,380-391`).
  None of these is a `/memories/{level}/` Store route; none is searchable by the agent via the native
  Store API; the digests are static-injected, not `MemoryMiddleware`-sourced.

- **The matter-memory tables ARE a hand-built store alternative.** `MatterMemoryEntry`
  (`api/app/models/project.py:288-368`) is a bespoke SQLAlchemy table doing what a `StoreBackend` would
  do for the matter tier — *plus* things the Store can't (bi-temporal columns). The agent read tools
  `search_matter_memory` / `matter_facts_as_of` (`matter_read_tools.py`) query **this SQL table
  directly** (`select(Project)...`, `select(MatterMemoryEntry)...`), **not** `store.asearch`. The write
  tools `update_matter_memory` / `record_matter_fact` (`matter_memory_tools.py:79`,
  `matter_fact_tools.py:75`) write SQL rows. So the matter tier is a **fully parallel, hand-rolled
  store** — part of which is justified (bi-temporal/pins, §4f) and part of which (plain durable text +
  search) the native Store would subsume.

- **Conversation is not retrievable at all on the agent path.** Per `conversations-as-...md` §2b: the
  agent path persists conversation only in `AgentRunStep` summaries (audit digests) and the opaque
  checkpointer; **no FTS, no embeddings, no cross-thread search**; `search_matter_conversations` **does
  not exist in code** (grep confirmed). The native verbatim-offload substrate (§2e) is **unused** because
  no `SummarizationMiddleware` + Store is wired.

**Net:** we are **off the native substrate**. CLAUDE.md describes the destination; the code has the
checkpointer and a pile of prompt-injected prose + one bespoke SQL table. The first move is to **get on
the substrate** (wire the Store + CompositeBackend), *then* decide what stays custom on top.

---

## 4. Component-by-component: native vs build

Verdict legend: **KEEP NATIVE** (use the framework as-is) · **REPLACE-WITH-NATIVE** (we are/would be
reinventing — switch to native) · **HYBRID** (native substrate + a thin custom layer) · **KEEP CUSTOM**
(prove the native gap).

| # | Component | Native primitive | Our status today | Native gap? | **Verdict** |
|---|---|---|---|---|---|
| a | Cross-thread / long-term memory **store + routing** | `AsyncPostgresStore` + `CompositeBackend`/`StoreBackend`; `create_deep_agent(store=, backend=)` | **Absent** — checkpointer only; tiers prompt-injected | None — it's CLAUDE.md's exact target, in our wheel | **REPLACE-WITH-NATIVE** (adopt it; we have no store at all) |
| b | "Search **conversations** in a matter" (cross-thread) | `store.asearch(("matter",id,"conversations"), query=…)` + `SummarizationMiddleware` verbatim offload to the backend | **Absent**; prior doc proposes a custom chunk→embed→`search_matter_conversations` pipeline | Largely **none** — semantic + namespaced search is native; offload is native | **REPLACE-WITH-NATIVE** (drop the custom pipeline; thin tool over `store.asearch`) — **HYBRID** only for the narrow extras (§4h) |
| c | Within-chat context mgmt (compaction + recall of older turns) | `SummarizationMiddleware` (+`ToolMiddleware`) with verbatim offload | **Absent** (no summarization middleware wired) | None for the common case | **KEEP NATIVE** (wire it; profile already set in `factory.py`) |
| d | Subagent **fan-out** | deepagents `task` tool + `subagents=[...]` | **Done & native** (C7b roster; ADR-F010 gate only) | None | **KEEP NATIVE** (already adopted; re-declare subagent permissions) |
| e | The **documents MAP** (L1 router store) | `store.search`/`filter` over a `("matter",id,"map")` namespace | Proposed to live in the fact ledger (`fact_type="document"`) | None for *storage*; the *routing heuristic* is ours | **HYBRID** (store the map in the native Store; the router logic/prompt is thin custom) |
| f | **Bi-temporal typed fact ledger + human-pinned corrections** | `store.put/search` (flat KV + metadata + optional vector) | **Custom SQL** (`MatterMemoryEntry`, ADR-F042/43/44) — live, shipped | **YES (proven)** — no `valid_at/invalid_at/superseded_by`, no as-of query, no gate-enforced pin-immutability, no append-only supersede ledger | **KEEP CUSTOM** (native gap proven below) |
| g | **Documents hybrid retriever** (FTS+dense **fusion**+rerank+**citation offsets**) | `store.search(query=)` = single-vector ANN over stored items | **Custom, shipped** (`knowledge/retrieval.py`, ADR-0008) — not yet wired to matters | **YES (proven)** — Store search is single-vector; no FTS+dense fusion, no cross-encoder rerank, no normalized-byte-offset citation contract | **KEEP CUSTOM** (for documents where cite-grade/hybrid/rerank is required) |
| h | **Recency weighting** for conversation candidates | none (Store search has no temporal decay term) | Proposed (β blend) | Yes, but trivial | **HYBRID** (a few lines on top of native search results) — *or defer until measured* |

### Reasoning for the non-obvious verdicts

**(a) REPLACE-WITH-NATIVE — cross-thread store.** We have no store at all; the framework's is our own
pin and is CLAUDE.md's stated destination. There is **no justification to hand-build storage/routing** —
the deepagents-ecosystem doc already adjudicated this (§2 rows 1-2: ADOPT, zero new deps; "drop any
'build storage/routing/compaction' work"). Anything we'd write here is a parallel re-implementation of
`StoreBackend`/`CompositeBackend`.

**(b) REPLACE-WITH-NATIVE — conversation search.** This is the sharpest correction. The prior doc's
custom plan (a `source_type='conversation'` column on a chunk table, a conversation→chunk→embed worker
firing on run completion, and a net-new `search_matter_conversations` tool fused into the documents
retriever) **rebuilds, by hand, what `store.asearch(namespace, query=...)` does natively** — namespaced,
semantic, matter-scoped recall. And the **raw verbatim transcript** the prior doc wants to "never delete
and retrieve on demand" is **already produced natively** by `SummarizationMiddleware`'s offload to
`/conversation_history/{thread_id}.md` on the backend (§2e) — if that backend is a `StoreBackend`, the
transcript is persistent and retrievable with no custom embed/index pipeline. **The native gap is
narrow:** (i) recency-decay weighting (§4h — a few lines, deferrable); (ii) "cite-grade" conversation
provenance (the Store returns the item + namespace + metadata, which is *already* enough for
"thread #4, your answer on 2026-05-02" — the prior doc itself says conversation is provenance-cited, not
byte-offset-cited). So the custom pipeline is **not justified**; a thin matter-tool that calls
`store.asearch` is. (See §6 for the explicit correction.)

**(f) KEEP CUSTOM — fact ledger + pins (gap proven).** The native Store is a namespaced KV with metadata
filters and an optional single vector. It has **no concept of**: world-time validity (`valid_at`),
invalidation without deletion (`invalid_at`), a forward supersede link (`superseded_by`), an **as-of**
query ("what did we believe at signing" — `matter_facts_as_of`), or a **gate-enforced** rule that the
agent may not overwrite/supersede a `trust='human-pinned'` row (ADR-F042 B2). You *could* shove these
into Store-item metadata, but you'd then **re-implement the bi-temporal query logic, the supersede
ledger, and the pin-immutability gate in application code anyway** — i.e. the custom layer survives;
only its physical table moves. The current SQL table also gives us CHECK constraints
(`chk_matter_memory_entries_valid_window: invalid_at > valid_at`), a real FK CASCADE confining blast
radius to one matter, and the audit/undo snapshots (ADR-F044) — guarantees the Store doesn't offer.
**Verdict: keep the typed bi-temporal ledger + pins as a thin custom tier the agent reads; do NOT try to
emulate it in Store metadata.** (matter-memory-reuse.md already proved no surveyed system ships the
enforced-pin primitive — this is genuinely ours.)

**(g) KEEP CUSTOM — documents hybrid retriever (gap proven).** `store.search(query=)` is single-vector
ANN. Our shipped retriever does **min-max-fused FTS + dense + 4× overshoot**
(`knowledge/retrieval.py:71-180`) and the plan adds a **local cross-encoder rerank** and preserves the
**Citation Engine's normalized-content byte-offset** contract (the legal must-have: a quote verifiable to
an exact span). The Store has none of FTS-fusion, rerank, or offset-citation. For **documents**, where
recall-at-scale and cite-grade verification matter (the whole point of the scale doc), the custom
retriever exceeds the Store. **Verdict: keep it — but use it ONLY for documents** (and only where
hybrid/rerank/offset is actually required); do not build a second retriever for conversations when the
Store covers them (§4b).

**(e/h) HYBRID.** The documents MAP and recency weighting are **thin logic on top of native storage** —
store the map *in* the Store; compute recency decay *over* Store results. Neither warrants a bespoke
subsystem.

---

## 5. The reconciled architecture — sitting on native primitives

The picture, redrawn so it **rides the framework** instead of paralleling it. (L1/L2/L3 = the retrieval
layers from the prior docs; the memory tiers = CLAUDE.md's four levels.)

```
create_deep_agent(
    model        = gateway ChatOpenAI (factory.py — unchanged),
    checkpointer = AsyncPostgresSaver        # within-thread durability (HAVE)
    store        = AsyncPostgresStore(index=IndexConfig(             # NEW substrate
                       dims=…, embed=<gateway-or-local callable>))   #   semantic search, gateway-routed
    backend      = CompositeBackend(                                  # NEW substrate
        default = StateBackend(),             # ephemeral working files
        routes  = {
          "/skills/":               RegistrySkillBackend(...),       # HAVE (read-only skills)
          "/memories/company/":     StoreBackend(store, ns=…),       # read-only to agent (permissions+wrapper)
          "/memories/practice/":    StoreBackend(store, ns=…),       # read-only to agent
          "/memories/user/":        StoreBackend(store, ns=…),       # agent-writable (D4 propose/own)
          "/memories/matter/":      StoreBackend(store, ns=…),       # agent-writable (ADR-F042 auto-write)
          "/conversation_history/": StoreBackend(store, ns=…),       # SummarizationMiddleware offload sink
        }),
    memory       = ["/memories/company/AGENTS.md", …],   # MemoryMiddleware always-inject digests (native)
    middleware   = [SummarizationMiddleware(backend=…, …)],          # native compaction + verbatim offload
    permissions  = FilesystemPermission(deny write on /memories/{company,practice}/**),  # native read-only
    subagents    = [...],   # native task fan-out (HAVE); re-declare permissions per subagent
    tools        = [
        # documents (L2) — CUSTOM hybrid retriever, matter-scoped:
        search_documents, read_document, get_document_metadata,     # → knowledge/retrieval.py hybrid_search
        # conversations — NATIVE store search behind a thin tool:
        search_matter_conversations,                                # → store.asearch(("matter",id,"conversations"|"history"), query=…)
        # bi-temporal facts/corrections — CUSTOM thin tier (proven gap):
        search_matter_memory, matter_facts_as_of,                   # → MatterMemoryEntry (ADR-F042/43/44)
        record_matter_fact, update_matter_memory, consolidate_matter_memory,
        # roster (HAVE), redline/etc (HAVE) …
    ])
```

**How each need is met, and by whom:**

- **Cross-thread long-term memory (4 levels)** → **native Store + CompositeBackend** (§4a). The four
  `/memories/{level}/` routes replace today's ad-hoc prompt concatenation. Company/practice are
  **read-only to the agent** via native `FilesystemPermission(mode='deny')` **plus** the ~30-line
  storage-level read-only `BackendProtocol` wrapper (deepagents-ecosystem §2 row 4 — permissions are
  tool-level and a custom tool holding a store handle bypasses them; the wrapper is the backstop). Pins
  remain **authenticated human actions**, never agent tools.

- **Always-inject the level digests** → **native `MemoryMiddleware`** sourcing one digest file per tier
  (with its built-in untrusted-data guard). Replaces the manual system-prompt assembly in
  `composition.py:305-391`.

- **Generic conversation recall (cross-thread "search this deal's conversations" + within-chat older
  turns)** → **native Store semantic search** over a `("matter", id, "conversations")` namespace, fed by
  the **native `SummarizationMiddleware` verbatim offload**. The agent tool is a **thin wrapper over
  `store.asearch`** — no custom chunk/embed/index pipeline. Within-chat (need 3b) is the **same tool with
  a thread filter**, or just relying on compaction first (§6).

- **Documents (L2)** → **CUSTOM hybrid retriever**, *only* here, because cite-grade + FTS-fusion + rerank
  exceed the Store (§4g). L1 documents MAP stored **in** the native Store (§4e). This is the only place
  the custom retriever runs.

- **Typed facts & pinned corrections** → **CUSTOM thin bi-temporal tier** (`MatterMemoryEntry`), read by
  the agent, justified by the as-of/supersede/pin-immutability guarantees the Store lacks (§4f). It is
  the **authoritative "current truth"** layer; the Store's conversation transcript is the
  **forensic "what was said"** layer; documents are the **source corpus**. Three complementary layers,
  each on the right substrate.

**Why this fits deepagents rather than fighting it:** memory is a *backend route* (the framework's model),
not a side-channel; compaction/offload is *middleware* (native); fan-out is the *task tool* (native);
the only custom tools are the ones backed by capabilities the framework genuinely lacks (hybrid doc
retrieval, bi-temporal facts). The agent's select-then-read loop composes over all of it uniformly.

---

## 6. What this CHANGES vs the prior research

**Corrected (was reinventing a native capability):**

1. **DROP the custom conversation→chunk→embed pipeline and the `source_type='conversation'` chunk-table
   delta** (`conversations-as-...md` §5a, §5f "net-new", §7 Slices G/H). The native
   `store.asearch(namespace, query=...)` provides namespaced semantic conversation recall, and
   `SummarizationMiddleware` already offloads the verbatim transcript to the backend (§2e). **Replace
   with:** wire the Store + a `SummarizationMiddleware` whose offload route is a `StoreBackend`, and add a
   **thin `search_matter_conversations` tool that calls `store.asearch`**. This removes an embed-worker
   trigger, a migration, and a fused-retriever code path from the plan.

2. **DON'T fuse conversations into the documents hybrid retriever** (`conversations-as-...md` §5b
   "one retriever, two source types"). Documents and conversations now live on **different substrates by
   design**: documents on the custom hybrid retriever (they need cite-grade/FTS-fusion/rerank),
   conversations on the native Store (they don't — provenance-cite is enough). The "one unified corpus"
   framing is replaced by "**right substrate per source type**." This is simpler, not more complex: no
   `source_type` discriminator, no UNION, no relaxed-citation-invariant special-casing inside the
   document retriever.

3. **Within-chat recall (need 3b) is native-first.** `conversations-as-...md` §5c already leaned this way
   ("rely on deepagents compaction first"); now make it explicit — compaction **plus the verbatim
   offload artifact** is the substrate, and the within-chat retrieval leg is just the conversation tool
   with a thread filter, built only if measured. No within-chat summariser to build (native owns it).

4. **The four-level memory model moves onto the native Store + CompositeBackend + MemoryMiddleware**,
   replacing the current hand-assembled prompt-injection in `composition.py`. CLAUDE.md *names* this
   target; the prior memory docs (matter-memory-reuse/patterns) designed the *matter tier's semantics*
   but did not re-anchor *storage/routing/injection* onto the native backend — this doc does.

**Kept (still justified — native gap proven):**

5. **The bi-temporal typed fact ledger + enforced human-pinned corrections** (ADR-F042/F043/F044,
   matter-memory-reuse.md "what we build ourselves"). §4f proves the Store can't express as-of /
   supersede / pin-immutability without re-implementing all of it in app code. Keep as a thin custom tier
   the agent reads. The mem0-style consolidation loop stays a **gateway-routed arq job** (no langmem dep).

6. **The documents hybrid retriever + local-embedding cost play + documents MAP**
   (`document-retrieval-at-scale-and-cost.md`, `document-discovery-and-map.md`). §4g proves the Store's
   single-vector search doesn't cover FTS-fusion + rerank + citation-offsets. Keep — for documents only.
   Slice A (wire the matter doc tools to `hybrid_search`) and Slice C (local embeddings) survive intact.
   **Note a reuse synergy:** the local-embedding callable built for the documents retriever (Slice C) is
   *also* the natural `IndexConfig.embed` callable for the Store's conversation index — **one local
   embedder serves both**, exactly the cost play, now spanning native + custom.

7. **Recency weighting** survives as an optional thin post-filter on Store results (§4h), but is
   **deferred until a real stale-turn failure is observed** (it's a heuristic; don't pre-build).

8. **The retrieval-strategy doc's read-vs-retrieve-vs-fan-out routing** is unaffected and reinforced: the
   agent picks documents-retriever vs Store-conversation-search vs fact-ledger-read by intent — which is
   the same model-driven tool selection that doc argues for. Fan-out stays native (§4d).

---

## 7. Revised decomposition — substrate first, then only the justified custom layers

Re-anchored so we **get on the native substrate before layering anything**. Next fork ADR number is
**F049**. Dependency order; cheap-wins flagged; where it simplifies the prior plan is called out.

### Phase 0 — get on the native substrate (do FIRST; unblocks everything)

- **Slice N0 — wire the langgraph `Store` + `CompositeBackend`** [**ADR-F049**, the substrate decision].
  Instantiate `AsyncPostgresStore` in the lifespan (mirror the checkpointer's DI seam,
  `checkpointer.py:57-104`), pass `store=` + a `CompositeBackend` with the `/memories/{level}/` routes to
  `create_deep_agent` (`composition.py:583`). Add the **namespace-distinctness assertion** + the
  **read-only `BackendProtocol` wrapper** for company/practice (deepagents-ecosystem §2 row 4, §3 #11).
  Key namespaces via `rt.context` (NOT `rt.server_info`, which is `None` self-hosted — deepagents-
  ecosystem §2 correction). **No semantic index yet** (filter-only) — degrades gracefully. *This is the
  foundational migration-light slice; everything else rides it.* **ADR-F049 required** (crosses module
  boundaries; diverges from the current prompt-injection approach; hard to reverse).

- **Slice N1 — move the always-inject digests to `MemoryMiddleware`** [rides N0; ADR-F049 addendum].
  Replace the hand-assembled prompt blocks (`composition.py:305-391`) with `MemoryMiddleware(sources=[…])`
  per tier. Cheap; reduces bespoke prompt-assembly code (simplification). Keep the matter wiki/pins/roster
  injection semantics identical (regression-test the prompt).

### Phase 1 — conversations on the native Store (replaces the prior custom pipeline)

- **Slice N2 — `SummarizationMiddleware` with a `StoreBackend` offload route** [rides N0; cheap win].
  Wire native compaction (profile already set, `factory.py:111`) and point the verbatim offload at
  `/conversation_history/` → `StoreBackend`. This *alone* gives persistent, retrievable within-thread
  transcripts (need 3b substrate) **with no custom code**. *Replaces prior Slices G/H/I storage work.*

- **Slice N3 — `search_matter_conversations` thin tool over `store.asearch`** [rides N0/N2; cheap win].
  A matter-scoped tool that calls `store.asearch(("matter", id, "conversations"|"history"), query=…)`,
  guarded by `guarded_tool_call`, 404-conflating cross-matter access. **No chunk/embed/index pipeline.**
  Works filter/lexical-first; gains semantic recall the moment N4 lands. *This is the corrected, far
  smaller replacement for the prior Slice G + the net-new `search_matter_conversations`.*

### Phase 2 — the cost play (shared local embedder; documents + conversations)

- **Slice C (carried forward, EXTENDED) — local embedding callable** [ADR-F049 addendum]. Build the
  in-process local embedder (ADR-F010 Door A) for the **documents** hybrid retriever, **and** reuse the
  **same callable** as the Store's `IndexConfig.embed` so conversation semantic search lights up too —
  **one model, one door, both substrates, $0 per token**. (Confirms `conversations-as-...md` Q6: same
  door.)

- **Slice A (carried forward) — wire matter document tools to the CUSTOM `hybrid_search`** [cheap win,
  independent of N0]. Point `_search` (`api/app/agents/tools.py`) at a matter-scoped `hybrid_search`;
  degrades to FTS until vectors exist. Unchanged from the scale doc — documents stay on the custom
  retriever.

### Phase 3 — later / only if measured

- **Slice D — local cross-encoder rerank** over the custom documents retriever's fused set (precision,
  not recall; documents only). Carried forward.
- **Recency weighting** on Store conversation results — thin post-filter, **only if** a stale-turn
  failure is observed (§4h / §6.7).
- **Documents MAP in the Store** (`fact_type="document"` → a `("matter",id,"map")` namespace) — the L1
  router; carried forward, now stored natively.

**Dependency order:** **N0 (ADR-F049) → N1, N2 → N3** | **C (local embedder) → [Store semantic + documents
dense]** | **A** independent (documents) | **D / recency / MAP** gated on measured need.

**Where this simplifies the prior plan (fewer custom slices):** the prior conversation plan was 4-5
net-new pieces (chunk-store delta + embed trigger + fused-retriever source-type + tool + recency). It
collapses to **N2 (native middleware) + N3 (thin tool) + a shared embedder callable** — **roughly two
small slices instead of a subsystem**, because the Store and SummarizationMiddleware do the heavy
lifting. The documents side is unchanged (the custom retriever is genuinely needed there).

**ADRs:** **F049** = "adopt the langgraph Store + deepagents CompositeBackend as the memory substrate;
conversations via native Store search + summarization-offload; documents via the custom hybrid retriever;
bi-temporal facts/pins remain custom" (one decision, several consequences). The existing ADR-F042/F043/F044
(matter fact ledger) and ADR-0008 (hybrid retriever) are **referenced, not superseded** — F049 places them
inside the native picture.

---

## 8. Open questions for the maintainer

1. **Adopt the native Store + CompositeBackend NOW (Slice N0)?** It's our own pin (zero new deps), it's
   CLAUDE.md's stated target, and we are currently **off-substrate** (checkpointer only; tiers
   prompt-injected; matter tier on a bespoke SQL table). **Recommendation: yes — make N0 + ADR-F049 the
   next memory slice; everything else rides it.** Any objection to moving the four tiers onto
   `/memories/{level}/` routes and retiring the hand-assembled prompt concatenation?

2. **Conversations: native Store semantic search + summarization-offload INSTEAD of the custom
   conversation→chunk→embed pipeline?** §6.1/§6.2 show the prior pipeline reinvents `store.asearch` and
   the native verbatim offload. **Recommendation: drop the custom pipeline; ship N2 (native middleware) +
   N3 (thin `search_matter_conversations` over `store.asearch`).** OK to **not** build the
   conversation-chunk index / fused source-type, and rely on the native primitives?

3. **Keep the bi-temporal fact ledger + pinned corrections as custom — confirm the native gap justifies
   it?** §4f: the Store has no `valid_at/invalid_at/superseded_by`, no as-of query, no gate-enforced
   pin-immutability — emulating them in Store metadata re-implements the whole layer in app code anyway.
   **Recommendation: keep `MatterMemoryEntry` as a thin custom tier the agent reads** (ADR-F042/43/44
   intact). Confirm we are **not** dissolving it into the Store?

4. **Keep the documents hybrid retriever as custom — confirm the native gap justifies it?** §4g: Store
   search is single-vector; no FTS-fusion, no rerank, no citation byte-offsets. **Recommendation: keep
   `knowledge/retrieval.py` for documents only** (Slices A/C/D unchanged), and explicitly **do not** route
   documents through the Store. Agreed?

5. **`IndexConfig.embed` = one shared local callable for BOTH the Store (conversations) and the documents
   retriever?** §6.6/Slice C: one local in-process embedder (Door A) serves the Store's semantic index and
   the documents pgvector column — one model, one door, $0/token, gateway-honest.
   **Recommendation: yes, one embedder.** Confirm conversations ride the documents embedder's door (no
   separate decision)?

6. **langmem, or roll our own thin extractor/consolidator?** The Store is native, but *what to extract /
   when to consolidate* is not. deepagents-ecosystem §4 rejected langmem as a dependency (stale, pre-1.0,
   SBOM bloat, no approval seam, Platform-only durable executor). **Recommendation: keep the gateway-routed
   arq consolidation we already run (ADR-F043), mining langmem's MIT prompts as IP — no langmem dep.**
   Confirm "roll our own thin layer, no langmem"?

7. **Read-only company/practice enforcement: native `FilesystemPermission(deny)` ALONE, or also the
   ~30-line storage-level wrapper?** deepagents-ecosystem §2 row 4 / §3 #11-12: permissions are tool-level
   and **subagent permissions REPLACE the parent's** — a custom tool or a subagent with replaced perms can
   bypass them. **Recommendation: both — native deny + the storage-level read-only `BackendProtocol`
   wrapper as the backstop, plus the namespace-distinctness assertion.** Accept the small wrapper?

8. **Recency weighting on conversation results — build now or defer?** §4h/§6.7: a few lines of temporal
   decay over `store.asearch` results, the main guard against surfacing a *superseded* turn — but the
   bi-temporal ledger already answers "current truth," so raw turns are forensic. **Recommendation: defer
   until a real stale-turn recall failure is observed; don't pre-build a tuned β.** Accept measure-first?

---

### Honest limits of this dossier

- **Native APIs verified at OUR pins, by introspection** (deepagents 0.6.8, langgraph-checkpoint-postgres,
  langchain 1.x, inside `lq-ai-api-1`, 2026-06-27). deepagents ships breaking changes on minors
  (`factory.py:1-8`) — re-verify `CompositeBackend`/`StoreBackend`/`IndexConfig` signatures at the slice
  boundary, especially the 0.7 namespace-factory removal flagged in deepagents-ecosystem §1.1.
- **"We wire none of it" is a grep + read-through claim**, not a runtime trace: no `Store`/`StoreBackend`/
  `CompositeBackend`/`MemoryMiddleware`/`SummarizationMiddleware` in `api/app/` (non-test), and
  `create_deep_agent` is called with only `backend=wiring.backend` + `checkpointer=`
  (`composition.py:583-585`). If a later slice wired one without my seeing it, re-confirm.
- **The native conversation-recall claim rests on the Store having a semantic index.** Without an
  `IndexConfig`, `store.search(query=)` degrades to filter-only — fine for "search by metadata," weaker
  for paraphrase recall until Slice C's embedder lands. The *substrate* is native either way; the
  *quality* of conversation recall scales with the shared embedder. This is the same FTS→dense
  degradation the documents plan already accepts.
- **The fact-ledger / hybrid-retriever "native gaps" are argued from API shape, not from a failed
  experiment.** They are strong (the Store demonstrably lacks bi-temporal columns, as-of queries, FTS-
  fusion, rerank, and offset-citations), but if the maintainer wants belt-and-braces, a one-afternoon
  spike storing a fact in Store metadata + trying an as-of reconstruction would make the
  "can't express it natively" claim concrete.
- **No measured memory/retrieval failure on our own data.** The reconciliation is reasoned from substrate
  shape + verified framework capability + the prior docs' web consensus — not from incident data. The
  thin custom layers (facts, documents retriever) are already shipped and tested; the native substrate
  slices (N0-N3) should land with a small behavioral regression check (prompt-equivalence after the
  MemoryMiddleware switch; a "search this matter's conversations" spot-check).
