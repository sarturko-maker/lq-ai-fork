"""Generate the C5 PDF fixtures.

Run from the repo root via the api/.venv after installing pymupdf::

    api/.venv/bin/python api/tests/fixtures/pdfs/_make_fixtures.py

The fixtures are synthetic invented content with no legal substance,
per CLAUDE.md (agents do not author legal-substance content). Each is
designed to exercise a specific corner of the chunker's
character-fidelity invariant:

* ``simple_text.pdf`` — single page, plain prose. The "did the
  pipeline work at all?" smoke fixture.
* ``multipage.pdf`` — three pages of prose with paragraph breaks
  spanning page boundaries. Exercises the page-span tracking and
  the chunker's behaviour at page-join newlines.
* ``two_column.pdf`` — visually two-column layout. PyMuPDF flattens
  the columns into reading order; this fixture exercises a layout
  PDFs commonly produce that PyMuPDF has to interpret.

We commit the produced PDFs into the fixtures directory so test runs
don't require PyMuPDF at fixture-creation time. Re-running this
script is idempotent — it overwrites the fixtures.
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz  # PyMuPDF


def make_simple_pdf(out: Path) -> None:
    """Produce a one-page PDF of simple prose for the smoke test."""

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 72),
        (
            "The Quick Reference Guide to Process Documentation\n\n"
            "This document explains how to write process documentation "
            "that other people can actually use. The first rule is to "
            "write for the reader, not for yourself.\n\n"
            "When documenting any process, start with the desired "
            "outcome. Then describe the precondition: what state "
            "the system must be in before the process can run. Then "
            "describe the steps. Then describe the validation: how "
            "the reader confirms that the process succeeded.\n\n"
            "The most common documentation failure is to skip the "
            "validation step. Without it, the reader has no way to "
            "tell whether they followed the steps correctly. The "
            "second most common failure is to assume context the "
            "reader does not have. Process documentation that "
            "starts with 'after the regular setup is complete' "
            "presumes that 'the regular setup' is well-known. "
            "It rarely is.\n\n"
            "A third failure mode is to use jargon that the reader "
            "may not know. Every domain has its own terminology, "
            "and the writer becomes blind to it. The reader does "
            "not have that blindness."
        ),
        fontsize=11,
    )
    doc.save(str(out))
    doc.close()


def make_multipage_pdf(out: Path) -> None:
    """Three pages of prose with paragraph breaks spanning page boundaries."""

    doc = fitz.open()
    pages_text = [
        (
            "Chapter One — On Beginnings\n\n"
            "Every project begins with a question. The question is "
            "rarely the right one, but it is the one available, and "
            "it is the one you start with. The discipline is to keep "
            "the question alive even after it stops being convenient.\n\n"
            "Beginnings are the part of a project that subsequent "
            "decisions tax most. A choice made on day one constrains "
            "every choice on day fifty. Most beginnings are made in "
            "haste, with insufficient information, and yet they are "
            "the most consequential."
        ),
        (
            "Chapter Two — On the Middle\n\n"
            "The middle is where the project gets unpleasant. The "
            "early enthusiasm is gone, the end is not yet in sight, "
            "and the work that remains is mostly uninteresting. "
            "This is where most projects die.\n\n"
            "Discipline in the middle looks like deciding what NOT "
            "to do. Every middle has dozens of paths that lead "
            "somewhere interesting but not where the project is "
            "going. The discipline is to recognize them as such and "
            "decline."
        ),
        (
            "Chapter Three — On the End\n\n"
            "Endings, when they finally arrive, are anticlimactic. "
            "The project that consumed your attention for months is "
            "suddenly done, and the world is largely unchanged.\n\n"
            "This is correct. The world's changing, when it happens, "
            "is gradual and rarely traceable to a single project's "
            "ending. The project's ending is for the project. The "
            "world's changing is for later."
        ),
    ]
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((50, 72), text, fontsize=11)
    doc.save(str(out))
    doc.close()


def make_two_column_pdf(out: Path) -> None:
    """Two-column layout: PyMuPDF flattens to reading order.

    We render two text-boxes side by side. PyMuPDF's text extraction
    flattens this into a single text stream — the chunker treats it
    as ordinary text. The fidelity invariant still holds: whatever
    PyMuPDF returns is the canonical stream, and the chunker slices
    against it.
    """

    doc = fitz.open()
    page = doc.new_page()
    left = (
        "Left column. The discipline of writing in columns is the "
        "discipline of writing for layout instead of writing for "
        "voice. Newspapers have done this for centuries; long-form "
        "essays do it less."
    )
    right = (
        "Right column. The right column continues a thought that is "
        "different from the left column's thought. They share the "
        "page but not the argument. Most readers will read the left "
        "first, then the right."
    )
    page.insert_textbox(
        fitz.Rect(50, 72, 270, 720),
        left,
        fontsize=11,
    )
    page.insert_textbox(
        fitz.Rect(290, 72, 510, 720),
        right,
        fontsize=11,
    )
    doc.save(str(out))
    doc.close()


def main() -> int:
    here = Path(__file__).resolve().parent
    here.mkdir(parents=True, exist_ok=True)
    make_simple_pdf(here / "simple_text.pdf")
    make_multipage_pdf(here / "multipage.pdf")
    make_two_column_pdf(here / "two_column.pdf")
    print("Wrote 3 fixture PDFs to", here)
    return 0


if __name__ == "__main__":
    sys.exit(main())
