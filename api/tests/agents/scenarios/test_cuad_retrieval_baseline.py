"""The frozen FTS-only CUAD retrieval baseline (ADR-F049, E0).

Corpus-gated: skips unless the CUAD fixture is present (``scripts/fetch_cuad.sh``;
``LQ_AI_CUAD_DIR`` to override). Retriever-only → no gateway, $0 — but heavy
(seeds the subset, runs thousands of FTS queries), so it is run on demand in the
dev image, not in CI (CI ships no corpus → it skips). Asserts only rig hygiene
(ADR-F015); the recall/precision numbers are the recorded baseline every later
retrieval slice is gated against, frozen under
``docs/fork/evidence/retrieval-eval/baseline/``.

Run (dev image, throwaway pgvector):
    LQ_AI_CUAD_DIR=/path/to/cuad LQ_AI_CUAD_SUBSET=150 \
      pytest tests/agents/scenarios/test_cuad_retrieval_baseline.py -s
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.agents.scenarios.cuad_eval import (
    DEFAULT_SUBSET,
    load_cuad,
    resolve_cuad_dir,
    run_cuad_retrieval_baseline,
    write_baseline_report,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_EVIDENCE = _REPO_ROOT / "docs" / "fork" / "evidence" / "retrieval-eval" / "baseline"


def _git_sha() -> str:
    # In the dev image the repo root is the mount point, so git is not reachable;
    # the caller passes the host HEAD via LQ_AI_GIT_SHA to pin the frozen run.
    env_sha = os.environ.get("LQ_AI_GIT_SHA")
    if env_sha:
        return env_sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=_REPO_ROOT, text=True
        ).strip()
    except Exception:  # pragma: no cover - provenance is best-effort
        return "unknown"


async def test_freeze_fts_only_cuad_baseline(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    resolution = resolve_cuad_dir(os.environ.get("LQ_AI_CUAD_DIR"))
    if not resolution.present:
        pytest.skip(
            f"CUAD corpus not found at {resolution.path} — run scripts/fetch_cuad.sh "
            "or set LQ_AI_CUAD_DIR (corpus is CC-BY-4.0, gitignored)."
        )

    subset = int(os.environ.get("LQ_AI_CUAD_SUBSET", str(DEFAULT_SUBSET)))
    corpus = load_cuad(resolution.path, limit=subset)
    assert corpus.contracts, "loaded an empty CUAD subset"

    results = await run_cuad_retrieval_baseline(
        commit_factory,
        corpus.contracts,
        run_cross_doc=True,
        gold_span_drift=corpus.gold_span_drift,
    )

    # Rig hygiene only (ADR-F015): the run produced scored present questions.
    assert results["corpus"]["present_questions"] > 0
    assert (
        results["within_doc"]["hit_rate_at_k"][str(max(results["params"]["k_values"]))] is not None
    )

    manifest = {
        "slice": "E0",
        "git_sha": _git_sha(),
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "subset_requested": subset,
        "subset_loaded": len(corpus.contracts),
        "selection": "deterministic (contracts sorted by id, first N)",
        "dataset": "CUAD v1 (CC-BY-4.0, theatticusproject)",
    }
    out_dir = Path(os.environ.get("LQ_AI_RETRIEVAL_EVIDENCE_DIR", str(_DEFAULT_EVIDENCE)))
    json_path, md_path = write_baseline_report(results, out_dir, manifest=manifest)
    print(f"\nFrozen FTS-only baseline → {json_path}\n               summary → {md_path}")
