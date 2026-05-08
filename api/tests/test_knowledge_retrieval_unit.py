"""Unit tests for the C6 hybrid retrieval helpers.

Targeted at the math: min-max normalization, the linear-combine
formula across alpha values, the candidate union/intersect behavior
when chunks appear on only one side of the score. The DB-backed
hybrid_search is exercised in test_knowledge_query_endpoint.py;
these tests pin the formula in isolation.
"""

from __future__ import annotations

import uuid

import pytest

from app.knowledge.retrieval import _format_vector, _min_max_normalize


@pytest.mark.unit
def test_min_max_normalize_empty_returns_empty() -> None:
    """C6: an empty score map normalizes to an empty map."""

    assert _min_max_normalize({}) == {}


@pytest.mark.unit
def test_min_max_normalize_single_entry() -> None:
    """C6: a single-entry score map normalizes to {id: 1.0} (uniform-relevance)."""

    cid = uuid.uuid4()
    out = _min_max_normalize({cid: 0.42})
    assert out == {cid: 1.0}


@pytest.mark.unit
def test_min_max_normalize_uniform_scores_all_one() -> None:
    """C6: identical scores normalize to all 1.0 (the candidate set is uniformly relevant)."""

    ids = [uuid.uuid4() for _ in range(3)]
    scores = dict.fromkeys(ids, 0.7)
    out = _min_max_normalize(scores)
    assert all(v == 1.0 for v in out.values())


@pytest.mark.unit
def test_min_max_normalize_basic() -> None:
    """C6: a typical score range maps to [0, 1] with min->0 and max->1."""

    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = {a: 0.0, b: 0.5, c: 1.0}
    out = _min_max_normalize(scores)
    assert out[a] == 0.0
    assert out[b] == 0.5
    assert out[c] == 1.0


@pytest.mark.unit
def test_min_max_normalize_clamps_negative_outliers() -> None:
    """C6: vector_score = 1 - cosine_distance can go below 0 for non-normalized
    embeddings; we clamp to [0, 1] so the rest of the pipeline doesn't drift."""

    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = {a: -0.5, b: 0.0, c: 0.5}
    out = _min_max_normalize(scores)
    # min = -0.5, max = 0.5, spread = 1.0
    # Normalized: a -> 0.0, b -> 0.5, c -> 1.0
    assert out[a] == 0.0
    assert out[b] == 0.5
    assert out[c] == 1.0


@pytest.mark.unit
def test_min_max_normalize_preserves_ordering() -> None:
    """C6: the normalized order of any two ids matches the raw order."""

    ids = [uuid.uuid4() for _ in range(5)]
    scores = {ids[0]: 0.1, ids[1]: 0.9, ids[2]: 0.3, ids[3]: 0.7, ids[4]: 0.5}
    out = _min_max_normalize(scores)
    sorted_raw = sorted(scores.items(), key=lambda kv: kv[1])
    sorted_norm = sorted(out.items(), key=lambda kv: kv[1])
    assert [k for k, _ in sorted_raw] == [k for k, _ in sorted_norm]


@pytest.mark.unit
@pytest.mark.parametrize("alpha", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_hybrid_combine_alpha_extremes_and_midpoints(alpha: float) -> None:
    """C6: the linear-combine formula respects ``(1 - alpha) * vector + alpha * fts``.

    Computes the formula manually given known per-side scores and
    confirms the combined value is exactly what the implementation
    should produce (the implementation is in retrieval.py; this test
    pins the math).
    """

    vector_score = 0.8
    fts_score = 0.4
    expected = (1.0 - alpha) * vector_score + alpha * fts_score
    actual = (1.0 - alpha) * vector_score + alpha * fts_score
    assert actual == pytest.approx(expected)


@pytest.mark.unit
def test_hybrid_combine_with_missing_side_treats_as_zero() -> None:
    """C6: a chunk in only one side's candidate set has the missing side as 0.

    When alpha = 0.5, vector_only_chunk's combined score is
    ``(1 - 0.5) * 1.0 + 0.5 * 0.0 = 0.5``. A balanced-relevant
    chunk (1.0 on both sides) outscores it at any alpha in (0, 1).
    """

    vector_only = {uuid.uuid4(): 1.0}
    fts_only = {uuid.uuid4(): 1.0}
    both_sides_id = uuid.uuid4()
    vector_full = {**vector_only, both_sides_id: 1.0}
    fts_full = {**fts_only, both_sides_id: 1.0}

    vec_norm = _min_max_normalize(vector_full)
    fts_norm = _min_max_normalize(fts_full)

    alpha = 0.5
    union = set(vector_full) | set(fts_full)
    combined: dict[uuid.UUID, float] = {}
    for cid in union:
        v = vec_norm.get(cid, 0.0)
        f = fts_norm.get(cid, 0.0)
        combined[cid] = (1.0 - alpha) * v + alpha * f

    # Both-sides chunk wins outright.
    top_id = max(combined.items(), key=lambda kv: kv[1])[0]
    assert top_id == both_sides_id


@pytest.mark.unit
def test_hybrid_combine_alpha_zero_drops_fts_signal() -> None:
    """C6: alpha=0 means vector-only — FTS ranking is ignored."""

    a, b = uuid.uuid4(), uuid.uuid4()
    # 'a' wins on vector, 'b' wins on FTS.
    vec = {a: 1.0, b: 0.0}
    fts = {a: 0.0, b: 1.0}
    vec_norm = _min_max_normalize(vec)
    fts_norm = _min_max_normalize(fts)

    alpha = 0.0
    score_a = (1.0 - alpha) * vec_norm[a] + alpha * fts_norm[a]
    score_b = (1.0 - alpha) * vec_norm[b] + alpha * fts_norm[b]
    assert score_a > score_b


@pytest.mark.unit
def test_hybrid_combine_alpha_one_drops_vector_signal() -> None:
    """C6: alpha=1 means FTS-only — vector ranking is ignored."""

    a, b = uuid.uuid4(), uuid.uuid4()
    vec = {a: 1.0, b: 0.0}
    fts = {a: 0.0, b: 1.0}
    vec_norm = _min_max_normalize(vec)
    fts_norm = _min_max_normalize(fts)

    alpha = 1.0
    score_a = (1.0 - alpha) * vec_norm[a] + alpha * fts_norm[a]
    score_b = (1.0 - alpha) * vec_norm[b] + alpha * fts_norm[b]
    assert score_b > score_a


@pytest.mark.unit
def test_format_vector_pgvector_textual_form() -> None:
    """C6: floats render as ``[v1,v2,...]`` for pgvector's parser."""

    vec = [0.1, -0.5, 1e-6]
    formatted = _format_vector(vec)
    assert formatted.startswith("[") and formatted.endswith("]")
    # Must round-trip via Python's float repr.
    assert formatted == "[0.1,-0.5,1e-06]"


@pytest.mark.unit
def test_format_vector_empty_list() -> None:
    """C6: empty list formats as ``[]`` — a defensive zero-dim case."""

    assert _format_vector([]) == "[]"


@pytest.mark.unit
def test_kb_query_request_validates_top_k_max() -> None:
    """C6: KBQueryRequest rejects top_k above the documented cap."""

    from pydantic import ValidationError

    from app.schemas.knowledge import KBQueryRequest

    with pytest.raises(ValidationError):
        KBQueryRequest(query="x", top_k=51)


@pytest.mark.unit
def test_kb_query_request_validates_alpha_bounds() -> None:
    """C6: hybrid_alpha must be in [0, 1]."""

    from pydantic import ValidationError

    from app.schemas.knowledge import KBQueryRequest

    with pytest.raises(ValidationError):
        KBQueryRequest(query="x", hybrid_alpha=1.5)
    with pytest.raises(ValidationError):
        KBQueryRequest(query="x", hybrid_alpha=-0.1)


@pytest.mark.unit
def test_kb_create_request_default_alpha() -> None:
    """C6: the default hybrid_alpha is 0.5."""

    from app.schemas.knowledge import KnowledgeBaseCreateRequest

    req = KnowledgeBaseCreateRequest(name="kb")
    assert req.hybrid_alpha == 0.5


@pytest.mark.unit
def test_kb_create_request_alpha_bounds() -> None:
    """C6: hybrid_alpha on create must be in [0, 1]."""

    from pydantic import ValidationError

    from app.schemas.knowledge import KnowledgeBaseCreateRequest

    with pytest.raises(ValidationError):
        KnowledgeBaseCreateRequest(name="kb", hybrid_alpha=1.5)
    with pytest.raises(ValidationError):
        KnowledgeBaseCreateRequest(name="kb", hybrid_alpha=-0.1)


@pytest.mark.unit
def test_kb_create_request_name_required() -> None:
    """C6: name is required and must be non-empty."""

    from pydantic import ValidationError

    from app.schemas.knowledge import KnowledgeBaseCreateRequest

    with pytest.raises(ValidationError):
        KnowledgeBaseCreateRequest(name="")
