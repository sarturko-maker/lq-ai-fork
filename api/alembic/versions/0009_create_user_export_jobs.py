"""create user_export_jobs — Task D6

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-09

Adds the ``user_export_jobs`` table per docs/db-schema.md §`user_export_jobs`.
Backs the GDPR Article 20 export endpoint pair:

* ``POST /api/v1/users/me/export`` inserts a queued row + enqueues an
  arq job; returns the job id for polling.
* ``GET  /api/v1/users/me/export/{job_id}`` reads the row's status
  and (when complete) returns a presigned download URL good for 24h.

Storage shape:

* ``status`` is TEXT + CHECK rather than a Postgres ENUM so adding a
  state later doesn't require a schema migration; the running set is
  ``queued | processing | completed | failed``.
* ``storage_key`` carries the MinIO key (``exports/<user_id>/<job_id>.zip``)
  the worker writes to; cleared by the GC cron once ``expires_at`` passes.
* ``expires_at`` is set at completion to ``now() + 7 days``; the partial
  index covers GC-eligible rows so the cron's scan is tight.
* ON DELETE CASCADE on ``user_id`` so the D6 hard-delete worker can drop
  a user without first deleting their export jobs.

Reversible: downgrade drops the table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_export_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_export_jobs_user_id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="chk_user_export_jobs_status",
        ),
    )

    # Listing / status-poll index — most-recent-first per user.
    op.execute(
        "CREATE INDEX idx_user_export_jobs_user_created "
        "ON user_export_jobs (user_id, created_at DESC)"
    )

    # GC scan index — partial on rows that still have bytes to reap so
    # the hourly cron sweep stays cheap as the table grows.
    op.execute(
        "CREATE INDEX idx_user_export_jobs_expires "
        "ON user_export_jobs (expires_at) "
        "WHERE storage_key IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("idx_user_export_jobs_expires", table_name="user_export_jobs")
    op.drop_index("idx_user_export_jobs_user_created", table_name="user_export_jobs")
    op.drop_table("user_export_jobs")
