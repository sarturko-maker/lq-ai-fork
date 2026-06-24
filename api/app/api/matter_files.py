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

from app.api.dependencies import ActiveUser
from app.api.projects import _load_visible_project
from app.db.session import get_db
from app.models.file import File
from app.models.project import ProjectFile

router = APIRouter(prefix="/matters", tags=["matter-files"])


class MatterFileRead(BaseModel):
    """One file in a matter, as the cockpit Documents tab renders it.

    ``created_by_run_id`` is the work-product provenance (ADR-F046): non-NULL for an
    agent output (e.g. a redline), NULL for a human upload. The run timeline filters
    on it to show the download inline under the run that produced the file.
    """

    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    ingestion_status: str
    created_at: datetime
    created_by_run_id: uuid.UUID | None


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
                created_by_run_id=f.created_by_run_id,
            )
            for f in rows
        ],
    )
