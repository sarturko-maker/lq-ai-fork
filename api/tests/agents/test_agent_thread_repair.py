"""Thread repair + runner hard-stop — F1-S1 (ADR-F009).

The #3789 regression class, against the REAL deepagents loop: a run
interrupted mid-tool-call leaves the thread's checkpoint transcript
ending in an AIMessage with dangling ``tool_calls``; without repair the
next invoke starts from an invalid alternation (langgraph #6726) and
deepagents' own PatchToolCallsMiddleware repair can permanently wedge
the thread (#3789, open at our 0.6.8 pin). The runner repairs BEFORE
invoking — these tests interrupt a real run, prove the damage, then
prove the follow-up turn completes and the model SAW the honest
synthetic ToolMessage.

Also the heartbeat hard-stop: a run settled elsewhere (cancel/sweep)
must stop the loop via the fenced heartbeat without overwriting the
terminal state.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agents.checkpointer import thread_config
from app.agents.factory import build_deep_agent
from app.agents.lease import claim_run, settle_run
from app.agents.runner import execute_agent_run, repair_dangling_tool_calls
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.user import User
from app.schemas.agent_runs import AgentRunStatus
from app.security import hash_password
from tests.agents.fakes import (
    ScriptedToolCallingModel,
    final_message,
    tool_call_message,
)

pytestmark = pytest.mark.integration


async def hanging_clause_lookup(topic: str) -> str:
    """A tool that outlives the wall clock — the mid-tool-call death."""
    await asyncio.sleep(60)
    return "never reached"  # pragma: no cover


def quick_clause_lookup(topic: str) -> str:
    """Return the contract clause covering ``topic`` (instant)."""
    return "Clause 7.2: liability capped at twelve months of fees."


@pytest_asyncio.fixture
async def commit_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def make_thread_run(
    commit_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]]]:
    """Committed (thread_id, run_id) pairs; cascade-delete at teardown."""
    user_ids: list[uuid.UUID] = []

    async def _make(
        *, thread_id: uuid.UUID | None = None, prompt: str = "What is the liability cap?"
    ) -> tuple[uuid.UUID, uuid.UUID]:
        async with commit_factory() as db:
            user = User(
                email=f"agent-repair-{uuid.uuid4().hex[:8]}@example.com",
                display_name="Repair Test User",
                hashed_password=hash_password("correct-horse-battery-staple"),
                is_admin=False,
                mfa_enabled=False,
                must_change_password=False,
            )
            db.add(user)
            await db.flush()
            user_ids.append(user.id)
            if thread_id is None:
                thread = AgentThread(user_id=user.id, title=prompt[:120])
                db.add(thread)
                await db.flush()
                thread_id = thread.id
            run = AgentRun(
                user_id=user.id,
                thread_id=thread_id,
                status="running",
                prompt=prompt,
                model_alias="smart",
                max_steps=20,
            )
            db.add(run)
            await db.commit()
            return thread_id, run.id

    yield _make

    async with commit_factory() as db:
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


async def _damage_thread(
    commit_factory: async_sessionmaker[AsyncSession],
    make_thread_run: Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]],
    saver: InMemorySaver,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Interrupt a REAL run mid-tool-call; return (thread_id, run_id).

    durability='sync' persists the model turn's checkpoint before the
    tool node hangs, so the wall-clock cancellation strands exactly the
    dangling-AIMessage state the repair exists for.
    """
    thread_id, run_id = await make_thread_run()
    model = ScriptedToolCallingModel(
        responses=[tool_call_message("hanging_clause_lookup", {"topic": "liability"})]
    )
    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[hanging_clause_lookup],
        model=model,
        wall_clock_seconds=3.0,
        checkpointer=saver,
        thread_id=thread_id,
    )
    async with commit_factory() as db:
        run = await db.get(AgentRun, run_id)
        assert run is not None and run.status == AgentRunStatus.failed.value
        assert run.error == "timeout"
    return thread_id, run_id


async def test_interrupted_run_strands_a_dangling_tool_call(
    commit_factory: async_sessionmaker[AsyncSession],
    make_thread_run: Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]],
) -> None:
    """The damage is real: the transcript ends in an unanswered
    tool_call (this is what un-repaired threads choke on)."""
    saver = InMemorySaver()
    thread_id, _ = await _damage_thread(commit_factory, make_thread_run, saver)

    agent = build_deep_agent(
        model=ScriptedToolCallingModel(responses=[final_message("unused")]),
        tools=[hanging_clause_lookup],
        system_prompt="test",
        checkpointer=saver,
    )
    state = await agent.aget_state(thread_config(thread_id))
    messages = state.values["messages"]
    last = messages[-1]
    assert isinstance(last, AIMessage) and last.tool_calls
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    assert all(c["id"] not in answered for c in last.tool_calls)


async def test_repair_appends_honest_synthetic_tool_messages(
    commit_factory: async_sessionmaker[AsyncSession],
    make_thread_run: Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]],
) -> None:
    saver = InMemorySaver()
    thread_id, _ = await _damage_thread(commit_factory, make_thread_run, saver)

    agent = build_deep_agent(
        model=ScriptedToolCallingModel(responses=[final_message("unused")]),
        tools=[hanging_clause_lookup],
        system_prompt="test",
        checkpointer=saver,
    )
    repaired = await repair_dangling_tool_calls(agent, thread_id)
    assert repaired == 1
    state = await agent.aget_state(thread_config(thread_id))
    tail = state.values["messages"][-1]
    assert isinstance(tail, ToolMessage)
    assert "may or may not have executed" in str(tail.content)
    # Idempotent: a second pass finds nothing dangling.
    assert await repair_dangling_tool_calls(agent, thread_id) == 0


async def test_repair_is_a_noop_on_a_healthy_thread(
    commit_factory: async_sessionmaker[AsyncSession],
    make_thread_run: Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]],
) -> None:
    saver = InMemorySaver()
    thread_id, run_id = await make_thread_run()
    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[quick_clause_lookup],
        model=ScriptedToolCallingModel(
            responses=[
                tool_call_message("quick_clause_lookup", {"topic": "liability"}),
                final_message("The cap is twelve months of fees."),
            ]
        ),
        checkpointer=saver,
        thread_id=thread_id,
    )
    agent = build_deep_agent(
        model=ScriptedToolCallingModel(responses=[final_message("unused")]),
        tools=[quick_clause_lookup],
        system_prompt="test",
        checkpointer=saver,
    )
    assert await repair_dangling_tool_calls(agent, thread_id) == 0


async def test_follow_up_after_interruption_completes(
    commit_factory: async_sessionmaker[AsyncSession],
    make_thread_run: Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]],
) -> None:
    """THE #3789 regression: interrupted mid-tool-call → the next turn
    on the same thread completes (repair runs inside execute_agent_run)
    and the follow-up model call SAW the honest interruption notice."""
    saver = InMemorySaver()
    thread_id, _ = await _damage_thread(commit_factory, make_thread_run, saver)

    _, run2_id = await make_thread_run(thread_id=thread_id, prompt="So what is the cap?")
    follow_up_model = ScriptedToolCallingModel(
        responses=[final_message("After the interruption: the cap is twelve months of fees.")]
    )
    await execute_agent_run(
        run2_id,
        commit_factory,
        tools=[quick_clause_lookup],
        model=follow_up_model,
        checkpointer=saver,
        thread_id=thread_id,
    )

    async with commit_factory() as db:
        run2 = await db.get(AgentRun, run2_id)
        assert run2 is not None
        assert run2.status == AgentRunStatus.completed.value
        assert run2.final_answer is not None and "twelve months" in run2.final_answer
    # The follow-up's model call contained the synthetic repair message.
    seen = follow_up_model.seen_messages[0]
    repair_notices = [
        m for m in seen if isinstance(m, ToolMessage) and "may or may not" in str(m.content)
    ]
    assert repair_notices, "the repair ToolMessage must be part of the resumed transcript"


async def test_heartbeat_hard_stops_a_run_settled_elsewhere(
    commit_factory: async_sessionmaker[AsyncSession],
    make_thread_run: Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]],
) -> None:
    """Cancel/sweep won the row mid-run: the fenced heartbeat misses,
    the loop hard-stops, and the terminal state is NOT overwritten
    (ADR-F009 terminal-status monotonicity, runner side)."""
    _, run_id = await make_thread_run()
    lease = await claim_run(commit_factory, run_id, claimed_by="w1")
    assert lease is not None
    # The cancel endpoint wins the row before the loop starts.
    assert await settle_run(commit_factory, run_id, status=AgentRunStatus.cancelled)

    model = ScriptedToolCallingModel(
        responses=[
            tool_call_message("quick_clause_lookup", {"topic": "liability"}),
            final_message("should never be written"),
        ],
        loop_last=True,
    )
    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[quick_clause_lookup],
        model=model,
        lease=lease,
        heartbeat_seconds=0.0,  # beat on every event — deterministic stop
    )

    # The hard-stop itself, not just monotonicity (review fix): the loop
    # stopped BEFORE any model call (no gateway spend) and persisted
    # nothing.
    assert model.seen_messages == []
    async with commit_factory() as db:
        steps = (
            (await db.execute(select(AgentRunStep).where(AgentRunStep.run_id == run_id)))
            .scalars()
            .all()
        )
        assert steps == []
        run = await db.get(AgentRun, run_id)
        assert run is not None
        assert run.status == AgentRunStatus.cancelled.value
        assert run.final_answer is None


async def slow_clause_lookup(topic: str) -> str:
    """Slower than the instant tool but still inside the wall clock."""
    await asyncio.sleep(0.3)
    return "Clause 9: governing law is Delaware."


async def test_repair_sees_the_checkpoint_view_not_pending_writes(
    commit_factory: async_sessionmaker[AsyncSession],
    make_thread_run: Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]],
) -> None:
    """Review fix (#3789 window): a run can die AFTER one parallel
    tool's result landed as a PENDING WRITE but BEFORE the superstep
    checkpoint. An un-pinned aget_state shows that call answered; the
    next invoke DISCARDS pending writes. Repair must use the pinned
    (checkpoint-only) view, or the dangling call survives repair and
    re-enters the middleware wedge path."""
    saver = InMemorySaver()
    thread_id, run_id = await make_thread_run()
    # One AIMessage requesting TWO parallel tools: one finishes fast
    # (its write can land as a pending write), one outlives the wall
    # clock (kills the superstep before its checkpoint).
    two_calls = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "slow_clause_lookup",
                "args": {"topic": "law"},
                "id": "call_fast",
                "type": "tool_call",
            },
            {
                "name": "hanging_clause_lookup",
                "args": {"topic": "liability"},
                "id": "call_hang",
                "type": "tool_call",
            },
        ],
    )
    await execute_agent_run(
        run_id,
        commit_factory,
        tools=[slow_clause_lookup, hanging_clause_lookup],
        model=ScriptedToolCallingModel(responses=[two_calls]),
        wall_clock_seconds=3.0,
        checkpointer=saver,
        thread_id=thread_id,
    )

    agent = build_deep_agent(
        model=ScriptedToolCallingModel(responses=[final_message("unused")]),
        tools=[slow_clause_lookup, hanging_clause_lookup],
        system_prompt="test",
        checkpointer=saver,
    )
    repaired = await repair_dangling_tool_calls(agent, thread_id)
    # BOTH calls must be answered in the checkpoint view the next invoke
    # uses — the fast call's ToolMessage existed (if at all) only as a
    # pending write the invoke would discard.
    assert repaired == 2

    # And the follow-up completes — the actual user-facing guarantee.
    _, run2_id = await make_thread_run(thread_id=thread_id, prompt="And the cap?")
    await execute_agent_run(
        run2_id,
        commit_factory,
        tools=[slow_clause_lookup, hanging_clause_lookup],
        model=ScriptedToolCallingModel(responses=[final_message("Twelve months of fees.")]),
        checkpointer=saver,
        thread_id=thread_id,
    )
    async with commit_factory() as db:
        run2 = await db.get(AgentRun, run2_id)
        assert run2 is not None and run2.status == AgentRunStatus.completed.value


async def test_follow_up_with_degraded_checkpointer_settles_failed(
    commit_factory: async_sessionmaker[AsyncSession],
    make_thread_run: Callable[..., Awaitable[tuple[uuid.UUID, uuid.UUID]]],
) -> None:
    """Review fix: admission promised continuation (API-side saver), but
    the WORKER's checkpointer is degraded — executing would silently
    answer with zero history while the UI presents a continuation.
    Refuse honestly instead."""
    from app.agents.composition import compose_and_execute_run

    thread_id, first_run_id = await make_thread_run()
    # Settle run 1 first — the partial unique index allows only one
    # RUNNING run per thread (and a real follow-up is only admitted
    # after the prior run settled anyway).
    assert await settle_run(commit_factory, first_run_id, status=AgentRunStatus.failed, error="x")
    _, run2_id = await make_thread_run(thread_id=thread_id, prompt="continue?")

    model = ScriptedToolCallingModel(responses=[final_message("should never run")])
    await compose_and_execute_run(
        run_id=run2_id,
        model_builder=lambda **_kw: model,
        session_factory_provider=lambda: commit_factory,
        checkpointer_provider=lambda: None,
    )

    assert model.seen_messages == []  # never invoked
    async with commit_factory() as db:
        run2 = await db.get(AgentRun, run2_id)
        assert run2 is not None
        assert run2.status == AgentRunStatus.failed.value
        assert run2.error == "persistence degraded: checkpointer unavailable in worker"
