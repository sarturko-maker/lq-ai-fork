"""Provider-agnostic inbound-email envelope + intake response shapes — INTAKE-1 (ADR-F086).

The mail-bridge (a future, separate microservice — INTAKE-2) is the ONLY
holder of mailbox credentials; it normalizes whatever a provider (AgentMail
in v1) sends into this envelope and POSTs it to
``POST /api/v1/internal/intake/emails``. Email content is untrusted model
input (CLAUDE.md; ADR-F086 security posture #1): every field here is
boundary-validated and REJECTED (422) rather than sanitized when it
exceeds its bound — an oversized or malformed envelope never reaches the
DB or an agent prompt.

Boundary bounds enforced here (ADR-F086 security posture + the INTAKE-1
slice spec):

* at most 10 attachments per message;
* each attachment's DECODED size capped at 25 MB;
* the message body text capped at 512k chars;
* ``headers`` is filtered to a small allowlist (loop/authenticity signals
  only — ``Auto-Submitted``, ``Precedence``, ``In-Reply-To``,
  ``References``) rather than carried through as an arbitrary untrusted
  dict; every other header the bridge might forward is silently dropped
  (not "sanitized" — simply outside the accepted shape).
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

AuthState = Literal["pass", "fail", "unknown"]

# Boundary caps (ADR-F086 security posture; INTAKE-1 slice spec).
MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_DECODED_BYTES = 25 * 1024 * 1024  # 25 MB decoded
MAX_BODY_TEXT_CHARS = 512_000
# Encoded-length ceiling on content_b64 BEFORE we even attempt to decode —
# base64 inflates by ~4/3; this is a generous outer bound (cheap length
# check) ahead of the exact decoded-byte check in _decode_and_bound below.
_MAX_ATTACHMENT_B64_CHARS = (MAX_ATTACHMENT_DECODED_BYTES * 4 // 3) + 1024

# Only these headers carry loop-prevention / sender-authenticity signal
# (ADR-F086 security posture #2/#3). Everything else the bridge forwards is
# dropped at this boundary — the doctrine (INTAKE-3) never sees, and the
# agent prompt never fences, header names/values outside this set.
ALLOWED_HEADER_KEYS = frozenset({"Auto-Submitted", "Precedence", "In-Reply-To", "References"})
_HEADER_VALUE_MAX_CHARS = 500


class InboundEmailThread(BaseModel):
    """The provider-thread identity a message belongs to."""

    model_config = ConfigDict(extra="forbid")

    provider_thread_id: str = Field(..., min_length=1, max_length=500)
    # Empty subject lines are real email traffic, not an error — the
    # intake router derives a fallback candidate-matter name for them.
    subject: str = Field(default="", max_length=998)


class InboundEmailAttachment(BaseModel):
    """One base64-encoded attachment on an inbound message.

    ``content_b64`` is decoded exactly ONCE, in :meth:`_decode_and_bound`
    below — the result is cached on a private attribute and exposed via
    :attr:`decoded_bytes` so callers (the ingest flow) never pay for a
    second decode.
    """

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(..., min_length=1, max_length=500)
    content_type: str = Field(default="application/octet-stream", max_length=200)
    content_b64: str = Field(..., min_length=1, max_length=_MAX_ATTACHMENT_B64_CHARS)

    _decoded: bytes = PrivateAttr(default=b"")

    @model_validator(mode="after")
    def _decode_and_bound(self) -> InboundEmailAttachment:
        try:
            decoded = base64.b64decode(self.content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                f"attachment {self.filename!r}: content_b64 is not valid base64"
            ) from exc
        if len(decoded) > MAX_ATTACHMENT_DECODED_BYTES:
            raise ValueError(
                f"attachment {self.filename!r} exceeds the "
                f"{MAX_ATTACHMENT_DECODED_BYTES} byte decoded limit"
            )
        self._decoded = decoded
        return self

    @property
    def decoded_bytes(self) -> bytes:
        """The base64-decoded attachment bytes (decoded once, at validation time)."""

        return self._decoded


class InboundEmailMessage(BaseModel):
    """The single inbound message this envelope carries."""

    model_config = ConfigDict(extra="forbid")

    provider_message_id: str = Field(..., min_length=1, max_length=500)
    from_addr: str = Field(..., min_length=1, max_length=320)
    to: list[str] = Field(default_factory=list, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    # Provider-claimed send time. Validated (a malformed value 422s) but NOT
    # trusted for the DB's `last_inbound_at` — the intake router stamps that
    # from the server's own clock (one clock source; defense against a
    # forged/skewed provider timestamp).
    timestamp: datetime
    text: str = Field(default="", max_length=MAX_BODY_TEXT_CHARS)
    headers: dict[str, str] = Field(default_factory=dict)
    auth_state: AuthState = "unknown"
    attachments: list[InboundEmailAttachment] = Field(
        default_factory=list, max_length=MAX_ATTACHMENTS
    )

    @field_validator("headers", mode="before")
    @classmethod
    def _bound_headers(cls, value: object) -> dict[str, str]:
        """Filter to the allowlisted header keys; cap each value's length.

        Not a rejection boundary (unlike attachments/text) — the bridge may
        legitimately forward a broader header set than we act on; we simply
        never carry more than the allowlisted subset past this point.
        """

        if not isinstance(value, dict):
            return {}
        return {
            str(k): str(v)[:_HEADER_VALUE_MAX_CHARS]
            for k, v in value.items()
            if k in ALLOWED_HEADER_KEYS
        }


class InboundEmailEnvelope(BaseModel):
    """The full provider-agnostic envelope POSTed by the mail-bridge."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., min_length=1, max_length=50)
    inbox_id: str = Field(..., min_length=1, max_length=500)
    thread: InboundEmailThread
    message: InboundEmailMessage


# ---------------------------------------------------------------------------
# Response shapes — counts/IDs only, never email content (ADR-F086 posture).
# ---------------------------------------------------------------------------


class IntakeEmailIngestResponse(BaseModel):
    """Response for ``POST /internal/intake/emails`` — counts/IDs only.

    Never echoes subject, body text, sender, or attachment content —
    matching the audit-contract posture elsewhere in this codebase (counts/
    types/IDs, never raw values).
    """

    duplicate: bool
    thread_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    files_ingested: int = 0
