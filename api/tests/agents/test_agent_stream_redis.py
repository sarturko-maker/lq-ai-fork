"""Cross-process run-stream transport — F025 (ADR-F025), pure unit (no real Redis).

A hand-rolled in-memory fake Redis (publish + pub/sub) lets the FULL round-trip
run in-process and in CI (which has no Redis): worker-side
:class:`RedisStreamBroker` → fake Redis → api-side :class:`RedisStreamBridge` →
the process-local :class:`RunStreamBroker` → a subscriber queue. The real Redis
round-trip is verified live on the dev stack.

Load-bearing properties:

* a part published by the worker broker reaches a local subscriber, in order,
  JSON-round-tripped — and the SAME :class:`RunStreamPublisher` drives it;
* ``close()`` rides the channel as a marker that closes the LOCAL channel
  (CHANNEL_CLOSED to subscribers) — after the terminal parts;
* the bridge is reference-counted (one Redis subscription per run, many viewers);
* a malformed message is dropped, never raised (animation only — ADR-F004).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections import defaultdict
from typing import Any

import pytest

from app.agents.stream import (
    CHANNEL_CLOSED,
    RedisStreamBridge,
    RedisStreamBroker,
    RunStreamBroker,
    stream_channel,
)

# pytest asyncio_mode = "auto" (pyproject) — bare `async def test_*` is collected.


# --- a minimal in-memory fake of redis.asyncio (publish + pubsub) -----------


class _FakePubSub:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._channels: list[str] = []

    async def subscribe(self, channel: str) -> None:
        self._redis._subs[channel].append(self)
        self._channels.append(channel)
        await self._queue.put({"type": "subscribe", "channel": channel, "data": 1})

    async def listen(self) -> Any:
        while True:
            yield await self._queue.get()

    async def _deliver(self, data: str) -> None:
        await self._queue.put({"type": "message", "data": data})

    async def aclose(self) -> None:
        for channel in self._channels:
            subs = self._redis._subs.get(channel, [])
            if self in subs:
                subs.remove(self)


class _FakeRedis:
    def __init__(self) -> None:
        self._subs: dict[str, list[_FakePubSub]] = defaultdict(list)

    async def publish(self, channel: str, data: str) -> int:
        targets = list(self._subs.get(channel, []))
        for ps in targets:
            await ps._deliver(data)
        return len(targets)

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub(self)


async def _drain_until(queue: asyncio.Queue[Any], count: int, timeout: float = 2.0) -> list[Any]:
    items: list[Any] = []

    async def _get() -> None:
        while len(items) < count:
            items.append(await queue.get())

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(_get(), timeout)
    return items


# --- tests ------------------------------------------------------------------


async def test_round_trip_worker_to_local_subscriber_in_order() -> None:
    run_id = uuid.uuid4()
    fake = _FakeRedis()
    local = RunStreamBroker()
    bridge = RedisStreamBridge(fake, local)
    worker = RedisStreamBroker(fake)

    # A browser is watching (local subscriber) and the bridge is relaying.
    queue = local.subscribe(run_id)
    await bridge.attach(run_id)

    # The worker runs a tiny run through the SAME publisher surface.
    pub = worker.publisher(run_id)
    pub.reasoning_delta("r1", "thinking…")
    pub.run_finished(status="completed", final_answer="done")

    # start, reasoning-start, reasoning-delta, reasoning-end, text-start,
    # text-delta, text-end, data-run, finish (9), then CHANNEL_CLOSED (10).
    parts = await _drain_until(queue, 10)
    types = [p if p is CHANNEL_CLOSED else p.get("type") for p in parts]

    assert types[0] == "start"  # lazy message-open rides the first publish
    assert "reasoning-start" in types
    assert types.index("reasoning-start") < types.index("reasoning-delta")
    assert "data-run" in types and "finish" in types
    assert CHANNEL_CLOSED in parts  # close() marker closed the LOCAL channel
    # data-run carried the settled terminal status (JSON round-tripped intact).
    data_run = next(p for p in parts if p is not CHANNEL_CLOSED and p.get("type") == "data-run")
    assert data_run["data"]["status"] == "completed"

    await bridge.detach(run_id)


async def test_ropa_change_frame_survives_the_round_trip() -> None:
    """The PRIV-9b highlight signal (ADR-F024) reaches the browser cross-process."""
    run_id = uuid.uuid4()
    fake = _FakeRedis()
    local = RunStreamBroker()
    bridge = RedisStreamBridge(fake, local)
    worker = RedisStreamBroker(fake)
    entity_id = str(uuid.uuid4())

    queue = local.subscribe(run_id)
    await bridge.attach(run_id)

    worker.publisher(run_id).ropa_changed(kind="vendor", entity_id=entity_id, verb="create")

    parts = await _drain_until(queue, 2)  # start + the change frame
    change = next(
        p for p in parts if p is not CHANNEL_CLOSED and p.get("type") == "data-ropa-change"
    )
    assert change["data"] == {"kind": "vendor", "id": entity_id, "verb": "create"}
    assert change["transient"] is True

    await bridge.detach(run_id)


async def test_bridge_is_reference_counted_one_subscription_per_run() -> None:
    run_id = uuid.uuid4()
    fake = _FakeRedis()
    bridge = RedisStreamBridge(fake, RunStreamBroker())
    channel = stream_channel(run_id)

    await bridge.attach(run_id)
    await bridge.attach(run_id)  # second viewer — no second Redis subscription
    assert len(fake._subs[channel]) == 1

    await bridge.detach(run_id)
    assert len(fake._subs[channel]) == 1  # still one viewer

    await bridge.detach(run_id)  # last viewer leaves → subscription torn down
    assert len(fake._subs[channel]) == 0


async def test_publish_never_raises_when_drain_queue_full() -> None:
    """A wedged drain drops parts (logged), never blocks/raises the run."""
    run_id = uuid.uuid4()
    worker = RedisStreamBroker(_FakeRedis())
    # Stuff the internal queue past its cap without letting the drain run.
    worker._queue = asyncio.Queue(maxsize=1)
    worker._queue.put_nowait(("x", {"type": "noise"}))
    # Does not raise even though the queue is full.
    worker.publish(run_id, {"type": "data-step", "id": "s1"})


async def test_malformed_redis_message_is_dropped_not_raised() -> None:
    run_id = uuid.uuid4()
    fake = _FakeRedis()
    local = RunStreamBroker()
    bridge = RedisStreamBridge(fake, local)

    queue = local.subscribe(run_id)
    await bridge.attach(run_id)

    channel = stream_channel(run_id)
    await fake.publish(channel, "not json {")  # malformed → dropped
    await fake.publish(channel, json.dumps(["not", "a", "dict"]))  # not a dict → dropped
    await fake.publish(channel, json.dumps({"type": "data-step", "id": "s1"}))  # good

    parts = await _drain_until(queue, 1)
    good = [p for p in parts if p is not CHANNEL_CLOSED]
    assert any(p.get("type") == "data-step" for p in good)

    await bridge.detach(run_id)


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    async def _w() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(_w(), timeout)


class _FailingSubscribePubSub:
    """pubsub whose subscribe() raises AFTER construction (the post-connect blip)."""

    def __init__(self) -> None:
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        raise ConnectionError("subscribe blip")

    async def aclose(self) -> None:
        self.closed = True


class _DroppingPubSub:
    """pubsub whose listen() raises mid-stream (a Redis connection drop)."""

    def __init__(self) -> None:
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        return None

    async def listen(self):  # type: ignore[no-untyped-def]
        raise ConnectionError("connection dropped")
        yield  # pragma: no cover - makes this an async generator

    async def aclose(self) -> None:
        self.closed = True


async def test_attach_closes_pubsub_and_records_nothing_when_subscribe_fails() -> None:
    """SF: a subscribe() blip must release the pubsub connection, not leak it."""
    ps = _FailingSubscribePubSub()

    class _R:
        def pubsub(self) -> _FailingSubscribePubSub:
            return ps

    bridge = RedisStreamBridge(_R(), RunStreamBroker())
    with pytest.raises(ConnectionError):
        await bridge.attach(uuid.uuid4())
    assert ps.closed is True  # released, not leaked
    assert bridge._subs == {}  # nothing left registered


async def test_pump_death_drops_the_subscription_so_a_later_attach_rebuilds() -> None:
    """SF: a mid-stream Redis drop must drop the dead sub (+ close it), not wedge
    _subs with a corpse a future viewer would bump refcount on."""
    ps = _DroppingPubSub()

    class _R:
        def pubsub(self) -> _DroppingPubSub:
            return ps

    bridge = RedisStreamBridge(_R(), RunStreamBroker())
    run_id = uuid.uuid4()
    await bridge.attach(run_id)
    await _wait_until(lambda: str(run_id) not in bridge._subs)
    assert str(run_id) not in bridge._subs  # dead entry dropped
    assert ps.closed is True  # connection released
