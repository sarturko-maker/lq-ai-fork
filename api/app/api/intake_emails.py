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
   continue with. A NEW thread first runs the INTAKE-4a resolver
   (:func:`resolve_inbound_attachment`, ADR-F088): a reply or forward that
   names a message we already hold, or carries a matter reference whose
   sender is on that matter's roster, lands on the EXISTING matter (and
   inherits its agent conversation) instead of opening a second one.
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
from dataclasses import dataclass
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
from app.matters.reference import allocate_reference
from app.matters.stamping import (
    MAX_PARSED_TAGS,
    looks_like_address,
    normalise_address,
    parse_plus_tags,
    parse_reference_tags,
    parse_threading_headers,
)
from app.models.intake import IntakeMailbox, IntakeMessage, IntakeThread
from app.models.project import MatterParticipant, Project
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


# ---------------------------------------------------------------------------
# INTAKE-4a (ADR-F088) — the inbound resolver: which matter does this belong to?
#
# The trust ladder, strongest first. Only layer 1 and layer 2 may attach on
# their own; layer 3 is sender-controlled text and attaches ONLY when the sender
# is already on the matter's roster. Everything weaker leaves a note and opens a
# new matter — email content never merges itself into a matter that may hold
# privileged material.
#
#   1  same (mailbox, provider_thread_id)   — the provider's own threading
#   2  References/In-Reply-To names a message WE SENT from this mailbox
#   3  [ORG-AREA-NNNN] subject tag or a plus-tagged recipient, Roster-gated
#
# Cross-owner is silence, not an error: a reference belonging to someone else's
# matter behaves EXACTLY like a reference that resolves to nothing (a new matter
# plus the same note), so nothing in the response, the prompt or the logs can be
# used to probe whether a given reference exists.
# ---------------------------------------------------------------------------

#: How many claimed references we are willing to look up for one message. The
#: parser already caps what it hands us (``MAX_PARSED_TAGS``); restating a
#: SMALLER number here would silently ignore tags the parser deliberately kept,
#: so the two are the same bound by construction.
_MAX_CLAIM_LOOKUPS = MAX_PARSED_TAGS


@dataclass(frozen=True)
class ResolvedAttachment:
    """Where an inbound message on a NEW provider thread belongs.

    ``project_id``/``agent_thread_id`` set ⇒ attach: a new ``intake_threads``
    row is created on that existing matter and carries its agent conversation
    forward. ``claimed_reference`` set ⇒ the sender named a matter we did NOT
    honour; the note reaches the agent through the intake prompt.
    """

    project_id: uuid.UUID | None = None
    agent_thread_id: uuid.UUID | None = None
    claimed_reference: str | None = None
    layer: str = "none"


async def _agent_thread_for_project(db: AsyncSession, project_id: uuid.UUID) -> uuid.UUID | None:
    """The agent conversation this matter's intake threads already run on.

    INTAKE-3 reuses one ``agent_thread_id`` per intake thread so follow-ups
    continue the same conversation; carrying it onto a NEW thread row on the
    same matter extends that property to a reply that arrived out of band.
    """

    return (
        await db.execute(
            select(IntakeThread.agent_thread_id)
            .where(
                IntakeThread.project_id == project_id,
                IntakeThread.agent_thread_id.is_not(None),
            )
            .order_by(IntakeThread.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _resolve_by_threading_headers(
    db: AsyncSession,
    *,
    mailbox_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    headers: dict[str, str],
) -> uuid.UUID | None:
    """Layer 2 — a message id WE ISSUED, in this mailbox, on this owner's matter.

    ``direction == 'out'`` is the whole strength of this layer. What makes the
    signal strong is not that we recognise the id but that WE MINTED it: an id
    from one of our own outbound replies can only be in a sender's
    ``References`` chain because they actually received that reply. An INBOUND
    id proves nothing — the sender chose it themselves, so anyone who once wrote
    to this inbox (or simply guesses the shape a provider mints) could quote
    their own earlier id back and be filed into whatever matter it opened.
    Matching those would quietly demote layer 2 to layer-3 strength while
    keeping layer-2 privileges (attaching with no Roster check).

    Doubly fenced besides — ``mailbox_id`` (this queue's own threads) AND the
    matter's owner (this queue's owner). The second is belt and braces for the
    case where a mailbox was re-bound to a different owner after producing
    matters: an attach must never file new mail into someone else's matter.
    """

    candidates = parse_threading_headers(headers.get("In-Reply-To"), headers.get("References"))
    if not candidates:
        return None
    return (
        await db.execute(
            select(IntakeThread.project_id)
            .join(IntakeMessage, IntakeMessage.thread_id == IntakeThread.id)
            .join(Project, Project.id == IntakeThread.project_id)
            .where(
                IntakeMessage.provider_message_id.in_(candidates),
                IntakeMessage.direction == "out",
                IntakeThread.mailbox_id == mailbox_id,
                Project.owner_id == owner_user_id,
            )
            .order_by(IntakeMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _sender_on_roster(db: AsyncSession, *, project_id: uuid.UUID, from_addr: str) -> bool:
    """Whether the sender is a HUMAN-CONFIRMED roster member of this matter.

    This is the only thing standing between a stranger's subject tag and a
    matter that may hold privileged material, so it is deliberately narrow on
    three axes:

    * **Addresses only.** A roster alias is a match STRING, not necessarily an
      address — ADR-F048 stores the tracked-change author strings a person
      writes under, which are routinely display names (``"Legal"``,
      ``"J. Smith"``). Comparing a sender against those would let anyone whose
      display name happens to collide pass an identity check, so both sides
      must look like an address (:func:`looks_like_address`) before they are
      compared at all.
    * **Confirmed participants only.** ``trust='inferred'`` rows were written by
      the agent from document metadata — i.e. derived from the same untrusted
      material an attacker can supply (a .docx whose author string they chose).
      Letting an inferred row open this gate would close the loop: send a
      document, get yourself onto the roster, then quote the reference. Only a
      human-confirmed row counts. (An inferred participant is still a real
      roster entry everywhere else; it just cannot authorise an attach.)
    * **Active rows only.** A retired participant (``superseded_at``) has been
      taken off the matter deliberately.

    Matched in Python over the JSONB alias lists — aliases are untrusted text
    and never reach a SQL predicate (ADR-F048) — case- and display-name-
    insensitively on both sides.
    """

    sender = normalise_address(from_addr)
    if not looks_like_address(sender):
        return False
    alias_lists = (
        await db.execute(
            select(MatterParticipant.aliases).where(
                MatterParticipant.project_id == project_id,
                MatterParticipant.superseded_at.is_(None),
                MatterParticipant.trust == "confirmed",
            )
        )
    ).scalars()
    for aliases in alias_lists:
        for alias in aliases or []:
            if not isinstance(alias, str):
                continue
            candidate = normalise_address(alias)
            if looks_like_address(candidate) and candidate == sender:
                return True
    return False


async def _resolve_by_claimed_reference(
    db: AsyncSession, *, owner_user_id: uuid.UUID, envelope: InboundEmailEnvelope
) -> tuple[uuid.UUID | None, str, str | None]:
    """Layer 3 — a subject tag or plus-tagged recipient, gated on the Roster.

    Returns ``(project_id, layer, claimed_reference)``, where ``layer`` names the
    signal that actually decided (``subject_tag`` / ``plus_tag`` / ``none``). A
    claim that resolves to nothing THIS queue owns, and a claim whose sender is
    not on the roster, are treated identically: no attach, and the claim is
    recorded for the agent to raise with the lawyer. That sameness is the
    anti-probe property.
    """

    # (reference, where it came from) — the origin travels with each claim so the
    # log names the signal that ACTUALLY decided, not merely the first one present.
    claims: list[tuple[str, str]] = [
        (tag, "subject_tag") for tag in parse_reference_tags(envelope.thread.subject)
    ]
    seen = {tag for tag, _ in claims}
    for tag in parse_plus_tags(list(envelope.message.to) + list(envelope.message.cc)):
        if tag not in seen:
            claims.append((tag, "plus_tag"))
            seen.add(tag)
    if not claims:
        return None, "none", None

    for tag, origin in claims[:_MAX_CLAIM_LOOKUPS]:
        project_id = (
            await db.execute(
                select(Project.id).where(
                    Project.reference == tag,
                    Project.owner_id == owner_user_id,
                )
            )
        ).scalar_one_or_none()
        if project_id is None:
            continue
        if await _sender_on_roster(db, project_id=project_id, from_addr=envelope.message.from_addr):
            return project_id, origin, None
    first_tag, first_origin = claims[0]
    return None, first_origin, first_tag


async def resolve_inbound_attachment(
    db: AsyncSession,
    *,
    mailbox_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    envelope: InboundEmailEnvelope,
) -> ResolvedAttachment:
    """Run the layer-2/layer-3 ladder for a message on a NEW provider thread."""

    project_id = await _resolve_by_threading_headers(
        db,
        mailbox_id=mailbox_id,
        owner_user_id=owner_user_id,
        headers=envelope.message.headers,
    )
    if project_id is not None:
        return ResolvedAttachment(
            project_id=project_id,
            agent_thread_id=await _agent_thread_for_project(db, project_id),
            layer="threading_headers",
        )

    project_id, layer, claimed = await _resolve_by_claimed_reference(
        db, owner_user_id=owner_user_id, envelope=envelope
    )
    if project_id is not None:
        return ResolvedAttachment(
            project_id=project_id,
            agent_thread_id=await _agent_thread_for_project(db, project_id),
            layer=layer,
        )
    return ResolvedAttachment(claimed_reference=claimed, layer=layer)


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
        # INTAKE-4a (ADR-F088): this message opens a NEW provider thread — run the
        # trust ladder before deciding it is a new matter. Layers 2/3 may land it
        # on an EXISTING matter (a reply from a fresh compose, a forward carrying
        # the tag), in which case the new thread row also inherits that matter's
        # agent conversation so the same run history continues.
        resolved = await resolve_inbound_attachment(
            db, mailbox_id=mailbox_id, owner_user_id=owner_user_id, envelope=envelope
        )
        thread = IntakeThread(
            mailbox_id=mailbox_id,
            provider_thread_id=envelope.thread.provider_thread_id,
            subject=envelope.thread.subject,
            message_count=0,
            project_id=resolved.project_id,
            agent_thread_id=resolved.agent_thread_id,
            claimed_reference=resolved.claimed_reference,
        )
        db.add(thread)
        log.info(
            "intake email thread resolution",
            extra={
                "event": "intake_email_resolved",
                "mailbox_id": str(mailbox_id),
                "layer": resolved.layer,
                "attached": resolved.project_id is not None,
                "claim_recorded": resolved.claimed_reference is not None,
            },
        )
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
        # INTAKE-4a (ADR-F088): the two allowlisted threading headers, persisted so
        # a LATER message that lands on a new provider thread can be matched back
        # to this one (layer 2). Opaque strings — compared, never interpreted.
        in_reply_to=envelope.message.headers.get("In-Reply-To"),
        references_header=envelope.message.headers.get("References"),
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
            # INTAKE-4a (ADR-F088): an intake-born matter gets its reference the
            # same way a cockpit-created one does — one allocator, one series.
            #
            # LOCK WINDOW, deliberately accepted: the allocator holds a row lock
            # on this area's counter until THIS request commits, which is after
            # the attachment loop below has uploaded to object storage. Two
            # first-messages arriving on the same area therefore serialise behind
            # each other's uploads. It is bounded by the envelope caps (at most
            # 10 attachments, 50 MB decoded per envelope — app.schemas.intake)
            # and by intake volumes measured in emails per hour, and the
            # alternative — flushing the matter with a NULL reference and
            # stamping it just before commit — buys a shorter lock at the price
            # of a matter that briefly exists without one. If intake ever runs
            # hot enough for this to bite, make that trade then, not now.
            reference = await allocate_reference(db, practice_area_id=practice_area_id)
            project = Project(
                owner_id=owner_user_id,
                practice_area_id=practice_area_id,
                name=project_name,
                slug=final_slug,
                intake_state="candidate",
                reference=reference,
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
