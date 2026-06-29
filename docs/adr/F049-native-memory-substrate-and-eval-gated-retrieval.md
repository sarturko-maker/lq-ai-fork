# F049 — Native memory substrate (langgraph Store + deepagents CompositeBackend) + custom retrieval layer, eval-gated

- Status: accepted (with F2 slice **N0**, 2026-06-28 — the native Store + CompositeBackend substrate);
  addenda: **N1** (2026-06-28, read-only tier middleware), **N2** (2026-06-29, conversation offload),
  **N3** (2026-06-29, cross-thread conversation-recall tool), **Slice A** (2026-06-29, matter document
  tool wired to one hybrid retriever), **Slice C2** (2026-06-29, Store `IndexConfig` semantic recall),
  **Slice C1** (2026-06-29, local embedder + matter-document hybrid
  retrieval — see the addenda at the end)
- Date: 2026-06-27
- Deciders: maintainer (Arturs), agent
- Milestone: **F2 — Memory: 4 levels + conversation memory** (ADR-F003). This ADR is the
  architecture decision produced by a seven-document retrieval/memory research arc
  (`docs/fork/research/` — see the index `RETRIEVAL-MEMORY-INDEX.md`). It governs *how* F2 is
  built and how document- and conversation-retrieval at scale are added.

## Context

The fork must let a practice-area Deep Agent **find the right material** in a matter — across
**many documents** (a long deal can carry hundreds to ~1000 files) **and** across **conversation
history** (decisions live in past threads, not only in `.docx` files) — and **pick** the right
item without confusion, cheaply. Today the matter agent has only: an un-annotated inventory
(`filename (N pages)`), a top-8 **lexical FTS** search (`api/app/agents/tools.py:70-83`), and a
40k-char `read_document`. That is adequate for one small upload and **fails at scale**: lexical FTS
silently misses paraphrase (*"audit rights"* ≠ *"permit inspection on 30 days' notice"*), there are
no per-document descriptions, no cross-turn "active document," and **no conversation search at all**
on the agent path.

The research arc established, with claims verified against our pinned packages and our code at
`file:line` (and the load-bearing ones re-verified directly this session — see the index):

1. **We are off the native substrate.** `create_deep_agent` is called with only a `checkpointer` +
   a read-only skills `backend` (`api/app/agents/composition.py:583-585`); there is **no langgraph
   `Store`, no `CompositeBackend`/`StoreBackend`, no `MemoryMiddleware`/`SummarizationMiddleware`**
   anywhere (grep is empty). The CLAUDE.md four-level memory model is implemented as **hand-assembled
   prompt-injected prose + one bespoke SQL table** (`MatterMemoryEntry`), not on the framework's
   memory tier.
2. **The native substrate already ships in our wheels and is exactly CLAUDE.md's target**
   (verified by introspection, deepagents 0.6.8 / langgraph 1.x): `BaseStore.asearch(namespace, *,
   query, filter, limit)` with semantic search; `IndexConfig{dims, embed, fields}` whose `embed`
   is a **plain callable** (our gateway/local embedder plugs in); `AsyncPostgresStore` (pgvector);
   `create_deep_agent(... store=, backend=, memory=, middleware=, subagents= ...)`;
   `CompositeBackend(routes={"/memories/…": StoreBackend(...)})`; `SummarizationMiddleware`
   (compaction + verbatim offload to `/conversation_history/{thread_id}.md`).
3. **The framework does NOT solve retrieval-at-scale.** `store.search(query=)` is single-vector
   ANN over stored items. It does **not** provide chunking, the embedding *pipeline* at scale
   (batching/backfill/the model behind the hook), **hybrid FTS+dense fusion**, **reranking**, or
   **citation byte-offsets**. The OSS deepagents ecosystem confirms this: no public project does
   cite-grade legal retrieval at scale; the richest reference (Milvus+deepagents) mounts the native
   `StoreBackend` and stops there.
4. **Two custom layers exceed the native Store and are justified:** (a) the **bi-temporal typed
   fact ledger + human-pinned corrections** (ADR-F042/F043/F044 — the Store has no
   `valid_at/invalid_at/superseded_by`, no as-of query, no gate-enforced pin-immutability); (b) the
   **documents hybrid retriever** (`api/app/knowledge/retrieval.py`, ADR-0008 — FTS+dense fusion +
   rerank + the Citation Engine byte-offset contract), already shipped for KnowledgeBases but **not
   wired to the matter agent path**.
5. **Cost is a first-class axis.** At ~1000 docs the dominant cost is one-time indexing; the cheap
   correct index for broad cross-corpus recall is **local embeddings** (`torch` already in-image;
   the gateway has Tier-1 local provider doors), with near-zero per-query cost. **PageIndex is a
   *different thing* — reasoning/agentic RAG (the LLM navigates a document's structure tree), not an
   embeddings substitute — and is complementary, not competing.** Its tree-build is LLM-heavy
   (~150–260 calls/doc), so its fit is a **use-case + cost question to settle by eval**, not a
   blanket skip (see consequences).
6. **We cannot ship an agentic-retrieval vision we cannot measure**, and the orchestrator (Claude)
   **cannot eyeball 1000-doc recall**. CUAD (510 human-annotated contracts, 41 clause categories,
   SQuAD-2.0 with gold `answer_start` offsets, CC-BY-4.0) is the objective gold standard for the
   scale case; DeepSeek (the qualified provider) is the agent-under-test and Claude judges the
   agentic-quality cases.

Constraints (CLAUDE.md): all external-provider LLM calls route through the gateway (sole egress/
key-holder, ADR-F010) — **local in-process compute is permitted**; cross-user access → 404 not 403;
audit carries counts/types/IDs only; retrieved documents + author/turn strings are untrusted model
input; the unit-of-work tier is auto-write-then-correct (ADR-F042); new dependencies are SBOM
surface; deepagents ships breaking changes on minors (re-verify signatures at each slice boundary).

## Considered options

1. **Build a parallel custom store + conversation index + retriever (the pre-research drift).**
   A new `source_type='conversation'` chunk table, a conversation→chunk→embed worker, a custom
   `search_matter_conversations` retriever, custom cross-thread memory storage/routing. **Rejected:**
   it hand-reimplements the langgraph `Store` + deepagents `CompositeBackend`/`SummarizationMiddleware`
   we already depend on — wasted work, a maintenance liability fighting the substrate, and exactly
   what the maintainer's "fit the framework, don't reinvent" constraint forbids.

2. **All-native (lean entirely on the langgraph Store for retrieval).** Store everything — memory,
   conversations, documents — in the Store and use `store.search`. **Rejected:** the Store is
   single-vector ANN; it does not do chunking, embedding-at-scale, hybrid FTS+dense fusion,
   reranking, or citation byte-offsets, and has no bi-temporal/as-of/pin semantics. It would
   regress document retrieval (the cite-grade legal must-have) and discard ADR-F042/0008. "Native"
   is the substrate, not retrieval-at-scale.

3. **Native substrate + custom retrieval layer, eval-gated (CHOSEN).** Adopt the native langgraph
   `Store` + deepagents `CompositeBackend`/`MemoryMiddleware`/`SummarizationMiddleware` as the
   memory/conversation substrate; keep custom **only** the two proven-gap layers (bi-temporal fact
   ledger; documents hybrid retriever incl. chunking + embedding-at-scale + fusion + rerank +
   offsets); plug **one shared local embedder** into both the Store's `IndexConfig.embed` and the
   documents pgvector column; and **gate every slice on a measured delta** against a CUAD-gold +
   Claude-judged-DeepSeek eval baseline.

## Decision outcome

Chosen: **option 3.** Maintainer rulings (AskUserQuestion, 2026-06-27): *use native, but Deep
Agents don't solve chunking/embeddings at scale — don't be confused*; conversations on the native
Store + summarization-offload (drop the custom pipeline); **eval-first sequencing** (build the
measurement instrument and a baseline before the architecture slices).

**The reconciled architecture:**

- **Substrate (native).** Wire `AsyncPostgresStore` (with an `IndexConfig` whose `embed` is the
  shared local callable) + a `CompositeBackend` routing `/memories/{company,practice,user,matter}/`
  + `/conversation_history/` to `StoreBackend` namespaces; `MemoryMiddleware` injects the tier
  digests (replacing hand-assembled prompt concatenation); `SummarizationMiddleware` does
  within-chat compaction + verbatim transcript offload. Company/practice routes are **read-only to
  the agent** (native `FilesystemPermission(deny)` **plus** a storage-level read-only wrapper as
  backstop, since subagent permissions *replace* the parent's). Subagent **fan-out** stays the
  native `task` tool (already adopted, zero scaffolding).
- **Conversations (native).** Cross-thread "search this matter's conversations" and within-chat
  recall are served by `store.asearch` over a matter-scoped namespace + the summarization offload,
  behind a **thin** `search_matter_conversations` tool (matter-scoped, 404-conflated) — **not** a
  custom chunk/embed/index pipeline. Provenance-cited (thread/date), never byte-offset-cited.
- **Documents (custom).** Keep the hybrid retriever (`knowledge/retrieval.py`) for documents only,
  wired to the matter path (degrades to FTS until vectors exist); chunking + embedding-at-scale are
  ours. Local embeddings are the cost play; PageIndex is backlog (measured-trigger only).
- **Facts/corrections (custom).** Keep `MatterMemoryEntry` as the thin bi-temporal "current truth"
  tier the agent reads (ADR-F042/F043/F044 referenced, not superseded).
- **One shared local embedder** serves the Store index (conversations) and the documents pgvector
  column — one model, one gateway-honest door (in-process local, ADR-F010), $0/token.
- **Eval-gated build.** Two tracks reusing the existing scenario harness (`api/tests/agents/
  scenarios/`) + `api/evals/`: **Track A** (Claude-judged DeepSeek on agentic scenarios) and
  **Track B** (CUAD-gold objective recall@k/precision/AUPR). Build order is **eval-first**: measure
  the FTS-only baseline, then ship each slice (local embeddings, rerank, …) only when it beats the
  baseline by a pre-registered margin (set *after* the baseline, never tighter than the CI).

The decomposition (eval-first) is in `docs/fork/plans/RETRIEVAL-MEMORY-eval-first.md`. ADR-0008
(hybrid retriever) and ADR-F042/F043/F044 (matter memory) are **referenced, not superseded** — this
ADR places them inside the native picture.

## Consequences

- **We get on the substrate the product was always meant to use**, retire the hand-assembled
  prompt-injection memory path, and stop a parallel build before it starts. The marginal work for
  "conversations as a retrievable source" collapses to native middleware + a thin tool.
- **The custom layer is now scoped precisely**: chunking, embedding-at-scale, hybrid/rerank/offsets,
  and bi-temporal facts — and *only* those — are ours. Anything else routes through the framework.
- **Two inference loci** (the gateway for chat/agents; an in-process local embedder for indexing)
  is a deliberate, recorded trade against CLAUDE.md's "one readable egress" value — it breaks no
  security rule (the embedder holds no key and egresses nothing), but it is a real call; the
  gateway-local door (Tier-1 `ollama`/`vllm`) remains the principled alternative if single-choke-point
  is later judged to matter more.
- **A new SBOM line** (`onnxruntime` + `fastembed`, Apache-2.0, + a vendored embedding model file)
  is added when local embeddings land; `torch` is already in-image (via Docling) so this is one
  permissive runtime, not a torch-scale add. It removes the recurring OpenAI-embedding egress
  dependency.
- **A real safety gap is surfaced, not assumed-closed:** R4 (the per-action cost cap) is today a
  documented **no-op** (`guard.py`), so nothing enforces a per-run *token* budget. Safe
  model-driven fan-out therefore needs a fan-out quota + wiring R4 into a real token budget — its
  own slice, called out here.
- **PageIndex / agentic tree-RAG is a first-class EVAL CANDIDATE, not a skip.** It is complementary
  to embeddings (reasoning over a document's structure vs vector similarity) and the two may compose.
  We **evaluate it through the same tracks** to find *where* it earns its cost — hypotheses to test:
  (a) precise navigation **inside a single large, highly-structured document** (long agreements,
  where chunk-embedding fragments cross-references); (b) as a **selectable agentic-retrieval strategy**
  the agent chooses for structure-heavy queries (ties to the strategy-selection research); (c)
  **explainability/auditability** — the navigation path is a traceable reasoning chain, valuable for
  legal defensibility. The trade is real (LLM-heavy tree-build ~150–260 calls/doc), so likely
  cost-bounded to high-value documents — *the eval decides the boundary*. Evaluation is a **contained
  spike** (PageIndex OSS is MIT; routes via LiteLLM, which can point at our gateway or a local model)
  that does **not** ship `litellm` into the product image; **adoption is a separate post-eval decision
  + its own ADR** if a dependency is added. Embeddings-hybrid remains the cross-corpus recall
  workhorse; PageIndex is measured against/alongside it, never assumed in or out.
- **Build is gated by measurement.** Every prior assumption (hybrid beats FTS, rerank helps, recency
  matters, within-chat retrieval is needed) becomes a measured delta; a slice that doesn't beat the
  baseline doesn't ship. CUAD gates the *mechanism* objectively; Claude-judged DeepSeek gates
  *agentic quality*. Eval cost (real DeepSeek tokens; local-embed compute) is bounded by subset
  sizing + a per-matrix ceiling.
- **Honest limits** (carried from the research): native API signatures re-verify at each slice
  boundary (deepagents minor churn); CUAD is commercial-contract-skewed (weaker proxy for Privacy/
  Disputes — area quality stays a Track-A judged concern); the custom eval scorer is designed, not
  yet written; all thresholds are post-baseline placeholders.

## Addendum — N2 (2026-06-29): conversation-history offload was already wired by N0

The planned N2 ("`SummarizationMiddleware` with a `StoreBackend` offload route") was found, on
exploration, to be **already structurally wired by N0** — recorded here so it is not relitigated.
`create_deep_agent` *always* installs a default `SummarizationMiddleware(model, backend)` (deepagents
`graph.py`); N0 passes it our per-run `CompositeBackend`, whose `/conversation_history/` route maps the
middleware's offload path `/conversation_history/{thread_id}.md` (computed from the composite's
`artifacts_root='/'`) verbatim into the Store under namespace `("conversation", thread_id)`. So evicted
history persists and is recalled via the path the summary message embeds (builtin `read_file`) — **with no
production code**. N2 therefore shipped as **verify + test + eval**: a deterministic offload drift-guard
(`tests/agents/test_summarization_offload.py`) + the A6 within-chat-recall Track-A scenario (a finding per
ADR-F015, not a gate). Compaction fires at ~0.85·`max_input_tokens` (200k in production), so it is exercised
only by lowering the window in the eval harness — a test seam, never a production knob.

**Maintainer rulings (2026-06-29):** (a) plain-chat transcripts persist too (the conversation route installs
whenever a `thread_id` is bound — always; thread-scoped, no cross-user reach — KEPT, not matter-gated);
(b) the A6 gate exercises the full offload → `read_file` recall path (an injected `InMemoryStore`).

**Known degraded-mode limitation (accepted, not fixed):** the offload *file name* derives from
`configurable.thread_id`, which the runner sets only when a checkpointer is present (`runner.py`), while the
Store *namespace* derives from `rt.context.thread_id` (always `str(run.thread_id)`). If the Store is live but
the checkpointer is `None` *and* a single bounded run crosses the ~170k-token trigger, the offload mis-keys
under a generated `session_<hex>` file name (right namespace, wrong key). It is doubly moot — degraded-
checkpointer runs already refuse follow-ups (so cross-run recall is moot) and within-run recall still works
(the same `session_<hex>` is used for the write and the embedded recall path) — so it is documented here
rather than guarded. The Store-vs-SQL convergence and shared Practice Knowledge tier remain the future prize
(ADR-F050).

## Addendum — N3 (2026-06-29): the cross-thread conversation-recall tool

N2 made each thread's transcript *persist* to the Store (`("conversation", str(thread_id))`); N3 adds the
agent's **reader**: a thin, area-agnostic, matter-scoped read tool `search_matter_conversations(query,
thread_id=None)` (`app/agents/matter_conversation_tools.py`), granted to every matter-bound run whose Store
is live — the new cross-thread recall capability (CLAUDE.md blocker #3). No production code beyond the tool +
its wiring; **no migration, no new dependency, no gateway change.**

**The SQL↔Store join (the load-bearing design call).** The conversation namespace is keyed by `thread_id`
ALONE; the matter→thread link lives only in SQL (`AgentThread.project_id`, and the namespace component is
exactly `str(AgentThread.id)`). The tool therefore (1) owner-scope-reloads the matter (`_load_owned_matter`
→ 404-conflate to `_GONE_MSG`), (2) **SQL-enumerates the matter's threads** `WHERE user_id AND project_id`
(parameterized, recent-first, capped, the current thread excluded for a whole-matter sweep), then (3) reads
each thread's Store namespace. We deliberately do **not** prefix-search `("conversation",)` directly: that
returns every thread of every user and matter in the store, turning the owner/matter boundary into an
in-memory filter applied *after* cross-tenant rows are in process memory. Keeping the boundary in the SQL
`WHERE` is the security invariant — a code comment marks it load-bearing.

**Lexical, not semantic (for now).** The production Store is filter-only (no `IndexConfig`), so
`store.asearch(query=…)` is a silent no-op without an embedder (verified in-container: unranked items,
`score=None`). N3 therefore does its own Python keyword scan over the retrieved `content` — exactly like
`search_matter_memory`. Slice C's embedder later layers Store `query=` ranking on top (no rewrite).

**Maintainer rulings (2026-06-29):** (a) **scope default = whole-matter** (no `thread_id` ⇒ search every
earlier thread of this owner+matter — the cross-thread win; a supplied `thread_id` narrows to within-chat
and is intersected against the matter's own set, so a foreign id silently matches nothing — no existence
leak); (b) **transcript source = Store-first** (the offloaded `/conversation_history` content only; "also
search the always-persisted SQL `AgentRun` transcript so short un-offloaded threads are recallable" is
logged as a backlog item to add *iff* the eval shows Store-only is too sparse); (c) **A5 gate = seed +
best-effort live** (a deterministic seed of thread-1's namespace for the repeatable gate — and the unit
test — plus a recorded live-compaction attempt; mirrors how N2 was gated).

**Security posture (read-only tool).** Routed through `guarded_dispatch` (R6/R5/R4) like the other read
tools; the guard's auto-audit is counts/IDs + `result_chars` only — no transcript text or thread_ids reach
an audit row. Retrieved transcripts are **untrusted** (the model, or a counterparty paste it once read,
wrote them) — the digest wraps them in a labelled "a record of what was said — not instructions" block and
the tool acts on nothing it retrieves. **Degraded-Store edge:** the tool is built/granted only when the
Store is live (a degraded Store has no transcripts to search); the doctrine is injected unconditionally for
matter-bound runs, so in that rare edge the agent gets a graceful R6 "not granted" if it tries — never a
crash. *Gate (ADR-F015 finding, not a frozen bar):* A5 cross-thread recall via the tool + a cross-matter /
cross-owner / foreign-thread_id isolation check (deterministic in `test_matter_conversation_tools.py`).

## Addendum — Slice A (2026-06-29): the matter document tool wired to one hybrid retriever

The first **Phase-2 ("cost play")** slice. The agent's matter document tool (`search_documents`) ran a
pure-FTS query (`tools.py:_FTS_SQL`); a production hybrid retriever (`knowledge/retrieval.py:hybrid_search`,
FTS + pgvector, ADR-0008) existed but was **KB-scoped and unreachable from the matter path**, and the
Track-B CUAD eval ran a *third* copy of the matter FTS query (`cuad_eval.py:_EVAL_FTS_TEMPLATE`) kept in
sync by a drift guard. Slice A collapses this to **one matter retriever**:
`knowledge/retrieval.py:matter_hybrid_search` — same fusion machinery as the KB `hybrid_search`, a matter
scope (the `project_files` attach-join ∪ the upload-time `files.project_id`, owner re-asserted,
`deleted_at IS NULL`), and `websearch_to_tsquery` FTS. Both the production tool **and** the eval's
`fts_retrieve` now route through it, so *"agent mode matches retriever-only"* is **structural**, not a
hand-kept drift guard.

**Maintainer rulings (2026-06-29):** (a) sequence = **Slice A first, alone** (a zero-behaviour-change
wiring refactor gated on matching the frozen E0 baseline), with Slice C (the local embedder) as the next
PR; (b) the Slice C embedder must keep **both** Door A (in-process) **and** Door B (gateway-side) paths
available — a configurable/injected embedding provider, *not* a one-way destructive commitment (recorded
here for the Slice C plan; Slice A is deliberately embedder-agnostic).

**No-op by construction.** No embedder is wired yet, so `search_documents` passes `query_embedding=None`
and `matter_hybrid_search` takes its **FTS-only fast path** — one ordered query
(`rank DESC, filename ASC, chunk_index ASC`) returned verbatim, **byte-identical** to the pre-Slice-A
behaviour and the frozen Track-B baseline. The hybrid fusion branch (FTS + pgvector candidates, min-max
fused, hydrated) is present and unit-tested with synthetic vectors but **dormant** until Slice C passes a
real query embedding + a tuned `alpha`. The matter scope **deliberately diverges** from the KB scope and
must not converge: no `ingestion_status='ready'` filter (a matter chunk is searchable as soon as it
exists), and `websearch_to_tsquery` not `plainto_tsquery`. **No migration, no new dependency, no gateway
change.** *Gate (ADR-F015 finding):* the full CUAD Track-B baseline re-run through the new path equals the
frozen E0 numbers (within-doc hit@8 0.391 / cross-doc 0.044); deterministic drift guard
(`test_cuad_retrieval_smoke`) + fusion/scope/document_id tests (`test_matter_hybrid_search`); the
`search_documents` tool contract + audit-body-free check (`test_agent_tools`) unchanged.

## Addendum — Slice C1 (2026-06-29): the local embedder + matter-document hybrid retrieval

The first **Phase-2 "cost play"** slice lights up the vector side of `matter_hybrid_search` (the dormant
branch Slice A built). A configurable, injected **`EmbeddingProvider`** (`app/knowledge/embedding_provider.py`)
keeps **both doors** the maintainer required:

- **Door A — `LocalEmbeddingProvider`** (the default): in-process `fastembed`/ONNX, `BAAI/bge-base-en-v1.5`
  (768-dim, MIT), bundled into the image at build (no runtime download). $0/token, no provider key, and the
  dev stack gets semantic retrieval with no live gateway embedding model. This is a **second inference
  locus** — permitted for *embeddings* (not external-provider generation, which ADR-F010 governs); keeping
  Door B available preserves the single-egress posture as a one-env-var switch. bge's query/passage
  asymmetry is applied in-provider (the query instruction prefix; `fastembed`'s `query_embed` is a no-op for
  the bundled ONNX build).
- **Door B — `GatewayEmbeddingProvider`**: the existing `/v1/embeddings` egress, now threading a
  `dimensions` reduction so an OpenAI `text-embedding-3-*` emits the same 768 dim → fits the same column.

Selection is `Settings.embedding_provider` (`local` | `gateway`, default `local`).

**No destructive ALTER (maintainer ruling).** Migration 0078 **adds** `document_chunks.embedding_local
vector(768)` + an ivfflat index; the live `embedding vector(1536)` column + the KB/chat `hybrid_search`
path are **untouched** (the two doors live in separate columns). The matter retriever's vector branch reads
`embedding_local`; the ingest worker backfills it via a new `embed_local_chunks_for_file` job (per-file
short-lived sessions); `tools.py:_search` embeds the query (local door) and fuses at `alpha` with an
FTS-only fallback when the embedder is unavailable or a matter is un-backfilled. **No gateway change beyond
the additive `dimensions` passthrough; one new SBOM family (`fastembed` → onnxruntime/tokenizers/numpy).**

*Gate (ADR-F015 finding — Track-B, apples-to-apples on the same N=30 CUAD subset, local door, alpha=0.5):*
hybrid vs the FTS floor — **within-doc recall@5 0.314 → 0.629 (+100%)**, hit@8 0.356 → 0.812; **cross-doc
recall@5 0.077 → 0.100 (+29%)**, hit@8 +27%. **Pre-registered X (ship threshold, set post-calibration):
within-doc recall@5 must beat the same-corpus FTS floor by ≥ +0.05 — observed +0.31, 6× the bar.** N=30 (not
the frozen 150) because the local embedder + eval query-volume crashed a Postgres backend on this
memory-constrained dev box at N≥60; N=30 alone is stable and its FTS floor tracks the frozen @150. Evidence +
the full table: `docs/fork/evidence/retrieval-eval-slice-c/`. Deterministic: `test_embedding_provider` (Door
A real model + Door B `dimensions`), `test_matter_hybrid_search` fusion over `embedding_local`, the FTS drift
guard, migration on a throwaway pgvector container. **C2 (the langgraph Store `IndexConfig` for
conversation/memory semantic recall) reuses this same provider — a separate slice.**

## Addendum — Slice C2 (2026-06-29): the Store `IndexConfig` for conversation/memory semantic recall

C1 lit up semantic search over matter **documents**; C2 lights it up over the **Store** —
conversation transcripts and the `/memories/*` tiers. N0 built the `AsyncPostgresStore` filter-only (no
`IndexConfig`), so `store.asearch(query=…)` was a silent no-op; N3's `search_matter_conversations` therefore
scanned transcripts lexically. C2 wires the Slice-C1 `EmbeddingProvider` as the Store's `IndexConfig.embed`
so `asearch(query=…)` ranks by cosine — the paraphrase recall a keyword scan misses.

**Single wiring point.** `app/agents/store.py:build_store_index_config(provider)` returns
`{dims, embed, fields:["content"]}`; `init_agent_store()` passes it to `AsyncPostgresStore(pool, index=…)`.
Both composition roots (api lifespan + arq worker) already route through `init_agent_store`, so this is ONE
edit. `setup()` then builds the pgvector `store_vectors`/`vector_migrations` tables **non-destructively**
(N0 left them absent; verified on a throwaway pgvector container — the library owns its own schema, ADR-F008,
so no alembic migration). The same helper builds the index for the `InMemoryStore` tests, so they exercise
production's shape.

**Symmetric embedding.** `embed` is a plain async `AEmbeddingsFunc` over the provider; `langgraph` wraps it
(`ensure_embeddings` → `EmbeddingsLambda`) so `aembed_query` and `aembed_documents` BOTH route to the same
function — embedding is symmetric regardless of which method a store calls (the `AsyncPostgresStore` embeds
the query via `aembed_documents`, the `InMemoryStore` via `aembed_query`; both land in the same closure;
verified in-container). bge's query-instruction asymmetry (applied in the C1 *document* path) is intentionally
not applied to the Store. `fields=["content"]` embeds only the transcript/summary text deepagents'
`StoreBackend` writes (`{"content": …}`), not timestamps/encoding. Indexing is store-WIDE (every
`/memories/*` + conversation write embeds on `put`) — deliberate; the local door is $0 and the model loads
lazily on first embed, so startup stays cheap and a degraded provider never crashes a run.

**The tool — two reads (a review-caught blocker).** A first cut passed `query=` to the single transcript
read. That silently regressed N3 recall: an *indexed* `AsyncPostgresStore` runs the query branch as
`store JOIN store_vectors` (an **INNER JOIN**), so any row written **before** the index existed (every
conversation transcript from the N0-N3 era, which has no `store_vectors` row and is not re-embedded until its
key is next `put`) is dropped from the result — `content=''` → the thread is skipped before the lexical scan
even runs, so an exact keyword match on pre-C2 history vanishes. (`InMemoryStore` masks this with a
`scoreless` fallback the pg store does not share.) The fix splits `_read_thread_transcript` into two reads of
the same namespace: a **query-less** read for the transcript `content` (returns every row, no vector join —
exactly the N3 read), and a separate best-effort **`query=`** read whose `SearchItem.score` drives semantic
ranking (`None` on a filter-only / degraded store, or for an un-embedded pre-index row → lexical fallback,
byte-identical to N3). The two layers compose: a thread surfaces when it matches the keyword scan **or**
clears `_SEM_THRESHOLD` (0.6); a semantic-only hit shows leading summary lines as context. Recall is
**thread/summary-granular** (the N2 offload writes one summary key per thread) — finer per-turn granularity is
a future slice (MILESTONES backlog). A pgvector regression test pins it: a row written index-OFF then
searched index-ON is dropped by `query=` but recovered by the query-less read, and surfaces end-to-end
through the tool's lexical scan.

*Gate (ADR-F015 finding — live, real `bge-base` on a throwaway pgvector, the production index path):*
genuine paraphrase queries sharing **no salient keyword** with their target summary rank it above threshold
and above the off-topic thread, while an unrelated query stays below threshold on both — paraphrase hits
**0.62–0.68**, off-topic/related-but-wrong **0.43–0.46**, so `_SEM_THRESHOLD = 0.6` sits in the gap with a
precision margin. Evidence: `docs/fork/evidence/retrieval-eval-slice-c2/`. Deterministic (hermetic concept
embedder, no model download): `test_store_index_config` (config shape + `InMemoryStore` cosine ranking +
filter-only no-op), `test_agent_store` (indexed `setup()` builds `store_vectors` + ranks on real pgvector;
no-index posture preserved), and the new semantic cases in `test_matter_conversation_tools` (paraphrase
surfaces, filter-only misses the same paraphrase, honest absence preserved). **No migration, no dep, no
gateway change.** The N-ladder semantic objective (A5 paraphrase recall) is now met end to end.
