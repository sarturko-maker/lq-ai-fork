"""Team management endpoints — Task D8.1a (operator-admin only).

Per the design call recorded in SESSION-HANDOFF-2026-05-10d follow-on:
operator-admin (``is_admin=True``) creates teams and adds members.
Team-admin-marked memberships gain mutate rights on team-scope
``user_skills`` rows when D8.1b lights up the team-scope CRUD branch.
This module ships the team management surface only — the team-scope
branches in ``/api/v1/user-skills`` are deferred to D8.1b.

Two surface groups:

* ``/api/v1/admin/teams*`` — admin-gated CRUD + membership management.
  Stacks on ``AdminUser`` like the alias endpoints in ``admin.py``.
* ``/api/v1/teams*`` — read-only routes for non-admin users to see
  the teams they belong to (so the LQ.AI shell can render team
  membership without operator round-trips).

Audit writes follow the D3-coverage convention from 2026-05-10c —
every state-changing call writes an ``audit_log`` row in the same
transaction as the state change, with details enough for forensics.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser, AdminUser
from app.audit import audit_action
from app.db.session import get_db
from app.models.team import Team, TeamMember
from app.models.user import User

admin_router = APIRouter(prefix="/admin/teams", tags=["admin", "teams"])
user_router = APIRouter(prefix="/teams", tags=["teams"])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# Same shape as user-skill slugs — lowercase alphanumeric + hyphens, must
# start and end with an alphanumeric. Reserved characters can't appear so
# slugs round-trip cleanly through URLs without encoding surprises.
_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,78}[a-z0-9])?$")

_NAME_MAX = 200
_DESCRIPTION_MAX = 2_000
_VALID_ROLES = frozenset({"admin", "member"})


def _validate_slug(slug: str) -> str:
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=422,
            detail=(
                "slug must be lowercase alphanumeric with hyphens, "
                "starting and ending with an alphanumeric, max 80 chars"
            ),
        )
    return slug


def _validate_role(role: str) -> str:
    if role not in _VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"role must be one of {sorted(_VALID_ROLES)}",
        )
    return role


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TeamMemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None = None
    role: str
    added_by_user_id: uuid.UUID
    created_at: datetime


class TeamSummary(BaseModel):
    """Compact team shape for list responses."""

    id: uuid.UUID
    slug: str
    name: str
    description: str | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    member_count: int = 0


class TeamResponse(TeamSummary):
    """Full team payload including the membership roster."""

    members: list[TeamMemberResponse] = Field(default_factory=list)


class TeamCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=_NAME_MAX)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=_NAME_MAX)
    description: str | None = Field(default=None, max_length=_DESCRIPTION_MAX)


class TeamMemberAdd(BaseModel):
    user_id: uuid.UUID
    role: str = "member"


class TeamMemberRoleUpdate(BaseModel):
    role: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_team(db: AsyncSession, team_id: uuid.UUID) -> Team:
    row = await db.get(Team, team_id)
    if row is None:
        raise HTTPException(status_code=404, detail="team not found")
    return row


async def _list_members(db: AsyncSession, team_id: uuid.UUID) -> list[TeamMemberResponse]:
    """Join team_members → users so each row carries display info."""

    stmt = (
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team_id)
        .order_by(TeamMember.created_at.asc(), User.email.asc())
    )
    rows = (await db.execute(stmt)).all()
    out: list[TeamMemberResponse] = []
    for membership, user in rows:
        out.append(
            TeamMemberResponse(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=membership.role,
                added_by_user_id=membership.added_by_user_id,
                created_at=membership.created_at,
            )
        )
    return out


async def _member_count(db: AsyncSession, team_id: uuid.UUID) -> int:
    stmt = select(TeamMember).where(TeamMember.team_id == team_id)
    return len((await db.execute(stmt)).scalars().all())


def _summary(row: Team, member_count: int = 0) -> TeamSummary:
    return TeamSummary(
        id=row.id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        member_count=member_count,
    )


# ---------------------------------------------------------------------------
# Admin endpoints — full CRUD + membership management
# ---------------------------------------------------------------------------


@admin_router.get(
    "",
    response_model=list[TeamSummary],
    summary="List every team in the deployment (admin)",
)
async def list_teams(
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TeamSummary]:
    stmt = select(Team).order_by(Team.created_at.desc(), Team.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    summaries: list[TeamSummary] = []
    for row in rows:
        count = await _member_count(db, row.id)
        summaries.append(_summary(row, count))
    return summaries


@admin_router.post(
    "",
    response_model=TeamResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new team (admin)",
)
async def create_team(
    payload: TeamCreate,
    request: Request,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamResponse:
    slug = _validate_slug(payload.slug)
    row = Team(
        slug=slug,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        created_by_user_id=admin.id,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a team with slug {slug!r} already exists",
        ) from None

    # The creating admin is automatically added as a team-admin member —
    # without this, the team has zero members and the operator has to
    # add themselves before any member-driven flow can exercise. Keeps
    # the first-creation path frictionless.
    membership = TeamMember(
        team_id=row.id,
        user_id=admin.id,
        role="admin",
        added_by_user_id=admin.id,
    )
    db.add(membership)
    await db.flush()

    await audit_action(
        db,
        user_id=admin.id,
        action="team.created",
        resource_type="team",
        resource_id=str(row.id),
        request=request,
        details={
            "slug": slug,
            "name": row.name,
            "creator_added_as_admin_member": True,
        },
    )
    await db.commit()
    await db.refresh(row)

    members = await _list_members(db, row.id)
    return TeamResponse(
        **_summary(row, len(members)).model_dump(),
        members=members,
    )


@admin_router.get(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Fetch a team with its membership roster (admin)",
)
async def get_team(
    team_id: uuid.UUID,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamResponse:
    row = await _load_team(db, team_id)
    members = await _list_members(db, team_id)
    return TeamResponse(
        **_summary(row, len(members)).model_dump(),
        members=members,
    )


@admin_router.patch(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Update a team's name or description (admin)",
)
async def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdate,
    request: Request,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamResponse:
    row = await _load_team(db, team_id)

    changed: dict[str, Any] = {}
    if payload.name is not None:
        new_name = payload.name.strip()
        if new_name != row.name:
            row.name = new_name
            changed["name"] = new_name
    if payload.description is not None:
        new_description = payload.description.strip() if payload.description else None
        if new_description != row.description:
            row.description = new_description
            changed["description"] = new_description

    if changed:
        await audit_action(
            db,
            user_id=admin.id,
            action="team.updated",
            resource_type="team",
            resource_id=str(row.id),
            request=request,
            details={"slug": row.slug, "changed_fields": sorted(changed.keys())},
        )
    await db.commit()
    await db.refresh(row)

    members = await _list_members(db, team_id)
    return TeamResponse(
        **_summary(row, len(members)).model_dump(),
        members=members,
    )


@admin_router.delete(
    "/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a team (admin); CASCADES to memberships + team-scope skills",
)
async def delete_team(
    team_id: uuid.UUID,
    request: Request,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    row = await _load_team(db, team_id)
    slug = row.slug
    name = row.name

    # Audit BEFORE deletion so the row's identity is captured even though
    # the resource_id will point at a now-gone row. CASCADEs handle the
    # rest (team_members + user_skills with scope='team').
    await audit_action(
        db,
        user_id=admin.id,
        action="team.deleted",
        resource_type="team",
        resource_id=str(team_id),
        request=request,
        details={"slug": slug, "name": name},
    )
    await db.delete(row)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a user to a team (admin)",
)
async def add_member(
    team_id: uuid.UUID,
    payload: TeamMemberAdd,
    request: Request,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamMemberResponse:
    await _load_team(db, team_id)
    role = _validate_role(payload.role)

    target = await db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )

    membership = TeamMember(
        team_id=team_id,
        user_id=payload.user_id,
        role=role,
        added_by_user_id=admin.id,
    )
    db.add(membership)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="user is already a member of this team",
        ) from None

    await audit_action(
        db,
        user_id=admin.id,
        action="team.member_added",
        resource_type="team",
        resource_id=str(team_id),
        request=request,
        details={
            "user_id": str(payload.user_id),
            "user_email": target.email,
            "role": role,
        },
    )
    await db.commit()
    await db.refresh(membership)

    return TeamMemberResponse(
        user_id=target.id,
        email=target.email,
        display_name=target.display_name,
        role=membership.role,
        added_by_user_id=membership.added_by_user_id,
        created_at=membership.created_at,
    )


@admin_router.patch(
    "/{team_id}/members/{user_id}",
    response_model=TeamMemberResponse,
    summary="Change a member's role within a team (admin)",
)
async def update_member_role(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: TeamMemberRoleUpdate,
    request: Request,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamMemberResponse:
    role = _validate_role(payload.role)
    stmt = select(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id
    )
    membership = (await db.execute(stmt)).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user is not a member of this team",
        )

    if membership.role == role:
        # No-op — return current state without writing audit (mirrors the
        # idempotent-PATCH pattern from user_skills + saved_prompts).
        user = await db.get(User, user_id)
        assert user is not None  # FK guarantees existence
        return TeamMemberResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            added_by_user_id=membership.added_by_user_id,
            created_at=membership.created_at,
        )

    old_role = membership.role
    membership.role = role
    user = await db.get(User, user_id)
    assert user is not None

    await audit_action(
        db,
        user_id=admin.id,
        action="team.member_role_changed",
        resource_type="team",
        resource_id=str(team_id),
        request=request,
        details={
            "user_id": str(user_id),
            "user_email": user.email,
            "role_before": old_role,
            "role_after": role,
        },
    )
    await db.commit()

    return TeamMemberResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=role,
        added_by_user_id=membership.added_by_user_id,
        created_at=membership.created_at,
    )


@admin_router.delete(
    "/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a user from a team (admin)",
)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    stmt = select(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id
    )
    membership = (await db.execute(stmt)).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user is not a member of this team",
        )

    target = await db.get(User, user_id)
    assert target is not None

    await audit_action(
        db,
        user_id=admin.id,
        action="team.member_removed",
        resource_type="team",
        resource_id=str(team_id),
        request=request,
        details={
            "user_id": str(user_id),
            "user_email": target.email,
            "role_at_removal": membership.role,
        },
    )
    await db.delete(membership)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# User-facing read endpoints — "what teams am I in?"
# ---------------------------------------------------------------------------


@user_router.get(
    "",
    response_model=list[TeamSummary],
    summary="List teams the caller belongs to (newest first)",
)
async def list_my_teams(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TeamSummary]:
    stmt = (
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
        .order_by(Team.created_at.desc(), Team.id.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    summaries: list[TeamSummary] = []
    for row in rows:
        count = await _member_count(db, row.id)
        summaries.append(_summary(row, count))
    return summaries


@user_router.get(
    "/{team_id}",
    response_model=TeamResponse,
    summary="Fetch a team the caller belongs to (with roster)",
    responses={404: {"description": "Team does not exist OR you are not a member"}},
)
async def get_my_team(
    team_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamResponse:
    # Conflate "no such team" with "not a member" so id-probing can't
    # enumerate teams the caller isn't in (same id-probing-safe posture
    # as user_skills / saved_prompts / chats).
    stmt = (
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(Team.id == team_id, TeamMember.user_id == user.id)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="team not found")
    members = await _list_members(db, team_id)
    return TeamResponse(
        **_summary(row, len(members)).model_dump(),
        members=members,
    )
