"""C5a negotiation_service tests (ADR-F032).

The pure Adeu adapter: read the counterparty's tracked changes + comments into a
``StateOfPlay`` checklist, and apply per-ref decisions (accept/reject/counter/reply)
with the post-write reconciliation. Real Adeu (in-process, zero network) — no DB, no
gateway. This is the empirical floor under the no-silent-action guarantee: a decision
that doesn't land fails ``Reconciliation.ok``.
"""

from __future__ import annotations

import io

import pytest

from app.agents.negotiation_service import Decision, apply_decisions, read_state_of_play

pytestmark = pytest.mark.integration


def _base_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(
        "The Vendor shall indemnify the Customer for all losses arising from the Services."
    )
    doc.add_paragraph("The term of this Agreement is three (3) years from the Effective Date.")
    doc.add_paragraph("Liability is capped at fees paid in the prior twelve (12) months.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def counterparty_markup() -> bytes:
    """A doc with 3 counterparty tracked changes + 1 anchored comment (author='Opposing
    Counsel'). Shared shape with the tool-integration tests."""
    from adeu import ModifyText, RedlineEngine

    eng = RedlineEngine(io.BytesIO(_base_docx()), author="Opposing Counsel")
    eng.apply_edits(
        [
            ModifyText(
                target_text="all losses",
                new_text="direct losses only",
                comment="Cap our exposure to direct losses please.",
            ),
            ModifyText(target_text="three (3)", new_text="five (5)"),
            ModifyText(target_text="twelve (12)", new_text="twenty-four (24)"),
        ]
    )
    out = eng.save_to_stream()
    return out.getvalue() if hasattr(out, "getvalue") else bytes(out)


def test_read_state_of_play_enumerates_changes_and_comments() -> None:
    state = read_state_of_play(counterparty_markup())

    assert [c.ref for c in state.changes] == ["C1", "C2", "C3"]  # document order
    c1 = state.changes[0]
    assert c1.kind == "modify"
    assert c1.deleted_text == "all losses"
    assert c1.inserted_text == "direct losses only"
    assert c1.author == "Opposing Counsel"
    assert len(c1.adeu_ids) == 2  # a modify is a del + ins pair

    # one OPEN counterparty comment (thread root, not ours)
    assert len(state.open_comment_refs) == 1
    cm = next(c for c in state.comments if c.parent_id is None and not c.is_ours)
    assert cm.author == "Opposing Counsel"
    assert "direct losses" in cm.text


def test_apply_decisions_full_round_reconciles() -> None:
    cp = counterparty_markup()
    state = read_state_of_play(cp)
    com_ref = next(iter(state.open_comment_refs))
    decisions = [
        Decision(ref="C1", verdict="accept", rationale="Direct losses is acceptable."),
        Decision(ref="C2", verdict="reject", rationale="Five years is too long; revert to three."),
        Decision(
            ref="C3",
            verdict="counter",
            target_text="twenty-four (24)",
            new_text="eighteen (18)",
            rationale="Eighteen months is the house fallback for the liability survival window here.",
        ),
        Decision(
            ref=com_ref, verdict="reply", reply_text="Agreed on direct losses; see our counter."
        ),
    ]

    out_bytes, recon = apply_decisions(cp, state, decisions)

    assert recon.ok, recon.issues
    assert recon.review_skipped == 0
    assert recon.counters_skipped == 0
    assert recon.counters_applied >= 1

    after = read_state_of_play(out_bytes)
    # C1 accepted → incorporated as clean text; C2 rejected → reverted to "three (3)".
    assert "direct losses only" in after.clean_view
    assert "three (3)" in after.clean_view
    assert "five (5)" not in after.clean_view


def test_apply_decisions_unknown_ref_fails_reconciliation() -> None:
    cp = counterparty_markup()
    state = read_state_of_play(cp)
    _out, recon = apply_decisions(cp, state, [Decision(ref="C99", verdict="accept", rationale="x")])
    assert not recon.ok
    assert any("C99" in issue for issue in recon.issues)


def test_apply_decisions_bad_anchor_counter_is_skipped_not_silent() -> None:
    """A counter whose target_text isn't in the document can't land → reconciliation
    fails (the response is rejected upstream; nothing is silently dropped)."""
    cp = counterparty_markup()
    state = read_state_of_play(cp)
    decisions = [
        Decision(
            ref="C1",
            verdict="counter",
            target_text="this exact phrase is absent from the document",
            new_text="replacement that will never anchor",
            rationale="A deliberately unanchorable counter to prove the reconciliation tripwire.",
        )
    ]
    _out, recon = apply_decisions(cp, state, decisions)
    assert not recon.ok
