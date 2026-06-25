"""files.updated_at — content last-modified time for editor save-back (Slice 3, ADR-F047)

The in-app Word editor's PutFile save-back (ADR-F047 Slice 3) is the only path
that mutates a file's bytes *in place* (every other write path creates a new
row). It stamps ``updated_at`` so WOPI ``LastModifiedTime`` reflects the save
and the ``X-COOL-WOPI-Timestamp`` "changed in storage" race-check is meaningful.

Nullable, no backfill: a NULL ``updated_at`` means "never edited in place", and
the WOPI host reads ``updated_at or created_at`` so existing rows keep reporting
their ``created_at`` as the last-modified time. Additive only.

Revision ID: 0075
Revises: 0074
Create Date: 2026-06-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("files", "updated_at")
