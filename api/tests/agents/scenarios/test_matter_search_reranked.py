"""Unit tests for ``matter_search_reranked`` — the Slice-D rerank wrapper (ADR-F049).

The wrapper fetches a WIDER hybrid candidate set then reorders it with a cross-encoder
down to ``top_k``. These tests prove the *mechanics* deterministically with a model-free
fake reranker (the real cross-encoder's precision lift is the live Track-B gate, an
ADR-F015 finding — CI proves the mechanism, the calibration proves the model). The
underlying ``matter_hybrid_search`` is covered by ``test_matter_hybrid_search.py``; this
file covers only what the rerank stage adds:

* ``reranker=None`` ⇒ **byte-identical** to ``matter_hybrid_search`` (frozen baselines hold);
* a wider fetch + reorder **promotes** a low-hybrid-rank chunk into ``top_k``;
* ≤1 candidate is a no-op (the reranker is never called);
* a reranker error or a score-count mismatch degrades to the **hybrid order**;
* the matter **scope isolation** holds on the rerank path.

All tests use the FTS-only path (``query_embedding=None``) so the candidate order is
deterministic without seeding vectors.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.tools import MatterBinding
from app.knowledge.retrieval import matter_hybrid_search, matter_search_reranked
from tests.agents.embedding_fakes import KeywordRerankProvider
from tests.agents.scenarios.harness import SeededMatter, seed_multi_doc_matter
from tests.agents.scenarios.scenarios import DocChunk, FixtureDocument


def _doc(filename: str, *chunk_texts: str) -> FixtureDocument:
    """A fixture document whose chunks are the given paragraphs (offsets exact)."""
    normalized = "\n\n".join(chunk_texts)
    chunks: list[DocChunk] = []
    cursor = 0
    for i, body in enumerate(chunk_texts):
        start = normalized.index(body, cursor)
        end = start + len(body)
        chunks.append(
            DocChunk(
                chunk_index=i,
                content=body,
                page_start=1,
                page_end=1,
                char_offset_start=start,
                char_offset_end=end,
            )
        )
        cursor = end
    return FixtureDocument(
        filename=filename, normalized_content=normalized, page_count=1, chunks=chunks
    )


def _binding(seeded: SeededMatter, name: str) -> MatterBinding:
    return MatterBinding(
        project_id=seeded.project_id,
        user_id=seeded.user_id,
        name=name,
        privileged=True,
        minimum_inference_tier=4,
        practice_area_id=seeded.practice_area_id,
    )


class _ContentMarkerRerank:
    """Scores 1.0 for the one passage equal to ``target`` else 0.0 — lets a test
    promote a specific (otherwise low-ranked) chunk deterministically."""

    name = "fake:content-marker"

    def __init__(self, target: str) -> None:
        self._target = target

    async def score(self, query: str, passages: Sequence[str]) -> list[float]:
        return [1.0 if p == self._target else 0.0 for p in passages]


async def test_none_reranker_is_byte_identical_to_hybrid(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``reranker=None`` delegates straight to ``matter_hybrid_search`` at ``top_k``."""
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[
            _doc("a.txt", "Termination for convenience on sixty days notice."),
            _doc("b.txt", "Termination for cause on a material breach of the agreement."),
        ],
        matter_name="passthrough matter",
    )
    binding = _binding(seeded, "passthrough matter")
    try:
        async with commit_factory() as db:
            common = {
                "project_id": binding.project_id,
                "user_id": binding.user_id,
                "query": "termination",
                "query_embedding": None,
                "top_k": 5,
                "alpha": 1.0,
            }
            plain = await matter_hybrid_search(db, **common)
            passthrough = await matter_search_reranked(
                db, **common, reranker=None, rerank_candidates=30
            )
            assert [(h.chunk_id, h.score) for h in passthrough] == [
                (h.chunk_id, h.score) for h in plain
            ]
    finally:
        await seeded.cleanup()


async def test_wider_fetch_and_rerank_promotes_a_low_ranked_chunk(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The wrapper fetches ``rerank_candidates`` (> top_k) then reorders: a chunk the
    narrow top-k would miss is promoted to first, and its score becomes the rerank
    score."""
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[
            _doc(
                "deed.txt",
                "The indemnity clause is set out in this section of the deed.",
                "A further indemnity clause appears in the schedule.",
                "Yet another indemnity clause covers third parties.",
                "The final indemnity clause concerns survival after termination.",
            )
        ],
        matter_name="promotion matter",
    )
    binding = _binding(seeded, "promotion matter")
    try:
        async with commit_factory() as db:
            common = {
                "project_id": binding.project_id,
                "user_id": binding.user_id,
                "query": "indemnity",
                "query_embedding": None,
                "alpha": 1.0,
            }
            ranked = await matter_hybrid_search(db, **common, top_k=10)
            assert len(ranked) == 4
            worst = ranked[-1]  # lowest hybrid rank
            top2_plain = await matter_hybrid_search(db, **common, top_k=2)
            assert worst.chunk_id not in {h.chunk_id for h in top2_plain}

            reranked = await matter_search_reranked(
                db,
                **common,
                top_k=2,
                reranker=_ContentMarkerRerank(worst.content),
                rerank_candidates=10,
            )
            assert len(reranked) == 2
            assert reranked[0].chunk_id == worst.chunk_id  # promoted last -> first
            assert reranked[0].score == 1.0  # hit.score becomes the rerank score
    finally:
        await seeded.cleanup()


async def test_single_candidate_skips_the_reranker(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """≤1 candidate returns directly — a *failing* reranker is never called."""
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[_doc("a.txt", "Only this paragraph mentions the bespoke escrow arrangement.")],
        matter_name="solo matter",
    )
    binding = _binding(seeded, "solo matter")
    try:
        async with commit_factory() as db:
            solo = await matter_search_reranked(
                db,
                project_id=binding.project_id,
                user_id=binding.user_id,
                query="escrow",
                query_embedding=None,
                top_k=8,
                alpha=1.0,
                reranker=KeywordRerankProvider(fail=True),  # would raise if called
                rerank_candidates=30,
            )
            assert len(solo) == 1
    finally:
        await seeded.cleanup()


async def test_reranker_error_falls_back_to_hybrid_order(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A reranker exception degrades to the hybrid order — retrieval never hard-fails."""
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[
            _doc(
                "deed.txt",
                "The first indemnity clause.",
                "The second indemnity clause.",
                "The third indemnity clause.",
            )
        ],
        matter_name="error-fallback matter",
    )
    binding = _binding(seeded, "error-fallback matter")
    try:
        async with commit_factory() as db:
            common = {
                "project_id": binding.project_id,
                "user_id": binding.user_id,
                "query": "indemnity",
                "query_embedding": None,
                "top_k": 3,
                "alpha": 1.0,
            }
            plain = await matter_hybrid_search(db, **common)
            fb = await matter_search_reranked(
                db, **common, reranker=KeywordRerankProvider(fail=True), rerank_candidates=30
            )
            assert [h.chunk_id for h in fb] == [h.chunk_id for h in plain]
    finally:
        await seeded.cleanup()


async def test_score_count_mismatch_falls_back_to_hybrid_order(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A reranker that returns the wrong number of scores degrades to the hybrid order."""
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[
            _doc(
                "deed.txt",
                "The first indemnity clause.",
                "The second indemnity clause.",
                "The third indemnity clause.",
            )
        ],
        matter_name="mismatch matter",
    )
    binding = _binding(seeded, "mismatch matter")
    try:
        async with commit_factory() as db:
            common = {
                "project_id": binding.project_id,
                "user_id": binding.user_id,
                "query": "indemnity",
                "query_embedding": None,
                "top_k": 3,
                "alpha": 1.0,
            }
            plain = await matter_hybrid_search(db, **common)
            fb = await matter_search_reranked(
                db, **common, reranker=KeywordRerankProvider(drop_scores=True), rerank_candidates=30
            )
            assert [h.chunk_id for h in fb] == [h.chunk_id for h in plain]
    finally:
        await seeded.cleanup()


async def test_rerank_path_preserves_matter_isolation(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A matter owner cannot reach another matter's chunks through the rerank path."""
    matter_a = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[_doc("a.txt", "The indemnity clause caps liability for matter A.")],
        matter_name="matter A",
    )
    matter_b = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[_doc("b.txt", "The indemnity clause caps liability for matter B.")],
        matter_name="matter B",
    )
    bind_a = _binding(matter_a, "matter A")
    bind_b = _binding(matter_b, "matter B")
    try:
        async with commit_factory() as db:
            cross = await matter_search_reranked(
                db,
                project_id=bind_b.project_id,
                user_id=bind_a.user_id,  # A's owner + B's project => owner re-assert
                query="indemnity",
                query_embedding=None,
                top_k=8,
                alpha=1.0,
                reranker=KeywordRerankProvider(),
                rerank_candidates=30,
            )
            assert cross == []
    finally:
        await matter_a.cleanup()
        await matter_b.cleanup()
