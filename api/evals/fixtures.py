"""Deterministic document fixtures for the F0-S9 qualification scenarios.

Two matters, content authored so every L1 metric has an unambiguous
ground truth (docs/fork/research/f0-s9-eval-reuse.md §3):

* ``SINGLE_DOC_MATTER`` — one MSA with a liability cap whose canonical
  language ("twelve (12) months", Excluded Claims) is quotable verbatim;
  the positive-grounding scenario checks the final answer for those
  fragments (zero-LLM grounding gate, oscar's char-overlap pattern).
* ``BATCH_MATTER`` — four small NDAs with DISTINCT governing law and
  term per document, so fan-out compliance is measurable both from
  per-task args (which NDA each subagent got) and from the final
  answer (all four laws present).

Content is plain text; the seeder writes it straight into
``documents.normalized_content`` + paragraph chunks (``content_tsv`` is
a generated column — FTS works without the ingest pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DocFixture:
    filename: str
    content: str


@dataclass(frozen=True)
class MatterFixture:
    name: str
    slug: str
    description: str
    documents: list[DocFixture] = field(default_factory=list)


_MSA = """\
MASTER SERVICES AGREEMENT

This Master Services Agreement (the "Agreement") is entered into between
Northwind Customer GmbH ("Customer") and Vendor Analytics Ltd ("Vendor").

1. SERVICES AND FEES. Vendor shall provide the data-processing services
described in each Statement of Work. Customer shall pay Vendor a monthly
service fee of USD 25,000, invoiced in arrears with thirty (30) day
payment terms.

2. TERM AND TERMINATION. This Agreement runs for an initial term of
twenty-four (24) months and renews for successive twelve (12) month
periods unless either party gives sixty (60) days written notice of
non-renewal. Either party may terminate for material breach not cured
within thirty (30) days of written notice.

3. CONFIDENTIALITY. Each party shall protect the other party's
Confidential Information with at least the care it applies to its own
similar information, and never less than reasonable care, and shall use
it solely to perform this Agreement.

4. LIMITATION OF LIABILITY. Except for the Excluded Claims, each party's
aggregate liability arising out of or relating to this Agreement shall
not exceed the total fees paid or payable by Customer in the twelve (12)
months preceding the first event giving rise to liability (the
"Liability Cap"). "Excluded Claims" means (a) a breach of
confidentiality obligations under Section 3, (b) a party's
indemnification obligations under Section 5, and (c) liability arising
from gross negligence or willful misconduct; the Liability Cap does not
apply to the Excluded Claims. Neither party is liable for indirect,
incidental, or consequential damages.

5. INDEMNIFICATION. Vendor shall defend and indemnify Customer against
third-party claims alleging that the services infringe a third party's
intellectual-property rights.

6. GOVERNING LAW. This Agreement is governed by the laws of the State of
Delaware, excluding its conflict-of-laws rules.
"""


def _nda(party: str, term: str, law: str) -> str:
    return f"""\
MUTUAL NON-DISCLOSURE AGREEMENT

This Mutual Non-Disclosure Agreement is entered into between Northwind
Customer GmbH and {party} (together, the "Parties").

1. PURPOSE. The Parties wish to explore a potential commercial
relationship and will exchange Confidential Information for that
purpose only.

2. OBLIGATIONS. Each Party shall hold the other Party's Confidential
Information in strict confidence, use it solely for the Purpose, and
disclose it only to representatives with a need to know who are bound
by obligations at least as protective as this Agreement.

3. TERM. The obligations in this Agreement run for {term} from the
Effective Date, except trade secrets, which remain protected for as
long as they qualify as trade secrets under applicable law.

4. GOVERNING LAW. This Agreement is governed by the laws of {law}.
"""


SINGLE_DOC_MATTER = MatterFixture(
    name="S9 Eval — Single Doc 9001",
    slug="s9-eval-single-doc-9001",
    description="F0-S9 qualification fixture: one MSA, liability-cap grounding.",
    documents=[DocFixture(filename="msa-vendor-services.txt", content=_MSA)],
)

BATCH_MATTER = MatterFixture(
    name="S9 Eval — Batch Fanout 9002",
    slug="s9-eval-batch-fanout-9002",
    description="F0-S9 qualification fixture: four NDAs with distinct law/term for fan-out.",
    documents=[
        DocFixture(
            filename="nda-alpha-systems.txt",
            content=_nda("Alpha Systems Inc.", "three (3) years", "the State of Delaware"),
        ),
        DocFixture(
            filename="nda-beta-logistics.txt",
            content=_nda("Beta Logistics LLC", "two (2) years", "the State of California"),
        ),
        DocFixture(
            filename="nda-gamma-labs.txt",
            content=_nda("Gamma Labs Corp.", "five (5) years", "the State of New York"),
        ),
        DocFixture(
            filename="nda-delta-marine.txt",
            content=_nda("Delta Marine Ltd.", "eighteen (18) months", "England and Wales"),
        ),
    ],
)

ALL_MATTERS = (SINGLE_DOC_MATTER, BATCH_MATTER)
