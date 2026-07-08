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
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage
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


# --- F2 Slice F (ADR-F051): the per-run token-budget brake (R4 realised) -------------


async def test_token_budget_halts_run_before_max_steps(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A run whose cumulative model tokens cross run_token_budget is halted as
    cap_exceeded with a DISTINCT error — before the (much higher) step cap, and
    even though the model would loop forever."""
    run_id = await make_run(max_steps=50)
    model = ScriptedToolCallingModel(
        responses=[tool_call_message("read_clause", {"topic": "liability"})],
        loop_last=True,
        usage_per_turn=100,  # each model turn reports 100 tokens
    )

    # Budget 250 → trips on the 3rd model turn (cumulative 300), well before max_steps=50.
    await execute_agent_run(
        run_id, commit_factory, tools=[read_clause], model=model, token_budget=250
    )

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "cap_exceeded"
    assert run.error == "token_budget_exceeded"  # told apart from the step cap (error NULL)
    assert run.final_answer is None
    assert run.finished_at is not None
    assert len(steps) < 50  # halted early on the token budget, not the step cap
    # Slice G: the cumulative total that tripped the budget is persisted (3 turns x 100).
    assert run.total_tokens == 300


async def test_token_budget_zero_disables_the_brake(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """token_budget <= 0 disables the brake: a normal run completes even though it
    reported usage well above any small ceiling."""
    run_id = await make_run()
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("The cap is the fees paid in the twelve months before the claim."),
        ],
        usage_per_turn=10_000,
    )

    await execute_agent_run(
        run_id, commit_factory, tools=[read_clause], model=model, token_budget=0
    )

    run, _ = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.error is None
    assert run.final_answer is not None and "twelve" in run.final_answer
    # Slice G: token usage is persisted even when the budget brake is disabled.
    assert run.total_tokens == 20_000


async def test_run_under_token_budget_completes_normally(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Usage accumulation does not disturb a normal run that stays under budget."""
    run_id = await make_run()
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("The cap is the fees paid in the twelve months before the claim."),
        ],
        usage_per_turn=100,
    )

    await execute_agent_run(
        run_id, commit_factory, tools=[read_clause], model=model, token_budget=1_000_000
    )

    run, _ = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.error is None
    assert run.final_answer is not None and "twelve" in run.final_answer
    # Slice G: a completed run persists its summed model tokens (2 turns x 100).
    assert run.total_tokens == 200
    # Slice O-2: the same terminal write prices the run from total_tokens (no
    # agent_loop routing rows seeded → the fallback rate applies, but the seam
    # populated a positive cost_usd — the exact-rate math lives in test_agent_cost).
    assert run.cost_usd is not None and run.cost_usd > Decimal("0")


async def test_token_budget_never_halts_mid_final_answer(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The brake mirrors max_steps: a turn that PRODUCES the final answer is never
    cut off, even if it pushes cumulative tokens over the budget."""
    run_id = await make_run()
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("The cap is the fees paid in the twelve months before the claim."),
        ],
        usage_per_turn=100,
    )

    # 150 → after the tool turn (100) we are under; the final turn (→200) crosses it but
    # is_final, so the run completes with its deliverable rather than being capped.
    await execute_agent_run(
        run_id, commit_factory, tools=[read_clause], model=model, token_budget=150
    )

    run, _ = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.error is None
    assert run.final_answer is not None and "twelve" in run.final_answer


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
    # Slice O-2: the timeout path settles with no token total, so the run is
    # left unpriced — cost_usd stays NULL (only the normal/cap path prices).
    assert run.cost_usd is None
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


# ---------------------------------------------------------------------------
# HITL-1 pause (ADR-F071)
# ---------------------------------------------------------------------------


def _gated_and_plain_turn() -> AIMessage:
    """One assistant turn requesting a GATED and an UNGATED tool together —
    the probe-A shape: the pause must land BEFORE either executes."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "send_notice",
                "args": {"recipient": "counterparty"},
                "id": "call_gated",
                "type": "tool_call",
            },
            {
                "name": "read_clause",
                "args": {"topic": "liability"},
                "id": "call_plain",
                "type": "tool_call",
            },
        ],
    )


async def _thread_id_of(factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID) -> uuid.UUID:
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        return run.thread_id


async def test_gated_tool_pauses_run_before_any_execution(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """T2 (ADR-F071): an armed run pauses at the stop-and-ask — NOTHING
    executes (not even the auto-approved sibling), the run settles
    ``awaiting_input`` with a NULL answer, and exactly one ``hitl_request``
    step row records the gated call's name+args as bounded JSON."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.hitl import compile_hitl_policy

    calls = {"send_notice": 0, "read_clause": 0}

    def send_notice(recipient: str) -> str:
        """Send a notice document to a recipient."""
        calls["send_notice"] += 1
        return "sent"

    def counting_read_clause(topic: str) -> str:
        """Return the verbatim text of the contract clause covering ``topic``."""
        calls["read_clause"] += 1
        return _CLAUSE_TEXT

    counting_read_clause.__name__ = "read_clause"

    run_id = await make_run()
    thread_id = await _thread_id_of(commit_factory, run_id)
    model = ScriptedToolCallingModel(
        responses=[_gated_and_plain_turn(), final_message("never reached")]
    )
    interrupt_on = compile_hitl_policy(
        {"send_notice": True}, frozenset({"send_notice", "read_clause"})
    )
    assert interrupt_on is not None

    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[send_notice, counting_read_clause],
        model=model,
        checkpointer=InMemorySaver(),
        thread_id=thread_id,
        interrupt_on=interrupt_on,
    )

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "awaiting_input"
    assert run.final_answer is None
    assert run.error is None
    assert run.finished_at is not None  # "stopped executing", not "delivered"
    # The honest pre-ask state: zero side effects, including the ungated sibling.
    assert calls == {"send_notice": 0, "read_clause": 0}

    assert [s.kind for s in steps] == ["model_turn", "hitl_request"]
    assert [s.seq for s in steps] == [1, 2]
    ask = steps[1]
    assert ask.name == "send_notice"
    assert ask.parent_step_id is None
    # Display-only digest of the pending call — only the GATED tool rides the
    # HITLRequest (the sibling is auto-approved, just not yet executed).
    assert json.loads(ask.summary) == [
        {"args": {"recipient": "counterparty"}, "tool": "send_notice"}
    ]


async def test_pause_wire_tail_carries_awaiting_input(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """T3 (ADR-F071): the paused run's SSE tail — the settled ``hitl_request``
    step mirrors as a generic data-step and the terminal ``data-run`` frame
    carries ``awaiting_input`` verbatim (zero stream.py changes)."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.hitl import compile_hitl_policy
    from app.agents.stream import CHANNEL_CLOSED, RunStreamBroker

    def send_notice(recipient: str) -> str:
        """Send a notice document to a recipient."""
        raise AssertionError("gated tool must never execute on a paused run")

    run_id = await make_run()
    thread_id = await _thread_id_of(commit_factory, run_id)
    broker = RunStreamBroker()
    queue = broker.subscribe(run_id)
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("send_notice", {"recipient": "counterparty"}),
            final_message("never reached"),
        ]
    )

    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[send_notice],
        model=model,
        checkpointer=InMemorySaver(),
        thread_id=thread_id,
        publisher=broker.publisher(run_id),
        interrupt_on=compile_hitl_policy({"send_notice": True}, frozenset({"send_notice"})),
    )

    parts: list[Any] = []
    while not queue.empty():
        parts.append(queue.get_nowait())
    assert parts[-1] is CHANNEL_CLOSED
    parts = parts[:-1]

    types = [p["type"] for p in parts]
    assert types[-2:] == ["data-run", "finish"]
    data_run = next(p for p in parts if p["type"] == "data-run")
    assert data_run["data"] == {"status": "awaiting_input", "error": None}
    # No deliverable → no text block on the tail.
    assert not any(p["type"] == "text-delta" for p in parts)
    # The settled ask reached the wire as a plain data-step (no tool frames).
    step_parts = [p for p in parts if p["type"] == "data-step"]
    assert step_parts[-1]["data"]["kind"] == "hitl_request"
    _run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert step_parts[-1]["id"] == str(steps[-1].id)
    assert not any(p["type"] == "tool-input-available" for p in parts)


async def test_armed_run_without_durability_refuses_at_entry(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """T5 (ADR-F071 R6): a pause without a checkpoint is unrecoverable —
    arming without checkpointer+thread_id must raise, never run."""
    from langgraph.checkpoint.memory import InMemorySaver

    run_id = await make_run()
    thread_id = await _thread_id_of(commit_factory, run_id)
    model = ScriptedToolCallingModel(responses=[final_message("unused")])
    armed = {"send_notice": {"allowed_decisions": ["approve", "reject"]}}

    with pytest.raises(ValueError, match="checkpointer"):
        await execute_agent_run(run_id, commit_factory, tools=[], model=model, interrupt_on=armed)
    with pytest.raises(ValueError, match="checkpointer"):
        await execute_agent_run(
            run_id,
            commit_factory,
            tools=[],
            model=model,
            checkpointer=InMemorySaver(),
            interrupt_on=armed,
        )
    with pytest.raises(ValueError, match="checkpointer"):
        await execute_agent_run(
            run_id,
            commit_factory,
            tools=[],
            model=model,
            thread_id=thread_id,
            interrupt_on=armed,
        )


async def test_armed_run_that_never_hits_the_gated_tool_completes_normally(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """R8 (ADR-F071): armed-but-not-paused ⇒ zero behaviour change. An armed run
    whose model calls only UNGATED tools runs them and settles ``completed`` with
    a real answer — no pause, no ``hitl_request`` step. Guards against a drift in
    the not-paused detection mis-settling an ordinary armed run to
    ``awaiting_input`` and locking its thread."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.hitl import compile_hitl_policy

    calls = {"read_clause": 0}

    def read_clause(topic: str) -> str:
        """Return the verbatim text of the contract clause covering ``topic``."""
        calls["read_clause"] += 1
        return _CLAUSE_TEXT

    run_id = await make_run()
    thread_id = await _thread_id_of(commit_factory, run_id)
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("read_clause", {"topic": "liability"}),
            final_message("The liability cap is mutual."),
        ]
    )
    # Armed for a tool the model never calls.
    interrupt_on = compile_hitl_policy(
        {"send_notice": True}, frozenset({"send_notice", "read_clause"})
    )
    assert interrupt_on is not None

    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[read_clause],
        model=model,
        checkpointer=InMemorySaver(),
        thread_id=thread_id,
        interrupt_on=interrupt_on,
    )

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"
    assert run.final_answer == "The liability cap is mutual."
    assert calls == {"read_clause": 1}  # the ungated tool DID run
    assert "hitl_request" not in [s.kind for s in steps]


async def test_in_stream_signal_without_pending_state_settles_completed_and_warns(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """R8 (ADR-F071): the checkpointed state is authoritative, not the in-stream
    ``__interrupt__`` signal. A real interrupt fires (setting the fast in-stream
    flag), but state-inspection reports NO pending action — the run must settle
    ``completed`` (never ``awaiting_input``) and log the signal-drift warning.
    Exercises the in-stream detection block + the drift branch together."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.hitl import compile_hitl_policy

    def send_notice(recipient: str) -> str:
        """Send a notice document to a recipient."""
        raise AssertionError("gated tool must never execute on a paused run")

    # Force the authoritative state read to report "not paused" even though the
    # graph genuinely interrupted — the in-stream flag alone must NOT settle paused.
    async def _no_pending(_agent: Any, _thread_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr("app.agents.runner._pending_hitl_actions", _no_pending)

    run_id = await make_run()
    thread_id = await _thread_id_of(commit_factory, run_id)
    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("send_notice", {"recipient": "counterparty"}),
            final_message("never reached"),
        ]
    )

    with caplog.at_level(logging.WARNING, logger="app.agents.runner"):
        await execute_agent_run(
            run_id,
            commit_factory,
            tools=[send_notice],
            model=model,
            checkpointer=InMemorySaver(),
            thread_id=thread_id,
            interrupt_on=compile_hitl_policy({"send_notice": True}, frozenset({"send_notice"})),
        )

    run, steps = await _load_run_and_steps(commit_factory, run_id)
    assert run.status == "completed"  # state authoritative — NOT awaiting_input
    assert "hitl_request" not in [s.kind for s in steps]
    assert any(
        getattr(rec, "event", None) == "agent_run_hitl_signal_drift"
        or "signal_drift" in rec.getMessage()
        or "without a pending interrupt" in rec.getMessage()
        for rec in caplog.records
    )


async def test_unarmed_run_never_passes_interrupt_on_to_the_builder(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1 zero-config invariant (ADR-F071), pinned at the builder boundary: a run
    with no compiled policy must call ``build_deep_agent`` WITHOUT an
    ``interrupt_on`` kwarg at all (no empty-config middleware) — the graph is
    byte-identical to an unconfigured area's. An armed run, by contrast, passes it.
    The spy delegates to the real builder so both runs complete normally."""
    from langgraph.checkpoint.memory import InMemorySaver

    import app.agents.runner as runner_mod

    real_build = runner_mod.build_deep_agent
    seen: list[bool] = []

    def spy(**kwargs: Any) -> Any:
        seen.append("interrupt_on" in kwargs)
        return real_build(**kwargs)

    monkeypatch.setattr(runner_mod, "build_deep_agent", spy)

    # Unarmed: interrupt_on=None (the zero-config default).
    unarmed_id = await make_run()
    await execute_agent_run(
        unarmed_id,
        commit_factory,
        tools=[],
        model=ScriptedToolCallingModel(responses=[final_message("done")]),
        interrupt_on=None,
    )
    assert seen == [False]  # kwarg omitted entirely

    # Armed: the same seam DOES forward the compiled policy.
    seen.clear()
    armed_id = await make_run()
    armed_thread = await _thread_id_of(commit_factory, armed_id)
    await execute_agent_run(
        armed_id,
        commit_factory,
        tools=[],
        model=ScriptedToolCallingModel(responses=[final_message("done")]),
        checkpointer=InMemorySaver(),
        thread_id=armed_thread,
        interrupt_on={"send_notice": {"allowed_decisions": ["approve", "reject"]}},
    )
    assert seen == [True]


# ---------------------------------------------------------------------------
# HITL-2 resume (ADR-F071)
# ---------------------------------------------------------------------------


async def _run_and_thread_owner(
    factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None
        return run.thread_id, run.user_id


async def _insert_run_on_thread(
    factory: async_sessionmaker[AsyncSession],
    *,
    thread_id: uuid.UUID,
    user_id: uuid.UUID,
    prompt: str = "[resume: approve]",
) -> uuid.UUID:
    """A fresh running run on an EXISTING thread — the run-per-resume shape."""
    async with factory() as db:
        run = AgentRun(
            user_id=user_id,
            thread_id=thread_id,
            status="running",
            prompt=prompt,
            model_alias="smart",
            max_steps=20,
        )
        db.add(run)
        await db.commit()
        return run.id


async def _drive_to_send_notice_pause(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
    saver: Any,
    send_notice: Callable[..., str],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Run an armed agent to a stop-and-ask pause on ``send_notice``.

    Returns (thread_id, user_id). The SAME ``saver`` must be reused for the
    resume so the checkpointed interrupt is visible.
    """
    from app.agents.hitl import compile_hitl_policy

    pause_run = await make_run()
    thread_id, user_id = await _run_and_thread_owner(commit_factory, pause_run)
    interrupt_on = compile_hitl_policy({"send_notice": True}, frozenset({"send_notice"}))
    assert interrupt_on is not None
    await execute_agent_run(
        pause_run,
        commit_factory,
        tools=[send_notice],
        model=ScriptedToolCallingModel(
            responses=[
                tool_call_message("send_notice", {"recipient": "counterparty"}),
                final_message("unused"),
            ]
        ),
        checkpointer=saver,
        thread_id=thread_id,
        interrupt_on=interrupt_on,
    )
    paused, _ = await _load_run_and_steps(commit_factory, pause_run)
    assert paused.status == "awaiting_input"
    return thread_id, user_id


async def test_resume_approve_executes_gated_tool_and_completes(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """HITL-2 (ADR-F071): approving a paused run drives the graph with
    Command(resume=…) on the SAME thread — the gated tool now executes and the
    run settles ``completed``. Exercises the REAL HumanInTheLoopMiddleware."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.hitl import compile_hitl_policy

    saver = InMemorySaver()
    executed = {"n": 0}

    def send_notice(recipient: str) -> str:
        """Send a notice document to a recipient."""
        executed["n"] += 1
        return "sent"

    thread_id, user_id = await _drive_to_send_notice_pause(
        make_run, commit_factory, saver, send_notice
    )
    assert executed["n"] == 0  # nothing ran while paused

    resume_run = await _insert_run_on_thread(commit_factory, thread_id=thread_id, user_id=user_id)
    await execute_agent_run(
        resume_run,
        commit_factory,
        tools=[send_notice],
        model=ScriptedToolCallingModel(responses=[final_message("Notice sent.")]),
        checkpointer=saver,
        thread_id=thread_id,
        # composition re-arms the policy on the resume run — a further gated
        # call would pause again; this one does not.
        interrupt_on=compile_hitl_policy({"send_notice": True}, frozenset({"send_notice"})),
        resume_decision={"type": "approve"},
    )

    rr, _ = await _load_run_and_steps(commit_factory, resume_run)
    assert rr.status == "completed"
    assert rr.final_answer == "Notice sent."
    assert executed["n"] == 1  # the APPROVED call executed exactly once


async def test_resume_reject_closes_turn_without_executing(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """HITL-2 (ADR-F071): rejecting a paused run hands the model the refusal so
    it closes the turn — the gated tool NEVER executes. Distinct from cancel."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.hitl import compile_hitl_policy

    saver = InMemorySaver()
    executed = {"n": 0}

    def send_notice(recipient: str) -> str:
        """Send a notice document to a recipient."""
        executed["n"] += 1
        return "sent"

    thread_id, user_id = await _drive_to_send_notice_pause(
        make_run, commit_factory, saver, send_notice
    )

    resume_run = await _insert_run_on_thread(
        commit_factory, thread_id=thread_id, user_id=user_id, prompt="[resume: reject]"
    )
    await execute_agent_run(
        resume_run,
        commit_factory,
        tools=[send_notice],
        model=ScriptedToolCallingModel(responses=[final_message("Understood — I won't send it.")]),
        checkpointer=saver,
        thread_id=thread_id,
        interrupt_on=compile_hitl_policy({"send_notice": True}, frozenset({"send_notice"})),
        resume_decision={"type": "reject", "message": "not authorised"},
    )

    rr, _ = await _load_run_and_steps(commit_factory, resume_run)
    assert rr.status == "completed"
    assert executed["n"] == 0  # rejected → the tool never ran


async def test_resume_reject_without_message_still_closes_turn(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """HITL-2 (ADR-F071): a reject with NO message is valid — the endpoint
    permits it and the middleware supplies a default rejection to the model
    (``decision.get("message") or <default>``). The tool still never runs."""
    from langgraph.checkpoint.memory import InMemorySaver

    from app.agents.hitl import compile_hitl_policy

    saver = InMemorySaver()
    executed = {"n": 0}

    def send_notice(recipient: str) -> str:
        """Send a notice document to a recipient."""
        executed["n"] += 1
        return "sent"

    thread_id, user_id = await _drive_to_send_notice_pause(
        make_run, commit_factory, saver, send_notice
    )
    resume_run = await _insert_run_on_thread(
        commit_factory, thread_id=thread_id, user_id=user_id, prompt="[resume: reject]"
    )
    await execute_agent_run(
        resume_run,
        commit_factory,
        tools=[send_notice],
        model=ScriptedToolCallingModel(responses=[final_message("Won't do it.")]),
        checkpointer=saver,
        thread_id=thread_id,
        interrupt_on=compile_hitl_policy({"send_notice": True}, frozenset({"send_notice"})),
        resume_decision={"type": "reject"},  # no message
    )
    rr, _ = await _load_run_and_steps(commit_factory, resume_run)
    assert rr.status == "completed"
    assert executed["n"] == 0


async def test_resume_path_skips_repair(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HITL-2 (ADR-F071): the resume path MUST NOT call
    ``repair_dangling_tool_calls`` — repair would answer the gated call with a
    synthetic ToolMessage and destroy the pending interrupt before the resume
    could apply the human's decision."""
    from langgraph.checkpoint.memory import InMemorySaver

    import app.agents.runner as runner_mod
    from app.agents.hitl import compile_hitl_policy

    saver = InMemorySaver()
    calls = {"repair": 0}
    real_repair = runner_mod.repair_dangling_tool_calls

    async def spy(agent: Any, thread_id: uuid.UUID) -> int:
        result = await real_repair(agent, thread_id)  # delegate FIRST so a raise still fails loud
        calls["repair"] += 1
        return result

    monkeypatch.setattr(runner_mod, "repair_dangling_tool_calls", spy)
    executed = {"n": 0}

    def send_notice(recipient: str) -> str:
        """Send a notice document to a recipient."""
        executed["n"] += 1
        return "sent"

    thread_id, user_id = await _drive_to_send_notice_pause(
        make_run, commit_factory, saver, send_notice
    )
    calls["repair"] = 0  # ignore the pause run's own entry repair

    resume_run = await _insert_run_on_thread(commit_factory, thread_id=thread_id, user_id=user_id)
    await execute_agent_run(
        resume_run,
        commit_factory,
        tools=[send_notice],
        model=ScriptedToolCallingModel(responses=[final_message("Notice sent.")]),
        checkpointer=saver,
        thread_id=thread_id,
        interrupt_on=compile_hitl_policy({"send_notice": True}, frozenset({"send_notice"})),
        resume_decision={"type": "approve"},
    )
    rr, _ = await _load_run_and_steps(commit_factory, resume_run)
    assert rr.status == "completed"  # the resume drove the graph to completion...
    assert executed["n"] == 1  # ...the approved tool ran...
    assert calls["repair"] == 0  # ...and repair was NEVER called on the resume path


async def test_new_message_follow_up_dissolves_the_pause(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HITL-2 (ADR-F071): the R11-retirement headline — a NON-resume follow-up
    (a new user message) on a PAUSED thread is the way OUT besides resume. The
    runner repairs the dangling gated call and the model answers the new message,
    so the run reaches ``completed`` and the gated tool never fires. Production
    shape: composition re-arms the area's ``interrupt_on`` for every run on the
    thread, so this follow-up graph carries the HITL middleware too."""
    from langgraph.checkpoint.memory import InMemorySaver

    import app.agents.runner as runner_mod
    from app.agents.hitl import compile_hitl_policy

    saver = InMemorySaver()
    calls = {"repair": 0}
    real_repair = runner_mod.repair_dangling_tool_calls

    async def spy(agent: Any, thread_id: uuid.UUID) -> int:
        result = await real_repair(agent, thread_id)
        calls["repair"] += 1
        return result

    monkeypatch.setattr(runner_mod, "repair_dangling_tool_calls", spy)
    executed = {"n": 0}

    def send_notice(recipient: str) -> str:
        """Send a notice document to a recipient."""
        executed["n"] += 1
        return "sent"

    thread_id, user_id = await _drive_to_send_notice_pause(
        make_run, commit_factory, saver, send_notice
    )
    calls["repair"] = 0

    # A new-message follow-up (resume_decision=None) with the policy RE-ARMED,
    # exactly as composition wires every run on the thread.
    follow_up = await _insert_run_on_thread(
        commit_factory,
        thread_id=thread_id,
        user_id=user_id,
        prompt="actually, never mind — summarise",
    )
    await execute_agent_run(
        follow_up,
        commit_factory,
        tools=[send_notice],
        model=ScriptedToolCallingModel(responses=[final_message("Sure — here is a summary.")]),
        checkpointer=saver,
        thread_id=thread_id,
        interrupt_on=compile_hitl_policy({"send_notice": True}, frozenset({"send_notice"})),
    )
    fr, _ = await _load_run_and_steps(commit_factory, follow_up)
    assert fr.status == "completed"  # the pause DISSOLVED — the run finished...
    assert fr.final_answer == "Sure — here is a summary."
    assert calls["repair"] == 1  # ...via repair on the NON-resume path...
    assert executed["n"] == 0  # ...and the gated tool never fired


async def test_resume_without_pending_interrupt_settles_failed(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """HITL-2 (ADR-F071): a resume whose interrupt has vanished (already
    resolved, or the thread never paused) settles ``failed`` with a bounded,
    non-leaky error — never a silent mis-completion."""
    from langgraph.checkpoint.memory import InMemorySaver

    saver = InMemorySaver()
    base_run = await make_run()
    thread_id, user_id = await _run_and_thread_owner(commit_factory, base_run)
    # Run to normal completion — the checkpoint schedules no further work.
    await execute_agent_run(
        base_run,
        commit_factory,
        tools=[read_clause],
        model=ScriptedToolCallingModel(responses=[final_message("done")]),
        checkpointer=saver,
        thread_id=thread_id,
    )

    resume_run = await _insert_run_on_thread(commit_factory, thread_id=thread_id, user_id=user_id)
    await execute_agent_run(
        resume_run,
        commit_factory,
        tools=[read_clause],
        model=ScriptedToolCallingModel(responses=[final_message("unused")]),
        checkpointer=saver,
        thread_id=thread_id,
        resume_decision={"type": "approve"},
    )
    rr, _ = await _load_run_and_steps(commit_factory, resume_run)
    assert rr.status == "failed"
    assert rr.error is not None
    assert "no pending interrupt" in rr.error


async def test_resume_without_checkpointer_refuses_at_entry(
    make_run: Callable[..., Awaitable[uuid.UUID]],
    commit_factory: async_sessionmaker[AsyncSession],
) -> None:
    """HITL-2 (ADR-F071): a resume without a checkpointer+thread is
    unrecoverable — refuse at entry (mirrors the interrupt_on guard)."""
    run_id = await make_run()
    model = ScriptedToolCallingModel(responses=[final_message("unused")])
    with pytest.raises(ValueError, match=r"(?i)checkpointer and a thread_id"):
        await execute_agent_run(
            run_id,
            commit_factory,
            tools=[read_clause],
            model=model,
            resume_decision={"type": "approve"},
        )
