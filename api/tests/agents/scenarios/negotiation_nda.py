"""Round-2 negotiation fixture — a counterparty-marked-up NDA (C5a, ADR-F032).

A short mutual NDA where the *counterparty* (acting against us) has returned the draft
with tracked changes + a comment, authored "Opposing Counsel". The live scenario drives
the agent to read this markup (``extract_counterparty_position``) and respond to every
change/comment (``respond_to_counterparty``) — accepting the benign edit, rejecting/
countering the one-sided ones, replying to the comment, and **escalating** the
below-floor demand (perpetual survival). Built with Adeu so the bytes carry real OOXML
tracked changes + comments (the same path the agent reads).
"""

from __future__ import annotations

import io

NDA_FILENAME = "Mutual NDA (counterparty markup).docx"

_BASE_CLAUSES = [
    "1. Purpose. The parties wish to explore a potential business relationship and may "
    "disclose confidential information to one another for that purpose.",
    "2. Confidential Information. Each party may disclose to the other certain non-public "
    "business and technical information designated as confidential.",
    "3. Obligations. Each party shall protect the other party's Confidential Information "
    "using the same degree of care it uses for its own, and shall not disclose it to third "
    "parties without prior written consent.",
    "4. Term. The obligations of confidentiality shall survive for three (3) years from the "
    "date of disclosure.",
    "5. Return of Materials. Upon written request, each party shall return or destroy the "
    "other party's Confidential Information.",
    "6. Governing Law. This Agreement is governed by the laws of England and Wales.",
]

# The counterparty's edits, authored "Opposing Counsel" (target_text must be unique in
# the base text). Designed to exercise every verdict in a live round:
#   - one-sided obligation swap (we should reject/counter),
#   - a survival period blown out to perpetual (below our floor → escalate),
#   - a benign clarification (we should accept),
#   - a unilateral consent carve-out (we should counter).
_COUNTERPARTY_EDITS = [
    # 3: make the mutual obligation one-directional in their favour
    (
        "Each party shall protect the other party's Confidential Information",
        "The Recipient shall protect the Discloser's Confidential Information",
        "We act for both sides equally — this should stay mutual.",
    ),
    # 4: blow out the survival term to perpetual (below-floor → escalate)
    ("three (3) years from the date of disclosure", "perpetuity", None),
    # 2: a benign clarification (accept)
    ("designated as confidential", "designated as confidential in writing", None),
    # 3: add a unilateral consent carve-out (counter)
    (
        "without prior written consent",
        "without prior written consent, except to its affiliates and advisers",
        None,
    ),
]


def build_counterparty_nda_docx() -> bytes:
    """The base NDA with the counterparty's tracked changes + one comment applied."""
    from adeu import ModifyText, RedlineEngine
    from docx import Document

    doc = Document()
    for clause in _BASE_CLAUSES:
        doc.add_paragraph(clause)
    buf = io.BytesIO()
    doc.save(buf)

    eng = RedlineEngine(io.BytesIO(buf.getvalue()), author="Opposing Counsel")
    eng.apply_edits(
        [
            ModifyText(target_text=target, new_text=new, comment=comment)
            for target, new, comment in _COUNTERPARTY_EDITS
        ]
    )
    out = eng.save_to_stream()
    return out.getvalue() if hasattr(out, "getvalue") else bytes(out)


def nda_clean_text() -> str:
    """The base NDA text (a reasonable searchable projection; the agent reads the
    tracked-changes bytes via Adeu, not this)."""
    return "\n".join(_BASE_CLAUSES)
