# Retrieval eval — evidence (F2, ADR-F049)

Frozen artefacts for the eval-first retrieval/memory build. Every later slice
(local embeddings, hybrid wiring, rerank, PageIndex) must beat a **pre-registered
delta vs the baseline here** to ship. Metrics are recorded findings, not pass/fail
gates on model/FTS quality (ADR-F015).

Plan: [`../../plans/RETRIEVAL-MEMORY-eval-first.md`](../../plans/RETRIEVAL-MEMORY-eval-first.md) ·
Decision: [`../../../adr/F049-native-memory-substrate-and-eval-gated-retrieval.md`](../../../adr/F049-native-memory-substrate-and-eval-gated-retrieval.md)

## `baseline/` — the FTS-only floor (slice E0, Track B / CUAD-gold)

The objective instrument: 150 CUAD contracts (CC-BY-4.0, deterministic subset
sorted by id) seeded as matter documents through the **production chunker**, then
the **production matter FTS retriever** (`websearch_to_tsquery('english')` +
`ts_rank_cd`, embeddings NULL) run over the 41 clause-category questions and
scored against CUAD's human `answer_start` gold spans. Retriever-only → **no
gateway, $0**. Full table in [`baseline/baseline.md`](baseline/baseline.md); raw
data in `baseline/baseline.json`.

### Headline (the eval-first payoff)

| arm | hit@8 | recall@8 | MAP |
|---|---|---|---|
| **within-doc** (right contract known) | 0.39 | 0.37 | 0.30 |
| **cross-doc** (matter-wide, 150 docs) | 0.04 | 0.04 | 0.02 |

Two findings that set the agenda for the rest of F2:

1. **Lexical FTS is weak even within the right document** (~37% of clauses found
   at the production top-k=8). It only works when the clause *category label is
   the in-text wording* — Insurance 0.99, Governing Law 0.91, Exclusivity 0.85 —
   and is **0.00** for semantically-named clauses whose label is not the contract
   text: Anti-Assignment, Revenue/Profit Sharing, Rofr/Rofo/Rofn, Uncapped
   Liability, Volume Restriction, No-Solicit. This is exactly the gap dense
   embeddings are meant to close.
2. **At matter scale, FTS essentially collapses** (cross-doc hit@8 ≈ 0.04): the
   right clause almost never surfaces from the right document among 150. This
   quantifies the "1000-document" problem the F2 milestone exists to solve, and
   shows the headroom embeddings / rerank / PageIndex have to earn.

### Method notes (so later slices compare apples to apples)

- **Query** = the clause category name (the realistic clause-type search intent),
  not the verbose CUAD question template.
- **Hit/recall/MAP** are gold-span-level (a gold covered by overlapping chunks
  counts once); **precision@k** is the per-retrieved-item rate. Definitions live
  in `api/tests/agents/scenarios/retrieval_metrics.py` (pure, CI-unit-tested).
- The eval retriever mirrors `app/agents/tools.py:_FTS_SQL` ranking/scoping
  exactly but also projects char offsets; `test_cuad_retrieval_smoke` drift-guards
  the two.
- **Absent clauses** (4066 of 6150 questions) are scored by an abstention/
  spurious-retrieval control, not recall — true abstention is an agent-mode/QA
  property deferred to E1.

### Reproduce

```bash
# 1. fetch the corpus (CC-BY-4.0, gitignored; ~18 MB download -> 39 MB JSON)
scripts/fetch_cuad.sh

# 2. run the baseline in the dev image (retriever-only, $0; ~50s for 150 contracts)
#    test_engine creates its own lq_ai_test_* DB -- never the live dev DB.
docker run --rm --network lq-ai_default \
  -e DATABASE_URL="postgresql+asyncpg://lq_ai:$POSTGRES_PASSWORD@postgres:5432/lq_ai" \
  -e LQ_AI_CUAD_DIR=/app/tests/fixtures/cuad \
  -e LQ_AI_CUAD_SUBSET=150 \
  -e LQ_AI_RETRIEVAL_EVIDENCE_DIR=/repo/docs/fork/evidence/retrieval-eval/baseline \
  -e LQ_AI_GIT_SHA="$(git rev-parse --short HEAD)" \
  -v "$PWD":/repo -v "$PWD/api":/app -v "$PWD/skills":/skills:ro \
  -w /app lq-ai-api-dev \
  bash -lc "python -m pytest tests/agents/scenarios/test_cuad_retrieval_baseline.py -s -q"
# (chown the written evidence back to your host user afterwards — the container runs as root)
```

The CI smoke (`test_cuad_retrieval_smoke`, synthetic 3-contract corpus, no
corpus download) + the pure scorer unit tests (`test_retrieval_metrics`) run in
CI for free; the full 150-contract baseline is corpus-gated and run on demand.
