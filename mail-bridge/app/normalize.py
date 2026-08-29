"""AgentMail ``Message`` → provider-agnostic ``InboundEmailEnvelope`` — INTAKE-2 (ADR-F086).

This module is the bridge's half of the envelope contract whose other half is
``api/app/schemas/intake.py``. ADR-F086: the provider is swappable at exactly
this seam — a future M365/Gmail bridge re-implements this file and the api never
learns a new shape.

**Why the bridge bounds instead of letting the api reject.** The api's schema is
a rejection boundary ("reject, don't sanitize") — an oversize body or a NUL byte
422s the whole envelope. For a *client* that would be correct; for an *inbound
email* it means the message is silently lost, because AgentMail has no dead-letter
we can replay from (the probe found ``inboxes.events.list`` is a label-only log —
``docs/fork/evidence/intake-probe/findings.md`` §Step-4/(d)). So the bridge
normalizes DOWN to what the api accepts — truncating the body with a visible
marker, dropping over-long recipients, skipping oversize attachments — and always
lands *something* the human can see in the Intake list. Orchestrator ruling,
INTAKE-2 spec.

**Email content is untrusted model input.** Nothing in here logs a subject, a
body, a sender or an attachment's bytes: log lines carry counts and types only,
matching the audit contract elsewhere in this codebase.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from agentmail import Message

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bounds — MUST stay in lockstep with api/app/schemas/intake.py. They cannot be
# imported (separate service, separate image), so they are restated here with
# the api's names. A bridge value LOOSER than the api's turns into a 422 and a
# lost email; a tighter one silently drops content. Keep them equal.
# ---------------------------------------------------------------------------
MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_AGGREGATE_ATTACHMENT_BYTES = 50 * 1024 * 1024
MAX_BODY_TEXT_CHARS = 512_000
MAX_ADDRESSES = 50
MAX_ADDR_CHARS = 320  # RFC 5321 4.5.3.1.3
MAX_SUBJECT_CHARS = 998
MAX_FILENAME_CHARS = 500
MAX_CONTENT_TYPE_CHARS = 200
MAX_HEADER_VALUE_CHARS = 500

#: Appended to a body we had to shorten so the reading lawyer (and the agent)
#: can see that the text is not the whole message.
TRUNCATION_MARKER = "\n[truncated by mail-bridge]"

#: The api allowlists exactly {Auto-Submitted, Precedence, In-Reply-To,
#: References} and drops everything else (ADR-F086 security posture), so those
#: four are all the bridge forwards. The first two can only ever arrive in the
#: raw header dict; the last two come from the SDK's own typed fields.
_RAW_HEADER_KEYS = ("Auto-Submitted", "Precedence")

_UNKNOWN_SENDER = "(unknown sender)"
_ANGLE_ADDR = re.compile(r"<([^<>]{1,320})>")


def strip_nuls(value: str) -> str:
    """Remove embedded NUL bytes.

    The api *rejects* a NUL (Postgres TEXT cannot hold ``\\x00``, and asyncpg
    raises client-side). Provider noise must not cost us the email, so the
    bridge strips here rather than handing the api a guaranteed 422.
    """

    return value.replace("\x00", "") if "\x00" in value else value


def _clean(value: str | None, *, limit: int) -> str:
    return strip_nuls(value or "")[:limit]


def truncate_body(text: str) -> str:
    """Bound the body to the api's cap, leaving room for the marker."""

    if len(text) <= MAX_BODY_TEXT_CHARS:
        return text
    keep = MAX_BODY_TEXT_CHARS - len(TRUNCATION_MARKER)
    log.info(
        "mail-bridge: inbound body truncated",
        extra={"event": "mail_body_truncated", "original_chars": len(text), "kept_chars": keep},
    )
    return text[:keep] + TRUNCATION_MARKER


def _bound_addresses(values: list[str] | None, *, field: str) -> list[str]:
    """Cap the list at :data:`MAX_ADDRESSES`, dropping over-long entries.

    Counts only in the log — never the addresses themselves.
    """

    if not values:
        return []
    kept: list[str] = []
    dropped_long = 0
    for raw in values:
        cleaned = strip_nuls(raw)
        if len(cleaned) > MAX_ADDR_CHARS:
            dropped_long += 1
            continue
        kept.append(cleaned)
        if len(kept) == MAX_ADDRESSES:
            break
    dropped_overflow = max(0, len(values) - len(kept) - dropped_long)
    if dropped_long or dropped_overflow:
        log.info(
            "mail-bridge: recipient list bounded",
            extra={
                "event": "mail_recipients_bounded",
                "field": field,
                "kept": len(kept),
                "dropped_too_long": dropped_long,
                "dropped_over_cap": dropped_overflow,
            },
        )
    return kept


def _bound_sender(value: str | None) -> str:
    """Produce a ``from_addr`` the api will accept (1-320 chars, no NULs).

    A ``From`` longer than the RFC 5321 path limit is malformed or hostile, but
    *dropping* it is not an option (the field is required) and letting it 422
    loses the email. Prefer the angle-bracket addr-spec when one is present —
    that is the actual address — and only fall back to a hard truncation.
    """

    cleaned = strip_nuls(value or "").strip()
    if not cleaned:
        return _UNKNOWN_SENDER
    if len(cleaned) <= MAX_ADDR_CHARS:
        return cleaned
    match = _ANGLE_ADDR.search(cleaned)
    log.info(
        "mail-bridge: over-long sender bounded",
        extra={"event": "mail_sender_bounded", "original_chars": len(cleaned)},
    )
    if match:
        return match.group(1)
    return cleaned[:MAX_ADDR_CHARS]


def _bound_headers(message: Message) -> dict[str, str]:
    """Forward only the loop/threading headers the api allowlists.

    The probe found ``message.headers`` arrives EMPTY on the wire even for a
    genuine inbound message (findings.md §Step-3 and the addendum), so
    ``In-Reply-To``/``References`` are read from the SDK's own typed fields;
    the raw dict is still consulted for ``Auto-Submitted``/``Precedence``
    should AgentMail ever start populating it. Absent → the key is omitted, not
    sent empty.
    """

    headers: dict[str, str] = {}

    in_reply_to = getattr(message, "in_reply_to", None)
    if isinstance(in_reply_to, str) and in_reply_to.strip():
        headers["In-Reply-To"] = _clean(in_reply_to, limit=MAX_HEADER_VALUE_CHARS)

    references = getattr(message, "references", None)
    if isinstance(references, str) and references.strip():
        headers["References"] = _clean(references, limit=MAX_HEADER_VALUE_CHARS)
    elif isinstance(references, list) and references:
        joined = " ".join(str(ref) for ref in references)
        headers["References"] = _clean(joined, limit=MAX_HEADER_VALUE_CHARS)

    raw = getattr(message, "headers", None)
    if isinstance(raw, dict):
        lowered = {str(k).lower(): v for k, v in raw.items()}
        for key in _RAW_HEADER_KEYS:
            value = lowered.get(key.lower())
            if value is None:
                continue
            cleaned = _clean(str(value), limit=MAX_HEADER_VALUE_CHARS)
            if cleaned:
                headers[key] = cleaned

    return headers


def _coerce_timestamp(value: object) -> str:
    """Always produce an ISO-8601 string, whatever the provider actually sent.

    ``Message`` is built with the SDK's ``construct_type``, which does NOT
    validate: a string (or anything else) in ``timestamp`` survives into a
    field typed ``datetime``. A bare ``.isoformat()`` would then raise inside
    the webhook handler — and because Svix retries a 5xx, a single malformed
    timestamp would become a permanent poison-retry against this bridge.

    The api re-validates this field anyway and stamps its own clock for
    ``last_inbound_at``, so falling back to "now" loses nothing that was
    trustworthy to begin with.
    """

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
    log.info(
        "mail-bridge: unparsable provider timestamp; stamping receipt time",
        extra={"event": "mail_timestamp_coerced", "value_type": type(value).__name__},
    )
    return datetime.now(tz=UTC).isoformat()


def normalize_message(message: Message, *, inbox_id: str) -> dict[str, Any]:
    """Build the envelope for one inbound message, WITHOUT its attachments.

    Attachment bytes need two further HTTP round-trips per item (see
    :mod:`app.attachments`), so they are filled in by the pipeline; this
    function stays pure and synchronously testable.

    ``auth_state`` is ``"pass"``: v1 forwards plain ``message.received`` only —
    AgentMail routes unauthenticated/spam arrivals to the
    ``.unauthenticated``/``.spam`` event variants, and the subscriber's
    ``messages.list`` call excludes them explicitly. Carrying a real ``fail``/
    ``unknown`` through to the thread (and capping the agent ladder on it) is
    **deferred to INTAKE-3, plan security posture #2**
    (``docs/fork/plans/INTAKE-INBOX-plan.md``) — ADR-F086 does not decide it.
    """

    body = message.text or getattr(message, "extracted_text", None) or ""
    text = truncate_body(strip_nuls(body))

    return {
        "provider": "agentmail",
        "inbox_id": inbox_id,
        "thread": {
            "provider_thread_id": message.thread_id,
            "subject": _clean(message.subject, limit=MAX_SUBJECT_CHARS),
        },
        "message": {
            # An RFC-822 id (angle brackets and all) minted by the SENDER —
            # opaque string, never parsed. Deliberately NOT truncated: it is
            # the api's idempotency anchor and a shortened id is a wrong
            # identity, where an over-long one is a loud 422 we can chase.
            "provider_message_id": message.message_id,
            "from_addr": _bound_sender(message.from_),
            "to": _bound_addresses(list(message.to or []), field="to"),
            "cc": _bound_addresses(list(message.cc or []), field="cc"),
            "timestamp": _coerce_timestamp(message.timestamp),
            "text": text,
            "headers": _bound_headers(message),
            "auth_state": "pass",
            "attachments": [],
        },
    }
