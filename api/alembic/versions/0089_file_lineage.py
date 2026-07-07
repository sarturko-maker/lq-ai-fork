"""files.parent_file_id + files.is_snapshot — document lineage (R-1, fork, ADR-F066)

Additive columns for redline continuity. ``parent_file_id`` ties a derived
document to the row it was derived from: a redline/response output points at
its source document; the editor's first-save snapshot points at the live row
whose prior bytes it preserves. ``ON DELETE SET NULL`` so deleting a source
never cascades into the work product. ``is_snapshot`` marks those WOPI
first-save copies as immutable prior versions, so the working-version resolver
can walk the lineage chain to the newest NON-snapshot leaf and continue from
the agent's own latest output instead of re-redlining the original. NULL /
false for existing rows — no backfill (pre-F066 outputs simply carry no
lineage).

Revision ID: 0089
Revises: 0088
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("parent_file_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "files",
        sa.Column("is_snapshot", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_foreign_key(
        "fk_files_parent_file_id",
        "files",
        "files",
        ["parent_file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # The resolver walks child rows by parent — index the join column.
    op.create_index("ix_files_parent_file_id", "files", ["parent_file_id"])


def downgrade() -> None:
    op.drop_index("ix_files_parent_file_id", table_name="files")
    op.drop_constraint("fk_files_parent_file_id", "files", type_="foreignkey")
    op.drop_column("files", "is_snapshot")
    op.drop_column("files", "parent_file_id")
