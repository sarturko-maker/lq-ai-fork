"""normalize → fetch attachments → forward — INTAKE-2 (ADR-F086).

The single path both ingresses share: the websocket subscriber (dev) and the
Svix-verified webhook route (prod) each end here, so there is exactly one place
where an AgentMail message becomes an LQ.AI envelope.

The loop guard lives here too: only a plain ``message.received`` is ever
processed. The probe proved a self-send fires ``message.sent`` +
``message.delivered`` and NEVER re-enters as ``message.received``
(``docs/fork/evidence/intake-probe/findings.md`` verdict (a)), so filtering on
the event type is a complete guard against the agent answering itself — no
state, no heuristics. The ``.spam``/``.unauthenticated``/``.blocked`` variants
are deliberately NOT forwarded in v1 (ADR-F086: ``auth_state`` widening is
future work).
"""

from __future__ import annotations

import logging
from typing import Any

from agentmail import Message

from .attachments import AttachmentFetcher
from .forwarder import IntakeForwarder
from .normalize import normalize_message

log = logging.getLogger(__name__)

#: The ONLY event type this bridge acts on. See the module docstring.
RECEIVED_EVENT_TYPE = "message.received"


class MalformedReceivedEvent(RuntimeError):
    """A ``message.received`` frame whose message could not be read."""


class IntakePipeline:
    """Turns one AgentMail message into one landed intake envelope."""

    def __init__(
        self,
        *,
        inbox_id: str,
        fetcher: AttachmentFetcher,
        forwarder: IntakeForwarder,
    ) -> None:
        self._inbox_id = inbox_id
        self._fetcher = fetcher
        self._forwarder = forwarder

    async def process_message(self, message: Message) -> dict[str, Any]:
        envelope = normalize_message(message, inbox_id=self._inbox_id)
        envelope["message"]["attachments"] = await self._fetcher.fetch_all(
            list(message.attachments or []),
            inbox_id=self._inbox_id,
            message_id=message.message_id,
        )
        return await self._forwarder.forward(envelope)

    async def process_event(self, event: object) -> dict[str, Any] | None:
        """Process a websocket/webhook frame, or return ``None`` if it is not ours.

        Anything that is not a plain ``message.received`` — our own
        ``message.sent``/``message.delivered`` copies included — is dropped
        here, silently by design: a log line per outbound delivery would be
        noise, and the count that matters (envelopes forwarded) is logged by the
        forwarder.
        """

        event_type = getattr(event, "event_type", None)
        if event_type != RECEIVED_EVENT_TYPE:
            return None
        message = getattr(event, "message", None)
        if not isinstance(message, Message):
            # A `message.received` we cannot read is NOT junk to be dropped: the
            # email is real and this is our bug or a provider contract change.
            # Raising makes the webhook answer 5xx (Svix retries, so the
            # delivery survives long enough to be noticed) and makes the
            # subscriber log it loudly — where returning None silently binned a
            # real inbound email.
            raise MalformedReceivedEvent(
                f"message.received carried no parsable message ({type(message).__name__})"
            )
        return await self.process_message(message)
