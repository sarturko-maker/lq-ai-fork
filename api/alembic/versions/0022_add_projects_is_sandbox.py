"""add projects.is_sandbox

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "is_sandbox",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Partial index keeps the default matters-list query fast.
    op.create_index(
        "idx_projects_not_sandbox",
        "projects",
        ["owner_id", "created_at"],
        postgresql_where=sa.text("is_sandbox = false AND archived_at IS NULL"),
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_projects_not_sandbox", table_name="projects")
    op.drop_column("projects", "is_sandbox")
