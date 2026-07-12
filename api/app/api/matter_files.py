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
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools import duplicate_groups_from_rows, is_summary_stale
from app.api.dependencies import ActiveUser, MutatingUser
from app.api.projects import _load_visible_project
from app.db.session import get_db
from app.models.file import File
from app.models.project import ProjectFile
from app.schemas.document_summary import RecordDocumentSummaryInput

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
    # 'agent' | 'human' | None — who wrote the summary (the panel labels a lawyer-set one).
    summary_author: str | None
    # True when the file's bytes were mutated AFTER the summary was written (editor
    # save-back / redline convergence) — the description may no longer match the content.
    summary_stale: bool
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

    # WORKSPACE-3 (ADR-F082): exact-duplicate markers, computed by the SAME pure rule the
    # agent sees (duplicate_groups_from_rows — hash-grouped, earliest-created canonical) over
    # the rows already fetched, so the panel and the agent never disagree about what is a copy
    # and the matter's files are queried once.
    dup = duplicate_groups_from_rows(rows)

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
                summary_author=f.summary_author,
                summary_stale=is_summary_stale(f),
                duplicate_of=(
                    DuplicateRef(id=dup[f.id][0], filename=dup[f.id][1]) if f.id in dup else None
                ),
            )
            for f in rows
        ],
    )


class SummaryWrite(BaseModel):
    """The supervising lawyer's summary correction (ADR-F082 / ADR-F042 human-owns-after).

    ``summary = null`` clears the recorded summary entirely. A non-null summary is validated
    by the same boundary rules as the agent's write (one line, capped, no reserved
    duplicate-marker text) — the human's text rides the same prompt surfaces.
    """

    summary: str | None


@router.put("/{project_id}/files/{file_id}/summary", response_model=MatterFileRead)
async def set_file_summary(
    project_id: uuid.UUID,
    file_id: uuid.UUID,
    body: SummaryWrite,
    user: MutatingUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MatterFileRead:
    """Set or clear a matter file's summary — the human half of auto-write-then-correct.

    The agent maintains summaries automatically (``record_document_summary``); this is the
    supervising lawyer's control AFTER the write (ADR-F042): correct a wrong or poisoned
    description, or clear it. A human-set summary is authoritative — the agent tool refuses
    to overwrite it (``summary_author='human'`` pins win). Owner-scoped, 404 on miss /
    cross-user / archived matter / foreign file (never 403 — no existence leak); viewer
    role excluded (``MutatingUser``, ADR-F064).
    """
    project = await _load_visible_project(db, project_id, user.id)
    file = (
        await db.execute(
            select(File)
            .outerjoin(
                ProjectFile,
                and_(ProjectFile.file_id == File.id, ProjectFile.project_id == project.id),
            )
            .where(
                File.id == file_id,
                or_(ProjectFile.project_id.is_not(None), File.project_id == project.id),
                File.owner_id == user.id,
                File.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")

    if body.summary is None:
        file.summary = None
        file.summary_updated_at = None
        file.summary_run_id = None
        file.summary_author = None
    else:
        # Reuse the agent boundary's validation (one line, cap, reserved-marker rejection) —
        # the human's text rides the same prompt surfaces. 422 on violation.
        try:
            proposal = RecordDocumentSummaryInput(
                document_name=file.filename or "-", summary=body.summary
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()[0]["msg"]) from exc
        file.summary = proposal.summary
        file.summary_updated_at = datetime.now(tz=UTC)
        file.summary_run_id = None
        file.summary_author = "human"
    await db.commit()
    await db.refresh(file)

    # An honest duplicate_of on the response (the client may replace its cached row):
    # same pure rule over the matter's live rows.
    matter_rows = (
        await db.execute(
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
        )
    ).scalars()
    dup = duplicate_groups_from_rows(list(matter_rows))

    return MatterFileRead(
        id=file.id,
        filename=file.filename,
        mime_type=file.mime_type,
        size_bytes=file.size_bytes,
        ingestion_status=file.ingestion_status,
        created_at=file.created_at,
        updated_at=file.updated_at,
        created_by_run_id=file.created_by_run_id,
        summary=file.summary,
        summary_author=file.summary_author,
        summary_stale=is_summary_stale(file),
        duplicate_of=(
            DuplicateRef(id=dup[file.id][0], filename=dup[file.id][1]) if file.id in dup else None
        ),
    )
