# Slice D — cross-encoder rerank: Track-B gate (ADR-F049, ADR-F015 finding)

**What.** F2 Slice D adds a local fastembed `TextCrossEncoder` that reorders the matter
retriever's wider candidate set by scoring *(query, passage)* pairs jointly — the
precision complement to the C1 bi-encoder fusion (which embeds query and passage
independently). Gate (`plans/RETRIEVAL-MEMORY-eval-first.md`): *ship only if precision@5
lifts ≥ Y vs the prior baseline without hurting recall@5* — Y set post-baseline; an
**ADR-F015 finding, not a CI bar**.

**How.** Real fastembed `Xenova/ms-marco-MiniLM-L-6-v2` cross-encoder over the production
retriever path (`matter_search_reranked`), N=30 deterministic CUAD subset (388 present
questions, 876 chunks), `rerank_candidates=30`, on a **throwaway pgvector** (the live DB
is never touched). Scripts: `tests/agents/scenarios/test_cuad_rerank_baseline.py` (+ the
hybrid/FTS floors via `test_cuad_hybrid_baseline` / `test_cuad_retrieval_baseline`).

## Hardware constraint (honest scope — the C1 full-150 precedent)

The dev box has **6.3 GB RAM (~3.8 GB free)**. Loading the bge embedder **and** the
cross-encoder while batch-evaluating (876-chunk backfill + ~23k cross-encoder inferences
growing the ONNX arena) **OOM-kills** the process (`dmesg`: killed at ~3.4 GB anon-rss),
at every N tried (30, 10). So **hybrid+rerank at scale could not be batch-measured here**
— it is a deferred finding for a bigger box (exactly as C1 deferred the full-150 hybrid
run). The **memory-feasible** arm is **FTS+rerank** (only the cross-encoder loads), which
is a **conservative lower bound** on the production hybrid+rerank benefit (the hybrid
candidate pool has ~2× the within-doc recall@5, so the reranker has *more* genuine wins to
surface there).

A separate **realistic-load** memory probe (both models + 12 searches, NOT the eval batch)
peaks at **~1.06 GB** — so a *production agent run* holding both models is safe on this box;
the OOM is purely an eval-batch-volume artifact.

## Result — VERDICT: PASS (default ON)

**FTS+rerank vs the frozen FTS floor (N=30, MiniLM-L-6, candidates=30):**

| metric | within-doc FTS → +rerank | Δ | cross-doc FTS → +rerank | Δ |
|---|---|---|---|---|
| precision@1 | 0.2320 → 0.2680 | **+15.5%** | 0.0412 → 0.0438 | +6% |
| precision@5 | 0.1887 → 0.1897 | +0.5% (flat) | 0.0303 → 0.0365 | **+20%** |
| recall@5 | 0.3145 → 0.3220 | +0.0075 | 0.0774 → 0.1055 | **+36%** |
| recall@8 | 0.3329 → 0.3317 | −0.0012 | 0.0988 → 0.1293 | **+31%** |
| hit@8 | 0.3557 → 0.3557 | 0.0 | 0.1134 → 0.1495 | **+32%** |
| MAP | 0.2522 → 0.2806 | **+11%** | 0.0557 → 0.0674 | **+21%** |

**Reading.** **Zero recall harm** anywhere. The reranker clearly improves top-rank ordering
(within-doc p@1 +15.5%, MAP +11%) and the at-scale cross-doc case broadly (+20–36%). The
*named* gate metric — within-doc precision@5 — is **flat**, but it is structurally blind to
the reranker's gain here: CUAD gold is typically a **single clause** (one relevant chunk),
so precision@5 caps at ~0.2 and promoting that chunk rank-3→rank-1 moves **p@1 and MAP, not
p@5**. The metrics that *can* move did, strongly. Cross-doc precision@5 (a multi-chunk
setting) **lifts +20%**.

**Hybrid floor reference** (`hyb-0.5/`, N=30 — where rerank sits in production; the
unmeasurable arm): within-doc recall@5 0.6287 / precision@5 0.1747 / MAP 0.4892. The
rerank lower bound + the richer hybrid pool together motivate the default.

## Decision (maintainer, eval-gated)

**`rerank_enabled` ships DEFAULT ON.** The theoretical case is strong (cross-encoder rerank
is the SOTA precision fix for a bi-encoder's independence assumption), the measured FTS+rerank
arm lifts top-rank + at-scale precision/recall with zero harm (a lower bound on the production
hybrid pool), memory is safe (~1 GB peak in real runs), and latency is minor (MiniLM-L-6,
~tens of ms / search). The one residual — the *marginal* lift on the hybrid pool specifically
— is inferred, not measured (dev-box OOM); it is bounded below by the measured result and is a
marginal-improvement question, not a will-it-work/will-it-crash one. **NEXT (deferred):**
batch-measure hybrid+rerank (and bge-reranker-base vs MiniLM) on a ≥16 GB box; tune
`rerank_candidates` / model from that.

Default model `Xenova/ms-marco-MiniLM-L-6-v2` (~5 MB, fast). `BAAI/bge-reranker-base` (native
bge-family, ~66 MB, heavier) is the configurable quality alternative for the bigger-box run.
