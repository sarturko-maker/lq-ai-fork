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
from typing import Any

logger = logging.getLogger(__name__)

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
        for opener in (
            *channel.open_reasoning.values(),
            *channel.open_tool_inputs.values(),
        ):
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
                    extra={
                        "event": "agent_stream_publish_failed",
                        "run_id": str(run_id),
                    },
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

    def __init__(self, broker: RunStreamBroker, run_id: uuid.UUID) -> None:
        self._broker = broker
        self._run_id = run_id
        self._open_reasoning: set[str] = set()
        self._started = False

    def _publish(self, part: dict[str, Any]) -> None:
        if not self._started:
            self._started = True
            self._broker.publish(
                self._run_id, {"type": "start", "messageId": str(self._run_id)}
            )
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
