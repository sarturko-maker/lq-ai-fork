"""Deep-agent run executor — F0-S2 (fork).

:func:`execute_agent_run` drives one persisted :class:`~app.models.agent_run.AgentRun`
through a deep agent built from :mod:`app.agents.factory`, appending an
:class:`~app.models.agent_run.AgentRunStep` row — and COMMITTING — after
every observable loop step so a poller (the ADR-F002 capability rail)
sees progress live. User-visible state derives from these settled rows,
never from parsing LLM turns (ADR-F004).

Event mapping (``agent.astream_events(..., version="v2")``):

* ``on_chat_model_end``  → ``model_turn``  (one completed model call)
* ``on_tool_start``      → ``tool_call``   (the model dispatched a tool)
* ``on_tool_end``        → ``tool_result`` (the tool returned)

Interim caps (F0-S2): ``max_steps`` from the run row (exceeding →
``cap_exceeded``) and a wall-clock timeout (→ ``failed`` with
``error='timeout'``). Step summaries are bounded to ~2000 chars; tool
args/results are truncated and never carry raw secrets.

Dependency injection per CLAUDE.md: the DB session factory, the tool
set, and the chat model are constructor arguments — tests substitute
fakes through the same seams, no monkeypatching. The caller
(:func:`app.agents.composition.compose_and_execute_run`) is the composition point:
it assembles the matter's guarded document tools (F0-S4,
:mod:`app.agents.tools`), the gateway chat model (with the matter's
tier-floor/privilege envelope), and the system prompt — this module
only drives the loop and persists what happened.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable, Collection, Sequence
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.checkpointer import thread_config
from app.agents.factory import build_deep_agent
from app.agents.lease import RunLease, RunSettledElsewhere, heartbeat_run, settle_run
from app.agents.stream import RunStreamPublisher, step_payload
from app.models.agent_run import AgentRun, AgentRunStep
from app.schemas.agent_runs import AgentRunStatus, AgentRunStepKind

logger = logging.getLogger(__name__)

DEFAULT_WALL_CLOCK_SECONDS = 300.0

# Bounded step digests — the polled UI renders these verbatim, so tool
# args/results are truncated here, before they ever reach a row.
_SUMMARY_LIMIT = 2000

# Default system prompt; the composition point appends the matter
# addendum for matter-bound runs (F0-S4). Public so the caller extends
# rather than restates it.
SYSTEM_PROMPT = (
    "You are LQ.AI's in-house legal deep agent. Work the user's request "
    "step by step, using the available tools whenever they can ground "
    "your answer — never invent contract text you could fetch. Finish "
    "with a concise, complete answer."
)


def _bounded(value: str, limit: int = _SUMMARY_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _text_of(content: Any) -> str:
    """Flatten message content (plain string or block list) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content)


def _message_from_chat_model_output(output: Any) -> Any:
    """Unwrap ``on_chat_model_end``'s output to the AI message.

    astream_events v2 emits the message directly; an LLMResult-shaped
    output (older event plumbing) is unwrapped defensively.
    """
    generations = getattr(output, "generations", None)
    if generations:
        first = generations[0]
        if isinstance(first, list) and first:
            return first[0].message
    return output


def _step_from_event(
    event: dict[str, Any],
) -> tuple[AgentRunStepKind, str | None, str, bool] | None:
    """Map one astream_events v2 event to ``(kind, name, summary, no_tools)``.

    Returns None for events that are not persisted steps. ``no_tools``
    is True for a model turn that requested no tools — a CANDIDATE for
    the run's final answer; :func:`_drive_agent` additionally requires
    the turn to be top-level (not nested under a tool run, i.e. not a
    subagent's or tool-wrapped middleware's turn) before treating it as
    final (F4 fix).
    """
    kind = event.get("event")
    data = event.get("data") or {}

    if kind == "on_chat_model_end":
        message = _message_from_chat_model_output(data.get("output"))
        text = _text_of(getattr(message, "content", "")).strip()
        tool_calls = getattr(message, "tool_calls", None) or []
        parts: list[str] = []
        if text:
            parts.append(text)
        if tool_calls:
            names = ", ".join(str(call.get("name", "?")) for call in tool_calls)
            parts.append(f"[requested tools: {names}]")
        summary = _bounded(" ".join(parts) or "(empty model turn)")
        return AgentRunStepKind.model_turn, None, summary, not tool_calls

    if kind == "on_tool_start":
        try:
            args = json.dumps(data.get("input"), default=str, sort_keys=True)
        except (TypeError, ValueError):
            args = str(data.get("input"))
        return AgentRunStepKind.tool_call, event.get("name"), _bounded(args), False

    if kind == "on_tool_end":
        output = data.get("output")
        content = getattr(output, "content", output)
        return (
            AgentRunStepKind.tool_result,
            event.get("name"),
            _bounded(_text_of(content)),
            False,
        )

    return None


def _is_nested(event: dict[str, Any], tool_run_ids: Collection[str]) -> bool:
    """True if ``event`` ran underneath any tool invocation.

    astream_events v2 events carry ``parent_ids`` — the run-id chain
    from the root graph down (verified against langchain-core 1.4.3).
    A chat-model turn whose ancestry includes a tool run belongs to a
    subagent (the deepagents ``task`` tool) or a tool-wrapped middleware
    graph, never to the root loop — so its no-tool turn must not be
    mistaken for the run's final answer.
    """
    return any(str(pid) in tool_run_ids for pid in event.get("parent_ids") or [])


def _innermost_tool_parent(
    event: dict[str, Any], tool_step_ids: dict[str, uuid.UUID]
) -> uuid.UUID | None:
    """The settled ``tool_call`` row this event ran underneath, if any.

    ``parent_ids`` orders the chain root-first, so the first match
    scanning from the END is the innermost enclosing tool dispatch —
    that row id becomes the step's ``parent_step_id`` (F0-S7: the
    ancestry the loop always computed but dropped at persist time).
    """
    for pid in reversed(event.get("parent_ids") or []):
        step_id = tool_step_ids.get(str(pid))
        if step_id is not None:
            return step_id
    return None


async def _persist_step(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    step_id: uuid.UUID,
    run_id: uuid.UUID,
    seq: int,
    kind: str,
    name: str | None,
    summary: str,
    parent_step_id: uuid.UUID | None,
    created_at: datetime,
) -> None:
    """Write one step row in its own short-lived session, retrying once.

    The loop used to hold ONE session for the whole run; a Postgres
    restart mid-run (the dev box's crash-recovery gotcha — seen live in
    the F0-S5 gate) then failed the run on the next INSERT ("connection
    is closed") even though the loop itself was healthy. A fresh session
    per step checks out a pre-pinged connection (``pool_pre_ping`` on
    the engine), and one retry after a short pause rides out a
    crash-recovery window in progress — same fresh-session posture as
    :func:`_finalize`. The ``(run_id, seq)``
    unique constraint makes a double write impossible.

    ``step_id`` / ``created_at`` are caller-generated (F0-S7) so the
    settled row and the wire's ``data-step`` mirror of it are built from
    the same values without a post-commit refresh.
    """
    for attempt in (1, 2):
        try:
            async with session_factory() as db:
                db.add(
                    AgentRunStep(
                        id=step_id,
                        run_id=run_id,
                        seq=seq,
                        kind=kind,
                        name=name,
                        summary=summary,
                        parent_step_id=parent_step_id,
                        created_at=created_at,
                    )
                )
                await db.commit()
                return
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(2.0)


async def _drive_agent(
    agent: Any,
    *,
    run_id: uuid.UUID,
    prompt: str,
    max_steps: int,
    session_factory: async_sessionmaker[AsyncSession],
    wall_clock_seconds: float,
    thread_id: uuid.UUID | None = None,
    publisher: RunStreamPublisher | None = None,
    lease: RunLease | None = None,
    heartbeat_seconds: float | None = None,
) -> tuple[str | None, bool]:
    """Stream the agent, persisting one step row + COMMIT per event.

    The commit-per-step is the load-bearing transaction pattern: the
    run's progress is readable mid-flight (ADR-F002 live activity), and
    a crash loses at most the in-flight step. Returns
    ``(final_answer, cap_hit)``.

    With ``thread_id`` set (F0-S5) the invocation addresses that
    conversation's checkpoint lineage: the new user message is APPENDED
    to the thread's persisted state by the ``add_messages`` reducer, so
    a follow-up run continues the same conversation (ADR-F008).

    With ``publisher`` set (F0-S7) the loop ALSO mirrors itself onto the
    SSE v2 stream: every settled row right after its commit (settled
    rows decide), plus live-only animation — model deltas as reasoning
    blocks, top-level turn boundaries as step frames. Publishing is
    fire-and-forget; the stream never gates or fails the run.

    With ``lease`` set (F1-S1, ADR-F009) the loop heartbeats the run row
    (throttled to one fenced write per ``heartbeat_seconds``) from INSIDE
    the event stream — the per-event granularity that survives long tool
    calls (langgraph #7417's per-job heartbeat is the failure case). A
    heartbeat that hits zero rows means the run was settled elsewhere
    (sweep / cancel): the loop hard-stops via :class:`RunSettledElsewhere`
    — every further gateway call would be spend on a run the user
    already sees as settled. ``durability="sync"`` pins each superstep's
    checkpoint before its effects can outrun a crash.
    """
    seq = 0
    final_answer: str | None = None
    cap_hit = False
    interval = heartbeat_seconds if heartbeat_seconds is not None else _default_heartbeat_seconds()
    last_beat = asyncio.get_running_loop().time()
    # Settled tool_call row id per dispatched tool's langchain run id.
    # The keys are the _is_nested ancestry test (F4); the values resolve
    # each nested step's parent_step_id and each tool_result's wire
    # toolCallId (F0-S7). Never pruned: a finished tool's id cannot
    # reappear in a later event's parent chain, and runs are bounded by
    # max_steps anyway.
    tool_step_ids: dict[str, uuid.UUID] = {}

    stream_kwargs: dict[str, Any] = {"version": "v2"}
    if thread_id is not None:
        stream_kwargs["config"] = thread_config(thread_id)
        # ADR-F009: the default "async" durability can lose the checkpoint
        # of a superstep whose side effects already ran — correctness
        # first; revisit only if checkpoint write latency measures badly.
        # Only with a checkpointer: langgraph's loop breaks on the kwarg
        # when none is present (AsyncPregelLoop._put_checkpoint_fut
        # AttributeError at langgraph 1.2.x, beyond the documented
        # "no effect" warning).
        stream_kwargs["durability"] = "sync"
    stream = agent.astream_events(
        {"messages": [{"role": "user", "content": prompt}]},
        **stream_kwargs,
    )
    try:
        async with asyncio.timeout(wall_clock_seconds):
            async for event in stream:
                etype = event.get("event")
                event_run_id = str(event.get("run_id") or "")
                if lease is not None:
                    now = asyncio.get_running_loop().time()
                    if now - last_beat >= interval:
                        last_beat = now
                        if not await heartbeat_run(session_factory, lease):
                            raise RunSettledElsewhere(str(run_id))
                if publisher is not None:
                    if etype == "on_chat_model_stream":
                        chunk = (event.get("data") or {}).get("chunk")
                        delta = _text_of(getattr(chunk, "content", ""))
                        if delta:
                            publisher.reasoning_delta(event_run_id, delta)
                        continue  # never a persisted step
                    if etype == "on_chat_model_start" and not _is_nested(event, tool_step_ids):
                        publisher.turn_started()
                step = _step_from_event(event)
                if step is None:
                    continue
                kind, name, summary, no_tools = step
                nested = _is_nested(event, tool_step_ids)
                # Final = top-level model turn with no tool requests. A
                # subagent's (or tool-wrapped middleware's) closing turn
                # is nested under its tool run and is NOT the answer (F4).
                is_final = no_tools and not nested
                seq += 1
                step_id = uuid.uuid4()
                created_at = datetime.now(UTC)
                parent_step_id = _innermost_tool_parent(event, tool_step_ids)
                await _persist_step(
                    session_factory,
                    step_id=step_id,
                    run_id=run_id,
                    seq=seq,
                    kind=kind.value,
                    name=name,
                    summary=summary,
                    parent_step_id=parent_step_id,
                    created_at=created_at,
                )
                if etype == "on_tool_start" and event_run_id:
                    tool_step_ids[event_run_id] = step_id
                if publisher is not None:
                    if kind is AgentRunStepKind.model_turn:
                        publisher.reasoning_end(event_run_id)
                    publisher.step_settled(
                        step_payload(
                            step_id=step_id,
                            run_id=run_id,
                            seq=seq,
                            kind=kind.value,
                            name=name,
                            summary=summary,
                            parent_step_id=parent_step_id,
                            created_at=created_at,
                        ),
                        tool_call_id=(
                            str(tool_step_ids[event_run_id])
                            if kind is AgentRunStepKind.tool_result
                            and event_run_id in tool_step_ids
                            else None
                        ),
                    )
                    if kind is AgentRunStepKind.model_turn and not nested:
                        publisher.turn_finished()
                if is_final:
                    # The deliverable itself is the user's work product —
                    # persisted in full, not bounded like step digests.
                    message = _message_from_chat_model_output(
                        (event.get("data") or {}).get("output")
                    )
                    final_answer = _text_of(getattr(message, "content", "")).strip() or None
                if seq >= max_steps and not is_final:
                    cap_hit = True
                    break
    finally:
        await stream.aclose()
    return final_answer, cap_hit


def _default_heartbeat_seconds() -> float:
    """Settings-backed default, read lazily (DI: tests pass the param)."""
    from app.config import get_settings

    return get_settings().agent_run_heartbeat_seconds


async def _finalize(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    *,
    status: AgentRunStatus,
    final_answer: str | None = None,
    error: str | None = None,
    lease: RunLease | None = None,
) -> bool:
    """Write the terminal state — F1-S1: one fenced conditional UPDATE.

    Delegates to :func:`app.agents.lease.settle_run` (fresh-session,
    retry-once — the F0-S2 posture survives): ``WHERE status='running'``
    gives terminal-status monotonicity for every caller (a cancel that
    raced us wins; we never flip 'cancelled' to 'completed'), and the
    lease token fences a worker-side write so a zombie can never
    overwrite its successor's state (ADR-F009). Returns whether THIS
    call settled the run — the publisher only announces a terminal
    state this process actually wrote.
    """
    return await settle_run(
        session_factory,
        run_id,
        status=status,
        final_answer=final_answer,
        error=error,
        lease_token=lease.token if lease is not None else None,
    )


async def repair_dangling_tool_calls(agent: Any, thread_id: uuid.UUID) -> int:
    """Append synthetic ToolMessages for unanswered tool calls (F1-S1).

    A run settled non-cooperatively (cancel, orphan sweep, crash) can
    leave the thread's checkpoint transcript ending in an AIMessage with
    ``tool_calls`` no ToolMessage ever answered — the next invoke then
    starts from an invalid alternation (langgraph #6726), and deepagents'
    own ``PatchToolCallsMiddleware`` repair can permanently wedge the
    thread (#3789, open at our pin). Repairing here, BEFORE the invoke,
    leaves that middleware nothing to patch — the wedge path is never
    entered. ``as_node="tools"`` because the synthetic answers logically
    come from the tool node (and a plain update raises
    ``InvalidUpdateError: Ambiguous update`` on this graph — verified
    against deepagents 0.6.8).

    The wording is honest about side effects: the tool MAY have executed
    before the interruption (its result just never reached the
    transcript). Returns the number of repairs written.
    """
    config = thread_config(thread_id)
    state = await agent.aget_state(config)
    if state is None or not (state.values or {}).get("messages"):
        return 0
    # Re-read PINNED to the snapshot's checkpoint id: an un-pinned
    # aget_state applies the checkpoint's PENDING WRITES (langgraph
    # 1.2.4), but the next invoke's input path DISCARDS those same
    # writes — repair must see exactly what the invoke will see, or a
    # tool call answered only in pending writes is skipped and the
    # #3789 middleware path re-opens (review fix). state.config carries
    # the checkpoint_id, which turns pending-write application off.
    pinned = await agent.aget_state(state.config)
    messages = (pinned.values or {}).get("messages") if pinned is not None else None
    if not messages:
        return 0
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage) and m.tool_call_id}
    synthetic = [
        ToolMessage(
            content=(
                "This tool call was interrupted before its result was recorded "
                "(the run was cancelled or its worker died). The action may or "
                "may not have executed — re-run it if its result is needed."
            ),
            tool_call_id=call_id,
        )
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls or []
        if (call_id := call.get("id")) and call_id not in answered
    ]
    if not synthetic:
        return 0
    await agent.aupdate_state(config, {"messages": synthetic}, as_node="tools")
    logger.info(
        "repaired dangling tool calls before invoke",
        extra={
            "event": "agent_thread_repaired",
            "thread_id": str(thread_id),
            "repaired": len(synthetic),
        },
    )
    return len(synthetic)


async def execute_agent_run(
    run_id: uuid.UUID,
    db_session_factory: async_sessionmaker[AsyncSession],
    *,
    tools: Sequence[Callable[..., Any]],
    model: BaseChatModel,
    system_prompt: str = SYSTEM_PROMPT,
    subagents: Sequence[dict[str, Any]] | None = None,
    wall_clock_seconds: float = DEFAULT_WALL_CLOCK_SECONDS,
    checkpointer: BaseCheckpointSaver | None = None,
    thread_id: uuid.UUID | None = None,
    publisher: RunStreamPublisher | None = None,
    lease: RunLease | None = None,
    heartbeat_seconds: float | None = None,
) -> None:
    """Execute one persisted agent run end to end.

    Opens its own DB session (the kick-off request's session closes when
    the 202 returns — same model as the playbook executor). ``tools``
    and ``model`` are injected by the composition point (F0-S4: the
    matter tools arrive pre-wrapped in the :mod:`app.agents.guard`
    chokepoint; the model carries the gateway envelope) — this function
    never builds either, so tests drive the real loop with fakes
    through the same seams.

    ``checkpointer`` + ``thread_id`` (F0-S5, ADR-F008) make the run
    multi-turn: state persists under the conversation's thread id and a
    later run on the same thread continues it. Both-or-neither — a
    checkpointer without a thread id would persist state nowhere
    addressable, a thread id without a checkpointer would silently
    drop history; the composition point passes both or neither.

    ``publisher`` (F0-S7) mirrors the run onto the SSE v2 stream; every
    terminal path below also closes the stream with the same settled
    state it writes to the run row, AFTER the row is written — the wire
    never announces a terminal state the DB doesn't have yet.

    Terminal writes: ``completed`` (+ ``final_answer``), ``cap_exceeded``
    (step cap), or ``failed`` (``error='timeout'`` for the wall clock;
    otherwise a bounded exception summary — never a stack trace).
    """
    # Load-then-release: the run's fields are snapshotted in a short
    # session; the loop itself holds NO long-lived connection (each step
    # write opens its own — see _persist_step). A Postgres restart
    # mid-run can then only fail the single write in flight, not the run.
    async with db_session_factory() as db:
        run = await db.get(AgentRun, run_id)
        if run is None:
            logger.warning(
                "agent run vanished before execution",
                extra={"event": "agent_run_missing", "run_id": str(run_id)},
            )
            return
        prompt, max_steps = run.prompt, run.max_steps

    try:
        # ADR-F002 chokepoint: matter tools dispatch through
        # app.agents.guard (F0-S4 minimal — R6 grants / R5 halt /
        # audit). F1 extends the wrap to the full tool universe
        # incl. the deepagents builtins, plus R4 budgets.
        # F1-S3: per-area declarative subagents (ADR-F010 — every spec is
        # model-free, so each inherits the gateway-bound parent model;
        # build_deep_agent re-asserts the guard). Omitted entirely when an
        # area declares none, so the qualified default graph is unchanged.
        agent_kwargs: dict[str, Any] = {"checkpointer": checkpointer}
        if subagents:
            agent_kwargs["subagents"] = list(subagents)
        agent = build_deep_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            **agent_kwargs,
        )
        if checkpointer is not None and thread_id is not None:
            # F1-S1 thread repair: a prior run settled non-cooperatively
            # may have left dangling tool_calls in the transcript.
            await repair_dangling_tool_calls(agent, thread_id)
        final_answer, cap_hit = await _drive_agent(
            agent,
            run_id=run_id,
            prompt=prompt,
            max_steps=max_steps,
            session_factory=db_session_factory,
            wall_clock_seconds=wall_clock_seconds,
            thread_id=thread_id if checkpointer is not None else None,
            publisher=publisher,
            lease=lease,
            heartbeat_seconds=heartbeat_seconds,
        )
    except RunSettledElsewhere:
        # Sweep or cancel won the row (ADR-F009): no terminal write of
        # ours could land (fenced), and the wire must not announce a
        # state the DB doesn't have — close the stream bare.
        logger.info(
            "agent run hard-stopped: settled elsewhere",
            extra={"event": "agent_run_settled_elsewhere", "run_id": str(run_id)},
        )
        if publisher is not None:
            publisher.close()
        return
    except TimeoutError:
        settled = await _finalize(
            db_session_factory,
            run_id,
            status=AgentRunStatus.failed,
            error="timeout",
            lease=lease,
        )
        if publisher is not None and settled:
            publisher.run_finished(status=AgentRunStatus.failed.value, error="timeout")
        elif publisher is not None:
            publisher.close()
        return
    except Exception as exc:
        # Bounded type+message only — stack traces stay in logs.
        logger.exception(
            "agent run failed",
            extra={"event": "agent_run_failed", "run_id": str(run_id)},
        )
        error = _bounded(f"{type(exc).__name__}: {exc}", 500)
        settled = await _finalize(
            db_session_factory,
            run_id,
            status=AgentRunStatus.failed,
            error=error,
            lease=lease,
        )
        if publisher is not None and settled:
            publisher.run_finished(status=AgentRunStatus.failed.value, error=error)
        elif publisher is not None:
            publisher.close()
        return

    status = AgentRunStatus.cap_exceeded if cap_hit else AgentRunStatus.completed
    settled = await _finalize(
        db_session_factory,
        run_id,
        status=status,
        # A capped run has no deliverable: any captured answer text is
        # incidental (e.g., a subagent's closing turn), not the run's
        # final answer — leave it NULL (F4).
        final_answer=None if cap_hit else final_answer,
        lease=lease,
    )
    if publisher is not None and settled:
        publisher.run_finished(
            status=status.value,
            final_answer=None if cap_hit else final_answer,
        )
    elif publisher is not None:
        publisher.close()
