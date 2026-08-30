"""Headless agent-run start service — INTAKE-3 (ADR-F086), extracted from the api layer.

``POST /api/v1/agents/runs`` used to own the whole "create a run" mechanic inline.
INTAKE-3 needs the SAME mechanic from a place that has no request, no
``MutatingUser`` and no ``HTTPException`` vocabulary: the intake arq job launches one
bound-area-agent run per inbound email thread on the mailbox's OWNER (there is no
logged-in caller). Rather than fork a second, drifting copy of the create path, the
reusable half lives here:

* create-or-continue the :class:`~app.models.agent_run.AgentThread`,
* resolve the budget profile ONCE and MATERIALIZE it on the row (SETUP-5a, ADR-F063 —
  a later default change must never silently re-price an already-created run),
* resolve ``max_steps`` from the profile envelope unless explicitly overridden
  (Slice O, ADR-F053),
* insert the :class:`~app.models.agent_run.AgentRun`, commit,
* enqueue with the FATAL-failure contract (ADR-F009): an un-enqueued run has no
  executor, so it is settled ``failed`` immediately — never a silent zombie.

What deliberately stays in the HTTP endpoint (it is request-shaped authorization,
not run mechanics): owner checks and the 404-not-403 posture, the sandbox filter,
the concurrent-run flood brake, the thread continuability/matter-archived gates,
and the ``thread_busy`` race translation. The endpoint performs those, then calls
:func:`start_agent_run` — so its observable behaviour is unchanged.

The one non-HTTP failure this service can hit is the partial unique index
"one running run per thread": it surfaces as :class:`AgentThreadBusy` for the caller
to translate (409 in the api; a deferral in the intake worker).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.budget import resolve_envelope
from app.config import Settings, get_settings
from app.models.agent_run import AgentRun, AgentThread
from app.models.practice_area import PracticeArea
from app.models.project import Project
from app.schemas.agent_runs import AgentRunStatus, BudgetProfile
from app.workers.queue import enqueue_agent_run_job

logger = logging.getLogger(__name__)

# The AgentThread.title bound — a display string, deliberately derived from the
# caller-supplied title (or the prompt) and nothing else.
TITLE_LIMIT = 120


class AgentThreadBusy(Exception):
    """The thread already has a run at ``'running'`` (DB-enforced, race-proof).

    Raised when the partial unique index ``uq_agent_runs_thread_running`` rejects
    the insert — the check-then-insert race between two concurrent follow-ups.
    """


async def start_agent_run(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    thread_id: uuid.UUID | None = None,
    thread: AgentThread | None = None,
    prompt: str,
    budget_profile: BudgetProfile | None = None,
    max_steps: int | None = None,
    model_alias: str | None = None,
    title: str | None = None,
    settings: Settings | None = None,
    enqueue: Callable[[uuid.UUID], Awaitable[bool]] = enqueue_agent_run_job,
) -> AgentRun:
    """Create and enqueue one agent run; return the (committed, refreshed) row.

    ``thread`` is the already-loaded conversation when the caller validated and
    locked it (the api endpoint does, ``with_for_update``); otherwise ``thread_id``
    is loaded owner-scoped here, and when both are absent a NEW thread is created
    bound to ``project_id``.

    ``title`` names the conversation when a new thread is created. It defaults to
    the prompt's head — which is right for a user-typed prompt, and WRONG for a
    prompt carrying untrusted third-party content (the intake worker passes a fixed
    fork-authored title so no email text ever lands in a display field).

    ``budget_profile`` / ``max_steps`` / ``model_alias`` are the caller's explicit
    choices; ``None`` falls through the documented chains (profile: explicit → the
    bound matter's practice-area default → deployment default → balanced; steps:
    explicit → the profile envelope's ceiling).

    Raises :class:`AgentThreadBusy` when the thread already has a running run.
    """
    settings = settings or get_settings()

    if thread is None and thread_id is not None:
        thread = (
            await db.execute(
                select(AgentThread).where(
                    AgentThread.id == thread_id, AgentThread.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            raise ValueError("thread_id does not name a conversation owned by this user")

    if thread is None:
        thread = AgentThread(
            user_id=user_id,
            project_id=project_id,
            title=(title if title is not None else prompt)[:TITLE_LIMIT],
        )
        db.add(thread)
        await db.flush()  # assigns thread.id for the run row below

    # SETUP-5a (ADR-F063): resolve the budget profile ONCE, here, and persist the
    # RESOLVED value — a later default change must never silently re-price an
    # already-created run. Chain: explicit > area default (the bound matter's
    # practice area) > deployment default > balanced.
    area_default: str | None = None
    if budget_profile is None and thread.project_id is not None:
        area_default = (
            await db.execute(
                select(PracticeArea.default_budget_profile)
                .join(Project, Project.practice_area_id == PracticeArea.id)
                .where(Project.id == thread.project_id)
            )
        ).scalar_one_or_none()
    resolved_profile = (
        budget_profile
        or (BudgetProfile(area_default) if area_default else None)
        or (
            BudgetProfile(settings.run_default_budget_profile)
            if settings.run_default_budget_profile
            else None
        )
        or BudgetProfile.balanced
    )

    # Slice O (ADR-F053): resolve the cost/effort envelope. ``max_steps`` is
    # materialized on the row (the runner reads it directly); the other three brakes
    # are re-resolved from ``budget_profile`` at composition. An explicit ``max_steps``
    # overrides the profile's step ceiling (advanced).
    envelope = resolve_envelope(resolved_profile, settings)
    resolved_max_steps = max_steps if max_steps is not None else envelope.max_steps
    run = AgentRun(
        user_id=user_id,
        thread_id=thread.id,
        # Snapshot of the thread's binding (ADR-F008) — re-validated at execution
        # time by the composition point (F0-S4 rule).
        project_id=thread.project_id,
        status=AgentRunStatus.running.value,
        prompt=prompt,
        model_alias=model_alias,
        max_steps=resolved_max_steps,
        budget_profile=resolved_profile.value,
    )
    db.add(run)
    thread.last_run_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError as exc:
        # The partial unique index (one running run per thread) closes the
        # check-then-insert race between concurrent follow-ups.
        if "uq_agent_runs_thread_running" in str(exc.orig):
            raise AgentThreadBusy(str(thread.id)) from exc
        raise
    await db.refresh(run)

    # F1-S1 (ADR-F009): execution happens on the arq worker. A run that could not be
    # queued has NO executor — settle it failed right here (the sweep would catch it
    # minutes later; nobody should wait that long to learn nothing is running). The
    # settle uses THIS session (the DI seam tests drive), conditional on
    # status='running' for monotonicity.
    if not await enqueue(run.id):
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

    return run


__all__ = ["TITLE_LIMIT", "AgentThreadBusy", "start_agent_run"]
