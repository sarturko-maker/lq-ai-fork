"""Reader protocol + shared offset/security helpers — C1 (ADR-F029).

The document-reader registry replaces the single PDF MIME gate
(``parsers.is_pdf_mime``) with an injected ``MIME -> reader`` map so a
matter ingests the formats a deal arrives in (PDF/DOCX/XLSX/PPTX/EML).
Every reader returns the *existing* :class:`app.pipeline.parsers.ParsedDocument`
contract, so the chunker, the ``Document``/``DocumentChunk`` models, and
the persist path stay byte-for-byte untouched.

Two invariants every reader owns:

* **Citation Engine offset fidelity** — ``canonical_text[start:end]``
  equals each chunk's ``content`` byte-for-byte. Because
  ``ingest`` sets ``normalized_content = parsed.canonical_text`` and the
  chunker slices that string, a reader holds the invariant simply by
  building ``canonical_text`` and tracking half-open ``[start, end)``
  unit spans against it. :func:`join_units` is the single source of
  offset truth (mirrors ``parsers._run_pymupdf``'s page-join accounting).
* **Untrusted input** — documents are untrusted (CLAUDE.md: prompt
  injection / XXE / SSRF / zip-bomb). OOXML files are zip containers of
  XML; :func:`guard_ooxml` rejects entity-bearing XML *before* the
  parsing library sees the bytes (so lxml never expands an entity) and
  bounds decompression. EML bodies are extracted with the stdlib only
  (no remote fetch, no attachment recursion — that's C2).

Heavy parser libraries (openpyxl/python-docx/python-pptx) are imported
*lazily inside each reader* — mirroring ``parsers.py`` — so this package
imports cleanly in environments where they are not installed.
"""

from __future__ import annotations

import importlib.metadata
import zipfile
from collections.abc import Iterable
from io import BytesIO
from typing import Protocol, runtime_checkable

from app.pipeline.parsers import (
    PageSpan,
    ParsedDocument,
    ParserError,
    ParserUnsupported,
)

__all__ = [
    "EML_MIME",
    "OOXML_DOCX_MIME",
    "OOXML_PPTX_MIME",
    "OOXML_XLSX_MIME",
    "DocumentReader",
    "PageSpan",
    "ParsedDocument",
    "ParserError",
    "ParserUnsupported",
    "ReaderRegistry",
    "build_parsed_document",
    "dist_version",
    "guard_ooxml",
    "join_units",
    "ooxml_subtype",
]


# ---------------------------------------------------------------------------
# Canonical MIME types
# ---------------------------------------------------------------------------

OOXML_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
OOXML_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
OOXML_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
EML_MIME = "message/rfc822"


# ---------------------------------------------------------------------------
# Reader protocol + registry
# ---------------------------------------------------------------------------


@runtime_checkable
class DocumentReader(Protocol):
    """A byte-stream reader for one document family.

    ``mimes`` are the declared MIME strings this reader claims (matched
    case-insensitively by the registry). ``sniff`` is a server-side
    content cross-check used at the ingest boundary to reject a file
    whose *bytes* contradict its *declared* type (reject-don't-guess).
    ``read`` returns the canonical :class:`ParsedDocument`.
    """

    parser_label: str
    mimes: frozenset[str]

    def sniff(self, data: bytes) -> bool: ...

    def read(self, data: bytes) -> ParsedDocument: ...


class ReaderRegistry:
    """An injected ``MIME -> reader`` map (the C1 DI seam).

    Built once at the composition root (:func:`build_default_registry`)
    and threaded into ``ingest_file``; tests substitute fakes through the
    same seam rather than monkeypatching module globals.
    """

    def __init__(self, readers: Iterable[DocumentReader]) -> None:
        self._by_mime: dict[str, DocumentReader] = {}
        for reader in readers:
            for mime in reader.mimes:
                self._by_mime[mime.lower()] = reader

    def for_mime(self, mime: str) -> DocumentReader | None:
        """Return the reader for ``mime`` (params stripped, lowercased), or None."""

        key = mime.split(";", 1)[0].strip().lower()
        return self._by_mime.get(key)

    def supported_mimes(self) -> frozenset[str]:
        return frozenset(self._by_mime)


# ---------------------------------------------------------------------------
# Offset accounting — the single source of fidelity truth
# ---------------------------------------------------------------------------


def join_units(unit_texts: list[str]) -> tuple[str, list[PageSpan]]:
    """Join per-unit texts with a single newline, recording ``[start, end)`` spans.

    Mirrors ``parsers._run_pymupdf``'s page-join accounting exactly: each
    unit's span is recorded *before* the inter-unit join newline is
    counted, and the running offset is asserted equal to the canonical
    length so any drift fails closed rather than corrupting chunk
    offsets downstream. ``page_number`` is the 1-based unit ordinal
    (sheet / paragraph-block / slide / message — see each reader).
    """

    pages: list[PageSpan] = []
    running = 0
    last = len(unit_texts) - 1
    for idx, text in enumerate(unit_texts):
        pages.append(
            PageSpan(page_number=idx + 1, char_start=running, char_end=running + len(text))
        )
        running += len(text)
        if idx < last:
            running += 1  # account for the join newline

    canonical = "\n".join(unit_texts)
    if running != len(canonical):  # pragma: no cover - defensive
        raise ParserError(
            f"reader offset accounting drift: running={running}, canonical_len={len(canonical)}"
        )
    return canonical, pages


def build_parsed_document(
    unit_texts: list[str], *, parser: str, parser_version: str
) -> ParsedDocument:
    """Join unit texts and wrap them in the canonical :class:`ParsedDocument`.

    Shared by the unit-based readers (XLSX/DOCX/PPTX); EML builds its own
    single whole-message span. Offset fidelity is owned by
    :func:`join_units`. ``structured_content`` is ``None`` (only the PDF
    cascade produces Docling structure).
    """

    canonical, pages = join_units(unit_texts)
    return ParsedDocument(
        canonical_text=canonical,
        pages=pages,
        page_count=len(pages),
        parser=parser,
        parser_version=parser_version,
        structured_content=None,
    )


# ---------------------------------------------------------------------------
# OOXML security helpers (XXE / entity-expansion / zip-bomb)
# ---------------------------------------------------------------------------

# Safety ceilings for OOXML zip containers (untrusted input). These are
# defensive bounds, not tuning knobs — a legitimate office document is far
# under them; a zip bomb is far over. The upload itself is already capped
# (LQ_AI_MAX_UPLOAD_SIZE_MB, default 100 MB compressed).
MAX_OOXML_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_OOXML_ENTRIES = 5_000
# XML declarations (DOCTYPE / ENTITY) are only legal in the prolog, so a
# bounded head read of each XML part catches them regardless of a lying
# central directory. Valid OOXML never contains a DTD.
_XML_PROLOG_SCAN_BYTES = 65_536
# [Content_Types].xml is tiny in legitimate files; bound the read so a
# bomb cannot blow up the content-sniff path.
_CONTENT_TYPES_READ_CAP = 1_048_576

_SUBTYPE_MARKERS: tuple[tuple[bytes, str], ...] = (
    (b"wordprocessingml.document.main", "docx"),
    (b"spreadsheetml.sheet.main", "xlsx"),
    (b"presentationml.presentation.main", "pptx"),
)


def ooxml_subtype(data: bytes) -> str | None:
    """Return ``'docx'``/``'xlsx'``/``'pptx'`` by inspecting the OOXML container.

    Reads the in-zip ``[Content_Types].xml`` and matches the main-part
    content type — distinguishing the OOXML subtypes that share the zip
    magic ``PK\\x03\\x04`` (so a ``.xlsx`` renamed ``.docx`` is caught).
    Returns ``None`` for non-zip bytes or an unrecognised/corrupt
    container. Read-bounded; never raises on bad input.
    """

    if not data.startswith(b"PK\x03\x04"):
        return None
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf, zf.open("[Content_Types].xml") as fh:
            content_types = fh.read(_CONTENT_TYPES_READ_CAP).lower()
    except (zipfile.BadZipFile, KeyError, OSError):
        return None
    for marker, subtype in _SUBTYPE_MARKERS:
        if marker in content_types:
            return subtype
    return None


def guard_ooxml(
    data: bytes,
    *,
    max_uncompressed: int = MAX_OOXML_UNCOMPRESSED_BYTES,
    max_entries: int = MAX_OOXML_ENTRIES,
) -> None:
    """Reject a hostile OOXML container before any parser library opens it.

    Three checks, all on untrusted bytes:

    * **entry-count cap** — a zip with absurdly many members,
    * **decompressed-size cap** — a classic zip bomb (small compressed,
      huge declared uncompressed),
    * **DOCTYPE/ENTITY scan** — any ``<!DOCTYPE``/``<!ENTITY`` in an XML
      part's prolog (XXE / billion-laughs). Valid OOXML never declares a
      DTD, so this is a true-positive-only reject; doing it *here* means
      python-docx/python-pptx (lxml) never see an entity to expand.

    Raises :class:`ParserError` for a non-zip and :class:`ParserUnsupported`
    for a file that is a zip but violates a safety bound.
    """

    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ParserError(f"not a valid OOXML (zip) container: {exc}") from exc

    with zf:
        infos = zf.infolist()
        if len(infos) > max_entries:
            raise ParserUnsupported(f"OOXML entry count {len(infos)} exceeds cap {max_entries}")
        total = sum(info.file_size for info in infos)
        if total > max_uncompressed:
            raise ParserUnsupported(
                f"OOXML decompressed size {total} exceeds cap {max_uncompressed}"
            )
        for info in infos:
            name = info.filename.lower()
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            with zf.open(info) as fh:
                prolog = fh.read(_XML_PROLOG_SCAN_BYTES).lower()
            if b"<!doctype" in prolog or b"<!entity" in prolog:
                raise ParserUnsupported(
                    "OOXML XML part declares a DOCTYPE/ENTITY (rejected: XXE / entity-expansion)"
                )


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def dist_version(dist_name: str) -> str:
    """Return an installed distribution's version, defensively (``'unknown'``)."""

    try:
        return importlib.metadata.version(dist_name)
    except Exception:  # pragma: no cover - defensive
        return "unknown"
