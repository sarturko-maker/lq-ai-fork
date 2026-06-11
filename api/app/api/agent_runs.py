"""Agent-run + conversation endpoints — F0-S2/F0-S5 (fork).

Surface (ADR-F002 "glass cockpit"; the polled capability rail renders
these settled records — ADR-F004):

* ``POST /api/v1/agents/runs`` — kick off a deep-agent run. Without
  ``thread_id`` a new conversation (:class:`AgentThread`) is created;
  with it, the run CONTINUES that conversation on the langgraph
  checkpointer (F0-S5, ADR-F008). Returns 202 with the new run row at
  status ``'running'``; the runner executes in a FastAPI
  ``BackgroundTask`` (same in-process pattern as the playbook executor —
  ARQ migration is a later slice) and appends step rows as the loop
  progresses.
* ``GET  /api/v1/agents/runs/{run_id}`` — run detail + steps in ``seq``
  order.
* ``GET  /api/v1/agents/runs`` — the caller's runs, newest first,
  paginated (total_count / limit / offset envelope).
* ``GET  /api/v1/agents/threads`` — the caller's conversations, newest
  activity first, each badged with its newest run's status.
* ``GET  /api/v1/agents/threads/{thread_id}`` — the whole conversation:
  runs oldest-first, each with its steps; ``continuable`` advises the
  composer. Clients poll this while a run is live.

Authorization: the router is registered under the ``_active`` dep group
in :mod:`app.api` (bearer token + must-change-password gate). All reads
are owner-scoped; another user's ``run_id``/``thread_id`` returns 404 —
never 403 — to avoid existence disclosure (CLAUDE.md house rule).

Tool injection: ``_run_in_background`` is the composition point
(F0-S4). A matter-bound run gets the matter's document tools —
pre-wrapped in the :mod:`app.agents.guard` chokepoint (ADR-F002) — a
matter-aware system prompt, and a gateway model whose envelope carries
the matter's tier floor + privilege flag (the chat path's D1 / M2-B3
pattern). An unbound run is a blank workspace: deepagents builtins
only. F1 extends the guard wrap to the full tool universe. F0-S5 adds
the checkpointer + thread id so state persists per conversation.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.checkpointer import get_agent_checkpointer, has_checkpoint
from app.agents.factory import build_gateway_chat_model, build_gateway_http_client
from app.agents.runner import SYSTEM_PROMPT, execute_agent_run, mark_run_failed
from app.agents.tools import MatterBinding, build_matter_tools
from app.api.dependencies import ActiveUser
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agent-runs"])

_LIMIT_DEFAULT = 50
_LIMIT_MAX = 200

# Interim flood brake until F1 lands R4 budgets and the arq migration:
# a caller may have at most this many runs at status='running' at once.
_MAX_CONCURRENT_RUNS_PER_USER = 3

# Thread titles are the bounded first prompt until auto-titling (F1/F2).
_TITLE_LIMIT = 120


def get_checkpointer_dep() -> BaseCheckpointSaver | None:
    """FastAPI seam for the process-global checkpointer (ADR-F008).

    Endpoints take the saver through ``Depends`` so tests substitute an
    ``InMemorySaver`` via ``app.dependency_overrides`` — the house DI
    pattern, no monkeypatching. ``None`` = persistence degraded.
    """
    return get_agent_checkpointer()


Checkpointer = Annotated[BaseCheckpointSaver | None, Depends(get_checkpointer_dep)]


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


@router.post(
    "/runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Kick off a deep-agent run.",
)
async def create_agent_run(
    body: AgentRunCreate,
    user: ActiveUser,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    checkpointer: Checkpointer,
) -> AgentRunRead:
    """Create an :class:`AgentRun` row and schedule the runner.

    Without ``thread_id``: a new conversation is created (optionally
    Matter-bound). With it: the run continues that conversation — the
    Matter binding is the THREAD's (F0-S5, ADR-F008).

    Returns 202 immediately with the row at status ``'running'``. The
    runner appends :class:`AgentRunStep` rows (committed per step) and
    promotes the run to ``completed`` / ``failed`` / ``cap_exceeded``;
    poll ``GET /agents/threads/{thread_id}`` for live progress.

    429 (``too_many_running_runs``) when the caller already has
    ``_MAX_CONCURRENT_RUNS_PER_USER`` runs at ``'running'``.

    404 when ``project_id`` names a matter — or ``thread_id`` a
    conversation — the caller does not own (or an archived matter) —
    never 403, no existence disclosure (F0-S4).

    409 ``thread_busy`` when the thread already has a running run
    (DB-enforced by a partial unique index — race-proof); 409
    ``thread_not_continuable`` when its latest run is not ``completed``
    or no checkpoint state exists (an interrupted loop can strand
    dangling tool calls in checkpoint state; pre-S5 threads never had
    state — ADR-F008). 422 when both ``thread_id`` and ``project_id``
    are set.
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
                select(AgentThread).where(
                    AgentThread.id == body.thread_id,
                    AgentThread.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            raise HTTPException(status_code=404, detail="thread not found")
        latest_status = await _latest_run_status(db, thread.id)
        if latest_status == AgentRunStatus.running.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="thread_busy")
        if latest_status != AgentRunStatus.completed.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="thread_not_continuable"
            )
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

    # The runner opens its own DB session so the per-request session can
    # close cleanly when we return 202 (playbook-executor pattern).
    background.add_task(_run_in_background, run_id=run.id)

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
    continuable = latest_status == AgentRunStatus.completed.value and await has_checkpoint(
        checkpointer, thread.id
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


# Appended to SYSTEM_PROMPT for matter-bound runs. Transparency rule:
# every agent instruction is readable in source (CLAUDE.md).
_MATTER_PROMPT = (
    '\n\nThis run is bound to the matter "{name}". Ground your answer in '
    "the matter's documents: search_documents finds passages (an empty "
    "query lists the documents); read_document fetches one document's "
    "full text. Cite the document name and page for anything you take "
    "from them, and say so plainly when the documents don't answer the "
    "question."
)


def _system_prompt_for(binding: MatterBinding | None) -> str:
    """The run's full system prompt — base + the matter addendum."""
    if binding is None:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + _MATTER_PROMPT.format(name=binding.name)


async def _run_in_background(
    *,
    run_id: uuid.UUID,
    model_builder: Callable[..., BaseChatModel] = build_gateway_chat_model,
    session_factory_provider: Callable[[], async_sessionmaker[AsyncSession]] = get_session_factory,
    checkpointer_provider: Callable[[], BaseCheckpointSaver | None] = get_agent_checkpointer,
) -> None:
    """Background-task entry point — the run's composition point (F0-S4).

    Loads the run's matter binding — the project is RE-validated against
    the run's owner and ``archived_at`` here, not just at the 202
    (binding facts must hold at execution time) — then assembles the
    guarded matter tools + matter-aware prompt + gateway model, and owns
    the gateway http client's lifecycle (the key rides the client's
    headers — see :func:`app.agents.factory.build_gateway_http_client`).
    ``model_builder`` / ``session_factory_provider`` /
    ``checkpointer_provider`` are injection seams: tests drive the REAL
    composition with a scripted model, the test DB, and an in-memory
    checkpointer — no gateway, no monkeypatching.

    F0-S5 (ADR-F008): the run executes against its conversation's
    checkpoint lineage (``thread_id``), so capabilities are REBOUND per
    run from the thread's current binding while the agent state
    persists — resume-on-existing per ADR-F004. A ``None`` checkpointer
    (init failed) degrades to the F0-S4 single-shot behavior.

    Any failure here finalizes the run as ``'failed'`` — a run must
    never strand at ``'running'``: the flood brake counts those forever
    and three of them lock the user out (F0-S4 review).
    """
    session_factory = session_factory_provider()
    try:
        binding: MatterBinding | None = None
        async with session_factory() as db:
            run = await db.get(AgentRun, run_id)
            if run is None:  # deleted underneath us (user cascade)
                return
            model_alias, purpose = run.model_alias, run.purpose
            thread_id = run.thread_id
            if run.project_id is not None:
                project = (
                    await db.execute(
                        select(Project).where(
                            Project.id == run.project_id,
                            Project.owner_id == run.user_id,
                            Project.archived_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                if project is not None:
                    binding = MatterBinding(
                        project_id=project.id,
                        user_id=run.user_id,
                        name=project.name,
                        privileged=project.privileged,
                        minimum_inference_tier=project.minimum_inference_tier,
                    )

        tools = (
            build_matter_tools(session_factory, run_id=run_id, binding=binding)
            if binding is not None
            else []
        )

        http_client = build_gateway_http_client()
        try:
            model = model_builder(
                model_alias=model_alias,
                purpose=purpose,
                http_async_client=http_client,
                project_minimum_inference_tier=(
                    binding.minimum_inference_tier if binding is not None else None
                ),
                privileged=binding.privileged if binding is not None else False,
            )
            await execute_agent_run(
                run_id,
                session_factory,
                tools=tools,
                model=model,
                system_prompt=_system_prompt_for(binding),
                checkpointer=checkpointer_provider(),
                thread_id=thread_id,
            )
        finally:
            await http_client.aclose()
    except Exception as exc:
        logger.exception(
            "agent run composition failed",
            extra={"event": "agent_run_composition_failed", "run_id": str(run_id)},
        )
        # mark_run_failed never overwrites a settled run, so a cleanup
        # error after a successful execution cannot flip 'completed'.
        await mark_run_failed(session_factory, run_id, error=f"{type(exc).__name__}: {exc}")
