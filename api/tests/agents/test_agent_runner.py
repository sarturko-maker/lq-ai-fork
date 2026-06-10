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

from app.agents.runner import execute_agent_run
from app.models.agent_run import AgentRun, AgentRunStep
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
            run = AgentRun(
                user_id=user.id,
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
    (no monkeypatching). Call 1 is the runner's driving session; calls
    2+ are ``_finalize``'s fresh terminal-write sessions.
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

    The factory poisons call 2 (``_finalize``'s first fresh session);
    the retry (call 3) opens another fresh session and lands the
    terminal state.
    """
    run_id = await make_run()
    factory = _FlakySessionFactory(commit_factory, fail_on_calls={2})
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
    assert factory.calls == 3  # driving session, poisoned finalize, fresh retry


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
    factory = _FlakySessionFactory(commit_factory, fail_on_calls={2, 3})
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
                {"description": "summarise the clause", "subagent_type": "general-purpose"},
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
    assert kinds == ["model_turn", "tool_call", "model_turn", "tool_result", "model_turn"]
    assert steps[1].name == "task"
    # The nested turn IS persisted as visible activity — just not as the answer.
    assert "SUBAGENT closing turn" in steps[2].summary


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
                {"description": "summarise the clause", "subagent_type": "general-purpose"},
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
