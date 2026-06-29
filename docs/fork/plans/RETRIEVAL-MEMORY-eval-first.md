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

- **E0 — Track-B CUAD harness + objective scorer + FTS-only baseline. ✅ SHIPPED (2026-06-28).**
  `load_cuad` (raw `CUADv1.json`, CC-BY-4.0, gitignored fixture via `scripts/fetch_cuad.sh`; deterministic
  150-contract subset) → seed each contract as a matter document via `seed_multi_doc_matter` (verbatim
  context through the **production chunker**, so gold `answer_start` shares the chunk coordinate system) →
  run clause questions **retriever-only** (no LLM, $0) over the production matter FTS path → score retrieved
  chunk spans vs gold spans (recall@k / hit@k / precision@k / MAP + an absent-clause spurious-retrieval
  control). Two arms: **within-doc** (right contract known) and **cross-doc** (matter-wide at scale).
  Pure metrics in `tests/agents/scenarios/retrieval_metrics.py` (CI-unit-tested); rig in `cuad_eval.py`;
  CI smoke (synthetic, no corpus) + drift-guard vs `tools.py:_FTS_SQL`; corpus-gated full baseline frozen
  at `docs/fork/evidence/retrieval-eval/baseline/`. **Result (the floor every later slice must beat):
  within-doc hit@8 0.39 / MAP 0.30; cross-doc hit@8 0.04 / MAP 0.02 — lexical FTS collapses at scale and
  is 0.00 for semantically-named clauses.** Agent-mode answer-quote scoring deferred to E1 (the agent's
  retrieved-chunk set is not observable from run steps). *No ADR; reused existing infra.*
- **E1 — Track-A first scenario suite + masked judge + baseline. ✅ SHIPPED (2026-06-28).** Generalised
  `craft_judge` into a **masked judging packet** + judge (`tests/agents/scenarios/track_a_lib.py`): the
  judge (the orchestrator Claude — primary — or a `deepseek-pro` gateway fallback) sees ONLY the sanitised
  tool timeline (`evals.runner.fetch_steps`) + the visible answer (`evals.scoring.visible_answer`) + the
  rubric/expectations — never the docs, the agent prompt/doctrine, or the `run_id`, so it grades
  faithfulness-to-what-was-surfaced. Deterministic L1 reuses `evals.scoring.score_all`. Shipped A1 (multi-doc
  grounding), A5 (cross-thread recall — frozen expected-fail until N2/N3), A7 (read/retrieve/fan-out
  strategy), A8 (negative control); A2/A3 (long-negotiation) reused from `test_commercial_redline_eval.py` /
  the C5a path (not rebuilt). CI net (`test_track_a_unit.py`, masking-leak assertion + verdict parsing +
  fake-gateway wiring + L1) runs free; the live matrix (`test_track_a_eval.py`) is provider-marked. **Frozen
  baseline (N=10, DeepSeek, Claude-judged): A1 grounding 8/10, A5 recall 0/10 but honest-abstention 10/10,
  A7 no autonomous fan-out 0/10 (synthesises inline, judge-appropriate; subagents WERE wired & it delegates
  when coached per C7b — a strategy-selection finding, not a capability limit), A8 honest-absence 10/10** —
  `docs/fork/evidence/retrieval-eval/track-a/`. *No ADR; no migration; no new dependency.*

**Phase-E exit: ✅ REACHED (2026-06-28).** A frozen FTS-only Track-B baseline (E0) + a frozen Track-A
agentic baseline & CI regression net (E1). Architecture slices (N0+) can now be gated on measured deltas.

## Phase 0 — get on the native substrate

- **N0 — wire the langgraph `Store` + `CompositeBackend` (ADR-F049 accepted here). ✅ SHIPPED
  (2026-06-28).** `AsyncPostgresStore` instantiated in BOTH composition roots (api lifespan +
  arq worker — runs execute in the worker), `store=` + a per-run `CompositeBackend`
  (`/memories/{company,practice,user,matter}/` + `/conversation_history/`) passed to
  `create_deep_agent`; the existing skills backend is the composite `default` (so `/skills` is
  unaffected). `ReadOnlyStoreBackend` storage-level wrapper for company/practice (the backstop that
  survives subagent permission-replacement). Namespaces keyed via `rt.context` (a new
  `AgentRuntimeContext` + `context_schema=` — the load-bearing detail; no `org_id` exists, so the
  owner segment is `run.user_id`). **No semantic index** (filter-only; `store.setup()` makes no
  pgvector table). **No migration, no new dependency** (`AsyncPostgresStore` ships in the pinned
  `langgraph-checkpoint-postgres`). **Honest gate (maintainer-ruled):** the substrate persists a note
  across threads of a matter + isolates by matter + company/practice are read-only — proven by a
  deterministic integration test (`test_memory_backend.py`); nothing green regresses; **A5 recall is a
  tracked finding, expected ~0 until N3** (N0 ships the substrate, NOT the recall behaviour).
- **N1 — move the read-only DATA tier digests onto a middleware seam. ✅ SHIPPED (2026-06-28).** The
  original framing ("use deepagents' `MemoryMiddleware` reading the Store") was **falsified by
  exploration**: the matter wiki can't move to the Store without a separate cross-module ADR'd slice (it
  would desync the cockpit C3-UM APIs, split the single-SQL wiki+fact-ledger+snapshot transaction, and
  weaken the `guarded_tool_call` chokepoint + structural pin-immutability), and deepagents' stock
  `MemoryMiddleware` injects generic `edit_file` self-learning guidance that conflicts with ADR-F042. So
  N1 shipped a thin **fork** `TierMemoryMiddleware` (`app/agents/tier_middleware.py`) that appends the
  four DATA tiers (House Brief, Matter File, Matter Corrections, Matter Roster) — rendered by the single
  `render_memory_tiers` source — to the system message on every model call; `system_prompt_for` stays the
  byte-identical equivalence oracle and **SQL stays the source of truth** (ADR-F042 unchanged). One
  documented, benign delta: the tiers now render AFTER deepagents' `BASE_AGENT_PROMPT`. *Gate met:
  prompt-equivalence (the four blocks render byte-identical and reach the model, proven by
  `test_tier_middleware.py` + the composition e2e tests) + full api suite 2857 passed / 38 skipped / 0
  failed + Track-A N=1 live smoke green.* The Store-vs-SQL **convergence** + the shared **Practice
  Knowledge** learning tier are registered as the prize: [ADR-F050](../../adr/F050-practice-knowledge-shared-learning.md)
  (proposed) + `plans/PRACTICE-KNOWLEDGE-prize.md`.

## Phase 1 — conversations on the native Store

- **N2 — `SummarizationMiddleware` with a `StoreBackend` offload route. ✅ SHIPPED (2026-06-29).** The
  premise was **falsified in our favour**: the offload was **already wired by N0** — `create_deep_agent`
  always installs the default `SummarizationMiddleware(model, backend)` over our `CompositeBackend`, whose
  `/conversation_history/` route maps the offload path `/conversation_history/{thread_id}.md` (from
  `artifacts_root='/'`) verbatim into the Store ns `("conversation", thread_id)`; recall is the path the
  summary embeds (builtin `read_file`). So N2 shipped as **verify + test + eval, no production code**: a
  deterministic offload drift-guard (`tests/agents/test_summarization_offload.py`: routing/artifacts_root,
  Store landing, append-on-2nd, thread isolation, read-back) + the **A6** within-chat-recall scenario (a
  per-scenario `compaction_max_input_tokens` + injected Store harness seam — both existing
  `compose_and_execute_run` params, no production change). **Live finding (ADR-F015, not a freeze;
  `docs/fork/evidence/n2-conversation-offload/`):** A6 forced a real compaction (`conversation_offloaded=
  True`, the opening turn evicted to the Store) and the agent **correctly recalled** the planted aside via
  the LLM summary (verdict PASS, `recalled_code=True`; `read_file` not needed). So native compaction
  suffices for within-chat recall when the summary preserves the detail; the explicit offload-file read and
  N3's `search_matter_conversations` are the backstop for dropped details / cross-thread. Maintainer rulings:
  plain-chat transcripts persist too (route is thread-keyed, not matter-gated); the degraded-key edge
  (checkpointer-`None` + single run over the trigger) is accepted + documented (ADR-F049 N2 addendum). Full
  api suite 2864/38/0; ruff + mypy clean; no migration, no new dependency. *Gate met.*
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
- **Slice P — PageIndex agentic-RAG EVAL SPIKE (find its fit through evals; not a skip).** PageIndex
  is reasoning/agentic RAG (LLM navigates a doc's structure tree) — *complementary* to embeddings, not
  a substitute. Run it as a **contained eval arm** (PageIndex OSS = MIT; LiteLLM pointed at our gateway
  or a local model; **does NOT ship `litellm` into the product image**) measured on the same Track-B/
  Track-A tasks, to test the hypotheses: (a) precise navigation **inside a single large, highly-
  structured document** (long agreements where chunk-embedding fragments cross-references) — compare
  recall/precision + cite-precision vs hybrid+rerank; (b) as a **selectable agentic-retrieval strategy**
  for structure-heavy queries (Track-A A7 extension); (c) **explainability** (auditable navigation path
  vs an opaque vector hit). Output: a measured map of *where PageIndex wins, at what cost* (tree-build
  ~150–260 LLM calls/doc → likely cost-bounded to high-value docs). **Adoption is a separate post-eval
  decision + its own ADR** if `litellm` (or a tree-index store) is added to the product. Sequenced
  after E0/E1 (needs the harness) and after C (so the hybrid+rerank baseline exists to compare against);
  can run independently of the substrate slices. A free chunk-derived section map remains the cheaper
  first option to compare against for use case (a).

**Dependency order:** E0 + E1 → N0 (ADR-F049) → N1, N2 → N3 | C → [Store semantic + docs dense] | A
(independent) | D / strategy-R4 / recency / MAP gated on measured need. **Slice P (PageIndex eval
spike)** after E0/E1 + C (needs the harness + a hybrid+rerank baseline to compare against); runs
independently of the substrate slices.

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
- No PageIndex *adoption* now (it IS evaluated — Slice P, a contained eval arm; it just isn't shipped
  into the product image until the eval shows where it wins + a dependency ADR is accepted).
- No a-priori eval thresholds (set X/Y after the B1 baseline, never tighter than CI).
- No CI spend on live DeepSeek (provider-marked, manual/on-demand; retriever-only + scorer units in CI).

## Open maintainer calls
1. **CUAD subset size — ✅ SETTLED (2026-06-28): 150 contracts, deterministic (sorted by id), all 41
   categories**, retriever-only for the frozen baseline (the runner is parameterised so any N can be
   re-run). The agent-mode small subset moves to **E1** with the Track-A scenarios (agent-mode recall is
   not observable from run steps; E0 stays deterministic/$0).
2. **Track-B gate thresholds X (embeddings) / Y (rerank)** — set post-baseline, never tighter than CI.
   Baseline now exists (within-doc hit@8 0.39 / cross-doc hit@8 0.04); approve the delta policy at Slice C.
3. **Track-A judge rubric strictness — ✅ SETTLED (2026-06-28, E1):** rates are recorded findings
   (ADR-F015), **pass-bars unset** this slice; per-scenario bars get set at a later gating slice against
   the frozen E1 baseline. Judge = the orchestrator (Claude) over masked packets — primary — with a
   `deepseek-pro` gateway fallback for automated runs.
4. **Eval-in-CI vs manual — ✅ SETTLED (2026-06-28):** scorer unit tests + a synthetic retriever-only
   smoke (+ the `_FTS_SQL` drift-guard) run in CI ($0, Postgres-only); the full corpus baseline is
   corpus-gated/on-demand; live agent-mode (E1) is provider-marked/CI-skipped.
5. **DeepSeek eval spend budget — ✅ SETTLED (2026-06-28, E1):** `LQ_AI_TRACK_A_N=1` smoke is the
   day-to-day default; **N≥10 only for an explicit baseline freeze**, under a per-matrix cap. Retriever-only
   (E0) stays the $0 day-to-day signal; Claude-judging is free (only the live *agent* runs spend tokens).
6. **Second model family for Track A — ✅ SETTLED (2026-06-28, E1): single DeepSeek now.** The E1 baseline
   is single-family; the agent model is already `LQ_AI_SCENARIO_MODEL`, so a 2nd family (e.g. Kimi K2.x,
   OpenAI-compatible) is a one-env-var matrix expansion in a later run.
7. **Embedding door / dim** — in-process local (Door A) vs gateway-local (Door B); 768 vs 384 vs keep
   1536. (Recommended: Door A, 768 — confirm at Slice C.)
