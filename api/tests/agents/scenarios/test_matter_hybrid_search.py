"""Unit tests for ``matter_hybrid_search`` — the one matter retriever (Slice A).

The FTS-only fast path (the production behaviour today) is locked elsewhere:
``test_matter_retriever_fts_only_matches_frozen_reference`` (in
``test_cuad_retrieval_smoke.py``) pins it against a frozen reference query, and
the ``test_search_*`` tests in ``test_agent_tools.py`` exercise it through the
``search_documents`` tool. This file covers what Slice A *adds*:

* the **document_id** narrowing (the eval's within-doc arm; ``None`` => whole
  matter);
* function-level **scope isolation** (a matter can only reach its own chunks);
* the **hybrid fusion branch** — dormant in production (no embedder is wired, so
  the tool always passes ``query_embedding=None``) but lit up by Slice C. We
  seed synthetic 1536-dim vectors directly onto the chunk column and prove the
  vector side ranks, that ``alpha>=1`` / ``embedding=None`` ignore it, and that a
  middling ``alpha`` merges both sides. This de-risks Slice C: only the embedder
  + the ``alpha`` get added there, the fusion is already proven.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.tools import MatterBinding
from app.knowledge.retrieval import matter_hybrid_search
from app.models.document import Document, DocumentChunk
from app.models.file import File
from tests.agents.scenarios.harness import SeededMatter, seed_multi_doc_matter
from tests.agents.scenarios.scenarios import DocChunk, FixtureDocument

_EMB_DIM = 1536  # the current chunk vector column dim (mig 0005); Slice C ALTERs it.


def _unit_vector(hot_index: int) -> list[float]:
    """A 1536-dim unit vector with a single 1.0 — orthogonal across indices."""
    vec = [0.0] * _EMB_DIM
    vec[hot_index] = 1.0
    return vec


def _pgvector_text(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in vec) + "]"


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


async def _chunk_ids_by_index(
    db: AsyncSession, project_id: uuid.UUID
) -> list[tuple[uuid.UUID, str]]:
    """(chunk_id, content) for one matter's chunks, ordered by chunk_index."""
    rows = (
        await db.execute(
            select(DocumentChunk.id, DocumentChunk.content)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(File, File.id == Document.file_id)
            .where(File.project_id == project_id)
            .order_by(DocumentChunk.chunk_index)
        )
    ).all()
    return [(r.id, r.content) for r in rows]


async def _set_embedding(db: AsyncSession, chunk_id: uuid.UUID, vec: list[float]) -> None:
    await db.execute(
        text("UPDATE document_chunks SET embedding = CAST(:v AS vector) WHERE id = :id"),
        {"v": _pgvector_text(vec), "id": str(chunk_id)},
    )


# ---------------------------------------------------------------------------
# document_id narrowing
# ---------------------------------------------------------------------------


async def test_document_id_narrows_to_one_document(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``document_id=None`` searches the whole matter; a value narrows to one doc."""
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[
            _doc("deed-a.txt", "Termination for convenience on sixty days notice."),
            _doc("deed-b.txt", "Termination for cause on material breach."),
        ],
        matter_name="doc-filter matter",
    )
    binding = _binding(seeded, "doc-filter matter")
    try:
        async with commit_factory() as db:
            whole = await matter_hybrid_search(
                db,
                project_id=binding.project_id,
                user_id=binding.user_id,
                query="termination",
                query_embedding=None,
                top_k=8,
                alpha=1.0,
            )
            assert {h.file_name for h in whole} == {"deed-a.txt", "deed-b.txt"}

            doc_a = next(h.document_id for h in whole if h.file_name == "deed-a.txt")
            narrowed = await matter_hybrid_search(
                db,
                project_id=binding.project_id,
                user_id=binding.user_id,
                query="termination",
                query_embedding=None,
                top_k=8,
                alpha=1.0,
                document_id=doc_a,
            )
            assert {h.file_name for h in narrowed} == {"deed-a.txt"}
    finally:
        await seeded.cleanup()


# ---------------------------------------------------------------------------
# scope isolation (the matter security boundary)
# ---------------------------------------------------------------------------


async def test_search_is_isolated_to_its_own_matter(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A shared keyword in two different matters never crosses between them."""
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
            a_hits = await matter_hybrid_search(
                db,
                project_id=bind_a.project_id,
                user_id=bind_a.user_id,
                query="indemnity",
                query_embedding=None,
                top_k=8,
                alpha=1.0,
            )
            assert {h.file_name for h in a_hits} == {"a.txt"}

            # Matter A's owner cannot reach matter B's project even by passing
            # B's project_id with A's user_id (owner re-assert) — and vice versa.
            cross = await matter_hybrid_search(
                db,
                project_id=bind_b.project_id,
                user_id=bind_a.user_id,
                query="indemnity",
                query_embedding=None,
                top_k=8,
                alpha=1.0,
            )
            assert cross == []
    finally:
        await matter_a.cleanup()
        await matter_b.cleanup()


# ---------------------------------------------------------------------------
# hybrid fusion branch (dormant in prod; lit by Slice C)
# ---------------------------------------------------------------------------


async def test_fusion_branch_uses_vectors_only_when_asked(
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """With synthetic vectors seeded: ``embedding=None``/``alpha>=1`` stay FTS-only;
    ``alpha=0`` ranks by vector; a middling ``alpha`` merges both sides."""
    gov = "Governing law and the exclusive jurisdiction of the English courts."
    conf = "Each party shall keep the other's confidential information secret."
    seeded = await seed_multi_doc_matter(
        commit_factory,
        area_key="commercial",
        docs=[_doc("agreement.txt", gov, conf)],
        matter_name="fusion matter",
    )
    binding = _binding(seeded, "fusion matter")
    try:
        async with commit_factory() as db:
            chunks = await _chunk_ids_by_index(db, binding.project_id)
            assert len(chunks) == 2
            (gov_id, gov_text), (conf_id, conf_text) = chunks
            assert "Governing" in gov_text and "confidential" in conf_text
            # Orthogonal unit vectors; the query points at the governing-law chunk.
            await _set_embedding(db, gov_id, _unit_vector(0))
            await _set_embedding(db, conf_id, _unit_vector(1))
            await db.commit()
            q_at_gov = _unit_vector(0)

            async def _search(*, query_embedding: list[float] | None, alpha: float) -> list[str]:
                hits = await matter_hybrid_search(
                    db,
                    project_id=binding.project_id,
                    user_id=binding.user_id,
                    query="confidential",  # lexically matches ONLY the conf chunk
                    query_embedding=query_embedding,
                    top_k=8,
                    alpha=alpha,
                )
                return [h.content for h in hits]

            # FTS-only (no embedder): only the lexical match surfaces.
            fts_none = await _search(query_embedding=None, alpha=1.0)
            assert fts_none == [conf]

            # alpha>=1 ignores the vector even when one is supplied.
            fts_alpha1 = await _search(query_embedding=q_at_gov, alpha=1.0)
            assert fts_alpha1 == [conf]

            # Vector-only: ranks by cosine — the governing-law chunk (query's
            # target) comes first, and the non-lexical chunk is reachable.
            vec_only = await _search(query_embedding=q_at_gov, alpha=0.0)
            assert vec_only[0] == gov
            assert set(vec_only) == {gov, conf}

            # Fusion merges the FTS hit (conf) with the vector hit (gov).
            fused = await _search(query_embedding=q_at_gov, alpha=0.5)
            assert set(fused) == {gov, conf}
    finally:
        await seeded.cleanup()
