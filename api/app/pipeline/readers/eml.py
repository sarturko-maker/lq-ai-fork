"""EML reader — a single email's headers + body, via the stdlib (no dep).

Produces one logical unit: a deterministic header block (From/To/Cc/Date/
Subject, in that order, absent headers skipped) then the body. The body
prefers ``text/plain``; if only HTML exists it is stripped with the
stdlib :class:`html.parser.HTMLParser` (no external HTML library, no
remote fetch). Per the C1 boundary this reader does **not** recurse into
attachments or stitch the reply chain — that is C2; ``get_body`` returns
only the inline body part, so attachments are ignored here.

The email and its HTML are untrusted: ``email.message_from_bytes`` and
``HTMLParser`` neither execute content nor fetch ``cid:``/``http(s)``
references; ``<script>``/``<style>`` contents are dropped.
"""

from __future__ import annotations

import sys
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as DEFAULT_POLICY
from html.parser import HTMLParser
from typing import cast

from app.pipeline.readers._base import (
    EML_MIME,
    PageSpan,
    ParsedDocument,
)

_HEADER_ORDER = ("From", "To", "Cc", "Date", "Subject")
_SKIP_TAGS = frozenset({"script", "style"})


class _HtmlTextExtractor(HTMLParser):
    """Collects visible text from HTML, dropping script/style contents.

    Note: stdlib HTMLParser ends a script/style block at the first
    ``</script>``/``</style>`` token — which matches HTML5 raw-text-element
    semantics (a browser ends the block there too and renders any trailing
    text), so text after a premature close tag is treated as body, not
    hidden content. Document text is untrusted model input regardless
    (CLAUDE.md), so this is acceptable for citation-text extraction.
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


def _strip_html(html: str) -> str:
    extractor = _HtmlTextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.text()


class EmlReader:
    """Extracts headers + the inline body from a single ``.eml`` message."""

    parser_label = "eml"
    mimes = frozenset({EML_MIME})

    def sniff(self, data: bytes) -> bool:
        # message/rfc822 is plain text with no reliable magic signature, so
        # a content cross-check cannot reject a spoof here; the declared
        # type is accepted. (Documented in ADR-F029.)
        return True

    def read(self, data: bytes) -> ParsedDocument:
        # policy=default yields an EmailMessage (get_body / get_content); the
        # stdlib's message_from_bytes is typed as the base Message, so narrow.
        message = cast(EmailMessage, message_from_bytes(data, policy=DEFAULT_POLICY))
        header_lines = [f"{name}: {message[name]}" for name in _HEADER_ORDER if message[name]]

        blocks: list[str] = []
        if header_lines:
            blocks.append("\n".join(header_lines))
        body = self._extract_body(message)
        if body:
            blocks.append(body)

        canonical = "\n\n".join(blocks)
        pages = (
            [PageSpan(page_number=1, char_start=0, char_end=len(canonical))] if canonical else []
        )
        return ParsedDocument(
            canonical_text=canonical,
            pages=pages,
            page_count=len(pages),
            parser=self.parser_label,
            parser_version=f"stdlib-email; python={sys.version.split()[0]}",
            structured_content=None,
        )

    @staticmethod
    def _extract_body(message: EmailMessage) -> str:
        # Prefer text/plain; fall back to stripped HTML. get_body ignores
        # attachments (no recursion — C2 boundary).
        for preference in (("plain",), ("html",)):
            try:
                part = message.get_body(preferencelist=preference)
            except Exception:  # pragma: no cover - defensive against odd MIME
                part = None
            if part is None:
                continue
            try:
                content = str(part.get_content())
            except Exception:  # pragma: no cover - undeclared charset etc.
                continue
            if preference == ("html",):
                content = _strip_html(content)
            stripped = content.strip()
            if stripped:
                return stripped
        return ""
