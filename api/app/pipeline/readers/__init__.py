"""Document-reader registry — multi-format matter ingestion (C1/C2, ADR-F029).

Replaces the single PDF MIME gate (``parsers.is_pdf_mime``) with an
injected ``MIME -> reader`` map. ``ingest_file`` takes a
:class:`ReaderRegistry`, defaulting to :func:`build_default_registry`,
and dispatches by the file's declared MIME after a server-side content
sniff. Each reader returns the existing ``ParsedDocument`` contract, so
the chunker, models, and persist path are untouched.

C2 adds the Outlook ``.msg`` reader and one-level attachment recursion:
the EML/MSG readers are wired with an :class:`AttachmentRecurser` here at
the composition root so a recursable attachment (office doc, nested email)
is extracted via the same registry.

See :mod:`app.pipeline.readers._base` for the reader protocol and the
shared offset/security helpers, and :mod:`app.pipeline.readers._message`
for the email assembly shared by the EML and MSG readers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.pipeline.readers._base import (
    AttachmentRecurser,
    DocumentReader,
    ParsedDocument,
    ReaderRegistry,
)
from app.pipeline.readers.docx import DocxReader
from app.pipeline.readers.eml import EmlReader
from app.pipeline.readers.msg import MsgReader
from app.pipeline.readers.pdf import PdfReader
from app.pipeline.readers.pptx import PptxReader
from app.pipeline.readers.xlsx import XlsxReader

if TYPE_CHECKING:
    from app.config import Settings

__all__ = [
    "DocumentReader",
    "DocxReader",
    "EmlReader",
    "MsgReader",
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
    permissive readers take no config. The EML/MSG readers are wired with a
    one-level attachment recurser so a recursable attachment is extracted via
    the registry. The registry is stateless and cheap, so it is built per
    call from settings rather than wired into ``app.state``.
    """

    eml = EmlReader()
    msg = MsgReader()
    registry = ReaderRegistry(
        [
            PdfReader(run_docling=settings.lq_ai_docling_enabled),
            XlsxReader(),
            eml,
            DocxReader(),
            PptxReader(),
            msg,
        ]
    )

    # C2: one-level attachment recursion. The factory mints a fresh depth-1
    # recurser per top-level email read; depth is carried per call (the
    # recurser is immutable), so a nested email recurses no further and
    # concurrent ingests can't clobber shared reader state.
    def _make_recurser() -> AttachmentRecurser:
        return AttachmentRecurser(registry, 1)

    eml.set_recurser_factory(_make_recurser)
    msg.set_recurser_factory(_make_recurser)
    return registry
