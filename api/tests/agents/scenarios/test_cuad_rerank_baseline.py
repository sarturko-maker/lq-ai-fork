"""The Slice D rerank CUAD baseline — measures the cross-encoder delta (ADR-F049).

Corpus-gated (skips without the CUAD fixture; ``LQ_AI_CUAD_DIR`` to override). Runs the
SAME ``run_cuad_retrieval_baseline`` as the hybrid floor (``test_cuad_hybrid_baseline``,
``docs/fork/evidence/retrieval-eval-slice-c``) but adds a real cross-encoder
``RerankProvider`` so the wider hybrid candidate set is reordered before truncation —
so the result is directly comparable to the hybrid baseline at the same N/alpha. The
Slice D gate is *precision@5 lifts ≥ Y vs hybrid without hurting recall@5* (Y set
post-baseline; an ADR-F015 finding, not a CI bar). Retriever-only → no chat tokens; the
local reranker needs no gateway (Door A is $0).

Run ALONE in the dev image (real embedder + real cross-encoder + heavy PG crash the
dev box — never concurrent with the full suite), throwaway pgvector:

    LQ_AI_CUAD_DIR=/app/tests/fixtures/cuad LQ_AI_CUAD_SUBSET=30 \\
    LQ_AI_RERANK_MODEL=Xenova/ms-marco-MiniLM-L-6-v2 LQ_AI_RERANK_CANDIDATES=30 \\
    LQ_AI_RETRIEVAL_EVIDENCE_DIR=/evidence \\
      pytest tests/agents/scenarios/test_cuad_rerank_baseline.py -s
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.knowledge.embedding_provider import build_embedding_provider
from app.knowledge.rerank_provider import build_rerank_provider
from tests.agents.scenarios.cuad_eval import (
    load_cuad,
    resolve_cuad_dir,
    run_cuad_retrieval_baseline,
    write_baseline_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_EVIDENCE = _REPO_ROOT / "docs" / "fork" / "evidence" / "retrieval-eval-slice-d"


async def test_rerank_cuad_baseline(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    resolution = resolve_cuad_dir(os.environ.get("LQ_AI_CUAD_DIR"))
    if not resolution.present:
        pytest.skip(
            f"CUAD corpus not found at {resolution.path} — run scripts/fetch_cuad.sh "
            "or set LQ_AI_CUAD_DIR (corpus is CC-BY-4.0, gitignored)."
        )

    # N=30 default (real models + eval volume crash the dev box at N>=60 — Slice C1).
    subset = int(os.environ.get("LQ_AI_CUAD_SUBSET", "30"))
    alpha = float(os.environ.get("LQ_AI_HYBRID_ALPHA", "0.5"))
    rerank_candidates = int(os.environ.get("LQ_AI_RERANK_CANDIDATES", "30"))
    rerank_model = os.environ.get("LQ_AI_RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
    # Candidate base: "hybrid" (rerank the FTS+vector set — the production path) or "fts"
    # (rerank FTS candidates only, no embedder). The dev box (6.3 GB) OOMs loading the bge
    # embedder AND the cross-encoder at once, so "fts" is the memory-feasible arm here;
    # hybrid+rerank at scale is deferred to a bigger box (the C1 full-150 precedent).
    base = os.environ.get("LQ_AI_RERANK_BASE", "hybrid")
    embedder = (
        None if base == "fts" else build_embedding_provider(Settings(embedding_provider="local"))
    )
    reranker = build_rerank_provider(Settings(rerank_model=rerank_model))

    corpus = load_cuad(resolution.path, limit=subset)
    assert corpus.contracts, "loaded an empty CUAD subset"

    results = await run_cuad_retrieval_baseline(
        commit_factory,
        corpus.contracts,
        run_cross_doc=True,
        gold_span_drift=corpus.gold_span_drift,
        query_embedder=embedder,
        alpha=alpha,
        reranker=reranker,
        rerank_candidates=rerank_candidates,
        matter_name="CUAD rerank-eval corpus",
    )

    # Rig hygiene only (ADR-F015): the rerank run produced scored present questions.
    assert results["corpus"]["present_questions"] > 0
    assert (
        results["within_doc"]["hit_rate_at_k"][str(max(results["params"]["k_values"]))] is not None
    )
    assert results["params"]["reranker"] == reranker.name
    assert results["params"]["rerank_candidates"] == rerank_candidates

    manifest = {
        "slice": "D",
        "git_sha": os.environ.get("LQ_AI_GIT_SHA", "unknown"),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "subset_requested": subset,
        "subset_loaded": len(corpus.contracts),
        "candidate_base": base,
        "embedder": embedder.name if embedder is not None else None,
        "reranker": reranker.name,
        "alpha": alpha if embedder is not None else None,
        "rerank_candidates": rerank_candidates,
        "selection": "deterministic (contracts sorted by id, first N)",
        "dataset": "CUAD v1 (CC-BY-4.0, theatticusproject)",
    }
    slug = rerank_model.split("/")[-1].lower()
    out_dir = (
        Path(os.environ.get("LQ_AI_RETRIEVAL_EVIDENCE_DIR", str(_DEFAULT_EVIDENCE)))
        / f"rerank-{slug}-{base}"
    )
    json_path, md_path = write_baseline_report(results, out_dir, manifest=manifest)
    print(
        f"\nRerank Slice-D baseline ({reranker.name}) → {json_path}\n"
        f"               summary → {md_path}"
    )
