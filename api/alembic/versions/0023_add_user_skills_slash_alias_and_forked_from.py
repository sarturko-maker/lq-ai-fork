"""add user_skills.slash_alias and user_skills.forked_from

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_skills", sa.Column("slash_alias", sa.Text(), nullable=True))
    op.add_column("user_skills", sa.Column("forked_from", sa.Text(), nullable=True))

    op.create_check_constraint(
        "chk_user_skills_slash_alias_format",
        "user_skills",
        "slash_alias IS NULL OR slash_alias ~ '^/[a-z0-9-]{1,32}$'",
    )

    # Unique per (owner_user_id, slash_alias) for active user-scope rows only.
    # Mirrors the existing slug-uniqueness partial-index pattern.
    op.create_index(
        "idx_user_skills_slash_alias_owner_active",
        "user_skills",
        ["owner_user_id", "slash_alias"],
        unique=True,
        postgresql_where=sa.text(
            "slash_alias IS NOT NULL AND archived_at IS NULL AND scope = 'user'"
        ),
    )

    # Team-scope analogue (one alias per team).
    op.create_index(
        "idx_user_skills_slash_alias_team_active",
        "user_skills",
        ["owner_team_id", "slash_alias"],
        unique=True,
        postgresql_where=sa.text(
            "slash_alias IS NOT NULL AND archived_at IS NULL AND scope = 'team'"
        ),
    )


def downgrade() -> None:
    op.drop_index("idx_user_skills_slash_alias_team_active", table_name="user_skills")
    op.drop_index("idx_user_skills_slash_alias_owner_active", table_name="user_skills")
    op.drop_constraint("chk_user_skills_slash_alias_format", "user_skills", type_="check")
    op.drop_column("user_skills", "forked_from")
    op.drop_column("user_skills", "slash_alias")
