"""Outbound-send request/response shapes — INTAKE-2 (ADR-F086).

Consumed by INTAKE-4 (api → bridge ``POST /send`` after a human approves a
drafted reply). Nothing calls it yet; the contract lands now so INTAKE-4 is a
wiring slice, not a design one.

**Reply-only by construction.** The probe verified that ``reply`` is keyed
purely by ``message_id`` — no recipients, no thread id
(``docs/fork/evidence/intake-probe/findings.md`` verdict (c)). It also
disproved the FAQ's claim that cold sends are impossible; we still expose NO
cold-send endpoint, because ADR-F086's safety line is structural: v1 sends
nothing unsolicited, and a mail-bridge that cannot originate a thread cannot be
talked into originating one.

Bounds mirror ``api/app/schemas/intake.py`` — a reply must be no less bounded
than an arrival.
"""

from __future__ import annotations

import base64
import binascii

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from .normalize import (
    MAX_AGGREGATE_ATTACHMENT_BYTES,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS,
    MAX_BODY_TEXT_CHARS,
    MAX_CONTENT_TYPE_CHARS,
    MAX_FILENAME_CHARS,
)

_MAX_ATTACHMENT_B64_CHARS = (MAX_ATTACHMENT_BYTES * 4 // 3) + 1024


class OutboundAttachment(BaseModel):
    """One base64-encoded attachment on an outbound reply."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(..., min_length=1, max_length=MAX_FILENAME_CHARS)
    content_type: str = Field(default="application/octet-stream", max_length=MAX_CONTENT_TYPE_CHARS)
    content_b64: str = Field(..., min_length=1, max_length=_MAX_ATTACHMENT_B64_CHARS)

    _decoded_size: int = PrivateAttr(default=0)

    @model_validator(mode="after")
    def _bound_decoded_size(self) -> OutboundAttachment:
        try:
            decoded = base64.b64decode(self.content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("content_b64 is not valid base64") from exc
        if len(decoded) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"attachment exceeds the {MAX_ATTACHMENT_BYTES} byte decoded limit")
        self._decoded_size = len(decoded)
        return self

    @property
    def decoded_size(self) -> int:
        return self._decoded_size


class SendReplyRequest(BaseModel):
    """Reply into an existing thread, keyed by the message being answered."""

    model_config = ConfigDict(extra="forbid")

    reply_to_provider_message_id: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., min_length=1, max_length=MAX_BODY_TEXT_CHARS)
    attachments: list[OutboundAttachment] = Field(default_factory=list, max_length=MAX_ATTACHMENTS)

    @model_validator(mode="after")
    def _bound_aggregate(self) -> SendReplyRequest:
        total = sum(a.decoded_size for a in self.attachments)
        if total > MAX_AGGREGATE_ATTACHMENT_BYTES:
            raise ValueError(
                f"attachments exceed the {MAX_AGGREGATE_ATTACHMENT_BYTES} byte aggregate limit"
            )
        return self


class SendReplyResponse(BaseModel):
    """Provider identifiers only — never an echo of the sent content."""

    provider_message_id: str
    provider_thread_id: str
