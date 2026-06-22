"""C4 surgical-gate tests (ADR-F031) — model-free, no I/O, no Adeu.

The deterministic half of the redline validated-write loop: the D1-D6 rules over
proposed edits. These have *teeth* — a phrase where a word suffices is rejected, a
justified rewrite is accepted, a bare substantive deletion is rejected, an
ambiguous anchor is rejected — and they honour the §5.1 doctrine that *adding*
protective language (a carve-out/super-cap) is surgical while *striking* existing
text is what must stay minimal.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.commercial import (
    ApplyRedlineInput,
    RedlineEditInput,
    changed_tokens,
    clause_token_count,
    count_occurrences,
    deleted_tokens,
    evaluate_gate,
    inserted_tokens,
    is_substantive_change,
    is_substantive_token,
)

CAP = (
    "The Vendor's aggregate liability arising out of or in connection with this "
    "Agreement shall not exceed the total fees paid by the Customer in the three (3) "
    "months preceding the claim."
)

# A realistic multi-clause document, so a full rewrite of ONE clause is a small
# fraction of the whole (D5 keys on the document, not the clause).
MULTI = " ".join(
    [
        CAP,
        "The Customer shall pay all undisputed invoices within thirty (30) days of "
        "receipt of a valid invoice.",
        "Either party may terminate this Agreement for material breach on thirty (30) "
        "days written notice if the breach remains uncured.",
        "Each party shall keep the other's Confidential Information secret and use it "
        "only to perform its obligations under this Agreement.",
    ]
)

_RATIONALE = (
    "The house liability floor is a twelve-month fee measure with carve-outs for "
    "data and IP breaches, so this aligns the cap period and protects the customer."
)


# --------------------------------------------------------------------------- #
# token-diff metrics: struck vs added (the load-bearing distinction)
# --------------------------------------------------------------------------- #


def test_struck_vs_added_distinguishes_replace_from_insert() -> None:
    # pure insertion: nothing struck, much added
    target = "preceding the claim."
    new = "preceding the claim, save that data-protection liability shall be unlimited."
    assert deleted_tokens(target, new) <= 1
    assert inserted_tokens(target, new) >= 6
    # word swap: one struck, one added
    assert deleted_tokens("best efforts", "reasonable efforts") == 1
    assert inserted_tokens("best efforts", "reasonable efforts") == 1
    assert changed_tokens("best efforts", "reasonable efforts") == 2


def test_changed_tokens_collapses_to_minimal_diff() -> None:
    # a one-word change expressed over a long matched span is a tiny real diff
    new = CAP.replace("three (3)", "twelve (12)")
    assert changed_tokens(CAP, new) <= 4  # not the ~30-token span length


@pytest.mark.parametrize(
    "tok,expected",
    [
        ("shall", True),
        ("not", True),
        ("90", True),
        ("$1,000", True),
        ("30%", True),
        ("months", True),
        ("Agreement", True),  # defined-term heuristic (TitleCase)
        ("the", False),
        ("efforts", False),
        ("reasonable", False),
    ],
)
def test_is_substantive_token(tok: str, expected: bool) -> None:
    assert is_substantive_token(tok) is expected


def test_is_substantive_change() -> None:
    assert is_substantive_change("90 days", "30 days") is True  # number
    assert is_substantive_change("shall indemnify", "shall not indemnify") is True
    assert is_substantive_change("best efforts", "reasonable efforts") is False


# --------------------------------------------------------------------------- #
# D2 / D3 / no-op — per-edit, document-free (the *Input validators)
# --------------------------------------------------------------------------- #


def test_noop_edit_rejected() -> None:
    with pytest.raises(ValidationError, match="no change"):
        RedlineEditInput(target_text="the claim", new_text="the claim")


def test_blank_target_rejected() -> None:
    with pytest.raises(ValidationError, match="non-blank"):
        RedlineEditInput(target_text="   ", new_text="something")


def test_d3_bare_substantive_deletion_rejected() -> None:
    with pytest.raises(ValidationError, match="D3"):
        RedlineEditInput(
            target_text="The Vendor shall not be liable for any data breach.",
            new_text="",
        )


def test_d2_substantive_edit_needs_rationale() -> None:
    with pytest.raises(ValidationError, match="D2"):
        RedlineEditInput(target_text="ninety (90) days", new_text="thirty (30) days")
    # with a real rationale it validates
    ok = RedlineEditInput(
        target_text="ninety (90) days", new_text="thirty (30) days", rationale=_RATIONALE
    )
    assert ok.new_text == "thirty (30) days"


def test_nonsubstantive_small_edit_needs_no_rationale() -> None:
    ok = RedlineEditInput(target_text="best efforts", new_text="reasonable efforts")
    assert ok.rationale == ""


def test_apply_input_rejects_empty_and_oversize_batch() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        ApplyRedlineInput(document_name="x.docx", edits=[])
    with pytest.raises(ValidationError, match="document_name"):
        ApplyRedlineInput(document_name="  ", edits=[{"target_text": "a", "new_text": "b"}])


# --------------------------------------------------------------------------- #
# clause/anchor helpers + D1/D4/D5 (document-relative)
# --------------------------------------------------------------------------- #


def test_unique_anchor_and_clause_resolution() -> None:
    assert count_occurrences(CAP, "three (3) months") == 1
    assert count_occurrences(CAP, "the Agreement") == 0  # CAP says "this Agreement"
    assert clause_token_count(CAP, "three (3) months") is not None
    # not found → unresolvable
    assert clause_token_count(CAP, "nonexistent span") is None


def _edit(**kw: object) -> RedlineEditInput:
    return RedlineEditInput(**kw)  # type: ignore[arg-type]


def test_d1_surgical_small_strike_allowed() -> None:
    report = evaluate_gate(
        CAP, [_edit(target_text="three (3)", new_text="twelve (12)", rationale=_RATIONALE)]
    )
    assert report.ok, report.rejection_text()


def test_d1_additive_carveout_is_surgical_even_when_large() -> None:
    # The §5.1 move: add a big protective carve-out. Strikes ~nothing → surgical.
    carveout = _edit(
        target_text="preceding the claim.",
        new_text=(
            "preceding the claim, save that liability for breach of confidentiality, "
            "data protection obligations or infringement of intellectual property "
            "rights shall be unlimited."
        ),
        rationale=_RATIONALE,
    )
    report = evaluate_gate(CAP, [carveout])
    assert report.ok, report.rejection_text()
    assert report.edits[0].deleted_tokens <= 1  # struck ~nothing; it adds protection


def test_d1_rip_and_replace_blocked_without_justification() -> None:
    # Strike (almost) all of ONE clause inside a multi-clause doc: D1 fires (a true
    # rewrite), D5 does not (it's a small fraction of the document).
    target = (
        "The Customer shall pay all undisputed invoices within thirty (30) days of "
        "receipt of a valid invoice."
    )
    new = "Remittance occurs forthwith upon issuance of a demand."
    blocked = evaluate_gate(MULTI, [_edit(target_text=target, new_text=new, rationale=_RATIONALE)])
    assert not blocked.ok
    assert any("D1" in r for v in blocked.edits for r in v.reasons), blocked.rejection_text()
    # the same rewrite, explicitly justified → allowed
    justified = _edit(
        target_text=target, new_text=new, rationale=_RATIONALE, rewrite_justified=True
    )
    assert evaluate_gate(MULTI, [justified]).ok, evaluate_gate(MULTI, [justified]).rejection_text()


def test_d1_phrase_where_a_word_suffices_blocked() -> None:
    doc = (
        "The Supplier shall use best efforts and all reasonable endeavours and every "
        "commercially practicable step to deliver the Services on time."
    )
    # strike a 9-word phrase to insert one word, no rationale → mid-band reject
    edit = _edit(
        target_text="best efforts and all reasonable endeavours and every commercially practicable step",
        new_text="reasonable efforts",
    )
    report = evaluate_gate(doc, [edit])
    assert not report.ok


def test_d4_ambiguous_anchor_blocked() -> None:
    doc = "Termination requires notice. The Customer may give notice at any time."
    edit = _edit(target_text="notice", new_text="written notice", rationale=_RATIONALE)
    report = evaluate_gate(doc, [edit])
    assert not report.ok
    assert any("D4" in r for v in report.edits for r in v.reasons)


def test_d5_gutting_the_document_escalates() -> None:
    doc = "Alpha beta gamma delta. Epsilon zeta eta theta. Iota kappa lambda mu."
    # strike most of the doc across edits
    edits = [
        _edit(target_text="Alpha beta gamma delta.", new_text="Removed.", rationale=_RATIONALE),
        _edit(target_text="Epsilon zeta eta theta.", new_text="Gone.", rationale=_RATIONALE),
    ]
    report = evaluate_gate(doc, edits)
    assert not report.ok
    assert any("D5" in r for r in report.batch_reasons)


def test_rejection_text_lists_reasons_without_clause_echo() -> None:
    report = evaluate_gate(
        CAP, [_edit(target_text="nonexistent span here", new_text="something else entirely")]
    )
    text = report.rejection_text()
    assert "rejected" in text.lower()
    assert "nonexistent span here" not in text  # never echoes the clause content
