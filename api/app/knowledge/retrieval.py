"""Hybrid (vector + FTS) retrieval over KB chunks (Task C6 / ADR 0008).

Per ADR 0008 §"Hybrid score combination":

1. Run pgvector cosine search: ``ORDER BY embedding <=> :q`` with a
   per-query limit of ``top_k * 4`` to give the rerank room to work.
2. Run Postgres FTS: ``ORDER BY ts_rank_cd(content_tsv, plainto_tsquery
   (:q)) DESC`` with the same overshoot.
3. Min-max normalize each side's scores across the union.
4. ``score = (1 - alpha) * vector + alpha * fts``.
5. Return top-``k`` by combined score.

The candidate set is filtered to chunks whose owning file is attached
to the KB AND whose ``ingestion_status='ready'`` AND whose file isn't
soft-deleted. Per-user isolation is enforced upstream by the handler
(the KB owner is the only caller; the handler verified ownership).

This module also hosts the **matter-scoped** sibling
:func:`matter_hybrid_search` (F2 Slice A, ADR-F049) — same fusion
machinery, a different (matter, not KB) scope, and ``websearch_to_tsquery``
on the FTS side. The agent's ``search_documents`` tool and the Track-B
retrieval eval both route through it, so there is exactly one matter
retriever (see its scope note — the KB and matter scopes diverge on
purpose and must not converge).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.knowledge.rerank_provider import RerankProvider

log = logging.getLogger(__name__)


CANDIDATE_OVERSHOOT: int = 4
"""Multiplier on top_k for the pre-merge candidate window.

Per ADR 0008 we overshoot 4x on each side to give the score
combination room to rerank. Smaller multipliers risk losing the
right chunk to a single-side artifact; larger multipliers cost more
DB work without measurable recall improvement at M1 scale.
"""


@dataclass(slots=True)
class HybridSearchResult:
    """One ranked chunk in a hybrid-search result.

    Field shapes mirror :class:`app.schemas.knowledge.SearchResult` so
    the handler can convert verbatim. ``vector_score`` and ``fts_score``
    are the *normalized* (post min-max) values; the raw scores are not
    surfaced to clients (they're not interpretable across queries).
    """

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    file_id: uuid.UUID
    file_name: str
    content: str
    page_start: int | None
    page_end: int | None
    char_offset_start: int
    char_offset_end: int
    vector_score: float
    fts_score: float
    hybrid_score: float


# ---------------------------------------------------------------------------
# Hybrid search entry point
# ---------------------------------------------------------------------------


async def hybrid_search(
    db: AsyncSession,
    *,
    kb_id: uuid.UUID,
    query: str,
    query_embedding: list[float] | None,
    top_k: int,
    alpha: float,
) -> list[HybridSearchResult]:
    """Run hybrid search against KB ``kb_id`` for ``query``.

    Args:
        db: Active :class:`AsyncSession`.
        kb_id: The :class:`KnowledgeBase` id to query.
        query: User's plain-text query — passed verbatim to FTS via
            :func:`plainto_tsquery`. The embedding for this same string
            is computed by the handler before calling here.
        query_embedding: 1536-dim vector or ``None``. When ``None``,
            we skip the vector side entirely and run FTS-only — used
            when embed-on-read fails or ``alpha=1``.
        top_k: Final result count after combining.
        alpha: Mixing weight in [0, 1]. 0 => vector-only; 1 => FTS-
            only. Out-of-bound values are clamped (the API layer
            already validates).

    Returns:
        List of up to ``top_k`` :class:`HybridSearchResult`, ordered by
        descending ``hybrid_score``.
    """

    alpha = max(0.0, min(1.0, alpha))
    candidate_limit = top_k * CANDIDATE_OVERSHOOT

    # --- Vector side ------------------------------------------------------
    vector_rows: list[tuple[uuid.UUID, float]] = []
    if query_embedding is not None and alpha < 1.0:
        vector_rows = await _vector_candidates(
            db,
            kb_id=kb_id,
            query_embedding=query_embedding,
            limit=candidate_limit,
        )

    # --- FTS side ---------------------------------------------------------
    fts_rows: list[tuple[uuid.UUID, float]] = []
    if alpha > 0.0:
        fts_rows = await _fts_candidates(
            db,
            kb_id=kb_id,
            query=query,
            limit=candidate_limit,
        )

    if not vector_rows and not fts_rows:
        return []

    # --- Combine ----------------------------------------------------------
    candidate_ids: set[uuid.UUID] = set()
    candidate_ids.update(cid for cid, _ in vector_rows)
    candidate_ids.update(cid for cid, _ in fts_rows)

    vector_lookup = dict(vector_rows)
    fts_lookup = dict(fts_rows)

    vector_norm = _min_max_normalize(vector_lookup)
    fts_norm = _min_max_normalize(fts_lookup)

    combined: list[tuple[uuid.UUID, float, float, float]] = []
    for cid in candidate_ids:
        v_score = vector_norm.get(cid, 0.0)
        f_score = fts_norm.get(cid, 0.0)
        hybrid = (1.0 - alpha) * v_score + alpha * f_score
        combined.append((cid, v_score, f_score, hybrid))

    combined.sort(key=lambda row: row[3], reverse=True)
    top = combined[:top_k]

    if not top:
        return []

    # --- Hydrate ----------------------------------------------------------
    score_map = {cid: (v, f, h) for cid, v, f, h in top}
    rows = await _hydrate_chunks(db, [cid for cid, _, _, _ in top])

    results: list[HybridSearchResult] = []
    for row in rows:
        cid = row["chunk_id"]
        scores = score_map.get(cid)
        if scores is None:
            continue
        v_score, f_score, hybrid_score = scores
        results.append(
            HybridSearchResult(
                chunk_id=cid,
                document_id=row["document_id"],
                file_id=row["file_id"],
                file_name=row["file_name"],
                content=row["content"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                char_offset_start=row["char_offset_start"],
                char_offset_end=row["char_offset_end"],
                vector_score=v_score,
                fts_score=f_score,
                hybrid_score=hybrid_score,
            )
        )
    # Re-sort because _hydrate_chunks doesn't preserve order.
    results.sort(key=lambda r: r.hybrid_score, reverse=True)
    return results


# ---------------------------------------------------------------------------
# Side queries
# ---------------------------------------------------------------------------


_VECTOR_SQL = text(
    """
    SELECT dc.id AS chunk_id,
           1.0 - (dc.embedding <=> CAST(:q_emb AS vector)) AS vec_score
      FROM document_chunks dc
      JOIN documents d ON d.id = dc.document_id
      JOIN files f ON f.id = d.file_id
      JOIN knowledge_base_files kbf ON kbf.file_id = f.id
     WHERE kbf.kb_id = :kb_id
       AND f.deleted_at IS NULL
       AND f.ingestion_status = 'ready'
       AND dc.embedding IS NOT NULL
     ORDER BY dc.embedding <=> CAST(:q_emb AS vector)
     LIMIT :limit
    """
)


async def _vector_candidates(
    db: AsyncSession,
    *,
    kb_id: uuid.UUID,
    query_embedding: list[float],
    limit: int,
) -> list[tuple[uuid.UUID, float]]:
    """Run the pgvector cosine query.

    Returns ``(chunk_id, vector_score)`` pairs; ``vector_score`` is
    ``1 - cosine_distance``, in roughly ``[0, 1]`` for normalized
    embeddings (OpenAI's text-embedding-3-* are unit-normalized at
    output, so cosine distance is in [0, 2] and ``1 - dist`` is in
    [-1, 1]; we clamp at the normalize step).
    """

    vector_text = _format_vector(query_embedding)
    result = await db.execute(
        _VECTOR_SQL,
        {"kb_id": str(kb_id), "q_emb": vector_text, "limit": limit},
    )
    rows = result.mappings().all()
    return [(uuid.UUID(str(row["chunk_id"])), float(row["vec_score"])) for row in rows]


_FTS_SQL = text(
    """
    SELECT dc.id AS chunk_id,
           ts_rank_cd(dc.content_tsv, plainto_tsquery('english', :q)) AS fts_rank
      FROM document_chunks dc
      JOIN documents d ON d.id = dc.document_id
      JOIN files f ON f.id = d.file_id
      JOIN knowledge_base_files kbf ON kbf.file_id = f.id
     WHERE kbf.kb_id = :kb_id
       AND f.deleted_at IS NULL
       AND f.ingestion_status = 'ready'
       AND dc.content_tsv @@ plainto_tsquery('english', :q)
     ORDER BY fts_rank DESC
     LIMIT :limit
    """
)


async def _fts_candidates(
    db: AsyncSession,
    *,
    kb_id: uuid.UUID,
    query: str,
    limit: int,
) -> list[tuple[uuid.UUID, float]]:
    """Run the FTS query (``plainto_tsquery`` + ``ts_rank_cd``).

    ``plainto_tsquery`` is the safest tsquery constructor for user
    input — it lexes and stems each whitespace-separated token without
    interpreting any operators. Operators (``&``, ``|``, ``!``) are
    treated as literal characters.
    """

    result = await db.execute(_FTS_SQL, {"kb_id": str(kb_id), "q": query, "limit": limit})
    rows = result.mappings().all()
    return [(uuid.UUID(str(row["chunk_id"])), float(row["fts_rank"])) for row in rows]


_HYDRATE_SQL = text(
    """
    SELECT dc.id AS chunk_id,
           dc.document_id AS document_id,
           f.id AS file_id,
           f.filename AS file_name,
           dc.content AS content,
           dc.page_start AS page_start,
           dc.page_end AS page_end,
           dc.char_offset_start AS char_offset_start,
           dc.char_offset_end AS char_offset_end
      FROM document_chunks dc
      JOIN documents d ON d.id = dc.document_id
      JOIN files f ON f.id = d.file_id
     WHERE dc.id = ANY(:ids)
    """
)


async def _hydrate_chunks(
    db: AsyncSession,
    chunk_ids: list[uuid.UUID],
) -> list[dict[str, Any]]:
    """Fetch the chunk rows + file metadata for ``chunk_ids``."""

    if not chunk_ids:
        return []
    result = await db.execute(_HYDRATE_SQL, {"ids": [str(cid) for cid in chunk_ids]})
    rows = result.mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "chunk_id": uuid.UUID(str(row["chunk_id"])),
                "document_id": uuid.UUID(str(row["document_id"])),
                "file_id": uuid.UUID(str(row["file_id"])),
                "file_name": str(row["file_name"]),
                "content": str(row["content"]),
                "page_start": (int(row["page_start"]) if row["page_start"] is not None else None),
                "page_end": int(row["page_end"]) if row["page_end"] is not None else None,
                "char_offset_start": int(row["char_offset_start"]),
                "char_offset_end": int(row["char_offset_end"]),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Score combination helpers
# ---------------------------------------------------------------------------


def _min_max_normalize(scores: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    """Min-max normalize a score map to [0, 1].

    Per ADR 0008 we use min-max not z-score — z-score requires non-trivial
    standard deviation which fails on small candidate sets common at M1
    scale. With min-max:

    * If every score is identical, every normalized score is 1.0 (the
      candidate set is uniformly relevant according to that side).
    * If the set is empty, returns an empty dict (caller handles the
      missing-entry case as 0 contribution).
    * Otherwise, ``norm = (score - min) / (max - min)`` clamped to
      [0, 1].
    """

    if not scores:
        return {}
    values = list(scores.values())
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return dict.fromkeys(scores, 1.0)
    out: dict[uuid.UUID, float] = {}
    spread = hi - lo
    for cid, score in scores.items():
        normalized = (score - lo) / spread
        # Clamp to [0, 1] — vector_score = 1 - cosine_distance can be
        # slightly outside [0, 1] for non-normalized embeddings.
        out[cid] = max(0.0, min(1.0, normalized))
    return out


def _format_vector(vector: list[float]) -> str:
    """Format a float list as pgvector's textual ``[v1,v2,...]`` form."""

    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


def _as_uuid(value: Any) -> uuid.UUID:
    """Coerce a DB-returned id (already a ``uuid.UUID`` under psycopg, or a str)."""

    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


# ---------------------------------------------------------------------------
# Matter-scoped hybrid retrieval (F2 Slice A, ADR-F049)
# ---------------------------------------------------------------------------
#
# The agent's matter document tool (``app/agents/tools.py:search_documents``)
# and the Track-B retrieval eval (``tests/.../cuad_eval.py:fts_retrieve``) BOTH
# route through :func:`matter_hybrid_search` — one retriever, so "agent mode
# matches retriever-only" is structural rather than a drift guard between two
# hand-kept copies.
#
# The matter scope diverges from the KB scope above ON PURPOSE and must NOT
# converge onto it:
#   * membership = the ``project_files`` attach join OR the upload-time
#     ``files.project_id`` column (either one makes a file the matter's);
#   * owner re-asserted (``files.owner_id == :uid``) + ``deleted_at IS NULL``;
#   * NO ``ingestion_status = 'ready'`` filter — a matter chunk is searchable
#     as soon as it exists; the matter path never gated on ingestion state (the
#     KB path does). Adding that filter here is a behaviour change — don't.
#   * FTS uses ``websearch_to_tsquery`` (quotes / OR / leading ``-`` honoured),
#     NOT the KB side's ``plainto_tsquery``.
# ``_MATTER_FROM_WHERE`` is the single source of that security boundary; the
# three matter queries below all build on it (parameterised, never f-string
# interpolated except the fixed ``:doc_id`` toggle).

_MATTER_FROM_WHERE = (
    "FROM document_chunks dc "
    "JOIN documents d ON d.id = dc.document_id "
    "JOIN files f ON f.id = d.file_id "
    "LEFT JOIN project_files pf ON pf.file_id = f.id AND pf.project_id = :pid "
    "WHERE (pf.project_id IS NOT NULL OR f.project_id = :pid) "
    "AND f.owner_id = :uid "
    "AND f.deleted_at IS NULL "
)

# Full-field FTS query (the FTS-only fast path): everything both callers render
# + the exact pre-Slice-A ranking/tiebreak (rank DESC, filename ASC, chunk_index
# ASC). ``{doc_filter}`` is either "" or the fixed within-document narrowing.
_MATTER_FTS_FULL = (
    "SELECT dc.id AS chunk_id, dc.document_id, f.filename AS file_name, dc.content, "
    "dc.page_start, dc.page_end, dc.char_offset_start, dc.char_offset_end, "
    "ts_rank_cd(dc.content_tsv, websearch_to_tsquery('english', :q)) AS score "
    + _MATTER_FROM_WHERE
    + "AND dc.content_tsv @@ websearch_to_tsquery('english', :q) "
    "{doc_filter}"
    "ORDER BY score DESC, f.filename ASC, dc.chunk_index ASC "
    "LIMIT :lim"
)

# Candidate-only FTS query (hybrid path): id + raw rank, overshot, no final
# tiebreak (fusion re-orders). Same scope + operator as the full query.
_MATTER_FTS_CAND = (
    "SELECT dc.id AS chunk_id, "
    "ts_rank_cd(dc.content_tsv, websearch_to_tsquery('english', :q)) AS score "
    + _MATTER_FROM_WHERE
    + "AND dc.content_tsv @@ websearch_to_tsquery('english', :q) "
    "{doc_filter}"
    "ORDER BY score DESC "
    "LIMIT :lim"
)

# Candidate-only vector query (hybrid path): id + cosine similarity, overshot.
# Targets ``embedding_local`` — the matter/agent path's OWN 768-dim column (mig
# 0078, ADR-F049 Slice C1), filled by the local embedder (Door A by default). This
# is deliberately NOT the KB/chat ``embedding`` (1536) column the KB ``hybrid_search``
# uses — the two doors live in separate columns. ``embedding_local IS NOT NULL``
# excludes un-embedded chunks, so an un-backfilled matter degrades to FTS.
_MATTER_VEC_CAND = (
    "SELECT dc.id AS chunk_id, "
    "1.0 - (dc.embedding_local <=> CAST(:q_emb AS vector)) AS vec_score "
    + _MATTER_FROM_WHERE
    + "AND dc.embedding_local IS NOT NULL "
    "{doc_filter}"
    "ORDER BY dc.embedding_local <=> CAST(:q_emb AS vector) "
    "LIMIT :lim"
)


@dataclass(slots=True)
class MatterSearchHit:
    """One ranked chunk from a matter document search.

    Carries everything both callers need: the production ``search_documents``
    tool renders ``file_name`` + page range + ``content``; the Track-B eval
    scores ``char_offset_start/_end`` against CUAD gold spans. ``score`` is the
    raw ``ts_rank_cd`` in FTS-only mode and the fused hybrid score in hybrid
    mode — interpretable only as an ordering, not across queries.
    """

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    file_name: str
    content: str
    page_start: int | None
    page_end: int | None
    char_offset_start: int
    char_offset_end: int
    score: float


async def matter_hybrid_search(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    query_embedding: list[float] | None,
    top_k: int,
    alpha: float,
    document_id: uuid.UUID | None = None,
) -> list[MatterSearchHit]:
    """Hybrid (FTS + pgvector) retrieval over ONE matter's chunks.

    Mirrors :func:`hybrid_search` but scoped to a matter (see the scope note
    above) with ``websearch_to_tsquery`` FTS. ``project_id`` / ``user_id`` are
    the B-class matter+owner scope (the caller unpacks them from its binding —
    this module stays free of the agents layer). ``document_id`` narrows to one
    document (the eval's within-doc arm); ``None`` searches the whole matter.

    ``query_embedding is None`` (or ``alpha >= 1``) takes the **FTS-only fast
    path** — one ordered query returned verbatim, byte-identical to the
    pre-Slice-A matter retriever and the frozen Track-B baseline. This is the
    path production runs today: no embedder is wired yet, so ``search_documents``
    always passes ``query_embedding=None``. When Slice C lands an embedder, the
    caller passes a real vector + a tuned ``alpha`` and the hybrid branch lights
    up with no change here.
    """
    alpha = max(0.0, min(1.0, alpha))
    doc_filter = "AND dc.document_id = :doc_id " if document_id is not None else ""
    scope: dict[str, Any] = {"pid": str(project_id), "uid": str(user_id)}
    if document_id is not None:
        scope["doc_id"] = str(document_id)

    # --- FTS-only fast path (today's production behaviour; keep it exact) ----
    if query_embedding is None or alpha >= 1.0:
        sql = text(_MATTER_FTS_FULL.format(doc_filter=doc_filter))
        rows = (await db.execute(sql, {**scope, "q": query, "lim": top_k})).all()
        return [_hit_from_full_row(r) for r in rows]

    # --- Hybrid path (dormant until Slice C wires an embedder) --------------
    candidate_limit = top_k * CANDIDATE_OVERSHOOT

    fts_rows: list[tuple[uuid.UUID, float]] = []
    if alpha > 0.0:
        res = await db.execute(
            text(_MATTER_FTS_CAND.format(doc_filter=doc_filter)),
            {**scope, "q": query, "lim": candidate_limit},
        )
        fts_rows = [(_as_uuid(m["chunk_id"]), float(m["score"])) for m in res.mappings().all()]

    res = await db.execute(
        text(_MATTER_VEC_CAND.format(doc_filter=doc_filter)),
        {**scope, "q_emb": _format_vector(query_embedding), "lim": candidate_limit},
    )
    vector_rows = [(_as_uuid(m["chunk_id"]), float(m["vec_score"])) for m in res.mappings().all()]

    if not fts_rows and not vector_rows:
        return []

    fts_norm = _min_max_normalize(dict(fts_rows))
    vector_norm = _min_max_normalize(dict(vector_rows))
    candidate_ids = set(fts_norm) | set(vector_norm)
    fused = sorted(
        (
            (cid, (1.0 - alpha) * vector_norm.get(cid, 0.0) + alpha * fts_norm.get(cid, 0.0))
            for cid in candidate_ids
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )[:top_k]
    if not fused:
        return []

    score_map = dict(fused)
    hydrated = await _hydrate_chunks(db, [cid for cid, _ in fused])
    hits = [
        MatterSearchHit(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            file_name=row["file_name"],
            content=row["content"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            char_offset_start=row["char_offset_start"],
            char_offset_end=row["char_offset_end"],
            score=score_map[row["chunk_id"]],
        )
        for row in hydrated
        if row["chunk_id"] in score_map
    ]
    # _hydrate_chunks doesn't preserve order; re-sort by fused score with a
    # stable tiebreak so the result is deterministic across runs.
    hits.sort(key=lambda h: (-h.score, h.file_name, h.char_offset_start))
    return hits


async def matter_search_reranked(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    query_embedding: list[float] | None,
    top_k: int,
    alpha: float,
    document_id: uuid.UUID | None = None,
    reranker: RerankProvider | None,
    rerank_candidates: int,
) -> list[MatterSearchHit]:
    """Cross-encoder rerank over the matter hybrid candidate set (ADR-F049 Slice D).

    Fetches a WIDER hybrid candidate set (``rerank_candidates``) from
    :func:`matter_hybrid_search`, scores each candidate's ``content`` against the
    query with a cross-encoder, and reorders down to ``top_k``. A cross-encoder
    judges *(query, passage)* jointly — the precision complement to the bi-encoder
    fusion (which scores the two independently, then compares).

    ``reranker is None`` → delegates straight to :func:`matter_hybrid_search` at
    ``top_k`` (**byte-identical** to the no-rerank path, so the frozen E0/Slice-A
    baselines hold), and ``rerank_candidates`` is ignored. With a reranker,
    ``rerank_candidates`` should exceed ``top_k`` to widen the pool the cross-encoder
    reorders; the pool size is ``max(rerank_candidates, top_k)``, so a value ≤ ``top_k``
    degrades gracefully to reranking the top-``top_k`` (no widening, never an error). A
    reranker error (or a score-count mismatch) degrades to the hybrid order — retrieval
    never hard-fails on the reranker (mirrors the embedder fallback in
    ``tools.py:_embed_query``). Production ``search_documents`` AND the Track-B eval both
    route through here, so "agent mode == retriever" (Slice A).
    """
    if reranker is None:
        return await matter_hybrid_search(
            db,
            project_id=project_id,
            user_id=user_id,
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            alpha=alpha,
            document_id=document_id,
        )

    candidates = await matter_hybrid_search(
        db,
        project_id=project_id,
        user_id=user_id,
        query=query,
        query_embedding=query_embedding,
        top_k=max(rerank_candidates, top_k),
        alpha=alpha,
        document_id=document_id,
    )
    if len(candidates) <= 1:
        return candidates[:top_k]

    try:
        scores = await reranker.score(query, [c.content for c in candidates])
    except Exception as exc:  # degrade, never hard-fail on the reranker (embedder posture)
        log.warning(
            "matter rerank failed; hybrid-order fallback",
            extra={"event": "matter_rerank_failed", "error": str(exc)},
        )
        return candidates[:top_k]

    if len(scores) != len(candidates):
        log.warning(
            "matter rerank score count mismatch; hybrid-order fallback",
            extra={
                "event": "matter_rerank_score_mismatch",
                "scores": len(scores),
                "candidates": len(candidates),
            },
        )
        return candidates[:top_k]

    ranked = sorted(
        zip(candidates, scores, strict=True),
        key=lambda cs: (-cs[1], cs[0].file_name, cs[0].char_offset_start),
    )[:top_k]
    # The hit's ``score`` becomes the cross-encoder relevance score (an ordering
    # only, not calibrated across queries — same contract as the fused/FTS score).
    return [replace(hit, score=score) for hit, score in ranked]


def _hit_from_full_row(row: Any) -> MatterSearchHit:
    """Map one ``_MATTER_FTS_FULL`` row to a :class:`MatterSearchHit`."""

    return MatterSearchHit(
        chunk_id=_as_uuid(row.chunk_id),
        document_id=_as_uuid(row.document_id),
        file_name=str(row.file_name),
        content=str(row.content),
        page_start=int(row.page_start) if row.page_start is not None else None,
        page_end=int(row.page_end) if row.page_end is not None else None,
        char_offset_start=int(row.char_offset_start),
        char_offset_end=int(row.char_offset_end),
        score=float(row.score),
    )
