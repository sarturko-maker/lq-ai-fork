# Retrieval & memory — research arc index (2026-06-27)

A seven-document research arc on how a practice-area Deep Agent discovers, selects, and retrieves
matter material (documents **and** conversations) at scale, cost-aware, **fitting langgraph/deepagents
rather than reinventing them**, and **how we test it**. Produced the architecture decision
**[ADR-F049](../../adr/F049-native-memory-substrate-and-eval-gated-retrieval.md)** and the
eval-first plan **[`plans/RETRIEVAL-MEMORY-eval-first.md`](../plans/RETRIEVAL-MEMORY-eval-first.md)**.
Feeds milestone **F2 — Memory** (MILESTONES.md).

Read order is top-to-bottom; each builds on and corrects the prior. The **native-fit** doc supersedes
the parts of the earlier docs that drifted toward reinventing native capabilities.

| # | Doc | Headline verdict |
|---|---|---|
| 1 | [`document-discovery-and-map.md`](document-discovery-and-map.md) | The gap is *descriptions + cross-turn focus*, not retrieval power. A maintained **documents MAP** (description·role·side·status) is the cross-document selection layer. *(Cost-blind — corrected by #2.)* |
| 2 | [`document-retrieval-at-scale-and-cost.md`](document-retrieval-at-scale-and-cost.md) | At ~1000 docs FTS-only fails; **local embeddings + the already-shipped hybrid retriever** are the cost play (one-time local index, ~$0/query). The fork **already ships** `hybrid_search` (pgvector+FTS+fusion) for KBs — the matter path just doesn't call it. *(Research framed PageIndex as skip-now; **refined by ADR-F049/plan to an eval candidate** — agentic RAG complementary to embeddings, fit found via evals, Slice P.)* |
| 3 | [`conversations-as-retrievable-knowledge-and-upstream-awareness.md`](conversations-as-retrievable-knowledge-and-upstream-awareness.md) | Conversations are a first-class source. Two substrates today: legacy chat FTS (owner-scoped, single-turn, not agent-callable) vs the agent path (**no** conversation search). Raw-transcript vs distilled-memory split. **Upstream review (ADR-F001 awareness only): 76 commits = CourtListener+MCP+chat-tool-loop+#151 multi-turn; no deepagents pivot, no conversation embeddings — solved nothing we're building; no sync recommended.** |
| 4 | [`retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md`](retrieval-strategy-selection-fanout-vs-read-vs-retrieve.md) | Compose three consumption modes (cheap retrieval / read-in-full / subagent fan-out); **cheap-first, escalate** (not fan-out-by-default), keyed on a pre-flight estimate (`Σ character_count / 4`) vs remaining budget. **Safety finding: R4 cost cap is a no-op** — no per-run token budget enforced today. |
| 5 | [`native-fit-reconciliation-store-vs-custom.md`](native-fit-reconciliation-store-vs-custom.md) | **The pivot.** We're off-substrate (checkpointer only). Adopt the native langgraph **Store + deepagents CompositeBackend/middleware**; keep custom ONLY the bi-temporal fact ledger + the documents hybrid retriever (proven native gaps). Conversations → native `store.asearch` + summarization-offload (drop the custom pipeline). |
| 6 | [`retrieval-eval-design-and-oss-deepagents.md`](retrieval-eval-design-and-oss-deepagents.md) | **The eval design.** No OSS deepagents project does cite-grade legal retrieval (we're ahead → must self-validate). Refined native-vs-custom boundary (native = substrate + search API + embed *hook*; custom = chunking/embedding-at-scale/hybrid/rerank/offsets). **Track A** (Claude-judged DeepSeek) + **Track B** (CUAD-gold objective). Eval gates the build. |
| — | [`deepagents-ecosystem.md`](deepagents-ecosystem.md) | Prior research the native-fit doc leans on (langmem rejected as a dep; the read-only-wrapper + namespace-factory caveats; ADOPT verdicts). |

## What was verified directly (not just synthesised)

Load-bearing claims re-checked against ground truth this session:
- **Native substrate exists in our pins** — `BaseStore.asearch(query=)`, `IndexConfig{dims,embed,fields}`,
  `AsyncPostgresStore`, deepagents `CompositeBackend`/`StoreBackend`, `create_deep_agent(store=,backend=,
  memory=,middleware=)`, `SummarizationMiddleware` (mentions `conversation_history`) — all confirmed by
  in-container introspection. *(A Haiku verifier had thrown a false "refuted" on this; ground truth
  overrode it.)*
- **We wire none of it** — `composition.py:583-585` passes only `backend=` + `checkpointer=`; grep for
  the native store/middleware classes is empty.
- **The shipped hybrid retriever + embed worker + `vector(1536)` column** exist (`knowledge/retrieval.py`,
  `document_pipeline.py`, `document.py`); the matter `_search` is FTS-only.
- **`character_count` stored** (`document.py:82`); **R4 cost cap is a no-op** (`guard.py`).
- **Upstream** — 76 commits since `f91149a`; `langgraph>=0.2.76,<0.3` (no deepagents); no `messages`
  embedding column. **CUAD** — 510 contracts / 41 categories / CC-BY-4.0 / SQuAD-2.0 `answer_start`
  (matches primary sources). **Harness reuse** — `run_scenario`, `seed_multi_doc_matter`, `craft_judge`
  all present.

## The decision

Native substrate + a precisely-scoped custom retrieval layer, **eval-gated**, **eval-first** —
see **ADR-F049** and the plan. Next ADR after F049 if a dependency (local embedder, PageIndex) is added.
