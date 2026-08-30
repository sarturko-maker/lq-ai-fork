"""ARQ worker function for the email-intake processing pipeline — INTAKE-3 (ADR-F086).

``POST /internal/intake/emails`` (``app.api.intake_emails``) enqueues this job (via
:func:`app.workers.queue.enqueue_intake_email_job`) onto the shared ``arq:m3a6``
queue after landing an inbound envelope: idempotency check, thread upsert, eager
matter creation, attachment ingest, and the ``intake_messages`` row
(content included, migration 0099) are all committed by the time this job runs.

**The payload is ONLY the thread id.** Everything else — which message triggered
this, the mailbox binding, the project, the attachment filenames — is re-derived
from the database here, so the job is replay-safe and no email content ever sits in
Redis (``queue.py``'s standing note).

What this does (Ruling 1: ONE deep-agent run per inbound email thread, on the bound
practice-area agent):

1. Load the thread + its mailbox + its matter, and the OLDEST inbound message that no
   run has claimed (``run_id IS NULL``). None ⇒ honest no-op.

   **Deliberate deviation from "the latest message" (S6):** oldest-first means a burst
   of three emails is worked in the order they were sent, and none is skipped. The
   cost — the newest message waits behind the older ones — is covered by the
   re-enqueue at the run job's exit
   (:func:`app.agents.intake_tools.requeue_pending_intake_message`), which walks the
   backlog one run at a time on the SAME conversation.
2. If that thread's agent conversation already has a run in flight, DEFER: leave the
   message unclaimed for the next job rather than running the thread twice.
3. Mark the thread ``processing``, build the intake prompt
   (:mod:`app.agents.intake_prompt` — fork instruction + the email fenced as
   untrusted DATA), and start a run through the shared headless service
   (:func:`app.agents.run_service.start_agent_run`) as the mailbox's OWNER, on the
   thread's own agent conversation (created on the first message and stored back, so
   follow-ups CONTINUE the same conversation and its memory).
4. Stamp the message with the run id. A failure anywhere leaves the thread ``error``.

The run itself is an ordinary ``agent_loop`` run — no gateway purpose, no special
graph. Its conclusion is the agent's ``record_intake_outcome`` call
(:mod:`app.agents.intake_tools`); a run that settles without one is caught by the
safe-fail hook at the agent-run job's exit.

Structured logs here are events + IDs + counts only, never email content.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.intake_prompt import IntakeEmailView, build_intake_prompt
from app.agents.run_service import AgentThreadBusy, start_agent_run
from app.config import Settings, get_settings
from app.db.session import get_session_factory
from app.models.agent_run import AgentRun
from app.models.intake import IntakeMailbox, IntakeMessage, IntakeThread
from app.models.project import Project
from app.schemas.agent_runs import AgentRunStatus, BudgetProfile
from app.workers.queue import enqueue_agent_run_job

log = logging.getLogger(__name__)

# Function name registered on the worker — must match the constant in
# :mod:`app.workers.queue` so the api-side enqueue helper targets the right
# function on the shared playbook queue.
INTAKE_EMAIL_JOB_NAME = "intake_email_job"

# Ruling 1: cost control is "run briefly", never "don't run". A mailbox binding may
# override both; these are the floor when it does not.
DEFAULT_INTAKE_BUDGET_PROFILE = BudgetProfile.economy
# Raised 24 -> 40 after the INTAKE-3 eval: three attachment-heavy threads hit the step
# cap before they could conclude (reading a SKILL.md costs read_file steps on top of the
# document reads). Still a LOW cap — "run briefly", not "don't run" (Ruling 1).
DEFAULT_INTAKE_MAX_STEPS = 40

# The conversation's display title. FIXED and fork-authored: an email subject is
# untrusted sender text and must never land in a display/title field (ADR-F086).
INTAKE_THREAD_TITLE = "Legal intake — email thread"

# A run is "in flight" on the thread's conversation at either of these statuses:
# ``running`` (executing) or ``awaiting_input`` (paused on a HITL approval — the
# lawyer owns the next move; a second run would fork the conversation).
_IN_FLIGHT_RUN_STATUSES = (AgentRunStatus.running.value, AgentRunStatus.awaiting_input.value)

# Fork-authored, fixed (never model text): a follow-up landed on a thread whose
# matter was already closed, so there is nothing to run against.
# Fork-authored, fixed (never model text): the matter's owner is no longer the mailbox
# owner every intake run is composed as.
OWNER_MISMATCH_NOTE = (
    "this matter is no longer owned by the intake mailbox's owner; re-bind the mailbox "
    "or the matter before this thread can run"
)

FILED_THREAD_NOTE = (
    "a follow-up arrived after this matter was closed; the lawyer decides whether to reopen it"
)


async def process_intake_thread(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    thread_id: uuid.UUID,
    *,
    enqueue: Callable[[uuid.UUID], Awaitable[bool]] = enqueue_agent_run_job,
) -> dict[str, Any]:
    """Start ONE bound-area-agent run for the thread's next unprocessed message (core).

    Returns a small status dict — ``{"status": "started"|"noop"|"deferred"|"filed"|
    "error", ...}`` — carrying IDs and counts only. Never raises for an expected
    condition (missing thread, no pending message, an in-flight run); an unexpected
    failure leaves the thread at ``status='error'`` and re-raises nothing to arq
    (a retry would re-run the same email).
    """
    async with session_factory() as db:
        # S1: serialize per thread. Two jobs for two messages on the SAME thread can be
        # dequeued concurrently; without this lock both pass the in-flight check and
        # start a run, forking the conversation. The lock is held for the whole
        # transaction, so the loser sees the winner's committed agent_thread_id.
        thread = (
            await db.execute(
                select(IntakeThread).where(IntakeThread.id == thread_id).with_for_update()
            )
        ).scalar_one_or_none()
        if thread is None:
            log.info(
                "intake_email_job: thread is gone",
                extra={"event": "intake_job_thread_missing", "thread_id": str(thread_id)},
            )
            return {"status": "noop", "reason": "thread_missing", "thread_id": str(thread_id)}

        message = (
            await db.execute(
                select(IntakeMessage)
                .where(
                    IntakeMessage.thread_id == thread.id,
                    IntakeMessage.direction == "in",
                    IntakeMessage.run_id.is_(None),
                )
                .order_by(IntakeMessage.created_at.asc(), IntakeMessage.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if message is None:
            # Every inbound message on this thread already has its run (a duplicate
            # enqueue, or a deferred job catching up after the queue drained).
            return {"status": "noop", "reason": "no_pending_message", "thread_id": str(thread_id)}

        # Plain scalars captured while the rows are live: start_agent_run COMMITS
        # this session, and a later attribute read on a stale instance would
        # lazy-refresh outside an awaited call (the MissingGreenlet trap).
        message_id = message.id
        mailbox = await db.get(IntakeMailbox, thread.mailbox_id)
        if mailbox is None or thread.project_id is None:
            thread.status = "error"
            await db.commit()
            log.warning(
                "intake_email_job: thread has no mailbox or no matter",
                extra={"event": "intake_job_binding_missing", "thread_id": str(thread_id)},
            )
            return {"status": "error", "reason": "binding_missing", "thread_id": str(thread_id)}

        # An in-flight run on this conversation means the previous message is still
        # being worked (or is paused on the lawyer's approval). Leave THIS message
        # unclaimed — the next enqueue picks it up — rather than forking the thread.
        if thread.agent_thread_id is not None:
            in_flight = (
                await db.execute(
                    select(AgentRun.id)
                    .where(
                        AgentRun.thread_id == thread.agent_thread_id,
                        AgentRun.status.in_(_IN_FLIGHT_RUN_STATUSES),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if in_flight is not None:
                log.info(
                    "intake_email_job: a run is already in flight on this thread; deferring",
                    extra={"event": "intake_job_deferred", "thread_id": str(thread_id)},
                )
                return {"status": "deferred", "thread_id": str(thread_id)}

        # The matter may already be CLOSED (a 'dealt_with' outcome archives it, and
        # archiving is the memory fence). Composition refuses to bind an archived
        # matter, so the run would degrade to a blank workspace with no intake tools —
        # worse than useless. Park the thread for the lawyer instead of spending a run.
        project = await db.get(Project, thread.project_id)
        if project is not None and project.owner_id != mailbox.owner_user_id:
            # S3: the matter's owner can be changed out of band (PATCH /projects), and
            # the mailbox owner is who every intake run is composed AS. A mismatch would
            # compose a run for a user who does not own the matter — composition would
            # refuse the binding and the run would degrade to a blank workspace. Refuse
            # loudly instead; re-binding the mailbox or the matter is a human decision.
            thread.status = "error"
            thread.outcome_note = OWNER_MISMATCH_NOTE
            await db.commit()
            log.warning(
                "intake_email_job: matter owner is not the mailbox owner",
                extra={"event": "intake_job_owner_mismatch", "thread_id": str(thread_id)},
            )
            return {"status": "error", "reason": "owner_mismatch", "thread_id": str(thread_id)}
        if project is None or project.archived_at is not None:
            thread.status = "awaiting_human"
            thread.outcome_note = FILED_THREAD_NOTE
            await db.commit()
            log.info(
                "intake_email_job: follow-up on a filed thread; parked for the lawyer",
                extra={"event": "intake_job_filed_thread", "thread_id": str(thread_id)},
            )
            return {"status": "filed", "thread_id": str(thread_id)}

        view = IntakeEmailView(
            thread_ref=str(thread.id),
            from_addr=message.from_addr or "(sender not recorded)",
            to_addrs=[str(a) for a in (message.to_addrs or [])],
            subject=message.subject or thread.subject,
            timestamp=message.provider_timestamp,
            auth_state=thread.auth_state,
            message_count=thread.message_count,
            attachment_filenames=[str(n) for n in (message.attachment_filenames or [])],
            body_text=message.body_text or "",
        )
        prompt = build_intake_prompt(view)

        # S4: the column has no DB CHECK (INTAKE-1 validates it at the Pydantic
        # boundary), so an out-of-band value must DEGRADE, not raise — an exception
        # here escapes to arq and the job is retried forever on the same bad row.
        budget_profile = DEFAULT_INTAKE_BUDGET_PROFILE
        if mailbox.default_budget_profile:
            try:
                budget_profile = BudgetProfile(mailbox.default_budget_profile)
            except ValueError:
                log.warning(
                    "intake mailbox has an unknown budget profile; using the default",
                    extra={
                        "event": "intake_job_bad_budget_profile",
                        "mailbox_id": str(mailbox.id),
                    },
                )
        max_steps = mailbox.max_steps or DEFAULT_INTAKE_MAX_STEPS

        thread.status = "processing"
        try:
            run = await start_agent_run(
                db,
                user_id=mailbox.owner_user_id,
                project_id=thread.project_id,
                thread_id=thread.agent_thread_id,
                prompt=prompt,
                budget_profile=budget_profile,
                max_steps=max_steps,
                # Fixed, fork-authored — never the email's subject (ADR-F086).
                title=INTAKE_THREAD_TITLE,
                settings=settings,
                enqueue=enqueue,
            )
        except AgentThreadBusy:
            # Lost the race to a concurrent job on the same conversation; the same
            # deferral rule applies (the message stays unclaimed).
            await db.rollback()
            log.info(
                "intake_email_job: conversation busy; deferring",
                extra={"event": "intake_job_deferred", "thread_id": str(thread_id)},
            )
            return {"status": "deferred", "thread_id": str(thread_id)}
        except Exception:
            await db.rollback()
            async with session_factory() as err_db:
                errored = await err_db.get(IntakeThread, thread_id)
                if errored is not None:
                    errored.status = "error"
                    await err_db.commit()
            log.exception(
                "intake_email_job: could not start the intake run",
                extra={"event": "intake_job_run_failed", "thread_id": str(thread_id)},
            )
            return {"status": "error", "reason": "run_start_failed", "thread_id": str(thread_id)}

        # start_agent_run committed; re-attach the rows this session still needs.
        thread = await db.get(IntakeThread, thread_id)
        message = await db.get(IntakeMessage, message_id)

        if run.status != AgentRunStatus.running.value:
            # The enqueue failed, so start_agent_run already settled the run
            # ``failed`` (ADR-F009: never a zombie). Leave the message UNCLAIMED so a
            # later re-enqueue can retry this email cleanly, and surface the thread as
            # errored rather than silently stuck at 'processing'.
            if thread is not None:
                thread.status = "error"
            await db.commit()
            log.warning(
                "intake_email_job: the intake run could not be queued",
                extra={
                    "event": "intake_job_enqueue_failed",
                    "thread_id": str(thread_id),
                    "run_id": str(run.id),
                },
            )
            return {"status": "error", "reason": "enqueue_failed", "thread_id": str(thread_id)}

        # ``agent_thread_id`` is stored back on the FIRST run so every follow-up
        # continues the SAME agent conversation (Ruling 1: conversation memory carries).
        if thread is not None:
            thread.status = "processing"
            if thread.agent_thread_id is None:
                thread.agent_thread_id = run.thread_id
        if message is not None:
            message.run_id = run.id
        await db.commit()

        log.info(
            "intake_email_job: run started",
            extra={
                "event": "intake_job_run_started",
                "thread_id": str(thread_id),
                "run_id": str(run.id),
                "agent_thread_id": str(run.thread_id),
                "attachments": len(view.attachment_filenames),
                "message_count": view.message_count,
            },
        )
        return {
            "status": "started",
            "thread_id": str(thread_id),
            "run_id": str(run.id),
        }


async def intake_email_job(ctx: dict[str, Any], thread_id_str: str) -> dict[str, Any]:
    """arq wrapper around :func:`process_intake_thread` (process globals)."""

    return await process_intake_thread(
        get_session_factory(), get_settings(), uuid.UUID(thread_id_str)
    )
