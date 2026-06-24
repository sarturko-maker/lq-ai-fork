"""C5a no-silent-action gate — model-free unit tests (ADR-F032).

The coverage gate + the closed-taxonomy decision validators ARE the net-new guarantee,
so they get direct, fast, DB-free coverage here (the DB-integration tests in
``test_commercial_tools.py`` exercise the wired path; these pin every branch)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.commercial import (
    CounterpartyDecision,
    RespondToCounterpartyInput,
    evaluate_coverage,
)


def _dec(ref: str, verdict: str, **kw: str) -> CounterpartyDecision:
    return CounterpartyDecision(ref=ref, verdict=verdict, **kw)


# ----------------------------- evaluate_coverage ----------------------------- #


def test_coverage_full_is_ok() -> None:
    report = evaluate_coverage(
        {"C1", "C2"},
        {"Com:1"},
        [
            _dec("C1", "accept"),
            _dec("C2", "reject", rationale="no"),
            _dec("Com:1", "reply", reply_text="ok"),
        ],
    )
    assert report.ok
    assert not (report.missing or report.unknown or report.duplicate)


def test_coverage_missing_ref_rejected() -> None:
    report = evaluate_coverage({"C1", "C2"}, {"Com:1"}, [_dec("C1", "accept")])
    assert not report.ok
    assert set(report.missing) == {"C2", "Com:1"}
    assert "UNADDRESSED" in report.rejection_text()
    assert "C2" in report.rejection_text() and "Com:1" in report.rejection_text()


def test_coverage_unknown_ref_rejected() -> None:
    report = evaluate_coverage({"C1"}, set(), [_dec("C1", "accept"), _dec("C9", "accept")])
    assert not report.ok
    assert report.unknown == ["C9"]


def test_coverage_duplicate_ref_rejected() -> None:
    report = evaluate_coverage(
        {"C1"}, set(), [_dec("C1", "accept"), _dec("C1", "reject", rationale="changed my mind")]
    )
    assert not report.ok
    assert report.duplicate == ["C1"]


def test_coverage_collects_all_errors_at_once() -> None:
    report = evaluate_coverage(
        {"C1", "C2"},
        {"Com:1"},
        [_dec("C2", "accept"), _dec("C2", "accept"), _dec("C7", "accept")],
    )
    assert not report.ok
    assert report.missing == ["C1", "Com:1"]  # C2 present, Com:1 + C1 missing
    assert report.unknown == ["C7"]
    assert report.duplicate == ["C2"]


# ------------------------- CounterpartyDecision shape ------------------------ #


def test_valid_decisions_construct() -> None:
    _dec("C1", "accept")
    _dec("C1", "reject", rationale="one-sided")
    _dec("C1", "counter", target_text="x", new_text="y", rationale="z")
    _dec("C1", "leave_open", rationale="parking this")
    _dec("C1", "escalate", rationale="below floor")
    _dec("Com:3", "reply", reply_text="thanks")
    _dec("Com:3", "leave_open", rationale="defer")


@pytest.mark.parametrize(
    "ref,verdict,kw",
    [
        ("Com:1", "accept", {}),  # a comment can't be accepted
        ("Com:1", "reject", {"rationale": "x"}),  # ...or rejected
        ("Com:1", "counter", {"target_text": "a", "new_text": "b", "rationale": "c"}),
        ("C1", "reply", {"reply_text": "x"}),  # a change can't be replied to
        ("C1", "counter", {"target_text": "only target"}),  # counter needs new_text
        ("C1", "counter", {"new_text": "only new"}),  # ...and target_text
        ("Com:1", "reply", {}),  # reply needs reply_text
        ("C1", "reject", {}),  # reject needs a rationale
        ("C1", "leave_open", {}),  # leave_open needs a rationale
        ("C1", "escalate", {}),  # escalate needs a rationale
        ("X1", "accept", {}),  # bad ref grammar
        ("C1", "bogus", {}),  # unknown verdict
    ],
)
def test_invalid_decisions_rejected(ref: str, verdict: str, kw: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        _dec(ref, verdict, **kw)


# --------------------------- RespondToCounterpartyInput ---------------------- #


def test_respond_input_requires_at_least_one_decision() -> None:
    with pytest.raises(ValidationError):
        RespondToCounterpartyInput(document_name="x.docx", decisions=[])


def test_respond_input_blank_document_name_rejected() -> None:
    with pytest.raises(ValidationError):
        RespondToCounterpartyInput(document_name="  ", decisions=[_dec("C1", "accept")])
