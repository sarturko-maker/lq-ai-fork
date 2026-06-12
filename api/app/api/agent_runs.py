"""Agent-run + conversation endpoints — F0-S2/F0-S5 (fork).

Surface (ADR-F002 "glass cockpit"; the polled capability rail renders
these settled records — ADR-F004):

* ``POST /api/v1/agents/runs`` — kick off a deep-agent run. Without
  ``thread_id`` a new conversation (:class:`AgentThread`) is created;
  with it, the run CONTINUES that conversation on the langgraph
  checkpointer (F0-S5, ADR-F008). Returns 202 with the new run row at
  status ``'running'``; execution happens on the arq worker (F1-S1,
  ADR-F009 — at-most-once, lease-fenced, swept when orphaned), which
  appends step rows as the loop progresses. A run that cannot be
  enqueued is settled ``failed`` before the 202 returns — never a
  silent zombie.
* ``POST /api/v1/agents/runs/{run_id}/cancel`` — settle a running run
  as ``cancelled`` (first-writer-wins; idempotent on settled runs),
  then best-effort-abort the worker job (F1-S1).
* ``DELETE /api/v1/agents/threads/{thread_id}`` — delete one
  conversation: runs/steps cascade, the checkpoint lineage is deleted
  through the saver's own API (F1-S1 retention; the daily GC cron is
  the backstop).
* ``GET  /api/v1/agents/runs/{run_id}`` — run detail + steps in ``seq``
  order.
* ``GET  /api/v1/agents/runs`` — the caller's runs, newest first,
  paginated (total_count / limit / offset envelope).
* ``GET  /api/v1/agents/threads`` — the caller's conversations, newest
  activity first, each badged with its newest run's status.
* ``GET  /api/v1/agents/threads/{thread_id}`` — the whole conversation:
  runs oldest-first, each with its steps; ``continuable`` advises the
  composer. Clients poll this while a run is live.
* ``GET  /api/v1/agents/runs/{run_id}/stream`` — SSE v2 (F0-S7): the
  run as an AI SDK UI Message Stream v1 (ADR-F006 wire spec). Settled
  step rows ride as ``data-step`` parts (id = row id, reconciling),
  model deltas as reasoning blocks; the polled thread endpoint stays
  the fallback and the durable truth (ADR-F004).

Authorization: the router is registered under the ``_active`` dep group
in :mod:`app.api` (bearer token + must-change-password gate). All reads
are owner-scoped; another user's ``run_id``/``thread_id`` returns 404 —
never 403 — to avoid existence disclosure (CLAUDE.md house rule).

Tool injection: :func:`app.agents.composition.compose_and_execute_run`
is the composition point (F0-S4; moved out of this module in F1-S1 so
the arq worker owns execution). A matter-bound run gets the matter's
document tools — pre-wrapped in the :mod:`app.agents.guard` chokepoint
(ADR-F002) — a matter-aware system prompt, and a gateway model whose
envelope carries the matter's tier floor + privilege flag (the chat
path's D1 / M2-B3 pattern). An unbound run is a blank workspace:
deepagents builtins only. F1 extends the guard wrap to the full tool
universe. F0-S5 adds the checkpointer + thread id so state persists
per conversation.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import CursorResult, func, select, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.checkpointer import get_agent_checkpointer, has_checkpoint
from app.agents.stream import (
    CHANNEL_CLOSED,
    SSE_DONE,
    SSE_PING,
    UI_MESSAGE_STREAM_HEADERS,
    RunStreamBroker,
    encode_sse,
    step_part,
    step_payload,
    terminal_parts,
)
from app.api.dependencies import ActiveUser
from app.audit import audit_action
from app.config import get_settings
from app.db.session import get_db, get_session_factory
from app.models.agent_run import AgentRun, AgentRunStep, AgentThread
from app.models.project import Project
from app.schemas.agent_runs import (
    AgentRunCreate,
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentRunRead,
    AgentRunStatus,
    AgentRunStepRead,
    AgentRunWithSteps,
    AgentThreadDetailResponse,
    AgentThreadListResponse,
    AgentThreadRead,
)
from app.workers.queue import abort_agent_run_job, enqueue_agent_run_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agent-runs"])

_LIMIT_DEFAULT = 50
_LIMIT_MAX = 200

# Interim flood brake until F1 lands R4 budgets and the arq migration:
# a caller may have at most this many runs at status='running' at once.
_MAX_CONCURRENT_RUNS_PER_USER = 3

# Thread titles are the bounded first prompt until auto-titling (F1/F2).
_TITLE_LIMIT = 120

# Follow-up admission set (F1-S1, ADR-F009): any settled run admits the
# next turn — thread repair fixes dangling tool calls; checkpoint state
# is still required (has_checkpoint) for honest continuation.
_TERMINAL_STATUSES = frozenset(
    s.value
    for s in (
        AgentRunStatus.completed,
        AgentRunStatus.failed,
        AgentRunStatus.cancelled,
        AgentRunStatus.cap_exceeded,
    )
)


def get_checkpointer_dep() -> BaseCheckpointSaver | None:
    """FastAPI seam for the process-global checkpointer (ADR-F008).

    Endpoints take the saver through ``Depends`` so tests substitute an
    ``InMemorySaver`` via ``app.dependency_overrides`` — the house DI
    pattern, no monkeypatching. ``None`` = persistence degraded.
    """
    return get_agent_checkpointer()


Checkpointer = Annotated[BaseCheckpointSaver | None, Depends(get_checkpointer_dep)]


def get_stream_broker(request: Request) -> RunStreamBroker:
    """FastAPI seam for the process-local run-stream broker (F0-S7).

    The lifespan constructs it on ``app.state`` (the composition root);
    the lazy fallback here covers bare test apps that skip the lifespan
    — still one broker per app, never per request. Tests substitute via
    ``app.dependency_overrides`` as usual.
    """
    broker = getattr(request.app.state, "agent_stream_broker", None)
    if broker is None:
        broker = RunStreamBroker()
        request.app.state.agent_stream_broker = broker
    return broker


StreamBroker = Annotated[RunStreamBroker, Depends(get_stream_broker)]


def get_stream_session_factory() -> async_sessionmaker[AsyncSession]:
    """Seam for the stream generator's short-lived read sessions.

    The generator outlives the request-scoped ``get_db`` session (closed
    before streaming starts — see :func:`stream_agent_run`), so it reads
    through this factory instead; tests override it to bind the
    generator to the migrated test DB (the house DI pattern).
    """
    return get_session_factory()


StreamSessionFactory = Annotated[
    async_sessionmaker[AsyncSession], Depends(get_stream_session_factory)
]

# DB-tail cadence for the stream's fallback path (matches the legacy
# client poll), and how long a silent stream goes between SSE comments.
_STREAM_DB_POLL_SECONDS = 2.0
_STREAM_HEARTBEAT_SECONDS = 15.0

# Stream-side orphan belt (F1-S1 review fix): the worker-side sweep is
# the authority — these cutoffs only close streams when the SWEEP
# ITSELF is dead (worker down entirely), so they mirror the sweep's two
# rules with generous slack on top, reading the lease columns. A run's
# started_at is now ENQUEUE time, not execution start — a wall-age
# cutoff would false-error queue-delayed runs. The web poller's
# STALE_RUNNING_AFTER_MS stays a coarser client-side approximation.
_STREAM_SWEEP_SLACK_SECONDS = 180.0


def _run_is_orphaned(run: AgentRun, db_now: datetime) -> bool:
    """True for a 'running' row that the dead-sweep belt should close.

    Compared against the DB clock (``db_now`` selected alongside the
    row — one clock authority, matching the lease module).
    """
    if run.status != AgentRunStatus.running.value:
        return False
    settings = get_settings()
    if run.claimed_at is not None:
        reference = run.heartbeat_at or run.claimed_at
        threshold = settings.agent_run_orphan_after_seconds + _STREAM_SWEEP_SLACK_SECONDS
    else:
        reference = run.started_at
        threshold = settings.agent_run_claim_grace_seconds + _STREAM_SWEEP_SLACK_SECONDS
    return (db_now - reference).total_seconds() > threshold


async def _latest_run_status(db: AsyncSession, thread_id: uuid.UUID) -> str | None:
    """The newest run's status for one thread (None = no runs)."""
    return (
        await db.execute(
            select(AgentRun.status)
            .where(AgentRun.thread_id == thread_id)
            .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _thread_matter_active(db: AsyncSession, thread: AgentThread) -> bool:
    """True when the thread is unbound OR its Matter is still active.

    A bound conversation whose Matter has been archived must not take
    follow-ups: execution-time re-validation would silently drop the
    binding (no document tools) while the UI still presents the matter —
    a dishonest grounding claim (F0-S5 review). Owner re-asserted out of
    habit; the thread row was already owner-scoped.
    """
    if thread.project_id is None:
        return True
    return (
        await db.execute(
            select(Project.id).where(
                Project.id == thread.project_id,
                Project.owner_id == thread.user_id,
                Project.archived_at.is_(None),
            )
        )
    ).scalar_one_or_none() is not None


@router.post(
    "/runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Kick off a deep-agent run.",
)
async def create_agent_run(
    body: AgentRunCreate,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    checkpointer: Checkpointer,
) -> AgentRunRead:
    """Create an :class:`AgentRun` row and enqueue it on the arq worker.

    Without ``thread_id``: a new conversation is created (optionally
    Matter-bound). With it: the run continues that conversation — the
    Matter binding is the THREAD's (F0-S5, ADR-F008).

    Returns 202 immediately with the row at status ``'running'``. The
    worker (F1-S1, ADR-F009) appends :class:`AgentRunStep` rows
    (committed per step) and promotes the run to ``completed`` /
    ``failed`` / ``cancelled`` / ``cap_exceeded``; poll
    ``GET /agents/threads/{thread_id}`` for live progress. An enqueue
    failure settles the run ``failed`` before returning — the 202 then
    carries the settled row, never a zombie.

    429 (``too_many_running_runs``) when the caller already has
    ``_MAX_CONCURRENT_RUNS_PER_USER`` runs at ``'running'``.

    404 when ``project_id`` names a matter — or ``thread_id`` a
    conversation — the caller does not own (or an archived matter) —
    never 403, no existence disclosure (F0-S4).

    409 ``thread_busy`` when the thread already has a running run
    (DB-enforced by a partial unique index — race-proof); 409
    ``thread_not_continuable`` when the thread has no settled run or no
    checkpoint state exists (pre-S5 threads never had state; a thread
    whose FIRST run failed before any checkpoint has nothing to
    honestly continue — ADR-F008). Since F1-S1 ANY terminal latest
    status admits a follow-up: dangling tool calls left by a failed/
    cancelled run are repaired before the next invoke (ADR-F009). 422
    when both ``thread_id`` and ``project_id`` are set.
    """
    thread: AgentThread | None = None
    if body.thread_id is not None:
        if body.project_id is not None:
            raise HTTPException(
                status_code=422,
                detail="project_id is fixed by the thread; omit it on follow-ups",
            )
        thread = (
            await db.execute(
                select(AgentThread)
                .where(
                    AgentThread.id == body.thread_id,
                    AgentThread.user_id == user.id,
                )
                # Serialize follow-up admission per thread: a concurrent
                # follow-up that committed-and-failed inside our check
                # window would otherwise slip past the status read (the
                # partial unique index only blocks two RUNNING rows —
                # F0-S5 review).
                .with_for_update()
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status_code=404, detail="thread not found")
        latest_status = await _latest_run_status(db, thread.id)
        if latest_status == AgentRunStatus.running.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="thread_busy")
        if latest_status not in _TERMINAL_STATUSES:
            # No run ever settled on this thread (None) — nothing to
            # honestly continue. Any TERMINAL status admits a follow-up
            # since F1-S1: the runner repairs dangling tool calls left
            # by a failed/cancelled/capped run before invoking
            # (ADR-F009 thread repair).
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="thread_not_continuable"
            )
        if not await _thread_matter_active(db, thread):
            # The conversation's Matter was archived since the thread was
            # created. Accepting the follow-up would silently degrade the
            # run to a blank workspace while the UI still presents the
            # matter binding — refuse honestly instead (F0-S5 review; the
            # new-thread path 404s archived matters for the same reason).
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="matter_archived")
        if not await has_checkpoint(checkpointer, thread.id):
            # Honest refusal: without persisted state the agent would not
            # remember the conversation it claims to continue (pre-S5
            # backfill, or a run executed while persistence was degraded).
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="thread_not_continuable"
            )
    elif body.project_id is not None:
        visible_project_id = (
            await db.execute(
                select(Project.id).where(
                    Project.id == body.project_id,
                    Project.owner_id == user.id,
                    Project.archived_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if visible_project_id is None:
            raise HTTPException(status_code=404, detail="project not found")

    # Flood brake — count via idx_agent_runs_user_started's user_id prefix.
    running_count: int = (
        await db.execute(
            select(func.count())
            .select_from(AgentRun)
            .where(
                AgentRun.user_id == user.id,
                AgentRun.status == AgentRunStatus.running.value,
            )
        )
    ).scalar_one()
    if running_count >= _MAX_CONCURRENT_RUNS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too_many_running_runs",
        )

    if thread is None:
        thread = AgentThread(
            user_id=user.id,
            project_id=body.project_id,
            title=body.prompt[:_TITLE_LIMIT],
        )
        db.add(thread)
        await db.flush()  # assigns thread.id for the run row below

    run = AgentRun(
        user_id=user.id,
        thread_id=thread.id,
        # Snapshot of the thread's binding (ADR-F008) — re-validated at
        # execution time by the composition point (F0-S4 rule).
        project_id=thread.project_id,
        status=AgentRunStatus.running.value,
        prompt=body.prompt,
        model_alias=body.model_alias,
        max_steps=body.max_steps,
    )
    db.add(run)
    thread.last_run_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError as exc:
        # The partial unique index (one running run per thread) closes
        # the check-then-insert race between concurrent follow-ups.
        if "uq_agent_runs_thread_running" in str(exc.orig):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="thread_busy") from exc
        raise
    await db.refresh(run)

    # F1-S1 (ADR-F009): execution happens on the arq worker. A run that
    # could not be queued has NO executor — settle it failed right here
    # (the sweep would catch it minutes later; the user shouldn't wait
    # that long to learn nothing is running). The settle uses THIS
    # request's session (the DI seam tests drive), conditional on
    # status='running' for monotonicity.
    if not await enqueue_agent_run_job(run.id):
        await db.execute(
            sa_update(AgentRun)
            .where(AgentRun.id == run.id, AgentRun.status == AgentRunStatus.running.value)
            .values(
                status=AgentRunStatus.failed.value,
                error="enqueue failed: no worker will execute this run",
                finished_at=func.now(),
            )
        )
        await db.commit()
        await db.refresh(run)

    return AgentRunRead.model_validate(run)


@router.get(
    "/runs",
    response_model=AgentRunListResponse,
    summary="List the calling user's agent runs (newest first, paginated).",
)
async def list_agent_runs(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = _LIMIT_DEFAULT,
    offset: int = 0,
) -> AgentRunListResponse:
    """GET /api/v1/agents/runs

    Returns the caller's runs ordered by ``started_at DESC`` (the
    ``idx_agent_runs_user_started`` index). ``limit`` is clamped to
    [1, 200]; ``offset`` to [0, ∞).
    """
    limit = max(1, min(limit, _LIMIT_MAX))
    offset = max(0, offset)

    count_stmt = select(func.count()).select_from(AgentRun).where(AgentRun.user_id == user.id)
    total_count: int = (await db.execute(count_stmt)).scalar_one()

    rows_stmt = (
        select(AgentRun)
        .where(AgentRun.user_id == user.id)
        .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(rows_stmt)).scalars().all()

    return AgentRunListResponse(
        runs=[AgentRunRead.model_validate(r) for r in rows],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunDetailResponse,
    summary="Fetch one agent run with its steps in order.",
)
async def get_agent_run(
    run_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentRunDetailResponse:
    """GET /api/v1/agents/runs/{run_id}

    Returns the run plus its steps ordered by ``seq`` — the settled
    records the capability rail renders (ADR-F004). Another user's
    ``run_id`` returns 404 (not 403) to avoid existence disclosure.
    """
    run = await db.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="run not found")

    steps_stmt = (
        select(AgentRunStep).where(AgentRunStep.run_id == run.id).order_by(AgentRunStep.seq.asc())
    )
    steps = (await db.execute(steps_stmt)).scalars().all()

    return AgentRunDetailResponse(
        run=AgentRunRead.model_validate(run),
        steps=[AgentRunStepRead.model_validate(s) for s in steps],
    )


async def _read_stream_state(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    *,
    after_seq: int,
) -> tuple[AgentRun | None, list[AgentRunStep], datetime]:
    """Run row + settled steps beyond ``after_seq`` + the DB clock.

    The stream generator opens a FRESH short-lived session per read so a
    long-lived stream never pins a pool connection (the same posture as
    the runner's per-step sessions). ``db_now`` rides along so the
    orphan-belt comparison stays on the database clock (F1-S1).
    """
    async with session_factory() as db:
        db_now: datetime = (await db.execute(select(func.now()))).scalar_one()
        run = await db.get(AgentRun, run_id)
        if run is None:
            return None, [], db_now
        steps = (
            (
                await db.execute(
                    select(AgentRunStep)
                    .where(AgentRunStep.run_id == run_id, AgentRunStep.seq > after_seq)
                    .order_by(AgentRunStep.seq.asc())
                )
            )
            .scalars()
            .all()
        )
        return run, list(steps), db_now


def _row_part(step: AgentRunStep) -> dict[str, object]:
    return step_part(
        step_payload(
            step_id=step.id,
            run_id=step.run_id,
            seq=step.seq,
            kind=step.kind,
            name=step.name,
            summary=step.summary,
            parent_step_id=step.parent_step_id,
            created_at=step.created_at,
        )
    )


async def _stream_run_events(
    run_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    broker: RunStreamBroker,
) -> AsyncIterator[str]:
    """The SSE v2 frame source for one run (AI SDK UI Message Stream v1).

    Two part sources, one wire, dedup by construction (same-id data
    parts reconcile client-side — the spec's replacement rule):

    1. settled rows — replayed up front, then DB-tailed whenever the
       live queue is silent for ``_STREAM_DB_POLL_SECONDS``. This path
       alone is a complete (animation-free) stream: it is what a
       subscriber gets after an api restart or once execution moves out
       of process (F1 arq migration).
    2. the broker's live parts — reasoning deltas, tool frames, step
       mirrors — published by the runner in this process.

    Every exit ends the message before ``[DONE]``: the terminal parts
    (built from the SETTLED run row, ADR-F004) when the run settled, a
    bare ``finish`` when there is nothing settled to report (run row
    vanished under a user-cascade delete), or an ``error`` + ``finish``
    when the run is ORPHANED at 'running' (process died; no recovery
    sweep until F1 arq) — the stream must never heartbeat a dead run
    open forever, and the client's polling path applies the same 330s
    cutoff.
    """
    yield encode_sse({"type": "start", "messageId": str(run_id)})
    queue = broker.subscribe(run_id)
    try:
        max_seq = 0
        run, steps, db_now = await _read_stream_state(session_factory, run_id, after_seq=0)
        for row in steps:
            max_seq = max(max_seq, row.seq)
            yield encode_sse(_row_part(row))
        if run is None:  # deleted underneath us (user cascade)
            yield encode_sse({"type": "finish"})
            yield SSE_DONE
            return
        if run.status != AgentRunStatus.running.value:
            for part in terminal_parts(
                run_id=run_id,
                status=run.status,
                final_answer=run.final_answer,
                error=run.error,
            ):
                yield encode_sse(part)
            yield SSE_DONE
            return
        if _run_is_orphaned(run, db_now):
            yield encode_sse(
                {"type": "error", "errorText": "run never settled (orphaned at 'running')"}
            )
            yield encode_sse({"type": "finish"})
            yield SSE_DONE
            return

        idle_seconds = 0.0
        while True:
            try:
                part = await asyncio.wait_for(queue.get(), timeout=_STREAM_DB_POLL_SECONDS)
            except TimeoutError:
                # Live queue silent — tail the settled rows (fallback
                # path; emits nothing the client hasn't reconciled).
                run, steps, db_now = await _read_stream_state(
                    session_factory, run_id, after_seq=max_seq
                )
                for row in steps:
                    max_seq = max(max_seq, row.seq)
                    yield encode_sse(_row_part(row))
                if run is None:
                    yield encode_sse({"type": "finish"})
                    yield SSE_DONE
                    return
                if run.status != AgentRunStatus.running.value:
                    for tpart in terminal_parts(
                        run_id=run_id,
                        status=run.status,
                        final_answer=run.final_answer,
                        error=run.error,
                    ):
                        yield encode_sse(tpart)
                    yield SSE_DONE
                    return
                if _run_is_orphaned(run, db_now):
                    yield encode_sse(
                        {
                            "type": "error",
                            "errorText": "run never settled (orphaned at 'running')",
                        }
                    )
                    yield encode_sse({"type": "finish"})
                    yield SSE_DONE
                    return
                if steps:
                    idle_seconds = 0.0
                else:
                    idle_seconds += _STREAM_DB_POLL_SECONDS
                    if idle_seconds >= _STREAM_HEARTBEAT_SECONDS:
                        idle_seconds = 0.0
                        yield SSE_PING  # SSE comment — keeps proxies awake
                continue

            idle_seconds = 0.0
            if part is CHANNEL_CLOSED:
                # Finish raced past us (or the channel was evicted):
                # flush the rows, end on the settled run state.
                run, steps, db_now = await _read_stream_state(
                    session_factory, run_id, after_seq=max_seq
                )
                for row in steps:
                    yield encode_sse(_row_part(row))
                if run is not None and run.status != AgentRunStatus.running.value:
                    for tpart in terminal_parts(
                        run_id=run_id,
                        status=run.status,
                        final_answer=run.final_answer,
                        error=run.error,
                    ):
                        yield encode_sse(tpart)
                else:
                    yield encode_sse({"type": "finish"})
                yield SSE_DONE
                return
            if part.get("type") == "start":
                continue  # the generator already opened the message
            if part.get("type") == "data-step":
                seq_value = (part.get("data") or {}).get("seq")
                if isinstance(seq_value, int):
                    max_seq = max(max_seq, seq_value)
            yield encode_sse(part)
            if part.get("type") == "finish":
                yield SSE_DONE
                return
    finally:
        broker.unsubscribe(run_id, queue)


@router.get(
    "/runs/{run_id}/stream",
    summary="Stream one agent run as an AI SDK UI Message Stream v1 (SSE).",
)
async def stream_agent_run(
    run_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    broker: StreamBroker,
    session_factory: StreamSessionFactory,
) -> StreamingResponse:
    """GET /api/v1/agents/runs/{run_id}/stream — SSE v2 (F0-S7).

    Emits the ADR-F006 wire spec for one run: replayed ``data-step``
    parts for already-settled rows, then live parts while the run
    executes, ending with the terminal parts + ``[DONE]``. A terminal
    run streams its full replay and closes — the endpoint is idempotent
    and safe to re-open (parts reconcile by id).

    Another user's ``run_id`` returns 404 (not 403) — no existence
    disclosure. The request-scoped session is explicitly closed before
    streaming starts (FastAPI tears yield-deps down only after the
    response body completes — a 300s stream must not pin a pool
    connection); the generator reads through short-lived sessions.
    """
    run = await db.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="run not found")
    await db.close()

    return StreamingResponse(
        _stream_run_events(run_id, session_factory, broker),
        media_type="text/event-stream",
        headers=UI_MESSAGE_STREAM_HEADERS,
    )


@router.get(
    "/threads",
    response_model=AgentThreadListResponse,
    summary="List the calling user's conversations (newest activity first).",
)
async def list_agent_threads(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = _LIMIT_DEFAULT,
    offset: int = 0,
) -> AgentThreadListResponse:
    """GET /api/v1/agents/threads

    Conversation list for the agents page (ADR-F008). Each thread is
    badged with its NEWEST run's status (``last_run_status``) so the UI
    can show working/completed/failed without N+1 round trips.
    """
    limit = max(1, min(limit, _LIMIT_MAX))
    offset = max(0, offset)

    count_stmt = select(func.count()).select_from(AgentThread).where(AgentThread.user_id == user.id)
    total_count: int = (await db.execute(count_stmt)).scalar_one()

    rows = (
        (
            await db.execute(
                select(AgentThread)
                .where(AgentThread.user_id == user.id)
                .order_by(AgentThread.last_run_at.desc(), AgentThread.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    # Newest run's status per listed thread, one query: DISTINCT ON the
    # thread, newest first (Postgres-only, like the FTS in agents/tools).
    statuses: dict[uuid.UUID, str] = {}
    if rows:
        status_rows = await db.execute(
            select(AgentRun.thread_id, AgentRun.status)
            .where(AgentRun.thread_id.in_([t.id for t in rows]))
            .distinct(AgentRun.thread_id)
            .order_by(AgentRun.thread_id, AgentRun.started_at.desc(), AgentRun.id.desc())
        )
        statuses = dict(status_rows.tuples().all())

    threads = []
    for t in rows:
        read = AgentThreadRead.model_validate(t)
        read.last_run_status = AgentRunStatus(statuses[t.id]) if t.id in statuses else None
        threads.append(read)

    return AgentThreadListResponse(
        threads=threads, total_count=total_count, limit=limit, offset=offset
    )


@router.get(
    "/threads/{thread_id}",
    response_model=AgentThreadDetailResponse,
    summary="Fetch one conversation: its runs (oldest first) with their steps.",
)
async def get_agent_thread(
    thread_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    checkpointer: Checkpointer,
) -> AgentThreadDetailResponse:
    """GET /api/v1/agents/threads/{thread_id}

    The whole conversation — settled rows only (ADR-F004); the UI polls
    this while a run is live. Another user's ``thread_id`` returns 404
    (not 403) to avoid existence disclosure. ``continuable`` mirrors the
    POST endpoint's follow-up rules (advisory; POST re-checks).
    """
    thread = (
        await db.execute(
            select(AgentThread).where(AgentThread.id == thread_id, AgentThread.user_id == user.id)
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")

    runs = (
        (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.thread_id == thread.id)
                .order_by(AgentRun.started_at.asc(), AgentRun.id.asc())
            )
        )
        .scalars()
        .all()
    )

    steps_by_run: dict[uuid.UUID, list[AgentRunStep]] = {r.id: [] for r in runs}
    if runs:
        step_rows = (
            (
                await db.execute(
                    select(AgentRunStep)
                    .where(AgentRunStep.run_id.in_(list(steps_by_run)))
                    .order_by(AgentRunStep.seq.asc())
                )
            )
            .scalars()
            .all()
        )
        for s in step_rows:
            steps_by_run[s.run_id].append(s)

    latest_status = runs[-1].status if runs else None
    continuable = (
        latest_status in _TERMINAL_STATUSES
        # Mirrors the POST follow-up rules exactly — incl. an archived
        # Matter (409 matter_archived there; greyed composer here).
        # Any terminal status since F1-S1 (thread repair, ADR-F009).
        and await _thread_matter_active(db, thread)
        and await has_checkpoint(checkpointer, thread.id)
    )

    thread_read = AgentThreadRead.model_validate(thread)
    thread_read.last_run_status = AgentRunStatus(latest_status) if latest_status else None

    return AgentThreadDetailResponse(
        thread=thread_read,
        runs=[
            AgentRunWithSteps(
                run=AgentRunRead.model_validate(r),
                steps=[AgentRunStepRead.model_validate(s) for s in steps_by_run[r.id]],
            )
            for r in runs
        ],
        continuable=continuable,
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=AgentRunRead,
    summary="Cancel a running agent run (idempotent).",
)
async def cancel_agent_run(
    run_id: uuid.UUID,
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentRunRead:
    """POST /api/v1/agents/runs/{run_id}/cancel — F1-S1 (ADR-F009).

    Settle-first: the row is flipped ``running → cancelled`` by one
    conditional UPDATE (first-writer-wins — a run that completed in the
    race keeps its real terminal state), THEN the worker is signalled:
    arq ``Job.abort`` as the impatient path, and the worker's own fenced
    writes stop landing within one heartbeat anyway. Cancelling an
    already-settled run is an explicit no-op returning the current row
    (the finish-vs-cancel race is common and not an error).

    Another user's ``run_id`` returns 404 (not 403) — no existence
    disclosure. One audit row per actual cancellation; none for the
    idempotent no-op.
    """
    run = await db.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="run not found")

    if run.status == AgentRunStatus.running.value:
        result: CursorResult[Any] = await db.execute(  # type: ignore[assignment]
            sa_update(AgentRun)
            .where(AgentRun.id == run.id, AgentRun.status == AgentRunStatus.running.value)
            .values(
                status=AgentRunStatus.cancelled.value,
                finished_at=func.now(),
            )
        )
        if result.rowcount == 1:
            await audit_action(
                db,
                user_id=user.id,
                action="agent_run.cancel",
                resource_type="agent_run",
                resource_id=str(run.id),
                project_id=run.project_id,
                request=request,
                details={"from_status": AgentRunStatus.running.value},
            )
        await db.commit()
        await db.refresh(run)
        if run.status == AgentRunStatus.cancelled.value:
            # Best-effort, AFTER the settle is durable: a queued job
            # aborts before starting; a running one gets CancelledError.
            await abort_agent_run_job(run.id)

    return AgentRunRead.model_validate(run)


@router.delete(
    "/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # The M3-C2 pattern: without response_class=Response, FastAPI's
    # default JSONResponse fails the import-time "204 must not have
    # body" assertion (see admin_intake_bridges).
    response_class=Response,
    summary="Delete one conversation, its runs, and its checkpoint state.",
)
async def delete_agent_thread(
    thread_id: uuid.UUID,
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    checkpointer: Checkpointer,
) -> Response:
    """DELETE /api/v1/agents/threads/{thread_id} — F1-S1 retention.

    Runs/steps cascade from the thread row; the langgraph checkpoint
    lineage (library-owned tables, no FK to ours) is deleted through
    the saver's own ``adelete_thread`` AFTER the row delete commits —
    best-effort, because the daily GC cron removes any lineage whose
    thread row is gone (the durable backstop).

    409 ``thread_busy`` while a run is live (cancel it first — deleting
    the transcript under a writing runner would strand its fenced
    writes pointlessly). Another user's ``thread_id`` returns 404 (not
    403) — no existence disclosure.
    """
    thread = (
        await db.execute(
            select(AgentThread)
            .where(AgentThread.id == thread_id, AgentThread.user_id == user.id)
            # Serialize against follow-up admission (which takes the same
            # lock): without it a concurrently admitted RUNNING run could
            # be cascade-deleted mid-execution (review fix) — the
            # thread_busy check below must be race-proof, not advisory.
            .with_for_update()
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="thread not found")
    if await _latest_run_status(db, thread.id) == AgentRunStatus.running.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="thread_busy")

    run_count: int = (
        await db.execute(
            select(func.count()).select_from(AgentRun).where(AgentRun.thread_id == thread.id)
        )
    ).scalar_one()
    await db.delete(thread)
    await audit_action(
        db,
        user_id=user.id,
        action="agent_thread.delete",
        resource_type="agent_thread",
        resource_id=str(thread_id),
        project_id=thread.project_id,
        request=request,
        details={"runs_deleted": run_count},
    )
    await db.commit()

    if checkpointer is not None:
        try:
            await checkpointer.adelete_thread(str(thread_id))
        except Exception:
            logger.exception(
                "thread checkpoint delete failed (daily GC will catch it)",
                extra={"event": "thread_checkpoint_delete_failed", "thread_id": str(thread_id)},
            )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
