"""Users endpoints — Task B1 + D6.

`/users/me` (B1) returns the calling user's public profile.

D6 lands the GDPR Article 17 / 20 surface:

* `POST /api/v1/users/me/export` queues an export job; the worker
  builds a ZIP of the user's data and uploads it to MinIO. Returns
  202 with `{job_id, status}`.
* `GET  /api/v1/users/me/export/{job_id}` polls a job. When complete,
  returns a presigned download URL good for 24 hours.
* `POST /api/v1/users/me/delete` schedules account deletion: sets
  `deletion_scheduled_at = now() + grace_period_days`, revokes all
  active sessions, audit-logs the request. Idempotent — re-calling
  returns the existing schedule rather than pushing it back.
* `POST /api/v1/users/me/delete/cancel` clears a pending deletion
  during the grace period.

Hard delete itself happens in the daily worker cron
(`app.workers.user_deletion.hard_delete_due_users_job`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserPublic
from app.api.dependencies import CurrentUser, get_active_user
from app.audit import audit_action
from app.config import get_settings
from app.db.session import get_db
from app.models.user import UserSession
from app.models.user_export import UserExportJob
from app.storage import presigned_get_url
from app.workers.queue import enqueue_user_export_job

router = APIRouter(prefix="/users", tags=["users"])

# Presigned download URL TTL for completed export bundles. 24 hours
# matches the brief and keeps the URL useful across timezone changes
# without leaving it valid long enough to be inadvertently shared.
_DOWNLOAD_URL_TTL_SECONDS = 24 * 3600


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ExportJobResponse(BaseModel):
    """Shared shape for POST /users/me/export and GET /users/me/export/{id}.

    The ``download_url`` is populated only when ``status == 'completed'``
    and the bundle has not yet expired.
    """

    job_id: str
    status: str
    download_url: str | None = None


class DeleteScheduledResponse(BaseModel):
    """Body for POST /users/me/delete (and the idempotent rerun)."""

    scheduled_deletion_at: datetime
    grace_period_days: int


# ---------------------------------------------------------------------------
# /users/me
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get current user",
)
async def get_me(user: CurrentUser) -> UserPublic:
    """GET /api/v1/users/me — return the calling user's public profile.

    Reachable while `must_change_password=true` so the client can read the
    flag and route to the change-password flow. Other authenticated
    endpoints are gated until the user clears it.
    """

    return UserPublic.from_user(user)


# ---------------------------------------------------------------------------
# /users/me/export — D6 GDPR Article 20
# ---------------------------------------------------------------------------


@router.post(
    "/me/export",
    response_model=ExportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(get_active_user)],
    summary="Queue a per-user data export",
)
async def export_me(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExportJobResponse:
    """POST /api/v1/users/me/export — async; returns a job id for polling.

    Inserts a `user_export_jobs` row with status='queued', enqueues the
    arq worker job, and returns 202. The worker runs the ZIP build +
    MinIO upload out-of-band.

    Re-calling while a queued/processing job exists is allowed —
    operators may want a fresh export after deleting some content.
    The two jobs run independently.
    """

    job = UserExportJob(user_id=user.id, status="queued")
    db.add(job)
    await db.flush()

    await audit_action(
        db,
        user_id=user.id,
        action="user.export_requested",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={"job_id": str(job.id)},
    )
    await db.commit()

    await enqueue_user_export_job(job.id)

    return ExportJobResponse(job_id=str(job.id), status=job.status, download_url=None)


@router.get(
    "/me/export/{job_id}",
    response_model=ExportJobResponse,
    dependencies=[Depends(get_active_user)],
    summary="Poll a user-export job",
)
async def get_export_job(
    job_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExportJobResponse:
    """GET /api/v1/users/me/export/{job_id}.

    Returns 404 if the job doesn't exist or belongs to another user
    (don't leak existence cross-user). On a completed job, returns a
    presigned download URL valid for 24h. On a job whose bundle has
    expired (storage_key cleared by the GC cron), the response carries
    no URL and the status remains 'completed' for audit clarity — the
    caller can re-request export to get a fresh bundle.
    """

    try:
        job_uuid = uuid.UUID(job_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found"
        ) from None

    job = await db.get(UserExportJob, job_uuid)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")

    download_url: str | None = None
    if job.status == "completed" and job.storage_key:
        download_url = await presigned_get_url(
            storage_path=job.storage_key,
            expires_in_seconds=_DOWNLOAD_URL_TTL_SECONDS,
        )

    return ExportJobResponse(
        job_id=str(job.id),
        status=job.status,
        download_url=download_url,
    )


# ---------------------------------------------------------------------------
# /users/me/delete — D6 GDPR Article 17
# ---------------------------------------------------------------------------


@router.post(
    "/me/delete",
    response_model=DeleteScheduledResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(get_active_user)],
    summary="Schedule account deletion (GDPR Article 17)",
)
async def delete_me(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeleteScheduledResponse:
    """POST /api/v1/users/me/delete — soft-schedule with a grace period.

    Idempotent: if the user already has a pending deletion the existing
    schedule is returned. This prevents accidental "extension" of the
    grace period via repeated calls.

    Side-effects:

    1. ``deletion_scheduled_at = now() + gdpr_grace_period_days``.
    2. All of the user's active ``user_sessions`` are revoked. The user
       can still log in during the grace period (to call cancel) — the
       gate is on ``deleted_at``, not ``deletion_scheduled_at``.
    3. An ``audit_log`` row records the request.

    Login during the grace period is preserved so the user retains the
    ability to cancel; hard delete itself runs in the daily worker
    cron.
    """

    settings = get_settings()
    grace = settings.gdpr_grace_period_days

    if user.deletion_scheduled_at is not None:
        return DeleteScheduledResponse(
            scheduled_deletion_at=user.deletion_scheduled_at,
            grace_period_days=grace,
        )

    scheduled = _utcnow() + timedelta(days=grace)
    user.deletion_scheduled_at = scheduled

    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )

    await audit_action(
        db,
        user_id=user.id,
        action="user.deletion_scheduled",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={
            "scheduled_deletion_at": scheduled.isoformat(),
            "grace_period_days": grace,
        },
    )
    await db.commit()

    return DeleteScheduledResponse(
        scheduled_deletion_at=scheduled,
        grace_period_days=grace,
    )


@router.post(
    "/me/delete/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_active_user)],
    summary="Cancel a pending account deletion",
)
async def cancel_delete_me(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """POST /api/v1/users/me/delete/cancel — clear a pending schedule.

    Returns 400 if there is no pending deletion. The grace-period
    window itself is the only valid cancel surface — once the worker
    has hard-deleted the user, there is no row to recover.
    """

    if user.deletion_scheduled_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending deletion to cancel.",
        )

    user.deletion_scheduled_at = None
    await audit_action(
        db,
        user_id=user.id,
        action="user.deletion_cancelled",
        resource_type="user",
        resource_id=str(user.id),
        request=request,
    )
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
