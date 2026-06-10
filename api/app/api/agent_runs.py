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

Tool injection: F0-S2 wires the single demo ``read_clause`` capability
into the runner here, at the caller. S3+ replaces this injection with
the practice area's tool universe (and F1 wraps each tool in the
``guarded_tool_call`` chokepoint per ADR-F002) without touching the
runner seam.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runner import demo_read_clause, execute_agent_run
from app.api.dependencies import ActiveUser
from app.db.session import get_db, get_session_factory
from app.models.agent_run import AgentRun, AgentRunStep
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
    """
    run = AgentRun(
        user_id=user.id,
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


async def _run_in_background(*, run_id: uuid.UUID) -> None:
    """Background-task entry point — fresh session factory for the runner.

    F0-S2 injects the single demo ``read_clause`` capability; S3+
    injects the practice area's tool universe here (ADR-F002).
    """
    await execute_agent_run(
        run_id,
        get_session_factory(),
        tools=[demo_read_clause],
    )
