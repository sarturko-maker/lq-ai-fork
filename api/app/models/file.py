"""File ORM model — per docs/db-schema.md §`files`.

Original uploaded files; the bytes themselves live in object storage
(MinIO/S3) at `storage_path`. Metadata (filename, mime_type, size_bytes,
hash_sha256, ingestion_status) lives in this row.

Lifecycle (M1):

* Created on `POST /api/v1/files` (Task C4) with `ingestion_status='pending'`.
* Picked up by the document pipeline worker (Task C5) which flips status
  through `processing` → `ready` or `failed`.
* Soft-deleted on `DELETE /api/v1/files/{id}` (Task C4) — `deleted_at` is
  set to `now()`; the MinIO bytes are NOT reaped synchronously (per
  `docs/adr/0005-file-storage-soft-delete-and-key-scheme.md`).

`project_id` references `projects(id)` once that table exists (Task C7);
0003 leaves it nullable without an FK constraint and a future migration
adds the FK.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class File(Base):
    """A single uploaded file.

    `storage_path` is the MinIO object key; per ADR 0005 we use the bare
    UUID as the key (no prefix) so the column carries the same string
    as `id`. The column is TEXT (not UUID) to leave room for a future
    migration that layers prefixes (`tenants/<tenant>/<file_id>`)
    without an ALTER on the column type.
    """

    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_files_owner_id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    ingestion_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'pending'"),
    )
    ingestion_error: Mapped[str | None] = mapped_column(String, nullable=True)
    # Work-product provenance (C7a, ADR-F046): the agent run that produced this
    # file (e.g. a redline output). NULL for human uploads. ``SET NULL`` on run
    # delete keeps the file (the work product outlives the run record). Lets the
    # cockpit tie a downloadable output back to the run that made it.
    created_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL", name="fk_files_created_by_run_id"),
        nullable=True,
    )
    # Document lineage (R-1, ADR-F066): the row this one was derived from — a
    # redline/response output points at its source document; the editor's
    # first-save snapshot points at the live row whose prior bytes it preserves.
    # NULL for original uploads. ``SET NULL`` on parent delete keeps the
    # derivative. The working-version resolver walks this chain.
    parent_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("files.id", ondelete="SET NULL", name="fk_files_parent_file_id"),
        nullable=True,
    )
    # ADR-F066: True marks an immutable prior-version copy (the WOPI first-save
    # snapshot) — never a working version; the resolver skips these leaves.
    is_snapshot: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    # Content last-modified time. NULL until the file's bytes are first mutated
    # in place (the in-app editor's PutFile save-back, ADR-F047 Slice 3): every
    # other write path creates a NEW row rather than mutating one, so for them
    # ``created_at`` already IS the last-modified time. WOPI ``LastModifiedTime``
    # therefore reads ``updated_at or created_at`` (and a save-back also makes
    # the ``X-COOL-WOPI-Timestamp`` "changed in storage" race-check meaningful).
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<File id={self.id} owner_id={self.owner_id} "
            f"filename={self.filename!r} size={self.size_bytes} "
            f"status={self.ingestion_status} deleted={self.deleted_at is not None}>"
        )
