"""Shared email assembly — turns a normalised message into a ``ParsedDocument`` (C2, ADR-F029 extended).

The EML (stdlib ``email``) and MSG (``python-oxmsg``) readers each normalise
their format into a :class:`NormalizedMessage`, then call
:func:`assemble_email`, which is the single home for the C2 logic:

* **Units + inline provenance.** One canonical-text *unit* per message and
  per attachment. Each unit is prefixed with a human-readable provenance
  label — the message header block (``From: …`` / ``Date: …`` / ``Subject:
  …``) and an ``[Attached file: … ]`` line per attachment. This inline label
  is the *only agent-visible provenance*: ``search_documents`` returns chunk
  **content verbatim** and does not read ``structured_content``.
* **One-level attachment recursion.** A recursable attachment (office doc,
  nested email) is parsed via the injected :class:`AttachmentRecurser` and
  its extracted text spliced in under the label; office docs inherit
  :func:`guard_ooxml`. ``cid:`` / ``http(s)`` are never fetched.
* **Caps (untrusted input).** Attachment count and cumulative recursed bytes
  are bounded; over a cap the attachment is recorded but not extracted.
* **Auditable map.** A flat thread/attachment map is written to
  ``structured_content`` (NOT agent-visible — the receipts/transparency
  record + the substrate C5/C7 build on).

Offsets are owned by :func:`join_units`, so the Citation-Engine invariant
``canonical_text[start:end] == chunk.content`` holds by construction.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Protocol

from app.pipeline.readers._base import (
    EML_MIME,
    MAX_EMAIL_ATTACHMENTS,
    MAX_RECURSED_TEXT_CHARS,
    MSG_MIME,
    OOXML_DOCX_MIME,
    OOXML_PPTX_MIME,
    OOXML_XLSX_MIME,
    ParsedDocument,
    build_parsed_document,
)

# Display order for the inline header block (absent headers skipped).
_DISPLAY_HEADERS: tuple[tuple[str, str], ...] = (
    ("from", "From"),
    ("to", "To"),
    ("cc", "Cc"),
    ("date", "Date"),
    ("subject", "Subject"),
)
# Threading headers recorded in the structured_content map (ordering/linking
# signal for C5/C7; never used to fetch anything).
_THREAD_HEADERS: tuple[str, ...] = ("message-id", "in-reply-to", "references")

_SKIP_TAGS = frozenset({"script", "style"})

# Extension -> MIME fallback when an attachment declares no usable type, so a
# recursable office doc / email isn't missed. Maps only to types a reader in
# the registry claims; anything else falls through to "not text-extracted".
_EXT_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": OOXML_DOCX_MIME,
    ".xlsx": OOXML_XLSX_MIME,
    ".pptx": OOXML_PPTX_MIME,
    ".eml": EML_MIME,
    ".msg": MSG_MIME,
}


class Recurser(Protocol):
    """Structural type for :class:`app.pipeline.readers._base.AttachmentRecurser`."""

    def recurse(self, mime: str, data: bytes) -> ParsedDocument | None: ...


class RecursingReader:
    """Mixin: the one-level attachment-recurser seam shared by the EML + MSG readers.

    A *bare* reader (factory unset) lists attachments but extracts none; the
    production reader is wired via :meth:`set_recurser_factory` at the
    composition root (``build_default_registry``), minting a fresh depth-1
    recurser per top-level read. ``read`` accepts an explicit ``recurser`` so a
    nested email is read with the depth-decremented child (the one-level bound).
    """

    accepts_recurser = True

    def __init__(self) -> None:
        self._recurser_factory: Callable[[], Recurser] | None = None

    def set_recurser_factory(self, factory: Callable[[], Recurser]) -> None:
        """Wire the attachment recurser (composition root; see build_default_registry)."""

        self._recurser_factory = factory

    def _mint_recurser(self) -> Recurser | None:
        return self._recurser_factory() if self._recurser_factory else None


# ---------------------------------------------------------------------------
# HTML stripping (shared by EML + MSG; untrusted, inert)
# ---------------------------------------------------------------------------


class _HtmlTextExtractor(HTMLParser):
    """Collects visible text from HTML, dropping script/style contents.

    stdlib HTMLParser ends a script/style block at the first
    ``</script>``/``</style>`` token — HTML5 raw-text-element semantics (a
    browser ends the block there too), so text after a premature close tag is
    treated as body, not hidden content. Document text is untrusted model
    input regardless (CLAUDE.md); neither executes content nor fetches
    ``cid:``/``http(s)`` references.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def strip_html(html: str) -> str:
    extractor = _HtmlTextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.text()


# ---------------------------------------------------------------------------
# Normalised message — the format-agnostic intermediate
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NormalizedAttachment:
    """One attachment's identity + raw bytes (best-effort fields)."""

    filename: str  # "" if unknown
    mime: str  # declared content-type; "" if unknown
    data: bytes


@dataclass(slots=True)
class NormalizedMessage:
    """A message reduced to display headers, body text, and attachments.

    ``headers`` keys are lowercase (``from``/``to``/``cc``/``date``/
    ``subject`` + the threading headers); absent headers are simply missing.
    """

    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    attachments: list[NormalizedAttachment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _header_block(headers: dict[str, str]) -> str:
    return "\n".join(
        f"{label}: {headers[key]}" for key, label in _DISPLAY_HEADERS if headers.get(key)
    )


def _message_unit(message: NormalizedMessage) -> str:
    block = _header_block(message.headers)
    body = message.body.strip()
    if block and body:
        return f"{block}\n\n{body}"
    return block or body


def _guess_mime(att: NormalizedAttachment) -> str:
    declared = att.mime.split(";", 1)[0].strip().lower()
    if declared and declared != "application/octet-stream":
        return declared
    name = att.filename.lower()
    dot = name.rfind(".")
    if dot != -1:
        return _EXT_MIME.get(name[dot:], declared)
    return declared


def _attachment_label(att: NormalizedAttachment, status_text: str) -> str:
    name = att.filename or "(unnamed)"
    mime = att.mime or "unknown type"
    return f"[Attached file: {name} ({mime}) — {status_text}]"


def assemble_email(
    message: NormalizedMessage,
    *,
    recurser: Recurser | None,
    parser_label: str,
    parser_version: str,
) -> ParsedDocument:
    """Assemble one message + its attachments into a single ``ParsedDocument``.

    The top message is unit 1; attachments are units 2..N. ``recurser`` is
    ``None`` for a bare reader (attachments are *listed* but not extracted)
    and a depth-1 recurser when wired at the composition root (recursable
    attachments are additionally *extracted*).
    """

    units: list[str] = [_message_unit(message)]
    msg_map: dict[str, object] = {"ordinal": 1, "type": "message"}
    for key, label in _DISPLAY_HEADERS:
        if message.headers.get(key):
            msg_map[label.lower()] = message.headers[key]
    for hkey in _THREAD_HEADERS:
        if message.headers.get(hkey):
            msg_map[hkey.replace("-", "_")] = message.headers[hkey]

    attachments_map: list[dict[str, object]] = []
    recursed_chars = 0
    skipped = 0

    for idx, att in enumerate(message.attachments):
        ordinal = len(units) + 1  # this attachment's unit ordinal (1-based)
        if idx >= MAX_EMAIL_ATTACHMENTS:
            skipped += 1
            status = "skipped (attachment cap)"
            parser = None
            text: str | None = None
        else:
            mime = _guess_mime(att)
            text, parser, status = _recurse_attachment(att, mime, recurser, recursed_chars)
            if text is not None and parser is not None:
                recursed_chars += len(text)  # bound the EXTRACTED text, not input bytes

        label = _attachment_label(att, status)
        units.append(f"{label}\n\n{text}" if text else label)
        attachments_map.append(
            {
                "ordinal": ordinal,
                "type": "attachment",
                "filename": att.filename or None,
                "mime": att.mime or None,
                "bytes": len(att.data),
                "status": status,
                "parser": parser,
            }
        )

    # The auditable thread/attachment map (NOT agent-visible — receipts /
    # transparency record + the C5/C7 substrate).
    structured: dict[str, object] = {
        "format": "email",
        "message_count": 1,
        "messages": [msg_map],
        "attachments": attachments_map,
        "caps": {
            "max_attachments": MAX_EMAIL_ATTACHMENTS,
            "max_recursed_text_chars": MAX_RECURSED_TEXT_CHARS,
            "attachments_total": len(message.attachments),
            "attachments_skipped": skipped,
        },
    }

    if not any(units):
        # Fully-empty message, no attachments — mirror the C1 empty-doc shape
        # (pages == []), still carrying the map for the audit record.
        return ParsedDocument(
            canonical_text="",
            pages=[],
            page_count=0,
            parser=parser_label,
            parser_version=parser_version,
            structured_content=structured,
        )

    doc = build_parsed_document(units, parser=parser_label, parser_version=parser_version)
    doc.structured_content = structured
    return doc


def _recurse_attachment(
    att: NormalizedAttachment,
    mime: str,
    recurser: Recurser | None,
    recursed_chars: int,
) -> tuple[str | None, str | None, str]:
    """Return ``(extracted_text, parser, status_text)`` for one attachment.

    The cumulative cap is enforced against the *extracted* text length (after
    parsing), not the compressed input — a compressed-bytes cap is inert (each
    attachment is already under the upload limit), whereas the extracted text is
    what is spliced into ``canonical_text`` and then chunked/persisted.
    """

    if recurser is None or not att.data:
        return None, None, "not text-extracted"
    parsed = recurser.recurse(mime, att.data)
    if parsed is None or not parsed.canonical_text.strip():
        return None, None, "not text-extracted"
    text = parsed.canonical_text
    if recursed_chars + len(text) > MAX_RECURSED_TEXT_CHARS:
        return None, None, "skipped (size cap)"
    return text, parsed.parser, f"extracted via {parsed.parser}"
