"""files.created_by_run_id — work-product provenance (C7a, fork, ADR-F046)

Additive-nullable column tying a file to the agent run that produced it (e.g. a
redline output). NULL for human uploads — no backfill. ``ON DELETE SET NULL`` so
deleting a run never cascades into the work product the lawyer downloads; the
file outlives the run record.

This is the link the cockpit uses to (a) list a matter's files in a Documents
tab and (b) surface the redlined ``.docx`` inline under the run that created it.

Revision ID: 0071
Revises: 0070
Create Date: 2026-06-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("created_by_run_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_files_created_by_run_id",
        "files",
        "agent_runs",
        ["created_by_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_files_created_by_run_id", "files", type_="foreignkey")
    op.drop_column("files", "created_by_run_id")
