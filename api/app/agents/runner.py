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
set, and (for tests) the chat model are constructor arguments — tests
substitute fakes through the same seams, no monkeypatching. The caller
(``app.api.agent_runs``) injects the S2 demo tool; S3+ injects the
practice-area tool universe through the same ``tools`` parameter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.factory import build_deep_agent, build_gateway_chat_model
from app.models.agent_run import AgentRun, AgentRunStep
from app.schemas.agent_runs import AgentRunStatus, AgentRunStepKind

logger = logging.getLogger(__name__)

DEFAULT_WALL_CLOCK_SECONDS = 300.0

# Bounded step digests — the polled UI renders these verbatim, so tool
# args/results are truncated here, before they ever reach a row.
_SUMMARY_LIMIT = 2000

_SYSTEM_PROMPT = (
    "You are LQ.AI's in-house legal deep agent. Work the user's request "
    "step by step, using the available tools whenever they can ground "
    "your answer — never invent contract text you could fetch. Finish "
    "with a concise, complete answer."
)

_CLAUSE_TEXT = (
    "Clause 7.2 (Limitation of Liability): each party's aggregate liability "
    "is capped at the fees paid in the twelve (12) months preceding the claim."
)


def demo_read_clause(topic: str) -> str:
    """Return the verbatim text of the contract clause covering ``topic``.

    F0-S2 placeholder capability (the F0-S1 spike tool, promoted to the
    run surface) so the run record has one real model-initiated tool to
    persist. S3+ replaces this injection with the practice area's tool
    universe.
    """
    return _CLAUSE_TEXT


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
    """Map one astream_events v2 event to ``(kind, name, summary, is_final)``.

    Returns None for events that are not persisted steps. ``is_final``
    is True only for a model turn that requested no tools — the natural
    end of the loop, whose text is the run's final answer.
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
        return AgentRunStepKind.tool_result, event.get("name"), _bounded(_text_of(content)), False

    return None


async def _drive_agent(
    agent: Any,
    *,
    run_id: uuid.UUID,
    prompt: str,
    max_steps: int,
    db: AsyncSession,
    wall_clock_seconds: float,
) -> tuple[str | None, bool]:
    """Stream the agent, persisting one step row + COMMIT per event.

    The commit-per-step is the load-bearing transaction pattern: the
    run's progress is readable mid-flight (ADR-F002 live activity), and
    a crash loses at most the in-flight step. Returns
    ``(final_answer, cap_hit)``.
    """
    seq = 0
    final_answer: str | None = None
    cap_hit = False

    stream = agent.astream_events(
        {"messages": [{"role": "user", "content": prompt}]},
        version="v2",
    )
    try:
        async with asyncio.timeout(wall_clock_seconds):
            async for event in stream:
                step = _step_from_event(event)
                if step is None:
                    continue
                kind, name, summary, is_final = step
                seq += 1
                db.add(
                    AgentRunStep(
                        run_id=run_id, seq=seq, kind=kind.value, name=name, summary=summary
                    )
                )
                await db.commit()
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


async def _finalize(
    db: AsyncSession,
    run_id: uuid.UUID,
    *,
    status: AgentRunStatus,
    final_answer: str | None = None,
    error: str | None = None,
) -> None:
    """Write the terminal state in a fresh transaction.

    Rolls back first so a failure mid-step never leaves the terminal
    UPDATE entangled with a half-written step row, then re-fetches the
    run (post-rollback instances are expired; ``Session.get`` refreshes
    them safely under asyncio).
    """
    await db.rollback()
    run = await db.get(AgentRun, run_id)
    if run is None:  # deleted underneath us (user cascade) — nothing to write
        return
    run.status = status.value
    run.final_answer = final_answer
    run.error = error
    run.finished_at = datetime.now(UTC)
    await db.commit()


async def execute_agent_run(
    run_id: uuid.UUID,
    db_session_factory: async_sessionmaker[AsyncSession],
    *,
    tools: Sequence[Callable[..., Any]],
    model: BaseChatModel | None = None,
    system_prompt: str = _SYSTEM_PROMPT,
    wall_clock_seconds: float = DEFAULT_WALL_CLOCK_SECONDS,
) -> None:
    """Execute one persisted agent run end to end.

    Opens its own DB session (the kick-off request's session closes when
    the 202 returns — same model as the playbook executor). ``tools`` is
    the injected capability set; ``model`` is an injection seam for
    tests (None → gateway chat model for the run's ``model_alias``,
    tagged with the run's ``purpose`` so the routing log separates
    agent traffic).

    Terminal writes: ``completed`` (+ ``final_answer``), ``cap_exceeded``
    (step cap), or ``failed`` (``error='timeout'`` for the wall clock;
    otherwise a bounded exception summary — never a stack trace).
    """
    async with db_session_factory() as db:
        run = await db.get(AgentRun, run_id)
        if run is None:
            logger.warning(
                "agent run vanished before execution",
                extra={"event": "agent_run_missing", "run_id": str(run_id)},
            )
            return
        # Snapshot before the first commit — commits/rollbacks may expire
        # ORM instances depending on the injected factory's configuration.
        prompt, max_steps = run.prompt, run.max_steps
        model_alias, purpose = run.model_alias, run.purpose

        try:
            chat_model = model or build_gateway_chat_model(
                model_alias=model_alias,
                purpose=purpose,
            )
            # F1 wraps every tool in the guarded_tool_call chokepoint
            # (R4 cost cap / R5 halt / R6 grants) per ADR-F002.
            agent = build_deep_agent(
                model=chat_model,
                tools=tools,
                system_prompt=system_prompt,
            )
            final_answer, cap_hit = await _drive_agent(
                agent,
                run_id=run_id,
                prompt=prompt,
                max_steps=max_steps,
                db=db,
                wall_clock_seconds=wall_clock_seconds,
            )
        except TimeoutError:
            await _finalize(db, run_id, status=AgentRunStatus.failed, error="timeout")
            return
        except Exception as exc:
            # Bounded type+message only — stack traces stay in logs.
            logger.exception(
                "agent run failed",
                extra={"event": "agent_run_failed", "run_id": str(run_id)},
            )
            await _finalize(
                db,
                run_id,
                status=AgentRunStatus.failed,
                error=_bounded(f"{type(exc).__name__}: {exc}", 500),
            )
            return

        await _finalize(
            db,
            run_id,
            status=AgentRunStatus.cap_exceeded if cap_hit else AgentRunStatus.completed,
            final_answer=final_answer,
        )
