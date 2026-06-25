"""Spike 0 fixtures — built with the fork's REAL redline path (ADR-F045 word-diff).

Outputs to /work:
  fix1_agent_redline.docx  — clean NDA + agent (LQ.AI) tracked changes + a comment
                             (the state the lawyer opens in the editor)
  fix2_counterparty.docx   — NDA marked up by "Opposing Counsel" + a comment
  fix3_multipass.docx      — agent redline applied ON TOP of fix2 (Risk #11:
                             a second tracked-change pass over an already-tracked doc)
"""

import io
import sys

sys.path.insert(0, "/repo/api")

from adeu import ModifyText, RedlineEngine  # noqa: E402
from app.agents.redline_service import (  # noqa: E402
    DEFAULT_AUTHOR,
    ProposedEdit,
    RedlineService,
)
from docx import Document  # noqa: E402

OUT = "/work"
CP_AUTHOR = "Opposing Counsel"

BASE_CLAUSES = [
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

# Counterparty edits (verbatim from tests/agents/scenarios/negotiation_nda.py).
CP_EDITS = [
    (
        "Each party shall protect the other party's Confidential Information",
        "The Recipient shall protect the Discloser's Confidential Information",
        "We act for both sides equally — this should stay mutual.",
    ),
    ("three (3) years from the date of disclosure", "perpetuity", None),
    ("designated as confidential", "designated as confidential in writing", None),
    (
        "without prior written consent",
        "without prior written consent, except to its affiliates and advisers",
        None,
    ),
]


def base_docx() -> bytes:
    doc = Document()
    for clause in BASE_CLAUSES:
        doc.add_paragraph(clause)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_counterparty() -> bytes:
    eng = RedlineEngine(io.BytesIO(base_docx()), author=CP_AUTHOR)
    eng.apply_edits(
        [ModifyText(target_text=t, new_text=n, comment=c) for t, n, c in CP_EDITS]
    )
    out = eng.save_to_stream()
    return out.getvalue() if hasattr(out, "getvalue") else bytes(out)


def write(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)
    print(f"  wrote {path} ({len(data)} bytes)")


def main() -> None:
    svc = RedlineService(author=DEFAULT_AUTHOR)

    # Fixture 1 — agent redline on a clean base, with a comment.
    agent_edits = [
        ProposedEdit(
            "three (3) years from the date of disclosure",
            "five (5) years from the date of disclosure",
            "Extended survival to five years in line with our standard position.",
        ),
        ProposedEdit(
            "shall return or destroy",
            "shall return and, at the Discloser's option, destroy",
            None,
        ),
    ]
    res1 = svc.apply(base_docx(), agent_edits)
    write(f"{OUT}/fix1_agent_redline.docx", res1.docx_bytes)
    print(f"    fix1 applied={res1.edits_applied} skipped={res1.edits_skipped}")

    # Fixture 2 — counterparty markup.
    cp = build_counterparty()
    write(f"{OUT}/fix2_counterparty.docx", cp)

    # Fixture 3 — MULTI-PASS: agent redline applied on top of the already-tracked
    # counterparty doc. Edit targets clause 6 (untouched by the counterparty) so it
    # applies; the question is whether the second pass nests <w:ins><w:del>.
    multipass_edits = [
        ProposedEdit(
            "governed by the laws of England and Wales",
            "governed by the laws of England and Wales, and the parties submit to the "
            "exclusive jurisdiction of its courts",
            "Added exclusive jurisdiction.",
        ),
    ]
    res3 = svc.apply(cp, multipass_edits)
    write(f"{OUT}/fix3_multipass.docx", res3.docx_bytes)
    print(f"    fix3 applied={res3.edits_applied} skipped={res3.edits_skipped}")


if __name__ == "__main__":
    main()
