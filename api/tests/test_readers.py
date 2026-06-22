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
    MsgReader,
    PdfReader,
    PptxReader,
    ReaderRegistry,
    XlsxReader,
    _message as _msg_mod,
    build_default_registry,
)
from app.pipeline.readers._base import (
    EML_MIME,
    MSG_MIME,
    MSG_MIME_ALT,
    OOXML_DOCX_MIME,
    OOXML_PPTX_MIME,
    OOXML_XLSX_MIME,
    guard_ooxml,
    join_units,
    ooxml_subtype,
)
from app.pipeline.readers._message import (
    NormalizedAttachment,
    NormalizedMessage,
    assemble_email,
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


_DOCX_SUBTYPE = "vnd.openxmlformats-officedocument.wordprocessingml.document"


def _make_eml_with_docx_attachment() -> bytes:
    from email.message import EmailMessage

    docx_bytes = _make_docx()  # importorskip docx
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "NDA attached"
    msg["Date"] = "Mon, 1 Jun 2026 10:00:00 +0000"
    msg.set_content("See the attached NDA for the cap position.")
    msg.add_attachment(
        docx_bytes, maintype="application", subtype=_DOCX_SUBTYPE, filename="nda.docx"
    )
    return msg.as_bytes()


def _make_eml_with_nested_eml_with_docx() -> bytes:
    """Outer email → forwarded (message/rfc822) email → which has a .docx attachment."""
    from email.message import EmailMessage

    inner = EmailMessage()
    inner["From"] = "deep@example.com"
    inner["Subject"] = "Inner forwarded note"
    inner.set_content("INNER BODY MARKER about indemnities.")
    inner.add_attachment(
        _make_docx(), maintype="application", subtype=_DOCX_SUBTYPE, filename="deep.docx"
    )

    outer = EmailMessage()
    outer["From"] = "mid@example.com"
    outer["To"] = "legal@example.com"
    outer["Subject"] = "Fwd: the chain"
    outer.set_content("OUTER BODY about the deal.")
    outer.add_attachment(inner)  # EmailMessage -> message/rfc822 part
    return outer.as_bytes()


class _FakeRecurser:
    """Stand-in recurser: extracts any attachment to a marker text."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def recurse(self, mime: str, data: bytes) -> ParsedDocument:
        self.calls.append(mime)
        return ParsedDocument(
            canonical_text=f"EXTRACTED[{mime}]",
            pages=[],
            page_count=0,
            parser="fake",
            parser_version="0",
        )


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


def test_eml_lists_attachment_without_recurser() -> None:
    # C2: a bare reader (no recurser wired) acknowledges the attachment with
    # an inline label but does NOT extract its bytes.
    parsed = EmlReader().read(_make_eml_with_attachment())
    assert parsed.page_count == 2  # message unit + 1 listed attachment unit
    assert "Inline body text about the matter." in parsed.canonical_text
    assert "secret.bin" in parsed.canonical_text  # listed (filename in the label)
    assert "not text-extracted" in parsed.canonical_text
    # The attachment's BYTES are not extracted (no recurser).
    assert "SECRET_ATTACHMENT_CONTENT" not in parsed.canonical_text
    _assert_spans_tile(parsed)
    assert _assert_chunk_fidelity(parsed) > 0
    sc = parsed.structured_content
    assert sc is not None
    assert sc["attachments"][0]["filename"] == "secret.bin"
    assert sc["attachments"][0]["status"] == "not text-extracted"


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
    assert isinstance(registry.for_mime(MSG_MIME), MsgReader)
    assert isinstance(registry.for_mime(MSG_MIME_ALT), MsgReader)
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


# ---------------------------------------------------------------------------
# C2 — email-chain assembly, one-level attachment recursion, caps
# ---------------------------------------------------------------------------


def _wired_eml() -> EmlReader:
    settings = types.SimpleNamespace(lq_ai_docling_enabled=False)
    registry = build_default_registry(settings)
    reader = registry.for_mime(EML_MIME)
    assert isinstance(reader, EmlReader)
    return reader


def test_eml_recurses_office_attachment_when_wired() -> None:
    pytest.importorskip("docx")
    parsed = _wired_eml().read(_make_eml_with_docx_attachment())
    assert parsed.page_count == 2  # message + recursed attachment
    # message body + the attachment's EXTRACTED text both present + grounded.
    assert "See the attached NDA" in parsed.canonical_text
    assert "Mutual Non-Disclosure Agreement." in parsed.canonical_text
    assert "nda.docx" in parsed.canonical_text  # inline provenance label
    _assert_spans_tile(parsed)
    assert _assert_chunk_fidelity(parsed) > 0
    sc = parsed.structured_content
    assert sc is not None
    att = sc["attachments"][0]
    assert att["filename"] == "nda.docx"
    assert str(att["status"]).startswith("extracted via")
    assert sc["messages"][0]["from"] == "alice@example.com"
    assert sc["caps"]["attachments_total"] == 1


def test_eml_attachment_recursion_is_one_level() -> None:
    pytest.importorskip("docx")
    parsed = _wired_eml().read(_make_eml_with_nested_eml_with_docx())
    text = parsed.canonical_text
    assert "OUTER BODY about the deal." in text
    # depth-1: the forwarded email's body IS extracted...
    assert "INNER BODY MARKER about indemnities." in text
    # ...and the forwarded email LISTS its own attachment...
    assert "deep.docx" in text
    # ...but depth-2 extraction is blocked: the inner .docx text is absent.
    assert "Mutual Non-Disclosure Agreement." not in text
    _assert_spans_tile(parsed)
    assert _assert_chunk_fidelity(parsed) > 0


def test_assemble_email_attachment_count_cap(monkeypatch) -> None:
    monkeypatch.setattr(_msg_mod, "MAX_EMAIL_ATTACHMENTS", 2)
    attachments = [
        NormalizedAttachment(filename=f"a{i}.docx", mime=OOXML_DOCX_MIME, data=b"x")
        for i in range(4)
    ]
    message = NormalizedMessage(headers={"from": "a@x.com"}, body="hi", attachments=attachments)
    parsed = assemble_email(
        message, recurser=_FakeRecurser(), parser_label="eml", parser_version="t"
    )
    statuses = [a["status"] for a in parsed.structured_content["attachments"]]
    assert statuses[:2] == ["extracted via fake", "extracted via fake"]
    assert statuses[2:] == ["skipped (attachment cap)", "skipped (attachment cap)"]
    assert parsed.structured_content["caps"]["attachments_skipped"] == 2


def test_assemble_email_caps_on_extracted_text_not_input_bytes(monkeypatch) -> None:
    # Tiny INPUT bytes but a larger EXTRACTED text: the cap must bound the
    # extracted text (what actually lands in canonical_text + is chunked),
    # not the compressed input — the decompression-amplification guard.
    extracted_len = len(f"EXTRACTED[{OOXML_DOCX_MIME}]")  # _FakeRecurser's output
    monkeypatch.setattr(_msg_mod, "MAX_RECURSED_TEXT_CHARS", extracted_len + 5)
    attachments = [
        NormalizedAttachment(filename="a.docx", mime=OOXML_DOCX_MIME, data=b"x"),
        NormalizedAttachment(filename="b.docx", mime=OOXML_DOCX_MIME, data=b"x"),
    ]
    message = NormalizedMessage(headers={"from": "a@x.com"}, body="hi", attachments=attachments)
    parsed = assemble_email(
        message, recurser=_FakeRecurser(), parser_label="eml", parser_version="t"
    )
    statuses = [a["status"] for a in parsed.structured_content["attachments"]]
    assert statuses == ["extracted via fake", "skipped (size cap)"]


def test_assemble_email_without_recurser_lists_only() -> None:
    message = NormalizedMessage(
        headers={"from": "a@x.com", "subject": "s"},
        body="body",
        attachments=[NormalizedAttachment(filename="x.docx", mime=OOXML_DOCX_MIME, data=b"d")],
    )
    parsed = assemble_email(message, recurser=None, parser_label="eml", parser_version="t")
    assert parsed.structured_content["attachments"][0]["status"] == "not text-extracted"
    assert "x.docx" in parsed.canonical_text  # still listed inline


def test_assemble_email_fully_empty_message() -> None:
    parsed = assemble_email(
        NormalizedMessage(), recurser=None, parser_label="eml", parser_version="t"
    )
    assert parsed.canonical_text == ""
    assert parsed.pages == []
    assert parsed.page_count == 0
    assert parsed.structured_content["format"] == "email"


def test_guess_mime_extension_fallback() -> None:
    from app.pipeline.readers._message import _guess_mime

    # octet-stream + a known extension -> resolved to the real recursable type
    assert (
        _guess_mime(NormalizedAttachment("nda.docx", "application/octet-stream", b""))
        == OOXML_DOCX_MIME
    )
    # a declared real mime wins over the extension
    assert _guess_mime(NormalizedAttachment("x.docx", "application/pdf", b"")) == "application/pdf"
    # unknown extension -> declared (octet-stream) left unchanged
    assert (
        _guess_mime(NormalizedAttachment("x.bin", "application/octet-stream", b""))
        == "application/octet-stream"
    )


def test_eml_attachment_spoof_fails_soft() -> None:
    # A spoofed/bad ATTACHMENT must NOT sink the email (C2 fail-soft): the
    # wired recurser sniff-rejects it and the email still parses, with the
    # attachment recorded "not text-extracted" and its bytes never extracted.
    pytest.importorskip("docx")
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = "a@x.com"
    msg["Subject"] = "spoofed attachment"
    msg.set_content("Body about the deal.")
    msg.add_attachment(
        b"SPOOF plain text, not OOXML at all",
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="nda.docx",
    )
    parsed = _wired_eml().read(msg.as_bytes())
    assert "Body about the deal." in parsed.canonical_text
    assert parsed.structured_content["attachments"][0]["status"] == "not text-extracted"
    assert "SPOOF plain text" not in parsed.canonical_text  # bytes never extracted
    _assert_spans_tile(parsed)


def test_recurser_gates_and_fails_soft() -> None:
    # Directly exercise AttachmentRecurser's defensive branches.
    pytest.importorskip("docx")
    from app.pipeline.readers._base import AttachmentRecurser

    registry = build_default_registry(types.SimpleNamespace(lq_ai_docling_enabled=False))
    recurser = AttachmentRecurser(registry, 1)
    # (a) unknown MIME -> no reader -> None
    assert recurser.recurse("application/x-nope", b"data") is None
    # (b) sniff rejects a spoof (bytes contradict the declared docx) -> None
    assert recurser.recurse(OOXML_DOCX_MIME, b"plain text, not a zip") is None
    # (c) sniff passes but the parse raises -> fail-soft None (not an exception)
    broken = _strip_part(_make_docx(), "word/document.xml")
    assert recurser.recurse(OOXML_DOCX_MIME, broken) is None
    # (d) depth exhausted -> None
    assert AttachmentRecurser(registry, 0).recurse(OOXML_DOCX_MIME, _make_docx()) is None


# ---------------------------------------------------------------------------
# C2 — .msg (python-oxmsg): sniff + normalization (via stub, no real .msg)
# ---------------------------------------------------------------------------


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def test_msg_sniff_requires_ole_magic() -> None:
    reader = MsgReader()
    assert reader.sniff(_OLE_MAGIC + b"rest of an OLE file") is True
    assert reader.sniff(b"%PDF-1.7 ...") is False
    assert reader.sniff(b"PK\x03\x04 zip/docx") is False
    assert reader.sniff(b"") is False


class _StubRecipient:
    def __init__(self, name: str, email: str) -> None:
        self.name = name
        self.email_address = email


class _StubAttachment:
    def __init__(self, file_name: str, mime_type: str, file_bytes: bytes) -> None:
        self.file_name = file_name
        self.mime_type = mime_type
        self.file_bytes = file_bytes


class _StubMsg:
    """Mimics the oxmsg Message surface for the normalization boundary."""

    def __init__(self) -> None:
        self.sender = "Jason Martinez <jason@securescan.com>"
        self.subject = "SecureScan order form"
        self.body = "Plain body wins."
        self.html_body = "<p>HTML loses.</p>"
        self.sent_date = None
        self.message_class = "IPM.Note"
        self.message_headers = {
            "Message-ID": "<abc@securescan>",
            "In-Reply-To": "<prev@zendesk>",
            "Date": "Mon, 1 Jun 2026 09:00:00 +0000",
            "Cc": "legal@zendesk.com",
        }
        self.recipients = [_StubRecipient("Bob Buyer", "bob@zendesk.com")]
        self.attachments = [_StubAttachment("order.docx", OOXML_DOCX_MIME, b"docx-bytes")]


def test_msg_normalization_maps_oxmsg_fields() -> None:
    nm = MsgReader._normalize(_StubMsg())
    assert nm.headers["from"] == "Jason Martinez <jason@securescan.com>"
    assert nm.headers["to"] == "Bob Buyer <bob@zendesk.com>"
    assert nm.headers["cc"] == "legal@zendesk.com"
    assert nm.headers["subject"] == "SecureScan order form"
    assert nm.headers["date"] == "Mon, 1 Jun 2026 09:00:00 +0000"  # from raw headers
    assert nm.headers["message-id"] == "<abc@securescan>"
    assert nm.headers["in-reply-to"] == "<prev@zendesk>"
    assert nm.body == "Plain body wins."  # plain preferred over html
    assert nm.attachments[0].filename == "order.docx"
    # assembled output carries the inline header block + recurses the attachment when wired
    parsed = assemble_email(nm, recurser=_FakeRecurser(), parser_label="msg", parser_version="t")
    assert "From: Jason Martinez <jason@securescan.com>" in parsed.canonical_text
    assert "Subject: SecureScan order form" in parsed.canonical_text
    assert "order.docx" in parsed.canonical_text
    assert parsed.structured_content["attachments"][0]["status"] == "extracted via fake"


def test_msg_normalization_falls_back_to_html_body() -> None:
    stub = _StubMsg()
    stub.body = "   "  # no plain body
    nm = MsgReader._normalize(stub)
    assert nm.body == "HTML loses."  # html stripped to text


def test_msg_read_end_to_end_with_patched_load(monkeypatch) -> None:
    # Covers MsgReader.read()'s full wiring (load boundary -> normalize ->
    # assemble) by patching the oxmsg byte-parse to return a stub. The real
    # CFB byte-parse is oxmsg's own (empirically API-verified at C2; first
    # live .msg lands at Scenario B — oxmsg is read-only, no synthetic .msg).
    oxmsg = pytest.importorskip("oxmsg")
    monkeypatch.setattr(oxmsg.Message, "load", lambda data: _StubMsg())
    parsed = MsgReader().read(_OLE_MAGIC + b"ignored-by-stub")
    assert parsed.parser == "msg"
    assert "From: Jason Martinez <jason@securescan.com>" in parsed.canonical_text
    assert "Plain body wins." in parsed.canonical_text
    assert parsed.structured_content is not None
    assert parsed.structured_content["format"] == "email"
    _assert_spans_tile(parsed)
    assert _assert_chunk_fidelity(parsed) > 0
