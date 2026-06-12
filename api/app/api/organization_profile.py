"""Organization Profile endpoints — Task D4.

PRD §3.12 / `docs/api/backend-openapi.yaml /api/v1/organization-profile`:

* ``GET  /api/v1/organization-profile``  — bearer-authed; returns the
  current Organization Profile (or an empty placeholder if no admin
  has set one yet). Readable by every authenticated user — the
  Profile shapes their chats and per the transparency principle
  (PRD §1.3) they're entitled to see what's framing their output.
* ``PUT  /api/v1/organization-profile``  — admin-only; upserts the
  singleton row's ``content_md``. Audit-logged via the D3 helper.
* ``GET  /api/v1/organization-profile/raw`` — convenience Markdown
  endpoint for Skill Inspector / UI surfaces (text/markdown body).

ADR 0004 keeps built-in skills filesystem-canonical so the Profile
lives in its own focused single-row table (migration 0010) rather
than as a row in a (nonexistent) ``skills`` SQL table. The gateway
fetches the Profile via the ``/api/v1/internal/organization-profile``
endpoint (separate file) and prepends it to every attached skill
unless the skill's frontmatter opts out.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser, AdminUser
from app.audit import audit_action
from app.db.session import get_db
from app.models.organization_profile import OrganizationProfile

router = APIRouter(prefix="/organization-profile", tags=["organization-profile"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class OrganizationProfileResponse(BaseModel):
    """GET response shape; PUT also returns this body on success."""

    content_md: str
    updated_at: datetime | None = None
    updated_by: str | None = None


class OrganizationProfileUpdateRequest(BaseModel):
    """PUT body. ``content_md`` is the full Markdown body (skill body).

    Empty string is allowed — operators may want to clear the Profile
    without deleting the row. The PUT is an upsert: insert if no row
    exists yet, update in place otherwise (preserving the row id so
    audit history correlates).
    """

    content_md: str = Field(min_length=0, max_length=200_000)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


async def _load_singleton(db: AsyncSession) -> OrganizationProfile | None:
    """Return the single ``organization_profile`` row, or ``None`` if unset.

    The DB enforces "at most one row" via the partial unique index on
    ``((true))``; this helper centralises the read so callers don't
    re-state the assumption.
    """

    stmt = select(OrganizationProfile).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.get(
    "",
    response_model=OrganizationProfileResponse,
    summary="Get the deployment's Organization Profile",
)
async def get_organization_profile(
    _user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationProfileResponse:
    """GET /api/v1/organization-profile — readable by any authenticated user.

    Returns ``content_md=""`` plus null timestamps when no admin has
    set a Profile yet — the read path never 404s. The transparency
    principle (PRD §1.3) requires every user to be able to see what's
    shaping their output; admins have the *write* side via PUT.
    """

    row = await _load_singleton(db)
    if row is None:
        return OrganizationProfileResponse(content_md="", updated_at=None, updated_by=None)
    return OrganizationProfileResponse(
        content_md=row.content_md,
        updated_at=row.updated_at,
        updated_by=str(row.updated_by) if row.updated_by else None,
    )


@router.put(
    "",
    response_model=OrganizationProfileResponse,
    summary="Update the Organization Profile (admin only)",
    responses={
        200: {"model": OrganizationProfileResponse},
        401: {"description": "Bearer token missing or invalid"},
        403: {"description": "Caller is not an admin"},
    },
)
async def put_organization_profile(
    payload: OrganizationProfileUpdateRequest,
    request: Request,
    user: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationProfileResponse:
    """PUT /api/v1/organization-profile — admin upsert.

    Idempotent: if a row exists, update its ``content_md`` +
    ``updated_by`` (the trigger maintains ``updated_at``); otherwise
    insert a fresh row. The singleton index guarantees the write
    converges to a single row regardless of concurrency.

    Audit-logged via the D3 helper as ``organization_profile.updated``
    so admins can trace who changed the Profile and when.
    """

    row = await _load_singleton(db)
    if row is None:
        row = OrganizationProfile(content_md=payload.content_md, updated_by=user.id)
        db.add(row)
    else:
        row.content_md = payload.content_md
        row.updated_by = user.id

    await audit_action(
        db,
        user_id=user.id,
        action="organization_profile.updated",
        resource_type="organization_profile",
        resource_id=None,
        request=request,
        details={"content_length": len(payload.content_md)},
    )
    await db.commit()
    await db.refresh(row)

    return OrganizationProfileResponse(
        content_md=row.content_md,
        updated_at=row.updated_at,
        updated_by=str(row.updated_by) if row.updated_by else None,
    )


@router.get(
    "/raw",
    response_class=Response,
    summary="Get the Profile as raw Markdown (text/markdown)",
    responses={
        200: {"content": {"text/markdown": {}}},
    },
)
async def get_organization_profile_raw(
    _user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """GET /api/v1/organization-profile/raw — content-typed Markdown.

    Convenience endpoint for the Skill Inspector (§3.4) and any UI
    surface that wants to render the Profile as Markdown without
    JSON-decoding the body. Returns an empty 200 if no Profile is
    set yet (rather than 404), consistent with the JSON GET above.
    """

    row = await _load_singleton(db)
    body = row.content_md if row is not None else ""
    return Response(
        content=body,
        media_type="text/markdown",
        status_code=status.HTTP_200_OK,
    )
