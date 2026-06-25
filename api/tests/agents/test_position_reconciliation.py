"""C7b post-fan-out reconciliation — model-free unit tests (ADR-F034).

``evaluate_position_consistency`` IS the net-new reconciliation guarantee (a head where
the fanned-out drafts diverge cannot pass without an explicit resolution), so it gets
direct, fast, DB-free coverage here. The wired tool path (receipt + audit) is exercised
in ``test_commercial_tools.py``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.commercial import (
    MAX_POSITIONS_PER_RECONCILE,
    ProposedPosition,
    ReconcilePositionsInput,
    evaluate_position_consistency,
)


def _pos(head: str, position: str, source: str = "clause-drafter") -> ProposedPosition:
    return ProposedPosition(head=head, position=position, source=source)


# ----------------------- evaluate_position_consistency ----------------------- #


def test_one_position_per_head_is_ok() -> None:
    report = evaluate_position_consistency(
        [
            _pos("liability", "cap at 12 months fees"),
            _pos("indemnity", "mutual, IP carve-out"),
        ],
        {},
    )
    assert report.ok
    assert report.position_count == 2
    assert report.head_count == 2
    assert report.divergences_resolved == 0
    assert report.resolved == {
        "liability": "cap at 12 months fees",
        "indemnity": "mutual, IP carve-out",
    }
    assert not report.divergent


def test_divergent_head_without_resolution_is_rejected() -> None:
    report = evaluate_position_consistency(
        [
            _pos("liability", "uncapped", source="clause-drafter"),
            _pos("liability", "cap at fees", source="clause-reviewer"),
        ],
        {},
    )
    assert not report.ok
    assert report.divergent == ["liability"]
    assert "liability" in report.rejection_text()
    assert "nothing was recorded" in report.rejection_text()


def test_divergent_head_with_resolution_is_reconciled() -> None:
    report = evaluate_position_consistency(
        [
            _pos("liability", "uncapped", source="clause-drafter"),
            _pos("liability", "cap at fees", source="clause-reviewer"),
        ],
        {"liability": "super-cap at 2x fees, data/IP uncapped"},
    )
    assert report.ok
    assert report.divergences_resolved == 1
    assert report.resolved == {"liability": "super-cap at 2x fees, data/IP uncapped"}


def test_identical_drafts_on_a_head_do_not_diverge() -> None:
    # Same head, same (normalized) position from two drafts → one agreed position.
    report = evaluate_position_consistency(
        [
            _pos("term", "3 years, auto-renew", source="clause-drafter (a)"),
            _pos("term", "3 years, auto-renew", source="clause-drafter (b)"),
        ],
        {},
    )
    assert report.ok
    assert report.head_count == 1
    assert report.position_count == 2
    assert report.divergences_resolved == 0
    assert report.resolved == {"term": "3 years, auto-renew"}


def test_head_and_position_are_normalized() -> None:
    # Case/whitespace differences collapse — no false divergence.
    report = evaluate_position_consistency(
        [
            _pos("Limitation of Liability", "Cap at fees"),
            _pos("limitation of   liability", "cap at fees"),
        ],
        {},
    )
    assert report.ok
    assert report.head_count == 1


def test_resolution_for_a_non_divergent_head_is_ignored() -> None:
    # A head with a single agreed position uses it; a stray resolution doesn't override.
    report = evaluate_position_consistency(
        [_pos("price", "fixed for year 1")],
        {"price": "should-be-ignored"},
    )
    assert report.ok
    assert report.resolved == {"price": "fixed for year 1"}
    assert report.divergences_resolved == 0


def test_collects_every_unresolved_divergence() -> None:
    # One agreed, one divergent-resolved, two divergent-unresolved → only the unresolved
    # are reported (collect-all-errors, the lead fixes in one pass).
    report = evaluate_position_consistency(
        [
            _pos("price", "fixed"),
            _pos("liability", "uncapped", source="a"),
            _pos("liability", "capped", source="b"),
            _pos("indemnity", "one-way", source="a"),
            _pos("indemnity", "mutual", source="b"),
            _pos("ip", "assign", source="a"),
            _pos("ip", "licence", source="b"),
        ],
        {"liability": "super-cap"},
    )
    assert not report.ok
    assert report.divergent == ["indemnity", "ip"]  # sorted, liability resolved away


def test_blank_resolution_does_not_resolve_a_divergence() -> None:
    report = evaluate_position_consistency(
        [_pos("liability", "uncapped", source="a"), _pos("liability", "capped", source="b")],
        {"liability": "   "},
    )
    assert not report.ok
    assert report.divergent == ["liability"]


# --------------------------- schema-level guards ----------------------------- #


def test_empty_positions_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        ReconcilePositionsInput(positions=[], resolutions={})


def test_over_cap_positions_rejected() -> None:
    too_many = [
        {"head": f"h{i}", "position": "p", "source": "s"}
        for i in range(MAX_POSITIONS_PER_RECONCILE + 1)
    ]
    with pytest.raises(ValidationError, match="too many positions"):
        ReconcilePositionsInput(positions=too_many, resolutions={})  # type: ignore[arg-type]


def test_blank_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ProposedPosition(head="", position="p", source="s")
    with pytest.raises(ValidationError):
        ProposedPosition(head="h", position="", source="s")
    with pytest.raises(ValidationError):
        ProposedPosition(head="h", position="p", source="")


def test_extra_key_rejected() -> None:
    with pytest.raises(ValidationError):
        ProposedPosition(head="h", position="p", source="s", verdict="accept")  # type: ignore[call-arg]
