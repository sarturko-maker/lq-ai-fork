# Plan — Retrieval & memory, eval-first (F2; ADR-F049)

**Decision:** [ADR-F049](../../adr/F049-native-memory-substrate-and-eval-gated-retrieval.md) —
native langgraph Store + deepagents CompositeBackend as the memory/conversation substrate; keep
custom only the bi-temporal fact ledger + the documents hybrid retriever (chunking, embedding-at-scale,
fusion, rerank, citation offsets); one shared local embedder; **eval-gated, eval-first** build.
Research arc: [`research/RETRIEVAL-MEMORY-INDEX.md`](../research/RETRIEVAL-MEMORY-INDEX.md). Milestone:
**F2 — Memory** (MILESTONES.md).

**Sequencing (maintainer ruling, 2026-06-27): EVAL-FIRST.** Build the measurement instrument and a
baseline *before* any architecture slice, so every slice must beat a measured number to ship. Each
slice is a vertical, runnable, ≤2–3-day, one-PR change under the ADR-F005 merge gate. Re-plan at phase
boundaries.

---

## Why eval-first

We cannot ship an agentic-retrieval vision we can't measure, and the orchestrator (Claude) **cannot
eyeball 1000-doc recall**. So the first deliverable is the instrument:
- **Track A** — Claude-judged DeepSeek on agentic scenarios (read/retrieve/fan-out choice, grounding,
  long negotiation, cross-thread recall, anti-hallucination). Reuses `run_scenario` + the shipped
  `craft_judge`.
- **Track B** — CUAD-gold objective retrieval (recall@k / precision / AUPR / abstention) against human
  `answer_start` spans. Reuses `seed_multi_doc_matter`; new code = a CUAD loader + an objective scorer.

Then every architecture slice is gated on a **pre-registered delta vs the FTS-only baseline** (margins
set *after* the baseline, never tighter than the metric CI). Eval design detail:
[`research/retrieval-eval-design-and-oss-deepagents.md`](../research/retrieval-eval-design-and-oss-deepagents.md).

---

## Phase E — the eval instrument (build FIRST; no architecture change)

- **E0 — Track-B CUAD harness + objective scorer + FTS-only baseline.** `load_cuad` (download
  `CUADv1.json`, CC-BY-4.0, into a gitignored fixture dir; pick the agreed subset) → seed each contract
  as a matter document via `seed_multi_doc_matter` → run clause questions (retriever-only mode = no LLM
  cost; agent mode on a small subset) → score retrieved/quoted spans vs gold `answer_start`
  (recall@k/precision/AUPR/abstention-on-absent). Reuses `api/tests/agents/scenarios/harness.py` +
  `api/evals/` (`runner`/`scoring`/`report`). **Output: the FTS-only baseline frozen at
  `docs/fork/evidence/retrieval-eval/baseline/`.** Scorer unit tests + a tiny retriever-only smoke run
  in CI ($0); live agent-mode is provider-marked/CI-skipped. *No ADR; reuses existing infra.*
- **E1 — Track-A first scenario suite + masked judge + baseline.** Generalise `craft_judge`
  (`commercial_redline_lib.py:223-277`) into a masked retrieval/agentic judge (f0-s9 masking: sanitised
  tool timeline + answer + expectations only). Ship A1 (multi-doc grounding), A5 (cross-thread recall —
  initially expected-fail until N0/N3), A7 (read/retrieve/fan-out strategy choice), A8 (negative
  control); A2/A3 (long-negotiation) largely exist in `test_commercial_redline_eval.py` / the C5a path.
  Freeze the Track-A baseline (N≥10). *No ADR.*

**Phase-E exit:** a frozen FTS-only Track-B baseline + a green Track-A regression net. Now slices can be
gated.

## Phase 0 — get on the native substrate

- **N0 — wire the langgraph `Store` + `CompositeBackend` (ADR-F049 accepted here).** Instantiate
  `AsyncPostgresStore` in the lifespan (mirror the checkpointer DI seam), pass `store=` + a
  `CompositeBackend` with `/memories/{company,practice,user,matter}/` + `/conversation_history/` routes
  to `create_deep_agent`. Add the namespace-distinctness assertion + the read-only `BackendProtocol`
  wrapper for company/practice (permissions are tool-level + subagent perms *replace* parent's). Key
  namespaces via `rt.context`. **No semantic index yet** (filter-only; degrades gracefully). *Migration-
  light; ADR-F049 accepted with this slice. Gate: A5 substrate lights up; nothing green regresses.*
- **N1 — move tier digests to `MemoryMiddleware`.** Replace the hand-assembled prompt blocks
  (`composition.py:305-391`) with `MemoryMiddleware(sources=[…])` per tier. *Gate: prompt-equivalence
  regression (the injected digests match the old prompt); all Track-A scenarios stay green.*

## Phase 1 — conversations on the native Store

- **N2 — `SummarizationMiddleware` with a `StoreBackend` offload route.** Native compaction (profile
  already set, `factory.py:111`) + verbatim offload to `/conversation_history/`. Gives persistent,
  retrievable within-thread transcripts with no custom code. *Gate: A6 (within-chat recall post-
  compaction). Also measures whether within-chat retrieval needs anything beyond native.*
- **N3 — thin `search_matter_conversations` over `store.asearch`.** Matter-scoped (404-conflated),
  optional `thread_id` filter for within-chat. No chunk/embed/index pipeline. Filter/lexical-first;
  gains semantic recall when the embedder (Slice C) lands. *Gate: A5 recall via the tool; cross-matter
  404 security check.*

## Phase 2 — the cost play (shared local embedder; documents)

- **Slice C — local embedding callable (ADR-F049 addendum; new SBOM line).** In-process FastEmbed/ONNX
  embedder (ADR-F010 Door A; `torch` already in-image, add `onnxruntime`+`fastembed`+a model file) for
  the documents pgvector column **and** as the Store's `IndexConfig.embed` — one model, one door,
  $0/token. ALTER the chunk `vector` column to the model's native dim (768 recommended; the path is
  anticipated at `embed.py:57-59`). *Gate: Track-B B2 — ship only if CUAD recall@5 beats FTS-only by
  ≥ X pp; conversation semantic recall improves.*
- **Slice A — wire matter document tools to the existing `hybrid_search`.** Point `_search`
  (`tools.py`) at a matter-scoped `hybrid_search` (`knowledge/retrieval.py`); degrades to FTS until
  vectors exist (safe to ship before C). *Gate: Track-B B1→B2 agent mode matches retriever-only.*

## Phase 3 — later / only if measured

- **Slice D — local cross-encoder rerank** over the fused set (documents). *Gate: Track-B B3 — ship
  only if precision@5 lifts ≥ Y pp without hurting recall@5.*
- **Strategy + safety — fan-out quota + wire R4 into a real per-run token budget.** R4 is a no-op today
  (`guard.py`); safe model-driven fan-out needs a token-budget brake + a fan-out quota + a pre-flight
  `estimate_read_cost` helper (over `character_count`) + budget visibility. *Likely its own ADR. Gate:
  A7 strategy choice; a runaway-fan-out cost test.*
- **Recency weighting** on conversation results — thin post-filter. *Build only if a measured stale-turn
  failure appears (A5 stale variant).*
- **Documents MAP in the Store** (the L1 router; first doc's `fact_type="document"` → a
  `(matter,id,"map")` namespace). *Build only if large-corpus recall degrades without it.*
- **Backlog — oversized-doc navigation / PageIndex.** Only on a *measured* single doc exceeding the
  read cap where in-doc FTS fails: free chunk-derived section map first, PageIndex-via-gateway/local
  (new `litellm` dep) only if insufficient. Own ADR if a dep is added.

**Dependency order:** E0 + E1 → N0 (ADR-F049) → N1, N2 → N3 | C → [Store semantic + docs dense] | A
(independent) | D / strategy-R4 / recency / MAP gated on measured need.

---

## Verification / DoD (per slice, ADR-F005 gate)
Build+lint+typecheck+tests pass and shown; new behaviour has tests; fresh-context adversarial review
incl. the mandatory security + simplification pass; live verification (the slice's eval gate run on the
dev stack, evidence in the PR); HANDOFF updated. Containerized suites quoted for touched services.
Re-verify deepagents/langgraph signatures at each slice boundary (minor churn). Eval slices freeze
baselines under `docs/fork/evidence/retrieval-eval/`.

## Non-goals
- No parallel custom store/conversation-index/retriever (use native — ADR-F049 option 1 rejected).
- No all-native retrieval (the Store is single-vector; documents keep the custom hybrid retriever).
- No PageIndex / tree-RAG now (backlog, measured trigger).
- No a-priori eval thresholds (set X/Y after the B1 baseline, never tighter than CI).
- No CI spend on live DeepSeek (provider-marked, manual/on-demand; retriever-only + scorer units in CI).

## Open maintainer calls (settle before/with E0)
1. **CUAD subset size** — retriever-only large subset (proposed 100–200 contracts, all 41 categories) +
   agent-mode small subset (proposed 10–25 contracts × ~10 high-value categories: cap, indemnity, IP,
   governing law, termination, exclusivity, change-of-control…). Confirm numbers + shortlist.
2. **Track-B gate thresholds X (embeddings) / Y (rerank)** — set post-baseline, never tighter than CI.
   Approve the policy.
3. **Track-A judge rubric strictness** — per-scenario pass bars (A3 coverage full/partial, A4 version
   correct/wrong, A7 strategy ≥2/3).
4. **Eval-in-CI vs manual** — live tracks manual/on-demand (provider-marked); scorer units + a tiny
   retriever-only smoke in CI. Confirm.
5. **DeepSeek eval spend budget** — a per-matrix ceiling; retriever-only as the day-to-day signal,
   agent-mode reserved for slice gates / milestone runs.
6. **Second model family for Track A?** (f0-s9 recommends ≥2.) Defer or include alongside DeepSeek?
7. **Embedding door / dim** — in-process local (Door A) vs gateway-local (Door B); 768 vs 384 vs keep
   1536. (Recommended: Door A, 768 — confirm at Slice C.)
