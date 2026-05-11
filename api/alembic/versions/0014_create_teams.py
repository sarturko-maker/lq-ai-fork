"""create teams and team_members; close user_skills.owner_team_id FK — Task D8.1a

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-10

ADR 0012 §"Out of scope" listed team-scope CRUD as deferred to D8.1.
This migration lands the structural piece — the ``teams`` table that
gives the ``user_skills.owner_team_id`` column a real FK target, plus
a ``team_members`` join table for membership.

D8.1a (this migration) ships the schema + admin-only team management
endpoints; D8.1b (a follow-on) wires the team-scope branches into
``/api/v1/user-skills`` CRUD and the gateway's
``/internal/skills/{slug}`` resolution middle slot. Splitting it this
way keeps each commit reviewable and lets the operator-admin invite
people into teams before the user_skills surface lights up.

Membership model: operator-admin-controlled. ``is_admin`` users create
teams + add/remove members. Each membership row carries a ``role``
(``admin`` or ``member``); team-admins gain mutate rights on the team's
user_skills rows once D8.1b lands. Tracking ``added_by_user_id`` makes
membership changes forensically traceable in audit logs that index by
actor.

The ``owner_team_id`` FK on ``user_skills`` is added here with
``ON DELETE CASCADE`` — deleting a team archives all its skills
implicitly. The 0013-era partial UNIQUE index on
``(owner_team_id, slug) WHERE scope='team' AND archived_at IS NULL``
was already in place and now becomes enforceable.

Reversible: ``downgrade()`` drops the FK, drops team_members, drops
teams. Existing user_skills with ``scope='team'`` rows would block the
downgrade (the FK CASCADE deletes them on team removal, but
downgrading the FK itself with team rows present is fine — the
constraint just goes away).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- teams -------------------------------------------------------------
    op.create_table(
        "teams",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="RESTRICT",
                name="fk_teams_created_by",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_teams_slug"),
    )

    op.execute(
        "CREATE TRIGGER trg_teams_updated_at "
        "BEFORE UPDATE ON teams "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # --- team_members ------------------------------------------------------
    op.create_table(
        "team_members",
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "teams.id",
                ondelete="CASCADE",
                name="fk_team_members_team",
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_team_members_user",
            ),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "added_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id",
                ondelete="RESTRICT",
                name="fk_team_members_added_by",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("team_id", "user_id", name="pk_team_members"),
        sa.CheckConstraint(
            "role IN ('admin', 'member')",
            name="ck_team_members_role_enum",
        ),
    )

    op.create_index(
        "idx_team_members_user",
        "team_members",
        ["user_id"],
    )

    # --- user_skills.owner_team_id FK closure ------------------------------
    op.create_foreign_key(
        constraint_name="fk_user_skills_team",
        source_table="user_skills",
        referent_table="teams",
        local_cols=["owner_team_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_user_skills_team", "user_skills", type_="foreignkey"
    )
    op.drop_index("idx_team_members_user", table_name="team_members")
    op.drop_table("team_members")
    op.execute("DROP TRIGGER IF EXISTS trg_teams_updated_at ON teams")
    op.drop_table("teams")
