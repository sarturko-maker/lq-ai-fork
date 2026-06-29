# F049 — Native memory substrate (langgraph Store + deepagents CompositeBackend) + custom retrieval layer, eval-gated

- Status: accepted (with F2 slice **N0**, 2026-06-28 — the native Store + CompositeBackend substrate);
  addenda: **N1** (2026-06-28, read-only tier middleware), **N2** (2026-06-29, conversation offload — see
  the addendum at the end)
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
