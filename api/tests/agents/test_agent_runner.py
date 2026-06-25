"""Runner tests — F0-S2: a fake tool-calling model drives the REAL deepagents loop.

No provider, no gateway: :class:`ScriptedToolCallingModel` is injected
through ``execute_agent_run``'s ``model`` seam, and a test-local tool
through ``tools`` (F0-S4 deleted the demo tool — the runner ships no
capabilities of its own) — the same seams production uses for the real
matter tools. What's real here: ``build_deep_agent``, the langgraph
loop, model-initiated tool dispatch, ``astream_events`` mapping, and
the commit-per-step persistence a poller depends on (ADR-F004
render-deterministic).

These tests COMMIT (the runner's contract is commit-per-step), so they
use a plain session factory on the migrated per-run test DB instead of
the savepoint-isolated ``db_session`` fixture; each test's user is
deleted at teardown and the cascade clears its runs and steps.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.runner import _innermost_tool_parent, _recursion_limit, execute_agent_run
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.user import User
from app.security import hash_password
from tests.agents.fakes import (
    ExplodingModel,
    ScriptedToolCallingModel,
    final_message,
    tool_call_message,
)

pytestmark = pytest.mark.integration

_CLAUSE_TEXT = (
    "Clause 7.2 (Limitation of Liability): each party's aggregate liability "
    "is capped at the fees paid in the twelve (12) months preceding the claim."
)


def read_clause(topic: str) -> str:
    """Return the verbatim text of the contract clause covering ``topic``."""
    return _CLAUSE_TEXT


@pytest_asyncio.fixture
async def commit_factory(
    test_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """A real commit-capable factory — the runner's production session shape."""
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def make_run(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[Callable[..., Awaitable[uuid.UUID]]]:
    """Create a committed user + run; cascade-delete the user at teardown."""
    user_ids: list[uuid.UUID] = []

    async def _make(
        *, max_steps: int = 20, prompt: str = "What is the liability cap?"
    ) -> uuid.UUID:
        async with commit_factory() as db:
            user = User(
                email=f"agent-runner-{uuid.uuid4().hex[:8]}@example.com",
                display_name="Agent Runner Test User",
                hashed_password=hash_password("correct-horse-battery-staple"),
                is_admin=False,
                mfa_enabled=False,
                must_change_password=False,
            )
            db.add(user)
            await db.flush()
            user_ids.append(user.id)
            thread = AgentThread(user_id=user.id, title=prompt[:120])
            db.add(thread)
            await db.flush()
            run = AgentRun(
                user_id=user.id,
                thread_id=thread.id,
                status="running",
                prompt=prompt,
                model_alias="smart",
                max_steps=max_steps,
            )
            db.add(run)
            await db.commit()
            return run.id

    yield _make

    async with commit_factory() as db:
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


async def _load_run_and_steps(
    factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID
) -> tuple[AgentRun, list[AgentRunStep]]:
    async with factory() as db:
        run = (await db.execute(select(AgentRun).where(AgentRun.id == run_id))).scalar_one()
        steps = (
            (
                await db.execute(
                    select(AgentRunStep)
                    .where(AgentRunStep.run_id == run_id)
                    .order_by(AgentRunStep.seq.asc())
                )
            )
            .scalars()
            .all()
        )
        return run, list(steps)


class _PoisonedSession:
    """Wraps a real ``AsyncSession``; ``commit`` always raises.

    Simulates a connection invalidated by wall-clock cancellation
    landing mid-commit — the failure mode ``_finalize`` must survive
    (F2: never reuse a possibly-poisoned session for the terminal write).
    """

    def __init__(self, real: AsyncSession) -> None:
        self._real = real

    async def __aenter__(self) -> _PoisonedSession:
        await self._real.__aenter__()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._real.__aexit__(*exc_info)

    async def commit(self) -> None:
        raise RuntimeError("simulated poisoned session: commit failed")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _FlakySessionFactory:
    """Session factory whose Nth call(s) hand out poisoned sessions.

    Injected through ``execute_agent_run``'s ``db_session_factory`` seam
    (no monkeypatching). Call sequence since F0-S5's per-step sessions:
    call 1 loads the run's fields, calls 2..N+1 are the N step writes
    (each step retries once on a fresh session), then ``_finalize``'s
    terminal-write sessions follow.
    """

    def __init__(self, inner: async_sessionmaker[AsyncSession], fail_on_calls: set[int]) -> None:
        self._inner = inner
        self._fail_on_calls = fail_on_calls
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        session = self._inner()
        if self.calls in self._fail_on_calls:
            return _PoisonedSession(session)
        return session


def test_recursion_limit_scales_with_max_steps_above_langgraph_default() -> None:
    # langgraph's default recursion_limit is 25; ours must scale with max_steps so
    # the intended cap (not the graph default) governs, with a floor that still
    # clears 25 for small runs (PRIV-7: skill-on runs blew 25 mid-build).
    assert _recursion_limit(60) == 240
    assert _recursion_limit(5) == 50  # floor
    assert _recursion_limit(16) == 64
    assert _recursion_limit(1) > 25  # never below the langgraph default


async def test_run_completes_with_ordered_steps(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Happy path: tool-call turn → tool dispatch → final answer.

    Steps persist in order with the correct kinds; the run lands at
    ``completed`` with the final answer and a finish timestamp.
    """
    run_id = await make_run()
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("The cap is the fees paid in the twelve months before the claim."),
        ]
    )

    await execute_agent_run(run_id, commit_factory, tools=[read_clause], model=model)

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.final_answer is not None and "twelve" in run.final_answer
    assert run.error is None
    assert run.finished_at is not None

    assert [s.seq for s in steps] == list(range(1, len(steps) + 1))
    kinds = [s.kind for s in steps]
    assert kinds == ["model_turn", "tool_call", "tool_result", "model_turn"]

    # Tool steps carry the tool name; model turns don't.
    assert steps[1].name == "read_clause"
    assert steps[2].name == "read_clause"
    assert steps[0].name is None and steps[3].name is None

    # Bounded summaries: args on the call, output digest on the result.
    assert "liability" in steps[1].summary
    assert "twelve (12) months" in steps[2].summary
    assert "read_clause" in steps[0].summary  # "[requested tools: …]"
    assert all(len(s.summary) <= 2000 for s in steps)


async def test_max_steps_cap_marks_cap_exceeded(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A model that never stops calling tools is cut off at max_steps."""
    run_id = await make_run(max_steps=4)
    model = ScriptedToolCallingModel(
        responses=[tool_call_message("read_clause", {"topic": "liability"})],
        loop_last=True,
    )

    await execute_agent_run(run_id, commit_factory, tools=[read_clause], model=model)

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "cap_exceeded"
    assert run.final_answer is None
    assert run.finished_at is not None
    assert len(steps) == 4
    assert [s.seq for s in steps] == [1, 2, 3, 4]


async def test_finishing_exactly_at_cap_is_completed_not_capped(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A final answer landing exactly on the cap is a natural completion."""
    run_id = await make_run(max_steps=4)  # mt, tc, tr, mt(final) = exactly 4
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("Twelve months of fees."),
        ]
    )

    await execute_agent_run(run_id, commit_factory, tools=[read_clause], model=model)

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.final_answer == "Twelve months of fees."
    assert len(steps) == 4


async def test_wall_clock_timeout_fails_run_and_keeps_steps(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The asyncio.timeout brake → failed/'timeout'; committed steps survive.

    The tool sleeps far longer than the brake (30s vs 2s) so the timeout
    always lands inside the tool call — the terminal status and error
    are the load-bearing assertions; how many steps committed before the
    brake is timing-dependent and only loosely asserted.
    """

    async def slow_read_clause(topic: str) -> str:
        """Return the clause covering ``topic`` (slowly)."""
        await asyncio.sleep(30.0)
        return "too late"

    run_id = await make_run()
    model = ScriptedToolCallingModel(
        responses=[tool_call_message("slow_read_clause", {"topic": "liability"})],
        loop_last=True,
    )

    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[slow_read_clause],
        model=model,
        wall_clock_seconds=2.0,
    )

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "failed"
    assert run.error == "timeout"
    assert run.finished_at is not None
    # At least the first model turn committed before the brake; committed
    # steps survive the failure.
    assert len(steps) >= 1


async def test_model_exception_fails_run_without_stack_trace(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A blown-up model call lands at failed with a bounded type+message error."""
    run_id = await make_run()

    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[read_clause],
        model=ExplodingModel(message="provider exploded"),
    )

    run, _steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "failed"
    assert run.error is not None
    assert "provider exploded" in run.error
    assert "Traceback" not in run.error
    assert len(run.error) <= 500
    assert run.finished_at is not None


async def test_finalize_survives_poisoned_session_with_fresh_retry(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """F2: the first terminal-write session failing must not strand the run.

    The 4-step run uses calls 1 (load) + 2-5 (step writes); the factory
    poisons call 6 (``_finalize``'s first fresh session); the retry
    (call 7) opens another fresh session and lands the terminal state.
    """
    run_id = await make_run()
    factory = _FlakySessionFactory(commit_factory, fail_on_calls={6})
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("Twelve months of fees."),
        ]
    )

    await execute_agent_run(run_id, factory, tools=[read_clause], model=model)

    run, _steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.final_answer == "Twelve months of fees."
    assert run.finished_at is not None
    assert factory.calls == 7  # load, 4 steps, poisoned finalize, fresh retry


async def test_finalize_double_failure_logs_and_does_not_raise(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """F2: both terminal-write sessions failing is logged, never raised.

    The run is left at ``'running'`` (the documented residual risk —
    the S3 UI applies a staleness cutoff; the recovery sweep lands with
    the arq migration).
    """
    run_id = await make_run()
    # 1-step run: call 1 loads, call 2 writes the step; calls 3 + 4 are
    # BOTH of _finalize's fresh sessions — poisoned.
    factory = _FlakySessionFactory(commit_factory, fail_on_calls={3, 4})
    model = ScriptedToolCallingModel(responses=[final_message("done")])

    with caplog.at_level(logging.ERROR, logger="app.agents.runner"):
        await execute_agent_run(run_id, factory, tools=[read_clause], model=model)

    run, _steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "running"
    assert run.finished_at is None
    assert any("terminal write failed twice" in r.message for r in caplog.records)


async def test_subagent_final_turn_is_not_the_run_final_answer(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """F4: only a TOP-LEVEL no-tool model turn is the run's final answer.

    The scripted model drives the real deepagents ``task`` tool: the
    subagent's closing turn (no tool calls) is nested under the tool run
    (``parent_ids``) and must not be read as the final answer — the
    root agent's closing turn is.
    """
    run_id = await make_run()
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "task",
                {
                    "description": "summarise the clause",
                    "subagent_type": "general-purpose",
                },
            ),
            final_message("SUBAGENT closing turn"),  # consumed by the subagent loop
            final_message("ROOT final answer"),
        ]
    )

    await execute_agent_run(run_id, commit_factory, tools=[read_clause], model=model)

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.final_answer == "ROOT final answer"
    kinds = [s.kind for s in steps]
    assert kinds == [
        "model_turn",
        "tool_call",
        "model_turn",
        "tool_result",
        "model_turn",
    ]
    assert steps[1].name == "task"
    # The nested turn IS persisted as visible activity — just not as the answer.
    assert "SUBAGENT closing turn" in steps[2].summary
    # F0-S7: the ancestry the loop always computed now PERSISTS — the
    # subagent's turn points at the task dispatch's settled row; the
    # root loop's own steps (and the task's result) stay parentless.
    assert steps[2].parent_step_id == steps[1].id
    assert steps[0].parent_step_id is None
    assert steps[1].parent_step_id is None
    assert steps[3].parent_step_id is None
    assert steps[4].parent_step_id is None


async def test_cap_during_subagent_leaves_final_answer_null(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """F4: capping right after a subagent's closing turn → no final answer.

    Pre-fix, the nested no-tool turn read as final: it bypassed the cap
    check and its text leaked into ``final_answer`` on the
    ``cap_exceeded`` path.
    """
    run_id = await make_run(max_steps=4)
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "task",
                {
                    "description": "summarise the clause",
                    "subagent_type": "general-purpose",
                },
            ),
            final_message("SUBAGENT closing turn"),
            final_message("ROOT final answer"),  # never reached — cap hits at step 4
        ]
    )

    await execute_agent_run(run_id, commit_factory, tools=[read_clause], model=model)

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "cap_exceeded"
    assert run.final_answer is None
    # model_turn, tool_call(task), nested model_turn, tool_result(task) = cap at 4.
    assert len(steps) == 4


def test_innermost_tool_parent_picks_the_nearest_enclosing_dispatch() -> None:
    """parent_ids orders root-first, so the INNERMOST enclosing tool is
    the LAST match — a deep step under nested dispatches must link to
    its nearest ancestor, not the outermost (S7 review: reversing the
    scan direction would otherwise pass the whole suite).
    """
    outer_step = uuid.uuid4()
    inner_step = uuid.uuid4()
    tool_step_ids = {"run-outer": outer_step, "run-inner": inner_step}

    nested_event = {"parent_ids": ["run-root", "run-outer", "run-mid", "run-inner"]}
    assert _innermost_tool_parent(nested_event, tool_step_ids) == inner_step

    outer_only = {"parent_ids": ["run-root", "run-outer", "run-mid"]}
    assert _innermost_tool_parent(outer_only, tool_step_ids) == outer_step

    assert _innermost_tool_parent({"parent_ids": ["run-root"]}, tool_step_ids) is None
    assert _innermost_tool_parent({}, tool_step_ids) is None


async def test_publisher_mirrors_the_real_loop_onto_the_wire(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """F0-S7: the SSE v2 publisher sees the run exactly as the rows settle.

    Drives the REAL deepagents loop (task subagent and all) with a
    broker subscription attached and asserts the wire mirrors the DB:
    data-step part ids == row ids in seq order, subagent ancestry on the
    wire, toolCallId == the settled tool_call row id, and the terminal
    text block == the persisted final answer.
    """
    from app.agents.stream import CHANNEL_CLOSED, RunStreamBroker

    run_id = await make_run()
    broker = RunStreamBroker()
    queue = broker.subscribe(run_id)
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message(
                "task",
                {
                    "description": "summarise the clause",
                    "subagent_type": "general-purpose",
                },
            ),
            final_message("SUBAGENT closing turn"),
            final_message("ROOT final answer"),
        ]
    )

    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[read_clause],
        model=model,
        publisher=broker.publisher(run_id),
    )

    parts: list[Any] = []
    while not queue.empty():
        parts.append(queue.get_nowait())
    assert parts[-1] is CHANNEL_CLOSED
    parts = parts[:-1]

    _run, steps = await _load_run_and_steps(commit_factory, run_id)

    assert parts[0]["type"] == "start"
    step_parts = [p for p in parts if p["type"] == "data-step"]
    assert [p["data"]["seq"] for p in step_parts] == [s.seq for s in steps]
    assert [p["id"] for p in step_parts] == [str(s.id) for s in steps]
    # Subagent ancestry on the wire == in the rows.
    nested = next(p for p in step_parts if p["data"]["seq"] == steps[2].seq)
    assert nested["data"]["parent_step_id"] == str(steps[1].id)

    tool_inputs = [p for p in parts if p["type"] == "tool-input-available"]
    tool_outputs = [p for p in parts if p["type"] == "tool-output-available"]
    assert [p["toolCallId"] for p in tool_inputs] == [str(steps[1].id)]
    assert [p["toolCallId"] for p in tool_outputs] == [str(steps[1].id)]
    assert tool_inputs[0]["toolName"] == "task"

    # The thinking ribbon's feed: model output rides as reasoning blocks
    # (start before delta before end, correlated by id), including the
    # NESTED subagent turn — and top-level turn boundaries frame as
    # start-step/finish-step (S7 review: this branch had no CI coverage).
    reasoning_deltas = [p for p in parts if p["type"] == "reasoning-delta"]
    blocks: dict[str, str] = {}
    for p in reasoning_deltas:
        blocks[p["id"]] = blocks.get(p["id"], "") + p["delta"]
    joined = list(blocks.values())
    assert any("SUBAGENT closing turn" in text for text in joined)
    assert any("ROOT final answer" in text for text in joined)
    for delta in reasoning_deltas:
        block_id = delta["id"]
        started = parts.index(
            next(p for p in parts if p["type"] == "reasoning-start" and p["id"] == block_id)
        )
        assert started < parts.index(delta)
    assert {p["id"] for p in parts if p["type"] == "reasoning-end"} >= {
        p["id"] for p in reasoning_deltas
    }
    # Three model turns total, ONE nested: exactly two top-level frames.
    assert sum(1 for p in parts if p["type"] == "start-step") == 2
    assert sum(1 for p in parts if p["type"] == "finish-step") == 2

    types = [p["type"] for p in parts]
    assert types[-4:] == ["text-delta", "text-end", "data-run", "finish"]
    text_delta = next(p for p in parts if p["type"] == "text-delta")
    assert text_delta["delta"] == "ROOT final answer"
    data_run = next(p for p in parts if p["type"] == "data-run")
    assert data_run["data"]["status"] == "completed"


async def test_run_drains_the_change_ledger_onto_the_stream_at_tool_result(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """PRIV-9b (ADR-F024): the runner glue — at each tool_result step the loop
    drains the run-scoped change ledger and publishes each entry as a
    data-ropa-change part. (The ledger, the publisher frame, the tool-body
    recording, and the cross-process transport are each tested in isolation;
    this is the seam that wires them together.)"""
    from app.agents.ropa_changes import RopaChangeLedger
    from app.agents.stream import RunStreamBroker

    run_id = await make_run()
    broker = RunStreamBroker()
    queue = broker.subscribe(run_id)
    # A ROPA tool body would record this after its flush; pre-seed it so the test
    # exercises ONLY the runner's drain-at-tool_result glue, not a real tool.
    ledger = RopaChangeLedger()
    ledger.record("system", "11111111-1111-4111-8111-111111111111", "create")

    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("done"),
        ]
    )
    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[read_clause],
        model=model,
        publisher=broker.publisher(run_id),
        change_ledger=ledger,
    )

    parts: list[Any] = []
    while not queue.empty():
        parts.append(queue.get_nowait())
    changes = [p for p in parts if isinstance(p, dict) and p.get("type") == "data-ropa-change"]
    assert len(changes) == 1
    assert changes[0]["data"] == {
        "kind": "system",
        "id": "11111111-1111-4111-8111-111111111111",
        "verb": "create",
    }
    assert changes[0]["transient"] is True
    # Drained exactly once — a second (answer) turn carries no further change.
    assert ledger.drain() == []


async def test_run_drains_a_deal_change_ledger_onto_the_stream_at_tool_result(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """C5b-3 (ADR-F032): the SAME runner drain seam is area-agnostic — a
    DealChangeLedger drains to data-deal-change parts via the LiveChange.publish
    contract (no runner change between areas). respond_to_counterparty would record
    these after its reconcile; pre-seed so the test exercises ONLY the drain glue."""
    from app.agents.deal_changes import DealChangeLedger
    from app.agents.stream import RunStreamBroker

    run_id = await make_run()
    broker = RunStreamBroker()
    queue = broker.subscribe(run_id)
    ledger = DealChangeLedger()
    ledger.record("C1", "accept")
    ledger.record("Com:1", "escalate")

    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("done"),
        ]
    )
    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[read_clause],
        model=model,
        publisher=broker.publisher(run_id),
        change_ledger=ledger,
    )

    parts: list[Any] = []
    while not queue.empty():
        parts.append(queue.get_nowait())
    changes = [p for p in parts if isinstance(p, dict) and p.get("type") == "data-deal-change"]
    assert [c["data"] for c in changes] == [
        {"ref": "C1", "verdict": "accept"},
        {"ref": "Com:1", "verdict": "escalate"},
    ]
    assert all(c["transient"] is True for c in changes)
    assert ledger.drain() == []  # drained exactly once


async def test_step_write_survives_a_transient_db_failure(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A dying connection under ONE step write must not fail the run:
    the write retries on a fresh session (F0-S5 — seen live when a
    Postgres crash-recovery window hit an in-flight step INSERT)."""
    run_id = await make_run()
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("The cap is the fees paid in the twelve months before the claim."),
        ]
    )
    # Call 1 = the run-fields load; call 2 = the FIRST step write's first
    # attempt - poisoned. The retry (call 3) and everything after is real.
    flaky = _FlakySessionFactory(commit_factory, fail_on_calls={2})

    await execute_agent_run(run_id, flaky, tools=[read_clause], model=model)  # type: ignore[arg-type]

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.error is None
    # Nothing lost and nothing doubled: the full ordered timeline exists.
    assert [s.kind for s in steps] == ["model_turn", "tool_call", "tool_result", "model_turn"]
    assert [s.seq for s in steps] == [1, 2, 3, 4]
