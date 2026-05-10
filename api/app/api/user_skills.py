"""User-skill management endpoints — Task D8 (ADR 0012).

CRUD surface for the caller's user-scope skills. These rows shadow
filesystem-canonical built-ins on slug collision when resolved for
the owning user's chats; other users continue to see the built-in.
See ``docs/adr/0012-db-backed-user-skills.md`` for the full design.

The read-side merge — listing built-ins + user shadows together for
the skill picker — lives in ``api/app/api/skills.py``. The
``POST /api/v1/skills/{slug}/fork`` operation likewise lives in that
module because the URL form ``/skills/<built-in slug>/fork`` reads
better as "fork this specific built-in" than a generic
``/user-skills`` write.

This router is mounted under ``ActiveUser`` at the include site, so
every handler inherits the B1 bearer-token check + the B2 must-change-
password gate. Cross-user reads/writes are blocked by filtering on
``owner_user_id`` in addition to the gate (defense in depth, matches
the chats / projects / saved_prompts pattern).

Audit logging follows the D3-coverage convention from 2026-05-10c —
every state-changing path writes an ``audit_log`` row. The
``user_skill.created`` / ``user_skill.updated`` / ``user_skill.deleted``
actions ride the same single-transaction commit as the row change.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser
from app.audit import audit_action
from app.db.session import get_db
from app.models.user_skill import UserSkill

router = APIRouter(prefix="/user-skills", tags=["user-skills"])


# ---------------------------------------------------------------------------
# Validation bounds
# ---------------------------------------------------------------------------

# Slug shape mirrors the filesystem skill folder-naming convention:
# lowercase ASCII letters, digits, and hyphens; must start and end with
# an alphanumeric. 80 chars is generous against the ~20-char names in
# the starter corpus and short enough to fit comfortably in UI chips.
_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,78}[a-z0-9])?$")

_NAME_MAX = 200
_DESCRIPTION_MAX = 2_000
_VERSION_MAX = 50
_TAG_MAX = 50
_MAX_TAGS = 20
# Skill bodies are markdown system-prompt chunks. Filesystem skills
# typically run 1-30KB; 200KB is the ceiling that catches accidental
# whole-document pastes without rejecting any reasonable authoring.
_BODY_MAX = 200_000
# Arbitrary ``lq_ai:`` extension keys (jurisdiction, output_format, etc.)
# land in this JSONB column. 16KB is plenty for the corpus reality and
# rejects pathological payloads.
_FRONTMATTER_EXTRA_MAX_BYTES = 16_384


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class UserSkillResponse(BaseModel):
    """Full row view — what the management UI consumes.

    Distinct from the ``Skill`` shape returned by the merged picker
    endpoint (``GET /api/v1/skills/{slug}``) because this view is
    designed for *editing*: every column is here, no synthesis,
    nothing dropped for compactness.
    """

    id: uuid.UUID
    scope: str
    owner_user_id: uuid.UUID
    slug: str
    display_name: str
    description: str
    version: str
    tags: list[str] = Field(default_factory=list)
    frontmatter_extra: dict[str, Any] = Field(default_factory=dict)
    body: str
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserSkillCreate(BaseModel):
    """POST body. Required fields mirror the minimum needed to render
    a Skill-shaped payload to the gateway during prompt assembly."""

    slug: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=_NAME_MAX)
    description: str = Field(min_length=1, max_length=_DESCRIPTION_MAX)
    body: str = Field(min_length=1, max_length=_BODY_MAX)
    version: str = Field(default="1.0.0", min_length=1, max_length=_VERSION_MAX)
    tags: list[str] = Field(default_factory=list, max_length=_MAX_TAGS)
    frontmatter_extra: dict[str, Any] = Field(default_factory=dict)


class UserSkillUpdate(BaseModel):
    """PATCH body. Every field is optional; only the supplied keys move."""

    display_name: str | None = Field(default=None, min_length=1, max_length=_NAME_MAX)
    description: str | None = Field(default=None, min_length=1, max_length=_DESCRIPTION_MAX)
    body: str | None = Field(default=None, min_length=1, max_length=_BODY_MAX)
    version: str | None = Field(default=None, min_length=1, max_length=_VERSION_MAX)
    tags: list[str] | None = Field(default=None, max_length=_MAX_TAGS)
    frontmatter_extra: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _validate_tags(tags: list[str]) -> list[str]:
    """Normalise + validate tags. Dedupes preserving first-seen order."""

    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        if not isinstance(raw, str):
            raise HTTPException(status_code=422, detail="tag values must be strings")
        tag = raw.strip()
        if not tag:
            raise HTTPException(status_code=422, detail="tag values must be non-empty")
        if len(tag) > _TAG_MAX:
            raise HTTPException(
                status_code=422,
                detail=f"tag values must be at most {_TAG_MAX} characters",
            )
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def _validate_frontmatter_extra(extra: dict[str, Any]) -> dict[str, Any]:
    """Reject pathologically large extension blobs.

    Keys/values are arbitrary JSON; the only guard at this layer is a
    serialized-size ceiling so a runaway client can't burn a JSONB
    page on a single row. The Pydantic ``dict[str, Any]`` typing
    already rejects non-dict bodies.
    """

    import json  # local — only this validator needs it

    encoded = json.dumps(extra, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > _FRONTMATTER_EXTRA_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"frontmatter_extra exceeds the {_FRONTMATTER_EXTRA_MAX_BYTES}-byte "
                "serialized ceiling for a single user skill"
            ),
        )
    return extra


def _to_response(row: UserSkill) -> UserSkillResponse:
    return UserSkillResponse(
        id=row.id,
        scope=row.scope,
        owner_user_id=row.owner_user_id,  # type: ignore[arg-type]  # narrowed by scope='user'
        slug=row.slug,
        display_name=row.display_name,
        description=row.description,
        version=row.version,
        tags=list(row.tags or []),
        frontmatter_extra=dict(row.frontmatter_extra or {}),
        body=row.body,
        archived_at=row.archived_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _load_owned(
    db: AsyncSession,
    *,
    skill_id: uuid.UUID,
    user_id: uuid.UUID,
    include_archived: bool = False,
) -> UserSkill:
    """Fetch a user-skill row by id; 404 if missing OR not owned.

    Conflating "no such id" with "exists but not yours" matches the
    privacy posture in saved_prompts / chats / projects — id-probing
    can't enumerate other users' rows.
    """

    stmt = select(UserSkill).where(
        UserSkill.id == skill_id,
        UserSkill.scope == "user",
        UserSkill.owner_user_id == user_id,
    )
    if not include_archived:
        stmt = stmt.where(UserSkill.archived_at.is_(None))
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user skill not found"
        )
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[UserSkillResponse],
    summary="List the caller's user-scope skills (newest first)",
)
async def list_user_skills(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserSkillResponse]:
    """GET /api/v1/user-skills — the caller's non-archived user skills.

    Sort: ``updated_at DESC`` then ``id DESC`` for deterministic tie-
    breaking (mirrors the saved_prompts convention).
    """

    stmt = (
        select(UserSkill)
        .where(
            UserSkill.scope == "user",
            UserSkill.owner_user_id == user.id,
            UserSkill.archived_at.is_(None),
        )
        .order_by(UserSkill.updated_at.desc(), UserSkill.id.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows]


@router.get(
    "/{skill_id}",
    response_model=UserSkillResponse,
    summary="Fetch a single user-scope skill (owner-only)",
    responses={404: {"description": "User skill not found"}},
)
async def get_user_skill(
    skill_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSkillResponse:
    row = await _load_owned(db, skill_id=skill_id, user_id=user.id)
    return _to_response(row)


@router.post(
    "",
    response_model=UserSkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user-scope skill",
)
async def create_user_skill(
    payload: UserSkillCreate,
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSkillResponse:
    """POST /api/v1/user-skills — create a fresh user-scope skill.

    Slug collision with a filesystem built-in is **allowed** — that's the
    shadow case per ADR 0012. Slug collision with the caller's own
    non-archived user-scope skills returns 409 (uniqueness violation
    surfaced by the partial UNIQUE index).
    """

    slug = _validate_slug(payload.slug)
    tags = _validate_tags(payload.tags)
    frontmatter_extra = _validate_frontmatter_extra(payload.frontmatter_extra)

    row = UserSkill(
        scope="user",
        owner_user_id=user.id,
        slug=slug,
        display_name=payload.display_name.strip(),
        description=payload.description.strip(),
        version=payload.version.strip(),
        tags=tags,
        frontmatter_extra=frontmatter_extra,
        body=payload.body,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"a user skill named {slug!r} already exists for this user",
        ) from None

    await audit_action(
        db,
        user_id=user.id,
        action="user_skill.created",
        resource_type="user_skill",
        resource_id=str(row.id),
        request=request,
        details={"slug": slug, "version": row.version, "tags": tags},
    )
    await db.commit()
    await db.refresh(row)

    return _to_response(row)


@router.patch(
    "/{skill_id}",
    response_model=UserSkillResponse,
    summary="Update a user-scope skill (partial; owner-only)",
    responses={404: {"description": "User skill not found"}},
)
async def update_user_skill(
    skill_id: uuid.UUID,
    payload: UserSkillUpdate,
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSkillResponse:
    """PATCH /api/v1/user-skills/{id} — partial update.

    The audit row's ``details.version_before`` / ``version_after`` make
    the *fact* of edits forensically traceable per ADR 0012 §5; the
    *content* of prior versions is not preserved (no history table in
    D8). An idempotent PATCH with no actual changes returns the current
    row without writing an audit row.
    """

    row = await _load_owned(db, skill_id=skill_id, user_id=user.id)

    changed: dict[str, Any] = {}
    version_before: str | None = None
    if payload.display_name is not None:
        new_value = payload.display_name.strip()
        if new_value != row.display_name:
            row.display_name = new_value
            changed["display_name"] = new_value
    if payload.description is not None:
        new_value = payload.description.strip()
        if new_value != row.description:
            row.description = new_value
            changed["description"] = new_value
    if payload.body is not None and payload.body != row.body:
        row.body = payload.body
        changed["body_length"] = len(payload.body)
    if payload.version is not None:
        new_value = payload.version.strip()
        if new_value != row.version:
            version_before = row.version
            row.version = new_value
            changed["version"] = new_value
    if payload.tags is not None:
        new_tags = _validate_tags(payload.tags)
        if new_tags != list(row.tags or []):
            row.tags = new_tags
            changed["tags"] = new_tags
    if payload.frontmatter_extra is not None:
        new_extra = _validate_frontmatter_extra(payload.frontmatter_extra)
        if new_extra != dict(row.frontmatter_extra or {}):
            row.frontmatter_extra = new_extra
            changed["frontmatter_extra"] = new_extra

    if not changed:
        return _to_response(row)

    details: dict[str, Any] = {
        "slug": row.slug,
        "changed_fields": sorted(changed.keys()),
    }
    if version_before is not None:
        details["version_before"] = version_before
        details["version_after"] = row.version

    await audit_action(
        db,
        user_id=user.id,
        action="user_skill.updated",
        resource_type="user_skill",
        resource_id=str(row.id),
        request=request,
        details=details,
    )
    await db.commit()
    await db.refresh(row)

    return _to_response(row)


@router.delete(
    "/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a user-scope skill (owner-only)",
    responses={
        404: {"description": "User skill not found"},
        410: {"description": "User skill is already archived"},
    },
)
async def delete_user_skill(
    skill_id: uuid.UUID,
    request: Request,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """DELETE /api/v1/user-skills/{id} — soft-delete via ``archived_at``.

    Archived rows free the slug for a new user skill at the same slug.
    The audit log preserves the row's identity so deletion is traceable
    even after the slug has been reused.
    """

    row = await _load_owned(
        db, skill_id=skill_id, user_id=user.id, include_archived=True
    )
    if row.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="user skill is already archived",
        )

    row.archived_at = datetime.now(timezone.utc)

    await audit_action(
        db,
        user_id=user.id,
        action="user_skill.deleted",
        resource_type="user_skill",
        resource_id=str(row.id),
        request=request,
        details={"slug": row.slug, "version": row.version},
    )
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
