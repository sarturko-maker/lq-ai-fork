"""Mail-bridge → api intake-email landing surface — INTAKE-1 (ADR-F086).

The (future, INTAKE-2) mail-bridge microservice is the ONLY holder of
mailbox credentials; it normalizes a provider's inbound-email event into an
:class:`~app.schemas.intake.InboundEmailEnvelope` and POSTs it here.
Authenticated the same way ``integrations_slack.py``/``integrations_teams.py``
authenticate their bridges: a shared ``LQ_AI_BRIDGE_TOKEN`` bearer via
``require_bridge_auth`` — NOT a user JWT (this is a service-to-service
caller with no user context). Mounted WITHOUT the ``ActiveUser`` gate (see
the router aggregation in ``app.api.__init__``).

Flow (ADR-F086 architecture diagram; see the fresh-context review fix that
made idempotency claim-first and leak-free):

1. Resolve the active :class:`~app.models.intake.IntakeMailbox` by
   ``(provider, inbox_id)`` — 404 if none is bound.
2. Resolve or create the :class:`~app.models.intake.IntakeThread`. Creating
   one races against a concurrent delivery of the FIRST message on the same
   thread: on a flush-time ``IntegrityError`` (``uq_intake_threads_*``), we
   roll back and re-select — the concurrent winner's row is what we
   continue with.
3. **Claim**: insert the :class:`~app.models.intake.IntakeMessage` row and
   flush IMMEDIATELY — before any project creation or attachment upload.
   This is the atomic idempotency anchor (``uq_intake_messages_*``): a
   concurrent redelivery of the SAME message loses this race and exits as
   ``duplicate: true`` having uploaded nothing. A pre-check SELECT would
   leave a TOCTOU window where two concurrent deliveries both pass the
   check and both upload; the flush-and-catch here closes it.
4. If the thread has no project yet, create one EAGERLY
   (``intake_state='candidate'`` — ADR-F086: the project row is substrate,
   created before any agent has looked at it; the agent's later
   ``record_intake_outcome`` (INTAKE-3) promotes or dismisses it).
5. Ingest every attachment via :func:`app.ingest.ingest_bytes`, tracking
   each successfully-uploaded storage path. On ANY exception from this
   point through the final commit (a later attachment too large, a DB
   error, …) every already-uploaded object from THIS request is
   best-effort deleted before the exception re-raises — a failed request
   leaves no rows AND no orphaned blobs; redelivery retries cleanly.
6. Commit, then enqueue ``intake_email_job`` on the shared ``arq:m3a6``
   queue — best-effort/non-fatal (log a warning, still return 200; the
   worker is a stub in this slice regardless — INTAKE-3 fills it in).

Response carries counts/IDs only (``thread_id``, ``project_id``,
``files_ingested``, ``duplicate``) — never email content, matching the
audit-contract posture elsewhere in this codebase. Structured logs here are
likewise events + counts only, never subject/body/sender values.
"""

from __future__ import annotations

import logging
import uuid
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
from app.storage import delete_object

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


async def _select_thread(
    db: AsyncSession, *, mailbox_id: uuid.UUID, provider_thread_id: str
) -> IntakeThread | None:
    return (
        await db.execute(
            select(IntakeThread).where(
                IntakeThread.mailbox_id == mailbox_id,
                IntakeThread.provider_thread_id == provider_thread_id,
            )
        )
    ).scalar_one_or_none()


async def _cleanup_uploaded(storage_paths: list[str]) -> None:
    """Best-effort delete of storage objects already written this request.

    Called when the request fails AFTER one or more attachments were
    already durably uploaded: a failed intake delivery must leave no
    orphaned blobs behind, same invariant :func:`app.ingest.ingest_bytes`
    upholds for its own single call — this covers the WIDER window across
    an entire multi-attachment request (an earlier attachment's bytes
    survive its own successful upload+flush even though a LATER attachment
    in the same request is what ultimately fails).
    """

    for storage_path in storage_paths:
        try:
            await delete_object(storage_path=storage_path)
        except Exception:
            log.warning(
                "intake email: failed to clean up storage object after request failure",
                extra={"event": "intake_email_cleanup_failed", "storage_path": storage_path},
            )


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

    # Capture plain scalars NOW: both IntegrityError branches below roll the
    # session back, which expires every loaded ORM instance — a later
    # `mailbox.<attr>` access would lazy-refresh outside an awaited call and
    # raise MissingGreenlet (the documented async-session trap).
    mailbox_id = mailbox.id
    owner_user_id = mailbox.owner_user_id
    practice_area_id = mailbox.practice_area_id

    thread = await _select_thread(
        db, mailbox_id=mailbox_id, provider_thread_id=envelope.thread.provider_thread_id
    )

    if thread is None:
        thread = IntakeThread(
            mailbox_id=mailbox_id,
            provider_thread_id=envelope.thread.provider_thread_id,
            subject=envelope.thread.subject,
            message_count=0,
        )
        db.add(thread)
        try:
            await db.flush()
        except IntegrityError:
            # A concurrent delivery of the FIRST message on this same
            # thread won the race and already created it — roll back and
            # continue with THEIR row rather than ours.
            await db.rollback()
            thread = await _select_thread(
                db, mailbox_id=mailbox_id, provider_thread_id=envelope.thread.provider_thread_id
            )
            if thread is None:  # pragma: no cover - defensive; FK/unique imply it exists
                raise Conflict(
                    "Thread creation race could not be resolved; retry the delivery.",
                    details={"provider_thread_id": envelope.thread.provider_thread_id},
                ) from None

    # CLAIM (ADR-F086 idempotency anchor): the ONLY thing that decides
    # duplicate-vs-new is this flush. Nothing above this line wrote
    # anything that isn't safely re-creatable (thread rows are idempotent
    # by construction — the unique constraint IS the arbiter).
    # INTAKE-3 (migration 0099): the message's own content is persisted HERE, at
    # the claim, because the arq job's payload is only the thread id — the worker
    # re-derives the email from these columns to build its fenced prompt block
    # (app.agents.intake_prompt). Every value is boundary-validated untrusted
    # sender text; ``attachment_filenames`` is filled in after ingest below with
    # the names actually stored (what ``read_document`` answers to).
    message_row = IntakeMessage(
        thread_id=thread.id,
        provider_message_id=envelope.message.provider_message_id,
        direction="in",
        from_addr=envelope.message.from_addr,
        to_addrs=list(envelope.message.to),
        subject=envelope.thread.subject,
        body_text=envelope.message.text,
        provider_timestamp=envelope.message.timestamp,
    )
    db.add(message_row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        log.info(
            "intake email duplicate delivery",
            extra={"event": "intake_email_duplicate", "mailbox_id": str(mailbox_id)},
        )
        # `thread` may be stale after the rollback (SQLAlchemy expires
        # objects touched by an aborted transaction) — re-select fresh
        # rather than risk an out-of-async-context lazy-load.
        current = await _select_thread(
            db, mailbox_id=mailbox_id, provider_thread_id=envelope.thread.provider_thread_id
        )
        return IntakeEmailIngestResponse(
            duplicate=True,
            thread_id=current.id if current else None,
            project_id=current.project_id if current else None,
            files_ingested=0,
        )

    # Everything from here on can fail partway through an upload; track
    # every attachment that actually lands in storage so a later failure
    # (in this loop OR at the final commit) can clean all of them up.
    uploaded_storage_paths: list[str] = []
    ingested_filenames: list[str] = []
    files_ingested = 0
    try:
        now = datetime.now(tz=UTC)
        thread.status = "received"
        thread.last_message_id = envelope.message.provider_message_id
        thread.last_inbound_at = now
        thread.auth_state = envelope.message.auth_state
        thread.message_count += 1

        # Eager project creation (ADR-F086): the project row is substrate —
        # it exists before any agent has looked at the thread. Only the
        # FIRST message on a thread creates one.
        if thread.project_id is None:
            from app.api.projects import _resolve_unique_slug
            from app.schemas.projects import slugify

            project_name = _derive_project_name(envelope.thread.subject)
            desired_slug = slugify(project_name)
            final_slug = await _resolve_unique_slug(
                db, owner_id=owner_user_id, desired=desired_slug
            )
            project = Project(
                owner_id=owner_user_id,
                practice_area_id=practice_area_id,
                name=project_name,
                slug=final_slug,
                intake_state="candidate",
            )
            db.add(project)
            try:
                await db.flush()
            except IntegrityError as exc:
                raise Conflict(
                    "Slug collision creating the candidate matter for this thread; "
                    "retry the delivery.",
                    details={"slug": final_slug},
                ) from exc
            thread.project_id = project.id

        for attachment in envelope.message.attachments:
            row = await ingest_bytes(
                session=db,
                settings=settings,
                owner_id=owner_user_id,
                project_id=thread.project_id,
                filename=attachment.filename,
                content_type=attachment.content_type,
                data=attachment.decoded_bytes,
            )
            uploaded_storage_paths.append(row.storage_path)
            ingested_filenames.append(row.filename)
            files_ingested += 1

        # The STORED names (ingest_bytes may normalise the provider's filename),
        # so the agent's prompt names files ``read_document`` will actually find.
        message_row.attachment_filenames = ingested_filenames

        await db.commit()
    except Exception:
        await db.rollback()
        await _cleanup_uploaded(uploaded_storage_paths)
        raise

    log.info(
        "intake email ingested",
        extra={
            "event": "intake_email_ingested",
            "mailbox_id": str(mailbox_id),
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

        await enqueue_intake_email_job(
            thread.id, provider_message_id=envelope.message.provider_message_id
        )
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
