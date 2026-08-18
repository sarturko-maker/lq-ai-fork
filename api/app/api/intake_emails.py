"""Mail-bridge → api intake-email landing surface — INTAKE-1 (ADR-F086).

The (future, INTAKE-2) mail-bridge microservice is the ONLY holder of
mailbox credentials; it normalizes a provider's inbound-email event into an
:class:`~app.schemas.intake.InboundEmailEnvelope` and POSTs it here.
Authenticated the same way ``integrations_slack.py``/``integrations_teams.py``
authenticate their bridges: a shared ``LQ_AI_BRIDGE_TOKEN`` bearer via
``require_bridge_auth`` — NOT a user JWT (this is a service-to-service
caller with no user context). Mounted WITHOUT the ``ActiveUser`` gate (see
the router aggregation in ``app.api.__init__``).

Flow (ADR-F086 architecture diagram):

1. Resolve the active :class:`~app.models.intake.IntakeMailbox` by
   ``(provider, inbox_id)`` — 404 if none is bound (never leaks whether a
   soft-deleted/inactive binding once existed; same posture as any other
   "unknown resource" 404 in this codebase).
2. Idempotency: if ``(thread, provider_message_id)`` is already recorded,
   return ``{"duplicate": true}`` and do nothing else — the
   ``intake_messages`` unique key is the anchor; this is a fast-path
   short-circuit ahead of it, not a replacement for it.
3. Upsert the :class:`~app.models.intake.IntakeThread` — create at
   ``status='received'`` or bump ``last_message_id``/``last_inbound_at``/
   ``message_count``/``auth_state`` on an existing one.
4. If the thread has no project yet, create one EAGERLY
   (``intake_state='candidate'`` — ADR-F086: the project row is substrate,
   created before any agent has looked at it; the agent's later
   ``record_intake_outcome`` (INTAKE-3) promotes or dismisses it).
5. Ingest every attachment via :func:`app.ingest.ingest_bytes`.
6. Insert the :class:`~app.models.intake.IntakeMessage` row (direction
   ``'in'`` — the idempotency anchor for future duplicate delivery).
7. Commit, then enqueue ``intake_email_job`` on the shared ``arq:m3a6``
   queue — best-effort/non-fatal (log a warning, still return 200; the
   worker is a stub in this slice regardless — INTAKE-3 fills it in).

Response carries counts/IDs only (``thread_id``, ``project_id``,
``files_ingested``, ``duplicate``) — never email content, matching the
audit-contract posture elsewhere in this codebase. Structured logs here are
likewise events + counts only, never subject/body/sender values.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_bridge_auth
from app.config import Settings, get_settings
from app.db.session import get_db
from app.errors import Conflict, NotFound
from app.ingest import ingest_bytes
from app.models.intake import IntakeMailbox, IntakeMessage, IntakeThread
from app.models.project import Project
from app.schemas.intake import InboundEmailEnvelope, IntakeEmailIngestResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/intake", tags=["intake-emails"])

_PROJECT_NAME_MAX_LEN = 200
_DEFAULT_PROJECT_NAME = "Intake — (no subject)"


def _derive_project_name(subject: str) -> str:
    """Bounded candidate-matter name from a thread's subject.

    Empty/whitespace-only subjects (real email traffic, not an error) fall
    back to a generic label rather than an empty project name.
    """

    stripped = subject.strip()
    if not stripped:
        return _DEFAULT_PROJECT_NAME
    return stripped[:_PROJECT_NAME_MAX_LEN]


@router.post(
    "/emails",
    response_model=IntakeEmailIngestResponse,
    dependencies=[Depends(require_bridge_auth)],
    summary="Land one inbound-email envelope from the mail-bridge",
)
async def ingest_email(
    envelope: InboundEmailEnvelope,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeEmailIngestResponse:
    mailbox = (
        await db.execute(
            select(IntakeMailbox).where(
                IntakeMailbox.provider == envelope.provider,
                IntakeMailbox.inbox_id == envelope.inbox_id,
                IntakeMailbox.active.is_(True),
                IntakeMailbox.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if mailbox is None:
        raise NotFound(
            message="No active intake mailbox is bound to this (provider, inbox_id).",
            details={"provider": envelope.provider, "inbox_id": envelope.inbox_id},
        )

    thread = (
        await db.execute(
            select(IntakeThread).where(
                IntakeThread.mailbox_id == mailbox.id,
                IntakeThread.provider_thread_id == envelope.thread.provider_thread_id,
            )
        )
    ).scalar_one_or_none()

    # Idempotency fast path: a thread that already recorded this exact
    # provider_message_id is a duplicate delivery (retried webhook, replayed
    # websocket event) — do nothing else. The intake_messages UNIQUE
    # constraint is the real anchor; this is just the early, cheap check.
    if thread is not None:
        existing_message = (
            await db.execute(
                select(IntakeMessage.id).where(
                    IntakeMessage.thread_id == thread.id,
                    IntakeMessage.provider_message_id == envelope.message.provider_message_id,
                )
            )
        ).scalar_one_or_none()
        if existing_message is not None:
            log.info(
                "intake email duplicate delivery",
                extra={
                    "event": "intake_email_duplicate",
                    "mailbox_id": str(mailbox.id),
                    "thread_id": str(thread.id),
                },
            )
            return IntakeEmailIngestResponse(
                duplicate=True,
                thread_id=thread.id,
                project_id=thread.project_id,
                files_ingested=0,
            )

    now = datetime.now(tz=UTC)
    if thread is None:
        thread = IntakeThread(
            mailbox_id=mailbox.id,
            provider_thread_id=envelope.thread.provider_thread_id,
            subject=envelope.thread.subject,
            status="received",
            last_message_id=envelope.message.provider_message_id,
            last_inbound_at=now,
            auth_state=envelope.message.auth_state,
            message_count=1,
        )
        db.add(thread)
        await db.flush()
    else:
        thread.status = "received"
        thread.last_message_id = envelope.message.provider_message_id
        thread.last_inbound_at = now
        thread.auth_state = envelope.message.auth_state
        thread.message_count += 1

    # Eager project creation (ADR-F086): the project row is substrate — it
    # exists before any agent has looked at the thread. `intake_state`
    # starts 'candidate'; INTAKE-3's record_intake_outcome later promotes or
    # dismisses it. Only the FIRST message on a thread creates one.
    if thread.project_id is None:
        from app.api.projects import _resolve_unique_slug
        from app.schemas.projects import slugify

        project_name = _derive_project_name(envelope.thread.subject)
        desired_slug = slugify(project_name)
        final_slug = await _resolve_unique_slug(
            db, owner_id=mailbox.owner_user_id, desired=desired_slug
        )
        project = Project(
            owner_id=mailbox.owner_user_id,
            practice_area_id=mailbox.practice_area_id,
            name=project_name,
            slug=final_slug,
            intake_state="candidate",
        )
        db.add(project)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise Conflict(
                "Slug collision creating the candidate matter for this thread; retry the delivery.",
                details={"slug": final_slug},
            ) from exc
        thread.project_id = project.id

    files_ingested = 0
    for attachment in envelope.message.attachments:
        await ingest_bytes(
            session=db,
            settings=settings,
            owner_id=mailbox.owner_user_id,
            project_id=thread.project_id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            data=attachment.decoded_bytes,
        )
        files_ingested += 1

    message_row = IntakeMessage(
        thread_id=thread.id,
        provider_message_id=envelope.message.provider_message_id,
        direction="in",
    )
    db.add(message_row)

    await db.commit()

    log.info(
        "intake email ingested",
        extra={
            "event": "intake_email_ingested",
            "mailbox_id": str(mailbox.id),
            "thread_id": str(thread.id),
            "project_id": str(thread.project_id),
            "files_ingested": files_ingested,
            "message_count": thread.message_count,
        },
    )

    # Enqueue the (stub, this slice) processing job — best-effort/non-fatal.
    # INTAKE-3 fills in the real body; the row already carries everything a
    # later worker run needs to pick up.
    try:
        from app.workers.queue import enqueue_intake_email_job

        await enqueue_intake_email_job(thread.id)
    except Exception as exc:
        log.warning(
            "enqueue_intake_email_job raised; thread stays 'received'",
            extra={
                "event": "intake_email_enqueue_raised",
                "thread_id": str(thread.id),
                "error": str(exc),
            },
        )

    return IntakeEmailIngestResponse(
        duplicate=False,
        thread_id=thread.id,
        project_id=thread.project_id,
        files_ingested=files_ingested,
    )


__all__ = ["router"]
