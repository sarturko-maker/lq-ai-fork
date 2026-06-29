"""The Slice C1 hybrid CUAD baseline — measures the local-embedder delta (ADR-F049).

Corpus-gated (skips without the CUAD fixture; ``LQ_AI_CUAD_DIR`` to override). Runs
the SAME ``run_cuad_retrieval_baseline`` as the frozen FTS floor but with a real
``EmbeddingProvider`` so the chunks are backfilled into ``embedding_local`` and each
clause query is embedded + fused at ``alpha`` — the result is directly comparable to
``docs/fork/evidence/retrieval-eval/baseline/`` (the E0 FTS floor). Retriever-only →
no chat tokens; the local door needs no gateway (Door A is $0). Per ADR-F015 the
numbers are recorded findings; this test asserts only rig hygiene.

Run (dev image, throwaway pgvector; local door is the default):
    LQ_AI_CUAD_DIR=/app/tests/fixtures/cuad LQ_AI_CUAD_SUBSET=150 \\
    LQ_AI_HYBRID_ALPHA=0.5 LQ_AI_RETRIEVAL_EVIDENCE_DIR=/evidence \\
      pytest tests/agents/scenarios/test_cuad_hybrid_baseline.py -s
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.knowledge.embedding_provider import build_embedding_provider
from tests.agents.scenarios.cuad_eval import (
    DEFAULT_SUBSET,
    load_cuad,
    resolve_cuad_dir,
    run_cuad_retrieval_baseline,
    write_baseline_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_EVIDENCE = _REPO_ROOT / "docs" / "fork" / "evidence" / "retrieval-eval-slice-c"


async def test_hybrid_cuad_baseline(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    resolution = resolve_cuad_dir(os.environ.get("LQ_AI_CUAD_DIR"))
    if not resolution.present:
        pytest.skip(
            f"CUAD corpus not found at {resolution.path} — run scripts/fetch_cuad.sh "
            "or set LQ_AI_CUAD_DIR (corpus is CC-BY-4.0, gitignored)."
        )

    subset = int(os.environ.get("LQ_AI_CUAD_SUBSET", str(DEFAULT_SUBSET)))
    alpha = float(os.environ.get("LQ_AI_HYBRID_ALPHA", "0.5"))
    # Default to the local door (in-process, $0). Override to "gateway" to measure
    # Door B (needs a live gateway embedding model).
    provider_name = os.environ.get("LQ_AI_EMBEDDING_PROVIDER", "local")
    provider = build_embedding_provider(
        Settings(embedding_provider=provider_name)  # type: ignore[arg-type]
    )

    corpus = load_cuad(resolution.path, limit=subset)
    assert corpus.contracts, "loaded an empty CUAD subset"

    results = await run_cuad_retrieval_baseline(
        commit_factory,
        corpus.contracts,
        run_cross_doc=True,
        gold_span_drift=corpus.gold_span_drift,
        query_embedder=provider,
        alpha=alpha,
        matter_name="CUAD hybrid-eval corpus",
    )

    # Rig hygiene only (ADR-F015): the hybrid run produced scored present questions.
    assert results["corpus"]["present_questions"] > 0
    assert (
        results["within_doc"]["hit_rate_at_k"][str(max(results["params"]["k_values"]))] is not None
    )
    assert results["params"]["alpha"] == alpha
    assert results["params"]["embedder"] == provider.name

    manifest = {
        "slice": "C1",
        "git_sha": os.environ.get("LQ_AI_GIT_SHA", "unknown"),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "subset_requested": subset,
        "subset_loaded": len(corpus.contracts),
        "embedder": provider.name,
        "alpha": alpha,
        "selection": "deterministic (contracts sorted by id, first N)",
        "dataset": "CUAD v1 (CC-BY-4.0, theatticusproject)",
    }
    out_dir = Path(os.environ.get("LQ_AI_RETRIEVAL_EVIDENCE_DIR", str(_DEFAULT_EVIDENCE)))
    json_path, md_path = write_baseline_report(results, out_dir, manifest=manifest)
    print(f"\nHybrid Slice-C baseline → {json_path}\n               summary → {md_path}")
