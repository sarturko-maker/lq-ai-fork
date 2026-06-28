"""Unit tests for the objective span-overlap retrieval metrics (ADR-F049, E0).

Pure, no DB, no provider — these run in CI and pin the Track-B scorer's
behaviour so a baseline frozen today is comparable to every later slice.
"""

from __future__ import annotations

import math

from tests.agents.scenarios.retrieval_metrics import (
    Span,
    any_hit_at_k,
    average_precision,
    gold_first_ranks,
    overlap_len,
    precision_at_k,
    recall_at_k,
    spans_overlap,
)


def test_overlap_len_and_spans_overlap() -> None:
    assert overlap_len((0, 10), (5, 15)) == 5
    assert overlap_len((0, 10), (10, 20)) == 0  # half-open: touching is not overlap
    assert overlap_len((0, 10), (20, 30)) == 0
    assert overlap_len((5, 15), (0, 10)) == 5  # symmetric
    assert spans_overlap((0, 10), (9, 11)) is True
    assert spans_overlap((0, 10), (10, 11)) is False


def test_gold_first_ranks_records_earliest_covering_chunk() -> None:
    retrieved: list[Span] = [(100, 200), (0, 50), (40, 60)]
    gold: list[Span] = [(10, 20), (45, 55)]
    ranks = gold_first_ranks(retrieved, gold)
    # gold[0]=(10,20) first covered by retrieved[1]=(0,50) -> rank 2
    # gold[1]=(45,55) first covered by retrieved[1]=(0,50) -> rank 2 (not the later (40,60))
    assert ranks == {0: 2, 1: 2}


def test_recall_at_k_is_gold_coverage() -> None:
    retrieved: list[Span] = [(0, 50), (1000, 1100)]
    gold: list[Span] = [(10, 20), (60, 70), (1050, 1060)]
    # top-1 covers gold[0] only -> 1/3
    assert recall_at_k(retrieved, gold, 1) == 1 / 3
    # top-2 covers gold[0] and gold[2] -> 2/3 (gold[1] never covered)
    assert recall_at_k(retrieved, gold, 2) == 2 / 3
    assert recall_at_k(retrieved, gold, 50) == 2 / 3


def test_recall_is_nan_for_absent_clause() -> None:
    assert math.isnan(recall_at_k([(0, 10)], [], 5))
    assert any_hit_at_k([(0, 10)], [], 5) is False


def test_any_hit_at_k() -> None:
    retrieved: list[Span] = [(1000, 1100), (0, 50)]
    gold: list[Span] = [(10, 20)]
    assert any_hit_at_k(retrieved, gold, 1) is False  # top-1 misses
    assert any_hit_at_k(retrieved, gold, 2) is True  # top-2 hits


def test_precision_at_k_counts_relevant_retrieved() -> None:
    retrieved: list[Span] = [(0, 50), (1000, 1100), (15, 25)]
    gold: list[Span] = [(10, 20)]
    # rank1 (0,50) relevant, rank2 (1000,1100) not, rank3 (15,25) relevant -> p@3 = 2/3
    assert precision_at_k(retrieved, gold, 3) == 2 / 3
    assert precision_at_k(retrieved, gold, 1) == 1.0
    # a disjoint chunk is not relevant: (40,60) does not overlap (10,20)
    assert precision_at_k([(40, 60)], gold, 1) == 0.0
    # short list: denominator is min(k, len)
    assert precision_at_k(retrieved, gold, 10) == 2 / 3
    assert precision_at_k([], gold, 5) == 0.0


def test_average_precision_rewards_ranking_relevant_high() -> None:
    gold: list[Span] = [(10, 20), (60, 70)]
    # both gold covered at ranks 1 and 2 -> AP = (1/1 + 2/2)/2 = 1.0
    perfect: list[Span] = [(0, 30), (55, 75)]
    assert average_precision(perfect, gold) == 1.0
    # one relevant pushed to rank 3 -> AP = (1/1 + 2/3)/2 = 0.8333...
    delayed: list[Span] = [(0, 30), (1000, 1100), (55, 75)]
    assert math.isclose(average_precision(delayed, gold), (1 / 1 + 2 / 3) / 2)


def test_average_precision_zero_when_nothing_relevant() -> None:
    assert average_precision([(1000, 1100)], [(10, 20)]) == 0.0
    assert math.isnan(average_precision([(0, 10)], []))


def test_average_precision_bounded_by_one_under_chunk_overlap() -> None:
    # Two overlapping retrieved chunks both cover the single gold (the production
    # chunker overlaps by 200 chars). AP must stay 1.0, never inflate.
    gold: list[Span] = [(100, 120)]
    retrieved: list[Span] = [(0, 110), (90, 200)]
    assert average_precision(retrieved, gold) == 1.0
    assert recall_at_k(retrieved, gold, 1) == 1.0


def test_average_precision_bounded_when_one_chunk_covers_many_golds() -> None:
    # CUAD multi-span answers co-located in ONE chunk (39% of present questions).
    # Tied first-cover ranks must NOT inflate AP above 1.0 (the regression the
    # adversarial review caught: the old i/p sum gave AP=1.5 / 2.0 / up to 7.0).
    assert average_precision([(0, 50)], [(10, 20), (30, 40)]) == 1.0
    assert average_precision([(0, 80)], [(10, 20), (30, 40), (60, 70)]) == 1.0
    # A 13-span clause all inside one perfectly-ranked chunk is still exactly 1.0.
    thirteen: list[Span] = [(i * 10, i * 10 + 5) for i in range(13)]
    assert average_precision([(0, 130)], thirteen) == 1.0
    # Both golds first covered together at rank 2 → each gets precision 1/2.
    assert average_precision([(1000, 1100), (0, 50)], [(10, 20), (30, 40)]) == 0.5
