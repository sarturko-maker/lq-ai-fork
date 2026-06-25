"""Run-event streaming — F0-S7 (fork): AI SDK UI Message Stream v1.

In-process bridge between the agent runner (a FastAPI ``BackgroundTask``)
and the SSE endpoint (``GET /agents/runs/{run_id}/stream``), speaking the
Vercel AI SDK **UI Message Stream v1** — spec-only, hand-rolled emitter,
no Vercel runtime (ADR-F006 option 2; the wire spec was accepted there).

Render-determinism (ADR-F004) shapes how the protocol is used:

* Every settled ``agent_run_steps`` row is mirrored onto the wire as a
  ``data-step`` part whose part ``id`` IS the row id. Same-id data parts
  RECONCILE client-side (the spec's replacement rule), so re-emission —
  endpoint replay, the DB-tail fallback, subscribe races — is idempotent
  by construction. Subagent ancestry rides in the payload
  (``parent_step_id``, F0-S7).
* Live-only parts (``reasoning-*`` deltas, ``tool-*`` frames,
  ``start-step``/``finish-step``, ``data-plan``) ANIMATE. Nothing
  durable derives from them; a client that misses them loses motion,
  not state — it re-derives everything from settled rows (polling
  remains the fallback).

The broker is constructed once at lifespan and injected (CLAUDE.md DI
rules): the POST handler passes it to the composition point, the stream
endpoint takes it through ``Depends``. It is process-local on purpose —
when execution moves out of process (the F1 arq migration), live parts
simply stop arriving and the endpoint's DB-tail fallback carries the
stream unchanged.

Step summaries are already bounded and secret-free when they reach this
module (runner truncation; audit rows carry counts/types/IDs — the
stream carries exactly what the polled rows carry, nothing more).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _StreamSink(Protocol):
    """What :class:`RunStreamPublisher` needs of a broker — F025.

    Both the in-process :class:`RunStreamBroker` and the cross-process
    :class:`RedisStreamBroker` satisfy it structurally, so the SAME publisher
    drives either transport.
    """

    def publish(self, run_id: uuid.UUID, part: dict[str, Any]) -> None: ...
    def close(self, run_id: uuid.UUID) -> None: ...


# Wire headers required by the spec (mirrors the SDK's
# UI_MESSAGE_STREAM_HEADERS): the version marker plus standard SSE
# anti-buffering. content-type rides on StreamingResponse's media_type.
UI_MESSAGE_STREAM_HEADERS = {
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "x-vercel-ai-ui-message-stream": "v1",
    "x-accel-buffering": "no",
}

# A subscriber that can't drain this many parts is wedged or gone — it
# gets closed (its client still has the DB-tail/polling path).
_SUBSCRIBER_QUEUE_MAX = 1000

# Closed channels linger briefly so a subscriber racing the finish still
# gets a clean close instead of a silent void.
_CLOSED_CHANNEL_RETENTION_SECONDS = 60.0

# Queue sentinel: the channel closed (run finished or evicted).
CHANNEL_CLOSED = object()


def encode_sse(part: dict[str, Any]) -> str:
    """One wire frame: ``data: {json}\\n\\n`` (compact separators)."""
    return f"data: {json.dumps(part, separators=(',', ':'), default=str)}\n\n"


SSE_DONE = "data: [DONE]\n\n"
SSE_PING = ": ping\n\n"


def step_payload(
    *,
    step_id: uuid.UUID,
    run_id: uuid.UUID,
    seq: int,
    kind: str,
    name: str | None,
    summary: str,
    parent_step_id: uuid.UUID | None,
    created_at: Any,
) -> dict[str, Any]:
    """One settled step row as a JSON-ready wire payload.

    Single builder for BOTH emitters — the runner (live path, from the
    values it just committed) and the endpoint (replay/DB-tail path,
    from the row it just read) — so the two paths cannot drift.
    """
    return {
        "id": str(step_id),
        "run_id": str(run_id),
        "seq": seq,
        "kind": kind,
        "name": name,
        "summary": summary,
        "parent_step_id": str(parent_step_id) if parent_step_id else None,
        "created_at": created_at.isoformat() if created_at else None,
    }


def step_part(step: dict[str, Any]) -> dict[str, Any]:
    """The ``data-step`` part for one settled step row (id = row id)."""
    return {"type": "data-step", "id": step["id"], "data": step}


def terminal_parts(
    *,
    run_id: uuid.UUID | str,
    status: str,
    final_answer: str | None,
    error: str | None,
) -> list[dict[str, Any]]:
    """The wire tail for a settled run, identical from every emitter.

    The publisher (live path) and the endpoint (replay / DB-tail path)
    both end streams with exactly these parts, so a client can't tell —
    or care — which path served it. The final answer streams as a text
    block (it IS the settled ``final_answer``, not a model parse);
    ``data-run`` is the reconcile signal carrying the terminal status.
    """
    parts: list[dict[str, Any]] = []
    if final_answer:
        text_id = f"answer-{run_id}"
        parts.append({"type": "text-start", "id": text_id})
        parts.append({"type": "text-delta", "id": text_id, "delta": final_answer})
        parts.append({"type": "text-end", "id": text_id})
    if error:
        parts.append({"type": "error", "errorText": error})
    parts.append(
        {
            "type": "data-run",
            "id": str(run_id),
            "data": {"status": status, "error": error},
        }
    )
    parts.append({"type": "finish"})
    return parts


class _RunChannel:
    """Fan-out state for one run: subscriber queues, closed flag, and the
    open live blocks a mid-run subscriber must have synthesized openers
    for (spec conformance — see :meth:`RunStreamBroker.subscribe`)."""

    __slots__ = ("closed", "open_reasoning", "open_tool_inputs", "subscribers")

    def __init__(self) -> None:
        self.subscribers: list[asyncio.Queue[Any]] = []
        self.closed = False
        # block id → its reasoning-start part (currently streaming).
        self.open_reasoning: dict[str, dict[str, Any]] = {}
        # toolCallId → its tool-input-available part (output not yet in).
        self.open_tool_inputs: dict[str, dict[str, Any]] = {}


# A run is watched by one user in practice; this cap only exists so a
# misbehaving client can't fan one run out to unbounded queues.
_MAX_SUBSCRIBERS_PER_RUN = 8


class RunStreamBroker:
    """Process-local pub/sub keyed by run id.

    No replay buffer on purpose: settled rows are the replay source
    (ADR-F004), the endpoint reads them itself. The ONLY live state kept
    is the set of open blocks (reasoning / pending tool inputs) so a
    mid-run subscriber's stream still satisfies the wire spec's
    start-before-delta and input-before-output correlation rules — a
    conformant AI SDK consumer crashes on a delta for an unknown id.
    Publishing never raises into the runner — a wedged subscriber is
    closed and dropped, the run is never the stream's hostage.
    """

    def __init__(self) -> None:
        self._channels: dict[uuid.UUID, _RunChannel] = {}

    def publisher(self, run_id: uuid.UUID) -> RunStreamPublisher:
        return RunStreamPublisher(self, run_id)

    def subscribe(self, run_id: uuid.UUID) -> asyncio.Queue[Any]:
        """A live queue for ``run_id`` (created lazily from either side).

        Subscribing to an already-closed (or subscriber-capped) channel
        yields a queue with the close sentinel pre-queued — the caller
        falls through to its settled-rows path immediately. A mid-run
        subscriber's queue is seeded with the openers of every block
        still in flight (synchronous with the event loop, so no part can
        interleave between seeding and registration).
        """
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAX)
        channel = self._channels.setdefault(run_id, _RunChannel())
        if channel.closed or len(channel.subscribers) >= _MAX_SUBSCRIBERS_PER_RUN:
            queue.put_nowait(CHANNEL_CLOSED)
            return queue
        for opener in (*channel.open_reasoning.values(), *channel.open_tool_inputs.values()):
            queue.put_nowait(opener)
        channel.subscribers.append(queue)
        return queue

    def unsubscribe(self, run_id: uuid.UUID, queue: asyncio.Queue[Any]) -> None:
        channel = self._channels.get(run_id)
        if channel is None:
            return
        with contextlib.suppress(ValueError):
            channel.subscribers.remove(queue)
        if not channel.subscribers:
            # Last subscriber gone: drop the channel even when no
            # publisher ever closed it (terminal replays, DB-tail-only
            # runs) — otherwise every streamed run leaks a channel for
            # the process lifetime. publish()/close() no-op on a missing
            # channel and a live publisher's next part simply recreates
            # nothing (no subscribers = nobody to tell).
            self._channels.pop(run_id, None)

    def publish(self, run_id: uuid.UUID, part: dict[str, Any]) -> None:
        channel = self._channels.get(run_id)
        if channel is None or channel.closed:
            return
        self._track_open_blocks(channel, part)
        for queue in list(channel.subscribers):
            try:
                queue.put_nowait(part)
            except asyncio.QueueFull:
                # Wedged consumer: close it out rather than block or
                # buffer unboundedly; its client re-derives from rows.
                self._drop_subscriber(channel, queue)
            except Exception:  # pragma: no cover - defensive
                logger.exception(
                    "stream publish failed; dropping subscriber",
                    extra={"event": "agent_stream_publish_failed", "run_id": str(run_id)},
                )
                self._drop_subscriber(channel, queue)

    @staticmethod
    def _track_open_blocks(channel: _RunChannel, part: dict[str, Any]) -> None:
        """Maintain the open-block state mid-run subscribers are seeded with."""
        part_type = part.get("type")
        if part_type == "reasoning-start":
            channel.open_reasoning[str(part.get("id"))] = part
        elif part_type == "reasoning-end":
            channel.open_reasoning.pop(str(part.get("id")), None)
        elif part_type == "tool-input-available":
            channel.open_tool_inputs[str(part.get("toolCallId"))] = part
        elif part_type == "tool-output-available":
            channel.open_tool_inputs.pop(str(part.get("toolCallId")), None)

    def close(self, run_id: uuid.UUID) -> None:
        """Mark the run's channel closed and wake every subscriber.

        Idempotent. The empty channel is retained briefly so a
        subscriber racing the finish still receives a clean close.
        """
        channel = self._channels.get(run_id)
        if channel is None or channel.closed:
            return
        channel.closed = True
        for queue in channel.subscribers:
            # A full queue keeps its backlog; the channel stays closed
            # regardless, so the consumer still terminates via DB state.
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(CHANNEL_CLOSED)
        channel.subscribers.clear()
        try:
            loop = asyncio.get_running_loop()
            loop.call_later(
                _CLOSED_CHANNEL_RETENTION_SECONDS,
                self._channels.pop,
                run_id,
                None,
            )
        except RuntimeError:  # no running loop (sync test context)
            self._channels.pop(run_id, None)

    def _drop_subscriber(self, channel: _RunChannel, queue: asyncio.Queue[Any]) -> None:
        try:
            channel.subscribers.remove(queue)
        except ValueError:
            return
        # Tell the consumer it was closed. The queue is full by
        # construction (that's why it was dropped), so make room first —
        # losing one animation part beats a sentinel that never arrives.
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(CHANNEL_CLOSED)


class RunStreamPublisher:
    """The runner's semantic surface; encodes wire parts, never raises.

    One per run, handed to the runner by the composition point. Methods
    are sync and fire-and-forget: streaming is best-effort animation —
    a publish failure must never fail the run (the settled rows it
    mirrors are already durable).
    """

    def __init__(self, broker: _StreamSink, run_id: uuid.UUID) -> None:
        self._broker = broker
        self._run_id = run_id
        self._open_reasoning: set[str] = set()
        self._started = False

    def _publish(self, part: dict[str, Any]) -> None:
        if not self._started:
            self._started = True
            self._broker.publish(self._run_id, {"type": "start", "messageId": str(self._run_id)})
        self._broker.publish(self._run_id, part)

    def turn_started(self) -> None:
        """A top-level model turn began (one assistant round = one step)."""
        self._publish({"type": "start-step"})

    def turn_finished(self) -> None:
        self._publish({"type": "finish-step"})

    def reasoning_delta(self, block_id: str, delta: str) -> None:
        """Live model output for the thinking ribbon (animation only).

        ALL streamed content rides as reasoning — intermediate turns,
        ``<think>`` blocks, subagent turns (distinct ``block_id`` per
        chat-model invocation). Until a row settles, none of it is an
        answer; the settled rows and the terminal text block decide
        (ADR-F004).
        """
        if block_id not in self._open_reasoning:
            self._open_reasoning.add(block_id)
            self._publish({"type": "reasoning-start", "id": block_id})
        self._publish({"type": "reasoning-delta", "id": block_id, "delta": delta})

    def reasoning_end(self, block_id: str) -> None:
        if block_id in self._open_reasoning:
            self._open_reasoning.discard(block_id)
            self._publish({"type": "reasoning-end", "id": block_id})

    def step_settled(
        self,
        step: dict[str, Any],
        *,
        tool_call_id: str | None = None,
    ) -> None:
        """Mirror one just-committed step row onto the wire.

        ``step`` is the JSON-ready row payload (the runner builds it
        from exactly what it persisted). ``tool_call_id`` correlates a
        ``tool_result`` to its ``tool_call`` row — the wire's
        ``toolCallId`` IS that settled row id.
        """
        kind = step.get("kind")
        if kind == "tool_call":
            self._publish(
                {
                    "type": "tool-input-available",
                    "toolCallId": step["id"],
                    "toolName": step.get("name") or "?",
                    "input": _parsed_or_raw(step.get("summary")),
                }
            )
            if step.get("name") == "write_todos":
                plan = _parsed_or_raw(step.get("summary"))
                if isinstance(plan, dict) and "todos" in plan:
                    self._publish({"type": "data-plan", "id": step["id"], "data": plan})
        elif kind == "tool_result" and tool_call_id is not None:
            self._publish(
                {
                    "type": "tool-output-available",
                    "toolCallId": tool_call_id,
                    "output": {"summary": step.get("summary")},
                }
            )
        self._publish(step_part(step))

    def ropa_changed(self, *, kind: str, entity_id: str, verb: str) -> None:
        """Announce one ROPA register row the agent just changed — PRIV-9b (ADR-F024).

        A TRANSIENT ``data-ropa-change`` part (the spec's ``data-*`` extension, like
        ``data-plan``) carrying ``{kind, id, verb}``. Drives the cockpit's live
        changed-row highlight: the client lifts the id into a recently-changed set
        and washes the matching register row. Transient ⇒ not tracked as an open
        block (``_track_open_blocks``), so a late subscriber simply misses it —
        animation only; the settled re-read remains the truth (ADR-F004). Ids are
        audit-safe (the audit contract allows counts/types/**IDs**)."""
        self._publish(
            {
                "type": "data-ropa-change",
                "transient": True,
                "data": {"kind": kind, "id": entity_id, "verb": verb},
            }
        )

    def deal_changed(self, *, ref: str, verdict: str) -> None:
        """Announce one counterparty item the agent just decided — C5b-3 (ADR-F032).

        The negotiation companion to :meth:`ropa_changed`: a TRANSIENT
        ``data-deal-change`` part carrying ``{ref, verdict}``. Drives the cockpit's
        live verdict chips — the conversation flashes a per-verdict chip keyed by
        ref ("C1 · accepted", "Com:1 · escalated"). Transient ⇒ not tracked as an
        open block (``_track_open_blocks``), so a late subscriber simply misses it —
        animation only; the saved response ``.docx`` and the run timeline remain the
        truth (ADR-F004). ``ref`` + ``verdict`` are audit-safe (refs/types, never raw
        clause text)."""
        self._publish(
            {
                "type": "data-deal-change",
                "transient": True,
                "data": {"ref": ref, "verdict": verdict},
            }
        )

    def run_finished(
        self,
        *,
        status: str,
        final_answer: str | None = None,
        error: str | None = None,
    ) -> None:
        """End the live stream with the settled run's terminal parts.

        Idempotent through the broker's closed flag — the composition
        point's failure path may call it after the runner already has.
        """
        for block_id in list(self._open_reasoning):
            self.reasoning_end(block_id)
        for part in terminal_parts(
            run_id=self._run_id,
            status=status,
            final_answer=final_answer,
            error=error,
        ):
            self._publish(part)
        self._broker.close(self._run_id)

    def close(self) -> None:
        """End the live channel WITHOUT terminal parts (F1-S1, ADR-F009).

        For exits where another actor settled the run (cancel endpoint /
        orphan sweep fenced our terminal write out): the wire must never
        announce a state this process didn't write. Closing the channel
        sends subscribers down the stream endpoint's ``CHANNEL_CLOSED``
        path, which ends the stream on the SETTLED run row from the DB —
        the durable truth (ADR-F004).
        """
        for block_id in list(self._open_reasoning):
            self.reasoning_end(block_id)
        self._broker.close(self._run_id)


def _parsed_or_raw(summary: str | None) -> Any:
    """Tool args as an object when the bounded digest is still valid JSON.

    Truncation can cut the JSON mid-token — then the raw digest is
    wrapped instead of guessed at.
    """
    if not summary:
        return {}
    try:
        parsed = json.loads(summary)
    except (TypeError, ValueError):
        return {"raw": summary}
    return parsed if isinstance(parsed, dict | list) else {"raw": summary}


# ---------------------------------------------------------------------------
# Cross-process transport — F025 (the worker publishes, the api relays)
# ---------------------------------------------------------------------------

_STREAM_CHANNEL_PREFIX = "agent_run_stream:"
# Distinct from any wire part (parts always carry "type") — the publish-side
# close() rides the channel after the terminal parts so the api bridge knows to
# close the local channel (→ CHANNEL_CLOSED to subscribers).
_STREAM_CLOSED_MARKER = {"__stream_closed__": True}
# Bound the publish-side buffer: a wedged drain drops parts (logged) rather than
# blocking the run — animation degrades, the run is never the stream's hostage.
_REDIS_PUBLISH_QUEUE_MAX = 2000


def stream_channel(run_id: uuid.UUID | str) -> str:
    """The Redis pub/sub channel one run's stream parts ride (F025)."""
    return f"{_STREAM_CHANNEL_PREFIX}{run_id}"


class RedisStreamBroker:
    """Publish-only, broker-shaped facade that fans run-stream parts onto Redis
    pub/sub so the api process can relay them to the browser — F025 (ADR-F025).

    Quacks like :class:`RunStreamBroker` for the publisher's needs
    (``publisher``/``publish``/``close``), so the SAME :class:`RunStreamPublisher`
    is reused unchanged in the worker. ``publish`` is sync + fire-and-forget (it
    must never raise into the runner): it enqueues onto one asyncio queue drained
    by a single background task that ``PUBLISH``es JSON parts IN ORDER — so
    ``start`` precedes ``delta`` and ``tool-input`` precedes ``tool-output``.
    One broker per worker process (created in the arq ``on_startup`` from
    ``ctx['redis']``); ``aclose`` cancels the drain on shutdown.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(
            maxsize=_REDIS_PUBLISH_QUEUE_MAX
        )
        self._drain_task: asyncio.Task[None] | None = None
        # Set by aclose() at worker shutdown: a late publish()/close() racing
        # teardown must NOT resurrect the drain task (review nit).
        self._closed = False

    def publisher(self, run_id: uuid.UUID) -> RunStreamPublisher:
        self._ensure_drain()
        return RunStreamPublisher(self, run_id)

    def publish(self, run_id: uuid.UUID, part: dict[str, Any]) -> None:
        if self._closed:
            return  # post-shutdown: drop the part rather than re-spawn the drain
        self._ensure_drain()
        try:
            self._queue.put_nowait((str(run_id), part))
        except asyncio.QueueFull:
            logger.warning(
                "redis run-stream publish queue full; dropping part",
                extra={"event": "agent_stream_redis_queue_full", "run_id": str(run_id)},
            )

    def close(self, run_id: uuid.UUID) -> None:
        """End the run's channel — rides AFTER the terminal parts (FIFO)."""
        self.publish(run_id, _STREAM_CLOSED_MARKER)

    def _ensure_drain(self) -> None:
        if self._closed:
            return
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        while True:
            run_id, part = await self._queue.get()
            try:
                await self._redis.publish(
                    stream_channel(run_id),
                    json.dumps(part, separators=(",", ":"), default=str),
                )
            except Exception:  # best-effort animation — a blip costs a part, not the run
                logger.warning(
                    "redis run-stream publish failed; dropping part",
                    extra={"event": "agent_stream_redis_publish_failed", "run_id": run_id},
                )

    async def aclose(self) -> None:
        """Cancel the drain task (worker shutdown). Idempotent, best-effort."""
        self._closed = True
        task = self._drain_task
        self._drain_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


class _BridgeSub:
    __slots__ = ("pubsub", "refcount", "task")

    def __init__(self, task: asyncio.Task[None], pubsub: Any) -> None:
        self.task = task
        self.pubsub = pubsub
        self.refcount = 1


class RedisStreamBridge:
    """Relays a run's Redis pub/sub parts into the process-local broker — F025.

    The api side of the transport: it subscribes to ``agent_run_stream:{run_id}``
    and republishes each part into the existing :class:`RunStreamBroker`, which
    fans it to the SSE endpoint's subscriber queue exactly as an in-process part.
    The endpoint and runner are untouched. Reference-counted per run id — ONE
    Redis subscription per run no matter how many browsers watch it (the local
    broker fans out), torn down when the last viewer detaches. Attach is called
    AFTER the endpoint's ownership check, so a run a user can't see is never
    bridged.
    """

    def __init__(self, redis: Any, broker: RunStreamBroker) -> None:
        self._redis = redis
        self._broker = broker
        self._subs: dict[str, _BridgeSub] = {}
        self._lock = asyncio.Lock()

    async def attach(self, run_id: uuid.UUID) -> None:
        """Ensure a Redis subscription is relaying ``run_id`` into the broker."""
        key = str(run_id)
        async with self._lock:
            sub = self._subs.get(key)
            if sub is not None:
                sub.refcount += 1
                return
            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(stream_channel(run_id))
            except Exception:
                # subscribe() can fail AFTER checking out a pooled connection
                # (a transient post-connect blip) — close the pubsub so that
                # connection is released, never leaked, then let the caller
                # fail soft to the DB-tail (review fix).
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
                raise
            task = asyncio.create_task(self._pump(run_id, pubsub))
            self._subs[key] = _BridgeSub(task=task, pubsub=pubsub)

    async def detach(self, run_id: uuid.UUID) -> None:
        """Drop one viewer; tear the subscription down when the last one leaves."""
        key = str(run_id)
        async with self._lock:
            sub = self._subs.get(key)
            if sub is None:
                return
            sub.refcount -= 1
            if sub.refcount > 0:
                return
            del self._subs[key]
        sub.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sub.task
        with contextlib.suppress(Exception):
            await sub.pubsub.aclose()

    async def _pump(self, run_id: uuid.UUID, pubsub: Any) -> None:
        key = str(run_id)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue  # skip the subscribe/unsubscribe confirmations
                raw = message.get("data")
                try:
                    part = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(part, dict):
                    continue
                if part.get("__stream_closed__"):
                    self._broker.close(run_id)
                    continue
                self._broker.publish(run_id, part)
        except asyncio.CancelledError:
            raise  # detach()/aclose() is tearing us down — normal teardown
        except Exception:
            # A mid-stream Redis drop (ConnectionError, …) ends THIS relay. Live
            # parts stop for the open stream — the SSE endpoint's DB-tail carries
            # the run on (ADR-F004/F025). Drop the now-dead subscription below so a
            # FUTURE viewer of this run rebuilds a fresh one instead of bumping
            # refcount on a corpse (review fix).
            logger.warning(
                "run-stream bridge pump failed; dropping subscription (DB-tail carries the run)",
                extra={"event": "agent_stream_bridge_pump_failed", "run_id": key},
            )
        finally:
            # If we exited on our own (error or clean channel end) — not via
            # detach()/aclose(), which already removed + closed us — drop the dead
            # entry and release its connection. The lock-then-release ordering in
            # detach() means the lock is free here; the identity check avoids
            # racing a concurrent detach that already swapped/removed the entry.
            dead = None
            async with self._lock:
                existing = self._subs.get(key)
                if existing is not None and existing.task is asyncio.current_task():
                    del self._subs[key]
                    dead = existing
            if dead is not None:
                with contextlib.suppress(Exception):
                    await dead.pubsub.aclose()

    async def aclose(self) -> None:
        """Tear down every subscription (api shutdown). Idempotent, best-effort."""
        async with self._lock:
            subs = list(self._subs.values())
            self._subs.clear()
        for sub in subs:
            sub.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sub.task
            with contextlib.suppress(Exception):
                await sub.pubsub.aclose()
