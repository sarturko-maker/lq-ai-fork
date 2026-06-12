"""SSE v2 stream tests — F0-S7 (ADR-F006 wire spec).

Three layers, mirroring the seams:

* unit: :class:`RunStreamBroker` / :class:`RunStreamPublisher` part
  shapes and lifecycle — no DB, no app.
* endpoint replay: a COMMITTED terminal run streams its settled rows +
  terminal parts + ``[DONE]`` (httpx's ASGITransport buffers bodies, so
  every test stream must terminate — they all do by design: the
  endpoint ends terminal runs itself).
* endpoint live + DB-tail: a running run served from broker parts, and
  from settled rows alone when no live publisher exists (the F1
  arq-migration posture).

Commit-style DB usage (the runner's contract is commit-per-step), same
pattern as ``test_agent_runner.py``: a real session factory on the
migrated test DB; each test's user is deleted at teardown and the
cascade clears threads/runs/steps.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.stream import (
    CHANNEL_CLOSED,
    UI_MESSAGE_STREAM_HEADERS,
    RunStreamBroker,
    encode_sse,
    step_payload,
    terminal_parts,
)
from app.main import app
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.user import User
from app.security import create_access_token, hash_password

# ---------------------------------------------------------------------------
# Unit: broker + publisher
# ---------------------------------------------------------------------------


def _drain(queue: asyncio.Queue[Any]) -> list[Any]:
    items: list[Any] = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


async def test_broker_fanout_and_close() -> None:
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    q1 = broker.subscribe(run_id)
    q2 = broker.subscribe(run_id)

    broker.publish(run_id, {"type": "start-step"})
    broker.close(run_id)

    for q in (q1, q2):
        parts = _drain(q)
        assert parts[0] == {"type": "start-step"}
        assert parts[-1] is CHANNEL_CLOSED

    # Subscribing after close: the sentinel is pre-queued.
    q3 = broker.subscribe(run_id)
    assert _drain(q3) == [CHANNEL_CLOSED]

    # Publishing after close is a silent no-op (publisher idempotency).
    broker.publish(run_id, {"type": "finish-step"})
    assert q3.empty()


async def test_broker_drops_wedged_subscriber_without_raising() -> None:
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    queue = broker.subscribe(run_id)
    healthy = broker.subscribe(run_id)

    # Wedge the first queue, then overflow it.
    for i in range(queue.maxsize):
        queue.put_nowait({"type": "reasoning-delta", "id": "r", "delta": str(i)})
    broker.publish(run_id, {"type": "start-step"})  # overflows q → dropped

    # The healthy subscriber still receives; the wedged one was closed —
    # and its close SENTINEL actually arrives (one buffered part is
    # sacrificed to make room; a sentinel that never lands would leave
    # the consumer waiting on a dead queue — S7 review).
    assert _drain(healthy) == [{"type": "start-step"}]
    assert _drain(queue)[-1] is CHANNEL_CLOSED
    broker.publish(run_id, {"type": "finish-step"})
    assert _drain(healthy) == [{"type": "finish-step"}]


async def test_broker_releases_channel_when_last_subscriber_leaves() -> None:
    """Replay-only streams (terminal runs, DB-tail) must not leak channels.

    No publisher ever closes those channels; the unsubscribe of the last
    subscriber is the only lifecycle event they get (S7 review — the
    leak was one retained channel per streamed run, forever).
    """
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    for _ in range(5):
        queue = broker.subscribe(run_id)
        broker.unsubscribe(run_id, queue)
    assert broker._channels == {}


async def test_broker_caps_subscribers_per_run() -> None:
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    queues = [broker.subscribe(run_id) for _ in range(8)]
    overflow = broker.subscribe(run_id)
    # The 9th gets an immediate close (its client falls back to polling).
    assert _drain(overflow) == [CHANNEL_CLOSED]
    broker.publish(run_id, {"type": "start-step"})
    assert all(_drain(q) == [{"type": "start-step"}] for q in queues)


async def test_mid_run_subscriber_is_seeded_with_open_block_openers() -> None:
    """Wire-spec conformance for mid-run attach (S7 review).

    A conformant AI SDK consumer crashes on a reasoning-delta whose
    reasoning-start it never saw, and on a tool-output for a toolCallId
    never introduced — the broker seeds new subscribers with the openers
    of every block still in flight.
    """
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    publisher = broker.publisher(run_id)
    early = broker.subscribe(run_id)

    publisher.reasoning_delta("r1", "thinking…")  # opens block r1
    call_payload = step_payload(
        step_id=uuid.uuid4(),
        run_id=run_id,
        seq=1,
        kind="tool_call",
        name="search_documents",
        summary='{"query": "cap"}',
        parent_step_id=None,
        created_at=datetime.now(UTC),
    )
    publisher.step_settled(call_payload)  # tool input published, output pending

    late = broker.subscribe(run_id)
    seeded = _drain(late)
    assert [p["type"] for p in seeded] == ["reasoning-start", "tool-input-available"]
    assert seeded[0]["id"] == "r1"
    assert seeded[1]["toolCallId"] == call_payload["id"]

    # Both blocks close → a third subscriber gets no stale openers.
    publisher.reasoning_end("r1")
    result_payload = step_payload(
        step_id=uuid.uuid4(),
        run_id=run_id,
        seq=2,
        kind="tool_result",
        name="search_documents",
        summary="hit",
        parent_step_id=None,
        created_at=datetime.now(UTC),
    )
    publisher.step_settled(result_payload, tool_call_id=call_payload["id"])
    latest = broker.subscribe(run_id)
    assert _drain(latest) == []
    assert _drain(early)  # the early subscriber saw the full sequence


async def test_publisher_reasoning_blocks_open_lazily_and_close_once() -> None:
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    queue = broker.subscribe(run_id)
    publisher = broker.publisher(run_id)

    publisher.reasoning_delta("r1", "thinking…")
    publisher.reasoning_delta("r1", " more")
    publisher.reasoning_end("r1")
    publisher.reasoning_end("r1")  # double-close is a no-op

    types = [(p["type"], p.get("id")) for p in _drain(queue)]
    assert types == [
        ("start", None),  # lazy message open rides the first publish
        ("reasoning-start", "r1"),
        ("reasoning-delta", "r1"),
        ("reasoning-delta", "r1"),
        ("reasoning-end", "r1"),
    ]


async def test_publisher_step_settled_tool_parts_and_plan() -> None:
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    queue = broker.subscribe(run_id)
    publisher = broker.publisher(run_id)

    call_payload = step_payload(
        step_id=uuid.uuid4(),
        run_id=run_id,
        seq=1,
        kind="tool_call",
        name="write_todos",
        summary=json.dumps({"todos": [{"content": "review clause", "status": "pending"}]}),
        parent_step_id=None,
        created_at=datetime.now(UTC),
    )
    publisher.step_settled(call_payload)
    result_payload = step_payload(
        step_id=uuid.uuid4(),
        run_id=run_id,
        seq=2,
        kind="tool_result",
        name="write_todos",
        summary="ok",
        parent_step_id=None,
        created_at=datetime.now(UTC),
    )
    publisher.step_settled(result_payload, tool_call_id=call_payload["id"])

    parts = [p for p in _drain(queue) if p["type"] != "start"]
    by_type = {p["type"]: p for p in parts}

    # tool_call → tool-input-available keyed by the SETTLED row id.
    assert by_type["tool-input-available"]["toolCallId"] == call_payload["id"]
    assert by_type["tool-input-available"]["toolName"] == "write_todos"
    assert by_type["tool-input-available"]["input"]["todos"][0]["content"] == "review clause"
    # write_todos additionally rides as a plan frame (rail label "Plan").
    assert by_type["data-plan"]["id"] == call_payload["id"]
    assert by_type["data-plan"]["data"]["todos"][0]["status"] == "pending"
    # tool_result correlates through the tool_call's row id.
    assert by_type["tool-output-available"]["toolCallId"] == call_payload["id"]
    assert by_type["tool-output-available"]["output"] == {"summary": "ok"}
    # Both rows mirrored as data-step parts, id = row id.
    step_parts = [p for p in parts if p["type"] == "data-step"]
    assert [p["id"] for p in step_parts] == [call_payload["id"], result_payload["id"]]
    assert step_parts[0]["data"]["parent_step_id"] is None


async def test_publisher_truncated_tool_args_ride_as_raw() -> None:
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    queue = broker.subscribe(run_id)
    publisher = broker.publisher(run_id)

    truncated = '{"query": "liability ca…'  # bounded digest cut mid-token
    publisher.step_settled(
        step_payload(
            step_id=uuid.uuid4(),
            run_id=run_id,
            seq=1,
            kind="tool_call",
            name="search_documents",
            summary=truncated,
            parent_step_id=None,
            created_at=datetime.now(UTC),
        )
    )
    parts = _drain(queue)
    tool_input = next(p for p in parts if p["type"] == "tool-input-available")
    assert tool_input["input"] == {"raw": truncated}


async def test_publisher_run_finished_terminal_sequence_and_idempotency() -> None:
    broker = RunStreamBroker()
    run_id = uuid.uuid4()
    queue = broker.subscribe(run_id)
    publisher = broker.publisher(run_id)

    publisher.reasoning_delta("r1", "thinking")
    publisher.run_finished(status="completed", final_answer="The cap is 12 months of fees.")
    publisher.run_finished(status="failed", error="late duplicate")  # closed channel → no-op

    parts = _drain(queue)
    assert parts[-1] is CHANNEL_CLOSED
    types = [p["type"] for p in parts[:-1]]
    # Open reasoning blocks are closed before the terminal parts.
    assert types == [
        "start",
        "reasoning-start",
        "reasoning-delta",
        "reasoning-end",
        "text-start",
        "text-delta",
        "text-end",
        "data-run",
        "finish",
    ]
    text_delta = next(p for p in parts if p["type"] == "text-delta")
    assert text_delta["delta"] == "The cap is 12 months of fees."
    assert text_delta["id"] == f"answer-{run_id}"
    data_run = next(p for p in parts if p["type"] == "data-run")
    assert data_run["id"] == str(run_id)
    assert data_run["data"] == {"status": "completed", "error": None}
    # Nothing about the late duplicate leaked past the close.
    assert "error" not in types


def test_terminal_parts_failed_run_carries_error_no_text() -> None:
    parts = terminal_parts(run_id=uuid.uuid4(), status="failed", final_answer=None, error="timeout")
    types = [p["type"] for p in parts]
    assert types == ["error", "data-run", "finish"]
    assert parts[0]["errorText"] == "timeout"


def test_encode_sse_is_one_compact_data_line() -> None:
    frame = encode_sse({"type": "finish"})
    assert frame == 'data: {"type":"finish"}\n\n'


# ---------------------------------------------------------------------------
# Endpoint: replay / live / DB-tail (committed rows, real session factory)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def stream_user(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[User]:
    async with commit_factory() as db:
        user = User(
            email=f"agent-stream-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Agent Stream Test User",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(user)
        await db.commit()
    yield user
    async with commit_factory() as db:
        await db.execute(delete(User).where(User.id == user.id))
        await db.commit()


@pytest_asyncio.fixture
async def stream_client(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """Client whose DB seams all target the migrated per-run test DB.

    The stream generator reads through its own short-lived sessions, so
    the fixtures must COMMIT — the savepoint-isolated ``db_session``
    would hide every row from it. Both seams are overridden the house
    way: ``get_db`` (handler-side auth/ownership reads) and
    ``get_stream_session_factory`` (the generator's reads).
    """
    from app.api.agent_runs import get_stream_session_factory
    from app.db.session import get_db

    async def _override() -> AsyncIterator[AsyncSession]:
        async with commit_factory() as db:
            yield db

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_stream_session_factory] = lambda: commit_factory
    app.state.agent_stream_broker = RunStreamBroker()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_stream_session_factory, None)


def _auth(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email, is_admin=user.is_admin)
    return {"Authorization": f"Bearer {token}"}


async def _make_thread_run(
    commit_factory: async_sessionmaker[AsyncSession],
    user: User,
    *,
    status: str,
    final_answer: str | None = None,
    error: str | None = None,
) -> AgentRun:
    async with commit_factory() as db:
        thread = AgentThread(user_id=user.id, title="stream test")
        db.add(thread)
        await db.flush()
        run = AgentRun(
            user_id=user.id,
            thread_id=thread.id,
            status=status,
            prompt="What is the liability cap?",
            model_alias="smart",
            max_steps=20,
            final_answer=final_answer,
            error=error,
            finished_at=datetime.now(UTC) if status != "running" else None,
        )
        db.add(run)
        await db.commit()
        return run


async def _add_step(
    commit_factory: async_sessionmaker[AsyncSession],
    run: AgentRun,
    *,
    seq: int,
    kind: str,
    name: str | None = None,
    summary: str = "step",
    parent_step_id: uuid.UUID | None = None,
) -> AgentRunStep:
    async with commit_factory() as db:
        step = AgentRunStep(
            run_id=run.id,
            seq=seq,
            kind=kind,
            name=name,
            summary=summary,
            parent_step_id=parent_step_id,
        )
        db.add(step)
        await db.commit()
        return step


def _parse_sse(body: str) -> list[Any]:
    """Frames in order; the ``[DONE]`` marker rides as the string."""
    frames: list[Any] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue  # comments (heartbeats) and blanks
        payload = line[len("data: ") :]
        frames.append("[DONE]" if payload == "[DONE]" else json.loads(payload))
    return frames


@pytest.mark.integration
async def test_stream_replays_terminal_run_and_closes(
    stream_client: AsyncClient,
    stream_user: User,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    run = await _make_thread_run(
        commit_factory,
        stream_user,
        status="completed",
        final_answer="The cap is twelve months of fees.",
    )
    call = await _add_step(
        commit_factory, run, seq=1, kind="tool_call", name="task", summary='{"description":"x"}'
    )
    await _add_step(
        commit_factory,
        run,
        seq=2,
        kind="model_turn",
        summary="SUBAGENT turn",
        parent_step_id=call.id,
    )

    response = await stream_client.get(
        f"/api/v1/agents/runs/{run.id}/stream", headers=_auth(stream_user)
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    for header, value in UI_MESSAGE_STREAM_HEADERS.items():
        assert response.headers.get(header) == value

    frames = _parse_sse(response.text)
    assert frames[0] == {"type": "start", "messageId": str(run.id)}
    step_frames = [f for f in frames if isinstance(f, dict) and f["type"] == "data-step"]
    assert [f["data"]["seq"] for f in step_frames] == [1, 2]
    # Subagent ancestry survives the wire (the S7 MUST).
    assert step_frames[1]["data"]["parent_step_id"] == str(call.id)
    text_delta = next(f for f in frames if isinstance(f, dict) and f["type"] == "text-delta")
    assert text_delta["delta"] == "The cap is twelve months of fees."
    data_run = next(f for f in frames if isinstance(f, dict) and f["type"] == "data-run")
    assert data_run["data"]["status"] == "completed"
    assert frames[-2] == {"type": "finish"}
    assert frames[-1] == "[DONE]"


@pytest.mark.integration
async def test_stream_404_for_missing_and_cross_user_run(
    stream_client: AsyncClient,
    stream_user: User,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    missing = await stream_client.get(
        f"/api/v1/agents/runs/{uuid.uuid4()}/stream", headers=_auth(stream_user)
    )
    assert missing.status_code == 404

    async with commit_factory() as db:
        other = User(
            email=f"agent-stream-other-{uuid.uuid4().hex[:8]}@example.com",
            display_name="Other",
            hashed_password=hash_password("correct-horse-battery-staple"),
            is_admin=False,
            mfa_enabled=False,
            must_change_password=False,
        )
        db.add(other)
        await db.commit()
    try:
        run = await _make_thread_run(commit_factory, other, status="completed", final_answer="x")
        cross = await stream_client.get(
            f"/api/v1/agents/runs/{run.id}/stream", headers=_auth(stream_user)
        )
        assert cross.status_code == 404  # never 403 — no existence disclosure
    finally:
        async with commit_factory() as db:
            await db.execute(delete(User).where(User.id == other.id))
            await db.commit()


@pytest.mark.integration
async def test_stream_serves_live_broker_parts(
    stream_client: AsyncClient,
    stream_user: User,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Parts published while the stream is open arrive on the wire."""
    run = await _make_thread_run(commit_factory, stream_user, status="running")
    broker: RunStreamBroker = app.state.agent_stream_broker

    request = asyncio.create_task(
        stream_client.get(f"/api/v1/agents/runs/{run.id}/stream", headers=_auth(stream_user))
    )
    # Wait for the generator's subscription (deterministic, not sleep-tuned).
    for _ in range(500):
        channel = broker._channels.get(run.id)
        if channel is not None and channel.subscribers:
            break
        await asyncio.sleep(0.01)
    else:
        request.cancel()
        pytest.fail("stream endpoint never subscribed to the broker")

    publisher = broker.publisher(run.id)
    publisher.reasoning_delta("r1", "thinking about the cap")
    publisher.run_finished(status="completed", final_answer="Twelve months of fees.")

    response = await request
    frames = _parse_sse(response.text)
    types = [f["type"] for f in frames if isinstance(f, dict)]
    assert "reasoning-delta" in types
    assert types[-2:] == ["data-run", "finish"]
    assert frames[-1] == "[DONE]"


@pytest.mark.integration
async def test_stream_ends_for_run_orphaned_at_running(
    stream_client: AsyncClient,
    stream_user: User,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A run stuck at 'running' past every recovery path must not hold
    the stream open forever (S7 review). Since F1-S1 the cutoff is the
    dead-sweep BELT mirroring the sweep's rules with slack: an UNCLAIMED
    run trips it only past claim_grace (1200s) + slack — backdate far
    beyond that (the sweep itself would settle a real one long before).
    """
    from datetime import timedelta

    run = await _make_thread_run(commit_factory, stream_user, status="running")
    async with commit_factory() as db:
        row = await db.get(AgentRun, run.id)
        assert row is not None
        row.started_at = datetime.now(UTC) - timedelta(seconds=3600)
        await db.commit()

    response = await stream_client.get(
        f"/api/v1/agents/runs/{run.id}/stream", headers=_auth(stream_user)
    )
    frames = _parse_sse(response.text)
    types = [f["type"] for f in frames if isinstance(f, dict)]
    assert "error" in types
    assert types[-1] == "finish"
    assert frames[-1] == "[DONE]"


@pytest.mark.integration
async def test_composition_failure_closes_the_stream(
    stream_user: User,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A failure BEFORE the runner takes over must still end the wire:
    compose_and_execute_run's failure path publishes the failed terminal
    parts through the same publisher the runner would have used.
    """
    from app.agents.composition import compose_and_execute_run

    run = await _make_thread_run(commit_factory, stream_user, status="running")
    broker = RunStreamBroker()
    queue = broker.subscribe(run.id)

    def _exploding_builder(**_kwargs: Any) -> Any:
        raise RuntimeError("model build exploded")

    await compose_and_execute_run(
        run_id=run.id,
        broker=broker,
        model_builder=_exploding_builder,
        session_factory_provider=lambda: commit_factory,
        checkpointer_provider=lambda: None,
    )

    parts = _drain(queue)
    assert parts[-1] is CHANNEL_CLOSED
    types = [p["type"] for p in parts[:-1]]
    assert types[-1] == "finish"
    assert "error" in types
    error_part = next(p for p in parts if isinstance(p, dict) and p["type"] == "error")
    assert "RuntimeError" in error_part["errorText"]
    assert "Traceback" not in error_part["errorText"]

    async with commit_factory() as db:
        row = await db.get(AgentRun, run.id)
        assert row is not None and row.status == "failed"


@pytest.mark.integration
async def test_stream_db_tail_serves_run_without_live_publisher(
    stream_client: AsyncClient,
    stream_user: User,
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No broker traffic at all — settled rows alone complete the stream.

    This is the F1 arq-migration posture (executor in another process)
    and the api-restart recovery path: the DB-tail emits new rows and
    the terminal parts from the settled run state.
    """
    run = await _make_thread_run(commit_factory, stream_user, status="running")
    broker: RunStreamBroker = app.state.agent_stream_broker

    request = asyncio.create_task(
        stream_client.get(f"/api/v1/agents/runs/{run.id}/stream", headers=_auth(stream_user))
    )
    for _ in range(500):
        channel = broker._channels.get(run.id)
        if channel is not None and channel.subscribers:
            break
        await asyncio.sleep(0.01)
    else:
        request.cancel()
        pytest.fail("stream endpoint never subscribed to the broker")

    # Settle a step and the run from "another process" (plain DB writes).
    await _add_step(commit_factory, run, seq=1, kind="model_turn", summary="worked")
    async with commit_factory() as db:
        row = await db.get(AgentRun, run.id)
        assert row is not None
        row.status = "completed"
        row.final_answer = "Tail-served answer."
        row.finished_at = datetime.now(UTC)
        await db.commit()

    response = await request
    frames = _parse_sse(response.text)
    step_frames = [f for f in frames if isinstance(f, dict) and f["type"] == "data-step"]
    assert [f["data"]["seq"] for f in step_frames] == [1]
    text_delta = next(f for f in frames if isinstance(f, dict) and f["type"] == "text-delta")
    assert text_delta["delta"] == "Tail-served answer."
    assert frames[-1] == "[DONE]"


def test_run_is_orphaned_mirrors_the_sweep_rules() -> None:
    """F1-S1 review fix: the stream belt reads the lease columns — a
    queue-delayed UNCLAIMED run and a heartbeating CLAIMED run are NOT
    orphans regardless of wall age; staleness past the sweep threshold
    + slack is."""
    from datetime import timedelta

    from app.api.agent_runs import _run_is_orphaned

    now = datetime.now(UTC)

    def run_row(**kwargs: object) -> AgentRun:
        defaults: dict[str, object] = {
            "status": "running",
            "started_at": now,
            "claimed_at": None,
            "heartbeat_at": None,
        }
        defaults.update(kwargs)
        return AgentRun(**defaults)  # type: ignore[arg-type]

    # Claimed + fresh heartbeat: alive, even if started long ago.
    alive = run_row(
        started_at=now - timedelta(hours=2), claimed_at=now - timedelta(hours=2), heartbeat_at=now
    )
    assert _run_is_orphaned(alive, now) is False
    # Claimed + heartbeat stale past orphan_after + slack: belt fires.
    dead = run_row(claimed_at=now - timedelta(hours=1), heartbeat_at=now - timedelta(hours=1))
    assert _run_is_orphaned(dead, now) is True
    # Unclaimed + young: queue wait is NOT an orphan.
    queued = run_row(started_at=now - timedelta(seconds=400))
    assert _run_is_orphaned(queued, now) is False
    # Unclaimed + past claim_grace + slack: belt fires.
    lost = run_row(started_at=now - timedelta(seconds=3600))
    assert _run_is_orphaned(lost, now) is True
    # Settled rows are never orphans.
    settled = run_row(status="completed", started_at=now - timedelta(hours=5))
    assert _run_is_orphaned(settled, now) is False
