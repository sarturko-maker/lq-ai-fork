"""Dev ingress — websocket subscriber + reconciliation — INTAKE-2 (ADR-F086).

The reconciliation poll is what closes the gap the probe found: AgentMail keeps
NO replayable delivery log, so a bridge that was disconnected can only catch up
by re-listing. It is safe to re-forward because the api's idempotency turns a
repeat into ``duplicate: true`` — which is why this bridge keeps no durable
state, only an in-process high-water mark as a cost bound.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

import pytest
from agentmail import Error, Message, MessageSentEvent, Subscribed
from agentmail.core.unchecked_base_model import construct_type

from app.subscriber import MailSubscriber, SubscriptionNotAcked
from tests.conftest import INBOX, make_message, make_message_payload, make_received_event


class _RecordingPipeline:
    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.events: list[Any] = []

    async def process_message(self, message: Message) -> dict[str, Any]:
        self.messages.append(message)
        return {"duplicate": False}

    async def process_event(self, event: object) -> dict[str, Any] | None:
        self.events.append(event)
        if getattr(event, "event_type", None) != "message.received":
            return None
        message = getattr(event, "message", None)
        if isinstance(message, Message):
            return await self.process_message(message)
        return None


class _FakeListing:
    def __init__(self, messages: list[Any], next_page_token: str | None = None) -> None:
        self.messages = messages
        self.next_page_token = next_page_token


class _FakeMessagesClient:
    def __init__(
        self,
        listing: list[Any],
        *,
        get_raises: Exception | None = None,
        list_raises: Exception | None = None,
        pages: list[_FakeListing] | None = None,
    ) -> None:
        self._listing = listing
        self._get_raises = get_raises
        self._list_raises = list_raises
        self._pages = pages
        self.get_calls: list[str] = []
        self.list_calls: list[dict[str, Any]] = []

    async def list(self, inbox_id: str, **kwargs: Any) -> _FakeListing:
        assert inbox_id == INBOX
        self.list_calls.append(kwargs)
        if self._list_raises is not None:
            raise self._list_raises
        if self._pages is not None:
            return self._pages[min(len(self.list_calls) - 1, len(self._pages) - 1)]
        return _FakeListing(self._listing)

    async def get(self, inbox_id: str, message_id: str) -> Message:
        self.get_calls.append(message_id)
        if self._get_raises is not None:
            raise self._get_raises
        return make_message(message_id=message_id)


_ACK = construct_type(type_=Subscribed, object_={"type": "subscribed", "inbox_ids": [INBOX]})


class _FakeSocket:
    """Mimics the SDK socket: ``recv()`` for the ack, then async iteration."""

    def __init__(self, frames: list[Any], *, ack: Any = _ACK, ack_hangs: bool = False) -> None:
        self._frames = frames
        self._ack = ack
        self._ack_hangs = ack_hangs
        self.subscribed: list[Any] = []

    async def send_subscribe(self, message: Any) -> None:
        self.subscribed.append(message)

    async def recv(self) -> Any:
        if self._ack_hangs:
            await asyncio.sleep(3600)
        return self._ack

    async def __aiter__(self) -> Any:
        for frame in self._frames:
            yield frame


class _FakeWebsockets:
    def __init__(self, socket: _FakeSocket) -> None:
        self._socket = socket

    @contextlib.asynccontextmanager
    async def connect(self) -> Any:
        yield self._socket


class _FakeInboxes:
    def __init__(self, messages: _FakeMessagesClient) -> None:
        self.messages = messages


class _FakeClient:
    def __init__(self, messages: _FakeMessagesClient, socket: _FakeSocket) -> None:
        self.inboxes = _FakeInboxes(messages)
        self.websockets = _FakeWebsockets(socket)


def _item(message_id: str, labels: list[str], **overrides: Any) -> Any:
    return construct_type(
        type_=Message,
        object_=make_message_payload(message_id=message_id, labels=labels, **overrides),
    )


def _sent_frame(event_id: str = "d" * 32) -> Any:
    return construct_type(
        type_=MessageSentEvent,
        object_={
            "type": "event",
            "event_type": "message.sent",
            "event_id": event_id,
            "send": {"inbox_id": INBOX, "message_id": "<own@email.amazonses.com>"},
        },
    )


def _subscriber(
    listing: list[Any],
    frames: list[Any],
    *,
    get_raises: Exception | None = None,
    list_raises: Exception | None = None,
    pages: list[_FakeListing] | None = None,
    socket: _FakeSocket | None = None,
    **kwargs: Any,
) -> tuple[MailSubscriber, _RecordingPipeline, _FakeMessagesClient, _FakeSocket]:
    messages = _FakeMessagesClient(
        listing, get_raises=get_raises, list_raises=list_raises, pages=pages
    )
    sock = socket if socket is not None else _FakeSocket(frames)
    pipeline = _RecordingPipeline()
    subscriber = MailSubscriber(
        client=_FakeClient(messages, sock),  # type: ignore[arg-type]
        pipeline=pipeline,  # type: ignore[arg-type]
        inbox_id=INBOX,
        **kwargs,
    )
    return subscriber, pipeline, messages, sock


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


async def test_reconcile_forwards_only_received_messages() -> None:
    subscriber, pipeline, messages, _ = _subscriber(
        [
            _item("<inbound-1@example.com>", ["received", "unread"]),
            _item("<outbound-1@email.amazonses.com>", ["sent"]),
            _item("<inbound-2@example.com>", ["received"]),
        ],
        [],
    )

    forwarded = await subscriber.reconcile()

    assert forwarded == 2
    assert messages.get_calls == ["<inbound-1@example.com>", "<inbound-2@example.com>"]
    assert len(pipeline.messages) == 2


async def test_reconcile_excludes_spam_blocked_unauthenticated_explicitly() -> None:
    """v1 forwards only mail AgentMail authenticated — never on server defaults."""

    subscriber, _, messages, _ = _subscriber([], [])
    await subscriber.reconcile()

    call = messages.list_calls[0]
    assert call["include_spam"] is False
    assert call["include_blocked"] is False
    assert call["include_unauthenticated"] is False
    assert call["limit"] == 50


async def test_cold_start_takes_the_newest_page_only() -> None:
    subscriber, _, messages, _ = _subscriber(
        [_item("<inbound-1@example.com>", ["received"])],
        [],
        pages=[
            _FakeListing([_item("<inbound-1@example.com>", ["received"])], "page-2"),
            _FakeListing([_item("<inbound-2@example.com>", ["received"])], None),
        ],
    )

    await subscriber.reconcile()

    # One call, no `after`, and the next_page_token is deliberately not chased.
    assert len(messages.list_calls) == 1
    assert messages.list_calls[0]["after"] is None


async def test_second_reconcile_asks_only_for_newer_messages() -> None:
    """The high-water mark bounds re-download cost across reconnects."""

    newest = "2026-08-29T21:00:00Z"
    subscriber, _, messages, _ = _subscriber(
        [_item("<inbound-1@example.com>", ["received"], timestamp=newest)], []
    )

    await subscriber.reconcile()
    await subscriber.reconcile()

    first, second = messages.list_calls[0], messages.list_calls[1]
    assert first["after"] is None and first["ascending"] is None
    assert second["after"] == datetime(2026, 8, 29, 21, 0, tzinfo=UTC)
    assert second["ascending"] is True


async def test_warm_reconcile_follows_pagination() -> None:
    subscriber, pipeline, messages, _ = _subscriber(
        [],
        [],
        pages=[
            # Cold-start page seeds the cursor.
            _FakeListing(
                [_item("<a@example.com>", ["received"], timestamp="2026-08-29T20:00:00Z")]
            ),
            _FakeListing(
                [_item("<b@example.com>", ["received"], timestamp="2026-08-29T21:00:00Z")],
                "page-2",
            ),
            _FakeListing(
                [_item("<c@example.com>", ["received"], timestamp="2026-08-29T22:00:00Z")], None
            ),
        ],
    )

    await subscriber.reconcile()  # cold start: 1 call
    await subscriber.reconcile()  # warm: follows next_page_token

    assert len(messages.list_calls) == 3
    assert messages.list_calls[2]["page_token"] == "page-2"
    assert [m.message_id for m in pipeline.messages] == [
        "<a@example.com>",
        "<b@example.com>",
        "<c@example.com>",
    ]


async def test_reconcile_survives_one_bad_message() -> None:
    """One failure must not abort the catch-up for the rest of the inbox."""

    subscriber, pipeline, _, _ = _subscriber(
        [_item("<inbound-1@example.com>", ["received"])], [], get_raises=RuntimeError("boom")
    )

    assert await subscriber.reconcile() == 0
    assert pipeline.messages == []


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


async def test_connect_reconciles_before_consuming_frames() -> None:
    subscriber, pipeline, _messages, socket = _subscriber(
        [_item("<inbound-1@example.com>", ["received"])],
        [_sent_frame(), make_received_event(message_id="<inbound-live@example.com>")],
    )

    await subscriber._connect_once()

    # Subscribed to exactly our inbox.
    assert socket.subscribed[0].inbox_ids == [INBOX]
    # Reconciliation ran first (its message is the earliest recorded).
    assert pipeline.messages[0].message_id == "<inbound-1@example.com>"
    assert [m.message_id for m in pipeline.messages] == [
        "<inbound-1@example.com>",
        "<inbound-live@example.com>",
    ]


async def test_message_sent_frame_is_never_forwarded() -> None:
    """Loop guard at the socket level — nothing outbound re-enters as intake."""

    subscriber, pipeline, _, _ = _subscriber([], [_sent_frame("e" * 32)])

    await subscriber._connect_once()

    assert pipeline.messages == []


async def test_frame_failure_does_not_kill_the_subscription() -> None:
    class _ExplodingPipeline(_RecordingPipeline):
        async def process_event(self, event: object) -> dict[str, Any] | None:
            self.events.append(event)
            raise RuntimeError("downstream unavailable")

    messages = _FakeMessagesClient([])
    socket = _FakeSocket([make_received_event(), make_received_event()])
    pipeline = _ExplodingPipeline()
    subscriber = MailSubscriber(
        client=_FakeClient(messages, socket),  # type: ignore[arg-type]
        pipeline=pipeline,  # type: ignore[arg-type]
        inbox_id=INBOX,
    )

    await subscriber._connect_once()

    assert len(pipeline.events) == 2  # the second frame was still served


async def test_reconcile_failure_does_not_prevent_serving_the_stream() -> None:
    """A `messages.list` outage must never cost us the live subscription."""

    subscriber, pipeline, _, _ = _subscriber(
        [],
        [make_received_event(message_id="<inbound-live@example.com>")],
        list_raises=RuntimeError("provider 503"),
    )

    await subscriber._connect_once()

    assert [m.message_id for m in pipeline.messages] == ["<inbound-live@example.com>"]


async def test_missing_ack_fails_the_session() -> None:
    """A socket that connects but never subscribes must not look healthy."""

    subscriber, pipeline, messages, _ = _subscriber(
        [], [], socket=_FakeSocket([], ack_hangs=True), ack_timeout_seconds=0.01
    )

    with pytest.raises(SubscriptionNotAcked):
        await subscriber._connect_once()

    assert messages.list_calls == []  # never reconciled on an unacked socket
    assert pipeline.messages == []


async def test_error_ack_fails_the_session() -> None:
    error = construct_type(
        type_=Error, object_={"type": "error", "name": "unauthorized", "message": "bad key"}
    )
    subscriber, _, _, _ = _subscriber([], [], socket=_FakeSocket([], ack=error))

    with pytest.raises(SubscriptionNotAcked):
        await subscriber._connect_once()


async def test_error_frame_mid_stream_is_logged_not_forwarded() -> None:
    error = construct_type(
        type_=Error, object_={"type": "error", "name": "rate_limited", "message": "slow down"}
    )
    subscriber, pipeline, _, _ = _subscriber([], [error, make_received_event()])

    await subscriber._connect_once()

    assert len(pipeline.messages) == 1  # the error frame never reached the pipeline
    assert error not in pipeline.events


async def test_health_snapshot_reports_ages() -> None:
    subscriber, _, _, _ = _subscriber([], [make_received_event()])

    assert subscriber.health()["connected"] is False
    await subscriber._connect_once()
    health = subscriber.health()
    # run() clears connected_at on exit; _connect_once alone leaves it set.
    assert health["connected"] is True
    assert isinstance(health["seconds_since_last_frame"], float)


# ---------------------------------------------------------------------------
# The reconnect loop
# ---------------------------------------------------------------------------


async def test_run_reconnects_with_backoff_and_is_cancellable() -> None:
    """No auto-reconnect in the SDK — the loop is what keeps intake alive."""

    attempts = 0

    class _FlakySubscriber(MailSubscriber):
        async def _connect_once(self) -> None:
            nonlocal attempts
            attempts += 1
            raise ConnectionError("socket dropped")

    subscriber = _FlakySubscriber(
        client=_FakeClient(_FakeMessagesClient([]), _FakeSocket([])),  # type: ignore[arg-type]
        pipeline=_RecordingPipeline(),  # type: ignore[arg-type]
        inbox_id=INBOX,
        max_backoff_seconds=0.001,
    )

    task = asyncio.create_task(subscriber.run())
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert attempts > 1


async def _record_backoffs(
    subscriber: MailSubscriber, monkeypatch: pytest.MonkeyPatch, *, cycles: int = 5
) -> list[float]:
    """Run the loop and capture the delay it asks for on each cycle.

    ``random.uniform`` is pinned to the full backoff so the sequence is the
    schedule itself, not a sample of it; the sleep is replaced so the test does
    not actually wait, and stops the loop once enough cycles are recorded.
    """

    real_sleep = asyncio.sleep
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) >= cycles:
            raise asyncio.CancelledError
        await real_sleep(0)

    monkeypatch.setattr("app.subscriber.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.subscriber.random.uniform", lambda _a, b: b)

    with contextlib.suppress(asyncio.CancelledError):
        await subscriber.run()
    return delays


async def test_clean_instant_close_does_not_become_a_reconnect_storm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE regression this guards.

    ``websockets`` swallows ``ConnectionClosedOK``, so a server closing with
    code 1000 makes ``_connect_once`` RETURN rather than raise. Resetting the
    backoff on every such return spun at ~2 reconnects/second, each re-running a
    full reconciliation (list + N gets + N attachment downloads + N POSTs at the
    api) — a self-inflicted DoS on our own api. A session shorter than the
    healthy threshold must grow the backoff exactly like a failure does.

    Before the fix this sequence was [1.0, 1.0, 1.0, 1.0, 1.0].
    """

    sessions = 0

    class _CleanCloseSubscriber(MailSubscriber):
        async def _connect_once(self) -> None:
            nonlocal sessions
            sessions += 1
            return  # clean close, zero uptime

    subscriber = _CleanCloseSubscriber(
        client=_FakeClient(_FakeMessagesClient([]), _FakeSocket([])),  # type: ignore[arg-type]
        pipeline=_RecordingPipeline(),  # type: ignore[arg-type]
        inbox_id=INBOX,
        max_backoff_seconds=60.0,
        min_healthy_session_seconds=30.0,
    )

    delays = await _record_backoffs(subscriber, monkeypatch)

    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert sessions == 5


async def test_backoff_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    class _CleanCloseSubscriber(MailSubscriber):
        async def _connect_once(self) -> None:
            return

    subscriber = _CleanCloseSubscriber(
        client=_FakeClient(_FakeMessagesClient([]), _FakeSocket([])),  # type: ignore[arg-type]
        pipeline=_RecordingPipeline(),  # type: ignore[arg-type]
        inbox_id=INBOX,
        max_backoff_seconds=4.0,
        min_healthy_session_seconds=30.0,
    )

    delays = await _record_backoffs(subscriber, monkeypatch)

    assert delays == [1.0, 2.0, 4.0, 4.0, 4.0]


async def test_healthy_session_resets_the_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """A session that really stayed up must not inherit an old penalty."""

    class _HealthySubscriber(MailSubscriber):
        async def _connect_once(self) -> None:
            return

    subscriber = _HealthySubscriber(
        client=_FakeClient(_FakeMessagesClient([]), _FakeSocket([])),  # type: ignore[arg-type]
        pipeline=_RecordingPipeline(),  # type: ignore[arg-type]
        inbox_id=INBOX,
        max_backoff_seconds=60.0,
        # Every session counts as healthy, so the reset branch is the one taken.
        min_healthy_session_seconds=0.0,
    )

    delays = await _record_backoffs(subscriber, monkeypatch)

    assert delays == [1.0, 1.0, 1.0, 1.0, 1.0]


async def test_failed_session_also_grows_the_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingSubscriber(MailSubscriber):
        async def _connect_once(self) -> None:
            raise ConnectionError("socket dropped")

    subscriber = _FailingSubscriber(
        client=_FakeClient(_FakeMessagesClient([]), _FakeSocket([])),  # type: ignore[arg-type]
        pipeline=_RecordingPipeline(),  # type: ignore[arg-type]
        inbox_id=INBOX,
        max_backoff_seconds=60.0,
    )

    delays = await _record_backoffs(subscriber, monkeypatch)

    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]
