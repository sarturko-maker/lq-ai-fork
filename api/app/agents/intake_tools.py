"""The intake run's two tools — INTAKE-3 (fork, ADR-F086).

An intake run is an ORDINARY agent run on the bound practice-area agent (Ruling 1):
same composition root, same brakes, same memory tiers. Only two things are added, and
only for a run whose matter was born from an intake email (``projects.intake_state IS
NOT NULL`` — provenance, and the grant gate) — the same "structural grant, not area data" precedent as the matter-memory
tools, so no ``practice_area_tool_groups`` row exists or is needed:

* :func:`record_intake_outcome` — the run's STRUCTURAL conclusion. A closed outcome
  enum plus a short free-form label and a note. This is the ONE thing an intake run
  must do (ADR-F086: "recorded structurally … never free prose"), and it decides
  whether the thread's matter closes or stays open for the lawyer.

  Every intake thread IS a matter from message one (ADR-F086 Amendment A1), so there
  are TWO outcomes and no promotion step:

  ================  =====================  ====================================
  outcome           intake_threads.status  the matter
  ================  =====================  ====================================
  ``dealt_with``    ``handled``            closed (``archived_at``), label + note
  ``needs_human``   ``awaiting_human``     stays open for the lawyer
  ================  =====================  ====================================

  ``projects.intake_state`` is PROVENANCE ("born from email") and the grant gate for
  these tools — the agent path never writes it.

* :func:`draft_email_reply` — composes a reply and records it as a
  ``direction='out'`` ``intake_messages`` row. **It sends nothing.** v1 has no
  auto-send path anywhere (ADR-F086), and this tool is interrupt-gated
  UNCONDITIONALLY by :data:`app.agents.hitl.ALWAYS_INTERRUPT_TOOL_NAMES` — a
  structural gate, not a policy one, so no area config and no instruction inside a
  hostile email can unlock it. Delivery (api → mail-bridge ``/send``) is INTAKE-4.

Both writes go through ``guarded_dispatch`` (R6 grant / R5 halt / R4 cost) with the
guard's auto-audit only: counts/IDs, never the label, the note or a body. The grant
set is DISJOINT from every matter/domain grant (confinement).

Zero model calls; pure DB writes.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.guard import GuardContext, guarded_dispatch
from app.agents.tools import MatterBinding
from app.models.agent_run import AgentRun
from app.models.file import File
from app.models.intake import IntakeMessage, IntakeThread
from app.models.project import Project
from app.schemas.intake import DraftEmailReplyInput, RecordIntakeOutcomeInput

logger = logging.getLogger(__name__)

INTAKE_TOOL_NAMES = frozenset({"record_intake_outcome", "draft_email_reply"})

# outcome -> the thread status it settles on. The matter-side effect (closing the
# matter on 'dealt_with') is applied beside this map in _record_intake_outcome.
_OUTCOME_THREAD_STATUS: dict[str, str] = {
    "dealt_with": "handled",
    "needs_human": "awaiting_human",
}

# R7 — the safe-fail note. FORK-AUTHORED and fixed: a run that ended without
# concluding must never have model text put in its place.
NO_OUTCOME_NOTE = "run ended without a recorded outcome"


def build_intake_tools(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    run_id: uuid.UUID,
    binding: MatterBinding,
) -> list[Callable[..., Any]]:
    """Build the two intake tools for one run on an intake-born matter.

    The guard context grants exactly :data:`INTAKE_TOOL_NAMES`; ``binding.project_id``
    scopes every write, so the blast radius is this one matter and the one
    intake thread bound to it.
    """
    ctx = GuardContext(
        session_factory=session_factory,
        run_id=run_id,
        user_id=binding.user_id,
        project_id=binding.project_id,
        granted=INTAKE_TOOL_NAMES,
        practice_area_id=binding.practice_area_id,
    )

    async def record_intake_outcome(outcome: str, label: str, note: str) -> str:
        """Conclude this intake thread — call this exactly once, last.

        `outcome` must be one of exactly two values:

        - "dealt_with" — nothing further is needed and nothing leaves the system
          (spam, marketing, an FYI, a notification, an automated message). The matter
          is CLOSED and filed with your label and note, so it does not clutter the
          lawyer's list. Use this ONLY when you are confident no lawyer needs to look.
        - "needs_human" — anything else: you prepared something, real work is
          starting, a decision or deadline is involved, or you are simply not sure.
          The matter stays OPEN and the thread waits for the supervising lawyer.
          This is the safe answer: when in doubt, choose it.

        `label` is a short tag of YOUR choosing for the lawyer's list ("NDA review",
        "renewal notice", "out of area — HR"). It is display only; nothing branches
        on it, and you are not picking from a fixed list.

        `note` is one short paragraph the lawyer reads at a glance: what this is,
        what you did, and what (if anything) you need from them.
        """
        return await guarded_dispatch(
            "record_intake_outcome",
            lambda db: _record_intake_outcome(db, binding, outcome=outcome, label=label, note=note),
            ctx,
        )

    async def draft_email_reply(
        to: list[str], subject: str, body: str, attachment_file_ids: list[str] | None = None
    ) -> str:
        """Draft a reply to this intake email. It is NOT sent — a lawyer decides.

        Use this when the right answer to the email is a reply: an answer to a
        question, an acknowledgement with what happens next, a request for the
        missing document, a handoff note for mail that belongs to another team.

        Write it as the company's legal team would write it: plain English, short,
        no legalese, no promises the lawyer has not made. `to` is the address(es)
        the reply should go to; `subject` is the reply's subject line; `body` is the
        full message text. `attachment_file_ids` may name documents already in this
        matter (their ids) if the reply should carry them.

        This call always stops for the supervising lawyer's approval before it does
        anything, and even once approved it only RECORDS the draft — nothing is
        delivered to anyone. Say so plainly when you tell the lawyer what you did.
        """
        return await guarded_dispatch(
            "draft_email_reply",
            lambda db: _draft_email_reply(
                db,
                binding,
                run_id=run_id,
                to=to,
                subject=subject,
                body=body,
                attachment_file_ids=attachment_file_ids or [],
            ),
            ctx,
        )

    return [record_intake_outcome, draft_email_reply]


async def load_intake_thread_for_run(
    db: AsyncSession, *, project_id: uuid.UUID, agent_thread_id: uuid.UUID | None
) -> IntakeThread | None:
    """The intake thread this RUN is the intake run OF, or ``None``.

    Under ADR-F086 Amendment A1 an intake-born matter is an ordinary matter: the
    lawyer opens it in the cockpit and chats about it like any other. Those chats run
    on their OWN agent conversation, so keying on the project alone (as the first cut
    did) would have let a cockpit turn be treated as the thread's intake run —
    arming the intake doctrine and tools, and letting a settled cockpit run flip a
    thread that is still processing (adversarial review S2/S5). The intake run is the
    one whose agent conversation IS the thread's ``agent_thread_id``; nothing else is.
    """
    if agent_thread_id is None:
        return None
    return (
        await db.execute(
            select(IntakeThread).where(
                IntakeThread.project_id == project_id,
                IntakeThread.agent_thread_id == agent_thread_id,
            )
        )
    ).scalar_one_or_none()


async def _load_thread_for_project(db: AsyncSession, project_id: uuid.UUID) -> IntakeThread | None:
    """The intake thread bound to this matter (oldest if ever more than one).

    Used by the TOOLS, which are only ever granted to a run that
    :func:`load_intake_thread_for_run` already identified as the thread's intake run —
    so the project binding is a sufficient key there.
    """
    return (
        await db.execute(
            select(IntakeThread)
            .where(IntakeThread.project_id == project_id)
            .order_by(IntakeThread.created_at.asc(), IntakeThread.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _record_intake_outcome(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    outcome: str,
    label: str,
    note: str,
) -> str:
    """Validate → write the outcome onto the thread → apply the project effect."""
    try:
        proposal = RecordIntakeOutcomeInput(
            outcome=outcome,  # type: ignore[arg-type]  # Pydantic validates the closed set
            label=label,
            note=note,
        )
    except ValidationError as exc:
        return _rejection_text(exc, tool="record_intake_outcome")

    thread = await _load_thread_for_project(db, binding.project_id)
    if thread is None:
        # Not an intake run after all (or the thread was deleted underneath us).
        return (
            "This matter is not an intake thread, so there is no intake outcome to "
            "record. Nothing was recorded."
        )

    if thread.outcome is not None:
        # Idempotent: last write wins, but a second conclusion in one run is worth
        # knowing about (IDs only — never the label or the note).
        logger.info(
            "record_intake_outcome called again in the same run; overwriting",
            extra={
                "event": "intake_outcome_overwritten",
                "thread_id": str(thread.id),
                "previous_outcome": thread.outcome,
                "outcome": proposal.outcome,
            },
        )

    prior_outcome = thread.outcome
    thread.outcome = proposal.outcome
    thread.label = proposal.label
    thread.outcome_note = proposal.note
    thread.status = _OUTCOME_THREAD_STATUS[proposal.outcome]

    project_note = "the matter stays open for the lawyer"
    if proposal.outcome != "dealt_with" and prior_outcome == "dealt_with":
        # Last-wins must win WHOLE (adversarial review B4): an earlier dealt_with in
        # this same run closed the matter, so changing our mind has to re-open it or
        # the thread says "open" while the matter is archived. Scoped to undoing OUR
        # OWN close — a matter the human archived was never given a dealt_with
        # outcome, so this branch cannot reach it.
        reopened = (
            await db.execute(
                select(Project).where(
                    Project.id == binding.project_id, Project.owner_id == binding.user_id
                )
            )
        ).scalar_one_or_none()
        if reopened is not None:
            reopened.archived_at = None
    if proposal.outcome == "dealt_with":
        # Close the matter: the SAME soft archive DELETE /projects/{id} performs
        # (archived_at), and nothing else — ``intake_state`` is provenance, never a
        # lifecycle the agent drives (ADR-F086 Amendment A1). Archiving is also the
        # memory fence: a closed matter composes no binding on a later run.
        project = (
            await db.execute(
                select(Project).where(
                    Project.id == binding.project_id, Project.owner_id == binding.user_id
                )
            )
        ).scalar_one_or_none()
        if project is not None and project.archived_at is None:
            project.archived_at = datetime.now(tz=UTC)
        project_note = "the matter is closed and filed away"

    return (
        f"Intake outcome recorded: {proposal.outcome} (label: {proposal.label}). "
        f"The thread is now {thread.status} and {project_note}. "
        "This thread stays visible to the lawyer with your label and note."
    )


async def _draft_email_reply(
    db: AsyncSession,
    binding: MatterBinding,
    *,
    run_id: uuid.UUID,
    to: list[str],
    subject: str,
    body: str,
    attachment_file_ids: list[str],
) -> str:
    """Validate → check the attachments are this matter's → record the draft."""
    try:
        proposal = DraftEmailReplyInput(
            to=to,
            subject=subject,
            body=body,
            attachment_file_ids=attachment_file_ids,  # type: ignore[arg-type]  # str → UUID
        )
    except ValidationError as exc:
        return _rejection_text(exc, tool="draft_email_reply")

    thread = await _load_thread_for_project(db, binding.project_id)
    if thread is None:
        return (
            "This matter is not an intake thread, so there is no email to reply to. "
            "Nothing was drafted."
        )

    attachment_names: list[str] = []
    if proposal.attachment_file_ids:
        # Owner- AND matter-scoped: a file id from anywhere else is simply "not
        # found" (no existence disclosure — the house 404 posture).
        rows = (
            (
                await db.execute(
                    select(File.id, File.filename).where(
                        File.id.in_(proposal.attachment_file_ids),
                        File.project_id == binding.project_id,
                        File.owner_id == binding.user_id,
                        File.deleted_at.is_(None),
                    )
                )
            )
            .tuples()
            .all()
        )
        found = {row[0] for row in rows}
        missing = [fid for fid in proposal.attachment_file_ids if fid not in found]
        if missing:
            return (
                f"{len(missing)} of the attachment ids you gave are not documents in this "
                "matter, so nothing was drafted. Attach only files from this matter's "
                "documents and call draft_email_reply again."
            )
        attachment_names = [row[1] for row in rows]

    draft = IntakeMessage(
        thread_id=thread.id,
        # There is no provider id until INTAKE-4 actually delivers this; the
        # unique key (thread_id, provider_message_id) needs a value, so mint a
        # local, clearly-marked one. INTAKE-4 replaces it with the real id on send.
        provider_message_id=f"draft:{uuid.uuid4()}",
        direction="out",
        run_id=run_id,
        to_addrs=list(proposal.to),
        subject=proposal.subject,
        body_text=proposal.body,
        attachment_filenames=attachment_names,
    )
    db.add(draft)
    await db.flush()

    attached = (
        ""
        if not attachment_names
        else f" It carries {len(attachment_names)} of this matter's documents as attachments."
    )
    return (
        "The reply is recorded as a draft on this intake thread and is NOT sent — "
        "nothing has left the system." + attached + " Delivery of approved replies "
        "arrives in a later slice (INTAKE-4); until then the lawyer sends it themselves. "
        "Tell the lawyer plainly that the reply is drafted, not sent."
    )


async def safe_fail_intake_thread(
    session_factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID
) -> bool:
    """R7 — a settled intake run that recorded NO outcome leaves the thread waiting.

    Called once at the run job's exit for EVERY run (no-op for the overwhelming
    majority — a run with no intake thread returns immediately). Without it a run
    that failed, was cancelled, capped, or paused for HITL without concluding would
    leave its thread stuck at ``processing`` forever, invisible in the lawyer's
    "waiting for me" list. The note is a FIXED fork-authored string — never model
    text, never an exception message.

    Returns whether it changed anything. Never raises: it must not mask the run's
    own outcome (the caller invokes it from a ``finally``).
    """
    try:
        async with session_factory() as db:
            run = await db.get(AgentRun, run_id)
            if run is None or run.project_id is None or run.status == "running":
                return False
            # S5: only the thread's OWN intake run may park it — a lawyer's cockpit
            # run on the same matter must never flip a thread that is still processing.
            thread = await load_intake_thread_for_run(
                db, project_id=run.project_id, agent_thread_id=run.thread_id
            )
            if thread is None or thread.status != "processing":
                return False
            thread.status = "awaiting_human"
            if thread.outcome_note is None:
                thread.outcome_note = NO_OUTCOME_NOTE
            await db.commit()
            logger.info(
                "intake thread left waiting: run settled without an outcome",
                extra={
                    "event": "intake_thread_safe_failed",
                    "thread_id": str(thread.id),
                    "run_id": str(run_id),
                    "run_status": run.status,
                },
            )
            return True
    except Exception:
        logger.exception(
            "intake safe-fail hook failed (the run's own settle stands)",
            extra={"event": "intake_safe_fail_error", "run_id": str(run_id)},
        )
        return False


async def requeue_pending_intake_message(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    *,
    enqueue: Callable[[uuid.UUID, str], Awaitable[bool]] | None = None,
) -> bool:
    """B3 — hand the thread's NEXT unprocessed message back to the queue.

    A follow-up that landed while a run was in flight is deliberately left unclaimed
    by :func:`app.workers.intake_worker.process_intake_thread` (it returns
    ``deferred`` rather than forking the conversation). Nothing else would ever
    re-enqueue it: the only other producer is the landing endpoint, and its arq job id
    is keyed per MESSAGE, so the deferred message had already burned its enqueue. The
    result was a silently orphaned email (adversarial review B3). Settling the
    in-flight run is exactly the moment the thread is free again, so the run job's
    exit re-enqueues here.

    Called once per settled run, right after the safe-fail hook; a no-op for every
    non-intake run and for a thread with nothing pending. Never raises — it must not
    mask the run's own outcome.
    """
    if enqueue is None:

        async def enqueue(thread_id: uuid.UUID, provider_message_id: str) -> bool:
            from app.workers.queue import enqueue_intake_email_job

            return await enqueue_intake_email_job(
                thread_id, provider_message_id=provider_message_id
            )

    try:
        async with session_factory() as db:
            run = await db.get(AgentRun, run_id)
            if run is None or run.project_id is None or run.status == "running":
                return False
            thread = await load_intake_thread_for_run(
                db, project_id=run.project_id, agent_thread_id=run.thread_id
            )
            if thread is None:
                return False
            pending = (
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
            if pending is None:
                return False
            thread_id, provider_message_id = thread.id, pending.provider_message_id
        queued = await enqueue(thread_id, provider_message_id)
        logger.info(
            "intake thread has a deferred message; re-enqueued after the run settled",
            extra={
                "event": "intake_deferred_message_requeued",
                "thread_id": str(thread_id),
                "run_id": str(run_id),
                "queued": queued,
            },
        )
        return queued
    except Exception:
        logger.exception(
            "intake re-enqueue hook failed (the message stays pending for a later run)",
            extra={"event": "intake_requeue_error", "run_id": str(run_id)},
        )
        return False


def _rejection_text(exc: ValidationError, *, tool: str) -> str:
    """Turn a Pydantic failure into a fix-and-retry message (no value echo)."""
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(input)"
        problems.append(f"- {loc}: {err['msg']}")
    return (
        f"Rejected — nothing was recorded. Fix the following and call {tool} again:\n"
        + "\n".join(problems)
    )


__all__ = [
    "INTAKE_TOOL_NAMES",
    "NO_OUTCOME_NOTE",
    "build_intake_tools",
    "load_intake_thread_for_run",
    "requeue_pending_intake_message",
    "safe_fail_intake_thread",
]
