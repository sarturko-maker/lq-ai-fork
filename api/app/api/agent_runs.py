"""Agent-run endpoints — F0-S2 (fork).

Surface (ADR-F002 "glass cockpit"; the polled capability rail renders
these settled records — ADR-F004):

* ``POST /api/v1/agents/runs`` — kick off a deep-agent run. Returns 202
  with the new :class:`~app.models.agent_run.AgentRun` row at status
  ``'running'``; the runner executes in a FastAPI ``BackgroundTask``
  (same in-process pattern as the playbook executor — ARQ migration is
  a later slice) and appends step rows as the loop progresses.
* ``GET  /api/v1/agents/runs/{run_id}`` — run detail + steps in ``seq``
  order. Clients poll this until they see a terminal status.
* ``GET  /api/v1/agents/runs`` — the caller's runs, newest first,
  paginated (total_count / limit / offset envelope).

Authorization: the router is registered under the ``_active`` dep group
in :mod:`app.api` (bearer token + must-change-password gate). All reads
are owner-scoped; another user's ``run_id`` returns 404 — never 403 —
to avoid existence disclosure (CLAUDE.md house rule).

Tool injection: ``_run_in_background`` is the composition point
(F0-S4). A matter-bound run gets the matter's document tools —
pre-wrapped in the :mod:`app.agents.guard` chokepoint (ADR-F002) — a
matter-aware system prompt, and a gateway model whose envelope carries
the matter's tier floor + privilege flag (the chat path's D1 / M2-B3
pattern). An unbound run is a blank workspace: deepagents builtins
only. F1 extends the guard wrap to the full tool universe.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.factory import build_gateway_chat_model, build_gateway_http_client
from app.agents.runner import SYSTEM_PROMPT, execute_agent_run
from app.agents.tools import MatterBinding, build_matter_tools
from app.api.dependencies import ActiveUser
from app.db.session import get_db, get_session_factory
from app.models.agent_run import AgentRun, AgentRunStep
from app.models.project import Project
from app.schemas.agent_runs import (
    AgentRunCreate,
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentRunRead,
    AgentRunStatus,
    AgentRunStepRead,
)

router = APIRouter(prefix="/agents", tags=["agent-runs"])

_LIMIT_DEFAULT = 50
_LIMIT_MAX = 200

# Interim flood brake until F1 lands R4 budgets and the arq migration:
# a caller may have at most this many runs at status='running' at once.
_MAX_CONCURRENT_RUNS_PER_USER = 3


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
) -> AgentRunRead:
    """Create an :class:`AgentRun` row and schedule the runner.

    Returns 202 immediately with the row at status ``'running'``. The
    runner appends :class:`AgentRunStep` rows (committed per step) and
    promotes the run to ``completed`` / ``failed`` / ``cap_exceeded``;
    poll ``GET /agents/runs/{run_id}`` for live progress.

    429 (``too_many_running_runs``) when the caller already has
    ``_MAX_CONCURRENT_RUNS_PER_USER`` runs at ``'running'``.

    404 when ``project_id`` names a matter the caller does not own (or
    an archived one) — never 403, no existence disclosure (F0-S4).
    """
    if body.project_id is not None:
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

    run = AgentRun(
        user_id=user.id,
        project_id=body.project_id,
        status=AgentRunStatus.running.value,
        prompt=body.prompt,
        model_alias=body.model_alias,
        max_steps=body.max_steps,
    )
    db.add(run)
    await db.commit()
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


async def _run_in_background(*, run_id: uuid.UUID) -> None:
    """Background-task entry point — the run's composition point (F0-S4).

    Loads the run's matter binding (if any), assembles the guarded
    matter tools + matter-aware prompt + gateway model, and owns the
    gateway http client's lifecycle (the key rides the client's
    headers — see :func:`app.agents.factory.build_gateway_http_client`).
    """
    session_factory = get_session_factory()

    binding: MatterBinding | None = None
    async with session_factory() as db:
        run = await db.get(AgentRun, run_id)
        if run is None:  # deleted underneath us (user cascade)
            return
        model_alias, purpose = run.model_alias, run.purpose
        if run.project_id is not None:
            project = await db.get(Project, run.project_id)
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
    system_prompt = (
        SYSTEM_PROMPT + _MATTER_PROMPT.format(name=binding.name)
        if binding is not None
        else SYSTEM_PROMPT
    )

    http_client = build_gateway_http_client()
    try:
        model = build_gateway_chat_model(
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
            system_prompt=system_prompt,
        )
    finally:
        await http_client.aclose()
