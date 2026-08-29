"""Dev ingress — AgentMail websocket subscriber — INTAKE-2 (ADR-F086).

ADR-F086 picks the websocket for development because the dev box has no public
URL AgentMail could POST a webhook to. The probe confirmed the mechanics
(``docs/fork/evidence/intake-probe/findings.md`` §Step-1, verdict (d)):
``connect()`` in ~0.8 s, ``Subscribe(inbox_ids=[…])`` acked in ~300 ms, typed
pydantic frames, stable for the whole observation window.

Three properties shape this loop:

1. **The SDK has no auto-reconnect.** A dropped socket simply ends the async
   iteration. Hence the outer forever-loop with exponential backoff (capped),
   logging reconnects as events only — never content.
2. **A clean close looks like success.** ``websockets`` swallows
   ``ConnectionClosedOK`` at the end of its async iteration, so a server that
   closes with code 1000 returns from :meth:`MailSubscriber._connect_once`
   *normally*. Resetting the backoff on every such return produced a ~2/second
   reconnect storm, each cycle re-running a full reconciliation (list + N gets +
   N attachment downloads + N POSTs at the api). The backoff is therefore reset
   only after a session that actually stayed up (:data:`_MIN_HEALTHY_SESSION_SECONDS`);
   anything shorter is treated as a failed session and grows the delay.
3. **There is no replay.** ``inboxes.events.list`` turned out to be a
   *label-only* log: delivery frames missed while disconnected can never be
   replayed from it. So every (re)connect runs a **reconciliation poll** and
   forwards everything labelled ``received``. The bridge keeps NO durable
   state — the api's ``(thread, provider_message_id)`` idempotency turns a
   re-POST into a cheap ``duplicate: true``. An in-process high-water mark is
   kept purely as a cost bound (see :meth:`MailSubscriber.reconcile`); losing it
   on restart costs one extra newest-page sweep, never correctness.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime

from agentmail import AsyncAgentMail, Error, Subscribe, Subscribed

from .pipeline import IntakePipeline

log = logging.getLogger(__name__)

_RECEIVED_LABEL = "received"
_RECONCILE_LIMIT = 50
_RECONCILE_MAX_PAGES = 10
_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 60.0
_SUBSCRIBE_ACK_TIMEOUT_SECONDS = 30.0
#: A session shorter than this never counts as "healthy" — see module docstring.
_MIN_HEALTHY_SESSION_SECONDS = 30.0


class SubscriptionNotAcked(RuntimeError):
    """The server never acked our ``subscribe`` frame."""


class MailSubscriber:
    """Keeps one long-lived subscription to the intake inbox alive."""

    def __init__(
        self,
        *,
        client: AsyncAgentMail,
        pipeline: IntakePipeline,
        inbox_id: str,
        max_backoff_seconds: float = _MAX_BACKOFF_SECONDS,
        min_healthy_session_seconds: float = _MIN_HEALTHY_SESSION_SECONDS,
        ack_timeout_seconds: float = _SUBSCRIBE_ACK_TIMEOUT_SECONDS,
    ) -> None:
        self._client = client
        self._pipeline = pipeline
        self._inbox_id = inbox_id
        self._max_backoff = max_backoff_seconds
        self._min_healthy_session = min_healthy_session_seconds
        self._ack_timeout = ack_timeout_seconds
        # In-process only. Never persisted; see the module docstring.
        self._last_seen_timestamp: datetime | None = None
        self._connected_at: float | None = None
        self._last_frame_at: float | None = None

    # -- observability ------------------------------------------------------

    def health(self) -> dict[str, object]:
        """A counts-and-ages snapshot for ``/readyz``.

        A silently dead subscription is otherwise invisible: the process is up,
        the port answers, and no mail arrives. Ages make that observable.
        """

        now = time.monotonic()
        return {
            "connected": self._connected_at is not None,
            "seconds_since_connect": (
                round(now - self._connected_at, 1) if self._connected_at is not None else None
            ),
            "seconds_since_last_frame": (
                round(now - self._last_frame_at, 1) if self._last_frame_at is not None else None
            ),
        }

    # -- the loop -----------------------------------------------------------

    async def run(self) -> None:
        """Connect / reconcile / consume, forever, with backoff on failure.

        Cancellation (process shutdown) propagates out untouched; every other
        exception is a reconnect, because a bridge that exits on the first
        provider hiccup silently stops the whole intake surface.
        """

        # The cap bounds the FIRST wait too, not just the doubling.
        initial = min(_INITIAL_BACKOFF_SECONDS, self._max_backoff)
        backoff = initial
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                await self._connect_once()
                uptime = time.monotonic() - started
                if uptime >= self._min_healthy_session:
                    # Only a session that actually stayed up earns a reset.
                    backoff = initial
                    attempt = 0
                    log.info(
                        "mail-bridge: websocket stream ended; reconnecting",
                        extra={
                            "event": "mail_ws_stream_ended",
                            "uptime_seconds": round(uptime, 1),
                        },
                    )
                else:
                    # A clean-but-instant close is a failure in disguise; let
                    # the backoff grow so it cannot become a reconnect storm.
                    attempt += 1
                    log.warning(
                        "mail-bridge: websocket closed too quickly; backing off",
                        extra={
                            "event": "mail_ws_short_session",
                            "attempt": attempt,
                            "uptime_seconds": round(uptime, 1),
                            "backoff_seconds": round(backoff, 2),
                        },
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt += 1
                log.warning(
                    "mail-bridge: websocket session failed; backing off",
                    extra={
                        "event": "mail_ws_reconnect",
                        "attempt": attempt,
                        "backoff_seconds": round(backoff, 2),
                        "error_type": type(exc).__name__,
                    },
                )
            finally:
                self._connected_at = None
            # Full jitter keeps several bridge replicas from re-dialling in
            # lockstep after a provider-side blip.
            await asyncio.sleep(random.uniform(0, backoff))
            backoff = min(self._max_backoff, backoff * 2)

    async def _connect_once(self) -> None:
        async with self._client.websockets.connect() as socket:
            await socket.send_subscribe(Subscribe(inbox_ids=[self._inbox_id]))
            await self._await_ack(socket)
            self._connected_at = time.monotonic()
            self._last_frame_at = self._connected_at
            log.info("mail-bridge: subscribed", extra={"event": "mail_ws_subscribed"})
            # Reconciliation runs on EVERY (re)connect — see the module
            # docstring. Best-effort: a provider hiccup on `messages.list` must
            # never stop us from serving the live stream we just established.
            try:
                await self.reconcile()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "mail-bridge: reconciliation poll failed; serving live stream anyway",
                    extra={
                        "event": "mail_reconcile_poll_failed",
                        "error_type": type(exc).__name__,
                    },
                )
            async for frame in socket:
                self._last_frame_at = time.monotonic()
                await self._handle_frame(frame)

    async def _await_ack(self, socket: object) -> None:
        """Block until the server acks the subscription, or fail the session.

        Without this, a socket that connects but never subscribes looks healthy:
        we would log "subscribed", poll once, and then sit silent forever.
        """

        recv = getattr(socket, "recv", None)
        if recv is None:  # pragma: no cover - defensive; the SDK always has it
            return
        try:
            frame = await asyncio.wait_for(recv(), timeout=self._ack_timeout)
        except TimeoutError as exc:
            raise SubscriptionNotAcked(f"no subscribe ack within {self._ack_timeout:.0f}s") from exc
        if isinstance(frame, Error):
            # `name`/`message` are the provider's own error taxonomy, not email
            # content — but only the name is logged, per the audit contract.
            raise SubscriptionNotAcked(f"server rejected the subscription: {frame.name}")
        if not isinstance(frame, Subscribed):
            raise SubscriptionNotAcked(f"unexpected first frame: {type(frame).__name__}")

    async def _handle_frame(self, frame: object) -> None:
        if isinstance(frame, Error):
            log.warning(
                "mail-bridge: provider error frame",
                extra={"event": "mail_ws_error_frame", "error_name": str(frame.name)},
            )
            return
        if isinstance(frame, Subscribed):
            # A re-ack (e.g. after a server-side resubscribe) is informational.
            log.info("mail-bridge: subscription re-acked", extra={"event": "mail_ws_resubscribed"})
            return
        try:
            await self._pipeline.process_event(frame)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # One bad message must not tear down the subscription: log the
            # failure by type and keep serving the inbox. The api's idempotency
            # means a later reconciliation can still land it.
            log.warning(
                "mail-bridge: failed to process frame",
                extra={"event": "mail_frame_failed", "error_type": type(exc).__name__},
            )

    # -- reconciliation -----------------------------------------------------

    async def reconcile(self) -> int:
        """Forward recently-received messages; return how many were landed.

        Cold start (no high-water mark yet) sweeps the newest page. Afterwards
        it asks only for what arrived ``after`` the newest message already seen,
        oldest-first, following ``next_page_token`` — so a reconnect storm or a
        long outage cannot turn into an unbounded re-download of the same fifty
        messages and their attachments.

        Re-forwarding is still always SAFE (the api answers ``duplicate: true``);
        the cursor is a cost bound, not a correctness mechanism, which is why
        losing it on restart is fine.

        Spam / blocked / unauthenticated arrivals are excluded EXPLICITLY rather
        than relying on the server's defaults: v1 forwards only mail that
        AgentMail authenticated (see ``normalize_message``'s ``auth_state``).
        """

        forwarded = 0
        page_token: str | None = None
        cold_start = self._last_seen_timestamp is None
        listed = 0

        for _page in range(_RECONCILE_MAX_PAGES):
            listing = await self._client.inboxes.messages.list(
                self._inbox_id,
                limit=_RECONCILE_LIMIT,
                page_token=page_token,
                # Cold start: newest page, provider default ordering. Warm:
                # everything after the high-water mark, oldest-first, so the
                # cursor advances monotonically across pages.
                after=self._last_seen_timestamp,
                ascending=None if cold_start else True,
                include_spam=False,
                include_blocked=False,
                include_unauthenticated=False,
            )
            items = list(listing.messages or [])
            listed += len(items)
            for item in items:
                self._advance_cursor(item)
                if _RECEIVED_LABEL not in (item.labels or []):
                    continue
                if await self._land(item.message_id):
                    forwarded += 1
            page_token = getattr(listing, "next_page_token", None)
            if cold_start or not page_token:
                # Cold start deliberately takes the newest page only.
                break

        log.info(
            "mail-bridge: reconciliation complete",
            extra={
                "event": "mail_reconciled",
                "cold_start": cold_start,
                "listed": listed,
                "forwarded": forwarded,
            },
        )
        return forwarded

    def _advance_cursor(self, item: object) -> None:
        timestamp = getattr(item, "timestamp", None)
        if not isinstance(timestamp, datetime):
            return
        if self._last_seen_timestamp is None or timestamp > self._last_seen_timestamp:
            self._last_seen_timestamp = timestamp

    async def _land(self, message_id: str) -> bool:
        try:
            # The list item carries no body — fetch the full message.
            message = await self._client.inboxes.messages.get(self._inbox_id, message_id)
            await self._pipeline.process_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning(
                "mail-bridge: reconciliation could not land a message",
                extra={
                    "event": "mail_reconcile_failed",
                    "error_type": type(exc).__name__,
                },
            )
            return False
        return True
