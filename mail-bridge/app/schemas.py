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

**Text-only by construction (F6a security-hardening).** ``draft_email_reply``
refuses ``attachment_file_ids`` (they are recorded, never delivered — see
``intake_tools``), and the api client sends no ``attachments`` field. The field
was therefore DEAD attack surface — a base64-decoding sink reachable with the
bridge token — so it is removed. A reply carries text only; ``extra="forbid"``
turns any ``attachments`` key into a 422.

Bounds mirror ``api/app/schemas/intake.py`` — a reply must be no less bounded
than an arrival.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .normalize import MAX_BODY_TEXT_CHARS

#: INTAKE-4b (ADR-F087/F088): the matter reference the api asks us to tag the
#: Reply-To with. Mirrors ``api/app/matters/reference.py``'s REFERENCE_PATTERN —
#: anchored, uppercase, no separators of its own. The api sends the TAG, never an
#: address: the bridge composes ``<local>+<tag>@<domain>`` from its OWN configured
#: inbox, so neither the api nor the agent behind it can choose where a reply goes.
_REPLY_TO_TAG_PATTERN = r"^[A-Z0-9]{2,6}-[A-Z0-9]{2,6}-[0-9]{4,}$"


class SendReplyRequest(BaseModel):
    """Reply into an existing thread, keyed by the message being answered."""

    model_config = ConfigDict(extra="forbid")

    reply_to_provider_message_id: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., min_length=1, max_length=MAX_BODY_TEXT_CHARS)
    # INTAKE-4b: the caller's own key for this send. The api derives it from the
    # human-approved ASK (its checkpointed tool-call id), never from a per-attempt
    # id, so a re-execution presents the SAME key — see ADR-F087. Required: an
    # unkeyed send cannot be told apart from a repeat, and a repeat is a second
    # letter in someone's inbox.
    idempotency_key: str = Field(..., min_length=1, max_length=64)
    reply_to_tag: str | None = Field(default=None, pattern=_REPLY_TO_TAG_PATTERN, max_length=40)


class SendReplyResponse(BaseModel):
    """Provider identifiers only — never an echo of the sent content."""

    provider_message_id: str
    provider_thread_id: str
