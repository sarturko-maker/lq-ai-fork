"""MSG reader — Outlook ``.msg`` (OLE/CFB) via python-oxmsg (MIT) — C2 (ADR-F029 extended).

Normalises the ``.msg`` into the same :class:`NormalizedMessage` the EML
reader produces, then hands it to :func:`assemble_email` — so threading,
one-level attachment recursion, inline provenance, caps, and the
``structured_content`` map are shared, format-agnostic logic.

python-oxmsg is **read-only OLE parsing** — no network, no eval. It is
lazy-imported inside :meth:`read` so the package imports cleanly without it.
``sniff`` checks the OLE/CFB magic (a real spoof check, unlike ``.eml``).
The parse boundary (``Message.load``) is isolated from :meth:`_normalize` so
the field-mapping is unit-testable with a stub message.
"""

from __future__ import annotations

from typing import Any

from app.pipeline.readers._base import (
    MSG_MIME,
    MSG_MIME_ALT,
    ParsedDocument,
    ParserError,
    dist_version,
)
from app.pipeline.readers._message import (
    NormalizedAttachment,
    NormalizedMessage,
    Recurser,
    RecursingReader,
    assemble_email,
    strip_html,
)

# OLE2 / Compound File Binary signature — the first 8 bytes of every .msg.
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_THREAD_KEYS = ("message-id", "in-reply-to", "references")


class MsgReader(RecursingReader):
    """Extracts an Outlook ``.msg`` message + its attachments."""

    parser_label = "msg"
    mimes = frozenset({MSG_MIME, MSG_MIME_ALT})

    def sniff(self, data: bytes) -> bool:
        return data[:8] == _OLE_MAGIC

    def read(self, data: bytes, recurser: Recurser | None = None) -> ParsedDocument:
        from oxmsg import Message  # lazy: heavy, optional dep

        try:
            message = Message.load(data)
        except Exception as exc:  # oxmsg raises ValueError on non-MSG/corrupt
            raise ParserError(f"oxmsg failed to parse .msg: {exc}") from exc
        normalized = self._normalize(message)
        rec = recurser if recurser is not None else self._mint_recurser()
        return assemble_email(
            normalized,
            recurser=rec,
            parser_label=self.parser_label,
            parser_version=f"python-oxmsg=={dist_version('python-oxmsg')}",
        )

    @staticmethod
    def _normalize(message: Any) -> NormalizedMessage:
        """Map an oxmsg ``Message`` (or a stub with the same shape) to a NormalizedMessage.

        Prefers oxmsg's parsed fields; falls back to the raw transport
        headers (``message_headers``) when a field is absent (e.g. a draft
        with no internet headers). Defensive throughout — a missing/odd
        attribute degrades, never raises.
        """

        raw = _raw_headers(message)
        headers: dict[str, str] = {}

        sender = _attr_str(message, "sender")
        headers["from"] = sender or raw.get("from", "")
        recipients = _format_recipients(message)
        headers["to"] = recipients or raw.get("to", "")
        if raw.get("cc"):
            headers["cc"] = raw["cc"]
        subject = _attr_str(message, "subject")
        if subject:
            headers["subject"] = subject
        headers["date"] = _sent_date(message) or raw.get("date", "")
        for key in _THREAD_KEYS:
            if raw.get(key):
                headers[key] = raw[key]
        headers = {k: v for k, v in headers.items() if v}  # drop empties

        body = _attr_str(message, "body")
        if not body.strip():
            html = _attr_str(message, "html_body")
            if html:
                body = strip_html(html)

        return NormalizedMessage(
            headers=headers,
            body=body.strip(),
            attachments=_extract_attachments(message),
        )


def _attr_str(obj: Any, name: str) -> str:
    value = getattr(obj, name, None)
    return str(value) if value else ""


def _raw_headers(message: Any) -> dict[str, str]:
    try:
        items = (message.message_headers or {}).items()
    except Exception:
        return {}
    out: dict[str, str] = {}
    for key, value in items:
        if key and value:
            out[str(key).lower()] = str(value)
    return out


def _sent_date(message: Any) -> str:
    sent = getattr(message, "sent_date", None)
    if sent is None:
        return ""
    return sent.isoformat() if hasattr(sent, "isoformat") else str(sent)


def _format_recipients(message: Any) -> str:
    try:
        recipients = message.recipients or ()
    except Exception:
        return ""
    parts: list[str] = []
    for recipient in recipients:
        name = _attr_str(recipient, "name").strip()
        email = _attr_str(recipient, "email_address").strip()
        formatted = f"{name} <{email}>" if name and email else (email or name)
        if formatted:
            parts.append(formatted)
    return "; ".join(parts)


def _extract_attachments(message: Any) -> list[NormalizedAttachment]:
    try:
        attachments = message.attachments or ()
    except Exception:
        return []
    out: list[NormalizedAttachment] = []
    for att in attachments:
        data = getattr(att, "file_bytes", b"") or b""
        out.append(
            NormalizedAttachment(
                filename=_attr_str(att, "file_name"),
                mime=_attr_str(att, "mime_type"),
                data=bytes(data),
            )
        )
    return out
