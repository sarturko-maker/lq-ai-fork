"""agent_runs.project_id — F0-S4 (fork)

Binds a deep-agent run to a Matter (``projects`` row) so the runner can
inject the matter's document tools (``search_documents`` /
``read_document``) and forward the matter's privilege/tier floor on the
run's gateway envelope (ADR-F002; CLAUDE.md memory model — unit of work).

Nullable: a run without a matter is a blank workspace (no document
tools injected). ``ON DELETE SET NULL`` — deleting a project unbinds
its runs but preserves the run records (projects soft-delete via
``archived_at`` in normal operation; the hard-delete path only exists
for cascades).

Partial index for the F1 matter-scoped run listing; cheap to carry now,
saves a migration later.

Revision ID: 0049
Revises: 0048
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL", name="fk_agent_runs_project_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_agent_runs_project",
        "agent_runs",
        ["project_id"],
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_agent_runs_project", table_name="agent_runs")
    op.drop_column("agent_runs", "project_id")
