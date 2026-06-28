"""CI smoke for the CUAD retrieval-eval rig (ADR-F049, E0).

Synthetic 3-contract corpus — no CUAD download, no gateway, $0. Exercises the
whole Track-B path (build fixture → seed → FTS retrieve → score) end-to-end on a
real Postgres (the GENERATED ``content_tsv`` makes seeded chunks searchable on
commit, no ingest worker), and **drift-guards** the offset-projecting eval query
against the production ``app/agents/tools.py:_FTS_SQL``. Runs in CI; the full
150-contract baseline run is corpus-gated (``test_cuad_retrieval_baseline``).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.tools import _FTS_SQL, MatterBinding
from tests.agents.scenarios.cuad_eval import (
    CuadContract,
    CuadQuestion,
    cuad_contract_to_fixture,
    fts_retrieve,
    matter_document_ids,
    run_cuad_retrieval_baseline,
)
from tests.agents.scenarios.harness import seed_multi_doc_matter

_ALPHA = (
    "ALPHA DISTRIBUTION AGREEMENT\n\n"
    "1. Governing Law. This Agreement shall be governed by and construed in "
    "accordance with the laws of England and Wales, and the parties submit to the "
    "exclusive jurisdiction of the English courts.\n\n"
    "2. Term. This Agreement commences on the Effective Date and continues for an "
    "initial term of twenty-four (24) months."
)
_BETA = (
    "BETA SERVICES AGREEMENT\n\n"
    "1. Limitation of Liability. The total aggregate liability of either party "
    "under this Agreement shall be capped at the fees paid in the twelve (12) "
    "months preceding the claim.\n\n"
    "2. Confidentiality. Each party shall keep confidential the other party's "
    "confidential information."
)
_GAMMA = (
    "GAMMA LICENSE AGREEMENT\n\n"
    "1. License Grant. Licensor grants Licensee a non-exclusive license to use "
    "the Software.\n\n"
    "2. Termination. Either party may terminate this Agreement for convenience on "
    "sixty (60) days written notice."
)


def _span(context: str, clause: str) -> tuple[int, int]:
    start = context.index(clause)
    return (start, start + len(clause))


def _synthetic_contracts() -> list[CuadContract]:
    gov = "This Agreement shall be governed by and construed in accordance with the laws of England and Wales"
    cap = "The total aggregate liability of either party under this Agreement shall be capped"
    term = "Either party may terminate this Agreement for convenience on sixty (60) days written notice"
    return [
        CuadContract(
            contract_id="Alpha Distribution Agreement",
            context=_ALPHA,
            questions=[
                CuadQuestion(
                    "Alpha Distribution Agreement",
                    "Governing Law",
                    "q",
                    False,
                    [_span(_ALPHA, gov)],
                ),
                CuadQuestion("Alpha Distribution Agreement", "Cap On Liability", "q", True, []),
            ],
        ),
        CuadContract(
            contract_id="Beta Services Agreement",
            context=_BETA,
            questions=[
                CuadQuestion(
                    "Beta Services Agreement", "Cap On Liability", "q", False, [_span(_BETA, cap)]
                ),
                CuadQuestion("Beta Services Agreement", "Governing Law", "q", True, []),
            ],
        ),
        CuadContract(
            contract_id="Gamma License Agreement",
            context=_GAMMA,
            questions=[
                CuadQuestion(
                    "Gamma License Agreement",
                    "Termination For Convenience",
                    "q",
                    False,
                    [_span(_GAMMA, term)],
                ),
            ],
        ),
    ]


async def test_cuad_baseline_smoke(commit_factory: async_sessionmaker[AsyncSession]) -> None:
    results = await run_cuad_retrieval_baseline(
        commit_factory, _synthetic_contracts(), run_cross_doc=True
    )

    assert results["corpus"]["contracts"] == 3
    assert results["corpus"]["present_questions"] == 3
    assert results["corpus"]["absent_questions"] == 2

    within = results["within_doc"]
    # Each clause sits in its contract's single chunk → found at rank 1.
    assert within["recall_at_k"]["1"] == 1.0
    assert within["hit_rate_at_k"]["8"] == 1.0
    assert within["mean_average_precision"] == 1.0

    cross = results["cross_doc"]
    assert cross is not None
    # Each category's keywords appear in exactly one contract → the right
    # document surfaces in a matter-wide search too.
    assert cross["hit_rate_at_k"]["8"] == 1.0

    # The absent clauses' keywords appear in no other part of their own doc.
    assert results["absent_control"]["within_doc_spurious_retrieval_rate"] == 0.0
    # Per-category breakdown present and scored.
    assert set(results["per_category_within_doc"]) == {
        "Governing Law",
        "Cap On Liability",
        "Termination For Convenience",
    }


async def test_eval_query_matches_production_fts(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Drift guard: the offset-projecting eval query must rank/scope identically
    to the production matter retriever (``_FTS_SQL``)."""
    contracts = _synthetic_contracts()
    fixtures = [cuad_contract_to_fixture(c, index=i) for i, c in enumerate(contracts)]
    seeded = await seed_multi_doc_matter(
        commit_factory, area_key="commercial", docs=fixtures, matter_name="CUAD drift-guard"
    )
    binding = MatterBinding(
        project_id=seeded.project_id,
        user_id=seeded.user_id,
        name="CUAD drift-guard",
        privileged=True,
        minimum_inference_tier=4,
        practice_area_id=seeded.practice_area_id,
    )
    try:
        async with commit_factory() as db:
            # The mapping query returns one document per seeded contract.
            assert len(await matter_document_ids(db, binding)) == 3

            for query in ("Governing Law", "Cap On Liability", "Termination For Convenience"):
                prod_rows = (
                    await db.execute(
                        _FTS_SQL,
                        {
                            "q": query,
                            "pid": str(binding.project_id),
                            "uid": str(binding.user_id),
                            "lim": 8,
                        },
                    )
                ).all()
                prod = [(r.filename, round(float(r.rank), 6)) for r in prod_rows]

                eval_rows = await fts_retrieve(db, binding, query, k=8)
                got = [(c.filename, round(c.rank, 6)) for c in eval_rows]

                assert got == prod, f"eval query drifted from _FTS_SQL for {query!r}"
                assert prod, f"expected a production FTS match for {query!r}"
                # Offsets are recoverable (the whole point of the parallel query).
                assert all(isinstance(c.document_id, uuid.UUID) for c in eval_rows)
                assert all(c.char_offset_end > c.char_offset_start for c in eval_rows)
    finally:
        await seeded.cleanup()
