"""normalize → fetch → forward, and the loop guard — INTAKE-2 (ADR-F086).

The loop guard is the whole reason a self-send cannot make the agent answer
itself: the probe proved an outbound copy fires ``message.sent`` +
``message.delivered`` and NEVER ``message.received``, so an event-type filter is
a complete guard (``docs/fork/evidence/intake-probe/findings.md`` verdict (a)).
"""

from __future__ import annotations

from typing import Any

import pytest
from agentmail import Attachment, MessageSentEvent
from agentmail.core.unchecked_base_model import construct_type

from app.pipeline import IntakePipeline, MalformedReceivedEvent
from tests.conftest import INBOX, make_attachment, make_message, make_received_event


class _FakeFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    async def fetch_all(
        self,
        attachments: list[Attachment] | None,
        *,
        inbox_id: str,
        message_id: str,
    ) -> list[dict[str, Any]]:
        self.calls.append((inbox_id, message_id, len(attachments or [])))
        return [
            {
                "filename": "SecureScan-MSA.docx",
                "content_type": "application/octet-stream",
                "content_b64": "AAAA",
            }
        ]


class _FakeForwarder:
    def __init__(self) -> None:
        self.envelopes: list[dict[str, Any]] = []

    async def forward(self, envelope: dict[str, Any]) -> dict[str, Any]:
        self.envelopes.append(envelope)
        return {"duplicate": False, "files_ingested": 1}


def _pipeline() -> tuple[IntakePipeline, _FakeFetcher, _FakeForwarder]:
    fetcher, forwarder = _FakeFetcher(), _FakeForwarder()
    pipeline = IntakePipeline(
        inbox_id=INBOX,
        fetcher=fetcher,  # type: ignore[arg-type]
        forwarder=forwarder,  # type: ignore[arg-type]
    )
    return pipeline, fetcher, forwarder


async def test_process_message_normalizes_fetches_and_forwards() -> None:
    pipeline, fetcher, forwarder = _pipeline()
    message = make_message(attachments=[make_attachment().model_dump()])

    result = await pipeline.process_message(message)

    assert result == {"duplicate": False, "files_ingested": 1}
    assert fetcher.calls == [(INBOX, "<CAF-abc123@mail.gmail.com>", 1)]
    envelope = forwarder.envelopes[0]
    assert envelope["provider"] == "agentmail"
    assert len(envelope["message"]["attachments"]) == 1


async def test_received_event_is_forwarded() -> None:
    pipeline, _, forwarder = _pipeline()
    await pipeline.process_event(make_received_event())
    assert len(forwarder.envelopes) == 1


async def test_message_sent_event_is_never_forwarded() -> None:
    """THE loop guard: our own outbound copy must not re-enter as intake."""

    pipeline, fetcher, forwarder = _pipeline()
    sent = construct_type(
        type_=MessageSentEvent,
        object_={
            "type": "event",
            "event_type": "message.sent",
            "event_id": "a" * 32,
            "send": {
                "inbox_id": INBOX,
                "thread_id": "2e1c9f73-4e29-424c-8404-c8cd03306c44",
                "message_id": "<010001a0@email.amazonses.com>",
                "timestamp": "2026-08-29T20:14:39Z",
                "recipients": [INBOX],
            },
        },
    )

    assert await pipeline.process_event(sent) is None
    assert forwarder.envelopes == []
    assert fetcher.calls == []


async def test_unauthenticated_variant_is_not_forwarded() -> None:
    """v1 subscribes to plain ``message.received`` only (ADR-F086)."""

    pipeline, _, forwarder = _pipeline()
    event = make_received_event()
    variant = event.model_copy(update={"event_type": "message.received.unauthenticated"})

    assert await pipeline.process_event(variant) is None
    assert forwarder.envelopes == []


async def test_event_without_a_message_raises_rather_than_dropping_it() -> None:
    """A signed `message.received` we cannot read is a real email, not junk.

    Returning None here silently binned it; raising makes the webhook 5xx (Svix
    retries) and the subscriber log it, without tearing down the stream.
    """

    class _Bogus:
        event_type = "message.received"
        message = None

    pipeline, _, forwarder = _pipeline()
    with pytest.raises(MalformedReceivedEvent):
        await pipeline.process_event(_Bogus())
    assert forwarder.envelopes == []
