"""Document-reader registry — multi-format matter ingestion (C1, ADR-F029).

Replaces the single PDF MIME gate (``parsers.is_pdf_mime``) with an
injected ``MIME -> reader`` map. ``ingest_file`` takes a
:class:`ReaderRegistry`, defaulting to :func:`build_default_registry`,
and dispatches by the file's declared MIME after a server-side content
sniff. Each reader returns the existing ``ParsedDocument`` contract, so
the chunker, models, and persist path are untouched.

See :mod:`app.pipeline.readers._base` for the reader protocol and the
shared offset/security helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.pipeline.readers._base import (
    DocumentReader,
    ParsedDocument,
    ReaderRegistry,
)
from app.pipeline.readers.docx import DocxReader
from app.pipeline.readers.eml import EmlReader
from app.pipeline.readers.pdf import PdfReader
from app.pipeline.readers.pptx import PptxReader
from app.pipeline.readers.xlsx import XlsxReader

if TYPE_CHECKING:
    from app.config import Settings

__all__ = [
    "DocumentReader",
    "DocxReader",
    "EmlReader",
    "ParsedDocument",
    "PdfReader",
    "PptxReader",
    "ReaderRegistry",
    "XlsxReader",
    "build_default_registry",
]


def build_default_registry(settings: Settings) -> ReaderRegistry:
    """Construct the production reader set (the composition root).

    PDF preserves the Docling toggle (``lq_ai_docling_enabled``); the
    permissive readers (XLSX/EML/DOCX/PPTX) take no config. The registry
    is stateless and cheap, so it is built per call from settings rather
    than wired into ``app.state`` — revisit if a reader ever needs a
    heavyweight handle.
    """

    return ReaderRegistry(
        [
            PdfReader(run_docling=settings.lq_ai_docling_enabled),
            XlsxReader(),
            EmlReader(),
            DocxReader(),
            PptxReader(),
        ]
    )
