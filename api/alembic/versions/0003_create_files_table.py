"""create files table — Task C4

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08

Adds the `files` table per docs/db-schema.md §`files`. Original uploaded
files; the bytes themselves live in object storage (MinIO/S3) at
`storage_path`. Metadata (filename, mime_type, size_bytes, hash_sha256,
ingestion_status) lives here.

Notes:
- Per ADR 0004, deletion is soft (`deleted_at` flips from NULL to now()).
  The MinIO bytes outlive the soft-delete and are reaped later by D6
  per-user export+delete or a future operator-facing GC sweep.
- `project_id` is nullable and the FK is deferred — `projects` does not
  exist until C7. We keep the column NULL-only here and add the FK
  constraint when C7's migration lands.
- Per A2's choice (and the deferred UUIDv7 migration item) we use
  `gen_random_uuid()` (UUIDv4) — `pgcrypto` is already enabled by 0001.
- `ingestion_status` defaults to `'pending'`; C5 (document pipeline)
  flips it through `processing` → `ready` (or `failed`).
- Indexes: owner-active (the listing index for C7), project-active,
  status-pending-or-processing (the C5 worker's pickup index), and
  hash for dedup detection (PRD §3.5).

Reversible: downgrade drops the table (CASCADE removes the indexes).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_files_owner_id"),
            nullable=False,
        ),
        # `project_id` references projects(id) — but `projects` does not
        # exist yet (lands in C7). The column is nullable; we hold off on
        # the FK constraint until C7's migration ALTERs to add it. The
        # OpenAPI sketch's File schema has `project_id` as nullable too.
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("hash_sha256", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "ingestion_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("ingestion_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "ingestion_status IN ('pending','processing','ready','failed')",
            name="chk_files_ingestion_status",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="chk_files_size_nonneg",
        ),
    )

    # Listing index: owner's active files, newest-first. C7's project
    # service will use this for the file-picker; the C5 worker uses it
    # too when it polls per-owner queues.
    op.execute(
        """
        CREATE INDEX idx_files_owner_active
            ON files (owner_id, created_at DESC)
            WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        CREATE INDEX idx_files_project
            ON files (project_id)
            WHERE project_id IS NOT NULL AND deleted_at IS NULL
        """
    )

    # Pickup index for the C5 document pipeline worker — narrow to the
    # statuses the worker cares about.
    op.execute(
        """
        CREATE INDEX idx_files_status
            ON files (ingestion_status)
            WHERE ingestion_status IN ('pending','processing')
        """
    )

    # Dedup detection index per PRD §3.5: a future "you already uploaded
    # this file" affordance does a hash lookup before re-running ingestion.
    op.execute("CREATE INDEX idx_files_hash ON files (hash_sha256)")


def downgrade() -> None:
    op.drop_table("files")
