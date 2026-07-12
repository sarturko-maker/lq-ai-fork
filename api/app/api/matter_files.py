"""Matter-files endpoint — C7a (fork, ADR-F046): the work-product download surface.

The commercial agent already persists its redlined ``.docx`` as a matter-scoped
``File`` (``commercial_tools._apply_redline``) and the bytes are downloadable via the
existing ``GET /api/v1/files/{file_id}/content``. What was missing is a way for the
cockpit to *find* that output: this read-only listing returns a matter's files with
the metadata the Documents tab renders + the ``created_by_run_id`` provenance the run
timeline uses to surface the redline inline under the run that produced it.

**Per-user isolation.** The matter is loaded via the projects ``_load_visible_project``
rule: owner-scoped, archived-excluded, **404** on miss / cross-user / archived (never
403 — no existence leak), the same posture as the matter-memory surface. The file list
is then scoped to the matter (membership union + owner re-assertion + not soft-deleted),
mirroring the agent layer's ``tools._matter_files_query`` so what the lawyer sees here
is the same set the agent reads. Metadata only — filenames/sizes/status, never bytes
and never document content. Bytes flow only through the audited per-file content route.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import MatterBinding, duplicate_of_map
from app.api.dependencies import ActiveUser
from app.api.projects import _load_visible_project
from app.db.session import get_db
from app.models.file import File
from app.models.project import ProjectFile

router = APIRouter(prefix="/matters", tags=["matter-files"])


class DuplicateRef(BaseModel):
    """The canonical file an exact duplicate points at (WORKSPACE-3, ADR-F082)."""

    id: uuid.UUID
    filename: str


class MatterFileRead(BaseModel):
    """One file in a matter, as the cockpit Documents tab renders it.

    ``created_by_run_id`` is the work-product provenance (ADR-F046/F081): non-NULL for
    an agent output (e.g. a redline) — since ADR-F081 it names the run that LAST WROTE
    the bytes, not only the row's creator — NULL for a human upload or a file the
    lawyer has since edited. The run timeline filters on it to show the download
    inline under the run. ``updated_at`` is non-NULL once the bytes have been mutated
    in place (an editor save-back, ADR-F047, or a redline convergence, ADR-F081); the
    web keys its "new redline ready" announce on ``(id, updated_at)`` so an in-place
    update re-fires it. ``summary`` is the agent-recorded description (ADR-F082,
    NULL until the agent has read the file); ``duplicate_of`` is non-NULL when this
    file is a byte-identical copy of an earlier matter file — computed server-side
    from the stored content hash (``duplicate_of_map``, never persisted and never
    model-asserted) and scoped to this matter/owner, so no raw hash and no cross-
    matter existence signal ever leaves the API.
    """

    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    ingestion_status: str
    created_at: datetime
    updated_at: datetime | None
    created_by_run_id: uuid.UUID | None
    summary: str | None
    duplicate_of: DuplicateRef | None


class MatterFilesRead(BaseModel):
    """The matter's files, newest-first."""

    project_id: uuid.UUID
    files: list[MatterFileRead]


@router.get("/{project_id}/files", response_model=MatterFilesRead)
async def list_matter_files(
    project_id: uuid.UUID,
    user: ActiveUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MatterFilesRead:
    """List a matter's files (metadata only), newest-first.

    Owner-scoped (404 on miss / cross-user / archived). An empty-but-existing matter
    returns an empty list (not 404). The scope is the membership union the agent reads:
    files attached via ``project_files`` OR persisted with ``File.project_id`` (the
    redline output path), re-asserting ``owner_id`` and excluding soft-deleted rows.
    """
    project = await _load_visible_project(db, project_id, user.id)

    stmt = (
        select(File)
        .outerjoin(
            ProjectFile,
            and_(ProjectFile.file_id == File.id, ProjectFile.project_id == project.id),
        )
        .where(
            or_(ProjectFile.project_id.is_not(None), File.project_id == project.id),
            File.owner_id == user.id,
            File.deleted_at.is_(None),
        )
        .order_by(File.created_at.desc(), File.id)
    )
    rows = (await db.execute(stmt)).scalars().all()

    # WORKSPACE-3 (ADR-F082): exact-duplicate markers, computed by the SAME rule the
    # agent sees (duplicate_of_map — matter+owner scoped, hash-grouped, earliest-created
    # canonical) so the panel and the agent never disagree about what is a copy.
    dup = await duplicate_of_map(
        db,
        MatterBinding(
            project_id=project.id,
            user_id=user.id,
            name=project.name,
            privileged=project.privileged,
            minimum_inference_tier=project.minimum_inference_tier,
            practice_area_id=project.practice_area_id,
        ),
    )

    return MatterFilesRead(
        project_id=project.id,
        files=[
            MatterFileRead(
                id=f.id,
                filename=f.filename,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                ingestion_status=f.ingestion_status,
                created_at=f.created_at,
                updated_at=f.updated_at,
                created_by_run_id=f.created_by_run_id,
                summary=f.summary,
                duplicate_of=(
                    DuplicateRef(id=dup[f.id][0], filename=dup[f.id][1]) if f.id in dup else None
                ),
            )
            for f in rows
        ],
    )
