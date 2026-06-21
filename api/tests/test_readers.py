"""Unit tests for the C1 document-reader registry (ADR-F029).

Covers, per reader (XLSX/EML/DOCX/PPTX) and for the registry:

* the Citation-Engine offset invariant ``canonical_text[start:end] ==
  chunk.content`` for every chunk, and tiling unit spans;
* the registry dispatch (case-insensitive, param-stripping, miss=None);
* the server-side content ``sniff`` (rejects a renamed/spoofed file);
* the OOXML security guard (DOCTYPE/ENTITY reject + zip-bomb caps);
* EML non-recursion into attachments and HTML body stripping.

Heavy parser libs are imported lazily; tests that build a fixture
``importorskip`` the relevant library so a lib-less runner skips rather
than fails (mirrors ``test_pipeline_ingest``'s ``importorskip('fitz')``).
"""

from __future__ import annotations

import ast
import io
import pathlib
import types
import zipfile

import pytest

from app.pipeline.chunker import chunk_document
from app.pipeline.parsers import ParsedDocument, ParserError, ParserUnsupported
from app.pipeline.readers import (
    DocxReader,
    EmlReader,
    PdfReader,
    PptxReader,
    ReaderRegistry,
    XlsxReader,
    build_default_registry,
)
from app.pipeline.readers._base import (
    EML_MIME,
    OOXML_DOCX_MIME,
    OOXML_PPTX_MIME,
    OOXML_XLSX_MIME,
    guard_ooxml,
    join_units,
    ooxml_subtype,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixture generators (lazy — skip if the lib isn't installed)
# ---------------------------------------------------------------------------


def _make_xlsx() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Pricing"
    ws1.append(["Item", "Qty", "Unit"])
    ws1.append(["Widget", 10, "GBP 4.50"])
    ws2 = wb.create_sheet("Terms")
    ws2.append(["Liability cap", "12 months fees"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_docx() -> bytes:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Mutual Non-Disclosure Agreement.")
    document.add_paragraph("1. Confidential Information means any non-public information.")
    document.add_paragraph("2. The term of this Agreement is two (2) years.")
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _make_pptx() -> bytes:
    pptx = pytest.importorskip("pptx")
    presentation = pptx.Presentation()
    blank = presentation.slide_layouts[6]
    for title in ("Deal overview", "Key risks"):
        slide = presentation.slides.add_slide(blank)
        box = slide.shapes.add_textbox(left=0, top=0, width=914400, height=914400)
        box.text_frame.text = f"{title}: see notes."
    buf = io.BytesIO()
    presentation.save(buf)
    return buf.getvalue()


_EML_PLAIN = (
    b"From: alice@example.com\r\n"
    b"To: bob@example.com\r\n"
    b"Subject: Deal terms\r\n"
    b"Date: Mon, 1 Jun 2026 10:00:00 +0000\r\n"
    b"\r\n"
    b"Please find our position on the liability cap below.\r\n"
)

_EML_HTML_ONLY = (
    b"From: alice@example.com\r\n"
    b"Subject: HTML only\r\n"
    b'Content-Type: text/html; charset="utf-8"\r\n'
    b"\r\n"
    b"<html><body><p>Hello <b>world</b></p>"
    b"<script>evil_tracker()</script></body></html>\r\n"
)


def _make_eml_with_attachment() -> bytes:
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "With attachment"
    msg["Date"] = "Mon, 1 Jun 2026 10:00:00 +0000"
    msg.set_content("Inline body text about the matter.")
    msg.add_attachment(
        b"SECRET_ATTACHMENT_CONTENT",
        maintype="application",
        subtype="octet-stream",
        filename="secret.bin",
    )
    return msg.as_bytes()


def _inject_doctype(ooxml: bytes, part: str) -> bytes:
    """Return a copy of an OOXML file with a DOCTYPE/ENTITY in one XML part."""

    doctype = '<!DOCTYPE root [<!ENTITY xxe "boom">]>'
    out_buf = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(ooxml)) as src,
        zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out,
    ):
        for info in src.infolist():
            content = src.read(info.filename)
            if info.filename == part:
                text = content.decode("utf-8", "replace")
                if text.startswith("<?xml"):
                    cut = text.find("?>") + 2
                    text = text[:cut] + doctype + text[cut:]
                else:
                    text = doctype + text
                content = text.encode("utf-8")
            out.writestr(info, content)
    return out_buf.getvalue()


# ---------------------------------------------------------------------------
# Shared assertions
# ---------------------------------------------------------------------------


def _assert_spans_tile(parsed: ParsedDocument) -> None:
    """Unit spans tile the canonical text: ordered, in-bounds, single join."""

    text = parsed.canonical_text
    pages = parsed.pages
    assert parsed.page_count == len(pages)
    if not pages:
        assert text == ""
        return
    assert pages[0].char_start == 0
    assert pages[-1].char_end == len(text)
    for idx, span in enumerate(pages):
        assert span.page_number == idx + 1
        assert 0 <= span.char_start <= span.char_end <= len(text)
        if idx + 1 < len(pages):
            nxt = pages[idx + 1]
            # exactly one join newline between consecutive units
            assert nxt.char_start == span.char_end + 1
            assert text[span.char_end : nxt.char_start] == "\n"


def _assert_chunk_fidelity(parsed: ParsedDocument) -> int:
    chunks = chunk_document(parsed, target_chars=120, overlap_chars=20)
    for chunk in chunks:
        slice_ = parsed.canonical_text[chunk.char_offset_start : chunk.char_offset_end]
        assert slice_ == chunk.content, f"fidelity broken at chunk {chunk.chunk_index}"
    return len(chunks)


# ---------------------------------------------------------------------------
# join_units — the single source of offset truth
# ---------------------------------------------------------------------------


def test_join_units_tracks_offsets_with_join_newline() -> None:
    canonical, pages = join_units(["a", "bb", "ccc"])
    assert canonical == "a\nbb\nccc"
    assert [(p.page_number, p.char_start, p.char_end) for p in pages] == [
        (1, 0, 1),
        (2, 2, 4),
        (3, 5, 8),
    ]
    for span in pages:
        assert (
            canonical[span.char_start : span.char_end] == ["a", "bb", "ccc"][span.page_number - 1]
        )


def test_join_units_empty_and_single() -> None:
    assert join_units([]) == ("", [])
    canonical, pages = join_units(["only"])
    assert canonical == "only"
    assert (pages[0].char_start, pages[0].char_end) == (0, 4)


# ---------------------------------------------------------------------------
# Per-reader: offset invariant + spans + parser label
# ---------------------------------------------------------------------------


def test_xlsx_reader_invariant_and_spans() -> None:
    parsed = XlsxReader().read(_make_xlsx())
    assert parsed.parser == "openpyxl"
    assert parsed.page_count == 2  # one unit per worksheet
    assert "# Pricing" in parsed.canonical_text and "# Terms" in parsed.canonical_text
    assert "Widget" in parsed.canonical_text
    _assert_spans_tile(parsed)
    # each worksheet's span slices back to its OWN sheet content
    pricing, terms = parsed.pages
    assert "# Pricing" in parsed.canonical_text[pricing.char_start : pricing.char_end]
    assert "# Terms" in parsed.canonical_text[terms.char_start : terms.char_end]
    assert _assert_chunk_fidelity(parsed) > 0


def test_docx_reader_invariant_and_spans() -> None:
    parsed = DocxReader().read(_make_docx())
    assert parsed.parser == "python-docx"
    assert parsed.page_count == 3  # one unit per paragraph block
    assert "Non-Disclosure" in parsed.canonical_text
    _assert_spans_tile(parsed)
    assert _assert_chunk_fidelity(parsed) > 0


def test_pptx_reader_invariant_and_spans() -> None:
    parsed = PptxReader().read(_make_pptx())
    assert parsed.parser == "python-pptx"
    assert parsed.page_count == 2  # one unit per slide
    assert "Deal overview" in parsed.canonical_text
    _assert_spans_tile(parsed)
    assert _assert_chunk_fidelity(parsed) > 0


def test_eml_reader_invariant_and_single_unit() -> None:
    parsed = EmlReader().read(_EML_PLAIN)
    assert parsed.parser == "eml"
    assert parsed.page_count == 1  # whole message is one unit
    assert "From: alice@example.com" in parsed.canonical_text
    assert "Subject: Deal terms" in parsed.canonical_text
    assert "liability cap" in parsed.canonical_text
    _assert_spans_tile(parsed)
    assert _assert_chunk_fidelity(parsed) > 0


# ---------------------------------------------------------------------------
# EML behaviours: non-recursion, HTML stripping
# ---------------------------------------------------------------------------


def test_eml_does_not_recurse_into_attachments() -> None:
    parsed = EmlReader().read(_make_eml_with_attachment())
    assert parsed.page_count == 1
    assert "Inline body text about the matter." in parsed.canonical_text
    # The attachment's bytes/name never leak into the extracted text (C2 boundary).
    assert "SECRET_ATTACHMENT_CONTENT" not in parsed.canonical_text
    assert "secret.bin" not in parsed.canonical_text


def test_eml_html_only_is_stripped_to_text() -> None:
    parsed = EmlReader().read(_EML_HTML_ONLY)
    assert "Hello" in parsed.canonical_text
    assert "world" in parsed.canonical_text
    # tags and <script> contents are dropped.
    assert "<b>" not in parsed.canonical_text
    assert "evil_tracker" not in parsed.canonical_text


# ---------------------------------------------------------------------------
# Registry dispatch
# ---------------------------------------------------------------------------


def test_registry_dispatch_by_mime() -> None:
    settings = types.SimpleNamespace(lq_ai_docling_enabled=False)
    registry = build_default_registry(settings)
    assert isinstance(registry.for_mime("application/pdf"), PdfReader)
    assert isinstance(registry.for_mime(OOXML_DOCX_MIME), DocxReader)
    assert isinstance(registry.for_mime(OOXML_XLSX_MIME), XlsxReader)
    assert isinstance(registry.for_mime(OOXML_PPTX_MIME), PptxReader)
    assert isinstance(registry.for_mime(EML_MIME), EmlReader)
    # case-insensitive + parameter-stripping
    assert isinstance(registry.for_mime("APPLICATION/PDF"), PdfReader)
    assert isinstance(registry.for_mime("application/pdf; charset=binary"), PdfReader)
    # miss
    assert registry.for_mime("text/plain") is None
    assert registry.for_mime("application/octet-stream") is None


def test_registry_keys_are_lowercased() -> None:
    class _Fake:
        parser_label = "fake"
        mimes = frozenset({"Application/Weird"})

        def sniff(self, data: bytes) -> bool:
            return True

        def read(self, data: bytes) -> ParsedDocument:  # pragma: no cover
            raise NotImplementedError

    registry = ReaderRegistry([_Fake()])
    assert registry.for_mime("application/weird") is not None
    assert registry.supported_mimes() == frozenset({"application/weird"})


# ---------------------------------------------------------------------------
# Server-side content sniff (spoof rejection)
# ---------------------------------------------------------------------------


def test_pdf_sniff() -> None:
    reader = PdfReader(run_docling=False)
    assert reader.sniff(b"%PDF-1.7\n...") is True
    assert reader.sniff(b"   %PDF-1.4 leading junk allowed") is True
    assert reader.sniff(b"this is not a pdf") is False


def test_ooxml_sniff_matches_true_subtype() -> None:
    docx_bytes, xlsx_bytes, pptx_bytes = _make_docx(), _make_xlsx(), _make_pptx()
    assert DocxReader().sniff(docx_bytes) is True
    assert XlsxReader().sniff(xlsx_bytes) is True
    assert PptxReader().sniff(pptx_bytes) is True
    # a renamed/spoofed OOXML is rejected (xlsx bytes declared as docx, etc.)
    assert DocxReader().sniff(xlsx_bytes) is False
    assert XlsxReader().sniff(docx_bytes) is False
    assert PptxReader().sniff(docx_bytes) is False
    # plain bytes are not OOXML at all
    assert DocxReader().sniff(b"hello world") is False
    assert ooxml_subtype(b"hello world") is None


def test_eml_sniff_accepts_text() -> None:
    # message/rfc822 has no reliable magic, so the sniff cannot reject; documented.
    assert EmlReader().sniff(b"anything") is True


# ---------------------------------------------------------------------------
# OOXML security guard
# ---------------------------------------------------------------------------


def test_guard_rejects_doctype_entity() -> None:
    malicious = _inject_doctype(_make_docx(), "word/document.xml")
    with pytest.raises(ParserUnsupported):
        guard_ooxml(malicious)
    # and the reader refuses it end-to-end (before python-docx/lxml opens it)
    with pytest.raises(ParserUnsupported):
        DocxReader().read(malicious)


def test_guard_zip_bomb_caps() -> None:
    docx_bytes = _make_docx()
    with pytest.raises(ParserUnsupported):
        guard_ooxml(docx_bytes, max_entries=0)
    with pytest.raises(ParserUnsupported):
        guard_ooxml(docx_bytes, max_uncompressed=1)


def test_guard_rejects_non_zip() -> None:
    with pytest.raises(ParserError):
        guard_ooxml(b"this is definitely not a zip container")


# ---------------------------------------------------------------------------
# AGPL boundary: no reader imports fitz
# ---------------------------------------------------------------------------


def test_no_reader_module_imports_fitz() -> None:
    readers_dir = pathlib.Path(__file__).resolve().parents[1] / "app" / "pipeline" / "readers"
    offenders: list[tuple[str, str]] = []
    for py in sorted(readers_dir.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "fitz" or alias.name.startswith("fitz."):
                        offenders.append((py.name, alias.name))
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and (node.module == "fitz" or node.module.startswith("fitz."))
            ):
                offenders.append((py.name, node.module))
    assert offenders == [], (
        "reader modules must not import fitz — the AGPL boundary stays behind "
        f"parsers.PdfReader (ADR-F029). Offenders: {offenders}"
    )


# ---------------------------------------------------------------------------
# Review fixes (C1 adversarial review): fail-closed OOXML, plain>html, empties
# ---------------------------------------------------------------------------


def _strip_part(ooxml: bytes, part: str) -> bytes:
    """Return a copy of an OOXML file with one zip part removed."""

    out_buf = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(ooxml)) as src,
        zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out,
    ):
        for info in src.infolist():
            if info.filename == part:
                continue
            out.writestr(info, src.read(info.filename))
    return out_buf.getvalue()


_OOXML_CASES = [
    (DocxReader(), _make_docx, "word/document.xml"),
    (XlsxReader(), _make_xlsx, "xl/workbook.xml"),
    (PptxReader(), _make_pptx, "ppt/presentation.xml"),
]


@pytest.mark.parametrize(("reader", "make", "main_part"), _OOXML_CASES)
def test_malformed_ooxml_passing_sniff_fails_closed(reader, make, main_part) -> None:
    """A container that passes sniff but is missing its main part must raise
    ParserError (-> ingestion parse_failed), not escape as a bare library
    KeyError/XMLSyntaxError that the worker would mistake for a retriable error."""

    broken = _strip_part(make(), main_part)
    assert reader.sniff(broken) is True  # [Content_Types].xml intact -> sniff passes
    with pytest.raises(ParserError):
        reader.read(broken)


@pytest.mark.parametrize(("reader", "make", "main_part"), _OOXML_CASES)
def test_guard_rejects_doctype_across_all_ooxml(reader, make, main_part) -> None:
    malicious = _inject_doctype(make(), main_part)
    with pytest.raises(ParserUnsupported):
        reader.read(malicious)


def test_eml_prefers_plain_over_html() -> None:
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = "a@x.com"
    msg["Subject"] = "alternative"
    msg.set_content("PLAINTEXT body wins.")
    msg.add_alternative("<html><body><p>HTML body loses.</p></body></html>", subtype="html")
    parsed = EmlReader().read(msg.as_bytes())
    assert "PLAINTEXT body wins." in parsed.canonical_text
    assert "HTML body loses" not in parsed.canonical_text


def test_empty_documents_degrade_cleanly() -> None:
    docx = pytest.importorskip("docx")
    pptx = pytest.importorskip("pptx")
    openpyxl = pytest.importorskip("openpyxl")

    empty_docx = io.BytesIO()
    docx.Document().save(empty_docx)
    _assert_spans_tile(DocxReader().read(empty_docx.getvalue()))

    empty_pptx = io.BytesIO()
    pptx.Presentation().save(empty_pptx)
    parsed_pptx = PptxReader().read(empty_pptx.getvalue())
    assert parsed_pptx.canonical_text == "" and parsed_pptx.pages == []

    empty_xlsx = io.BytesIO()
    openpyxl.Workbook().save(empty_xlsx)  # one empty default sheet
    _assert_spans_tile(XlsxReader().read(empty_xlsx.getvalue()))

    # headers only, no body -> single message unit, spans tile
    _assert_spans_tile(EmlReader().read(b"From: a@x.com\r\nSubject: empty\r\n\r\n"))
