"""PDF reader — thin wrapper over the existing PyMuPDF/Docling cascade.

Keeps PDF behaviour byte-identical to the pre-C1 pipeline: it delegates
to :func:`app.pipeline.parsers.parse_pdf`, which lazily imports ``fitz``
(PyMuPDF). PyMuPDF is the project's only AGPL dependency; containing it
behind this single reader (and *only* here) keeps the AGPL boundary
intact — enforced by the CI import-guard test that asserts no reader
module imports ``fitz`` directly.
"""

from __future__ import annotations

from app.pipeline.parsers import SUPPORTED_PDF_MIMES, ParsedDocument, parse_pdf


class PdfReader:
    """Reads PDFs via the canonical PyMuPDF (+ optional Docling) cascade."""

    parser_label = "pymupdf"
    mimes = SUPPORTED_PDF_MIMES

    def __init__(self, *, run_docling: bool = True) -> None:
        self._run_docling = run_docling

    def sniff(self, data: bytes) -> bool:
        # The PDF spec allows up to 1024 bytes of leading junk before %PDF;
        # PyMuPDF tolerates it, so the sniff mirrors that tolerance.
        return b"%PDF" in data[:1024]

    def read(self, data: bytes) -> ParsedDocument:
        return parse_pdf(data, run_docling=self._run_docling)
