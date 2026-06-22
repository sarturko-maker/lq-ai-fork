"""EML reader — a message + its attachments, via the stdlib (no dep).

C2 (ADR-F029 extended): the reader normalises the ``.eml`` into a
:class:`NormalizedMessage` (ordered display headers + threading headers,
plain-preferred/HTML-stripped body, attachments incl. nested
``message/rfc822`` parts) and hands it to :func:`assemble_email`, which emits
one canonical-text unit per message + per attachment, recurses ONE level into
recursable attachments (via the injected recurser), and writes the auditable
thread/attachment map to ``structured_content``.

A **bare** ``EmlReader()`` (no recurser wired) *lists* attachments with an
inline label but does not extract them; the production reader, wired at the
composition root (``build_default_registry``), additionally extracts
recursable attachments. The email and its HTML are untrusted:
``message_from_bytes`` / the HTML stripper neither execute content nor fetch
``cid:``/``http(s)`` references.
"""

from __future__ import annotations

import sys
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as DEFAULT_POLICY
from typing import cast

from app.pipeline.readers._base import (
    EML_MIME,
    ParsedDocument,
)
from app.pipeline.readers._message import (
    NormalizedAttachment,
    NormalizedMessage,
    Recurser,
    RecursingReader,
    assemble_email,
    strip_html,
)

# Header names pulled into the normalised message (lowercase keys). Display
# order + threading linkage are owned by the assembler.
_DISPLAY_KEYS = ("From", "To", "Cc", "Date", "Subject")
_THREAD_KEYS = ("Message-ID", "In-Reply-To", "References")


class EmlReader(RecursingReader):
    """Extracts a message + its attachments from a single ``.eml``."""

    parser_label = "eml"
    mimes = frozenset({EML_MIME})

    def sniff(self, data: bytes) -> bool:
        # message/rfc822 is plain text with no reliable magic signature, so a
        # content cross-check cannot reject a spoof here; the declared type is
        # accepted. (Documented in ADR-F029.)
        return True

    def read(self, data: bytes, recurser: Recurser | None = None) -> ParsedDocument:
        message = cast(EmailMessage, message_from_bytes(data, policy=DEFAULT_POLICY))
        normalized = self._normalize(message)
        rec = recurser if recurser is not None else self._mint_recurser()
        return assemble_email(
            normalized,
            recurser=rec,
            parser_label=self.parser_label,
            parser_version=f"stdlib-email; python={sys.version.split()[0]}",
        )

    def _normalize(self, message: EmailMessage) -> NormalizedMessage:
        headers: dict[str, str] = {}
        for name in (*_DISPLAY_KEYS, *_THREAD_KEYS):
            value = message[name]
            if value:
                headers[name.lower()] = str(value)
        return NormalizedMessage(
            headers=headers,
            body=self._extract_body(message),
            attachments=self._extract_attachments(message),
        )

    @staticmethod
    def _extract_body(message: EmailMessage) -> str:
        # Prefer text/plain; fall back to stripped HTML. get_body ignores
        # attachments, so this is the inline body only.
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
                content = strip_html(content)
            stripped = content.strip()
            if stripped:
                return stripped
        return ""

    @staticmethod
    def _extract_attachments(message: EmailMessage) -> list[NormalizedAttachment]:
        attachments: list[NormalizedAttachment] = []
        for part in message.iter_attachments():
            part = cast(EmailMessage, part)
            ctype = part.get_content_type()
            filename = part.get_filename() or ""
            if ctype == "message/rfc822":
                # A nested (forwarded/replied) email: recurse over its bytes.
                data = _nested_message_bytes(part)
                attachments.append(
                    NormalizedAttachment(
                        filename=filename or "forwarded-message.eml",
                        mime=EML_MIME,
                        data=data,
                    )
                )
                continue
            attachments.append(
                NormalizedAttachment(filename=filename, mime=ctype, data=_part_bytes(part))
            )
        return attachments


def _part_bytes(part: EmailMessage) -> bytes:
    """Raw decoded bytes of a leaf attachment part (transfer-encoding handled)."""

    payload = part.get_payload(decode=True)
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    # Text parts with no transfer-encoding: get_content returns str.
    try:
        content = part.get_content()
    except Exception:  # pragma: no cover - undeclared charset etc.
        return b""
    if isinstance(content, str):
        return content.encode("utf-8", "replace")
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    return b""


def _nested_message_bytes(part: EmailMessage) -> bytes:
    """Serialise a ``message/rfc822`` part's nested message to bytes."""

    try:
        nested = part.get_content()  # an EmailMessage
        if isinstance(nested, EmailMessage):
            return nested.as_bytes()
    except Exception:  # pragma: no cover - defensive against odd MIME
        pass
    return _part_bytes(part)
