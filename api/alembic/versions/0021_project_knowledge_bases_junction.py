"""project_knowledge_bases junction table

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-12

Junction for matter (project) <-> knowledge_base many-to-many.
Composite PK; FK CASCADE on either side; attached_at + attached_by
for audit ordering. Required for Wave D.1 KB attach modal (spec §7.3).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_knowledge_bases",
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "attached_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("attached_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            ondelete="CASCADE",
            name="fk_pkb_project_id",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["knowledge_bases.id"],
            ondelete="CASCADE",
            name="fk_pkb_kb_id",
        ),
        sa.ForeignKeyConstraint(
            ["attached_by_user_id"], ["users.id"],
            ondelete="SET NULL",
            name="fk_pkb_attached_by",
        ),
        sa.PrimaryKeyConstraint("project_id", "knowledge_base_id"),
    )
    op.create_index(
        "idx_pkb_kb_id", "project_knowledge_bases", ["knowledge_base_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_pkb_kb_id", table_name="project_knowledge_bases")
    op.drop_table("project_knowledge_bases")
