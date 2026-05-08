"""Projects endpoints — Task C7 (Project service).

Surface (per ``docs/api/backend-openapi.yaml``):

* ``POST   /api/v1/projects``                          — create.
* ``GET    /api/v1/projects?archived=true|false``      — list (default
  excludes archived; ``archived=true`` returns archived only;
  ``archived=`` (absent) returns active only).
* ``GET    /api/v1/projects/{project_id}``             — fetch single
  including attached file ids and skill names.
* ``PATCH  /api/v1/projects/{project_id}``             — partial update
  (name, slug, description, context_md, privileged,
  minimum_inference_tier, archived).
* ``DELETE /api/v1/projects/{project_id}``             — soft-delete
  (set ``archived_at``); idempotent — already-archived returns 404.

* ``POST   /api/v1/projects/{project_id}/files``       — attach a file
  (body: ``{file_id}``).
* ``DELETE /api/v1/projects/{project_id}/files/{file_id}`` — detach.

* ``POST   /api/v1/projects/{project_id}/skills``      — attach a skill
  by name; validates the skill exists in the in-memory registry.
* ``DELETE /api/v1/projects/{project_id}/skills/{skill_name}`` — detach.

All endpoints inherit the auth+gate from the router-level
``Depends(get_active_user)`` in ``app.api.__init__`` (B2 pattern). Each
handler also takes ``ActiveUser`` directly so the user object is
available for ``owner_id`` checks (FastAPI dedupes the dependency).

**Per-user isolation.** Projects are scoped to ``owner_id``. Cross-user
access returns 404, not 403, to avoid leaking existence (same posture
as C4 / files). File attachment requires the user to own *both* the
project AND the file. Skill attachment is registry-wide so any
authenticated user may attach any registered skill (skills are
filesystem-canonical per ADR 0004).

**Privileged constraint.** ``privileged=true`` requires
``minimum_inference_tier`` to be set. Enforced at three layers:
(1) the ``ProjectCreateRequest`` model rejects on create; (2) the PATCH
handler validates the merged state; (3) the DB CHECK constraint
``chk_projects_privileged_implies_tier`` is the safety net.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import ActiveUser
from app.db.session import get_db
from app.errors import Conflict, NotFound, ValidationError
from app.models.file import File as FileModel
from app.models.project import Project, ProjectFile, ProjectSkill
from app.schemas.projects import (
    SLUG_RE,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    slugify,
)
from app.skills.registry import MutableSkillRegistry

router = APIRouter(prefix="/projects", tags=["projects"])
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request bodies for attachment endpoints
# ---------------------------------------------------------------------------


class AttachFileRequest(BaseModel):
    """``POST /api/v1/projects/{id}/files`` body."""

    file_id: uuid.UUID


class AttachSkillRequest(BaseModel):
    """``POST /api/v1/projects/{id}/skills`` body."""

    skill_name: str = Field(min_length=1, max_length=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_project_id(project_id: str) -> uuid.UUID:
    """Reject non-UUID project ids per the OpenAPI sketch's ``{project_id}: uuid``."""

    try:
        return uuid.UUID(project_id)
    except ValueError as exc:
        raise ValidationError(
            "project_id must be a UUID",
            details={"project_id": project_id},
        ) from exc


async def _load_visible_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    include_archived: bool = False,
) -> Project:
    """Load a project row scoped to the caller; 404 on miss / cross-user / archived.

    The cross-user case collapses into 404 deliberately — same posture as
    C4 (files). Archived projects are also invisible by default; pass
    ``include_archived=True`` to surface them (used by the unarchive
    PATCH path so a caller can see and act on their own archived rows).
    """

    stmt = select(Project).where(
        Project.id == project_id,
        Project.owner_id == owner_id,
    )
    if not include_archived:
        stmt = stmt.where(Project.archived_at.is_(None))

    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFound(
            f"Project {project_id} not found.",
            details={"project_id": str(project_id)},
        )
    return row


async def _load_visible_file(
    db: AsyncSession,
    file_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> FileModel:
    """Load a file row scoped to the caller; 404 on miss / cross-user.

    Reuses the C4 file-visibility rule: the user must own the file and
    the file must not be soft-deleted.
    """

    stmt = select(FileModel).where(
        FileModel.id == file_id,
        FileModel.owner_id == owner_id,
        FileModel.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFound(
            f"File {file_id} not found.",
            details={"file_id": str(file_id)},
        )
    return row


async def _load_attached_file_ids(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Return file ids attached to a project, ordered by ``attached_at``."""

    stmt = (
        select(ProjectFile.file_id)
        .where(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.attached_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _load_attached_skill_names(db: AsyncSession, project_id: uuid.UUID) -> list[str]:
    """Return skill names attached to a project, ordered by ``attached_at``."""

    stmt = (
        select(ProjectSkill.skill_name)
        .where(ProjectSkill.project_id == project_id)
        .order_by(ProjectSkill.attached_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _serialize_project(db: AsyncSession, project: Project) -> ProjectResponse:
    """Build the ``ProjectResponse`` shape for a row.

    Two extra round-trips: one to fetch attached file ids, one to fetch
    attached skill names. Cheap on the M1 footprint (a project has a
    handful of attachments, not hundreds); a future optimisation could
    JOIN them in if it shows up in production.
    """

    file_ids = await _load_attached_file_ids(db, project.id)
    skill_names = await _load_attached_skill_names(db, project.id)
    return ProjectResponse(
        id=project.id,
        owner_id=project.owner_id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        context_md=project.context_md,
        privileged=project.privileged,
        minimum_inference_tier=project.minimum_inference_tier,
        attached_file_ids=file_ids,
        attached_skill_names=skill_names,
        archived_at=project.archived_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def _resolve_unique_slug(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    desired: str,
    exclude_project_id: uuid.UUID | None = None,
) -> str:
    """Return ``desired`` if free for the owner, else suffix with ``-2``, ``-3``, …

    ``exclude_project_id`` lets the PATCH path keep the project's own
    current slug without colliding with itself.
    """

    candidate = desired
    suffix = 2
    while True:
        stmt = select(Project.id).where(
            Project.owner_id == owner_id,
            Project.slug == candidate,
            Project.archived_at.is_(None),
        )
        if exclude_project_id is not None:
            stmt = stmt.where(Project.id != exclude_project_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            return candidate
        # Trim to fit the slug-length cap when adding a suffix.
        from app.schemas.projects import SLUG_MAX_LEN

        suffix_str = f"-{suffix}"
        head = desired[: SLUG_MAX_LEN - len(suffix_str)]
        candidate = f"{head}{suffix_str}"
        suffix += 1


def _registry(request: Request) -> MutableSkillRegistry:
    """Return the live in-memory skill registry from app state.

    Mirrors the helper in :mod:`app.api.skills`. Surfaces a typed
    InternalError if the lifespan handler hasn't installed the registry
    (this is a wiring bug, not a user error).
    """

    holder: MutableSkillRegistry | None = getattr(request.app.state, "skill_registry", None)
    if holder is None:
        from app.errors import InternalError

        raise InternalError(
            message="Skill registry is not initialised; the API process is "
            "not yet ready to serve project skill attachments.",
            details={"hint": "lifespan startup did not run"},
        )
    return holder


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
    description=(
        "Create a new project owned by the caller. ``slug`` is generated "
        "from ``name`` if omitted; collisions with the caller's existing "
        "active projects are resolved with a numeric suffix (``-2``, "
        "``-3``, …). Returns the canonical ``Project`` shape."
    ),
)
async def create_project(
    payload: ProjectCreateRequest,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectResponse:
    desired_slug = payload.slug or slugify(payload.name)
    final_slug = await _resolve_unique_slug(db, owner_id=user.id, desired=desired_slug)

    project = Project(
        owner_id=user.id,
        name=payload.name,
        slug=final_slug,
        description=payload.description,
        context_md=payload.context_md,
        privileged=payload.privileged,
        minimum_inference_tier=payload.minimum_inference_tier,
    )
    db.add(project)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        # Most likely cause is the partial UNIQUE index racing with a
        # parallel create; surface as 409. We re-derive the slug above
        # before flushing, so this is genuinely concurrent.
        raise Conflict(
            "Slug collision; another project with the same slug was "
            "created concurrently. Retry with a different slug.",
            details={"slug": final_slug},
        ) from exc

    await db.commit()
    await db.refresh(project)

    log.info(
        "project created",
        extra={
            "event": "project_created",
            "user_id": str(user.id),
            "project_id": str(project.id),
            "slug": project.slug,
            "privileged": project.privileged,
        },
    )

    return await _serialize_project(db, project)


@router.get(
    "",
    summary="List the caller's projects",
    description=(
        "Returns the caller's active projects by default. "
        "``archived=true`` returns archived projects only; "
        "``archived=false`` is equivalent to omitting the parameter."
    ),
    response_model=list[ProjectResponse],
)
async def list_projects(
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    archived: bool | None = Query(
        default=None,
        description="When true, return only archived projects.",
    ),
) -> list[ProjectResponse]:
    stmt = select(Project).where(Project.owner_id == user.id)
    if archived is True:
        stmt = stmt.where(Project.archived_at.is_not(None))
    else:
        # Default and ``archived=false`` both exclude archived rows.
        stmt = stmt.where(Project.archived_at.is_(None))
    stmt = stmt.order_by(Project.created_at.desc())

    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    return [await _serialize_project(db, row) for row in rows]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Fetch a single project (with attachments)",
)
async def get_project(
    project_id: str,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectResponse:
    pid = _validate_project_id(project_id)
    # Archived projects are visible to their owner via direct GET so
    # the client can render an "archived" detail page; the list endpoint
    # excludes them by default.
    project = await _load_visible_project(db, pid, user.id, include_archived=True)
    return await _serialize_project(db, project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Partial update of a project",
)
async def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectResponse:
    pid = _validate_project_id(project_id)
    project = await _load_visible_project(db, pid, user.id, include_archived=True)

    update_fields = payload.model_dump(exclude_unset=True)

    if "name" in update_fields:
        project.name = update_fields["name"]

    if "slug" in update_fields:
        new_slug = update_fields["slug"]
        if new_slug is None:
            # Disallow clearing the slug — it must always be present.
            raise ValidationError(
                "slug cannot be cleared; supply a non-empty value or omit the field.",
            )
        if not SLUG_RE.match(new_slug):
            raise ValidationError(
                "slug must match the pattern lowercase-letters-digits-and-dashes.",
                details={"slug": new_slug},
            )
        if new_slug != project.slug:
            project.slug = await _resolve_unique_slug(
                db,
                owner_id=user.id,
                desired=new_slug,
                exclude_project_id=project.id,
            )

    if "description" in update_fields:
        project.description = update_fields["description"]

    if "context_md" in update_fields:
        project.context_md = update_fields["context_md"]

    # Apply privileged / tier together so we can validate the merged
    # state. If the caller sets either, we re-check the cross-field rule
    # against the post-update values.
    privileged_set = "privileged" in update_fields
    tier_set = "minimum_inference_tier" in update_fields
    new_privileged = update_fields["privileged"] if privileged_set else project.privileged
    new_tier = (
        update_fields["minimum_inference_tier"] if tier_set else project.minimum_inference_tier
    )
    if new_privileged and new_tier is None:
        raise ValidationError(
            "minimum_inference_tier must be set when privileged=true.",
            details={"field": "minimum_inference_tier"},
        )
    if privileged_set:
        project.privileged = new_privileged
    if tier_set:
        project.minimum_inference_tier = new_tier

    if "archived" in update_fields:
        # Map the boolean PATCH flag to ``archived_at`` semantics.
        from datetime import UTC, datetime

        archived = update_fields["archived"]
        if archived is True and project.archived_at is None:
            project.archived_at = datetime.now(tz=UTC)
        elif archived is False and project.archived_at is not None:
            # Unarchive: must not collide with an active project that
            # already holds the slug. Re-resolve to a free variant.
            project.slug = await _resolve_unique_slug(
                db,
                owner_id=user.id,
                desired=project.slug,
                exclude_project_id=project.id,
            )
            project.archived_at = None

    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(
            "Project update conflicted with current state.",
            details={"project_id": str(project.id)},
        ) from exc

    await db.refresh(project)

    log.info(
        "project updated",
        extra={
            "event": "project_updated",
            "user_id": str(user.id),
            "project_id": str(project.id),
            "fields": sorted(update_fields.keys()),
        },
    )

    return await _serialize_project(db, project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a project",
    description=(
        "Sets ``archived_at`` on the row. Hard-delete is owned by D6. "
        "Idempotent: a second delete on an already-archived project "
        "returns 404."
    ),
    response_class=Response,
)
async def delete_project(
    project_id: str,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    pid = _validate_project_id(project_id)
    # NOT include_archived — already-archived returns 404 (idempotent
    # for clients that retry).
    project = await _load_visible_project(db, pid, user.id, include_archived=False)

    from datetime import UTC, datetime

    project.archived_at = datetime.now(tz=UTC)
    await db.commit()

    log.info(
        "project archived",
        extra={
            "event": "project_archived",
            "user_id": str(user.id),
            "project_id": str(pid),
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Attachment endpoints — files
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/files",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Attach a file to a project",
    description=(
        "Body: ``{file_id}``. The caller must own both the project and "
        "the file (cross-user → 404 on either side). Re-attaching an "
        "already-attached file returns 409."
    ),
    response_class=Response,
)
async def attach_file(
    project_id: str,
    payload: AttachFileRequest,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    pid = _validate_project_id(project_id)
    project = await _load_visible_project(db, pid, user.id)
    file_row = await _load_visible_file(db, payload.file_id, user.id)

    # Capture as plain UUIDs before the write — these are needed for
    # the conflict-error envelope and the structured log; after a
    # rollback the ORM expires its row attributes and dereferencing
    # them lazily would re-query the (now-rolled-back) session.
    project_uuid = project.id
    file_uuid = file_row.id

    join = ProjectFile(project_id=project_uuid, file_id=file_uuid)
    db.add(join)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # Composite-PK violation = already attached. 409 is the right
        # shape for an idempotency-violating attach (POST is not
        # idempotent; a separate DELETE removes the join).
        raise Conflict(
            "File is already attached to this project.",
            details={
                "project_id": str(project_uuid),
                "file_id": str(file_uuid),
            },
        ) from exc

    log.info(
        "project file attached",
        extra={
            "event": "project_file_attached",
            "user_id": str(user.id),
            "project_id": str(project_uuid),
            "file_id": str(file_uuid),
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{project_id}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a file from a project",
    description=(
        "Idempotent: removing a file that is not attached returns 404. "
        "The file row itself is untouched (use DELETE /api/v1/files/{id} "
        "for the file)."
    ),
    response_class=Response,
)
async def detach_file(
    project_id: str,
    file_id: str,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    pid = _validate_project_id(project_id)
    try:
        fid = uuid.UUID(file_id)
    except ValueError as exc:
        raise ValidationError(
            "file_id must be a UUID",
            details={"file_id": file_id},
        ) from exc

    # Verify the project is visible to the caller before peeking at the
    # join — otherwise a cross-user request could distinguish "file
    # exists but not attached" from "project exists but not yours."
    await _load_visible_project(db, pid, user.id)

    stmt = select(ProjectFile).where(
        ProjectFile.project_id == pid,
        ProjectFile.file_id == fid,
    )
    result = await db.execute(stmt)
    join = result.scalar_one_or_none()
    if join is None:
        raise NotFound(
            "File is not attached to this project.",
            details={
                "project_id": str(pid),
                "file_id": str(fid),
            },
        )

    await db.delete(join)
    await db.commit()

    log.info(
        "project file detached",
        extra={
            "event": "project_file_detached",
            "user_id": str(user.id),
            "project_id": str(pid),
            "file_id": str(fid),
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Attachment endpoints — skills
# ---------------------------------------------------------------------------


@router.post(
    "/{project_id}/skills",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Attach a skill to a project",
    description=(
        "Body: ``{skill_name}``. The skill must exist in the in-memory "
        "registry (registry-wide; no per-user check). Re-attaching an "
        "already-attached skill returns 409."
    ),
    response_class=Response,
)
async def attach_skill(
    project_id: str,
    payload: AttachSkillRequest,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> Response:
    pid = _validate_project_id(project_id)
    project = await _load_visible_project(db, pid, user.id)

    holder = _registry(request)
    registry = holder.current()
    if registry.get(payload.skill_name) is None:
        raise NotFound(
            f"Skill {payload.skill_name!r} is not in the registry.",
            details={"skill_name": payload.skill_name},
        )

    # Capture as plain UUID before the write — see attach_file for
    # the rationale (post-rollback ORM lazy-load avoidance).
    project_uuid = project.id

    join = ProjectSkill(project_id=project_uuid, skill_name=payload.skill_name)
    db.add(join)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict(
            "Skill is already attached to this project.",
            details={
                "project_id": str(project_uuid),
                "skill_name": payload.skill_name,
            },
        ) from exc

    log.info(
        "project skill attached",
        extra={
            "event": "project_skill_attached",
            "user_id": str(user.id),
            "project_id": str(project_uuid),
            "skill_name": payload.skill_name,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{project_id}/skills/{skill_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a skill from a project",
    response_class=Response,
)
async def detach_skill(
    project_id: str,
    skill_name: str,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    pid = _validate_project_id(project_id)
    await _load_visible_project(db, pid, user.id)

    stmt = select(ProjectSkill).where(
        ProjectSkill.project_id == pid,
        ProjectSkill.skill_name == skill_name,
    )
    result = await db.execute(stmt)
    join = result.scalar_one_or_none()
    if join is None:
        raise NotFound(
            "Skill is not attached to this project.",
            details={
                "project_id": str(pid),
                "skill_name": skill_name,
            },
        )

    await db.delete(join)
    await db.commit()

    log.info(
        "project skill detached",
        extra={
            "event": "project_skill_detached",
            "user_id": str(user.id),
            "project_id": str(pid),
            "skill_name": skill_name,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = [
    "attach_file",
    "attach_skill",
    "create_project",
    "delete_project",
    "detach_file",
    "detach_skill",
    "get_project",
    "list_projects",
    "router",
    "update_project",
]
