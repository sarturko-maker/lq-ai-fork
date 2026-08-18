"""Admin CRUD for intake-mailbox bindings — INTAKE-1 (ADR-F086).

Style mirrors ``api/app/api/admin_intake_bridges.py`` (the sibling admin
surface for the Slack/Teams OAuth bridge connections): every endpoint
stacks on ``ActiveUser`` (mounted at the router level in ``app.api``) plus
the ``AdminUser`` dependency at handler level. Non-admin authenticated
users see 403 ``forbidden``.

Unlike the bridge surface (which only lists/soft-deletes rows another
service upserts), the admin binds a mailbox HERE: ``POST`` creates the
``(provider, inbox_id) → practice_area, owner_user`` binding the plan
calls for; ``PATCH``/``DELETE`` manage it afterward. There is no UI for
this yet (the plan defers it) — this is the API surface only.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import AdminUser
from app.db.session import get_db
from app.errors import Conflict, NotFound
from app.models.intake import IntakeMailbox
from app.models.practice_area import PracticeArea
from app.models.user import User
from app.schemas.intake_mailboxes import (
    IntakeMailboxCreate,
    IntakeMailboxResponse,
    IntakeMailboxUpdate,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/intake-mailboxes", tags=["admin-intake-mailboxes"])


async def _load_live_owner(db: AsyncSession, owner_user_id: uuid.UUID) -> User:
    """Fetch a non-soft-deleted user by id, or raise 404.

    A soft-deleted user is not a valid mailbox owner — treated the same as
    "does not exist" (no existence leak either way).
    """

    user = (
        await db.execute(select(User).where(User.id == owner_user_id, User.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if user is None:
        raise NotFound(
            message="owner_user_id does not reference an existing user.",
            details={"owner_user_id": str(owner_user_id)},
        )
    return user


async def _load_live_mailbox(db: AsyncSession, mailbox_id: uuid.UUID) -> IntakeMailbox:
    row = (
        await db.execute(select(IntakeMailbox).where(IntakeMailbox.id == mailbox_id))
    ).scalar_one_or_none()
    if row is None or row.deleted_at is not None:
        raise NotFound(
            message="Intake mailbox not found.",
            details={"mailbox_id": str(mailbox_id)},
        )
    return row


@router.post(
    "",
    response_model=IntakeMailboxResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_intake_mailbox(
    payload: IntakeMailboxCreate,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeMailboxResponse:
    """Bind a mailbox to a practice area + owner user.

    Validates ``practice_area_id`` and ``owner_user_id`` both reference
    existing (live) rows — 404 on either miss, matching
    ``app.api.projects.create_project``'s practice-area validation. A
    collision on ``(provider, inbox_id)`` among LIVE mailboxes is a 409
    (the partial unique index is the source of truth; a pre-check gives a
    clean error and the IntegrityError catch covers the race).
    """

    area = await db.get(PracticeArea, payload.practice_area_id)
    if area is None:
        raise NotFound(
            message="practice_area_id does not reference an existing practice area.",
            details={"practice_area_id": str(payload.practice_area_id)},
        )
    await _load_live_owner(db, payload.owner_user_id)

    existing = (
        await db.execute(
            select(IntakeMailbox.id).where(
                IntakeMailbox.provider == payload.provider,
                IntakeMailbox.inbox_id == payload.inbox_id,
                IntakeMailbox.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict(
            "An active intake mailbox is already bound to this (provider, inbox_id).",
            details={"provider": payload.provider, "inbox_id": payload.inbox_id},
        )

    mailbox = IntakeMailbox(
        provider=payload.provider,
        inbox_id=payload.inbox_id,
        address=payload.address,
        practice_area_id=payload.practice_area_id,
        owner_user_id=payload.owner_user_id,
        default_budget_profile=(
            payload.default_budget_profile.value if payload.default_budget_profile else None
        ),
        max_steps=payload.max_steps,
    )
    db.add(mailbox)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(
            "An active intake mailbox is already bound to this (provider, inbox_id).",
            details={"provider": payload.provider, "inbox_id": payload.inbox_id},
        ) from exc

    await db.commit()
    await db.refresh(mailbox)

    log.info(
        "intake mailbox created",
        extra={
            "event": "intake_mailbox_created",
            "mailbox_id": str(mailbox.id),
            "provider": mailbox.provider,
            "practice_area_id": str(mailbox.practice_area_id),
            "owner_user_id": str(mailbox.owner_user_id),
        },
    )

    return IntakeMailboxResponse.model_validate(mailbox)


@router.get("", response_model=list[IntakeMailboxResponse])
async def list_intake_mailboxes(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[IntakeMailboxResponse]:
    """List live (non-soft-deleted) intake mailboxes, newest first."""

    rows = (
        (
            await db.execute(
                select(IntakeMailbox)
                .where(IntakeMailbox.deleted_at.is_(None))
                .order_by(IntakeMailbox.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [IntakeMailboxResponse.model_validate(row) for row in rows]


@router.patch("/{mailbox_id}", response_model=IntakeMailboxResponse)
async def update_intake_mailbox(
    mailbox_id: uuid.UUID,
    payload: IntakeMailboxUpdate,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntakeMailboxResponse:
    """Partial update: ``active``, ``owner_user_id``, ``default_budget_profile``, ``max_steps``.

    Only fields the caller actually sets are applied (``exclude_unset``) —
    the same partial-update idiom ``app.api.projects.update_project`` uses.
    """

    mailbox = await _load_live_mailbox(db, mailbox_id)
    update_fields = payload.model_dump(exclude_unset=True)

    if "owner_user_id" in update_fields and update_fields["owner_user_id"] is not None:
        await _load_live_owner(db, update_fields["owner_user_id"])
        mailbox.owner_user_id = update_fields["owner_user_id"]

    if "active" in update_fields:
        mailbox.active = update_fields["active"]

    if "default_budget_profile" in update_fields:
        profile = update_fields["default_budget_profile"]
        mailbox.default_budget_profile = profile.value if profile else None

    if "max_steps" in update_fields:
        mailbox.max_steps = update_fields["max_steps"]

    mailbox.updated_at = datetime.now(tz=UTC)
    await db.commit()
    await db.refresh(mailbox)

    log.info(
        "intake mailbox updated",
        extra={"event": "intake_mailbox_updated", "mailbox_id": str(mailbox.id)},
    )

    return IntakeMailboxResponse.model_validate(mailbox)


@router.delete(
    "/{mailbox_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_intake_mailbox(
    mailbox_id: uuid.UUID,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Soft-delete a mailbox binding. Idempotent: already-deleted/missing → 404."""

    mailbox = await _load_live_mailbox(db, mailbox_id)
    mailbox.deleted_at = datetime.now(tz=UTC)
    await db.commit()

    log.info(
        "intake mailbox deleted",
        extra={"event": "intake_mailbox_deleted", "mailbox_id": str(mailbox_id)},
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
