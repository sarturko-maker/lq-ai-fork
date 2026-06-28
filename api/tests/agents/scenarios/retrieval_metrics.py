"""Objective span-overlap retrieval metrics — the Track-B scorer (ADR-F049, E0).

Pure functions over half-open character spans ``[start, end)``. No DB, no app
imports, no I/O — so the unit tests run in CI for free and the same metric code
scores every later retrieval slice (FTS baseline, local embeddings, rerank,
PageIndex). A baseline is only meaningful if later slices are measured with the
*identical* metric, so this module is deliberately tiny, dependency-free, and
frozen in shape.

The retrieval unit is a chunk (a ``[start, end)`` slice of a document's
``normalized_content``); the ground truth is a set of gold answer spans (CUAD's
human ``answer_start`` + ``len(text)``). A retrieved chunk *covers* a gold span
when their character ranges overlap. Each gold span is one relevant target — a
chunk that overlaps several golds covers several; several overlapping chunks
(the production chunker uses a 200-char overlap) that cover the same gold count
that gold once. recall@k / average-precision are therefore computed at the
**gold-span level** (dedup-safe, bounded by 1); precision@k is the usual
per-retrieved-item rate.
"""

from __future__ import annotations

from collections.abc import Sequence

# A half-open character range ``[start, end)`` into one document's text.
Span = tuple[int, int]


def overlap_len(a: Span, b: Span) -> int:
    """Length of the character overlap between two spans (0 if disjoint)."""
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def spans_overlap(a: Span, b: Span) -> bool:
    """True iff two spans share at least one character position."""
    return overlap_len(a, b) > 0


def gold_first_ranks(retrieved: Sequence[Span], gold: Sequence[Span]) -> dict[int, int]:
    """Map each gold-span index to the 1-based rank of the first chunk covering it.

    Walks ``retrieved`` in rank order (best first); records, for each gold span,
    the earliest retrieved-chunk rank whose span overlaps it. Gold spans never
    covered are absent from the result. This is the shared primitive behind
    recall@k and average precision — both are gold-span-level, so a gold covered
    by two overlapping chunks counts once at its first (best) rank.
    """
    first: dict[int, int] = {}
    for i, chunk in enumerate(retrieved):
        for j, g in enumerate(gold):
            if j not in first and spans_overlap(chunk, g):
                first[j] = i + 1
    return first


def recall_at_k(retrieved: Sequence[Span], gold: Sequence[Span], k: int) -> float:
    """Gold-span coverage in the top-k: |gold covered by top-k| / |gold|.

    Returns NaN when ``gold`` is empty (an absent clause — coverage is undefined;
    absent questions are scored by the abstention/spurious-retrieval control,
    not by recall).
    """
    if not gold:
        return float("nan")
    ranks = gold_first_ranks(retrieved, gold)
    covered = sum(1 for r in ranks.values() if r <= k)
    return covered / len(gold)


def any_hit_at_k(retrieved: Sequence[Span], gold: Sequence[Span], k: int) -> bool:
    """True iff at least one top-k chunk covers any gold span (question-level hit)."""
    if not gold:
        return False
    return any(r <= k for r in gold_first_ranks(retrieved, gold).values())


def precision_at_k(retrieved: Sequence[Span], gold: Sequence[Span], k: int) -> float:
    """Fraction of the top-k retrieved chunks that cover at least one gold span.

    Denominator is ``min(k, len(retrieved))`` so a short result list is not
    penalised for ranks it never returned. Returns 0.0 for an empty result.
    Unlike recall, this is a per-retrieved-item rate: a redundant chunk that
    overlaps an already-covered gold still counts as relevant (it is).
    """
    topk = list(retrieved[:k])
    if not topk:
        return 0.0
    relevant = sum(1 for chunk in topk if any(spans_overlap(chunk, g) for g in gold))
    return relevant / len(topk)


def average_precision(retrieved: Sequence[Span], gold: Sequence[Span]) -> float:
    """Average precision over the ranked list, at the gold-span level.

    Each gold span contributes the **chunk-level precision at the rank where it
    is first covered**: if gold *g* is first covered by the chunk at rank ``r``,
    its contribution is ``(relevant chunks in top-r) / r`` (a relevant chunk is
    one overlapping any gold). AP = mean of those contributions over ALL gold
    spans. Bounded in [0, 1] — the precision term is ≤ 1 and there are ≤ |gold|
    covered golds. This handles **tied ranks correctly**: when one chunk covers
    several gold spans (CUAD multi-span answers under the 200-char-overlap
    chunker), each of those golds gets that chunk's precision (≤ 1), never an
    inflated ``i/p`` sum. Returns NaN for absent clauses, 0.0 when no gold span
    is ever covered. Mean over questions = MAP.
    """
    if not gold:
        return float("nan")
    first = gold_first_ranks(retrieved, gold)
    if not first:
        return 0.0
    # Cumulative count of relevant retrieved chunks (overlapping any gold) by rank.
    cum_relevant: list[int] = []
    seen = 0
    for chunk in retrieved:
        if any(spans_overlap(chunk, g) for g in gold):
            seen += 1
        cum_relevant.append(seen)
    total = sum(cum_relevant[rank - 1] / rank for rank in first.values())
    return total / len(gold)
